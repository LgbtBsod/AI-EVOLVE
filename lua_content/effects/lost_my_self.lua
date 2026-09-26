-- lua_content/effects/lost_my_self.lua — ПОЛНАЯ регистрация берсерка через реестры
-- (B.10 справочника): resources + stats + statuses + effects. Ни одной правки ядра:
-- движок резолвит имена по registry.lua / schemas/*, ops исполняет src/effects/ops.py.
-- Игровая версия предмета (с преcomputed-полем) — items/sorrow_of_berserk.lua;
-- здесь демонстрация «чистого» регистрационного пути для мода.
--
-- Порядок записей = load_order registry.lua: сначала то, от чего зависят.
return {
  -- 1. Ресурсы ---------------------------------------------------------------
  resources = {
    { id = "rage", max_stat = "max_rage", min = 0, decay = 2, visible = true,
      tags = { "combat" } },
  },

  -- 2. Статы (схема schemas/stats.lua: scope+type обязательны) ----------------
  stats = {
    { id = "hp_missing_below_40", scope = "self", type = "number",
      min = 0, max = 40, computed = true, visible = false,
      compute_expr = "max(0, 40 - ctx.hp_pct)",   -- выражение вместо функции (сериализуемо)
      tags = { "derived", "berserk" } },
  },

  -- 3. Статус Last Will (схема schemas/statuses.lua) ---------------------------
  statuses = {
    { id = "last_will", duration = "required", purgeable = false, stacking = "refresh",
      ops = {
        { kind = "immune", target = "self", damage_type = "all", value = { pct = 100 } },
        { kind = "untargetable", target = "self" },
      },
      on_kill = { { kind = "extend", buff_id = "last_will", flat = 5 } },  -- продление по событию
      cooldown = { flat = 30 },
      tags = { "shield", "berserk" } },
  },

  -- 4. Эффекты (схема schemas/effects.lua; поля — schema.lua) -------------------
  effects = {
    { id = "lost_my_self", layer = "effect", tags = { "berserk", "passive" },
      trigger = { kind = "condition", when = "ctx.hp_pct < 40" },
      ops = {
        { kind = "mod", target = "self", stat = "strength", op = "add", value = { pct = 20 } },
        { kind = "mod", target = "self", stat = "crit_chance", op = "add", value = { flat = 5 },
          scale = { every = 10, of = "hp_missing_below_40", value = { flat = 5 } } },
        { kind = "drain", target = "self", stat = "hp", op = "sub",
          value = { pct = 0.5, of = "max_hp" },
          scale = { every = 10, of = "hp_missing_below_40", value = { pct = 0.5, of = "max_hp" } },
          fail = {  -- цена больше текущего HP: hp -> 1 и Last Will (x2 за каждые 10% нехватки)
            { kind = "set", target = "self", stat = "hp", op = "set", value = { flat = 1 } },
            { kind = "buff", target = "self", buff_id = "last_will", flags = { "iframe" },
              duration = { flat = 5, scale = { every = 10, of = "hp_missing_below_40", factor = 2 } },
              cooldown = { flat = 30 }, extend = { on = "kill", flat = 5 } },
        } },
      } },
    -- событие Timeline («attack») ловит триггер event; owner_has проверяет активный пассив
    { id = "lost_my_self.attack", layer = "effect", tags = { "berserk" },
      trigger = { kind = "event", event = "attack", owner_has = "lost_my_self" },
      ops = {
        { kind = "deal", target = "enemy", stat = "hp", op = "sub",
          value = { pct = 1.5, of = "max_hp" },
          scale = { every = 10, of = "hp_missing_below_40", value = { pct = 1.5, of = "max_hp" } } },
      } },
  },

  -- 5. Слушатель (B.8): подписку Registry.on_register("effects","lost_my_self")
  --    оформляет ядро по этой декларации (UI добавит иконку в HUD при регистрации).
  listeners = {
    { on = "register", namespace = "effects", id = "lost_my_self",
      ["do"] = "hud.add_icon" },   -- `do` is a Lua keyword: a bare `do = ...` key is a syntax error
  },
}
