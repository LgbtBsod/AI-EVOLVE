"""qa.py quality - the code-quality ratchet from the command line (tools/quality_metrics.py; same numbers as `qa.py check --name quality`).

    qa.py quality                     # measure now: the check line + every regression / improvement
    qa.py quality --worst 10          # top offenders: functions by CC, files by violations, with a one-line SRP hint (qa.lua)
    qa.py quality --explain BLE001    # what a rule/metric means and the usual fix (also blind_except cc11 dup_defs layers vulture)
    qa.py quality --update-baseline   # rewrite tests/quality_baseline.json; refuses to RAISE any number unless --force
    qa.py quality --scope tools       # game | tools | all (default): one check line per scope (quality, quality_tools)
    qa.py quality --result            # what the `quality` check of qa.lua parses: detail lines, `repro:`, one RESULT line
"""
from __future__ import annotations

import argparse
import time

import qa_report as R
import quality_metrics as QM
from probe_settings import qa_settings


def _one(args, rcfg, scope: str, base_cfg: dict) -> int:
    """One scope: measure, then --update-baseline | --worst | the check line + findings. Returns the exit code (0/1/2)."""
    name = "quality" if scope == "game" else f"quality_{scope}"
    try:
        cfg = QM.scoped_cfg(base_cfg, scope)
        base = QM.load_baseline(QM.baseline_path(cfg))
        t0 = time.perf_counter()
        m = QM.measure(cfg)
    except QM.ToolError as exc:
        print(R.format_line(R.Result("error", {}, [str(exc)], "python tools/qa.py doctor", 0.0, name), 7, cfg=rcfg))
        return 2
    if args.update_baseline:
        ok, lines = QM.update_baseline(QM.baseline_path(cfg), m, args.force)
        print("\n".join(lines))
        return 0 if ok else 1
    if args.worst is not None:
        n = args.worst or int((cfg.get("budget") or {}).get("worst", 10))
        lines = QM.worst_lines(cfg, m, n, rcfg["line_width"])
        lines[0] = f"[{scope}] " + lines[0]
        print("\n".join(R.budgeted(lines, lines, rcfg, R.write_full)))
        return 0
    res = QM.evaluate(cfg, m, base)
    if args.result:
        print("\n".join(QM.result_lines(res)))
        return R.exit_code([res])
    res.name, res.dur = name, time.perf_counter() - t0
    prev = R.load_prev()
    print(R.format_line(res, len(res.name), R.delta_tokens(res.metrics, prev.get(res.key), rcfg), rcfg))
    if base is not None:
        worse, better = QM.compare(base, m)
        shown = [f"  {f.text()}{f.where(m)}" for f in worse if f.kind not in ("total", "rule")]
        shown += [f"  (better) {f.text()}" for f in better if f.kind not in ("total", "rule")]
        if shown:
            print("\n".join(R.budgeted(shown[:rcfg["max_lines"] - 2], shown, rcfg, R.write_full)))
    R.append_history([res], {}, rcfg)
    return R.exit_code([res])


def cmd_quality(args) -> int:
    settings = qa_settings()
    rcfg = R.report_cfg(settings)
    try:
        base_cfg = QM.load_cfg(settings)
        if args.explain:
            cfg = QM.scoped_cfg(base_cfg, "game" if args.scope == "all" else args.scope)
            print("\n".join(QM.explain_lines(base_cfg, args.explain, QM.load_baseline(QM.baseline_path(cfg)))))
            return 0
        scopes = ["game", *(base_cfg.get("scopes") or {})] if args.scope == "all" else [args.scope]
    except QM.ToolError as exc:
        print(R.format_line(R.Result("error", {}, [str(exc)], "python tools/qa.py doctor", 0.0, "quality"), 7, cfg=rcfg))
        return 2
    if args.result and len(scopes) > 1:
        scopes = ["game"]              # the machine form is ONE RESULT line: `--scope tools --result` for the other scope
    return max(_one(args, rcfg, s, base_cfg) for s in scopes)


def register(sub):
    p = sub.add_parser("quality", help="code-quality ratchet: SOLID/DRY/SRP/SSOT violations may not grow",
                       description=__doc__.strip().splitlines()[0], epilog=__doc__.split("\n\n", 1)[1],
                       formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--worst", nargs="?", type=int, const=0, default=None, metavar="N", help="top N offenders (default: quality.budget.worst)")
    p.add_argument("--scope", choices=["game", "tools", "all"], default="all",
                   help="game = src/ modules, tools = tools/ modules (own baseline); default all")
    p.add_argument("--explain", metavar="RULE", help="one screen about a rule or metric")
    p.add_argument("--update-baseline", action="store_true", help="rewrite the baseline (never raises a number without --force)")
    p.add_argument("--result", action="store_true", help="machine form for `qa.py check` (RESULT line)")
    p.add_argument("--force", action="store_true", help="with --update-baseline: allow raising numbers (adding a rule, splitting a module)")
    p.set_defaults(func=cmd_quality)
