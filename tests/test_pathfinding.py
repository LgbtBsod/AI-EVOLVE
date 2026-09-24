"""Поиск пути по сетке (src/gameplay/pathfinding.py): A*, JPS, поле потока.

Ручные случаи, случайные сетки (пути допустимы, JPS == A*, поле потока == A*) и паритет
rust_core <-> Python-двойник. Без собранного rust_core (или со старым колесом без find_path)
работают только двойник и его проверки: паритет пропускается.
Только двойник, как в CI без cargo:  AI_EVOLVE_PATHFINDING=python pytest tests/test_pathfinding.py
"""
import importlib
import math
import os
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.gameplay import pathfinding as pf  # noqa: E402

BACKENDS = pf.available_backends()
HAS_RUST = "rust" in BACKENDS
SQRT2 = math.sqrt(2.0)
TOL = 1e-6


@pytest.fixture(params=BACKENDS)
def backend(request):
    return request.param


def parse(rows):
    """ASCII-карта -> (w, h, costs): '#' стена, '.' цена 1, цифра - цена."""
    costs = bytearray()
    for row in rows:
        for ch in row:
            costs.append(0 if ch == "#" else 1 if ch in ".SG" else int(ch))
    return len(rows[0]), len(rows), bytes(costs)


def random_grid(rng, weighted=None):
    w, h = rng.randint(5, 64), rng.randint(5, 64)
    density = rng.choice([0.0, 0.05, 0.15, 0.25, 0.4])
    if weighted is None:
        weighted = rng.random() < 0.5
    base = rng.randint(1, 4)
    costs = bytes(0 if rng.random() < density else (rng.randint(1, 9) if weighted else base) for _ in range(w * h))
    return w, h, costs


def free_cells(w, costs):
    return [(i % w, i // w) for i, c in enumerate(costs) if c]


def is_uniform(costs):
    return len(set(costs) - {0}) <= 1


def follow(field, start, target, w, h, costs):
    """Идём по field.direction от start; стоимость пройденного пути (проверяет допустимость шагов)."""
    cell, cells = start, [start]
    while cell != target:
        d = field.direction(*cell)
        assert d is not None, f"no direction at {cell}"
        cell = (cell[0] + d[0], cell[1] + d[1])
        cells.append(cell)
        assert len(cells) <= w * h + 1, "the field loops"
    return pf.path_cost(w, h, costs, cells)


# ------------------------------------------------------------------ hand-made cases

@pytest.mark.parametrize("algorithm", ["auto", "astar", "jps"])
def test_open_grid(backend, algorithm):
    w, h, costs = parse(["......"] * 4)
    path = pf.find_path(w, h, costs, (0, 0), (5, 3), algorithm, backend=backend)
    assert path[0] == (0, 0) and path[-1] == (5, 3)
    assert pf.path_cost(w, h, costs, path) == pytest.approx(2 + 3 * SQRT2, abs=TOL)
    assert len(path) == 6                     # 3 диагонали + 2 прямых


@pytest.mark.parametrize("algorithm", ["astar", "jps"])
def test_wall_with_a_gap(backend, algorithm):
    w, h, costs = parse(["..#..", "..#..", ".....", "..#..", "..#.."])
    path = pf.find_path(w, h, costs, (0, 0), (4, 0), algorithm, backend=backend)
    assert (2, 2) in path                     # единственный проход
    # в проём нельзя войти по диагонали (угол): 2 диагонали до и после + 4 прямых
    assert pf.path_cost(w, h, costs, path) == pytest.approx(4 + 2 * SQRT2, abs=TOL)


def test_unreachable(backend):
    w, h, costs = parse(["..#..", "..#..", "..#.."])
    for algorithm in ("auto", "astar", "jps"):
        assert pf.find_path(w, h, costs, (0, 0), (4, 2), algorithm, backend=backend) == []


def test_start_equals_goal(backend):
    w, h, costs = parse(["...", "...", "..."])
    for algorithm in ("auto", "astar", "jps"):
        assert pf.find_path(w, h, costs, (1, 1), (1, 1), algorithm, backend=backend) == [(1, 1)]


def test_blocked_and_outside_endpoints(backend):
    w, h, costs = parse(["..#..", "..#..", "..#.."])
    for algorithm in ("auto", "astar", "jps"):
        find = lambda a, b: pf.find_path(w, h, costs, a, b, algorithm, backend=backend)  # noqa: E731
        assert find((2, 1), (0, 0)) == []     # старт - стена
        assert find((0, 0), (2, 1)) == []     # цель - стена
        assert find((2, 1), (2, 1)) == []     # start == goal, но это стена
        assert find((-1, 0), (0, 0)) == []
        assert find((0, 0), (5, 0)) == []
        assert find((0, 3), (0, 0)) == []
        assert find((0, 0), (10 ** 12, 0)) == []


def test_empty_grid(backend):
    assert pf.find_path(0, 0, b"", (0, 0), (0, 0), backend=backend) == []
    assert pf.find_path(3, 3, bytes(9), (0, 0), (1, 1), backend=backend) == []
    assert pf.find_path(3, 3, bytes(9), (0, 0), (1, 1), "jps", backend=backend) == []


def test_corner_cutting_is_forbidden(backend):
    # обе ортогональные клетки - стены: по диагонали нельзя, обходного пути нет
    w, h, costs = parse(["S#", "#G"])
    for algorithm in ("astar", "jps"):
        assert pf.find_path(w, h, costs, (0, 0), (1, 1), algorithm, backend=backend) == []
    # одна из ортогональных клеток - стена: тоже нельзя, идём в обход
    w, h, costs = parse(["S#", ".G"])
    for algorithm in ("astar", "jps"):
        path = pf.find_path(w, h, costs, (0, 0), (1, 1), algorithm, backend=backend)
        assert path == [(0, 0), (0, 1), (1, 1)]
    # и поле потока не режет угол
    field = pf.flow_field(w, h, costs, (1, 1), backend=backend)
    assert field.direction(0, 0) == (0, 1)
    assert field.distance(0, 0) == pytest.approx(2.0, abs=TOL)


def test_weighted_detour_is_taken_when_cheaper(backend):
    w, h, costs = parse([".....", ".999.", "....."])
    path = pf.find_path(w, h, costs, (0, 1), (4, 1), backend=backend)          # auto -> A*
    assert (2, 1) not in path and (1, 1) not in path and (3, 1) not in path
    assert pf.path_cost(w, h, costs, path) == pytest.approx(2 + 2 * SQRT2, abs=TOL)
    with pytest.raises(ValueError):
        pf.find_path(w, h, costs, (0, 1), (4, 1), "jps", backend=backend)


def test_weighted_direct_route_is_kept_when_cheaper(backend):
    # дорога цены 2 прямо против обхода по цене 5: идём напрямую
    w, h, costs = parse(["55555", "22222", "55555"])
    path = pf.find_path(w, h, costs, (0, 1), (4, 1), backend=backend)
    assert path == [(x, 1) for x in range(5)]
    assert pf.path_cost(w, h, costs, path) == pytest.approx(8.0, abs=TOL)


def test_auto_picks_jps_on_uniform_and_astar_otherwise(backend):
    w, h, costs = parse(["....", "..#.", "...."])
    assert pf.find_path(w, h, costs, (0, 0), (3, 2), backend=backend) == \
        pf.find_path(w, h, costs, (0, 0), (3, 2), "jps", backend=backend)
    w, h, costs = parse(["....", "..#.", "..2."])
    assert pf.find_path(w, h, costs, (0, 0), (3, 2), backend=backend) == \
        pf.find_path(w, h, costs, (0, 0), (3, 2), "astar", backend=backend)


def test_uniform_cost_scales_the_path_cost_not_the_path(backend):
    w, h, costs = parse(["..#..", "..#..", ".....", "..#..", "..#.."])
    p1 = pf.find_path(w, h, costs, (0, 0), (4, 4), "jps", backend=backend)
    scaled = bytes(0 if c == 0 else 7 for c in costs)
    p7 = pf.find_path(w, h, scaled, (0, 0), (4, 4), "jps", backend=backend)
    assert p1 == p7
    assert pf.path_cost(w, h, scaled, p7) == pytest.approx(7 * pf.path_cost(w, h, costs, p1), abs=TOL)


# ------------------------------------------------------------------- API and input

def test_costs_may_be_bytes_bytearray_or_list(backend):
    w, h, costs = parse([".#.", "...", "..."])
    expected = pf.find_path(w, h, costs, (0, 0), (2, 0), backend=backend)
    assert expected
    assert pf.find_path(w, h, bytearray(costs), (0, 0), (2, 0), backend=backend) == expected
    assert pf.find_path(w, h, list(costs), (0, 0), (2, 0), backend=backend) == expected
    assert pf.find_path(w, h, costs, [0, 0], [2, 0], backend=backend) == expected


def test_bad_input_raises_value_error(backend):
    with pytest.raises(ValueError):
        pf.find_path(3, 3, bytes(8), (0, 0), (1, 1), backend=backend)             # неверная длина
    with pytest.raises(ValueError):
        pf.find_path(3, 3, bytes(9), (0, 0), (1, 1), "dijkstra", backend=backend)
    with pytest.raises(ValueError):
        pf.find_path(3, 3, [1, 2, 300, 1, 1, 1, 1, 1, 1], (0, 0), (1, 1), backend=backend)  # цена > 255
    with pytest.raises(ValueError):
        pf.flow_field(3, 3, bytes(8), (0, 0), backend=backend)
    with pytest.raises(ValueError):
        pf.find_path(3, 3, bytes(9), (0, 0), (1, 1), backend="gpu")


def test_flow_field_api(backend):
    w, h, costs = parse(["....", ".##.", "...."])
    field = pf.flow_field(w, h, costs, (3, 1), backend=backend)
    assert (field.width, field.height, tuple(field.target)) == (4, 3, (3, 1))
    assert field.distance(3, 1) == 0.0 and field.direction(3, 1) is None
    assert field.distance(1, 1) is None and field.direction(1, 1) is None      # стена
    assert field.distance(-1, 0) is None and field.distance(0, 3) is None      # вне сетки
    assert field.direction(-1, 0) is None and field.direction(9, 9) is None
    assert field.distance(0, 0) == pytest.approx(pf.path_cost(w, h, costs, pf.find_path(w, h, costs, (0, 0), (3, 1))), abs=TOL)
    flat = field.directions()
    assert len(flat) == 2 * w * h
    for y in range(h):
        for x in range(w):
            d = field.direction(x, y)
            assert (flat[2 * (y * w + x)], flat[2 * (y * w + x) + 1]) == (d if d else (0, 0))
    dists = field.distances()
    assert len(dists) == w * h
    assert dists[1 * w + 1] == math.inf and dists[1 * w + 3] == 0.0


def test_flow_field_unreachable_and_blocked_target(backend):
    w, h, costs = parse(["..#..", "..#..", "..#.."])
    field = pf.flow_field(w, h, costs, (0, 0), backend=backend)
    assert field.distance(1, 2) is not None and field.distance(4, 0) is None
    assert field.direction(4, 0) is None
    for target in ((2, 1), (-1, -1), (9, 9)):          # стена / вне сетки
        dead = pf.flow_field(w, h, costs, target, backend=backend)
        assert all(dead.distance(x, y) is None and dead.direction(x, y) is None
                   for x in range(w) for y in range(h))
        assert set(dead.directions()) == {0}


def test_path_cost_rejects_illegal_paths():
    w, h, costs = parse(["S#", ".G"])
    assert pf.path_cost(w, h, costs, [(0, 0), (0, 1), (1, 1)]) == pytest.approx(2.0, abs=TOL)
    for bad in ([(0, 0), (1, 1)],            # срез угла
                [(0, 0), (1, 0)],            # стена
                [(0, 0), (1, 1 + 5)],        # вне сетки
                [(0, 0), (0, 1), (0, 1)]):   # не сосед (шаг на месте)
        with pytest.raises(ValueError):
            pf.path_cost(w, h, costs, bad)


# ------------------------------------------------------------------- backend choice

def test_default_dispatch_follows_backend_variable(monkeypatch):
    w, h, costs = parse(["...", "...", "..."])

    def boom(*a, **k):
        raise AssertionError("the Rust kernel must not be called")

    monkeypatch.setattr(pf, "_RUST_FIND", boom)
    monkeypatch.setattr(pf, "_RUST_FLOW", boom)
    monkeypatch.setattr(pf, "BACKEND", "python")
    assert pf.find_path(w, h, costs, (0, 0), (2, 2)) == [(0, 0), (1, 1), (2, 2)]
    assert isinstance(pf.flow_field(w, h, costs, (2, 2)), pf.PyFlowField)
    assert isinstance(pf.flow_field(w, h, costs, (2, 2), backend="python"), pf.PyFlowField)

    calls = []
    monkeypatch.setattr(pf, "_RUST_FIND", lambda *a: calls.append(a) or [])
    monkeypatch.setattr(pf, "BACKEND", "rust")
    assert pf.find_path(w, h, costs, (0, 0), (2, 2)) == []       # ответ подставного ядра
    assert calls and calls[0][:2] == (3, 3) and calls[0][-1] == "auto"
    assert pf.find_path(w, h, costs, (0, 0), (2, 2), backend="python") == [(0, 0), (1, 1), (2, 2)]


def test_env_variable_forces_the_python_twin():
    saved = os.environ.get(pf.ENV)
    try:
        os.environ[pf.ENV] = "python"
        importlib.reload(pf)
        assert pf.BACKEND == "python"
        del os.environ[pf.ENV]
        importlib.reload(pf)
        assert pf.BACKEND == ("rust" if HAS_RUST else "python")
    finally:
        if saved is None:
            os.environ.pop(pf.ENV, None)
        else:
            os.environ[pf.ENV] = saved
        importlib.reload(pf)


def test_rust_backend_reports_a_clear_error_when_missing(monkeypatch):
    monkeypatch.setattr(pf, "_RUST_OK", False)
    with pytest.raises(RuntimeError):
        pf.find_path(3, 3, bytes([1] * 9), (0, 0), (1, 1), backend="rust")


# ------------------------------------------------------------- randomized (per backend)

@pytest.mark.parametrize("seed", range(60))
def test_random_grids_paths_are_valid_and_consistent(backend, seed):
    rng = random.Random(1000 + seed)
    w, h, costs = random_grid(rng, weighted=bool(seed % 2))
    free = free_cells(w, costs)
    if len(free) < 2:
        return
    uniform = is_uniform(costs)
    for _ in range(3):
        start, goal = rng.choice(free), rng.choice(free)
        astar = pf.find_path(w, h, costs, start, goal, "astar", backend=backend)
        field = pf.flow_field(w, h, costs, goal, backend=backend)
        d = field.distance(*start)
        if not astar:
            assert d is None
            assert pf.find_path(w, h, costs, start, goal, backend=backend) == []
            if uniform:
                assert pf.find_path(w, h, costs, start, goal, "jps", backend=backend) == []
            continue
        assert astar[0] == start and astar[-1] == goal
        cost = pf.path_cost(w, h, costs, astar)          # шаги соседние, без стен и срезов угла
        assert d is not None and d == pytest.approx(cost, abs=TOL)                 # поле == A*
        assert follow(field, start, goal, w, h, costs) == pytest.approx(cost, abs=TOL)
        auto = pf.find_path(w, h, costs, start, goal, backend=backend)
        assert pf.path_cost(w, h, costs, auto) == pytest.approx(cost, abs=TOL)
        if uniform:
            jps = pf.find_path(w, h, costs, start, goal, "jps", backend=backend)
            assert jps[0] == start and jps[-1] == goal
            assert pf.path_cost(w, h, costs, jps) == pytest.approx(cost, abs=TOL)  # JPS == A*
        else:
            with pytest.raises(ValueError):
                pf.find_path(w, h, costs, start, goal, "jps", backend=backend)


@pytest.mark.parametrize("seed", range(6))
def test_flow_field_reaches_the_target_from_every_reachable_cell(backend, seed):
    rng = random.Random(7000 + seed)
    w, h = rng.randint(5, 24), rng.randint(5, 24)
    palette = [0, 0, 1, 2, 3] if seed % 2 else [0, 1, 1, 1]
    costs = bytes(rng.choice(palette) for _ in range(w * h))
    free = free_cells(w, costs)
    if len(free) < 2:
        return
    target = rng.choice(free)
    field = pf.flow_field(w, h, costs, target, backend=backend)
    for cell in free:
        d = field.distance(*cell)
        if d is None:
            assert pf.find_path(w, h, costs, cell, target, "astar", backend=backend) == []
            assert field.direction(*cell) is None
        else:
            assert follow(field, cell, target, w, h, costs) == pytest.approx(d, abs=TOL)


# ------------------------------------------------------------- Rust <-> Python parity

@pytest.mark.skipif(not HAS_RUST, reason="rust_core without pathfinding kernels (rebuild: maturin develop --release)")
@pytest.mark.parametrize("seed", range(120))
def test_rust_matches_python_twin(seed):
    rng = random.Random(5000 + seed)
    w, h, costs = random_grid(rng, weighted=bool(seed % 2))
    free = free_cells(w, costs)
    if len(free) < 2:
        return
    uniform = is_uniform(costs)
    for _ in range(3):
        start, goal = rng.choice(free), rng.choice(free)
        for algorithm in (("astar", "auto", "jps") if uniform else ("astar", "auto")):
            rust = pf.find_path(w, h, costs, start, goal, algorithm, backend="rust")
            py = pf.find_path(w, h, costs, start, goal, algorithm, backend="python")
            assert bool(rust) == bool(py)
            if rust:
                assert pf.path_cost(w, h, costs, rust) == pytest.approx(pf.path_cost(w, h, costs, py), abs=TOL)
            assert rust == py             # тот же порядок раскрытия и те же float-операции: путь в путь
    target = rng.choice(free)
    fr = pf.flow_field(w, h, costs, target, backend="rust")
    fp = pf.flow_field(w, h, costs, target, backend="python")
    assert fr.distances() == pytest.approx(fp.distances(), abs=TOL)
    assert fr.directions() == fp.directions()
    for cell in rng.sample(free, min(20, len(free))):
        assert fr.distance(*cell) == pytest.approx(fp.distance(*cell), abs=TOL)
        assert fr.direction(*cell) == fp.direction(*cell)
