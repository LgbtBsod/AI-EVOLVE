#!/usr/bin/env python3
"""Аналитика прогонов на уровне БД: расчёты в SQLite вместо чтения JSONL.

Каждый прогон dev_probe.py / agent_play.py сам складывается сюда
(dev_probe_output/probe.sqlite, путь - lua_content/dev_tools.lua: db.path):
сэмплы героя и врагов, боевые события, убийства. Дальше вопросы вида
"какой тип врага наносит больше всего урона", "стал ли герой умирать чаще
после моего фикса", "когда он умрёт при таком темпе" - это один короткий
вызов с ответом в несколько строк, а не чтение сотен строк state.jsonl.

    python tools/probe_db.py runs                      # последние прогоны
    python tools/probe_db.py stats [RUN]               # бой по типам врагов, hit/crit/dodge, TTK
    python tools/probe_db.py why [RUN]                 # гипотезы (probe_analysis)
    python tools/probe_db.py predict [RUN]             # прогнозы (смерть, давление врагов, level-up)
    python tools/probe_db.py compare RUN_A RUN_B       # что изменилось между двумя прогонами
    python tools/probe_db.py trend kills --last 10     # метрика по прогонам + спарклайн + выброс
    python tools/probe_db.py sql "SELECT etype, COUNT(*) FROM kills GROUP BY 1"
    python tools/probe_db.py ingest dev_probe_output/<run_dir>   # старый прогон с диска

RUN - run_id, его уникальный префикс или "last" (по умолчанию).
Таблицы: runs, samples (герой), enemy_samples, combat, kills.
"""
import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe_analysis as analysis  # noqa: E402
import probe_kernels as kernels  # noqa: E402
from probe_settings import ROOT, section  # noqa: E402

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, kind TEXT, created REAL, dir TEXT, status TEXT, seed INTEGER,
    duration REAL, fast INTEGER, render TEXT, label TEXT, player_id TEXT,
    kills INTEGER, dmg_dealt REAL, dmg_taken REAL, min_hp REAL, end_hp REAL, died INTEGER,
    errors INTEGER, warnings INTEGER, crit_chance REAL, backend TEXT, meta TEXT
);
CREATE TABLE IF NOT EXISTS samples (
    run_id TEXT, t REAL, hp REAL, max_hp REAL, x REAL, y REAL, alive INTEGER, lvl INTEGER,
    xp REAL, xp_next REAL, ai TEXT, enemies INTEGER
);
CREATE TABLE IF NOT EXISTS enemy_samples (
    run_id TEXT, t REAL, eid TEXT, etype TEXT, hp REAL, max_hp REAL, x REAL, y REAL
);
CREATE TABLE IF NOT EXISTS combat (
    run_id TEXT, t REAL, source TEXT, target TEXT, source_type TEXT, target_type TEXT,
    damage REAL, critical INTEGER, dodged INTEGER
);
CREATE TABLE IF NOT EXISTS kills (run_id TEXT, t REAL, eid TEXT, etype TEXT, kind TEXT);
CREATE INDEX IF NOT EXISTS i_samples ON samples(run_id, t);
CREATE INDEX IF NOT EXISTS i_enemy ON enemy_samples(run_id, eid);
CREATE INDEX IF NOT EXISTS i_combat ON combat(run_id, t);
CREATE INDEX IF NOT EXISTS i_kills ON kills(run_id);
"""
RUN_TABLES = ("samples", "enemy_samples", "combat", "kills")


def db_path():
    """lua_content/dev_tools.lua: db.path; env AI_EVOLVE_PROBE_DB перекрывает (тесты, CI)."""
    path = Path(os.environ.get("AI_EVOLVE_PROBE_DB") or section("db")["path"])
    return path if path.is_absolute() else ROOT / path


def connect(path=None):
    path = Path(path) if path else db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    return con


# ---------------------------------------------------------------- ingest

def ingest(con, run_id, meta, samples, events, kills=(), despawns=()):
    """Складывает прогон (перезаписывает run_id, если он уже был)."""
    pid = analysis.player_id_of(samples)
    stats = analysis.combat_stats(events, pid)
    hero = [s["player"] for s in samples if s.get("player")]
    for table in (*RUN_TABLES, "runs"):
        con.execute(f"DELETE FROM {table} WHERE run_id=?", (run_id,))
    con.execute(
        "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, meta.get("kind"), meta.get("created", time.time()), meta.get("dir"), meta.get("status"),
         meta.get("seed"), meta.get("duration"), int(bool(meta.get("fast"))), meta.get("render"),
         meta.get("label"), pid, len(kills), stats["dealt"], stats["taken"],
         min((p["hp"] for p in hero), default=None), hero[-1]["hp"] if hero else None,
         int(any(not p.get("alive", p["hp"] > 0) for p in hero)),
         meta.get("errors", 0), meta.get("warnings", 0), meta.get("crit_chance"), kernels.BACKEND,
         json.dumps({k: v for k, v in meta.items() if k not in ("dir",)}, default=str)))
    con.executemany("INSERT INTO samples VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [
        (run_id, s["t"], p["hp"], p["max_hp"], p["pos"][0], p["pos"][1], int(p.get("alive", p["hp"] > 0)),
         p.get("lvl"), p.get("xp"), p.get("xp_next"), p.get("ai"), len(s.get("enemies", [])))
        for s in samples if (p := s.get("player"))])
    con.executemany("INSERT INTO enemy_samples VALUES (?,?,?,?,?,?,?,?)", [
        (run_id, s["t"], e["id"], e["type"], e["hp"], e["max_hp"], e["pos"][0], e["pos"][1])
        for s in samples for e in s.get("enemies", [])])
    con.executemany("INSERT INTO combat VALUES (?,?,?,?,?,?,?,?,?)", [
        (run_id, e["t"], e["source"], e["target"], e.get("source_type"), e.get("target_type"),
         e["damage"], int(e["critical"]), int(e["dodged"])) for e in events])
    con.executemany("INSERT INTO kills VALUES (?,?,?,?,?)",
                    [(run_id, t, eid, et, "kill") for t, eid, et in kills]
                    + [(run_id, t, eid, et, "despawn") for t, eid, et in despawns])
    keep = int(section("db")["keep_runs"])
    old = [r[0] for r in con.execute("SELECT run_id FROM runs ORDER BY created DESC LIMIT -1 OFFSET ?", (keep,))]
    for rid in old:
        for table in (*RUN_TABLES, "runs"):
            con.execute(f"DELETE FROM {table} WHERE run_id=?", (rid,))
    con.commit()
    return run_id


def ingest_quietly(run_id, meta, samples, events, kills=(), despawns=()):
    """Для инструментов: БД - бонус, её поломка не должна ронять прогон."""
    try:
        con = connect()
        try:
            ingest(con, run_id, meta, samples, events, kills, despawns)
        finally:
            con.close()
        return None
    except Exception as exc:
        return f"probe DB ingest failed: {exc!r}"


def _read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def ingest_dir(con, run_dir):
    run_dir = Path(run_dir)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8")) if (run_dir / "summary.json").exists() else {}
    samples = _read_jsonl(run_dir / "state.jsonl")
    events = _read_jsonl(run_dir / "combat.jsonl")
    kills = [tuple(k) for k in summary.get("kills_list", [])]
    meta = {"kind": summary.get("kind", "dev_probe"), "dir": str(run_dir), "status": summary.get("status"),
            "seed": summary.get("seed"), "duration": summary.get("elapsed"), "fast": summary.get("fast"),
            "render": summary.get("render"), "errors": summary.get("error_count", 0),
            "warnings": summary.get("warning_count", 0), "created": run_dir.stat().st_mtime}
    return ingest(con, run_dir.name, meta, samples, events, kills)


# ---------------------------------------------------------------- load back

def resolve_run(con, ref="last"):
    if ref in (None, "last"):
        row = con.execute("SELECT run_id FROM runs ORDER BY created DESC LIMIT 1").fetchone()
    else:
        rows = con.execute("SELECT run_id FROM runs WHERE run_id LIKE ? ORDER BY created DESC", (f"{ref}%",)).fetchall()
        if len(rows) > 1 and not any(r[0] == ref for r in rows):
            raise SystemExit(f"ambiguous run prefix {ref!r}: {', '.join(r[0] for r in rows[:5])}")
        row = next((r for r in rows if r[0] == ref), rows[0] if rows else None)
    if row is None:
        raise SystemExit("no runs in the probe DB yet (run tools/agent_play.py or tools/dev_probe.py first)")
    return row[0]


def load_run(con, run_id):
    """-> (meta_row_dict, samples, events, kills) в формате probe_analysis."""
    con.row_factory = sqlite3.Row
    meta = dict(con.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone())
    enemies_at = {}
    for r in con.execute("SELECT * FROM enemy_samples WHERE run_id=? ORDER BY t", (run_id,)):
        enemies_at.setdefault(r["t"], []).append(
            {"id": r["eid"], "type": r["etype"], "hp": r["hp"], "max_hp": r["max_hp"], "pos": [r["x"], r["y"]]})
    samples = [{"t": r["t"], "player": {"id": meta["player_id"], "hp": r["hp"], "max_hp": r["max_hp"],
                                         "pos": [r["x"], r["y"]], "alive": bool(r["alive"]), "lvl": r["lvl"],
                                         "xp": r["xp"], "xp_next": r["xp_next"], "ai": r["ai"]},
                "enemies": enemies_at.get(r["t"], [])}
               for r in con.execute("SELECT * FROM samples WHERE run_id=? ORDER BY t", (run_id,))]
    events = [{"t": r["t"], "source": r["source"], "target": r["target"], "source_type": r["source_type"],
               "target_type": r["target_type"], "damage": r["damage"], "critical": bool(r["critical"]),
               "dodged": bool(r["dodged"])}
              for r in con.execute("SELECT * FROM combat WHERE run_id=? ORDER BY t", (run_id,))]
    kills = [(r["t"], r["eid"], r["etype"])
             for r in con.execute("SELECT * FROM kills WHERE run_id=? AND kind='kill' ORDER BY t", (run_id,))]
    con.row_factory = None
    return meta, samples, events, kills


# ---------------------------------------------------------------- output

def table(rows, headers, max_rows=40):
    rows = [["" if v is None else (f"{v:.4g}" if isinstance(v, float) else str(v)) for v in r] for r in rows]
    if not rows:
        return "(no rows)"
    widths = [max(len(h), *(len(r[i]) for r in rows[:max_rows])) for i, h in enumerate(headers)]
    lines = ["  ".join(h.ljust(w) for h, w in zip(headers, widths))]
    lines += ["  ".join(v.ljust(w) for v, w in zip(r, widths)) for r in rows[:max_rows]]
    if len(rows) > max_rows:
        lines.append(f"... {len(rows) - max_rows} more row(s)")
    return "\n".join(lines)


# ---------------------------------------------------------------- commands

def cmd_runs(con, args):
    rows = con.execute(
        "SELECT run_id, kind, status, seed, duration, kills, dmg_dealt, dmg_taken, min_hp, died, errors "
        "FROM runs ORDER BY created DESC LIMIT ?", (args.last,)).fetchall()
    return table(rows, ["run", "kind", "status", "seed", "dur", "kills", "dealt", "taken", "min_hp", "died", "err"])


STATS_SQL = {
    "by_side": """
        SELECT CASE WHEN source=:pid THEN 'hero->enemies' ELSE 'enemies->hero' END side,
               COUNT(*) attacks, SUM(dodged=0) hits,
               ROUND(100.0*SUM(dodged)/COUNT(*),1) dodge_pct,
               ROUND(100.0*SUM(critical AND dodged=0)/MAX(SUM(dodged=0),1),1) crit_pct,
               ROUND(SUM(CASE WHEN dodged=0 THEN damage END),1) dmg,
               ROUND(AVG(CASE WHEN dodged=0 THEN damage END),1) avg_hit,
               ROUND(MAX(damage),1) max_hit
        FROM combat WHERE run_id=:run AND (source=:pid OR target=:pid) GROUP BY side""",
    "by_type": """
        WITH seen AS (SELECT eid, etype, MIN(t) first_t FROM enemy_samples WHERE run_id=:run GROUP BY eid),
             k AS (SELECT kills.etype, kills.t - seen.first_t ttk FROM kills JOIN seen USING(eid)
                   WHERE kills.run_id=:run AND kills.kind='kill'),
             spawned AS (SELECT etype, COUNT(*) n FROM seen GROUP BY etype)
        SELECT spawned.etype,
               spawned.n seen,
               (SELECT COUNT(*) FROM kills WHERE run_id=:run AND kind='kill' AND etype=spawned.etype) killed,
               (SELECT ROUND(AVG(ttk),1) FROM k WHERE k.etype=spawned.etype) avg_ttk_s,
               (SELECT ROUND(SUM(damage),1) FROM combat WHERE run_id=:run AND dodged=0 AND target=:pid
                  AND source_type=spawned.etype) dmg_to_hero,
               (SELECT ROUND(SUM(damage),1) FROM combat WHERE run_id=:run AND dodged=0 AND source=:pid
                  AND target_type=spawned.etype) dmg_from_hero
        FROM spawned ORDER BY dmg_to_hero DESC NULLS LAST, seen DESC""",
    "hero": """
        SELECT ROUND(MIN(hp),1) min_hp, ROUND(AVG(hp),1) avg_hp, MAX(lvl) max_lvl,
               ROUND(MAX(xp),1) max_xp, MAX(enemies) max_enemies, ROUND(MAX(t),1) duration
        FROM samples WHERE run_id=:run""",
}


def cmd_stats(con, args):
    run = resolve_run(con, args.run)
    pid = con.execute("SELECT player_id FROM runs WHERE run_id=?", (run,)).fetchone()[0]
    params = {"run": run, "pid": pid}
    out = [f"run {run}"]
    for name, headers in (("hero", ["min_hp", "avg_hp", "max_lvl", "max_xp", "max_enemies", "duration"]),
                          ("by_side", ["side", "attacks", "hits", "dodge%", "crit%", "dmg", "avg_hit", "max_hit"]),
                          ("by_type", ["enemy_type", "seen", "killed", "avg_ttk_s", "dmg_to_hero", "dmg_from_hero"])):
        out += ["", f"[{name}]", table(con.execute(STATS_SQL[name], params).fetchall(), headers)]
    hp = [r[0] for r in con.execute("SELECT hp FROM samples WHERE run_id=? ORDER BY t", (run,))]
    if hp:
        out += ["", f"hero HP {analysis.sparkline(hp)}"]
    return "\n".join(out)


def cmd_why(con, args):
    run = resolve_run(con, args.run)
    meta, samples, events, kills = load_run(con, run)
    hyps = analysis.hypotheses(samples, events, {"kills": kills, "duration": meta["duration"],
                                                 "player_crit_chance": meta["crit_chance"]})
    return "\n".join([f"run {run} - hypotheses:", *analysis.format_hypotheses(hyps, args.limit)])


def cmd_predict(con, args):
    run = resolve_run(con, args.run)
    meta, samples, events, kills = load_run(con, run)
    fc = analysis.forecast(samples, events, {"kills": kills, "duration": meta["duration"]})
    return "\n".join([f"run {run} - forecast:", *analysis.format_forecast(fc)])


COMPARE_FIELDS = ["status", "duration", "kills", "dmg_dealt", "dmg_taken", "min_hp", "end_hp", "died", "errors", "warnings"]


def cmd_compare(con, args):
    a, b = resolve_run(con, args.a), resolve_run(con, args.b)
    con.row_factory = sqlite3.Row
    ra, rb = (dict(con.execute("SELECT * FROM runs WHERE run_id=?", (r,)).fetchone()) for r in (a, b))
    con.row_factory = None
    lines = [f"{a} -> {b}"]
    for f in COMPARE_FIELDS:
        va, vb = ra.get(f), rb.get(f)
        if va == vb:
            continue
        delta = f" ({vb - va:+.4g})" if isinstance(va, (int, float)) and isinstance(vb, (int, float)) else ""
        lines.append(f"{f}: {va} -> {vb}{delta}")
    per_type = {}
    for run in (a, b):
        pid = con.execute("SELECT player_id FROM runs WHERE run_id=?", (run,)).fetchone()[0]
        for etype, dmg in con.execute("SELECT source_type, ROUND(SUM(damage),1) FROM combat WHERE run_id=? "
                                      "AND target=? AND dodged=0 GROUP BY 1", (run, pid)):
            per_type.setdefault(etype, {})[run] = dmg
    for etype, d in sorted(per_type.items(), key=lambda kv: str(kv[0])):
        if d.get(a) != d.get(b):
            lines.append(f"dmg_to_hero[{etype}]: {d.get(a, 0)} -> {d.get(b, 0)}")
    if len(lines) == 1:
        lines.append("No differences in run-level metrics.")
    return "\n".join(lines)


TREND_METRICS = {"kills", "dmg_dealt", "dmg_taken", "min_hp", "end_hp", "died", "errors", "warnings", "duration"}


def cmd_trend(con, args):
    if args.metric not in TREND_METRICS:
        raise SystemExit(f"metric must be one of {sorted(TREND_METRICS)}")
    where, params = "", []
    if args.kind:
        where, params = "WHERE kind=?", [args.kind]
    rows = con.execute(f"SELECT run_id, {args.metric} FROM runs {where} ORDER BY created DESC LIMIT ?",
                       (*params, args.last)).fetchall()[::-1]
    vals = [float(v) for _, v in rows if v is not None]
    if not vals:
        return "(no data)"
    lines = [f"{args.metric} over {len(vals)} run(s), oldest->newest: {analysis.sparkline(vals)}",
             f"values: {', '.join(f'{v:.4g}' for v in vals)}"]
    if len(vals) >= 4:
        prev = vals[:-1]
        mean = sum(prev) / len(prev)
        sd = (sum((v - mean) ** 2 for v in prev) / len(prev)) ** 0.5
        z = (vals[-1] - mean) / sd if sd > 1e-9 else 0.0
        verdict = "OUTLIER vs previous runs" if abs(z) >= 2 else "within normal range"
        lines.append(f"latest {vals[-1]:.4g} vs mean {mean:.4g} (sd {sd:.3g}): z={z:+.2f} -> {verdict}")
    return "\n".join(lines)


def cmd_sql(con, args):
    cur = con.execute(args.query)
    if cur.description is None:
        con.commit()
        return f"ok ({cur.rowcount} row(s) affected)"
    return table(cur.fetchall(), [d[0] for d in cur.description], max_rows=args.max_rows)


def cmd_ingest(con, args):
    return "\n".join(f"ingested {ingest_dir(con, d)}" for d in args.dirs)


def main(argv=None):
    if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        # Windows + перенаправленный вывод (так его читает агент) = cp1252:
        # спарклайны и кириллица иначе роняют print()
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--db", default=None, help=f"SQLite file (default: {db_path()})")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("runs")
    p.add_argument("--last", type=int, default=10)
    for name in ("stats", "why", "predict"):
        p = sub.add_parser(name)
        p.add_argument("run", nargs="?", default="last")
        if name == "why":
            p.add_argument("--limit", type=int, default=None)
    p = sub.add_parser("compare")
    p.add_argument("a")
    p.add_argument("b", nargs="?", default="last")
    p = sub.add_parser("trend")
    p.add_argument("metric")
    p.add_argument("--last", type=int, default=10)
    p.add_argument("--kind", choices=["dev_probe", "agent_play"], default=None)
    p = sub.add_parser("sql")
    p.add_argument("query")
    p.add_argument("--max-rows", type=int, default=40)
    p = sub.add_parser("ingest")
    p.add_argument("dirs", nargs="+")
    args = parser.parse_args(argv)

    con = connect(args.db)
    try:
        print(globals()[f"cmd_{args.cmd}"](con, args))
    finally:
        con.close()


if __name__ == "__main__":
    main()
