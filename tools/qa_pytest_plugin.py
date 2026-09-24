"""pytest-плагин для tools/qa.py: результаты тестов - в JSONL, а не в консоль.

Подключается как `-p qa_pytest_plugin` (tools/ в PYTHONPATH), файл вывода -
переменная окружения QA_PYTEST_OUT. Одна строка на тест/ошибку сбора:
{"id", "outcome": passed|failed|skipped|error|collect_error, "s": секунды,
 "msg": первая строка причины, "at": "файл:строка" места падения}.
qa.py сливает строки всех шардов и печатает только новое и важное.
"""
import json
import os
from pathlib import Path

_state = {"fh": None, "root": None}


def pytest_configure(config):
    path = os.environ.get("QA_PYTEST_OUT")
    if path:
        _state["fh"] = open(path, "a", encoding="utf-8")
        _state["root"] = Path(str(config.rootpath))


def pytest_unconfigure(config):
    if _state["fh"]:
        _state["fh"].close()
        _state["fh"] = None


def _write(rec):
    if _state["fh"]:
        _state["fh"].write(json.dumps(rec, ensure_ascii=False) + "\n")
        _state["fh"].flush()


def _where(path, line):
    try:
        path = Path(path).resolve().relative_to(_state["root"]).as_posix()
    except (ValueError, TypeError):
        path = str(path)
    return f"{path}:{line}"


def _in_project(path):
    p = str(path).replace("\\", "/")
    return "site-packages" not in p and "/lib/python" not in p and str(_state["root"]).replace("\\", "/") in \
        str(Path(path).resolve()).replace("\\", "/")


def _crash(report):
    crash = getattr(report.longrepr, "reprcrash", None)
    if crash is not None:
        msg = crash.message.strip().splitlines()[0][:300] if crash.message else ""
        where = _where(crash.path, crash.lineno)
        # unittest/stdlib-ассерты падают внутри stdlib: берём последний кадр проекта
        entries = getattr(getattr(report.longrepr, "reprtraceback", None), "reprentries", [])
        for entry in reversed(entries):
            loc = getattr(entry, "reprfileloc", None)
            if loc is not None and _in_project(loc.path):
                where = _where(loc.path, loc.lineno)
                break
        return msg, where
    text = str(report.longrepr or "").strip().splitlines()
    return (text[-1][:300] if text else ""), None


def pytest_runtest_logreport(report):
    if report.when == "call" or (report.when == "setup" and report.outcome != "passed") \
            or (report.when == "teardown" and report.outcome == "failed"):
        outcome = report.outcome
        if report.when != "call" and outcome == "failed":
            outcome = "error"
        rec = {"id": report.nodeid, "outcome": outcome, "s": round(report.duration, 3)}
        if outcome in ("failed", "error"):
            rec["msg"], rec["at"] = _crash(report)
        elif outcome == "skipped" and isinstance(report.longrepr, tuple):
            rec["msg"] = str(report.longrepr[2])[:200]
        _write(rec)


def pytest_collectreport(report):
    if report.outcome == "failed":
        text = str(report.longrepr or "").strip().splitlines()
        msg = next((l for l in reversed(text) if l.startswith("E ")), text[-1] if text else "")
        _write({"id": report.nodeid, "outcome": "collect_error", "s": 0.0, "msg": msg[:300].lstrip("E ").strip()})
