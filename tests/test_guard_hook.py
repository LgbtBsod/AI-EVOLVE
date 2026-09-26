"""The tool-call guard (tools/guard_hook.py, tools/file_toc.py, `qa.py guard`, lua_content/guards.lua).

Decision table on synthetic hook payloads (real files in tmp_path, the rules compiled from the real guards.lua): big unranged Read -> deny with the outline,
ranged -> pass, retry -> pass (soft mode), unchanged repeat -> one-line stub, raw log -> digest command, guard off / malformed JSON / internal error ->
pass (fail open); the state file, the compile cache, install/uninstall on a tmp settings.json, the batch nudge from a synthetic transcript, latency.
"""
import copy
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import file_toc as FO  # noqa: E402
import guard_hook as G  # noqa: E402
import qa  # noqa: E402
from qa_plugins import guard as GP  # noqa: E402

NOW = 1_800_000_000.0


@pytest.fixture(scope="module")
def cfg(tmp_path_factory):
    out = tmp_path_factory.mktemp("guards_cfg")
    return G.compile_rules(str(ROOT), str(out))       # the real rules through the real Lua bridge


class Guard:
    """One fake session: files under root, state + log under out, a controllable clock."""

    def __init__(self, tmp_path, cfg):
        self.root, self.out, self.cfg, self.now = tmp_path / "repo", tmp_path / "out", copy.deepcopy(cfg), NOW
        self.root.mkdir()

    def file(self, rel, text="", data=None):
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if data is not None else text.encode("utf-8"))
        return path

    def py(self, rel, functions):
        return self.file(rel, "".join(f"def f{i}(a, b):\n    \"\"\"doc {i}\"\"\"\n    return a + b + {i}\n\n" for i in range(functions)))

    def call(self, tool="Read", agent="", event="PreToolUse", session="s1", **tool_input):
        payload = {"session_id": session, "hook_event_name": event, "tool_name": tool, "tool_input": tool_input, "cwd": str(self.root),
                   "tool_use_id": "toolu_x", **({"agent_id": agent} if agent else {})}
        return self.raw(json.dumps(payload).encode("utf-8"))

    def raw(self, data):
        return G.decide(data, {"cfg": self.cfg, "out": str(self.out), "root": str(self.root), "now": self.now, "env": {}})

    def read(self, path, **kw):
        return self.call("Read", file_path=str(path), **kw)

    def log(self):
        p = self.out / "guards.jsonl"
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.is_file() else []


@pytest.fixture
def g(tmp_path, cfg):
    return Guard(tmp_path, cfg)


# ---------------------------------------------------------------- read guard

def test_big_unranged_read_is_denied_with_the_outline(g):
    big = g.py("src/big.py", 400)                               # 1600 lines
    d = g.read(big)
    assert (d.action, d.rule) == ("deny", "read-big")
    lines = d.message.splitlines()
    assert lines[0].startswith("GUARD read denied: src/big.py = 1600 lines")
    assert any("def f0(a, b)" in ln and "L1-3" in ln for ln in lines)       # outline with line ranges for offset/limit
    assert "offset/limit" in lines[-1] and "repeat the same Read once" in lines[-1]
    assert len(lines) <= 42
    code, out, err = G.render(d)
    assert (code, out) == (2, "") and err == d.message + "\n"


def test_ranged_read_and_small_file_pass(g):
    big, small = g.py("big.py", 400), g.py("small.py", 20)
    assert g.read(big, offset=100, limit=80).action == "allow"
    assert g.read(big, limit=g.cfg["read"]["ranged_max_lines"]).action == "allow"
    assert g.read(big, limit=g.cfg["read"]["ranged_max_lines"] + 1).action == "deny"        # a huge limit is an unranged read
    assert g.read(small).action == "allow"


def test_long_lines_trip_the_byte_limit(g):
    d = g.read(g.file("blob.json", "x" * (g.cfg["read"]["min_bytes"] + 10)))
    assert (d.action, d.rule) == ("deny", "read-big")


def test_retry_within_window_passes_then_expires(g):
    big = g.py("big.py", 400)
    assert g.read(big).action == "deny"
    g.now += 30
    retry = g.read(big)
    assert (retry.action, retry.rule) == ("allow", "read-retry") and retry.chars > 0
    other_range = g.read(big, offset=5)                        # another call is not the retry of the first
    assert other_range.action == "deny"
    g.now += g.cfg["window_s"] + 1
    assert g.read(big, offset=5).action == "deny"              # the window is over: denied again, never deadlocked (next call passes)
    assert g.read(big, offset=5).action == "allow"


def test_unchanged_repeat_gets_a_one_line_stub_edit_resets_it(g):
    mid = g.py("mid.py", 60)                                    # 240 lines, ~4 KB: under the big limit, over the stub minimum
    assert g.read(mid).rule == "read-pass"
    g.now += 120
    d = g.read(mid)
    assert (d.action, d.rule) == ("deny", "read-repeat")
    assert len(d.message.splitlines()) == 1 and "unchanged" in d.message and "2 min" in d.message
    assert g.read(mid).rule == "read-retry"                     # soft mode: the same call again passes
    mid.write_text(mid.read_text(encoding="utf-8") + "def extra():\n    return 1\n", encoding="utf-8")
    assert g.read(mid).action == "allow"                        # edited in between: real content again


def test_repeat_of_a_covered_range_and_isolation_between_contexts(g):
    mid = g.py("mid.py", 60)
    g.read(mid)
    assert g.read(mid, offset=10, limit=200).rule == "read-repeat"            # already held in the context
    assert g.read(mid, agent="agent-a1").action == "allow"                    # a sub-agent has its own context
    assert g.read(mid, session="s2").action == "allow"                        # so has another session
    tiny = g.py("tiny.py", 3)
    g.read(tiny)
    assert g.read(tiny).action == "allow"                                     # cheaper than the stub's extra turn


def test_precompact_forgets_the_reads(g):
    mid = g.py("mid.py", 60)
    g.read(mid)
    assert g.call(event="PreCompact", tool="").rule == "compact-reset"
    assert g.read(mid).rule == "read-pass"                                    # the text is gone from the context: no stub


BINARY = {"png": bytes([137]) + b"PNG" + bytes(50000), "dat": b"ab" + bytes(1) + b"cd" * 20000}


@pytest.mark.parametrize("rel", [".claude/notes/big.md", "memory/MEMORY.md", "CLAUDE.md", "img/shot.png", "data/blob.dat"])
def test_allowlisted_and_binary_files_always_pass(g, rel):
    data = BINARY.get(rel.rsplit(".", 1)[-1])
    path = g.file(rel, "line\n" * 5000) if data is None else g.file(rel, data=data)
    assert g.read(path).action == "allow"


def test_mode_off_log_and_env_switch(g):
    big = g.py("big.py", 400)
    g.cfg["mode"] = "log"
    d = g.read(big)
    assert (d.action, d.rule) == ("allow", "would-read-big")                  # recorded, never blocked
    assert g.log()[-1]["rule"] == "would-read-big"
    g.cfg["mode"] = "off"
    assert g.read(big).action == "allow"
    g.cfg["mode"] = "soft"
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(big)}, "session_id": "s"}).encode()
    off = G.decide(payload, {"cfg": g.cfg, "out": str(g.out), "root": str(g.root), "env": {"AI_EVOLVE_GUARD": "off"}})
    assert off.action == "allow"


# ---------------------------------------------------------------- raw logs

def test_raw_log_denied_with_digest_and_small_sample(g):
    log = g.file("dev_probe_output/run1/state.jsonl", "".join(f'{{"t": {i}, "hp": 10.5}}\n' for i in range(3000)))
    d = g.read(log)
    assert (d.action, d.rule) == ("deny", "read-raw")
    assert "probe_db.py" in d.message and "raw dump" in d.message
    sample = [ln for ln in d.message.splitlines() if ln.startswith("  ") and ("{" in ln or ln.strip() == "...")]
    assert 0 < len(sample) <= 15 and sample[0].strip().startswith('{"t": 0')
    assert g.read(log, limit=50).action == "allow"                              # a ranged look is fine
    assert g.read(g.file("dev_probe_output/run1/summary.md", "x" * 9000)).action == "allow"   # summaries are meant to be read
    assert g.read(g.file("dev_probe_output/run1/tiny.jsonl", '{"a": 1}\n')).action == "allow"
    ci = g.file("dev_probe_output/qa/ci_123.log", "step ok\n" * 2000)
    assert "qa.py ci" in g.read(ci).message


def test_bash_cat_of_a_raw_log_is_denied_other_commands_pass(g):
    log = g.file("game.log", "INFO something happened here\n" * 1000)
    d = g.call("Bash", command=f"cat {log}")
    assert (d.action, d.rule) == ("deny", "bash-raw")
    assert g.call("Bash", command=f'cat "{g.file("notes.txt", "hello")}"').action == "allow"
    assert g.call("Bash", command=f"cat {log} | head -5").action == "allow"      # not a plain cat
    assert g.call("Bash", command="ls -la").action == "allow"
    retry = g.call("Bash", command=f"cat {log}")
    assert (retry.action, retry.rule) == ("allow", "read-retry")                 # soft mode applies to cat as well


# ---------------------------------------------------------------- fail open

@pytest.mark.parametrize("raw", [b"", b"not json", b"[1, 2]", b'{"tool_name": "Read"}', b'{"tool_name": "Read", "tool_input": {"file_path": 5}}',
                                 b'{"tool_name": "Read", "tool_input": {"file_path": "Z:/does/not/exist.py"}}', b"\xff\xfe\x00", b'{"hook_event_name": "Stop"}'])
def test_malformed_input_never_crashes_or_blocks(g, raw):
    assert g.raw(raw).action == "allow"


def test_internal_errors_fail_open(g, monkeypatch):
    big = g.py("big.py", 400)

    def boom(*_a, **_k):
        raise RuntimeError("bug")

    monkeypatch.setattr(G, "read_flow", boom)
    assert g.read(big).action == "allow"
    code, out, err = G.render(g.read(big))
    assert (code, out, err) == (0, "", "")


def test_missing_config_passes_everything(tmp_path):
    payload = json.dumps({"tool_name": "Read", "tool_input": {"file_path": str(tmp_path / "x.py")}, "session_id": "s"}).encode()
    assert G.decide(payload, {"root": str(tmp_path), "out": str(tmp_path / "o"), "env": {}}).action == "allow"     # no lua_content/guards.lua there


def test_hook_process_end_to_end(tmp_path, cfg):
    """The real entry point as Claude Code runs it: stdin JSON -> exit code + stderr; a broken stdin is exit 0."""
    big = tmp_path / "big.py"
    big.write_text("".join(f"def f{i}():\n    return {i}\n\n" for i in range(400)), encoding="utf-8")
    env = {"AI_EVOLVE_GUARD_OUT": str(tmp_path / "out"), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    payload = json.dumps({"session_id": "e2e", "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": str(big)}, "cwd": str(tmp_path)})

    def run(data):
        return subprocess.run([sys.executable, "-S", "-E", str(ROOT / "tools" / "guard_hook.py")], input=data, capture_output=True, env=env, timeout=60, check=False)

    denied = run(payload.encode())
    assert denied.returncode == 2 and b"GUARD read denied" in denied.stderr and denied.stdout == b""
    assert run(payload.encode()).returncode == 0                                # the retry passes
    assert run(b"{{{").returncode == 0


# ---------------------------------------------------------------- state file

def test_state_file_is_keyed_by_owner_path_range_and_pruned(g):
    big = g.py("big.py", 400)
    g.read(big)
    state = json.loads((g.out / "guard_state.json").read_text(encoding="utf-8"))
    (key,) = state["denied"]
    assert key.startswith("s1|") and key.endswith("big.py|1:0") and state["v"] == 1
    assert not list(g.out.glob("*.tmp"))                                          # atomic write leaves nothing behind
    g.cfg["state"]["ttl_s"] = 60
    g.now += 61
    g.read(g.py("other.py", 400))                                                 # any save prunes the expired entries
    state = json.loads((g.out / "guard_state.json").read_text(encoding="utf-8"))
    assert all("big.py" not in k for k in state["denied"]) and any("other.py" in k for k in state["denied"])


def test_state_cap_and_corrupt_state(g):
    g.cfg["state"]["max_entries"] = 3
    for i in range(6):
        g.now += 1
        g.read(g.py(f"m{i}.py", 400))
    state = json.loads((g.out / "guard_state.json").read_text(encoding="utf-8"))
    assert len(state["denied"]) == 3 and any("m5.py" in k for k in state["denied"])
    (g.out / "guard_state.json").write_text("{corrupt", encoding="utf-8")
    assert g.read(g.py("z.py", 400)).action == "deny"                            # unreadable state = empty state, not a crash


def test_every_decision_is_logged_with_avoided_chars(g):
    big = g.py("big.py", 400)
    g.read(big)
    g.read(big)
    g.read(g.py("s.py", 3))
    rows = g.log()
    assert [r["rule"] for r in rows] == ["read-big", "read-retry", "read-pass"]
    assert rows[0]["act"] == "deny" and rows[0]["chars"] > 10000 and rows[0]["path"] == "big.py" and rows[0]["k"] == rows[1]["k"]
    s = GP.summarize(rows)
    assert (s["blocks"], s["allows"], s["forced"]) == (1, 2, 1) and s["avoided_tok"] == 0       # the retry read it anyway: nothing was avoided net
    assert GP.summarize(rows[:1])["avoided_tok"] > 3000


# ---------------------------------------------------------------- compile cache

def test_compile_cache_staleness(tmp_path):
    root, out, calls = tmp_path / "repo", tmp_path / "out", []
    (root / "lua_content").mkdir(parents=True)
    src = root / "lua_content" / "guards.lua"
    src.write_text("return {mode='soft'}", encoding="utf-8")

    def loader(path):
        calls.append(path)
        return {"mode": "soft", "text": Path(path).read_text(encoding="utf-8")}

    first = G.load_cfg(str(root), str(out), loader)
    assert first["mode"] == "soft" and len(calls) == 1
    assert G.load_cfg(str(root), str(out), loader)["_src"] == first["_src"] and len(calls) == 1      # fresh cache: Lua is not touched
    src.write_text("return {mode='log'}", encoding="utf-8")
    second = G.load_cfg(str(root), str(out), loader)
    assert len(calls) == 2 and second["_src"] != first["_src"] and "log" in second["text"]         # edited guards.lua: recompiled

    def broken(_path):
        raise RuntimeError("lua exploded")

    src.write_text("return {mode='off'}", encoding="utf-8")
    assert G.load_cfg(str(root), str(out), broken)["text"] == second["text"]                       # broken Lua: the stale cache still guards
    assert G.load_cfg(str(root), str(tmp_path / "empty"), broken) is None                          # nothing at all: the hook passes


def test_real_lua_compiles_to_the_documented_defaults(cfg):
    assert cfg["mode"] == "soft" and cfg["window_s"] == 600
    assert cfg["read"]["min_lines"] == 250 and cfg["repeat_read"]["enabled"] is True
    assert len(cfg["raw"]["rules"]) >= 5 and cfg["_src"]
    for key in ("read_big", "read_repeat", "read_raw", "batch"):
        assert key in cfg["messages"]


# ---------------------------------------------------------------- batch nudge

def _transcript(path, turns, current_calls=1):
    """turns: list of [(tool name, input)] per assistant turn; the last `current_calls` blocks form the current turn (written before the hook runs)."""
    lines = []
    for i, calls in enumerate(turns):
        for j, (name, inp) in enumerate(calls):
            lines.append({"type": "assistant", "message": {"id": f"msg_{i}", "content": [{"type": "tool_use", "id": f"toolu_{i}_{j}", "name": name, "input": inp}]}})
        lines.append({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": f"toolu_{i}_0", "content": "x" * 300}]}})
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return path


READ = ("Read", {"file_path": "a.py", "limit": 10})


def _nudge_call(g, transcript, tool="Grep", **extra):
    payload = {"session_id": "s1", "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": {"pattern": "x"} if tool == "Grep" else {"file_path": "b.py", "limit": 5},
               "cwd": str(g.root), "transcript_path": str(transcript), "tool_use_id": "toolu_2_0", **extra}
    return g.raw(json.dumps(payload).encode())


def test_batch_nudge_after_two_single_read_only_turns(g, tmp_path):
    t = _transcript(tmp_path / "t.jsonl", [[READ], [("Grep", {"pattern": "y"})], [("Grep", {"pattern": "x"})]])    # the third turn is the current call
    d = _nudge_call(g, t)
    assert (d.action, d.rule) == ("nudge", "batch") and "ONE message" in d.message
    code, out, err = G.render(d)
    body = json.loads(out)
    assert code == 0 and err == "" and body["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "ONE message" in body["hookSpecificOutput"]["additionalContext"] and "permissionDecision" not in body["hookSpecificOutput"]
    assert _nudge_call(g, t).action == "allow"                                                  # cooldown: no nag on the next call
    g.now += g.cfg["batch"]["cooldown_s"] + 1
    assert _nudge_call(g, t).action == "nudge"
    assert g.log()[-1]["rule"] == "batch"


@pytest.mark.parametrize("turns", [
    [[READ], [("Edit", {"file_path": "a.py"})], [("Grep", {})]],                    # a write in between: the run is not read-only
    [[READ, READ], [READ], [("Grep", {})]],                                          # an earlier turn already batched
    [[READ], [("Bash", {"command": "pytest -x"})], [("Grep", {})]],                  # a non read-only Bash
])
def test_no_nudge_when_the_pattern_is_missing(g, tmp_path, turns):
    assert _nudge_call(g, _transcript(tmp_path / "t.jsonl", turns)).action == "allow"


def test_no_nudge_when_the_current_turn_already_batches_or_history_is_short(g, tmp_path):
    t = _transcript(tmp_path / "t.jsonl", [[READ], [READ], [("Grep", {}), ("Glob", {})]])
    assert _nudge_call(g, t).action == "allow"                                              # the current turn holds two calls: already batching
    assert _nudge_call(g, _transcript(tmp_path / "s.jsonl", [[READ]])).action == "allow"    # not enough history
    assert _nudge_call(g, tmp_path / "missing.jsonl").action == "allow"                      # unreadable transcript
    g.cfg["batch"]["enabled"] = False
    assert _nudge_call(g, _transcript(tmp_path / "u.jsonl", [[READ], [READ], [("Grep", {})]])).action == "allow"


def test_nudge_counts_read_only_bash_and_covers_read_calls(g, tmp_path):
    t = _transcript(tmp_path / "t.jsonl", [[("Bash", {"command": "python tools/qa.py ctx tools/x.py"})], [("Bash", {"command": "git status --short"})], [READ]])
    assert _nudge_call(g, t, tool="Read").action == "nudge"                                # a small Read gets the nudge too (and is still allowed)


def test_subagent_transcript_is_found_next_to_the_session_file(g, tmp_path):
    main = tmp_path / "proj" / "sess1.jsonl"
    main.parent.mkdir()
    main.write_text("", encoding="utf-8")
    (tmp_path / "proj" / "sess1" / "subagents").mkdir(parents=True)
    sub = _transcript(tmp_path / "proj" / "sess1" / "subagents" / "agent-abc123.jsonl", [[READ], [READ], [("Grep", {})]])
    d = _nudge_call(g, main, session_id="sess1", agent_id="abc123")
    assert sub.is_file() and d.action == "nudge"
    assert _nudge_call(g, main, session_id="sess1", agent_id="zzz").action == "allow"       # unknown agent file: no guess from the main transcript


# ---------------------------------------------------------------- install / uninstall

def _settings():
    return {"permissions": {"allow": ["Bash(git status)"]}, "hooks": {"PreToolUse": [{"matcher": "Edit", "hooks": [{"type": "command", "command": "echo mine"}]}],
                                                                        "Stop": [{"hooks": [{"type": "command", "command": "echo stop"}]}]}}


def test_install_is_idempotent_and_keeps_foreign_settings():
    once = GP.install(_settings(), "${CLAUDE_PROJECT_DIR}/.venv/Scripts/python.exe")
    assert GP.install(once, "${CLAUDE_PROJECT_DIR}/.venv/Scripts/python.exe") == once
    assert once["permissions"] == _settings()["permissions"] and once["hooks"]["Stop"][0] == _settings()["hooks"]["Stop"][0]
    pre = once["hooks"]["PreToolUse"]
    assert pre[0] == _settings()["hooks"]["PreToolUse"][0] and pre[1]["matcher"] == "Read|Grep|Glob|Bash"
    hook = pre[1]["hooks"][0]
    assert hook == {"type": "command", "command": "${CLAUDE_PROJECT_DIR}/.venv/Scripts/python.exe",
                    "args": ["-S", "-E", "${CLAUDE_PROJECT_DIR}/tools/guard_hook.py"], "timeout": 10}
    assert sorted(GP.installed_events(once)) == sorted(["PreToolUse", "PreCompact", "SessionStart", "Stop", "SubagentStop"])
    assert GP.uninstall(once) == _settings()                                           # only OUR entries went away
    assert GP.uninstall(GP.uninstall(once)) == _settings()


def test_uninstall_removes_our_hook_from_a_shared_group_and_empty_file(tmp_path):
    shared = {"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": "echo mine"}, GP.hook_entry("py")]}]}}
    assert GP.uninstall(shared) == {"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": [{"type": "command", "command": "echo mine"}]}]}}
    path = tmp_path / ".claude" / "settings.json"
    GP.write_settings(path, GP.install({}, "py"))
    assert path.read_bytes().endswith(b"}\n") and b"\r" not in path.read_bytes()
    before = path.read_bytes()
    GP.write_settings(path, GP.install(GP.read_settings(path), "py"))
    assert path.read_bytes() == before                                                 # idempotent on disk, byte for byte
    GP.write_settings(path, GP.uninstall(GP.read_settings(path)))
    assert not path.exists()                                                           # nothing but ours was in it: no empty file left behind


def test_cli_install_uninstall_and_invalid_settings(tmp_path, capsys):
    path = tmp_path / "s.json"
    path.write_text(json.dumps(_settings()), encoding="utf-8")
    assert qa.main(["guard", "--install", "--settings", str(path)]) == 0
    text = capsys.readouterr().out
    assert "mode=soft" in text and "PreToolUse" in text and "AI_EVOLVE_GUARD=off" in text and "--uninstall" in text
    assert "guard_hook.py" in path.read_text(encoding="utf-8")
    assert qa.main(["guard", "--uninstall", "--settings", str(path)]) == 0
    assert json.loads(path.read_text(encoding="utf-8")) == _settings()
    path.write_text("{broken", encoding="utf-8")
    assert qa.main(["guard", "--install", "--settings", str(path)]) == 2
    assert path.read_text(encoding="utf-8") == "{broken"                               # never overwrites what it cannot parse


def test_cli_simulate_and_stats(g, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("AI_EVOLVE_GUARD_OUT", str(g.out))
    big = g.py("big.py", 400)
    sample = tmp_path / "p.json"
    sample.write_text(json.dumps({"session_id": "sim", "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": str(big)}, "cwd": str(g.root)}), encoding="utf-8")
    assert qa.main(["guard", "--simulate", str(sample)]) == 0
    text = capsys.readouterr().out
    assert "action=deny" in text and "rule=read-big" in text and "exit=2" in text and "GUARD read denied" in text
    assert not (g.out / "guards.jsonl").exists()                                       # a simulation writes no log and no state
    g.read(big)
    assert qa.main(["guard", "--stats"]) == 0
    assert "blocks=1" in capsys.readouterr().out


# ---------------------------------------------------------------- outline + glob + latency

def test_outline_tiers_and_other_languages(cfg):
    src = "".join(f"class C{i}:\n    def a(self):\n        pass\n    def b(self):\n        pass\n\n" for i in range(30))
    for limit in (40, 20, 8):
        lines = FO.outline_for("m.py", src, cfg["outline"], limit)
        assert len(lines) <= limit
    assert FO.outline_for("m.py", src, cfg["outline"], 8)[-1].startswith("... +")
    assert "  L2-3 .a()" in FO.outline_for("m.py", src, cfg["outline"], 200)[1]
    lua = "-- tool: x\nlocal function helper()\nend\nreturn {\n  checks = {\n  },\n  tools = {\n  },\n}\n"
    assert [ln.split(" ", 1)[1] for ln in FO.outline_for("a.lua", lua, cfg["outline"], 40)][:3] == [": x", "helper", "checks"]
    assert FO.outline_for("x.rs", "pub fn go() {}\nstruct S;\n", cfg["outline"], 40) == ["L1 fn go", "L2 struct S"]
    assert FO.outline_for("x.weird", "\n".join(f"row {i}" for i in range(100)), cfg["outline"], 40)[0] == "L1 row 0"
    assert FO.outline_for("broken.py", "def (:\n", cfg["outline"], 40) == ["L1 def (:"]          # a syntax error falls back to the first lines


@pytest.mark.parametrize("pattern,path,expected", [
    ("**/state.jsonl", "c:/a/b/state.jsonl", True), ("**/state.jsonl", "state.jsonl", True), ("**/state.jsonl", "c:/a/mystate.jsonl", False),
    ("**/dev_probe_output/**", "c:/r/dev_probe_output/run/x.txt", True), ("**/*.md", "c:/r/docs/a.md", True), ("**/*.md", "c:/r/docs/a.mdx", False),
    ("**/ci_*.log", "c:/r/dev_probe_output/qa/ci_9.log", True), ("**/.claude/**", "c:/u/proj/.claude/projects/x.jsonl", True),
])
def test_glob_matching(pattern, path, expected):
    assert G.glob_match(pattern.lower(), path) is expected


@pytest.mark.parametrize("pattern,path,expected", [
    ("a?c", "abc", True), ("a?c", "a/c", False), ("*.py", "x.py", True), ("*.py", "d/x.py", False), ("**", "any/thing", True), ("a/**/b", "a/b", True),
    ("a/**/b", "a/x/y/b", True), ("", "", True), ("", "x", False), ("**/x", "x", True), ("**/x", "a/b/x", True), ("**/x", "a/bx", False),
])
def test_glob_edge_cases(pattern, path, expected):
    assert G.glob_match(pattern, path) is expected


def test_json_helpers_match_the_json_module():
    """The hook parses/serialises through the C scanner/encoder directly (no `json`/`re` import): same results as json on what it handles."""
    import json as stdjson
    samples = [{"a": [1, 2.5, -3, 1e16, True, False, None, "x\u00e9\u4e2d\U0001f600\"\\\n\t\x01"], "b": {"nested": {"k": []}}}, [], {}, "s", 0, -1.25, [[["deep"]]],
               {"reads": {"s1|c:/a b/\u00fc.py": {"h": "0a1b2c3d:99", "t": 1800000000.5, "r": [[1, 2], [5, 9]]}}}]
    for obj in samples:
        text = G.dumps(obj)
        assert stdjson.loads(text) == obj and G.loads(text) == obj and G.loads(stdjson.dumps(obj)) == obj
    assert G.loads(b"\xef\xbb\xbf  {\"bom\": 1}  trailing") == {"bom": 1}
    assert G.dumps(float("nan")) == "null" and G.dumps(float("inf")) == "null" and G.dumps(True) == "true" and G.dumps(None) == "null"
    for bad in (b"", b"   ", b"{", b"not json", b"\xff\xfe", b'{"a": }'):
        with pytest.raises(ValueError):
            G.loads(bad)


def test_stale_rules_are_recompiled_by_a_child_interpreter(tmp_path):
    """The hook itself runs `python -S` (no lupa/rust_core): a stale guards.json is rebuilt by a child interpreter, real Lua included."""
    out = tmp_path / "out"
    first = G.load_cfg(str(ROOT), str(out))                                     # no cache: the child compiles the real guards.lua
    assert first and first["mode"] == "soft" and (out / "guards.json").is_file()
    cache = json.loads((out / "guards.json").read_text(encoding="utf-8"))
    cache["_src"] = "stale:0"
    cache["marker"] = "old"
    (out / "guards.json").write_text(json.dumps(cache), encoding="utf-8")
    again = G.load_cfg(str(ROOT), str(out))
    assert again["_src"] == first["_src"] and "marker" not in again           # stale checksum: rebuilt from the Lua source


def test_latency_budget_of_the_decision(g):
    """Start-up of the interpreter dominates a hook call (~50 ms on Windows); the decision itself must stay far below it."""
    big, small = g.py("big.py", 400), g.py("small.py", 10)
    g.cfg["mode"] = "log"                                      # log mode: no denied entry, so the same call can be timed repeatedly
    g.read(big)                                                # warm-up (imports ast, compiles the globs)

    def best(fn, n=15):
        times = []
        for _ in range(n):
            t0 = time.perf_counter()
            fn()
            times.append(time.perf_counter() - t0)
        return min(times)

    assert best(lambda: g.read(big)) < 0.15                    # deny path incl. the outline of a 1600-line file (~25 ms alone; loose: 11 shards share the CPU)
    assert best(lambda: g.read(small)) < 0.05                  # pass path (~2 ms alone)
    assert best(lambda: g.raw(b"not json")) < 0.02             # fail-open path


def test_hook_source_stays_light():
    """The hook imports only the standard library, and nothing heavy at module level."""
    src = (ROOT / "tools" / "guard_hook.py").read_text(encoding="utf-8")
    top = [ln for ln in src.splitlines() if ln.startswith(("import ", "from "))]
    assert set(top) == {"from __future__ import annotations", "import os", "import sys", "import time", "import zlib"}


def test_hook_process_does_not_import_json_or_re(tmp_path, cfg):
    """The point of the import diet: neither `json` nor `re` is loaded on the pass path of a Read (they cost ~25 ms of a ~60 ms hook)."""
    small = tmp_path / "s.py"
    small.write_text("x = 1\n", encoding="utf-8")
    payload = json.dumps({"session_id": "imp", "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {"file_path": str(small)}, "cwd": str(tmp_path)})
    env = {"AI_EVOLVE_GUARD_OUT": str(tmp_path / "out"), "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
    G.compile_rules(str(ROOT), str(tmp_path / "out"))                       # compiled up front: no recompile child in this run
    run = subprocess.run([sys.executable, "-S", "-E", "-X", "importtime", str(ROOT / "tools" / "guard_hook.py")], input=payload.encode(), capture_output=True, env=env,
                         timeout=60, check=False)
    imported = {ln.split("|")[-1].strip() for ln in run.stderr.decode(errors="replace").splitlines() if ln.startswith("import time:")}
    assert run.returncode == 0 and {"os", "zlib"} <= imported and not imported & {"json", "re", "collections", "subprocess", "ast"}, sorted(imported)
