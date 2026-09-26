"""relay_core - pure logic of `qa.py relay` (limit parsing, reset math, tick gates, command construction). Stdlib only; no I/O except small helpers.

Numbers, paths and tool lists come from the `relay` table of lua_content/qa.lua (passed in as `c`).
"""
from __future__ import annotations

import json
import re
import shlex
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RESET_RE = re.compile(r"resets\s+(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*\(([A-Za-z_]+(?:/[A-Za-z_+\-0-9]+)*)\)", re.I)


def project_dir(root: Path, home: Path | None = None) -> Path:
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(root))
    return (home or Path.home()) / ".claude" / "projects" / slug


def newest_transcript(pdir: Path) -> Path | None:
    files = [f for f in pdir.glob("*.jsonl") if f.is_file()] if pdir.is_dir() else []
    return max(files, key=lambda f: f.stat().st_mtime, default=None)


def read_tail(path: Path, nbytes: int) -> list[str]:
    with path.open("rb") as fh:
        fh.seek(0, 2)
        start = max(0, fh.tell() - nbytes)
        fh.seek(start)
        return fh.read().decode("utf-8", errors="replace").splitlines()[1 if start else 0:]


def tzinfo_for(name: str, fallback: dict):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - no tzdata / unknown key: fixed offset table
        return timezone(timedelta(hours=float(fallback.get(name, 0))))


def next_reset(text: str, sent: datetime, fallback: dict) -> datetime | None:
    """The next wall-clock H[:MM]am/pm in the message's IANA tz strictly after `sent` (aware)."""
    m = RESET_RE.search(text)
    if not m:
        return None
    hour, minute, ap, tzname = int(m.group(1)) % 12, int(m.group(2) or 0), m.group(3).lower(), m.group(4)
    hour += 12 if ap == "pm" else 0
    tz = tzinfo_for(tzname, fallback)
    local = sent.astimezone(tz)
    for add in (0, 1, 2):
        day = (local + timedelta(days=add)).date()
        cand = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tz)
        if cand.astimezone(timezone.utc) > sent.astimezone(timezone.utc):
            return cand
    return None


def parse_ts(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def find_limit(lines: list[str], fallback: dict, last_rows: int = 3) -> dict | None:
    """The limit message among the last `last_rows` JSONL rows: {'reset': aware datetime, 'sent': datetime} or None. Tolerant: any row whose text has 'limit' + 'resets H(:MM)am (TZ)'."""
    for raw in reversed([ln for ln in lines if ln.strip()][-last_rows:]):
        if "limit" not in raw or not RESET_RE.search(raw):
            continue
        try:
            sent = parse_ts(json.loads(raw).get("timestamp"))
        except (ValueError, AttributeError):
            sent = None
        if sent is None:
            continue
        reset = next_reset(raw, sent, fallback)
        if reset:
            return {"reset": reset, "sent": sent}
    return None


def gates(now: datetime, f: dict, c: dict) -> tuple[bool, str]:
    """(act, reason) from facts f = unfinished, idle_min, limit, lock_age_h, runs_today; the first failing gate names the reason."""
    limit, lock = f["limit"], f["lock_age_h"]
    checks = [
        (not f["unfinished"], "no unfinished work"),
        (f["idle_min"] < c["idle_min"], f"session idle {f['idle_min']:.0f}m < {c['idle_min']}m"),
        (lock is not None and lock < c["lock_h"], f"lock {lock}h < {c['lock_h']}h"),
        (f["runs_today"] >= c["max_per_day"], f"{f['runs_today']} runs today >= {c['max_per_day']}"),
        (bool(limit) and now < limit["reset"] + timedelta(minutes=c["margin_min"]), "reset not passed"),
        (not limit and f["idle_min"] < c["crash_idle_min"], f"no limit message, idle {f['idle_min']:.0f}m < {c['crash_idle_min']}m"),
    ]
    for failed, why in checks:
        if failed:
            return False, why
    return True, "limit reset passed" if limit else "crash (no limit message)"


def continue_prompt(brief: str) -> str:
    return ("Read docs/agent_context/preamble.md and docs/agent_context/implementer.md, then continue: " + brief +
            ". Do not commit or push; end with `qa.py ckpt` (done/next) and the report lines.")


def headless_cmd(claude: str, prompt: str, c: dict) -> list[str]:
    return [claude, "-p", prompt, "--permission-mode", c["permission_mode"], "--allowedTools", *c["allowed_tools"], "--disallowedTools", *c["disallowed_tools"],
            "--max-budget-usd", str(c["max_budget_usd"]), "--model", c["model"], "--output-format", "text"]


def find_claude(c: dict, env: dict, appdata: Path | None, which) -> str | None:
    if env.get("AI_EVOLVE_CLAUDE_BIN"):
        return env["AI_EVOLVE_CLAUDE_BIN"]
    if appdata:
        def key(p: Path):
            return [int(x) if x.isdigit() else 0 for x in re.split(r"\D+", p.parent.name)]
        found = sorted(appdata.glob(c["claude_glob"]), key=key)
        if found:
            return str(found[-1])
    return which("claude")


def venv_python(root: Path, windowless: bool = False) -> str:
    for rel in (".venv/Scripts/pythonw.exe" if windowless else ".venv/Scripts/python.exe", ".venv/Scripts/python.exe", ".venv/bin/python"):
        if (root / rel).is_file():
            return str(root / rel)
    return sys.executable


def schtasks_create(root: Path, c: dict, every: int) -> list[str]:
    tr = f'"{venv_python(root, True)}" "{root / "tools" / "qa.py"}" relay tick'
    return ["schtasks", "/Create", "/SC", "MINUTE", "/MO", str(every), "/TN", c["task_name"], "/TR", tr, "/F"]


def cron_line(root: Path, c: dict, every: int) -> str:
    return f"*/{every} * * * * cd {shlex.quote(str(root))} && {shlex.quote(venv_python(root))} tools/qa.py relay tick {c['cron_marker']}"


def cron_replace(current: str, line: str | None, marker: str) -> str:
    keep = [ln for ln in current.splitlines() if marker not in ln]
    return "\n".join(keep + ([line] if line else [])) + "\n"


def toast_script(title: str, body: str) -> str:
    esc = lambda s: s.replace("'", "''").replace("&", "&amp;").replace("<", "&lt;")  # noqa: E731
    return ("[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; "
            "$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); "
            f"$t = $x.GetElementsByTagName('text'); $t.Item(0).AppendChild($x.CreateTextNode('{esc(title)}')) | Out-Null; "
            f"$t.Item(1).AppendChild($x.CreateTextNode('{esc(body)}')) | Out-Null; "
            "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('AI-EVOLVE').Show([Windows.UI.Notifications.ToastNotification]::new($x))")


def ready_md(reason: str, brief: str, cmd: str, limit: dict | None) -> str:
    when = limit["reset"].isoformat(timespec="minutes") if limit else "-"
    return (f"# Relay ready\n\nWhy: {reason} (limit reset {when})\n\nState: {brief}\n\nContinue with ONE command:\n\n    {cmd}\n")
