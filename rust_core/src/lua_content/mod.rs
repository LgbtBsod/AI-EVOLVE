// rust_core/src/lua_content/mod.rs
//! L10: Lua content bridge for tools/lua_bridge.py.
//!
//! Content (items, tool settings) is Lua 5.5. Instead of walking Lua tables
//! from Python key by key (one language crossing per key) or parsing the
//! text, the file is executed here in a sandbox and its data leaves as ONE
//! JSON string (mlua's serde support), which Python reads with json.loads.
//!
//! Sandbox: math/string/table/utf8 plus the base library without file and
//! code loading (dofile, loadfile, load, require), print silenced, a memory
//! limit and an instruction budget, so a broken or hostile file cannot hang
//! the tools.
//!
//! The export rules (pred objects -> their source string, functions dropped)
//! live in export.lua, shared with the Python (lupa) fallback.

use std::cell::Cell;
use std::rc::Rc;

use mlua::{Function, HookTriggers, Lua, LuaOptions, LuaSerdeExt, StdLib, Table, Value, VmState};

/// Lua helpers shared with tools/lua_bridge.py (same file on both sides).
pub const EXPORT_LUA: &str = include_str!("export.lua");

const HOOK_STEP: u32 = 10_000;

#[derive(Clone, Copy, Debug)]
pub struct Limits {
    pub memory_bytes: usize,
    pub instructions: u64,
}

impl Default for Limits {
    fn default() -> Self {
        // A generated stress item with tens of thousands of effects fits well within these.
        Self { memory_bytes: 1 << 30, instructions: 2_000_000_000 }
    }
}

fn sandbox(limits: Limits) -> mlua::Result<Lua> {
    let lua = Lua::new_with(
        StdLib::MATH | StdLib::STRING | StdLib::TABLE | StdLib::UTF8,
        LuaOptions::default(),
    )?;
    let globals = lua.globals();
    for name in ["dofile", "loadfile", "load", "require"] {
        globals.raw_set(name, Value::Nil)?;
    }
    // content files are data: their print() output would only be noise in tool reports
    globals.raw_set("print", lua.create_function(|_, _: mlua::MultiValue| Ok(()))?)?;
    lua.set_memory_limit(limits.memory_bytes)?;
    let used = Rc::new(Cell::new(0u64));
    let budget = limits.instructions;
    lua.set_hook(HookTriggers::new().every_nth_instruction(HOOK_STEP), move |_, _| {
        used.set(used.get() + HOOK_STEP as u64);
        if used.get() > budget {
            Err(mlua::Error::runtime("instruction budget exceeded"))
        } else {
            Ok(VmState::Continue)
        }
    })?;
    Ok(lua)
}

fn helpers(lua: &Lua) -> mlua::Result<Table> {
    lua.load(EXPORT_LUA).set_name("=export.lua").eval()
}

/// Run `source`; the root value is what the chunk returns, or, when `globals`
/// is given and any of them is set, a table of those globals.
fn run(lua: &Lua, source: &str, chunk_name: &str, globals: &[String]) -> mlua::Result<Value> {
    let returned: Value = lua.load(source).set_name(format!("={chunk_name}")).eval()?;
    if globals.is_empty() {
        return Ok(returned);
    }
    let picked = lua.create_table()?;
    let mut any = false;
    for name in globals {
        let v: Value = lua.globals().get(name.as_str())?;
        if !v.is_nil() {
            picked.set(name.as_str(), v)?;
            any = true;
        }
    }
    Ok(if any { Value::Table(picked) } else { returned })
}

fn to_json(value: &Value) -> Result<String, String> {
    serde_json::to_string(&value.to_serializable().deny_unsupported_types(false)).map_err(|e| e.to_string())
}

/// Execute a content file and return its data as JSON.
pub fn export_json(source: &str, chunk_name: &str, globals: &[String], limits: Limits) -> Result<String, String> {
    let lua = sandbox(limits).map_err(|e| e.to_string())?;
    let root = run(&lua, source, chunk_name, globals).map_err(|e| e.to_string())?;
    let export: Function = helpers(&lua).and_then(|h| h.get("export")).map_err(|e| e.to_string())?;
    let plain: Value = export.call(root).map_err(|e| e.to_string())?;
    to_json(&plain)
}

/// Evaluate every pred() condition of a content file on each context.
/// `ctxs_json` is a JSON array of objects; the result is a JSON array with one
/// object per context: {condition source: result or "error: ..."}.
pub fn eval_preds_json(source: &str, chunk_name: &str, ctxs_json: &str, limits: Limits) -> Result<String, String> {
    let ctxs: serde_json::Value = serde_json::from_str(ctxs_json).map_err(|e| e.to_string())?;
    if !ctxs.is_array() {
        return Err("ctxs must be a JSON array".into());
    }
    let lua = sandbox(limits).map_err(|e| e.to_string())?;
    let root = run(&lua, source, chunk_name, &[]).map_err(|e| e.to_string())?;
    let preds: Function = helpers(&lua).and_then(|h| h.get("preds")).map_err(|e| e.to_string())?;
    let ctxs = lua.to_value(&ctxs).map_err(|e| e.to_string())?;
    let rows: Value = preds.call((root, ctxs)).map_err(|e| e.to_string())?;
    to_json(&rows)
}

#[cfg(test)]
mod tests {
    use super::*;

    const ITEM: &str = r#"
local PRED_MT = { __call = function(p, ctx) return p.fn(ctx) end }
local function pred(src, fn) return setmetatable({ src = src, fn = fn }, PRED_MT) end
return {
  name = "Test",
  effects = {
    { id = "a", trigger = { kind = "condition", when = pred("ctx.hp_pct < 40", function(ctx) return (ctx.hp_pct < 40) end) },
      ops = { { kind = "mod", value = { flat = 5 } } } },
  },
}
"#;

    fn parse(json: &str) -> serde_json::Value {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn export_replaces_preds_with_source() {
        let data = parse(&export_json(ITEM, "item", &[], Limits::default()).unwrap());
        assert_eq!(data["name"], "Test");
        assert_eq!(data["effects"][0]["trigger"]["when"], "ctx.hp_pct < 40");
        assert_eq!(data["effects"][0]["ops"][0]["value"]["flat"], 5);
    }

    #[test]
    fn export_drops_plain_functions() {
        let data = parse(&export_json("return { a = 1, f = function() end }", "t", &[], Limits::default()).unwrap());
        assert_eq!(data, serde_json::json!({"a": 1}));
    }

    #[test]
    fn globals_mode_picks_declared_tables() {
        let src = "mannequins = { dummy = { hp = 10 } }\nlocal x = 1";
        let data = parse(&export_json(src, "t", &["mannequins".into(), "scenarios".into()], Limits::default()).unwrap());
        assert_eq!(data["mannequins"]["dummy"]["hp"], 10);
        assert!(data.get("scenarios").is_none());
    }

    #[test]
    fn sandbox_has_no_file_or_code_loading() {
        for src in ["return io.open('x')", "return os.time()", "return dofile('x')", "return load('return 1')()"] {
            assert!(export_json(src, "t", &[], Limits::default()).is_err(), "{src} must fail");
        }
        assert!(export_json("return math.max(1, 2) + #string.rep('a', 3)", "t", &[], Limits::default()).is_ok());
    }

    #[test]
    fn instruction_budget_stops_infinite_loops() {
        let limits = Limits { instructions: 1_000_000, ..Limits::default() };
        let err = export_json("while true do end", "t", &[], limits).unwrap_err();
        assert!(err.contains("instruction budget"), "{err}");
    }

    #[test]
    fn recursive_table_is_an_error() {
        assert!(export_json("local t = {}; t.me = t; return t", "t", &[], Limits::default()).is_err());
    }

    #[test]
    fn eval_preds_on_each_context() {
        let rows = parse(&eval_preds_json(ITEM, "item", r#"[{"hp_pct": 30}, {"hp_pct": 50}, {}]"#, Limits::default()).unwrap());
        assert_eq!(rows[0]["ctx.hp_pct < 40"], true);
        assert_eq!(rows[1]["ctx.hp_pct < 40"], false);
        assert!(rows[2]["ctx.hp_pct < 40"].as_str().unwrap().starts_with("error:"));
    }
}
