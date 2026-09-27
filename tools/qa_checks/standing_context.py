"""qa_checks/standing_context.py - size of the context every session/agent pays on EVERY spawn (CLAUDE.md, always; docs/agent_context/preamble.md,
always for a typed agent; the rest, per role). A silent creep here taxes every single spawn forever, the same way the account's plugin/skill
catalog silently taxed every session until `qa.py ctxwatch` started watching it. Thresholds: `standing_context` in lua_content/qa.lua.
"""
from __future__ import annotations

from pathlib import Path

from probe_settings import qa_settings, ROOT
from qa_report import Result, check

ALWAYS = ("CLAUDE.md", "docs/agent_context/preamble.md")


def cfg() -> dict:
    return dict(qa_settings()["standing_context"])


def _role_files() -> list[Path]:
    return sorted((ROOT / "docs" / "agent_context").glob("*.md"))


def _tok(path: Path) -> int:
    return path.stat().st_size // int(cfg()["chars_per_token"])


@check("standing_context", cost="low", watches=["CLAUDE.md", "docs/agent_context/*.md"], tags=["tokens"])
def standing_context(ctx):
    """Token size of CLAUDE.md + docs/agent_context/*.md, paid on every session/agent spawn; warns past lua_content/qa.lua ceilings."""
    w = cfg()
    claude_md = ROOT / "CLAUDE.md"
    roles = _role_files()                                              # preamble.md + one per role
    always_tok = sum(_tok(ROOT / p) for p in ALWAYS if (ROOT / p).is_file())
    metrics = {"claude_md_tok": _tok(claude_md) if claude_md.is_file() else 0, "always_tok": always_tok,
               "roles": len(roles), "worst_role_tok": max((_tok(p) for p in roles), default=0)}
    for p in roles:
        metrics[f"tok_{p.stem}"] = _tok(p)
    bad = metrics["claude_md_tok"] > int(w["warn_claude_md_tok"]) or always_tok > int(w["warn_always_tok"])
    return Result("warn" if bad else "ok", metrics, name="standing_context",
                  detail=["every session/agent pays claude_md_tok + always_tok before its first useful token"] if bad else [])
