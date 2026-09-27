"""qa.py ctxwatch: plugin/skill name parsing, history round-trip, delta report, brief line -- no real transcript needed."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("qa_plugin_ctxwatch", Path(__file__).resolve().parents[1] / "tools" / "qa_plugins" / "ctxwatch.py")
C = importlib.util.module_from_spec(_spec)      # not on sys.path: qa_plugins/tools.py would shadow the `tools` package
_spec.loader.exec_module(C)


def test_names_accepts_bare_strings_and_enabled_dicts():
    items = ["a", {"name": "b", "enabled": True}, {"name": "c", "enabled": False}, {"name": "a"}]
    assert C._names(items) == ["a", "b"]


def test_snapshot_then_report_shows_new_names_and_ctx_growth(tmp_path, monkeypatch):
    hist = tmp_path / "h.jsonl"
    monkeypatch.setattr(C, "_current_first_ctx", lambda: (100000, "sess1"))
    args = argparse.Namespace(action="snapshot", file=None, json=False)
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": staticmethod(lambda: json.dumps({"plugins": ["a", "b"]}))})())
    assert C.cmd_snapshot(args, hist) == 0

    monkeypatch.setattr(C, "_current_first_ctx", lambda: (108000, "sess2"))
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": staticmethod(lambda: json.dumps({"plugins": ["a", "b", "c"], "skills": ["x"]}))})())
    assert C.cmd_snapshot(args, hist) == 0

    r = C._report(hist)
    assert r == {"ok": False, "empty": False, "session": "sess2", "first_ctx": 108000, "d_ctx": 8000,
                 "plugins": 3, "skills": 1, "d_plugins": 1, "d_skills": 1,
                 "added_plugins": ["c"], "removed_plugins": [], "added_skills": ["x"], "removed_skills": []}

    line = C.brief_line(hist)
    assert line.startswith("ctxwatch: plugins=3(+1) skills=1(+1) (non-project bloat?)")


def test_report_empty_without_a_snapshot(tmp_path):
    assert C._report(tmp_path / "missing.jsonl") == {"ok": True, "empty": True}
    assert C.brief_line(tmp_path / "missing.jsonl") == ""


def test_cmd_snapshot_rejects_bad_payload(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", type("S", (), {"read": staticmethod(lambda: "not json")})())
    assert C.cmd_snapshot(argparse.Namespace(action="snapshot", file=None, json=False), tmp_path / "h.jsonl") == 2


def test_history_keep_limit(tmp_path):
    path = tmp_path / "h.jsonl"
    for i in range(5):
        C._append({"ts": i, "plugins": [str(i)]}, keep=3, path=path)
    assert len(C._load_history(path)) == 3
    assert C._load_history(path)[0]["plugins"] == ["2"]
