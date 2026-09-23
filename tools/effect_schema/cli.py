"""CLI-генератор предметов из Effect Schema JSON -> Lua.

Использование:
    python -m tools.effect_schema.cli build item.json [-o out.lua]
    python -m tools.effect_schema.cli validate item.json
    python -m tools/effect_schema/cli.py templates            # список шаблонов
    python -m tools.effect_schema.cli new <template_id> [-o effect.json]

Формат item.json (схема Effect -> Ops[], см. schema.py):
{
  "name": "...", "description": "...", "rarity": "...",
  "base_stats": { ... },
  "effects": [ {id, tags, trigger, ops, ...}, ... ]
}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import catalog, lua_gen, lua_parse, validate


def _load_json(path: str | None) -> dict:
    if path in (None, "-"):
        return json.load(sys.stdin)
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_validate(args) -> int:
    data = _load_json(args.file)
    effects = data.get("effects", data if isinstance(data, list) else [])
    errs = validate.validate_item(data) if "effects" in data or "name" in data \
        else [e for ef in effects for e in validate.validate_effect(ef)]
    if errs:
        print("INVALID:")
        for e in errs:
            print("  ✗", e)
        return 1
    print(f"OK: {len(effects)} effect(s) valid against effect-schema v1")
    return 0


def cmd_build(args) -> int:
    data = _load_json(args.file)
    effects = data.pop("effects", [])
    errs = validate.validate_item({**data, "effects": effects})
    if errs and not args.force:
        print("Schema validation failed:", file=sys.stderr)
        for e in errs:
            print("  ✗", e, file=sys.stderr)
        return 1
    lua = lua_gen.render_item(data, effects)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(lua, encoding="utf-8")
        print(f"written: {out}")
    else:
        print(lua)
    return 0


def cmd_templates(args) -> int:
    for tid, (name, _) in catalog.CATALOG.items():
        print(f"{tid:28} {name}")
    return 0


def cmd_new(args) -> int:
    try:
        ef = catalog.get_template(args.template_id)
    except KeyError:
        print(f"unknown template {args.template_id!r}; see `templates`", file=sys.stderr)
        return 1
    text = ef.dump()
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"written: {args.out}")
    else:
        print(text)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="effect_schema.cli",
                                 description="Effect Schema v1 generator (JSON -> Lua)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("validate", help="проверить JSON-предмет/эффект по схеме")
    p.add_argument("file", nargs="?", default="-")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("build", help="собрать Lua-файл предмета из JSON")
    p.add_argument("file", nargs="?", default="-")
    p.add_argument("-o", "--out", help="куда писать (по умолчанию stdout)")
    p.add_argument("--force", action="store_true", help="игнорировать ошибки схемы")
    p.set_defaults(fn=cmd_build)

    p = sub.add_parser("templates", help="список шаблонов эффектов")
    p.set_defaults(fn=cmd_templates)

    p = sub.add_parser("new", help="выдать шаблон эффекта как JSON")
    p.add_argument("template_id")
    p.add_argument("-o", "--out")
    p.set_defaults(fn=cmd_new)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
