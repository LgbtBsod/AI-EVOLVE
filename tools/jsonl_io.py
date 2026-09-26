"""One jsonl reader/writer for the tools (stdlib only): utf-8, LF-only, tolerant of partial or corrupt lines."""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path


def _rows(lines):
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except ValueError:  # a torn write or a hand edit: skip the line, keep the rest
            continue


def read_jsonl(path) -> list:
    """All parsable rows of `path` ([] when the file is absent or unreadable)."""
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as fh:
            return list(_rows(fh))
    except OSError:
        return []


def tail_jsonl(path, n: int) -> list:
    """The parsable rows among the last `n` lines of `path`."""
    try:
        with Path(path).open(encoding="utf-8", errors="replace") as fh:
            return list(_rows(deque(fh, maxlen=max(0, n))))
    except OSError:
        return []


def append_jsonl(path, obj) -> None:
    """Append one row as a single LF-terminated line (creates parent dirs)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
