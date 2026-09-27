"""qa_checks/standing_context.py: reads real CLAUDE.md + docs/agent_context/*.md sizes, warns past configured ceilings."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("qa_checks_standing_context", Path(__file__).resolve().parents[1] / "tools" / "qa_checks" / "standing_context.py")
S = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(S)


def test_metrics_cover_claude_md_and_every_role_file():
    r = S.standing_context(None)
    assert r.metrics["claude_md_tok"] > 0
    assert r.metrics["always_tok"] >= r.metrics["claude_md_tok"]        # always_tok = CLAUDE.md + preamble.md
    assert r.metrics["roles"] == len(S._role_files())
    assert "tok_preamble" in r.metrics and "tok_implementer" in r.metrics


def test_ok_under_the_configured_ceilings():
    r = S.standing_context(None)
    assert r.status == "ok"


def test_warns_past_a_lowered_ceiling(monkeypatch):
    monkeypatch.setattr(S, "cfg", lambda: {"chars_per_token": 4, "warn_claude_md_tok": 1, "warn_always_tok": 1})
    r = S.standing_context(None)
    assert r.status == "warn" and r.detail
