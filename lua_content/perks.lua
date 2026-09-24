-- lua_content/perks.lua
-- Перки характеристик: каждые `every` очков характеристики открывают навык
-- (ранг = очки / every). Перки - эффекты схемы Effect -> Ops[], их исполняет тот
-- же менеджер эффектов, что удары и предметы: пассивные (всегда), по условию
-- (since_hit - секунд с последнего полученного урона, since_attack - с удара)
-- и реактивные (на события боя). Сила перка растёт с характеристикой через scale.
-- Перки есть и у врагов: их очки характеристик растут с уровнем.
return {
  perks = {
    -- ---------------------------------------------------------- сила
    { id = "surge_of_might", name = "Прилив силы", attribute = "strength", every = 15,
      effect = { trigger = { kind = "event", event = "crit" }, cooldown = { flat = 6 },
                 ops = { { kind = "mod", target = "self", stat = "strength", op = "add", value = { pct = 15 },
                           duration = { flat = 4 } } } } },
    { id = "armor_breaker", name = "Раскол брони", attribute = "strength", every = 30,
      effect = { trigger = { kind = "event", event = "attack_hit" },
                 ops = { { kind = "mod", target = "enemy", stat = "defense", op = "add", value = { pct = -12 },
                           duration = { flat = 3 } } } } },
    -- ---------------------------------------------------------- ловкость
    { id = "strafe", name = "Стрейф", attribute = "agility", every = 15,
      effect = { trigger = { kind = "event", event = "take_damage", filter = "ctx.since_hit > 0.5" }, cooldown = { flat = 8 },
                 ops = { { kind = "move", target = "self", mode = "strafe", distance = 3 },
                         { kind = "mod", target = "self", stat = "dodge", op = "add", value = { flat = 30 },
                           duration = { flat = 1.5 } } } } },
    { id = "double_strike", name = "Второй удар", attribute = "agility", every = 30,
      effect = { trigger = { kind = "event", event = "attack_hit" }, cooldown = { flat = 5 },
                 ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { pct = 50, of = "attack_damage" },
                           scale = { every = 30, of = "agility", value = { pct = 10, of = "attack_damage" } } } } } },
    -- ---------------------------------------------------------- живучесть
    { id = "fortitude", name = "Стойкость", attribute = "vitality", every = 15,
      effect = { trigger = { kind = "condition", when = "ctx.hp_pct < 30" },
                 ops = { { kind = "mod", target = "self", stat = "defense", op = "add", value = { pct = 25 } } } } },
    { id = "troll_blood", name = "Кровь тролля", attribute = "vitality", every = 30,
      effect = { trigger = { kind = "condition", when = "ctx.since_hit > 4" },
                 ops = { { kind = "mod", target = "self", stat = "hp_regen", op = "add", value = { pct = 1, of = "max_hp" },
                           scale = { every = 30, of = "vitality", value = { pct = 0.5, of = "max_hp" } } } } } },
    -- ---------------------------------------------------------- выносливость
    { id = "light_feet", name = "Лёгкий шаг", attribute = "endurance", every = 15,
      effect = { trigger = { kind = "condition", when = "ctx.since_hit > 3" },
                 ops = { { kind = "mod", target = "self", stat = "move_speed", op = "add", value = { pct = 25 } } } } },
    { id = "grit", name = "Выдержка", attribute = "endurance", every = 30,
      effect = { trigger = { kind = "event", event = "take_damage", filter = "ctx.hp_pct < 50" }, cooldown = { flat = 15 },
                 ops = { { kind = "heal", target = "self", stat = "hp", op = "add", value = { pct = 8, of = "max_hp" } } } } },
    -- ---------------------------------------------------------- интеллект и мудрость
    { id = "spark", name = "Искра", attribute = "intelligence", every = 15,
      effect = { trigger = { kind = "event", event = "cast" },
                 ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { pct = 30, of = "spell_power" } } } } },
    { id = "clarity", name = "Ясность", attribute = "wisdom", every = 15,
      effect = { trigger = { kind = "condition", when = "ctx.mana < ctx.max_mana * 0.3" },
                 ops = { { kind = "mod", target = "self", stat = "mana_regen", op = "add", value = { pct = 100 } } } } },
    -- ---------------------------------------------------------- удача
    { id = "lucky_break", name = "Удачный случай", attribute = "luck", every = 15,
      effect = { trigger = { kind = "event", event = "kill" }, cooldown = { flat = 4 },
                 ops = { { kind = "heal", target = "self", stat = "hp", op = "add", value = { pct = 5, of = "max_hp" } },
                         { kind = "mod", target = "self", stat = "crit_chance", op = "add", value = { flat = 10 },
                           duration = { flat = 4 } } } } },
    { id = "battle_trance", name = "Боевой транс", attribute = "strength", every = 45,
      effect = { trigger = { kind = "condition", when = "ctx.since_attack < 2 and ctx.since_hit > 2" },
                 ops = { { kind = "mod", target = "self", stat = "aspd", op = "add", value = { pct = 20 } } } } },
  },
}
