"""usage ledger: last usage per message.id, missing usage, typed/untyped meta, two days, cache reuse, calibration medians."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import usage_ledger as U  # noqa: E402
from qa_plugins import wf  # noqa: E402


def _line(mid, ts, inp, cw, cr, out, kind="assistant"):
    return json.dumps({"type": kind, "timestamp": ts, "message": {"id": mid, "usage": {"input_tokens": inp, "cache_creation_input_tokens": cw,
                                                                                         "cache_read_input_tokens": cr, "output_tokens": out}}})


def _project(tmp_path):
    main = tmp_path / "abcdef12-0000.jsonl"
    main.write_text("\n".join([
        _line("m1", "2026-09-26T10:00:00Z", 1, 100, 0, 5),
        _line("m1", "2026-09-26T10:00:01Z", 1, 100, 0, 50),        # same id: the LAST usage counts
        _line("m2", "2026-09-27T09:00:00Z", 2, 10, 500, 7),
        json.dumps({"type": "assistant", "timestamp": "2026-09-27T09:00:05Z", "message": {"id": "m3"}}),   # no usage
        _line("u1", "2026-09-27T09:00:06Z", 9, 9, 9, 9, kind="user"),
    ]) + "\n", encoding="utf-8")
    sub = tmp_path / "abcdef12-0000" / "subagents"
    sub.mkdir(parents=True)
    for i, typ in enumerate(["implementer", "implementer", "implementer", "workflow-subagent"]):
        (sub / f"agent-a{i}bcdefgh.jsonl").write_text(_line(f"x{i}", "2026-09-27T10:00:00Z", 1, 1000 * (i + 1), 200, 10) + "\n", encoding="utf-8")
        (sub / f"agent-a{i}bcdefgh.meta.json").write_text(json.dumps({"agentType": typ, "description": "d"}), encoding="utf-8")
    return tmp_path


def test_last_usage_per_message_and_missing_usage(tmp_path):
    files = U.project_files(_project(tmp_path))
    main = next(f for f in files if f["kind"] == "main")
    recs = U.scan_file(main["path"])
    assert [r[1:] for r in recs] == [[1, 100, 0, 50], [2, 10, 500, 7]]
    st = U.file_stats({**main, "recs": recs})
    assert st["billed"] == 1 + 100 + 50 + 2 + 10 + 7 and st["cr"] == 500 and st["turns"] == 2 and st["first_ctx"] == 101


def test_groups_by_day_and_role_with_untyped_meta(tmp_path):
    files, _ = U.rows_for(U.project_files(_project(tmp_path)), None)
    days = {r["name"]: r for r in U.group(files, "day")}
    assert set(days) == {"2026-09-26", "2026-09-27"} and days["2026-09-26"]["billed"] == 151
    roles = {r["name"]: r for r in U.group(files, "role")}
    assert set(roles) == {"main", "implementer", "untyped"} and roles["untyped"]["n"] == 1


def test_cache_hit_and_refresh(tmp_path):
    files = U.project_files(_project(tmp_path))
    cache = tmp_path / "c.json"
    _, dirty = U.rows_for(files, cache)
    assert dirty and cache.is_file()
    assert U.rows_for(files, cache)[1] is False
    files[0]["path"].write_text(_line("z", "2026-09-27T00:00:00Z", 1, 1, 1, 1) + "\n", encoding="utf-8")
    assert U.rows_for(files, cache)[1] is True


def test_medians_need_three_samples_and_estimate_uses_them(tmp_path):
    files, _ = U.rows_for(U.project_files(_project(tmp_path)), None)
    med = U.medians(U.agent_samples(files))
    assert set(med) == {"implementer"} and med["implementer"]["billed"] == 2011 + 0 and med["implementer"]["n"] == 3
    cost = {"cold_default": 67000, "cold_typed": 12000, "avg_turns": 17, "growth_per_turn": 3600, "out_per_turn": 2050, "default_fanout": 3}
    script = "const r = await agent('x', { agentType: 'implementer' })"
    assert wf.estimate(script, cost, {"wf": med})["billed"] == 2011
    assert wf.estimate(script, cost, {})["billed"] == 12000 + 17 * 5650
