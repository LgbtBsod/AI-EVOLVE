"""Characterization of the pure helpers extracted from cmd_golden / cmd_test / cmd_docs / cmd_sweep / cmd_determinism."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import qa  # noqa: E402
from qa_plugins import determinism as det  # noqa: E402

REF = {"script": "s", "seed": 1, "status": "OK", "final": {"hp": 10, "kills": 1}, "invariants": [],
       "fingerprints": ["a", "b", "c"], "t": [0.0, 1.0, 2.0]}


def test_golden_verdict_equal_and_changed():
    fields = ["hp", "kills"]
    assert qa._golden_verdict("x", REF, dict(REF), fields) is None
    cur = {**REF, "final": {"hp": 9, "kills": 1}, "fingerprints": ["a", "z", "c"]}
    assert qa._golden_verdict("x", REF, cur, fields) == "x: CHANGED hp 10->9; trajectory diverges at t=1.0"
    assert qa._golden_verdict("x", None, REF, fields) == "x: NEW scenario (not in golden)"
    assert qa._golden_verdict("x", REF, {**REF, "seed": 2}, fields) == "x: scenario definition changed - re-record"


def test_golden_field_diffs_status_and_invariants():
    cur = {**REF, "status": "FAIL", "invariants": ["I1"]}
    assert qa._golden_field_diffs(REF, cur, ["hp"]) == ["status OK->FAIL", "invariants []->['I1']"]


def test_first_fp_divergence_length_mismatch():
    assert qa._first_fp_divergence(["a", "b"], ["a", "b"]) is None
    assert qa._first_fp_divergence(["a", "b"], ["a"]) == 1
    assert qa._first_fp_divergence(["a"], ["b"]) == 0


def test_doc_verdict_thresholds():
    assert qa._doc_verdict(0, [], []) == "NO-REFS"
    assert qa._doc_verdict(3, ["a"], []) == "CHECK"
    assert qa._doc_verdict(3, ["a", "b"], []) == "STALE"
    assert qa._doc_verdict(3, [], []) == "OK"


def test_doc_line_truncates():
    line = qa._doc_line("STALE", "a.md", 9, list("edcbafg"), ["x.py", "y.py", "z.py", "w.py"])
    assert line == "STALE   a.md (9 refs) missing: a, b, c, d ...; dead code: w.py, x.py, y.py ..."


def test_sweep_outcome_lines():
    ok = [{"final": {"alive": True}, "status": "OK", "expects": [{"passed": True}], "invariants": []},
          {"final": {"alive": False}, "status": "FAIL", "expects": [{"passed": False}],
           "invariants": [{"id": "I"}], "repro": "r"}]
    assert qa._sweep_outcome_lines(ok) == [
        "hero died in 1/2 runs (50%); status {'OK': 1, 'FAIL': 1}; expects passed 1/2",
        "invariant violations: I in 1 run(s)", "example failing run: r"]


def test_classify_helpers_and_header():
    recs = [{"outcome": "passed"}, {"outcome": "skipped"}, {"outcome": "failed"}]
    head = qa._test_header(recs, (1, 1, 0, 0), (1.26, 2, 9.0))
    assert head == "tests: 1 passed, 1 skipped, 1 failing (1 NEW, 0 flaky, 0 known) in 1.3s on 2 shard(s) (serial ~9s)"
    assert Counter(r["outcome"] for r in recs)["passed"] == 1


def test_determinism_helpers():
    args = SimpleNamespace(script="", variants=None)
    assert det._validate_args(args, {"variants": ["normal"]}) == (None, 2)
    assert det._exit_code([1], [], [1]) == 1
    assert det._exit_code([], ["e"], [1]) == 2
    assert det._exit_code([], [], []) == 2
    assert det._exit_code([], [], [1]) == 0
    assert det._head_line(det._Outcome(None, (1, 1, []), {}, {}, [SimpleNamespace(div=None, fp_a="f", fp_b="f")], [])) == \
        "RESULT determinism pairs=1 diverged=0 classes=1 first_frame=- t=- channel=none"


def test_brief_prints_relay_hint(monkeypatch, capsys):
    from qa_plugins import relay
    monkeypatch.setattr(relay, "unread_line", lambda root: "relay: ready")
    qa._print_relay_hint()
    assert capsys.readouterr().out == "relay: ready\n"
    monkeypatch.setattr(relay, "unread_line", lambda root: "")
    qa._print_relay_hint()
    assert capsys.readouterr().out == ""
