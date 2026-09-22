#!/usr/bin/env python3
"""Shared before/after comparison logic for dev_probe.py's summary.json.

Used both by dev_probe.py itself (auto-compares against dev_probe_baseline.json
when one exists, so a run's own tail already answers "did this help or hurt")
and by dev_probe_diff.py (explicit --before/--after runs). Kept as pure
functions over plain dicts, no file I/O, so both callers share the exact same
delta logic instead of two copies that could drift apart.

Comparing summary.json fields (plain numbers/dicts) instead of summary.md text
means "did anything change" is a lookup, not an LLM-reasoning task over two
prose documents - and comparing event *categories* + *counts* instead of raw
timestamped timeline lines means run-to-run timing jitter (dt depends on
wall-clock frame time - see dev_probe.py's own --seed docstring) doesn't make
every line look "changed" just because timestamps drifted a few tenths of a
second.
"""

NUMERIC_FIELDS = [
    "dmg_dealt", "dmg_taken", "kill_count", "hits", "dodges", "crits",
    "min_hp", "end_hp", "warning_count", "blank_frame_count", "sample_count",
]


def diff_summaries(before, after):
    """Return a dict describing what changed between two summary.json dicts.
    Missing fields on either side are skipped rather than raising, so an older
    summary.json (from before a field was added) can still be compared."""
    result = {
        "status_changed": None,
        "numeric_changes": [],
        "new_event_kinds": [],
        "gone_event_kinds": [],
        "event_count_changes": [],
        "screenshot_reason_delta": [],
    }

    if before.get("status") != after.get("status"):
        result["status_changed"] = [before.get("status"), after.get("status")]

    for field in NUMERIC_FIELDS:
        b, a = before.get(field), after.get(field)
        if b is None or a is None or b == a:
            continue
        delta = round(a - b, 2) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None
        result["numeric_changes"].append({"field": field, "before": b, "after": a, "delta": delta})

    before_events = before.get("event_counts", {}) or {}
    after_events = after.get("event_counts", {}) or {}
    for kind in sorted(set(after_events) - set(before_events)):
        if after_events[kind]:
            result["new_event_kinds"].append({"kind": kind, "count": after_events[kind]})
    for kind in sorted(set(before_events) - set(after_events)):
        if before_events[kind]:
            result["gone_event_kinds"].append({"kind": kind, "count": before_events[kind]})
    for kind in sorted(set(before_events) & set(after_events)):
        if before_events[kind] != after_events[kind]:
            result["event_count_changes"].append({"kind": kind, "before": before_events[kind], "after": after_events[kind]})

    before_reasons = before.get("screenshot_reason_counts", {}) or {}
    after_reasons = after.get("screenshot_reason_counts", {}) or {}
    for kind in sorted(set(before_reasons) | set(after_reasons)):
        b, a = before_reasons.get(kind, 0), after_reasons.get(kind, 0)
        if b != a:
            result["screenshot_reason_delta"].append({"kind": kind, "before": b, "after": a})

    return result


def diff_is_empty(diff):
    return not any(diff[k] for k in diff if k != "status_changed") and diff["status_changed"] is None


def format_diff(diff, before_label="before", after_label="after"):
    """Render a diff_summaries() result as a short text block - this is the
    whole point: read this instead of two full summary.md files."""
    if diff_is_empty(diff):
        return f"No differences between {before_label} and {after_label}."

    lines = []
    if diff["status_changed"]:
        lines.append(f"status: {diff['status_changed'][0]} -> {diff['status_changed'][1]}")
    for c in diff["numeric_changes"]:
        delta = f" ({'+' if isinstance(c['delta'], (int, float)) and c['delta'] > 0 else ''}{c['delta']})" \
            if c["delta"] is not None else ""
        lines.append(f"{c['field']}: {c['before']} -> {c['after']}{delta}")
    for e in diff["new_event_kinds"]:
        lines.append(f"NEW: {e['kind']} (x{e['count']})")
    for e in diff["gone_event_kinds"]:
        lines.append(f"GONE: {e['kind']} (was x{e['count']})")
    for e in diff["event_count_changes"]:
        lines.append(f"{e['kind']}: {e['before']}x -> {e['after']}x")
    for s in diff["screenshot_reason_delta"]:
        lines.append(f"screenshots[{s['kind']}]: {s['before']} -> {s['after']}")
    return "\n".join(lines)
