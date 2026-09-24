"""Бенчмарк поиска пути: A*/JPS/поле потока, rust_core против Python-двойника.

    python tools/bench_pathfinding.py [--seed 1] [--size 256] [--density 0.2] [--queries 200]

Сетка size x size со случайными стенами (одна цена), запросы - случайные пары клеток
из одной связной области. Без rust_core (или со старым колесом) печатает только Python-строки.
Результаты детерминированы по seed (время - нет).
"""
import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.gameplay import pathfinding as pf  # noqa: E402

HAS_RUST = "rust" in pf.available_backends()


def make_grid(rng: random.Random, size: int, density: float) -> bytes:
    return bytes(0 if rng.random() < density else 1 for _ in range(size * size))


def main_component(size: int, costs: bytes, rng: random.Random) -> list:
    """Клетки одной связной области (достижимые из случайной клетки): пары из неё всегда достижимы."""
    backend = "rust" if HAS_RUST else "python"
    free = [(i % size, i // size) for i, c in enumerate(costs) if c]
    best = []
    for _ in range(3):                       # три пробы: берём самую большую область
        hub = rng.choice(free)
        dist = pf.flow_field(size, size, costs, hub, backend=backend).distances()
        comp = [(i % size, i // size) for i, d in enumerate(dist) if d != float("inf")]
        if len(comp) > len(best):
            best = comp
    return best


def timed(fn, repeat: int = 1) -> float:
    """Среднее время одного вызова fn в мс."""
    t0 = time.perf_counter()
    for _ in range(repeat):
        fn()
    return (time.perf_counter() - t0) * 1000.0 / repeat


def bench_queries(size, costs, pairs, algorithm, backend) -> float:
    t0 = time.perf_counter()
    for a, b in pairs:
        pf.find_path(size, size, costs, a, b, algorithm, backend=backend)
    return (time.perf_counter() - t0) * 1000.0 / len(pairs)


def check_parity(size, costs, pairs) -> float:
    """Макс. расхождение стоимости путей между всеми вариантами на первых запросах (не в замере)."""
    worst = 0.0
    for a, b in pairs[:25]:
        costs_of = []
        for backend, algorithm in [("python", "astar"), ("python", "jps")] + \
                ([("rust", "astar"), ("rust", "jps")] if HAS_RUST else []):
            path = pf.find_path(size, size, costs, a, b, algorithm, backend=backend)
            costs_of.append(pf.path_cost(size, size, costs, path))
        worst = max(worst, max(costs_of) - min(costs_of))
    return worst


def row(name: str, ms: float, base: float) -> str:
    return f"  {name:<28}{ms:>12.3f}{base / ms:>12.1f}x"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--size", type=int, default=256)
    ap.add_argument("--density", type=float, default=0.2, help="доля стен")
    ap.add_argument("--queries", type=int, default=200)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    size = args.size
    costs = make_grid(rng, size, args.density)
    comp = main_component(size, costs, rng)
    pairs = [(rng.choice(comp), rng.choice(comp)) for _ in range(args.queries)]
    pairs = [(a, b) if a != b else (a, comp[0] if comp[0] != a else comp[-1]) for a, b in pairs]

    print(f"pathfinding benchmark: seed={args.seed} grid={size}x{size} walls={args.density:.0%} uniform cost, "
          f"{len(pairs)} reachable queries (connected area: {len(comp)} cells)")
    if not HAS_RUST:
        print("rust_core has no pathfinding kernels: Python rows only "
              "(cd rust_core && maturin develop --release)")
    worst = check_parity(size, costs, pairs)
    print(f"path cost parity across A*/JPS/Rust/Python on 25 queries: max diff {worst:.2e}")

    print("\nsingle query, ms/query (speedup vs Python A*)")
    print(f"  {'':<28}{'ms/query':>12}{'speedup':>13}")
    py_astar = bench_queries(size, costs, pairs, "astar", "python")
    print(row("Python A*", py_astar, py_astar))
    print(row("Python JPS", bench_queries(size, costs, pairs, "jps", "python"), py_astar))
    if HAS_RUST:
        rust_astar = bench_queries(size, costs, pairs, "astar", "rust")
        rust_jps = bench_queries(size, costs, pairs, "jps", "rust")
        print(row("Rust A*", rust_astar, py_astar))
        print(row("Rust JPS", rust_jps, py_astar))

    print("\nflow field compute, ms per field (whole grid)")
    print(f"  {'':<28}{'ms':>12}{'speedup':>13}")
    target = comp[len(comp) // 2]
    py_flow = timed(lambda: pf.flow_field(size, size, costs, target, backend="python"), repeat=3)
    print(row("Python flow field", py_flow, py_flow))
    if HAS_RUST:
        print(row("Rust flow field", timed(lambda: pf.flow_field(size, size, costs, target, backend="rust"), repeat=30),
                  py_flow))

    if HAS_RUST:
        print("\nN enemies chasing one target, ms per round (Rust)")
        print(f"  {'N':<6}{'N x A*':>12}{'N x JPS':>12}{'1 flow field':>15}{'flow speedup':>15}")
        rounds = 20
        for n in (10, 50):
            t_astar = t_jps = t_flow = 0.0
            for _ in range(rounds):
                tg = rng.choice(comp)
                enemies = [rng.choice(comp) for _ in range(n)]
                t0 = time.perf_counter()
                for e in enemies:
                    pf.find_path(size, size, costs, e, tg, "astar", backend="rust")
                t_astar += time.perf_counter() - t0
                t0 = time.perf_counter()
                for e in enemies:
                    pf.find_path(size, size, costs, e, tg, "jps", backend="rust")
                t_jps += time.perf_counter() - t0
                t0 = time.perf_counter()
                field = pf.flow_field(size, size, costs, tg, backend="rust")
                for e in enemies:                         # каждый враг спрашивает свой шаг
                    field.direction(*e)
                t_flow += time.perf_counter() - t0
            a, j, f = (t * 1000.0 / rounds for t in (t_astar, t_jps, t_flow))
            print(f"  {n:<6}{a:>12.3f}{j:>12.3f}{f:>15.3f}{a / f:>14.1f}x")

        # для сравнения: открытая карта, где JPS обычно выигрывает у A*
        open_costs = make_grid(rng, size, 0.02)
        open_comp = main_component(size, open_costs, rng)
        open_pairs = [(rng.choice(open_comp), rng.choice(open_comp)) for _ in range(args.queries)]
        open_pairs = [(a, b) for a, b in open_pairs if a != b] or open_pairs
        oa = bench_queries(size, open_costs, open_pairs, "astar", "rust")
        oj = bench_queries(size, open_costs, open_pairs, "jps", "rust")
        print(f"\nfor comparison, open map (2% walls), Rust ms/query: A* {oa:.3f}, JPS {oj:.3f} "
              f"({oa / oj:.1f}x)")


if __name__ == "__main__":
    main()
