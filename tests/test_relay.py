"""qa.py relay: limit parsing, reset math, gates, command construction (no scheduler, no claude, no network)."""
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import relay_core as R  # noqa: E402
from qa_plugins import relay as P  # noqa: E402

C = P.cfg()
FB = C["tz_fallback"]
UTC = timezone.utc


def msg(text, ts):
    return json.dumps({"type": "assistant", "timestamp": ts, "message": {"content": [{"type": "text", "text": text}]}})


def test_reset_am_pm_and_wrap():
    sent = datetime(2026, 9, 26, 20, 0, tzinfo=UTC)  # 00:00 Yerevan on the 27th
    r = R.next_reset("You've hit your session limit · resets 4:30am (Asia/Yerevan)", sent, FB)
    assert r.astimezone(UTC).isoformat() == "2026-09-27T00:30:00+00:00"
    assert R.next_reset("limit resets 2am (Asia/Yerevan)", sent, FB).astimezone(UTC).hour == 22
    r = R.next_reset("limit resets 1:40pm (Asia/Yerevan)", datetime(2026, 9, 26, 10, 0, tzinfo=UTC), FB)  # 14:00 local -> tomorrow
    assert r.astimezone(UTC).isoformat() == "2026-09-27T09:40:00+00:00"
    assert R.next_reset("limit resets 12am (UTC)", datetime(2026, 9, 26, 23, 0, tzinfo=UTC), FB).isoformat() == "2026-09-27T00:00:00+00:00"


def test_reset_dst():
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("America/New_York")
    except Exception:
        pytest.skip("no tzdata")
    sent = datetime(2026, 11, 1, 4, 0, tzinfo=UTC)  # 00:00 EDT, DST ends 06:00 UTC
    assert R.next_reset("limit resets 5am (America/New_York)", sent, FB).astimezone(UTC).hour == 10  # EST after the change


def test_fallback_offset_table():
    r = R.next_reset("limit resets 4:30am (Nowhere/Land)", datetime(2026, 9, 26, 0, 0, tzinfo=UTC), {"Nowhere/Land": 3})
    assert r.utcoffset() == timedelta(hours=3)


def test_find_limit_tolerant():
    lines = [msg("hi", "2026-09-26T10:00:00Z"), msg("You've hit your session limit · resets 4:30am (Asia/Yerevan)", "2026-09-26T21:00:00Z")]
    assert R.find_limit(lines, FB) is not None
    assert R.find_limit([lines[1], msg("a", "x"), msg("b", "x"), msg("c", "x")], FB) is None  # not in the last rows
    assert R.find_limit(["not json limit resets 4am (UTC)"], FB) is None


def gate(**kw):
    base = dict(unfinished=True, idle_min=60, limit=None, lock_age_h=None, runs_today=0)
    base.update(kw)
    return R.gates(datetime(2026, 9, 27, 5, 0, tzinfo=UTC), base, C)


def test_gates():
    passed = {"reset": datetime(2026, 9, 27, 4, 0, tzinfo=UTC)}
    fresh = {"reset": datetime(2026, 9, 27, 5, 1, tzinfo=UTC)}
    assert gate(limit=passed)[0]
    assert gate()[0]  # crash: idle 60 >= 45
    assert not gate(unfinished=False)[0]
    assert not gate(idle_min=5, limit=passed)[0]
    assert not gate(limit=fresh)[0]
    assert not gate(limit=passed, lock_age_h=1)[0]
    assert gate(limit=passed, lock_age_h=7)[0]
    assert not gate(limit=passed, runs_today=C["max_per_day"])[0]
    assert not gate(idle_min=20)[0]


def test_headless_cmd_is_narrow():
    cmd = R.headless_cmd("claude.exe", "p", C)
    assert "--dangerously-skip-permissions" not in cmd
    assert cmd[cmd.index("--permission-mode") + 1] == "acceptEdits"
    allowed = cmd[cmd.index("--allowedTools") + 1:cmd.index("--disallowedTools")]
    assert "Read" in allowed and not any("push" in a or "ship" in a for a in allowed)
    denied = cmd[cmd.index("--disallowedTools") + 1:cmd.index("--max-budget-usd")]
    assert {"Bash(*qa.py ship*)", "Bash(git push*)", "Bash(git commit*)"} <= set(denied)
    assert cmd[cmd.index("--max-budget-usd") + 1] == "5"


def test_find_claude(tmp_path):
    for v in ("2.1.9", "2.1.281", "2.1.100"):
        f = tmp_path / "Claude" / "claude-code" / v / "claude.exe"
        f.parent.mkdir(parents=True)
        f.write_text("")
    assert "2.1.281" in R.find_claude(C, {}, tmp_path, lambda n: "x")
    assert R.find_claude(C, {"AI_EVOLVE_CLAUDE_BIN": "z"}, tmp_path, lambda n: "x") == "z"
    assert R.find_claude(C, {}, None, lambda n: "onpath") == "onpath"


def test_install_quoting_and_cron(tmp_path):
    root = tmp_path / "my repo"
    (root / ".venv" / "Scripts").mkdir(parents=True)
    (root / ".venv" / "Scripts" / "python.exe").write_text("")
    cmd = R.schtasks_create(root, C, 20)
    assert cmd[:2] == ["schtasks", "/Create"] and cmd[cmd.index("/MO") + 1] == "20" and "/F" in cmd
    tr = cmd[cmd.index("/TR") + 1]
    assert f'"{root / "tools" / "qa.py"}" relay tick' in tr and tr.startswith('"')
    line = R.cron_line(root, C, 20)
    assert "'" in line and line.endswith(C["cron_marker"])
    assert R.cron_replace("a\n" + line + "\n", line, C["cron_marker"]).count(C["cron_marker"]) == 1
    assert R.cron_replace("a\n" + line + "\n", None, C["cron_marker"]) == "a\n"


def test_ready_md_and_toast():
    lim = {"reset": datetime(2026, 9, 27, 4, 30, tzinfo=UTC)}
    md = R.ready_md("limit reset passed", "[RISKY] next=x", "python tools/qa.py resume", lim)
    assert "2026-09-27T04:30" in md and "python tools/qa.py resume" in md and "RISKY" in md
    assert "it''s" in R.toast_script("t", "it's")


def test_tick_notify_and_dry_run(tmp_path, monkeypatch):
    root, home = tmp_path / "repo", tmp_path / "home"
    (root / "dev_probe_output" / "qa").mkdir(parents=True)
    pd = R.project_dir(root, home)
    pd.mkdir(parents=True)
    f = pd / "s.jsonl"
    f.write_text(msg("You've hit your session limit · resets 2am (Asia/Yerevan)", "2026-09-27T01:00:00Z") + "\n", encoding="utf-8")
    now = datetime(2026, 9, 27, 5, 0, tzinfo=UTC)
    t = now.timestamp() - 120 * 60
    os.utime(f, (t, t))
    monkeypatch.setattr(P, "unfinished", lambda r, s: True)
    monkeypatch.setattr(P, "brief_line", lambda r: "[RISKY] next=go")
    monkeypatch.setattr(P, "toast", lambda *a: None)
    acted, why = P.tick(root, dry=True, now=now, home=home)
    assert not acted and "not passed" in why  # sent 05:00 local, next 2am is tomorrow
    acted, out = P.tick(root, dry=True, force=True, now=now, home=home)
    assert acted and "would write" in out and not (root / "dev_probe_output/qa/relay_ready.md").exists()
    acted, out = P.tick(root, force=True, now=now, home=home)
    assert acted and (root / "dev_probe_output/qa/relay_ready.md").is_file()
    assert P.tick(root, now=now, home=home)[0] is False
