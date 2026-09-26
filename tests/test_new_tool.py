"""qa.py new tool: scaffold, refuse to overwrite, DRY guard."""
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import tool_registry as TR
from probe_settings import ROOT, qa_settings
from qa_plugins import new


@pytest.fixture
def tmp_root(tmp_path):
    (tmp_path / "tools" / "qa_plugins").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    return tmp_path


@pytest.mark.parametrize("plugin", [False, True])
def test_scaffold_writes_importable_files(tmp_root, plugin):
    tool, test = new.scaffold(tmp_root, "zz_demo", "demo purpose line", plugin)
    assert tool.read_text().startswith('"""') and "demo purpose line" in tool.read_text()
    assert "def test_zz_demo_runs" in test.read_text()
    spec = importlib.util.spec_from_file_location("zz_demo_t", tool)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert (hasattr(mod, "register") if plugin else mod.main([]) == 0)


def test_scaffold_refuses_overwrite(tmp_root):
    new.scaffold(tmp_root, "zz_demo", "demo", False)
    with pytest.raises(FileExistsError):
        new.scaffold(tmp_root, "zz_demo", "demo", False)


def test_similar_finds_existing_tool():
    settings = qa_settings()
    hits = new.similar(TR.build(ROOT, settings), "trend slow or flipping checks history", settings.get("tools") or {})
    assert hits and hits[0][1].id == "trend" and hits[0][0] >= settings["new_tool"]["similar_score"]
