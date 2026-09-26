"""One path-glob matcher for the QA tools (stdlib only): `PurePosixPath.full_match` semantics (Python 3.13+).

`**` as a segment matches zero or more directories, `*` and `?` never cross a `/`. Paths use `/` separators."""
from __future__ import annotations

from pathlib import PurePosixPath


def gmatch(path: str, glob: str) -> bool:
    return PurePosixPath(path).full_match(glob)


def matches(path: str, patterns) -> bool:
    """True when `path` matches any glob of `patterns`."""
    return any(gmatch(path, g) for g in patterns)
