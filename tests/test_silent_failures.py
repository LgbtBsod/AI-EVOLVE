"""Row 1: unknown op kinds / flags / never-emitted events are loud."""
from src.effects import ops, schema
from src.effects.damage import CERTAIN_FLAGS
from tools.effect_schema.itemcheck import check_emitted
from tools.effect_schema.validate import validate_item


class _H:
    def op_stat_prefix(self, cx, tgt):
        return ""


class _Cx:
    ctx: dict = {}
    t = 0.0


def test_unknown_kind_counted_and_logged_once(caplog):
    ops.UNKNOWN_KIND_COUNT.clear()
    for _ in range(3):
        ops.apply_op(_H(), _Cx(), None, {"kind": "no_such_op_zz"})
    assert ops.UNKNOWN_KIND_COUNT["no_such_op_zz"] == 3
    assert sum("no_such_op_zz" in r.getMessage() for r in caplog.records) == 1


def test_flags_derived_from_certain_flags():
    assert set(CERTAIN_FLAGS) <= schema.FLAGS


def test_validator_rejects_unknown_kind_and_flag():
    item = {"name": "x", "effects": [{"id": "e", "trigger": {"kind": "passive"},
            "ops": [{"kind": "nope_kind", "target": "self"}]}]}
    assert "nope_kind" in " ".join(validate_item(item))
    item["effects"][0]["ops"] = [{"kind": "deal", "target": "self", "value": {"flat": 1}, "flags": ["bogus"]}]
    assert "unknown flags" in " ".join(validate_item(item))


def test_never_emitted_event_warns():
    item = {"name": "x", "effects": [{"id": "e", "trigger": {"kind": "event", "event": "combat_start"}, "ops": []}]}
    c = check_emitted(item)
    assert c.ok and "combat_start" in c.findings[0]
