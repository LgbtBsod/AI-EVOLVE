"""qa.py tokens --workflow: per-agent billing from a synthetic workflow run (last usage per message.id counts; UNTYPED above the cold-start limit)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import token_ledger as L  # noqa: E402
from qa_plugins.tokens import workflow_lines  # noqa: E402

WC = {"untyped_first_ctx": 40000, "use": "agentType"}


def _agent(path: Path, first: int, turns: int, label: str) -> None:
    rows = []
    for i in range(turns):
        u = {"input_tokens": 1, "cache_creation_input_tokens": first if i == 0 else 100,
             "cache_read_input_tokens": 0 if i == 0 else first, "output_tokens": 10}
        for _ in range(2):    # two blocks of one message repeat the usage: counted once
            rows.append({"type": "assistant", "message": {"id": f"m{i}", "usage": u}})
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    path.with_suffix(".meta.json").write_text(json.dumps({"label": label}), encoding="utf-8")


def test_agent_usage_and_untyped_flag(tmp_path):
    _agent(tmp_path / "agent-aaaaaaaa1.jsonl", 67000, 4, "cold")
    _agent(tmp_path / "agent-bbbbbbbb2.jsonl", 12000, 4, "typed")
    agents = L.workflow_agents(tmp_path)
    cold = next(a for a in agents if a["label"] == "cold")
    assert cold["turns"] == 4 and cold["first_ctx"] == 67001 and cold["out"] == 40
    assert cold["billed"] == cold["inp"] + cold["cw"] + cold["out"] == 4 + 67000 + 300 + 40
    head, *rows = workflow_lines(tmp_path, agents, WC)
    assert "untyped=1" in head and "verdict=WARN" in head
    assert "UNTYPED" in rows[0] and "cold" in rows[0] and "UNTYPED" not in rows[1]


def test_find_workflow(tmp_path):
    run = tmp_path / "p" / "s" / "subagents" / "workflows" / "wf_abc123-x"
    run.mkdir(parents=True)
    assert L.find_workflow(tmp_path, "abc1") == run and L.find_workflow(tmp_path, "latest") == run
    assert L.find_workflow(tmp_path, "zzz") is None
