import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from jsonl_io import append_jsonl, read_jsonl, tail_jsonl  # noqa: E402


def test_roundtrip_lf_utf8(tmp_path):
    p = tmp_path / "sub" / "x.jsonl"
    append_jsonl(p, {"a": 1, "t": "привет"})
    append_jsonl(p, {"a": 2})
    raw = p.read_bytes()
    assert b"\r" not in raw and "привет".encode() in raw
    assert read_jsonl(p) == [{"a": 1, "t": "привет"}, {"a": 2}]


def test_corrupt_and_partial_lines_are_skipped(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text('{"a": 1}\nnot json\n\n{"a": 2}\n{"a": ', encoding="utf-8")
    assert read_jsonl(p) == [{"a": 1}, {"a": 2}]
    assert tail_jsonl(p, 2) == [{"a": 2}]


def test_missing_file_and_tail(tmp_path):
    assert read_jsonl(tmp_path / "no.jsonl") == [] and tail_jsonl(tmp_path / "no.jsonl", 3) == []
    p = tmp_path / "x.jsonl"
    for i in range(5):
        append_jsonl(p, {"i": i})
    assert tail_jsonl(p, 2) == [{"i": 3}, {"i": 4}] and tail_jsonl(p, 0) == []
