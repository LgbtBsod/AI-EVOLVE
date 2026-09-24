"""Поиск пути по сетке: A*, Jump Point Search и поле потока (flow field).

Ядра живут в rust_core (rust_core.find_path / flow_field / FlowField, файл
rust_core/src/simulation/pathfinding.rs); здесь тот же алгоритм на Python -
двойник даёт те же пути и те же стоимости (тот же порядок операций над float,
тот же порядок раскрытия узлов), это проверяет tests/test_pathfinding.py.
Если rust_core не собран или устарел (нет find_path) - работает двойник.

Семантика (одинаковая в обеих реализациях):
- сетка width x height, `costs` по строкам: 0 - стена, 1..255 - цена ВХОДА в клетку;
- 8 направлений; шаг по прямой стоит cost(клетки назначения), по диагонали -
  sqrt(2) * cost(клетки назначения); срезать угол нельзя: диагональ допустима,
  только если обе ортогональные соседние клетки проходимы;
- find_path -> [(x, y), ...] от start до goal включительно; [] если пути нет,
  старт/цель - стена или вне сетки; [start] если start == goal;
- algorithm: "astar" (эвристика octile * минимальная цена), "jps" (только для
  сетки с одной ценой у всех проходимых клеток, иначе ValueError; путь
  оптимален и развёрнут по клеткам), "auto" (jps при равных ценах, иначе astar);
- flow_field(target) - Дейкстра от цели: distance(x, y) - стоимость пути из
  клетки в цель, direction(x, y) - шаг, ведущий к цели по оптимальному пути.

Бэкенд: BACKEND ("rust" | "python"); переменная окружения AI_EVOLVE_PATHFINDING=python
или backend="python" в вызове принудительно выбирают двойник (для тестов).
"""
from __future__ import annotations

import heapq
import math
import os
from typing import Iterable, Optional, Sequence

try:
    import rust_core as _rc
except ImportError:
    _rc = None

_RUST_FIND = getattr(_rc, "find_path", None)
_RUST_FLOW = getattr(_rc, "flow_field", None)
_RUST_OK = _RUST_FIND is not None and _RUST_FLOW is not None

ENV = "AI_EVOLVE_PATHFINDING"
BACKEND = "rust" if _RUST_OK and os.environ.get(ENV, "").strip().lower() != "python" else "python"

ALGORITHMS = ("auto", "astar", "jps")
SQRT2 = math.sqrt(2.0)
# Порядок соседей (он же порядок разрешения ничьих): прямые, потом диагонали.
DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, 1), (-1, -1), (1, -1))

__all__ = ["ALGORITHMS", "BACKEND", "DIRS", "ENV", "PyFlowField", "SQRT2", "available_backends",
           "find_path", "flow_field", "path_cost"]


def available_backends() -> tuple:
    return ("python", "rust") if _RUST_OK else ("python",)


def _use_rust(backend: Optional[str]) -> bool:
    if backend is None:
        return BACKEND == "rust"
    if backend == "python":
        return False
    if backend == "rust":
        if not _RUST_OK:
            raise RuntimeError("rust_core has no pathfinding kernels (cd rust_core && maturin develop --release)")
        return True
    raise ValueError(f"unknown backend {backend!r}: expected 'rust' or 'python'")


def _prepare(width: int, height: int, costs) -> tuple:
    """(width, height, costs как bytes/bytearray); ValueError для кривых размеров и цен."""
    w, h = int(width), int(height)
    if w < 0 or h < 0:
        raise ValueError("width and height must be >= 0")
    if not isinstance(costs, (bytes, bytearray)):
        costs = bytes(costs)            # ValueError, если цена вне 0..255
    if len(costs) != w * h:
        raise ValueError(f"costs has {len(costs)} cells, expected {w * h}")
    return w, h, costs


def _octile(dx: int, dy: int, min_cost: float) -> float:
    dx, dy = abs(dx), abs(dy)
    lo, hi = (dx, dy) if dx < dy else (dy, dx)
    return min_cost * (hi - lo + lo * SQRT2)


# --------------------------------------------------------------------------- A*

def _astar(w: int, h: int, costs, start: tuple, goal: tuple, min_cost: float) -> list:
    n = w * h
    s, t = start[1] * w + start[0], goal[1] * w + goal[0]
    gx, gy = goal
    g = [math.inf] * n
    parent = [-1] * n
    closed = bytearray(n)
    g[s] = 0.0
    h0 = _octile(start[0] - gx, start[1] - gy, min_cost)
    heap = [(h0, h0, s)]
    push, pop = heapq.heappush, heapq.heappop
    while heap:
        _f, _h, cur = pop(heap)
        if closed[cur]:
            continue
        closed[cur] = 1
        if cur == t:
            break
        cy, cx = divmod(cur, w)
        gc = g[cur]
        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            if nx < 0 or ny < 0 or nx >= w or ny >= h:
                continue
            ni = ny * w + nx
            c = costs[ni]
            if not c or closed[ni]:
                continue
            if dx and dy:
                if not costs[cy * w + nx] or not costs[ny * w + cx]:
                    continue
                ng = gc + SQRT2 * c
            else:
                ng = gc + 1.0 * c
            if ng < g[ni]:
                g[ni] = ng
                parent[ni] = cur
                hh = _octile(nx - gx, ny - gy, min_cost)
                push(heap, (ng + hh, hh, ni))
    if not closed[t]:
        return []
    path = []
    cur = t
    while cur != -1:
        cy, cx = divmod(cur, w)
        path.append((cx, cy))
        cur = parent[cur]
    path.reverse()
    return path


# --------------------------------------------------------------------------- JPS

def _jps(w: int, h: int, costs, start: tuple, goal: tuple) -> list:
    """Jump Point Search для сетки с одной ценой (единицы - клетки: цена не влияет на путь).

    Диагональ - только при обеих проходимых ортогональных клетках. При таком правиле
    у диагонального хода нет вынужденных соседей, а у прямого хода вынужденная
    клетка - боковая (x, y+s), если (x-dx, y+s) стена: её берём и диагональ за ней.
    """
    W = w + 2                                    # рамка из стен: проверки границ не нужны
    pad = bytearray(W * (h + 2))
    for y in range(h):
        o = (y + 1) * W + 1
        pad[o:o + w] = costs[y * w:(y + 1) * w]
    s = (start[1] + 1) * W + start[0] + 1
    t = (goal[1] + 1) * W + goal[0] + 1
    gx, gy = goal[0] + 1, goal[1] + 1

    def jump(i: int, dx: int, dy: int) -> int:
        """Следующая точка прыжка от клетки i по направлению (dx, dy) или -1."""
        if dy == 0:
            while True:
                j = i + dx
                if not pad[j]:
                    return -1
                i = j
                if i == t:
                    return i
                if (not pad[i - dx + W] and pad[i + W]) or (not pad[i - dx - W] and pad[i - W]):
                    return i
        if dx == 0:
            off = dy * W
            while True:
                j = i + off
                if not pad[j]:
                    return -1
                i = j
                if i == t:
                    return i
                if (not pad[i - off + 1] and pad[i + 1]) or (not pad[i - off - 1] and pad[i - 1]):
                    return i
        oy = dy * W
        off = oy + dx
        while True:
            if not (pad[i + dx] and pad[i + oy] and pad[i + off]):
                return -1
            i += off
            if i == t:
                return i
            if jump(i, dx, 0) >= 0 or jump(i, 0, dy) >= 0:
                return i

    n = len(pad)
    g = [math.inf] * n
    parent = [-1] * n
    closed = bytearray(n)
    g[s] = 0.0
    h0 = _octile(start[0] + 1 - gx, start[1] + 1 - gy, 1.0)
    heap = [(h0, h0, s)]
    push, pop = heapq.heappush, heapq.heappop
    while heap:
        _f, _h, cur = pop(heap)
        if closed[cur]:
            continue
        closed[cur] = 1
        if cur == t:
            break
        cy, cx = divmod(cur, W)
        p = parent[cur]
        if p < 0:
            dirs = DIRS
        else:
            py, px = divmod(p, W)
            dx = (cx > px) - (cx < px)
            dy = (cy > py) - (cy < py)
            if dx and dy:
                dirs = ((dx, 0), (0, dy), (dx, dy))
            elif dy == 0:
                dirs = [(dx, 0)]
                for sd in (1, -1):
                    if not pad[cur - dx + sd * W] and pad[cur + sd * W]:
                        dirs.append((0, sd))
                        dirs.append((dx, sd))
            else:
                dirs = [(0, dy)]
                for sd in (1, -1):
                    if not pad[cur + sd - dy * W] and pad[cur + sd]:
                        dirs.append((sd, 0))
                        dirs.append((sd, dy))
        gc = g[cur]
        for dx, dy in dirs:
            j = jump(cur, dx, dy)
            if j < 0 or closed[j]:
                continue
            jy, jx = divmod(j, W)
            steps = max(abs(jx - cx), abs(jy - cy))
            ng = gc + steps * (SQRT2 if dx and dy else 1.0)
            if ng < g[j]:
                g[j] = ng
                parent[j] = cur
                hh = _octile(jx - gx, jy - gy, 1.0)
                push(heap, (ng + hh, hh, j))
    if not closed[t]:
        return []
    jumps = []
    cur = t
    while cur != -1:
        jumps.append(divmod(cur, W))
        cur = parent[cur]
    jumps.reverse()
    path = [(jumps[0][1] - 1, jumps[0][0] - 1)]
    for (ay, ax), (by, bx) in zip(jumps, jumps[1:]):
        sx, sy = (bx > ax) - (bx < ax), (by > ay) - (by < ay)
        while (ax, ay) != (bx, by):
            ax += sx
            ay += sy
            path.append((ax - 1, ay - 1))
    return path


def _find_path_py(w: int, h: int, costs, start: tuple, goal: tuple, algorithm: str) -> list:
    if algorithm not in ALGORITHMS:
        raise ValueError(f"unknown algorithm {algorithm!r}: expected one of {ALGORITHMS}")
    prices = set(costs)
    prices.discard(0)
    uniform = len(prices) <= 1
    if algorithm == "jps" and not uniform:
        raise ValueError("jps needs a uniform-cost grid (all passable cells share one cost)")
    use_jps = algorithm == "jps" or (algorithm == "auto" and uniform)
    for x, y in (start, goal):
        if x < 0 or y < 0 or x >= w or y >= h or not costs[y * w + x]:
            return []
    if start == goal:
        return [start]
    if use_jps:
        return _jps(w, h, costs, start, goal)
    return _astar(w, h, costs, start, goal, float(min(prices)))


def find_path(width: int, height: int, costs: Sequence[int], start: tuple, goal: tuple,
              algorithm: str = "auto", backend: Optional[str] = None) -> list:
    """Оптимальный путь [(x, y), ...] от start до goal (см. описание модуля)."""
    if algorithm not in ALGORITHMS:
        raise ValueError(f"unknown algorithm {algorithm!r}: expected one of {ALGORITHMS}")
    w, h, cs = _prepare(width, height, costs)
    st, gl = (int(start[0]), int(start[1])), (int(goal[0]), int(goal[1]))
    if _use_rust(backend):
        return _RUST_FIND(w, h, bytes(cs), st, gl, algorithm)
    return _find_path_py(w, h, cs, st, gl, algorithm)


# --------------------------------------------------------------------- flow field

class PyFlowField:
    """Python-двойник rust_core.FlowField: расстояния Дейкстры от цели."""

    def __init__(self, width: int, height: int, costs, target: tuple):
        w, h, cs = _prepare(width, height, costs)
        self.width, self.height, self.target = w, h, (int(target[0]), int(target[1]))
        self._costs = bytes(cs)
        n = w * h
        dist = [math.inf] * n
        tx, ty = self.target
        if 0 <= tx < w and 0 <= ty < h and cs[ty * w + tx]:
            t = ty * w + tx
            dist[t] = 0.0
            done = bytearray(n)
            heap = [(0.0, t)]
            push, pop = heapq.heappush, heapq.heappop
            while heap:
                d, cur = pop(heap)
                if done[cur]:
                    continue
                done[cur] = 1
                y, x = divmod(cur, w)
                cost_here = cs[cur]
                for dx, dy in DIRS:              # ход из соседа (x-dx, y-dy) в cur
                    px, py = x - dx, y - dy
                    if px < 0 or py < 0 or px >= w or py >= h:
                        continue
                    pi = py * w + px
                    if not cs[pi] or done[pi]:
                        continue
                    if dx and dy:
                        if not cs[y * w + px] or not cs[py * w + x]:
                            continue
                        nd = d + SQRT2 * cost_here
                    else:
                        nd = d + 1.0 * cost_here
                    if nd < dist[pi]:
                        dist[pi] = nd
                        push(heap, (nd, pi))
        self._dist = dist

    def distance(self, x: int, y: int) -> Optional[float]:
        if x < 0 or y < 0 or x >= self.width or y >= self.height:
            return None
        d = self._dist[y * self.width + x]
        return None if d == math.inf else d

    def direction(self, x: int, y: int) -> Optional[tuple]:
        """Шаг (dx, dy) к цели по оптимальному пути; None в цели, в стене и без пути."""
        w, h, cs, dist = self.width, self.height, self._costs, self._dist
        if x < 0 or y < 0 or x >= w or y >= h or dist[y * w + x] in (0.0, math.inf):
            return None
        best, out = math.inf, None
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if nx < 0 or ny < 0 or nx >= w or ny >= h:
                continue
            ni = ny * w + nx
            if not cs[ni] or dist[ni] == math.inf:
                continue
            if dx and dy:
                if not cs[y * w + nx] or not cs[ny * w + x]:
                    continue
                v = dist[ni] + SQRT2 * cs[ni]
            else:
                v = dist[ni] + 1.0 * cs[ni]
            if v < best:
                best, out = v, (dx, dy)
        return out

    def distances(self) -> list:
        """Расстояния по строкам, math.inf - нет пути."""
        return list(self._dist)

    def directions(self) -> list:
        """Плоский список [dx0, dy0, dx1, dy1, ...] по клеткам в порядке строк; (0, 0) - нет шага."""
        out = []
        for y in range(self.height):
            for x in range(self.width):
                d = self.direction(x, y)
                out.extend(d if d else (0, 0))
        return out


def flow_field(width: int, height: int, costs: Sequence[int], target: tuple, backend: Optional[str] = None):
    """Поле потока к цели: .distance(x, y), .direction(x, y), .directions(), .distances()."""
    w, h, cs = _prepare(width, height, costs)
    tg = (int(target[0]), int(target[1]))
    if _use_rust(backend):
        return _RUST_FLOW(w, h, bytes(cs), tg)
    return PyFlowField(w, h, cs, tg)


# --------------------------------------------------------------------------- utils

def path_cost(width: int, height: int, costs: Sequence[int], path: Iterable[tuple]) -> float:
    """Стоимость пути по правилам сетки; ValueError, если шаг недопустим (стена, не сосед, срез угла)."""
    w, h, cs = _prepare(width, height, costs)
    total, prev = 0.0, None
    for x, y in path:
        if x < 0 or y < 0 or x >= w or y >= h or not cs[y * w + x]:
            raise ValueError(f"cell {(x, y)} is blocked or out of bounds")
        if prev is not None:
            dx, dy = x - prev[0], y - prev[1]
            if (dx, dy) not in DIRS:
                raise ValueError(f"step {prev} -> {(x, y)} is not between neighbours")
            if dx and dy and (not cs[prev[1] * w + x] or not cs[y * w + prev[0]]):
                raise ValueError(f"step {prev} -> {(x, y)} cuts a corner")
            total += (SQRT2 if dx and dy else 1.0) * cs[y * w + x]
        prev = (x, y)
    return total
