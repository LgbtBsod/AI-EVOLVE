-- lua_content/items/cursed_relics.lua
-- Предметы постановки боя «Рёмен Сукуна vs Сатору Годжо» (lua_content/bosses.lua):
-- реликвии проклятой энергии для героя (или как дроп с боссов). Схема Effect -> Ops[]
-- (docs/EFFECT_SCHEMA.md); проверка: python -m tools.effect_schema.itemcheck <этот файл>.

local PRED_MT = { __call = function(p, ctx) return p.fn(ctx) end }
local function pred(src, fn) return setmetatable({ src = src, fn = fn }, PRED_MT) end

return {
  items = {
    -- ------------------------------------------------- Палец Сукуны (Король проклятий)
    { id = "sukuna_finger", name = "Палец Рёмена Сукуны", kind = "equipment", slot = "ring",
      rarity = "legendary", value = 600,
      description = "Фрагмент короля проклятий. Вливает проклятую энергию в удары и" ..
                    " открывает цель после «Разрыва»: каждый удар по врагу снимает броню.",
      stats = { attack_damage = 10, spell_power = 12, max_mana = 40, mana_regen = 2 },
      effects = {
        -- пассив: король не знает усталости — скорость атаки и проброневый урон
        { id = "sukuna_finger.blessing", tags = { "cursed", "passive" },
          trigger = { kind = "passive" },
          meta = { name = "Благословение короля",
                   description = "+10% aspd, +15% damage_physical, +10 penetration_flat." },
          ops = {
            { kind = "mod", target = "self", stat = "aspd", op = "add", value = { pct = 10 } },
            { kind = "mod", target = "self", stat = "damage_physical", op = "add", value = { pct = 15 } },
            { kind = "mod", target = "self", stat = "penetration_flat", op = "add", value = { flat = 10 } },
          } },
        -- событийный: каждый удар расщепляет броню цели («Разрыв» режет, добивающий удар косит)
        { id = "sukuna_finger.dismantle_mark", tags = { "cursed", "attack" },
          trigger = { kind = "event", event = "attack_hit" },
          cooldown = { flat = 2 },
          meta = { name = "Метка Разрыва",
                   description = "On hit: -8 defense to the enemy for 4 s (stacks per refresh)." },
          ops = {
            { kind = "mod", target = "enemy", stat = "defense", op = "add", value = { flat = -8 },
              duration = { flat = 4 } },
          } },
        -- жажда плоти: вампиризм растёт от недостающего здоровья (шкала hp_missing_below_40 - поле ctx схемы)
        { id = "sukuna_finger.feast", tags = { "cursed", "lifesteal" },
          trigger = { kind = "condition", when = pred("ctx.hp_pct < 40", function(ctx) return (ctx.hp_pct < 40.0) end) },
          meta = { name = "Пир плоти",
                   description = "Below 40% HP: lifesteal grows by 3 per missing 10% HP." },
          ops = {
            { kind = "mod", target = "self", stat = "lifesteal", op = "add", value = { flat = 0 },
              scale = { every = 10, of = "hp_missing_below_40", factor = 1, value = { flat = 3 } } },
          } },
      } },

    -- ------------------------------------------------- Очки Годжо (Шесть Глаз)
    { id = "gojo_blindfold", name = "Повязка Шести Глаз", kind = "equipment", slot = "trinket",
      rarity = "legendary", value = 600,
      description = "Ткань, сдерживающая Шесть Глаз. Снимешь — мир станет медленнее:" ..
                    " выше точность, обзор и запас проклятой энергии; под угрозой — Безграничность.",
      stats = { spell_power = 15, max_mana = 60, accuracy = 25, vision_range = 10 },
      effects = {
        -- пассив: Шесть Глаз читают технику противника раньше, чем она вышла из кулдауна
        { id = "gojo_blindfold.six_eyes", tags = { "limitless", "passive" },
          trigger = { kind = "passive" },
          meta = { name = "Шесть Глаз",
                   description = "+12% damage_spell-ish via lightning bonus, +8 evasion, faster mana regen." },
          ops = {
            { kind = "mod", target = "self", stat = "damage_lightning", op = "add", value = { pct = 20 } },
            { kind = "mod", target = "self", stat = "evasion", op = "add", value = { flat = 8 } },
            { kind = "mod", target = "self", stat = "mana_regen", op = "add", value = { flat = 4 } },
          } },
        -- условие: когда прижмут — «Бесконечность» режет входящий урон (не iframe на весь бой,
        -- честная страховка: до -40% урона, пока здоровье под 35%)
        { id = "gojo_blindfold.infinity", tags = { "limitless", "defense" },
          trigger = { kind = "condition", when = pred("ctx.hp_pct < 35", function(ctx) return (ctx.hp_pct < 35.0) end) },
          meta = { name = "Бесконечность",
                   description = "Below 35% HP: damage_taken reduced up to 40% (grows as HP falls)." },
          amplify = {
            when = pred("ctx.hp_pct < 15", function(ctx) return (ctx.hp_pct < 15.0) end),
            every = 10, of = "hp_missing_below_35", factor = 2,
          },
          ops = {
            { kind = "mod", target = "self", stat = "damage_taken", op = "add", value = { pct = -20 } },
            { kind = "mod", target = "self", stat = "resist_physical", op = "add", value = { flat = 15 } },
          } },
      } },
  },
}
