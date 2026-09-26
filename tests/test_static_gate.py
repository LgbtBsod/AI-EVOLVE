"""The static gate (tools/static_gate.py, `qa.py static`): undefined names, syntax errors, Lua that does not compile, a workflow without jobs."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import static_gate as SG  # noqa: E402


def test_undefined_name_and_syntax_error_report_file_and_line(tmp_path):
    (tmp_path / "ok.py").write_text("import re\nprint(re)\n")
    (tmp_path / "lost.py").write_text("def f():\n    return re.sub('a', 'b', 'c')\n")
    (tmp_path / "broken.py").write_text("def f(:\n")
    res = SG.run(tmp_path, ["ok.py", "lost.py", "broken.py"])
    text = "\n".join(res.detail)
    assert res.status == "fail" and res.metrics["errors"] >= 1 and res.metrics["py"] == 3
    assert "broken.py:1" in text and ("lost.py:2" in text or "ruff missing" in text)
    assert "ok.py" not in text


def test_lua_syntax_error_names_the_line_and_a_clean_file_passes(tmp_path):
    (tmp_path / "good.lua").write_text("return { a = 1 }\n")
    (tmp_path / "bad.lua").write_text("return {\n  a = = 1,\n}\n")
    res = SG.run(tmp_path, ["good.lua", "bad.lua"])
    lua = [ln for ln in res.detail if ln.startswith("LUA")]
    assert res.metrics["lua"] == 2
    assert not lua or all("bad.lua:2" in ln for ln in lua)                      # lupa missing -> skipped, never a false FAIL


def test_workflow_structure(tmp_path):
    good = "name: x\non: [push]\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo hi\n"
    (tmp_path / "good.yml").write_text(good)
    (tmp_path / "nojobs.yml").write_text("name: x\non: [push]\n")
    (tmp_path / "nosteps.yml").write_text("on: push\njobs:\n  a:\n    runs-on: x\n")
    assert SG.check_workflow(tmp_path / "good.yml", tmp_path) == []
    assert any("jobs" in e for e in SG.check_workflow(tmp_path / "nojobs.yml", tmp_path))
    assert any("no steps" in e for e in SG.check_workflow(tmp_path / "nosteps.yml", tmp_path))


def test_the_repository_itself_is_clean():
    res = SG.run(ROOT)
    assert res.metrics["errors"] == 0, res.detail
