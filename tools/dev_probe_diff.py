#!/usr/bin/env python3
"""Delta-only comparison between two tools/dev_probe.py runs.

Without this, comparing "before my fix" vs "after my fix" means opening both
summary.md files in full (Config/Timeline/Combat totals/Player HP/Issues
detected/Screenshots - typically 20-60 lines each) and reasoning over the
diff yourself. This reads each run's summary.json instead (a few plain
fields dev_probe.py already computed in finish()) and prints ONLY what
changed - usually a handful of lines, sometimes "No differences" - no image
opening involved even when screenshot counts differ (see --before/--after
screenshot reason counts, not the images themselves).

Usage:
    .venv/Scripts/python.exe tools/dev_probe_diff.py --before dev_probe_output/2026...aaa --after dev_probe_output/2026...bbb
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dev_probe_compare import diff_is_empty, diff_summaries, format_diff  # noqa: E402


def load_summary(run_dir):
    path = Path(run_dir) / "summary.json"
    if not path.exists():
        print(f"error: {path} not found (run tools/dev_probe.py first, or check the path)", file=sys.stderr)
        sys.exit(2)
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--before", required=True, help="a dev_probe.py output directory (the earlier run)")
    parser.add_argument("--after", required=True, help="a dev_probe.py output directory (the later run)")
    args = parser.parse_args()

    before = load_summary(args.before)
    after = load_summary(args.after)
    diff = diff_summaries(before, after)

    print(f"Comparing {args.before} -> {args.after}\n")
    print(format_diff(diff, before_label=args.before, after_label=args.after))
    sys.exit(0 if diff_is_empty(diff) else 1)


if __name__ == "__main__":
    main()
