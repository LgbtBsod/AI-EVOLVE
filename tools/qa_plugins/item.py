"""qa.py item - предметы Effect Schema без чтения Lua.

    qa.py item check PATH | --forge N [--hostile]   # itemcheck: схема -> Lua -> условия -> бой
    qa.py item digest PATH                          # одна строка на эффект
    qa.py item diff PATH [--base REF]               # что поменялось в предмете относительно git REF (HEAD)
    qa.py item all                                  # каждый предмет lua_content/items + каждый шаблон каталога

PATH: файл .lua/.json или catalog:<id шаблона> (шаблон вместе с зависимостями).
"""
from __future__ import annotations

import json
import subprocess
import sys

from probe_settings import ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ITEMS = ROOT / "lua_content" / "items"


def load(spec: str, ref: str | None = None) -> dict:
    """Предмет по спецификации; ref - версия файла из git (None - рабочее дерево)."""
    from tools import lua_bridge
    from tools.effect_schema.catalog import bundle
    if spec.startswith("catalog:"):
        tid = spec.split(":", 1)[1]
        return {"name": tid, "effects": bundle(tid)}
    path = (ROOT / spec) if not spec.startswith("/") else __import__("pathlib").Path(spec)
    if ref is None:
        text = path.read_text(encoding="utf-8")
    else:
        rel = path.resolve().relative_to(ROOT).as_posix()
        r = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            return {"name": f"{rel}@{ref}", "effects": []}  # файла ещё не было
        text = r.stdout
    if path.suffix == ".json":
        return json.loads(text)
    return lua_bridge.load(text)


def cmd_check(args) -> int:
    from tools.effect_schema import itemcheck
    if args.forge is not None or not args.path:
        from tools.effect_schema.forge import forge_item
        item = forge_item(args.forge or 0, seed=args.seed, hostile=args.hostile)
    else:
        item = load(args.path)
    report = itemcheck.check_item(item, pred_samples=args.samples, seed=args.seed)
    print("\n".join(report.lines(findings=args.findings)))
    return 0 if report.ok else 1


def cmd_digest(args) -> int:
    from tools.effect_schema.digest import digest
    print("\n".join(digest(load(args.path))))
    return 0


def cmd_diff(args) -> int:
    from tools.effect_schema.digest import diff
    print("\n".join(diff(load(args.path, ref=args.base), load(args.path))))
    return 0


def cmd_all(args) -> int:
    from tools.effect_schema import itemcheck
    from tools.effect_schema.catalog import CATALOG
    specs = [p.relative_to(ROOT).as_posix() for p in sorted(ITEMS.glob("*.lua"))] + [f"catalog:{t}" for t in CATALOG]
    bad = 0
    for spec in specs:
        report = itemcheck.check_item(load(spec), pred_samples=args.samples)
        failed = [c for c in report.checks if not c.ok]
        bad += bool(failed)
        line = f"{'PASS' if not failed else 'FAIL'} {spec} ({report.effects} effects)"
        if failed:
            line += ": " + "; ".join(f"{c.name}: {c.findings[0] if c.findings else c.summary}" for c in failed)
        print(line)
    print(f"items: {len(specs) - bad}/{len(specs)} pass")
    return 1 if bad else 0


def register(sub):
    p = sub.add_parser("item", help="Effect Schema items: check / digest / diff / all")
    s = p.add_subparsers(dest="item_cmd", required=True)
    c = s.add_parser("check", help="itemcheck an item or a forged stress item")
    c.add_argument("path", nargs="?")
    c.add_argument("--forge", type=int, metavar="N")
    c.add_argument("--hostile", action="store_true")
    c.add_argument("--seed", type=int, default=0)
    c.add_argument("--samples", type=int, default=200)
    c.add_argument("--findings", type=int, default=8)
    c.set_defaults(func=cmd_check)
    d = s.add_parser("digest", help="one line per effect")
    d.add_argument("path")
    d.set_defaults(func=cmd_digest)
    f = s.add_parser("diff", help="changed effects vs a git ref")
    f.add_argument("path")
    f.add_argument("--base", default="HEAD")
    f.set_defaults(func=cmd_diff)
    a = s.add_parser("all", help="check every item file and catalog template")
    a.add_argument("--samples", type=int, default=100)
    a.set_defaults(func=cmd_all)
