"""qa.py coverage - how many of the 60 corpus abilities (tests/fixtures/ability_corpus.json) the canon effect system can say today.

    qa.py coverage           # one line: canon / with_aliases / spec / target / floor | next kinds
    qa.py coverage --list    # + the still-blocked abilities grouped by blocking kind, most frequent first (orders the next slices)
    qa.py coverage --result  # machine form for the `coverage` check of qa.lua (FAIL under coverage.floor, warn under coverage.target)

An ability is expressible when every spec kind is an OP_HANDLERS key (canon) or an exact alias of lua_content/kind_aliases.lua and the
spec needs no addition (`lacks`). Data: `coverage` table of lua_content/qa.lua (floor = ratchet, never lowered; target; spec).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

import qa_report as R
from probe_settings import ROOT, qa_settings

CORPUS = ROOT / "tests" / "fixtures" / "ability_corpus.json"
FAMILIES = {"deal": "combat", "zone": "space", "aura": "space", "hypnosis": "control", "command": "control", "possess": "control",
            "dominance": "control", "perceive": "perception", "reveal": "perception", "precognition": "perception",
            "on_lethal": "trigger", "delay": "trigger", "transform": "form", "timed_power_up": "form", "stance": "form"}


def canon_kinds() -> set:
    sys.path.insert(0, str(ROOT))
    from src.effects.ops import OP_HANDLERS
    return set(OP_HANDLERS)


def alias_rows() -> dict:
    import lua_bridge
    return lua_bridge.load(ROOT / "lua_content" / "kind_aliases.lua").get("aliases") or {}


def blockers(ab: dict, known: set) -> list:
    """The spec kinds of an ability that `known` does not cover, plus its `lacks` additions (as `+name`)."""
    return [k for k in ab["spec_kinds"] if k not in known] + [f"+{x}" for x in ab["lacks"]]


def _pct(count: int, n: int) -> float:
    return round(100.0 * count / n, 1)


def _shares(corpus: list, blocked: list, canon: set) -> dict:
    """Counts of expressible abilities: by canon names, with exact aliases, by the author's hand tags, by the spec alone."""
    return {"canon": sum(1 for ab in corpus if not blockers(ab, canon)), "with_aliases": sum(1 for _, b in blocked if not b),
            "hand": sum(1 for ab in corpus if ab["hand_canon"]), "spec": sum(1 for ab in corpus if not ab["lacks"])}


def compute(corpus: list, canon: set, aliases: dict) -> dict:
    with_al = canon | {k for k, v in aliases.items() if v.get("exact") and v.get("canon") in canon}
    n = len(corpus)
    blocked = [(ab, blockers(ab, with_al)) for ab in corpus]
    shares = _shares(corpus, blocked, canon)
    return {"n": n, "canon_n": shares["canon"], "alias_n": shares["with_aliases"], "blocked": blocked,
            "freq": Counter(k for _, b in blocked for k in b), **{k: _pct(v, n) for k, v in shares.items()}}


def next_kinds(freq: Counter, k: int = 5) -> str:
    return " ".join(f"{name}({c} abilities, {FAMILIES.get(name, 'other')})" for name, c in freq.most_common(k)) or "-"


def line(c: dict, cfg: dict) -> str:
    return (f"coverage canon={c['canon']:.1f}% ({c['canon_n']}/{c['n']}) with_aliases={c['with_aliases']:.1f}% spec={c['spec']:.1f}% "
            f"target={cfg.get('target', 90)}% floor={cfg.get('floor', 0):.1f}% | next: {next_kinds(c['freq'])}")


def listing(c: dict) -> list:
    out = [f"hand tags={c['hand']:.1f}% (doc 46.7%); still blocked: {len(c['blocked']) and sum(1 for _, b in c['blocked'] if b)} of {c['n']}"]
    for kind, cnt in c["freq"].most_common():
        who = [f"#{ab['id']} {ab['ability']}" for ab, b in c["blocked"] if kind in b]
        out.append(f"  {kind:<22} {cnt:>2}  {FAMILIES.get(kind, 'other'):<10} " + "; ".join(who[:4]) + (" ..." if cnt > 4 else ""))
    return out


def verdict(c: dict, cfg: dict) -> str:
    if c["with_aliases"] + 1e-9 < float(cfg.get("floor", 0)):
        return "fail"
    return "warn" if c["with_aliases"] < float(cfg.get("target", 90)) else "ok"


def cmd_coverage(args) -> int:
    cfg = qa_settings().get("coverage") or {}
    c = compute(json.loads(CORPUS.read_text(encoding="utf-8")), canon_kinds(), alias_rows())
    text = line(c, cfg)
    if args.result:
        st = verdict(c, cfg)
        res = R.Result(st, {"canon": c["canon"], "with_aliases": c["with_aliases"], "floor": float(cfg.get("floor", 0))}, [text],
                       repro="python tools/qa.py coverage --list")
        print("\n".join(R.result_lines(res)))
        return 1 if st == "fail" else 0
    print(text)
    if args.list:
        print("\n".join(listing(c)))
    return 0


def register(sub):
    p = sub.add_parser("coverage", help="share of the 60-ability corpus the canon effect system can express (floor ratchet)",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--list", action="store_true", help="the blocked abilities grouped by blocking kind")
    p.add_argument("--result", action="store_true", help="machine form for `qa.py check` (RESULT line)")
    p.set_defaults(func=cmd_coverage)
