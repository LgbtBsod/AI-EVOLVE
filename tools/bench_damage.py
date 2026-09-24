"""Damage pipeline benchmark: the Python twin vs the Rust kernel (one call per hit) vs the Rust batch, hits per second.

    python tools/bench_damage.py [--seed 1] [--hits 20000] [--repeat 3] [--mix neutral|rich]

`neutral` = today's hits (armor + crit only), `rich` = every stage active (accuracy, dodge, block, resistance,
penetration, variance). The rolls are pre-drawn (no RNG in the timing); the twin and the Rust kernel must agree bit
for bit on every hit (checked, not timed). Without a rust_core that has the kernel only the Python line is printed.
Results are deterministic by seed, the times are not.
"""
import argparse
import random
import sys
import time
from array import array
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.effects import damage as dmg  # noqa: E402

HAS_RUST = "rust" in dmg.available_backends()


def make_hits(rng: random.Random, n: int, mix: str) -> tuple:
    """(params rows, rolls rows): a mix of hits like the game's (neutral) or with every stage on (rich)."""
    rich = mix == "rich"
    rows, rolls = [], []
    for _ in range(n):
        rows.append(dmg.Params(
            amount=rng.uniform(5, 60), flags=float(rng.choice((0, 0, 0, 3, 6))),
            accuracy=rng.uniform(0, 30) if rich else 0.0, evasion=rng.uniform(0, 60) if rich else 0.0,
            dodge=rng.uniform(0, 0.2) if rich else 0.0, block_chance=rng.uniform(0, 40) if rich else 0.0,
            block_bonus=rng.uniform(0, 20) if rich else 0.0, crit_chance=rng.uniform(0, 0.3), crit_mult=1.5,
            type_mod=rng.uniform(-10, 40) if rich else 0.0, resist=rng.uniform(-20, 70) if rich else 0.0,
            resist_pen=rng.uniform(0, 30) if rich else 0.0, armor=rng.uniform(0, 25),
            pen_pct=rng.uniform(0, 40) if rich else 0.0, pen_flat=rng.uniform(0, 5) if rich else 0.0,
            taken=rng.uniform(-10, 30) if rich else 0.0))
        rolls.append(tuple(rng.random() for _ in range(dmg.ROLLS)))
    return rows, rolls


def per_second(n: int, seconds: float) -> str:
    return f"{n / seconds:>12,.0f} hits/s ({seconds * 1e6 / n:6.2f} us/hit)"


def best(fn, repeat: int) -> float:
    """Fastest of `repeat` runs, seconds."""
    out = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        out.append(time.perf_counter() - t0)
    return min(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--hits", type=int, default=20000)
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--mix", choices=("neutral", "rich"), default=None, help="default: both")
    args = ap.parse_args(argv)
    consts = dmg.config().consts
    for mix in ([args.mix] if args.mix else ["neutral", "rich"]):
        rows, rolls = make_hits(random.Random(args.seed), args.hits, mix)
        pcols = [array("d", col) for col in zip(*rows, strict=True)]
        rcols = [array("d", col) for col in zip(*rolls, strict=True)]
        print(f"mix={mix} hits={args.hits} seed={args.seed} backend={dmg.BACKEND}")
        t_py = best(lambda: [dmg.resolve_hit_py(p, r, consts) for p, r in zip(rows, rolls, strict=True)], args.repeat)
        print(f"  python twin      {per_second(args.hits, t_py)}")
        t_pyb = best(lambda: dmg.resolve_hits(pcols, rcols, consts, backend="python"), args.repeat)
        print(f"  python batch     {per_second(args.hits, t_pyb)}")
        if not HAS_RUST:
            continue
        t_one = best(lambda: [dmg.resolve_hit(p, r, consts, backend="rust") for p, r in zip(rows, rolls, strict=True)],
                     args.repeat)
        t_batch = best(lambda: dmg.resolve_hits(pcols, rcols, consts, backend="rust"), args.repeat)
        print(f"  rust single      {per_second(args.hits, t_one)}   x{t_py / t_one:.1f} vs twin")
        print(f"  rust batch       {per_second(args.hits, t_batch)}   x{t_py / t_batch:.1f} vs twin")
        fast, slow = dmg.resolve_hits(pcols, rcols, consts, backend="rust"), dmg.resolve_hits(pcols, rcols, consts,
                                                                                                backend="python")
        same = all(a.tobytes() == b.tobytes() for a, b in zip(fast, slow, strict=True))
        print(f"  parity           {'bit for bit' if same else 'MISMATCH'} on {args.hits} hits")
        if not same:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
