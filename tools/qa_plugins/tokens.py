"""qa.py tokens [--session latest|ID|PATH] [--agents] [--top N] [--json] - transcript waste ledger, one QA line per metric group, worst first.

    qa.py tokens                    # the latest session of this project: turns, calls/turn, batchable runs, result/written tokens, reads, retries
    qa.py tokens --agents --top 5   # + the sub-agent summary and the 5 heaviest agents (turns, calls/turn, saveable, biggest result)

Parsing: tools/token_ledger.py (groups blocks by message.id). Thresholds, patterns, `| use:` replacements: `tokens` in lua_content/qa.lua.
Trend: dev_probe_output/qa/tokens_history.jsonl (previous run of the same session / agent summary). Sizes are chars/4 (approximate).
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import token_ledger as L
from probe_settings import ROOT, qa_settings
from qa_report import QA_OUT, fmt_num

TOKENS_HISTORY = QA_OUT / "tokens_history.jsonl"
TREND_KEYS = ("cpt", "saveable_pct", "result_tok", "unbounded", "repeats")


def cfg() -> dict:
    return dict(qa_settings().get("tokens") or {})


def previous(key: str, path: Path = TOKENS_HISTORY) -> dict:
    if not path.is_file():
        return {}
    last: dict = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if rec.get("key") == key:
            last = rec.get("m") or {}
    return last


def record(key: str, m: dict, keep: int, path: Path = TOKENS_HISTORY) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": int(time.time()), "key": key, "m": {k: m[k] for k in TREND_KEYS if k in m}}) + "\n")
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > keep * 2:
        path.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")


def kv(k: str, v, prev: dict) -> str:
    """`k=v` plus the change against the previous run: `k=1.13(+0.02)`."""
    s = f"{k}={fmt_num(v)}"
    old = prev.get(k)
    if isinstance(v, (int, float)) and isinstance(old, (int, float)) and old != v:
        s += f"({fmt_num(round(v - old, 2))})".replace("(", "(+" if v > old else "(", 1)
    return s


def _row(bad: bool, weight: int, name: str, body: str, use: str) -> tuple:
    return (0 if bad else 1, -weight, f"{'warn' if bad else 'ok':<5} {name:<10} {body} | use: {use}")


def group_rows(m: dict, cfg: dict, prev: dict, guard: dict) -> list[tuple]:
    """(severity, -weight, line) per metric group; sorted worst first by the caller."""
    w, use = cfg["warn"], cfg["use"]
    wr = m["writes"]
    written = wr.get("edit", 0) + wr.get("write", 0) + wr.get("heredoc", 0)
    top = " ".join(f"{t}={n}" for t, n in list(m["by_tool"].items())[:4])
    heavy = "; ".join(f"{n}tok {t} {p[-40:]}" for n, t, p in m["heavy"])
    rows = [
        _row(m["cpt"] < w["calls_per_turn_below"] or m["saveable_pct"] > w["saveable_pct_over"], m["saveable"] * 2000, "batch",
             " ".join([f"turns={m['turns']}", f"calls={m['calls']}", kv("cpt", m["cpt"], prev), f"multi={m['multi_pct']}%", kv("saveable_pct", m["saveable_pct"], prev)]), use["batch"]),
        _row(m["unbounded"] > w["unbounded_reads_over"], m["unbounded"] * 2500, "unbounded", f"{kv('unbounded', m['unbounded'], prev)} " + " ".join(p[-40:] for p in m["unbounded_paths"][:3]), use["unbounded"]),
        _row(m["repeats"] > w["repeat_reads_over"], m["repeats"] * 1500, "repeats", kv("repeats", m["repeats"], prev), use["repeats"]),
        _row(False, m["result_tok"], "results", " ".join([kv("result_tok", m["result_tok"], prev), top]), use["results"]),
        _row(bool(m["heavy"]) and m["heavy"][0][0] > w["heavy_tokens_over"], m["heavy"][0][0] if m["heavy"] else 0, "heavy", heavy, use["heavy"]),
        _row(written > w["write_tokens_over"], written, "writes", f"written_tok={written} edit_old={wr.get('edit_old', 0)}/{wr.get('edit', 0)} write={wr.get('write', 0)} heredoc={wr.get('heredoc', 0)}", use["writes"]),
        _row(m["retries"] > w["retries_over"], m["retries"] * 1000, "retries", f"retries={m['retries']}", use["retries"]),
        _row(False, m["relays"], "relays", f"relays={m['relays']}", use["relays"]),
    ]
    if guard:
        rows.append(_row(False, 0, "guard", " ".join(f"{k}={v}" for k, v in guard.items()), use["guard"]))
    return rows


def agent_rows(agents: dict, cfg: dict, prev: dict, top: int) -> tuple[dict, list[str]]:
    """Aggregate over all sub-agent logs + one line per heaviest agent."""
    n = len(agents)
    turns = sum(a["turns"] for a in agents.values())
    calls = sum(a["calls"] for a in agents.values())
    saved = sum(a["saveable"] for a in agents.values())
    agg = {"cpt": round(calls / turns, 2) if turns else 0.0, "saveable_pct": round(100 * saved / turns) if turns else 0,
           "result_tok": sum(a["result_tok"] for a in agents.values())}
    bad = agg["saveable_pct"] > cfg["warn"]["saveable_pct_over"]
    head = _row(bad, saved * 2000, "agents", f"n={n} avg_turns={round(turns / n) if n else 0} {kv('cpt', agg['cpt'], prev)} {kv('saveable_pct', agg['saveable_pct'], prev)} {kv('result_tok', agg['result_tok'], prev)}", cfg["use"]["batch"])
    heavy = sorted(agents.items(), key=lambda kv_: -kv_[1]["result_tok"])[:top]
    lines = [head[2]] + [f"      {name[-12:]} turns={a['turns']} cpt={a['cpt']} saveable={a['saveable_pct']}% result_tok={a['result_tok']} "
                         f"{('biggest=' + str(a['heavy'][0][0]) + 'tok ' + a['heavy'][0][1] + ' ' + a['heavy'][0][2][-30:]) if a['heavy'] else ''}".rstrip()
                         for name, a in heavy]
    return agg, lines


def collect(main: Path, c: dict, with_agents: bool) -> tuple[dict, dict]:
    _, subs = L.session_files(main)
    m = L.metrics(L.parse_log(main), c)
    agents = {p.stem: L.metrics(L.parse_log(p), c) for p in subs} if with_agents else {}
    return m, agents


def header(key: str, m: dict, n_agents: int, lines: list[str], t0: float) -> str:
    worst = "WARN" if any(ln.startswith("warn") for ln in lines) else "OK"
    return (f"QA verdict={worst} tokens session={key[:8]} turns={m['turns']} calls={m['calls']} cpt={m['cpt']} saveable={m['saveable_pct']}% "
            f"result_tok~{m['result_tok']} agents={n_agents} dur={time.time() - t0:.1f}s")


def build(main: Path, c: dict, with_agents: bool, top: int, history: Path | None = TOKENS_HISTORY) -> tuple[list[str], dict]:
    """(printed lines, data). `history` None = do not read or write the trend file."""
    t0 = time.time()
    m, agents = collect(main, c, with_agents)
    key, keep = main.stem, int(c["trend_keep"])
    rows = sorted(group_rows(m, c, previous(key, history) if history else {}, L.guard_stats(QA_OUT / "guards.jsonl")))
    lines = [r[2] for r in rows][:top + 4]
    extra: dict = {}
    if with_agents:
        agg, alines = agent_rows(agents, c, previous(key + ":agents", history) if history else {}, top)
        lines, extra = lines + alines, {"agents": agg}
        history and record(key + ":agents", agg, keep, history)
    history and record(key, m, keep, history)
    n_agents = len(agents) if with_agents else len(L.session_files(main)[1])
    return [header(key, m, n_agents, lines, t0), *lines], {"session": key, **m, **extra, "agent_rows": agents}


def workflow_lines(run: Path, agents: list[dict], wc: dict) -> list[str]:
    """Header + one line per agent, untyped (cold start above `untyped_first_ctx`) first."""
    bad = [a for a in agents if a["first_ctx"] > wc["untyped_first_ctx"]]
    tot = {k: sum(a[k] for a in agents) for k in ("cw", "cr", "out", "billed")}
    head = (f"QA verdict={'WARN' if bad else 'OK'} tokens workflow={run.name} agents={len(agents)} untyped={len(bad)} billed={fmt_num(tot['billed'])} "
            f"cw={fmt_num(tot['cw'])} cr={fmt_num(tot['cr'])} out={fmt_num(tot['out'])}")
    rows = [f"{'warn' if a in bad else 'ok':<5} {a['id']} {a['label'][:18]:18} turns={a['turns']} first_ctx={a['first_ctx']} cw={a['cw']} cr={a['cr']} out={a['out']} "
            f"billed={a['billed']} cold_pct={a['cold_pct']}" + (" UNTYPED | use: " + wc["use"] if a in bad else "")
            for a in sorted(agents, key=lambda a: (a not in bad, -a["billed"]))]
    return [head, *rows]


def cmd_workflow(args, c: dict) -> int:
    run = L.find_workflow(Path.home() / ".claude" / "projects", args.workflow)
    if run is None:
        print(f"tokens: no workflow run '{args.workflow}' under ~/.claude/projects")
        return 2
    lines = workflow_lines(run, L.workflow_agents(run), c["workflow"])
    print("\n".join(lines))
    return 0


def cmd_tokens(args) -> int:
    c = cfg()
    if args.workflow:
        return cmd_workflow(args, c)
    main = L.find_session(Path.home() / ".claude" / "projects", ROOT, args.session)
    if main is None:
        print("RESULT status=OK turns=0 agents=0 (no transcript for this project under ~/.claude/projects)" if args.check
              else "tokens: no transcript for this project under ~/.claude/projects")
        return 0 if args.check else 2
    top = args.top if args.top is not None else int(c["top"])
    if args.check:
        m, agents = collect(main, c, False)
        print(f"RESULT status=OK turns={m['turns']} agents={len(L.session_files(main)[1])} cpt={m['cpt']}")
        return 0
    lines, data = build(main, c, args.agents, top)
    print(json.dumps(data, ensure_ascii=False) if args.json else "\n".join(lines))
    return 0


def register(sub):
    p = sub.add_parser("tokens", help="transcript waste ledger: turns, calls/turn, batchable runs, result/written tokens, reads, retries, trend",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--session", default="latest", help="latest | session id prefix | PATH to a .jsonl")
    p.add_argument("--workflow", nargs="?", const="latest", metavar="RUN", help="per-agent billing of a workflow run (latest | wf_ID): first_ctx, cw, cr, out, billed, UNTYPED flag")
    p.add_argument("--agents", action="store_true", help="also the sub-agent summary and the heaviest agents")
    p.add_argument("--top", type=int, default=None, help="rows: metric groups / heaviest agents (default: tokens.top)")
    p.add_argument("--json", action="store_true", help="machine output")
    p.add_argument("--check", action="store_true", help="one `RESULT status=OK turns=N agents=M` line for `qa.py check`")
    p.set_defaults(func=cmd_tokens)
