"""Executable specs of `qa.py coverage` (tools/qa_plugins/coverage.py) over tests/fixtures/ability_corpus.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("qa_plugin_coverage", ROOT / "tools" / "qa_plugins" / "coverage.py")
cov = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cov)

CORPUS = json.loads(cov.CORPUS.read_text(encoding="utf-8"))


def test_corpus_shape_and_doc_numbers():
    assert len(CORPUS) == 60
    c = cov.compute(CORPUS, cov.canon_kinds(), cov.alias_rows())
    assert c["hand"] == 46.7 and c["spec"] == 78.3          # docs/EFFECT_GAP.md said 80.0 before #40 got its honest lack `unbounded_reality` (Reality warp is a model-breaker)


def test_aliases_only_raise_coverage_and_inexact_are_not_counted():
    canon = cov.canon_kinds()
    rows = cov.alias_rows()
    base = cov.compute(CORPUS, canon, {})
    full = cov.compute(CORPUS, canon, rows)
    assert full["with_aliases"] >= base["with_aliases"] > 0
    inexact_only = {k: v for k, v in rows.items() if not v.get("exact")}
    assert cov.compute(CORPUS, canon, inexact_only)["with_aliases"] == base["with_aliases"]


def test_floor_is_a_ratchet_and_alias_targets_are_canon():
    from probe_settings import qa_settings
    cfg = qa_settings()["coverage"]
    c = cov.compute(CORPUS, cov.canon_kinds(), cov.alias_rows())
    assert cov.verdict(c, cfg) in ("ok", "warn")
    assert all(v["canon"] in cov.canon_kinds() for v in cov.alias_rows().values())


def test_holdout_corpus_shape_and_disjoint_ids():
    main = json.loads(cov.CORPUS.read_text(encoding="utf-8"))
    hold = json.loads(cov.corpus_path("holdout").read_text(encoding="utf-8"))
    assert len(hold) == 60 and {a["id"] for a in hold}.isdisjoint({a["id"] for a in main})
    assert all(a["hand_canon"] is None and isinstance(a["lacks"], list) for a in hold)


def test_holdout_config_and_floor_ratchet():
    from probe_settings import qa_settings
    cfg = qa_settings()["coverage"]
    assert cov.corpus_cfg(cfg, "holdout") == {"floor": cfg["holdout_floor"], "target": cfg["holdout_target"]}
    hold = json.loads(cov.corpus_path("holdout").read_text(encoding="utf-8"))
    c = cov.compute(hold, cov.canon_kinds(), cov.alias_rows())
    assert c["with_aliases"] + 1e-9 >= cfg["holdout_floor"]
