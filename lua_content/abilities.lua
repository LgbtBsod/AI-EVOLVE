-- lua_content/abilities.lua
-- Способности: удар оружием, навыки героя и врагов. Это эффекты схемы
-- Effect -> Ops[] (docs/EFFECT_SCHEMA.md) плюс поля способности:
--   range     - дальность (для способностей с целью): число, стат ("attack_range" - дальность
--               оружия: лук бьёт издалека) или value ({ pct = 110, of = "attack_range" }),
--   cooldown  - секунды или "attack" (1 / скорость атаки - удар оружием),
--   cost      - { mana = 10 } / { stamina = 20 } / { hp = 5 },
--   when      - условие применения (ИИ не тратит лечение на полном HP),
--   needs_target - нужна живая цель в range (по умолчанию - если операции бьют enemy),
--   tags      - attack (лайфстил, attack_hit, события оружия), spell, skill, heal,
--   cast_time - задержка с кругом на земле (навыки боссов), radius - для area.
-- area бьёт ВСЕХ в круге, и своих, и самого заклинателя (френдли фаер); affects =
-- "others" | "enemies" | "allies" сужает круг. ИИ сам решает, стоит ли бить по кругу.
-- Всё исполняет один менеджер эффектов (src/effects/manager.py): удар оружием -
-- та же способность, что навык, просто с уроном = ctx.attack_damage.

local function hit(pct)  -- урон в % от урона оружия
  return { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { pct = pct, of = "attack_damage" } }
end

return {
  abilities = {
    -- ------------------------------------------------------------ общее
    { id = "weapon_attack", name = "Удар оружием", tags = { "attack", "weapon" }, range = "attack_range", cooldown = "attack",
      ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { ref = "ctx.attack_damage" } } } },

    -- ------------------------------------------------------------ воин
    { id = "power_strike", name = "Мощный удар", tags = { "attack", "skill" }, range = { pct = 110, of = "attack_range" },
      cooldown = 6,
      cost = { stamina = 20 }, ops = { hit(180) } },
    { id = "cleave", name = "Рассекающий удар", tags = { "attack", "skill" }, range = 2.5, cooldown = 8,
      cost = { stamina = 25 }, needs_target = true,
      ops = { { kind = "deal", target = "area", center = "self", radius = 3.5, affects = "others", stat = "hp",
                op = "sub", value = { pct = 90, of = "attack_damage" } } } },
    { id = "second_wind", name = "Второе дыхание", tags = { "heal", "skill" }, cooldown = 12,
      cost = { stamina = 25 }, when = "ctx.hp_pct < 40",
      ops = { { kind = "heal", target = "self", stat = "hp", op = "add", value = { pct = 18, of = "max_hp" } } } },

    -- ------------------------------------------------------------ маг
    { id = "magic_bolt", name = "Магическая стрела", tags = { "attack", "spell" }, range = 7.0, cooldown = 1.2,
      cost = { mana = 10 },
      ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { ref = "ctx.spell_power" } } } },
    { id = "fireball", name = "Огненный шар", tags = { "spell" }, range = 8.0, cooldown = 7, cost = { mana = 25 },
      ops = { { kind = "deal", target = "area", radius = 3.0, stat = "hp", op = "sub", value = { pct = 120, of = "spell_power" } },
              { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { pct = 15, of = "spell_power" },
                every = 1, duration = { flat = 3 }, flags = { "true_damage" } } } },
    { id = "self_heal", name = "Исцеление", tags = { "heal", "spell" }, cooldown = 4, cost = { mana = 15 },
      when = "ctx.hp_pct < 45",
      ops = { { kind = "heal", target = "self", stat = "hp", op = "add", value = { flat = 20 } } } },

    -- ------------------------------------------------------------ разбойник
    { id = "stealth_strike", name = "Удар из тени", tags = { "attack", "skill" }, range = "attack_range", cooldown = 4,
      cost = { stamina = 20 },
      ops = { hit(150),
              { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { flat = 4 },
                every = 1, duration = { flat = 5 }, flags = { "true_damage" } } } },
    -- стелс: большой круг вокруг себя, в нём все видят заклинателя на 75% хуже
    -- (обзор В СТОРОНУ заклинателя, toward = "source"); свои в круге тоже теряют его из виду
    { id = "shadow_veil", name = "Покров тени", tags = { "skill", "stealth" }, cooldown = 18,
      cost = { stamina = 20 }, when = "ctx.hp_pct < 60",
      ops = { { kind = "mod", target = "area", center = "self", radius = 14, affects = "others",
                stat = "vision_range", op = "add", value = { pct = -75 }, toward = "source",
                duration = { flat = 6 } } } },

    -- ------------------------------------------------------------ враги
    { id = "crushing_blow", name = "Сокрушающий удар", tags = { "attack", "skill" }, range = { pct = 110, of = "attack_range" },
      cooldown = 5,
      ops = { hit(130),
              { kind = "mod", target = "enemy", stat = "move_speed", op = "add", value = { pct = -40 },
                duration = { flat = 3 } } } },
    { id = "venom_spit", name = "Ядовитый плевок", tags = { "attack", "skill" }, range = 6.0, cooldown = 6,
      ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { pct = 25, of = "attack_damage" },
                every = 1, duration = { flat = 4 }, flags = { "true_damage" } } } },
    { id = "war_cry", name = "Боевой клич", tags = { "skill" }, cooldown = 15, needs_target = true, range = 8.0,
      ops = { { kind = "mod", target = "self", stat = "attack_damage", op = "add", value = { pct = 30 },
                duration = { flat = 6 } } } },
  },
}
