-- lua_content/bestiary.lua
-- Враги: статы на 1-м уровне (дальше их масштабирует world.lua -> scaling),
-- вид (shape, size, color), навыки (lua_content/abilities.lua / bosses.lua),
-- класс добычи (loot.lua -> enemies.<loot>) и тактики, которые враг умеет.
--   shape: humanoid | beast | blob | spirit | giant | spider | serpent
local function foe(name, shape, size, color, hp, dmg, def, speed, exp, opts)
  opts = opts or {}
  return { name = name, shape = shape, size = size, color = color,
           health = hp, damage = dmg, defense = def, speed = speed, exp_reward = exp,
           skills = opts.skills or {}, loot = opts.loot or "basic", ranged = opts.ranged or false,
           tactics = opts.tactics }
end

return {
  enemies = {
    -- Мидгард
    slime        = foe("Слизень", "blob", 0.7, { 0.3, 0.85, 0.35, 1 }, 40, 6, 1, 3.0, 15),
    goblin       = foe("Гоблин", "humanoid", 0.8, { 0.35, 0.6, 0.25, 1 }, 55, 9, 2, 5.0, 22,
                       { skills = { "venom_spit" }, loot = "strong" }),
    wolf         = foe("Волк", "beast", 0.9, { 0.45, 0.45, 0.5, 1 }, 50, 10, 1, 6.5, 20, { tactics = { "flank", "pack" } }),
    goblin_chief = foe("Вождь гоблинов", "humanoid", 1.2, { 0.25, 0.5, 0.15, 1 }, 140, 15, 5, 4.5, 70,
                       { skills = { "war_cry", "crushing_blow" }, loot = "elite" }),
    -- Йотунхейм
    frost_wolf   = foe("Ледяной волк", "beast", 1.0, { 0.75, 0.85, 0.95, 1 }, 55, 11, 2, 6.5, 24, { tactics = { "flank", "pack" } }),
    ice_troll    = foe("Ледяной тролль", "giant", 1.5, { 0.55, 0.7, 0.8, 1 }, 110, 14, 6, 3.5, 45,
                       { skills = { "crushing_blow" }, loot = "strong" }),
    skeleton     = foe("Скелет", "humanoid", 0.9, { 0.9, 0.9, 0.82, 1 }, 45, 10, 3, 5.5, 20, { skills = { "venom_spit" } }),
    frost_giant  = foe("Ледяной великан", "giant", 2.0, { 0.6, 0.75, 0.95, 1 }, 220, 20, 8, 3.5, 110,
                       { skills = { "war_cry", "crushing_blow" }, loot = "elite" }),
    -- Свартальфхейм
    dark_elf     = foe("Тёмный альв", "humanoid", 0.95, { 0.3, 0.25, 0.45, 1 }, 60, 12, 3, 6.0, 26,
                       { skills = { "venom_spit" }, ranged = true, tactics = { "kite", "flank" } }),
    cave_spider  = foe("Пещерный паук", "spider", 0.9, { 0.25, 0.2, 0.2, 1 }, 45, 11, 2, 6.5, 22, { skills = { "venom_spit" } }),
    golem_shard  = foe("Осколок голема", "giant", 1.1, { 0.55, 0.45, 0.35, 1 }, 90, 12, 9, 3.0, 30),
    forge_guard  = foe("Страж кузни", "humanoid", 1.3, { 0.6, 0.35, 0.2, 1 }, 200, 18, 10, 4.0, 110,
                       { skills = { "crushing_blow", "war_cry" }, loot = "elite" }),
    -- Ванахейм
    bog_lurker   = foe("Болотник", "serpent", 1.1, { 0.3, 0.4, 0.25, 1 }, 75, 12, 3, 4.5, 28, { tactics = { "ambush" } }),
    wisp         = foe("Блуждающий огонь", "spirit", 0.6, { 0.6, 0.95, 0.9, 0.85 }, 35, 9, 0, 7.0, 18,
                       { ranged = true, tactics = { "kite" } }),
    swamp_shaman = foe("Болотный шаман", "humanoid", 1.1, { 0.35, 0.55, 0.3, 1 }, 150, 16, 4, 4.5, 100,
                       { skills = { "venom_spit", "war_cry" }, loot = "elite", ranged = true }),
    -- Хельхейм
    ghoul        = foe("Упырь", "humanoid", 1.0, { 0.5, 0.55, 0.45, 1 }, 70, 13, 3, 5.5, 26, { tactics = { "rush", "pack" } }),
    wraith       = foe("Призрак", "spirit", 1.0, { 0.7, 0.75, 0.9, 0.75 }, 55, 14, 1, 6.0, 26, { tactics = { "flank" } }),
    death_knight = foe("Рыцарь смерти", "humanoid", 1.4, { 0.2, 0.2, 0.25, 1 }, 240, 22, 10, 4.5, 130,
                       { skills = { "crushing_blow", "war_cry" }, loot = "elite" }),
    -- Преддверие
    lost_soul    = foe("Заблудшая душа", "spirit", 0.8, { 0.8, 0.8, 0.95, 0.7 }, 50, 12, 0, 6.0, 24),
    tempest_shade= foe("Тень бури", "spirit", 1.0, { 0.45, 0.4, 0.7, 0.8 }, 65, 15, 1, 7.5, 28, { tactics = { "flank", "kite" } }),
    harpy        = foe("Гарпия", "beast", 1.1, { 0.6, 0.35, 0.45, 1 }, 170, 18, 4, 7.0, 110,
                       { skills = { "venom_spit", "war_cry" }, loot = "elite", tactics = { "kite" } }),
    -- Дит
    fire_imp     = foe("Огненный бес", "humanoid", 0.8, { 0.95, 0.35, 0.1, 1 }, 55, 14, 2, 6.5, 26,
                       { ranged = true, tactics = { "kite", "pack" } }),
    heretic_flame= foe("Пламя ересиарха", "spirit", 1.0, { 1.0, 0.55, 0.15, 0.9 }, 70, 16, 1, 5.0, 28),
    centaur_guard= foe("Кентавр-страж", "beast", 1.5, { 0.55, 0.35, 0.25, 1 }, 120, 18, 6, 7.0, 45,
                       { skills = { "crushing_blow" }, ranged = true, loot = "strong" }),
    fury         = foe("Фурия", "humanoid", 1.2, { 0.7, 0.1, 0.15, 1 }, 220, 24, 6, 6.0, 130,
                       { skills = { "war_cry", "venom_spit" }, loot = "elite" }),
    -- Муспельхейм
    fire_giant   = foe("Огненный великан", "giant", 2.2, { 0.85, 0.25, 0.05, 1 }, 200, 22, 9, 3.5, 60,
                       { skills = { "crushing_blow" }, loot = "strong" }),
    frost_damned = foe("Вмёрзший грешник", "humanoid", 1.0, { 0.65, 0.8, 0.95, 1 }, 80, 16, 5, 4.0, 30),
    surtr_herald = foe("Глашатай Сурта", "giant", 1.8, { 1.0, 0.45, 0.1, 1 }, 300, 28, 10, 4.5, 150,
                       { skills = { "war_cry", "crushing_blow" }, loot = "elite" }),
  },
  -- как тип врага распределяет очки характеристик за уровень (по форме тела)
  attribute_weights = {
    humanoid = { strength = 0.35, vitality = 0.3, agility = 0.2, endurance = 0.15 },
    beast    = { strength = 0.35, agility = 0.35, vitality = 0.3 },
    blob     = { vitality = 0.6, strength = 0.4 },
    spirit   = { agility = 0.4, intelligence = 0.3, vitality = 0.3 },
    giant    = { vitality = 0.45, strength = 0.4, endurance = 0.15 },
    spider   = { agility = 0.4, strength = 0.3, vitality = 0.3 },
    serpent  = { vitality = 0.4, strength = 0.35, agility = 0.25 },
  },
  -- старые типы (клавиша 1 и тесты): basic/strong/elite -> враги текущего акта
  legacy = { basic = "enemies", strong = "enemies", elite = "elites", boss = "boss" },
}
