"""qa.py new tool - scaffold a tool with the repo conventions in one call (script or plugin + smoke test + registry regeneration).

    qa.py new tool NAME --purpose "one line"            # tools/NAME.py + tests/test_NAME.py, then `qa.py tools --write`
    qa.py new tool NAME --purpose "one line" --plugin   # tools/qa_plugins/NAME.py (a `qa.py NAME` subcommand: register(sub))
    qa.py new tool NAME --purpose "..." --force         # scaffold although an existing tool looks alike

DRY guard first: the purpose words are scored like `qa.py tools --find`; the top 3 similar tools are printed, and a score >= `new_tool.similar_score`
(lua_content/qa.lua) refuses without --force. The docstring / `help=` is the tool's registry purpose, so no `tools.rows` entry is needed.
Never overwrites a file.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import tool_registry as TR
from probe_settings import ROOT, qa_settings

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")

SCRIPT = '''"""{purpose}

    python tools/{name}.py
"""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    print("{name}: not implemented yet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''

PLUGIN = '''"""qa.py {name} - {purpose}

    qa.py {name}
"""
from __future__ import annotations

import argparse


def cmd_{name}(args) -> int:
    print("{name}: not implemented yet")
    return 0


def register(sub):
    p = sub.add_parser("{name}", help="{purpose}",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\\n\\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.set_defaults(func=cmd_{name})
'''

TEST_SCRIPT = '''"""Smoke test of tools/{name}.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import {name}  # noqa: E402


def test_{name}_runs():
    assert {name}.main([]) == 0
'''

TEST_PLUGIN = '''"""Smoke test of tools/qa_plugins/{name}.py."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from qa_plugins import {name}  # noqa: E402


def test_{name}_runs():
    assert {name}.cmd_{name}(argparse.Namespace()) == 0
'''


def paths_for(root: Path, name: str, plugin: bool) -> tuple[Path, Path]:
    return (root / "tools" / ("qa_plugins" if plugin else "") / f"{name}.py"), root / "tests" / f"test_{name}.py"


def similar(reg, text: str, tcfg: dict, top: int = 3) -> list[tuple[int, object]]:
    """[(score, tool)] best first: the scoring of `qa.py tools --find`, with the numbers."""
    stop = set(TR._as_list(tcfg.get("stopwords")))
    query = TR._tokens(text, stop)
    scored = []
    for t in reg.tools:
        name, body = TR._tokens(t.id, stop), TR._tokens(f"{t.purpose} {t.when} {t.replaces}", stop)
        if score := sum(TR._word_score(w, name, body) for w in query):
            scored.append((score, t))
    return sorted(scored, key=lambda x: (-x[0], x[1].id))[:top]


def scaffold(root: Path, name: str, purpose: str, plugin: bool) -> list[Path]:
    """Write the tool and its smoke test; refuses (FileExistsError) to overwrite. -> [tool path, test path]."""
    tool, test = paths_for(root, name, plugin)
    for p in (tool, test):
        if p.exists():
            raise FileExistsError(p.relative_to(root).as_posix())
    fields = {"name": name, "purpose": purpose.replace('"', "'")}
    tool.write_text((PLUGIN if plugin else SCRIPT).format(**fields), encoding="utf-8", newline="\n")
    test.write_text((TEST_PLUGIN if plugin else TEST_SCRIPT).format(**fields), encoding="utf-8", newline="\n")
    return [tool, test]


def dry_guard(args, settings: dict) -> int | None:
    """Print the top look-alikes; 1 when the best one scores >= new_tool.similar_score and there is no --force."""
    cfg = {"similar_score": 6, "show": 3, **(settings.get("new_tool") or {})}
    hits = similar(TR.build(ROOT, settings), f"{args.name} {args.purpose}", settings.get("tools") or {}, int(cfg["show"]))
    if hits:
        print("similar existing tools:\n" + "\n".join(f"  {s:>2} {t.id} | {t.command or '-'} | {t.purpose}" for s, t in hits))
    if hits and hits[0][0] >= float(cfg["similar_score"]) and not args.force:
        print(f"new: {hits[0][1].id} looks like it (score {hits[0][0]} >= {cfg['similar_score']}): extend it, or re-run with --force")
        return 1
    return None


def cmd_new(args) -> int:
    settings = qa_settings()
    if not NAME_RE.match(args.name):
        print(f"new: bad name {args.name!r} (lower_snake, 2-41 chars)")
        return 2
    if (blocked := dry_guard(args, settings)) is not None:
        return blocked
    try:
        made = scaffold(ROOT, args.name, args.purpose, args.plugin)
    except FileExistsError as exc:
        print(f"new: {exc} exists, nothing written")
        return 1
    TR.write(ROOT, settings)
    rels = [p.relative_to(ROOT).as_posix() for p in made] + ["docs/TOOLS.md"]
    print("created: " + " ".join(rels))
    print(f"next: python tools/qa.py test --changed   (then implement {rels[0]}; `qa.py check --name tools` keeps the registry honest)")
    return 0


def register(sub):
    p = sub.add_parser("new", help="scaffold a tool: script or plugin + smoke test + docs/TOOLS.md, with a look-alike (DRY) guard",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("kind", choices=["tool"])
    p.add_argument("name", help="lower_snake tool name")
    p.add_argument("--purpose", required=True, help="one line: becomes the docstring and the registry purpose")
    p.add_argument("--plugin", action="store_true", help="a qa.py subcommand (tools/qa_plugins/NAME.py) instead of a script")
    p.add_argument("--force", action="store_true", help="scaffold although a similar tool exists")
    p.set_defaults(func=cmd_new)
