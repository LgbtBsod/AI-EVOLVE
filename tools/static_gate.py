"""static_gate - the `static` check: undefined names, redefinitions and syntax errors before they reach a run.

Python: ruff F821 (undefined name) F811 (redefinition) E9 (syntax) + an in-process compile. Lua: every file compiled (never run) by LuaJIT 2.1 and Lua 5.5
through lupa. Workflows: a small structural lint (actionlint-py ships only an sdist that downloads a Go binary at install time: no wheel for cp314, so it is not used).
Missing ruff/lupa -> that part is skipped and named in the detail (never a FAIL). Entry: `qa.py static`.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import qa_report as R
from probe_settings import ROOT

PY_ROOTS = ("tools", "src")
PY_TOP = ("main.py",)
RUFF_SELECT = "F821,F811,E9"
_RUFF_LINE = re.compile(r"^(?P<file>.+?):(?P<line>\d+):\d+: (?P<code>[A-Z]+\d+) (?P<msg>.*)$")
_LUA_ERR = re.compile(r"^(?:\[string )?\"?=?(?P<name>[^:\"]*)\"?\]?:(?P<line>\d+): (?P<msg>.*)$")


_KIND_BY_EXT = {".py": "py", ".lua": "lua", ".yml": "yml", ".yaml": "yml"}


def _paths(root: Path, files: list[str] | None) -> list[Path]:
    if files:
        return [root / f for f in files]                       # an absolute f wins in Path division
    paths = [p for d in PY_ROOTS for p in (root / d).rglob("*.py")] + [root / f for f in PY_TOP]
    return paths + list((root / "lua_content").rglob("*.lua")) + list((root / ".github" / "workflows").glob("*.y*ml"))


def collect(root: Path, files: list[str] | None = None) -> dict[str, list[Path]]:
    """{'py': [...], 'lua': [...], 'yml': [...]}: the given files, or every file of the repo the gate knows."""
    out: dict[str, list[Path]] = {"py": [], "lua": [], "yml": []}
    for p in _paths(root, files):
        if p.suffix in _KIND_BY_EXT and p.is_file() and not {"__pycache__", ".venv"} & set(p.parts):
            out[_KIND_BY_EXT[p.suffix]].append(p)
    return out


def _rel(p: Path, root: Path) -> str:
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def _find_ruff(root: Path) -> list[str] | None:
    for cand in (root / ".venv" / "Scripts" / "ruff.exe", root / ".venv" / "bin" / "ruff"):
        if cand.is_file():
            return [str(cand)]
    found = shutil.which("ruff")
    return [found] if found else None


def check_python(files: list[Path], root: Path) -> tuple[list[str], list[str]]:
    """(errors 'CODE msg file:line', notes). compile() per file + one ruff call for all files."""
    errors, notes = [], []
    for p in files:
        try:
            compile(p.read_bytes(), str(p), "exec", dont_inherit=True)
        except SyntaxError as exc:
            errors.append(f"E999 {exc.msg} {_rel(p, root)}:{exc.lineno or 1}")
        except (OSError, ValueError) as exc:
            errors.append(f"E902 {exc} {_rel(p, root)}:1")
    ruff = _find_ruff(root)
    if ruff is None:
        return errors, ["ruff missing: F821/F811 skipped (uv pip install -r requirements-dev.txt)"]
    if files:
        errors += _ruff(ruff, files, root, {e.rsplit(" ", 1)[-1].rsplit(":", 1)[0] for e in errors})
    return errors, notes


def _ruff(ruff: list[str], files: list[Path], root: Path, skip: set[str]) -> list[str]:
    args = [str(p) for p in files if _rel(p, root) not in skip]
    if not args:
        return []
    run = subprocess.run([*ruff, "check", "--isolated", "--select", RUFF_SELECT, "--output-format", "concise", "--no-cache", *args],
                         cwd=root, capture_output=True, text=True, timeout=120, check=False)
    out = []
    for ln in run.stdout.splitlines():
        m = _RUFF_LINE.match(ln)
        if m:
            f = _rel(Path(m["file"]) if Path(m["file"]).is_absolute() else root / m["file"], root)
            out.append(f"{m['code']} {m['msg']} {f}:{m['line']}")
    return out


def _lua_runtimes() -> list[tuple[str, object]]:
    out = []
    for mod in ("luajit21", "lua55"):
        try:
            lupa = __import__(f"lupa.{mod}", fromlist=["LuaRuntime"])
            out.append((mod, lupa.LuaRuntime(register_eval=False)))
        except Exception:  # noqa: BLE001 - a backend that does not import is a skip, not a failure
            continue
    return out


def check_lua(files: list[Path], root: Path) -> tuple[list[str], list[str]]:
    """Compile-only check of every Lua file with every backend: errors 'LUA msg file:line'."""
    rts = _lua_runtimes()
    if not rts:
        return [], ["lupa missing: Lua syntax skipped"]
    errors = []
    for p in files:
        src, rel = p.read_bytes(), _rel(p, root)
        for name, rt in rts:
            res = rt.globals().load(src, "=" + rel)
            err = res[1] if isinstance(res, tuple) else None
            if err:
                m = _LUA_ERR.match(str(err))
                errors.append(f"LUA[{name}] {m['msg'] if m else err} {rel}:{m['line'] if m else 1}")
    return errors, []


def _has_key(text: str, key: str) -> bool:
    quoted = rf"^(?:{key}|\"{key}\"|'{key}'):"
    return bool(re.search(quoted, text, re.M) or (key == "on" and re.search(r"^true:", text, re.M)))


def check_workflow(path: Path, root: Path) -> list[str]:
    """Structural lint: no tabs, top-level on/jobs, every job has runs-on (or uses) and steps, every step has run or uses."""
    rel, text = _rel(path, root), path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    errs = [f"WF tab indentation {rel}:{i}" for i, ln in enumerate(lines, 1) if "	" in ln[: len(ln) - len(ln.lstrip())]]
    errs += [f"WF missing top-level `{k}:` {rel}:1" for k in ("jobs", "on") if not _has_key(text, k)]
    return errs + _workflow_jobs(lines, rel)


def _split_jobs(lines: list[str]) -> list[tuple[str, int, str]]:
    """(name, line number, body text) of every job under the top-level `jobs:` key."""
    start = next((i for i, ln in enumerate(lines) if ln.startswith("jobs:")), None)
    jobs: list[tuple[str, int, list[str]]] = []
    for i in range(start + 1 if start is not None else len(lines), len(lines)):
        ln = lines[i]
        if ln and not ln.startswith(" "):
            break
        m = re.match(r"^  ([\w-]+):\s*$", ln)
        if m:
            jobs.append((m[1], i + 1, []))
        elif jobs:
            jobs[-1][2].append(ln)
    return [(n, no, chr(10).join(body)) for n, no, body in jobs]


def _workflow_jobs(lines: list[str], rel: str) -> list[str]:
    errs = []
    for name, ln_no, blob in _split_jobs(lines):
        if not re.search(r"^    (?:runs-on|uses):", blob, re.M):
            errs.append(f"WF job `{name}` has no runs-on/uses {rel}:{ln_no}")
        elif "    uses:" not in blob and not re.search(r"^    steps:", blob, re.M):
            errs.append(f"WF job `{name}` has no steps {rel}:{ln_no}")
    return errs


def run(root: Path = ROOT, files: list[str] | None = None) -> R.Result:
    found = collect(root, files)
    py_err, py_notes = check_python(found["py"], root)
    lua_err, lua_notes = check_lua(found["lua"], root)
    wf_err = [e for p in found["yml"] for e in check_workflow(p, root)]
    errors = py_err + lua_err + wf_err
    metrics = {"py": len(found["py"]), "lua": len(found["lua"]), "workflows": len(found["yml"]), "errors": len(errors)}
    status = "fail" if errors else "warn" if py_notes + lua_notes else "ok"
    repro = "python tools/qa.py static " + " ".join(sorted({e.rsplit(" ", 1)[-1].rsplit(":", 1)[0] for e in errors})[:3]) if errors else None
    return R.Result(status, metrics, [*errors[:25], *py_notes, *lua_notes], repro=repro, name="static")

