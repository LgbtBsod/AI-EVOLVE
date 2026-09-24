-- lua_content/items/game_items.lua
-- Предметы игры. Поля предмета:
--   id, name (ru), kind = equipment | consumable | map | artifact,
--   slot (weapon/armor/amulet/ring/trinket - для equipment и artifact),
--   attack - оружие: способность удара (abilities.lua): sword_swing / axe_swing - дугой,
--            spear_thrust / bow_shot - в одну цель, staff_blast - по площади; нет - weapon_attack,
--   rarity = common | rare | epic | legendary, value (золото у торговца),
--   stats  - плоские статы, пока предмет надет (имена статов схемы эффектов),
--   effects - эффекты по схеме Effect -> Ops[] (docs/EFFECT_SCHEMA.md),
--   knowledge - что предмет открывает герою (карты, артефакты):
--     { reveals = "exit" | "exit_region" | "exit_direction" | "chests" | "merchants" }
-- Условия - строки на языке схемы (их считает src/effects/runtime.py).

local function heal_pct(id, pct)
  return { id = id, trigger = { kind = "event", event = "use" },
           ops = { { kind = "heal", target = "self", stat = "hp", op = "add", value = { pct = pct, of = "max_hp" } } } }
end

return {
  items = {
    -- ------------------------------------------------------------ оружие
    { id = "rusty_sword", name = "Ржавый меч", kind = "equipment", slot = "weapon", rarity = "common", value = 10,
      attack = "sword_swing", stats = { attack_damage = 4 } },
    { id = "iron_sword", name = "Железный меч", kind = "equipment", slot = "weapon", rarity = "common", value = 30,
      attack = "sword_swing", stats = { attack_damage = 8 } },
    { id = "vampire_fang", name = "Клык вампира", kind = "equipment", slot = "weapon", rarity = "rare", value = 90,
      stats = { attack_damage = 6 },
      effects = {
        { id = "vampire_fang.drink", trigger = { kind = "event", event = "attack_hit" },
          ops = { { kind = "heal", target = "self", stat = "hp", op = "add", value = { pct = 12, of = "last_damage" } } } },
      } },
    { id = "executioner_axe", name = "Топор палача", kind = "equipment", slot = "weapon", rarity = "epic", value = 160,
      attack = "axe_swing", stats = { attack_damage = 12, aspd = -0.1 },
      effects = {
        { id = "executioner_axe.judgement", trigger = { kind = "event", event = "attack" },
          ops = { { kind = "kill", target = "enemy", when = "ctx.enemy_hp_pct < 12" } } },
      } },
    { id = "venom_dagger", name = "Ядовитый кинжал", kind = "equipment", slot = "weapon", rarity = "rare", value = 80,
      stats = { attack_damage = 5, aspd = 0.2 },
      effects = {
        { id = "venom_dagger.bite", trigger = { kind = "event", event = "attack_hit" },
          ops = { { kind = "apply_effect", target = "enemy", buff_id = "venom_dagger.poison" } } },
        { id = "venom_dagger.poison", trigger = { kind = "applied" },
          ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { pct = 2, of = "enemy_max_hp" },
                    flags = { "true_damage" } },
                  { kind = "mod", target = "enemy", stat = "defense", op = "sub", value = { flat = 2 } } } },
      } },
    -- дальность атаки: лук бьёт издалека, копьё - дальше меча
    { id = "hunting_bow", name = "Охотничий лук", kind = "equipment", slot = "weapon", rarity = "common", value = 35,
      attack = "bow_shot", stats = { attack_damage = 6, attack_range = 7, aspd = -0.1 } },
    { id = "ash_spear", name = "Ясеневое копьё", kind = "equipment", slot = "weapon", rarity = "common", value = 30,
      attack = "spear_thrust", stats = { attack_damage = 7, attack_range = 1.5 } },
    { id = "woodcutter_axe", name = "Топор лесоруба", kind = "equipment", slot = "weapon", rarity = "common", value = 25,
      attack = "axe_swing", stats = { attack_damage = 9, aspd = -0.15 } },
    { id = "apprentice_staff", name = "Посох ученика", kind = "equipment", slot = "weapon", rarity = "common", value = 30,
      attack = "staff_blast", stats = { spell_power = 10, attack_range = 5, intelligence = 3 } },
    { id = "worn_dagger", name = "Старый кинжал", kind = "equipment", slot = "weapon", rarity = "common", value = 12,
      stats = { attack_damage = 3, aspd = 0.3, crit_chance = 5 } },
    { id = "stormcaller", name = "Зов бури", kind = "equipment", slot = "weapon", rarity = "epic", value = 150,
      attack = "sword_swing", stats = { attack_damage = 9, agility = 6 },
      effects = {
        { id = "stormcaller.crit", trigger = { kind = "event", event = "crit" },
          ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { flat = 18 }, flags = { "true_damage" } } } },
      } },

    -- ------------------------------------------------------------ броня
    { id = "leather_armor", name = "Кожаная броня", kind = "equipment", slot = "armor", rarity = "common", value = 25,
      stats = { defense = 3, max_hp = 20 } },
    { id = "chainmail", name = "Кольчуга", kind = "equipment", slot = "armor", rarity = "rare", value = 70,
      stats = { defense = 6, max_hp = 40, move_speed = -0.5 } },
    { id = "mantle_of_thorns", name = "Мантия шипов", kind = "equipment", slot = "armor", rarity = "epic", value = 140,
      stats = { defense = 5, max_hp = 30 },
      effects = {
        { id = "mantle_of_thorns.retaliate", trigger = { kind = "event", event = "take_damage" },
          ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = { pct = 25, of = "last_damage" },
                    flags = { "no_crit" } } } },
      } },

    -- ------------------------------------------------------------ амулеты и кольца
    { id = "amulet_of_vigor", name = "Амулет бодрости", kind = "equipment", slot = "amulet", rarity = "common", value = 40,
      stats = { vitality = 6, hp_regen = 0.5 } },
    { id = "ring_of_precision", name = "Кольцо точности", kind = "equipment", slot = "ring", rarity = "rare", value = 60,
      stats = { crit_chance = 8, crit_dmg = 20 } },
    { id = "ring_of_haste", name = "Кольцо спешки", kind = "equipment", slot = "ring", rarity = "rare", value = 60,
      stats = { aspd = 0.25, move_speed = 1.0 } },
    { id = "second_wind_band", name = "Браслет второго дыхания", kind = "equipment", slot = "ring", rarity = "epic", value = 120,
      stats = { endurance = 5 },
      effects = {
        { id = "second_wind_band.surge", cooldown = { flat = 20 },
          trigger = { kind = "event", event = "take_damage", filter = "ctx.hp_pct < 35 and ctx.stamina >= 30" },
          ops = { { kind = "drain", target = "self", stat = "stamina", op = "sub", value = { flat = 30 } },
                  { kind = "heal", target = "self", stat = "hp", op = "add", value = { pct = 20, of = "max_hp" } },
                  { kind = "buff", target = "self", buff_id = "second_wind", flags = { "iframe" }, duration = { flat = 1.5 } } } },
      } },

    -- ------------------------------------------------------------ артефакты (знания о мире)
    { id = "echo_compass", name = "Компас эха", kind = "artifact", slot = "trinket", rarity = "epic", value = 200,
      knowledge = { reveals = "exit_direction" },
      stats = { move_speed = 0.5 } },
    { id = "seers_eye", name = "Око провидца", kind = "artifact", slot = "trinket", rarity = "rare", value = 120,
      knowledge = { reveals = "chests" },
      stats = { luck = 5 } },
    { id = "phoenix_feather", name = "Перо феникса", kind = "artifact", slot = "trinket", rarity = "legendary", value = 300,
      effects = {
        { id = "phoenix_feather.rebirth", cooldown = { flat = 120 }, trigger = { kind = "event", event = "die" },
          ops = { { kind = "set", target = "self", stat = "hp", op = "set", value = { pct = 30, of = "max_hp" } },
                  { kind = "buff", target = "self", buff_id = "rebirth", flags = { "iframe" }, duration = { flat = 3 } } } },
      } },

    -- ------------------------------------------------------------ расходники
    { id = "health_potion", name = "Зелье лечения", kind = "consumable", rarity = "common", value = 15,
      effects = { heal_pct("health_potion.drink", 35) } },
    { id = "greater_health_potion", name = "Большое зелье лечения", kind = "consumable", rarity = "rare", value = 40,
      effects = { heal_pct("greater_health_potion.drink", 70) } },
    { id = "mana_potion", name = "Зелье маны", kind = "consumable", rarity = "common", value = 15,
      effects = { { id = "mana_potion.drink", trigger = { kind = "event", event = "use" },
                    ops = { { kind = "heal", target = "self", stat = "mana", op = "add", value = { pct = 50, of = "max_mana" } } } } } },
    { id = "stamina_tonic", name = "Тоник выносливости", kind = "consumable", rarity = "common", value = 12,
      effects = { { id = "stamina_tonic.drink", trigger = { kind = "event", event = "use" },
                    ops = { { kind = "heal", target = "self", stat = "stamina", op = "add", value = { pct = 60, of = "max_stamina" } } } } } },
    { id = "rage_tonic", name = "Тоник ярости", kind = "consumable", rarity = "rare", value = 35,
      effects = { { id = "rage_tonic.drink", trigger = { kind = "event", event = "use" },
                    ops = { { kind = "buff", target = "self", buff_id = "enraged", duration = { flat = 10 } },
                            { kind = "drain", target = "self", stat = "hp", op = "sub", value = { pct = 10 },
                              fail = { { kind = "set", target = "self", stat = "hp", op = "set", value = { flat = 1 } } } } } },
                  { id = "rage_tonic.fury", trigger = { kind = "condition", when = "ctx.buff_enraged > 0" },
                    ops = { { kind = "mod", target = "self", stat = "attack_damage", op = "add", value = { flat = 8 } },
                            { kind = "mod", target = "self", stat = "aspd", op = "add", value = { flat = 0.2 } } } } } },

    -- ------------------------------------------------------------ карты
    { id = "exit_map", name = "Карта выхода", kind = "map", rarity = "rare", value = 60,
      knowledge = { reveals = "exit" } },
    { id = "torn_map", name = "Обрывок карты", kind = "map", rarity = "common", value = 20,
      knowledge = { reveals = "exit_region" } },
    { id = "treasure_map", name = "Карта сокровищ", kind = "map", rarity = "common", value = 25,
      knowledge = { reveals = "chests" } },

    -- ------------------------------------------------------------ стелс
    { id = "smoke_bomb", name = "Дымовая шашка", kind = "consumable", rarity = "rare", value = 30,
      effects = { { id = "smoke_bomb.cloud", trigger = { kind = "event", event = "use" },
                    ops = { { kind = "mod", target = "area", center = "self", radius = 10, affects = "others",
                              stat = "vision_range", op = "add", value = { pct = -80 }, toward = "source",
                              duration = { flat = 5 } } } } } },
    { id = "hunters_lens", name = "Линза охотника", kind = "equipment", slot = "trinket", rarity = "rare", value = 70,
      stats = { vision_range = 12 } },
  },
}
