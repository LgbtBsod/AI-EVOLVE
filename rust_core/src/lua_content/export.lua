-- Экспорт Lua-контента в чистые данные. Один и тот же код исполняют оба
-- бэкенда: rust_core (mlua, include_str!) и Python-фолбэк (lupa,
-- tools/lua_bridge.py читает этот файл).
--
-- Условие pred("src", fn) -> строка src (функции наружу не отдаются);
-- прочие функции/userdata/потоки -> nil; цикл в таблицах -> ошибка.
-- Возвращает таблицу { export = f(value), preds = f(value, ctxs) }.

local function is_pred(v)
  local mt = getmetatable(v)
  return type(mt) == "table" and mt.__call ~= nil
     and type(rawget(v, "src")) == "string" and type(rawget(v, "fn")) == "function"
end

local function export(v, seen)
  local t = type(v)
  if t == "function" or t == "userdata" or t == "thread" then return nil end
  if t ~= "table" then return v end
  if is_pred(v) then return v.src end
  seen = seen or {}
  if seen[v] then error("recursive table in content") end
  seen[v] = true
  local out = {}
  for k, x in pairs(v) do
    out[k] = export(x, seen)
  end
  seen[v] = nil
  return out
end

local function collect(v, found, seen)
  if type(v) ~= "table" then return end
  if is_pred(v) then
    found[v.src] = v
    return
  end
  if seen[v] then return end
  seen[v] = true
  for _, x in pairs(v) do collect(x, found, seen) end
end

-- Все условия контента на каждом ctx: { [i] = { [src] = результат | "error: ..." } }
local function preds(v, ctxs)
  local found = {}
  collect(v, found, {})
  local results = {}
  for i, ctx in ipairs(ctxs) do
    local row = {}
    for src, p in pairs(found) do
      local ok, res = pcall(p.fn, ctx)
      if ok then row[src] = res else row[src] = "error: " .. tostring(res) end
    end
    results[i] = row
  end
  return results
end

return { export = export, preds = preds }
