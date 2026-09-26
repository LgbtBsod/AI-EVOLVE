"""qa.py wf: skeleton is typed and estimates cleanly; the estimate counts literal fan-out; assemble checks references."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import agent_kit  # noqa: E402
import guard_hook as G  # noqa: E402
from qa_plugins import wf  # noqa: E402

KIT = agent_kit.load()
COST = KIT["workflow_cost"]


def test_skeleton_has_no_untyped_agent_and_predicts_typed_cost():
    for kind in KIT["wf"]["kinds"]:
        text = wf.skeleton("demo", kind, KIT)
        assert G.untyped_agent_lines(text) == [] and "<" not in text.replace("<this file>", "")
        e = wf.estimate(text, COST)
        assert e["untyped"] == 0 and e["agents"] == 2                       # AREAS has two literal items
        assert e["billed"] == 2 * (COST["cold_typed"] + COST["avg_turns"] * (COST["growth_per_turn"] + COST["out_per_turn"]))


def test_estimate_untyped_costs_more_and_single_call_is_one_agent():
    one = "const r = await agent('x')"
    typed = "const r = await agent('x', { agentType: 'explorer' })"
    a, b = wf.estimate(one, COST), wf.estimate(typed, COST)
    assert (a["agents"], a["untyped"], b["untyped"]) == (1, 1, 0)
    assert a["billed"] - b["billed"] == COST["cold_default"] - COST["cold_typed"]


def test_assemble_flags_missing_reference(tmp_path, capsys):
    (tmp_path / "a.md").write_text("see `tools/qa.py:10` and `tools/nope_missing.py:3`\n", encoding="utf-8")
    class A: dir, out = str(tmp_path), None
    assert wf.cmd_assemble(A) == 1
    assert "refs_bad=1" in capsys.readouterr().out
