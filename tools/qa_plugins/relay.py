"""qa.py relay - continue unfinished work automatically after a usage-limit stop or a crash; ZERO model tokens while there is nothing to do.

    qa.py relay detect [--session latest|PATH]   # limit=hit reset=... idle=12m | limit=none
    qa.py relay tick [--dry-run] [--force]        # what the OS scheduler runs: acts only when every gate holds (unfinished work, idle, reset passed, lock, per-day cap)
    qa.py relay install [--mode notify|headless] [--every N] [--dry-run] | uninstall | status

Modes (dev_probe_output/qa/relay.json): notify (default: relay_ready.md + toast) or headless (opt-in: the bundled claude.exe with a NARROW tool list, never commits/pushes;
leaves a checkpoint for the owner to review and `qa.py ship`). Numbers, tool lists and paths: the `relay` table of lua_content/qa.lua.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import relay_core as R
from probe_settings import ROOT, qa_settings

IS_WIN = os.name == "nt"


def cfg() -> dict:
    return qa_settings()["relay"]


def qdir(root: Path) -> Path:
    return root / "dev_probe_output" / "qa"


def load_state(root: Path) -> dict:
    try:
        return json.loads((qdir(root) / "relay.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(root: Path, st: dict) -> None:
    qdir(root).mkdir(parents=True, exist_ok=True)
    (qdir(root) / "relay.json").write_text(json.dumps(st, indent=1), encoding="utf-8")


def detect(root: Path, c: dict, session: str = "latest", now: datetime | None = None, home: Path | None = None) -> dict:
    path = R.newest_transcript(R.project_dir(root, home)) if session == "latest" else Path(session)
    if path is None or not path.is_file():
        return {"limit": None, "idle_min": 1e9, "path": None}
    now = now or datetime.now(timezone.utc)
    idle = (now.timestamp() - path.stat().st_mtime) / 60
    return {"limit": R.find_limit(R.read_tail(path, c["tail_bytes"]), c["tz_fallback"]), "idle_min": idle, "path": path}


def detect_line(d: dict) -> str:
    lim = d["limit"]
    idle = f"{d['idle_min']:.0f}m" if d["path"] else "-"
    return f"limit=hit reset={lim['reset'].isoformat(timespec='minutes')} idle={idle}" if lim else f"limit=none idle={idle}"


def unfinished(root: Path, since: float) -> bool:
    from qa_plugins import ckpt as C
    if C.dirty_files(root):
        return True
    j = (C.read_journal(root) or [{}])[-1]
    return bool(j.get("next")) and j.get("ts", 0) > since


def lock_age_h(root: Path, now: float) -> float | None:
    p = qdir(root) / "relay.lock"
    return (now - p.stat().st_mtime) / 3600 if p.is_file() else None


def runs_today(st: dict, now: float) -> int:
    day = datetime.fromtimestamp(now).date()
    return sum(1 for t in st.get("runs", []) if datetime.fromtimestamp(t).date() == day)


def brief_line(root: Path) -> str:
    from qa_plugins import resume as RS
    return RS.brief(RS.gather(root, brief=True))


def notify(root: Path, c: dict, why: tuple[str, dict | None], dry: bool, why_fallback: str = "") -> str:
    reason, limit = why
    brief = brief_line(root)
    cmd = f'python tools/qa.py prompt implementer --task "continue: {brief}"'
    text = R.ready_md(reason + why_fallback, brief, cmd, limit)
    if dry:
        return "would write relay_ready.md + toast"
    qdir(root).mkdir(parents=True, exist_ok=True)
    (qdir(root) / "relay_ready.md").write_text(text, encoding="utf-8")
    toast(c["toast_title"], brief[:200])
    return "notified (relay_ready.md)"


def toast(title: str, body: str) -> None:
    try:
        if IS_WIN:
            subprocess.run(["powershell", "-NoProfile", "-Command", R.toast_script(title, body)], capture_output=True, timeout=20, check=False)
        elif shutil.which("notify-send"):
            subprocess.run(["notify-send", title, body], capture_output=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def headless(root: Path, c: dict, claude: str, dry: bool) -> str:
    prompt = R.continue_prompt(brief_line(root))
    cmd = R.headless_cmd(claude, prompt, c)
    if dry:
        return "would run headless: " + " ".join(cmd[:3])[:60] + f" ... --max-budget-usd {c['max_budget_usd']} (no commit/push)"
    log = qdir(root) / f"relay_{time.strftime('%Y%m%d_%H%M%S')}.log"
    with log.open("w", encoding="utf-8") as fh:
        subprocess.run(cmd, cwd=root, stdout=fh, stderr=subprocess.STDOUT, timeout=c["timeout_h"] * 3600, check=False)
    subprocess.run([sys.executable, str(root / "tools" / "qa.py"), "ckpt", "--auto"], cwd=root, capture_output=True, timeout=60, check=False)
    return f"headless run finished: {log.name}"


def act(root: Path, c: dict, mode: str, why: tuple[str, dict | None], dry: bool) -> str:
    if mode == "headless":
        claude = R.find_claude(c, dict(os.environ), Path(os.environ["APPDATA"]) if os.environ.get("APPDATA") else None, shutil.which)
        if claude:
            return headless(root, c, claude, dry)
        return notify(root, c, why, dry, "; no claude binary found: fell back to notify")
    return notify(root, c, why, dry)


def tick(root: Path, dry: bool = False, force: bool = False, now: datetime | None = None, home: Path | None = None) -> tuple[bool, str]:
    c, st = cfg(), load_state(root)
    now = now or datetime.now(timezone.utc)
    ts = now.timestamp()
    d = detect(root, c, now=now, home=home)
    facts = {"unfinished": unfinished(root, st.get("last_action", 0)), "idle_min": d["idle_min"], "limit": d["limit"],
             "lock_age_h": lock_age_h(root, ts), "runs_today": runs_today(st, ts)}
    ok, reason = R.gates(now, facts, c)
    if not dry:
        st["last_tick"] = ts
    if not (ok or force):
        if not dry:
            save_state(root, st)
        return False, reason
    result = act(root, c, st.get("mode", c["mode"]), (reason if ok else f"forced ({reason})", d["limit"]), dry)
    if not dry:
        qdir(root).joinpath("relay.lock").write_text(str(ts), encoding="utf-8")
        st.update(last_action=ts, runs=[*st.get("runs", [])[-20:], ts])
        save_state(root, st)
    return True, result


def install_cmds(root: Path, c: dict, every: int) -> list[str]:
    if IS_WIN:
        return [subprocess.list2cmdline(R.schtasks_create(root, c, every))]
    return [R.cron_line(root, c, every)]


def cmd_install(root: Path, args) -> int:
    c = cfg()
    every = args.every or c["every_min"]
    cmds = install_cmds(root, c, every)
    print(("would run: " if args.dry_run else "") + cmds[0])
    if args.dry_run:
        return 0
    st = load_state(root)
    st.update(mode=args.mode or st.get("mode", c["mode"]), every=every)
    save_state(root, st)
    if IS_WIN:
        return subprocess.run(R.schtasks_create(root, c, every), check=False).returncode
    cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False).stdout
    return subprocess.run(["crontab", "-"], input=R.cron_replace(cur, cmds[0], c["cron_marker"]), text=True, check=False).returncode


def cmd_uninstall(root: Path, args) -> int:
    c = cfg()
    if IS_WIN:
        return subprocess.run(["schtasks", "/Delete", "/TN", c["task_name"], "/F"], check=False).returncode
    cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False).stdout
    return subprocess.run(["crontab", "-"], input=R.cron_replace(cur, None, c["cron_marker"]), text=True, check=False).returncode


def is_installed(c: dict) -> bool:
    try:
        if IS_WIN:
            return subprocess.run(["schtasks", "/Query", "/TN", c["task_name"]], capture_output=True, timeout=10, check=False).returncode == 0
        cur = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10, check=False).stdout
        return c["cron_marker"] in cur
    except (OSError, subprocess.SubprocessError):
        return False


def fmt_ts(t) -> str:
    return datetime.fromtimestamp(t).strftime("%m-%d %H:%M") if t else "-"


def status_line(root: Path) -> str:
    c, st = cfg(), load_state(root)
    d = detect(root, c)
    return (f"relay mode={st.get('mode', c['mode'])} installed={'yes' if is_installed(c) else 'no'} every={st.get('every', c['every_min'])}m "
            f"last_tick={fmt_ts(st.get('last_tick'))} last_action={fmt_ts(st.get('last_action'))} " + detect_line(d).split(" idle")[0])


def unread_line(root: Path) -> str:
    """One line for `qa.py brief`: only when relay is installed (relay.json has a mode) and relay_ready.md is newer than the last brief."""
    ready, st = qdir(root) / "relay_ready.md", load_state(root)
    if "mode" not in st or not ready.is_file() or ready.stat().st_mtime <= st.get("brief_seen", 0):
        return ""
    st["brief_seen"] = time.time()
    save_state(root, st)
    return "relay: unfinished work is ready to continue - see dev_probe_output/qa/relay_ready.md"


def cmd_tick(root: Path, args) -> int:
    acted, msg = tick(root, args.dry_run, args.force)
    if acted and args.dry_run:
        print("WOULD: " + msg)
    elif acted:
        print(msg)
    elif args.dry_run:
        print(f"no action: {msg}")
    return 0


def cmd_relay(args) -> int:
    root = Path(args.root) if args.root else ROOT
    table = {"detect": lambda: print(detect_line(detect(root, cfg(), args.session))) or 0, "tick": lambda: cmd_tick(root, args),
             "install": lambda: cmd_install(root, args), "uninstall": lambda: cmd_uninstall(root, args), "status": lambda: print(status_line(root)) or 0}
    return table[args.action]()


def register(sub):
    p = sub.add_parser("relay", help="auto-continue unfinished work after a usage-limit stop/crash (OS scheduler runs `tick`; notify or opt-in headless)",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("action", choices=["detect", "tick", "install", "uninstall", "status"])
    p.add_argument("--session", default="latest")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--mode", choices=["notify", "headless"])
    p.add_argument("--every", type=int)
    p.add_argument("--root", help=argparse.SUPPRESS)
    p.set_defaults(func=cmd_relay)
