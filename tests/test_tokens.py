"""qa.py tokens: synthetic transcripts only (split assistant blocks, tool_result linking, waste patterns, trend)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import importlib.util  # noqa: E402

import token_ledger as L  # noqa: E402
from probe_settings import qa_settings  # noqa: E402

CFG = qa_settings()["tokens"]
_spec = importlib.util.spec_from_file_location("qa_plugin_tokens", Path(__file__).resolve().parents[1] / "tools" / "qa_plugins" / "tokens.py")
T = importlib.util.module_from_spec(_spec)      # not on sys.path: qa_plugins/tools.py would shadow the `tools` package
_spec.loader.exec_module(T)


def use(msg, tid, name, inp):
    return {"type": "assistant", "message": {"id": msg, "role": "assistant", "content": [{"type": "tool_use", "id": tid, "name": name, "input": inp}]}}


def res(tid, text, err=False):
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": err}]}}


def write(tmp_path, recs, name="s1.jsonl"):
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")
    return p


def test_split_blocks_group_into_one_turn(tmp_path):
    recs = [use("m1", "a", "Read", {"file_path": "x.py", "limit": 5}), use("m1", "b", "Grep", {"pattern": "q"}),
            res("a", "1"), res("b", "2"), use("m2", "c", "Read", {"file_path": "y.py"}), res("c", "3")]
    m = L.metrics(L.parse_log(write(tmp_path, recs)), CFG)
    assert (m["turns"], m["calls"], m["cpt"], m["multi_pct"]) == (2, 3, 1.5, 50)
    assert m["saveable"] == 1 and m["saveable_pct"] == 50      # two read-only turns in a row


def test_writes_break_a_run_and_shell_classification(tmp_path):
    recs = [use("1", "a", "Bash", {"command": "ls 2>&1"}), use("2", "b", "Bash", {"command": "echo x > f.txt"}),
            use("3", "c", "Read", {"file_path": "z"}), res("a", "ok"), res("b", "ok"), res("c", "ok")]
    m = L.metrics(L.parse_log(write(tmp_path, recs)), CFG)
    assert m["saveable"] == 0


def test_repeats_unbounded_heavy_retries_relay(tmp_path):
    big = "\n".join(f"{i} line" for i in range(300))
    recs = [use("1", "a", "Read", {"file_path": "big.py"}), res("a", big), use("2", "b", "Read", {"file_path": "big.py"}), res("b", ("x" + chr(10)) * 30000),
            use("3", "c", "Bash", {"command": "python3 x"}), res("c", "boom same error", True),
            use("4", "d", "Bash", {"command": "python3 x"}), res("d", "boom same error", True),
            {"type": "assistant", "message": {"id": "5", "content": [{"type": "text", "text": "done\nRELAY: continue with qa.py resume"}]}}]
    m = L.metrics(L.parse_log(write(tmp_path, recs)), CFG)
    assert m["repeats"] == 1 and m["unbounded"] == 2
    assert m["heavy"][0][:2] == [15000, "Read"] and m["retries"] == 1 and m["relays"] == 1
    assert m["turns"] == 4 and m["by_tool"]["Read"] > 15000


def test_written_input_tokens(tmp_path):
    recs = [use("1", "a", "Edit", {"file_path": "f", "old_string": "o" * 400, "new_string": "n" * 400}),
            use("2", "b", "Write", {"file_path": "g", "content": "c" * 800}), use("3", "d", "Bash", {"command": "python - <<'EOF'\n" + "x" * 400})]
    w = L.metrics(L.parse_log(write(tmp_path, recs)), CFG)["writes"]
    assert w["edit_old"] == 100 and w["edit"] > 200 and w["write"] > 200 and w["heredoc"] > 100


def test_session_files_and_lines_with_trend(tmp_path):
    main = write(tmp_path, [use("1", "a", "Read", {"file_path": "x"}), res("a", "x")], "abc.jsonl")
    sub = tmp_path / "abc" / "subagents"
    sub.mkdir(parents=True)
    write(sub, [use("1", "a", "Read", {"file_path": "x"}), use("2", "b", "Grep", {"pattern": "y"})], "agent-1.jsonl")
    assert len(L.session_files(main)[1]) == 1
    hist = tmp_path / "h.jsonl"
    first, _ = T.build(main, CFG, True, 3, hist)
    second, data = T.build(main, CFG, True, 3, hist)
    assert first[0].startswith("QA verdict=") and any(ln.startswith("warn") and "| use:" in ln for ln in second)
    assert data["agents"]["cpt"] == 1.0 and any("agents" in ln for ln in second)
    assert T.previous("abc", hist)["cpt"] == 1.0
