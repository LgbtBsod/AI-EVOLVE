-- lua_content/bosses.lua
-- Боссы (последний уровень акта) и мини-боссы (5-й уровень акта).
-- Каждый навык - способность схемы Effect -> Ops[] и исполняется единым
-- менеджером эффектов, как удар оружием героя. Телеграф: cast_time > 0 -
-- на земле появляется круг radius, через cast_time секунд удар по кругу
-- (герой может выйти из него). Фазы: навыки с when = "ctx.hp_pct < N".
-- Круги бьют всех (френдли фаер): удар по земле заденет и призванных слуг, и
-- самого босса, если он стоит в круге; нова вокруг себя - affects = "others".
-- Хелперы ниже собирают типовые навыки; prefix делает id уникальными.

local P = ""  -- префикс текущего босса (id навыков: "<босс>.<навык>")
local function id(s) return P .. "." .. s end
local function dmg(pct) return { pct = pct, of = "attack_damage" } end

local function strike(n, name, pct, cd, extra)
  local ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = dmg(pct) } }
  for _, o in ipairs(extra or {}) do ops[#ops + 1] = o end
  return { id = id(n), name = name, tags = { "attack", "skill" }, range = { pct = 120, of = "attack_range" },
           cooldown = cd, ops = ops }
end
local function slam(n, name, pct, radius, cast, cd, when)   -- удар по кругу у цели, с телеграфом
  return { id = id(n), name = name, tags = { "skill", "aoe" }, range = 9, cooldown = cd, cast_time = cast,
           radius = radius, when = when,
           ops = { { kind = "deal", target = "area", radius = radius, stat = "hp", op = "sub", value = dmg(pct) } } }
end
local function nova(n, name, pct, radius, cast, cd, when)   -- волна вокруг себя
  return { id = id(n), name = name, tags = { "skill", "aoe" }, cooldown = cd, cast_time = cast, radius = radius,
           needs_target = true, range = radius + 2, when = when,
           ops = { { kind = "deal", target = "area", center = "self", radius = radius, affects = "others",
                     stat = "hp", op = "sub", value = dmg(pct) } } }
end
local function bolt(n, name, pct, range, cd, dot)            -- снаряд (+ урон со временем)
  local ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = dmg(pct) } }
  if dot then
    ops[2] = { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = dmg(dot), every = 1,
               duration = { flat = 4 }, flags = { "true_damage" } }
  end
  return { id = id(n), name = name, tags = { "skill", "spell" }, range = range, cooldown = cd, ops = ops }
end
local function field(n, name, pct, radius, secs, cd)         -- ядовитое/ледяное поле: урон каждую секунду
  return { id = id(n), name = name, tags = { "skill", "aoe" }, range = 9, cooldown = cd, cast_time = 1.0, radius = radius,
           ops = { { kind = "deal", target = "area", radius = radius, stat = "hp", op = "sub", value = dmg(pct),
                     every = 1, duration = { flat = secs }, flags = { "true_damage" } } } }
end
local function summon(n, name, kind, count, cd, when)
  return { id = id(n), name = name, tags = { "skill", "summon" }, cooldown = cd, when = when,
           ops = { { kind = "summon", target = "self", summon = kind, count = count } } }
end
local function heal(n, name, pct, cd, when)
  return { id = id(n), name = name, tags = { "skill", "heal" }, cooldown = cd, when = when or "ctx.hp_pct < 50",
           ops = { { kind = "heal", target = "self", stat = "hp", op = "add", value = { pct = pct, of = "max_hp" } } } }
end
local function shield(n, name, secs, cd, when)               -- неуязвимость
  return { id = id(n), name = name, tags = { "skill", "buff" }, cooldown = cd, when = when or "ctx.hp_pct < 60",
           ops = { { kind = "buff", target = "self", buff_id = id(n), flags = { "iframe" }, duration = { flat = secs } } } }
end
local function enrage(n, name, pct, secs, cd, when)
  return { id = id(n), name = name, tags = { "skill", "buff" }, cooldown = cd, when = when,
           needs_target = true, range = 12,
           ops = { { kind = "mod", target = "self", stat = "attack_damage", op = "add", value = { pct = pct }, duration = { flat = secs } },
                   { kind = "mod", target = "self", stat = "aspd", op = "add", value = { pct = pct / 2 }, duration = { flat = secs } } } }
end
local function curse(n, name, stat, pct, secs, cd, range)   -- ослабить героя на время
  return { id = id(n), name = name, tags = { "skill", "curse" }, range = range or 8, cooldown = cd,
           ops = { { kind = "mod", target = "enemy", stat = stat, op = "add", value = { pct = -pct }, duration = { flat = secs } } } }
end
local function charge(n, name, pct, cd)                     -- рывок к цели и удар
  return { id = id(n), name = name, tags = { "attack", "skill" }, range = 12, cooldown = cd,
           ops = { { kind = "move", target = "self", mode = "charge", distance = 12 },
                   { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = dmg(pct) } } }
end
local function knock(n, name, pct, cd)                       -- удар с отбрасыванием
  return { id = id(n), name = name, tags = { "attack", "skill" }, range = 2.8, cooldown = cd,
           ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = dmg(pct) },
                   { kind = "move", target = "enemy", mode = "knockback", distance = 5 } } }
end
local function pull(n, name, pct, cd)                        -- притянуть к себе
  return { id = id(n), name = name, tags = { "skill" }, range = 10, cooldown = cd,
           ops = { { kind = "move", target = "enemy", mode = "pull", distance = 8 },
                   { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = dmg(pct) } } }
end
local function drain(n, name, pct, cd)                       -- похищение жизни
  return { id = id(n), name = name, tags = { "skill", "spell" }, range = 7, cooldown = cd,
           ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = dmg(pct) },
                   { kind = "heal", target = "self", stat = "hp", op = "add", value = dmg(pct / 2) } } }
end
local function blink(n, name, cd)                            -- мгновенно оказаться за спиной
  return { id = id(n), name = name, tags = { "skill" }, range = 14, cooldown = cd,
           ops = { { kind = "move", target = "self", mode = "blink", distance = 14 } } }
end

local function boss(def)
  P = def.id
  def.skills = def.kit()
  def.kit = nil
  return def
end

return {
  bosses = {
    -- ====================================================== Мидгард
    boss { id = "bandit_captain", name = "Атаман разбойников", role = "miniboss", shape = "humanoid", size = 1.5,
           color = { 0.5, 0.3, 0.2, 1 }, health = 400, damage = 16, defense = 5, speed = 5.0, exp_reward = 250,
           kit = function() return {
             strike("slash", "Размашистый удар", 150, 5), charge("rush", "Натиск", 120, 9),
             summon("gang", "Банда", "goblin", 2, 18, "ctx.hp_pct < 70"), heal("flask", "Фляга", 20, 20),
             bolt("knife", "Метательный нож", 90, 8, 6, 20), enrage("fury", "Злоба", 30, 8, 25, "ctx.hp_pct < 40"),
           } end },
    boss { id = "forest_warden", name = "Хранитель леса", role = "boss", shape = "giant", size = 2.8,
           color = { 0.25, 0.45, 0.2, 1 }, health = 1100, damage = 22, defense = 8, speed = 3.5, exp_reward = 700,
           kit = function() return {
             strike("branch", "Удар ветвью", 140, 4), slam("root_slam", "Корни из-под земли", 170, 3.5, 1.5, 7),
             nova("thorn_ring", "Кольцо шипов", 110, 4.5, 1.2, 10), field("spores", "Споры", 25, 4, 5, 12),
             summon("wolves", "Стая", "wolf", 2, 16), summon("slimes", "Гниль", "slime", 3, 22, "ctx.hp_pct < 60"),
             heal("sap", "Живица", 12, 18), curse("entangle", "Опутывание", "move_speed", 60, 3, 11),
             knock("sweep", "Размах", 130, 9), shield("bark", "Кора", 3, 30),
             enrage("wrath", "Гнев леса", 35, 10, 30, "ctx.hp_pct < 35"),
             slam("fall", "Падение древа", 260, 3.0, 2.2, 20, "ctx.hp_pct < 50"),
           } end },

    -- ====================================================== Йотунхейм
    boss { id = "rime_witch", name = "Изморозная ведьма", role = "miniboss", shape = "humanoid", size = 1.4,
           color = { 0.7, 0.85, 1.0, 1 }, health = 520, damage = 18, defense = 5, speed = 4.5, exp_reward = 380,
           kit = function() return {
             bolt("ice_shard", "Ледяной осколок", 120, 9, 3, 15), curse("frostbite", "Обморожение", "aspd", 30, 5, 12),
             field("rime", "Иней", 30, 3.5, 5, 13), blink("step", "Шаг метели", 11),
             summon("wolves", "Ледяные волки", "frost_wolf", 2, 18), shield("mirror", "Ледяное зеркало", 2.5, 24),
             slam("icicles", "Сосульки", 170, 3, 1.6, 9),
           } end },
    boss { id = "frost_jarl", name = "Ярл Инея", role = "boss", shape = "giant", size = 3.0,
           color = { 0.55, 0.7, 0.95, 1 }, health = 1500, damage = 26, defense = 10, speed = 4.0, exp_reward = 1100,
           kit = function() return {
             strike("axe", "Секира йотуна", 150, 4), charge("avalanche", "Лавина", 140, 10),
             slam("glacier", "Ледник", 200, 3.5, 1.6, 8), nova("frost_nova", "Морозная волна", 120, 5, 1.2, 11),
             field("blizzard", "Буран", 30, 5, 6, 15), curse("chill", "Стужа", "move_speed", 50, 4, 9),
             curse("brittle", "Хрупкость", "defense", 40, 6, 14), knock("shoulder", "Толчок плечом", 120, 8),
             summon("trolls", "Тролли", "ice_troll", 2, 22), summon("wolves", "Волчья стая", "frost_wolf", 3, 26, "ctx.hp_pct < 50"),
             heal("mead", "Мёд скальдов", 12, 22), shield("ice_armor", "Ледяной доспех", 3, 28),
             enrage("berserk", "Ярость йотуна", 40, 10, 30, "ctx.hp_pct < 35"),
             slam("ragnarok", "Лёд Рагнарёка", 300, 4.5, 2.5, 24, "ctx.hp_pct < 30"),
           } end },

    -- ====================================================== Свартальфхейм
    boss { id = "spider_queen", name = "Королева пауков", role = "miniboss", shape = "spider", size = 2.2,
           color = { 0.2, 0.15, 0.2, 1 }, health = 700, damage = 22, defense = 6, speed = 6.0, exp_reward = 520,
           kit = function() return {
             strike("fangs", "Жвалы", 140, 4, { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = dmg(20),
               every = 1, duration = { flat = 4 }, flags = { "true_damage" } } }),
             curse("web", "Паутина", "move_speed", 70, 3, 10), summon("brood", "Выводок", "cave_spider", 3, 15),
             field("venom_pool", "Лужа яда", 35, 3.5, 5, 12), pull("silk", "Шёлковая нить", 90, 11),
             blink("skitter", "Метнуться", 9), heal("feed", "Пир", 15, 20),
           } end },
    boss { id = "forge_golem", name = "Голем Горна", role = "boss", shape = "giant", size = 3.2,
           color = { 0.55, 0.35, 0.2, 1 }, health = 2100, damage = 30, defense = 14, speed = 3.0, exp_reward = 1600,
           kit = function() return {
             strike("hammer", "Молот", 150, 4), slam("anvil", "Наковальня", 220, 3.5, 1.7, 8),
             nova("slag", "Выброс шлака", 120, 5, 1.3, 10), field("molten", "Расплав", 40, 4, 6, 14),
             bolt("rivet", "Раскалённая заклёпка", 110, 10, 5, 25), knock("piston", "Поршень", 140, 9),
             charge("steam", "Паровой рывок", 130, 12), curse("rust", "Ржа", "defense", 45, 6, 13),
             curse("heat", "Жар горна", "aspd", 30, 5, 15), summon("shards", "Осколки", "golem_shard", 2, 18),
             shield("plating", "Бронелисты", 3, 26), heal("reforge", "Перековка", 12, 24),
             enrage("overheat", "Перегрев", 40, 10, 28, "ctx.hp_pct < 40"),
             slam("meltdown", "Расплавление", 320, 5, 2.6, 26, "ctx.hp_pct < 30"),
             nova("steam_burst", "Паровой взрыв", 160, 6, 1.8, 18, "ctx.hp_pct < 60"),
           } end },

    -- ====================================================== Ванахейм
    boss { id = "mire_hag", name = "Трясинная карга", role = "miniboss", shape = "humanoid", size = 1.3,
           color = { 0.35, 0.45, 0.25, 1 }, health = 900, damage = 24, defense = 6, speed = 4.5, exp_reward = 700,
           kit = function() return {
             drain("leech", "Пиявки", 120, 6), field("bog", "Топь", 35, 4, 6, 12),
             curse("mire", "Засасывание", "move_speed", 60, 4, 10), summon("lurkers", "Болотники", "bog_lurker", 2, 18),
             bolt("hex", "Порча", 110, 9, 5, 25), blink("mist_step", "Шаг в тумане", 12), heal("brew", "Варево", 18, 20),
             shield("bubble", "Пузырь", 2.5, 26),
           } end },
    boss { id = "bog_hydra", name = "Болотная гидра", role = "boss", shape = "serpent", size = 3.2,
           color = { 0.25, 0.4, 0.3, 1 }, health = 2800, damage = 34, defense = 10, speed = 4.0, exp_reward = 2200,
           kit = function() return {
             strike("bite", "Укус", 150, 3), strike("second_head", "Вторая голова", 120, 5),
             strike("third_head", "Третья голова", 120, 7), bolt("acid", "Кислота", 110, 9, 5, 30),
             field("acid_pool", "Кислотная лужа", 40, 4, 6, 12), slam("tail", "Удар хвостом", 200, 3.5, 1.5, 9),
             nova("thrash", "Метания", 130, 5.5, 1.2, 11), pull("coil", "Кольца", 100, 13),
             curse("rot", "Гниль", "hp_regen", 100, 8, 16), summon("spawn", "Отродья", "bog_lurker", 3, 20),
             heal("regrow", "Новая голова", 15, 16, "ctx.hp_pct < 70"), shield("submerge", "Погружение", 3, 28),
             enrage("frenzy", "Бешенство", 40, 10, 30, "ctx.hp_pct < 40"),
             bolt("miasma", "Миазмы", 90, 10, 9, 45), slam("tidal", "Волна топи", 300, 5, 2.4, 24, "ctx.hp_pct < 30"),
             curse("drown", "Утопление", "aspd", 35, 5, 18),
           } end },

    -- ====================================================== Хельхейм
    boss { id = "bone_colossus", name = "Костяной колосс", role = "miniboss", shape = "giant", size = 2.8,
           color = { 0.85, 0.85, 0.75, 1 }, health = 1300, damage = 30, defense = 12, speed = 3.5, exp_reward = 950,
           kit = function() return {
             strike("crush", "Раздавить", 150, 4), slam("bone_rain", "Костяной дождь", 200, 3.5, 1.6, 9),
             summon("skeletons", "Мертвецы", "skeleton", 3, 16), knock("sweep", "Размах", 130, 9),
             nova("shatter", "Разлёт костей", 130, 5, 1.3, 12), shield("ossify", "Окостенение", 3, 26),
             enrage("marrow", "Костный мозг", 35, 10, 28, "ctx.hp_pct < 40"),
           } end },
    boss { id = "hel_matron", name = "Хель, Госпожа мёртвых", role = "boss", shape = "humanoid", size = 2.4,
           color = { 0.35, 0.3, 0.4, 1 }, health = 3400, damage = 38, defense = 12, speed = 4.5, exp_reward = 3000,
           kit = function() return {
             strike("half_touch", "Касание полусмерти", 140, 3), drain("soul_sip", "Глоток души", 130, 6),
             bolt("grave_bolt", "Могильный болт", 120, 10, 4, 25), field("gloom", "Сумрак", 40, 4.5, 6, 12),
             slam("gate", "Врата Хельхейма", 230, 4, 1.8, 10), nova("wail", "Плач", 140, 6, 1.4, 13),
             curse("decay", "Тление", "max_hp", 20, 8, 18), curse("dread", "Ужас", "aspd", 35, 5, 14),
             curse("weakness", "Бессилие", "attack_damage", 30, 6, 16), summon("draugr", "Драугры", "ghoul", 3, 18),
             summon("wraiths", "Призраки", "wraith", 2, 22, "ctx.hp_pct < 60"), blink("veil", "Покров", 12),
             pull("chains", "Цепи мёртвых", 100, 12), heal("tithe", "Десятина душ", 12, 20),
             shield("half_life", "Полужизнь", 3, 26), enrage("queen", "Воля королевы", 40, 10, 30, "ctx.hp_pct < 35"),
             slam("nidhogg", "Нидхёгг грызёт", 340, 5, 2.6, 26, "ctx.hp_pct < 30"),
           } end },

    -- ====================================================== Преддверие
    boss { id = "minos_judge", name = "Минос, судия", role = "miniboss", shape = "giant", size = 2.6,
           color = { 0.45, 0.2, 0.2, 1 }, health = 1700, damage = 34, defense = 12, speed = 4.0, exp_reward = 1300,
           kit = function() return {
             strike("verdict", "Приговор", 160, 4), pull("tail_coil", "Хвост судии", 110, 10),
             curse("sentence", "Кара", "defense", 50, 6, 13), slam("judgement", "Суд", 240, 3.5, 1.8, 10),
             summon("souls", "Осуждённые", "lost_soul", 3, 16), shield("gavel", "Непогрешимость", 3, 26),
             nova("tempest", "Буря сладострастных", 140, 5.5, 1.3, 12),
           } end },
    boss { id = "cerberus", name = "Цербер", role = "boss", shape = "beast", size = 3.0,
           color = { 0.3, 0.2, 0.15, 1 }, health = 4200, damage = 42, defense = 13, speed = 6.0, exp_reward = 3800,
           kit = function() return {
             strike("head_left", "Левая пасть", 130, 3), strike("head_mid", "Средняя пасть", 140, 4),
             strike("head_right", "Правая пасть", 130, 5), charge("pounce", "Прыжок", 150, 9),
             nova("howl", "Троекратный вой", 130, 6, 1.2, 12), field("slaver", "Слюна", 45, 4, 5, 13),
             slam("maul", "Растерзание", 240, 3.5, 1.5, 9), knock("bat", "Удар лапой", 140, 8),
             curse("terror", "Ужас трёх голов", "move_speed", 55, 4, 12), curse("gluttony", "Чревоугодие", "max_hp", 20, 8, 20),
             summon("pups", "Щенки ада", "fire_imp", 3, 20), heal("devour", "Пожрать", 12, 18),
             enrage("frenzy", "Бешенство", 45, 10, 28, "ctx.hp_pct < 40"), shield("hide", "Шкура", 3, 26),
             slam("stampede", "Три головы вместе", 360, 5, 2.4, 24, "ctx.hp_pct < 30"),
           } end },

    -- ====================================================== Дит
    boss { id = "minotaur", name = "Минотавр", role = "miniboss", shape = "giant", size = 2.6,
           color = { 0.45, 0.25, 0.15, 1 }, health = 2300, damage = 42, defense = 14, speed = 5.0, exp_reward = 1800,
           kit = function() return {
             charge("gore", "Бодание", 170, 7), knock("stomp", "Топот", 150, 8),
             slam("labyrinth", "Стены лабиринта", 250, 3.5, 1.6, 10), nova("rage", "Ярость быка", 150, 5, 1.2, 12),
             enrage("bull", "Бычья кровь", 45, 10, 26, "ctx.hp_pct < 45"), curse("maze", "Лабиринт", "move_speed", 50, 4, 12),
             heal("eat", "Жертва", 12, 22),
           } end },
    boss { id = "geryon", name = "Герион, образ обмана", role = "boss", shape = "serpent", size = 3.3,
           color = { 0.6, 0.4, 0.25, 1 }, health = 5200, damage = 48, defense = 15, speed = 5.0, exp_reward = 4800,
           kit = function() return {
             strike("honest_face", "Лицо праведника", 140, 3), strike("scorpion", "Жало скорпиона", 160, 5,
               { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = dmg(30), every = 1,
                   duration = { flat = 5 }, flags = { "true_damage" } } }),
             blink("deceit", "Обман", 9), drain("usury", "Лихва", 140, 7), bolt("fire_rain", "Огненный дождь", 120, 10, 5, 30),
             field("burning_sand", "Горящий песок", 50, 5, 6, 12), slam("plunge", "Спуск в Злые Щели", 260, 4, 1.8, 10),
             nova("wings", "Взмах крыльев", 150, 6, 1.3, 12), curse("lies", "Ложь", "crit_chance", 50, 8, 16),
             curse("fraud", "Подлог", "defense", 50, 6, 14), pull("lure", "Приманка", 110, 11),
             summon("furies", "Фурии", "fury", 1, 24, "ctx.hp_pct < 70"), summon("imps", "Бесы", "fire_imp", 3, 18),
             heal("false_mercy", "Ложная милость", 12, 20), shield("mask", "Маска", 3, 26),
             enrage("true_face", "Истинный лик", 50, 12, 30, "ctx.hp_pct < 35"),
             slam("malebolge", "Злые Щели", 380, 5.5, 2.6, 26, "ctx.hp_pct < 30"),
           } end },

    -- ====================================================== Муспельхейм и Коцит
    boss { id = "surtr", name = "Сурт, владыка огня", role = "miniboss", shape = "giant", size = 3.2,
           color = { 1.0, 0.35, 0.05, 1 }, health = 3600, damage = 52, defense = 16, speed = 4.0, exp_reward = 3000,
           kit = function() return {
             strike("flame_sword", "Пламенный меч", 170, 4), slam("sunfall", "Падение солнца", 280, 4, 1.8, 10),
             nova("flare", "Вспышка", 150, 6, 1.3, 12), field("embers", "Угли", 55, 5, 6, 13),
             summon("giants", "Огненные великаны", "fire_giant", 1, 24), enrage("inferno", "Инферно", 45, 10, 28, "ctx.hp_pct < 40"),
             curse("scorch", "Ожог", "hp_regen", 100, 8, 14), charge("wildfire", "Пожар", 160, 11),
           } end },
    -- Люцифер: вмёрз в Коцит по грудь; три пасти, шесть крыльев морозят озеро.
    -- Не «главное зло», а самая заметная сущность этого мира - первый из финальных боссов.
    boss { id = "lucifer", name = "Люцифер, вмёрзший в Коцит", role = "final", shape = "giant", size = 4.2,
           color = { 0.35, 0.45, 0.65, 1 }, health = 12000, damage = 60, defense = 20, speed = 0.0, exp_reward = 20000,
           rooted = true,
           dialog = { spawn = "Ещё один герой. Их посылают ко мне каждый цикл. Ты знаешь, кто?",
                      death = "Я лишь страж на виду. Нити держат другие... Спроси Орден Узла." },
           kit = function() return {
             strike("mouth_judas", "Пасть Иуды", 170, 3), strike("mouth_brutus", "Пасть Брута", 150, 4),
             strike("mouth_cassius", "Пасть Кассия", 150, 5), pull("grasp", "Хватка предателя", 130, 9),
             nova("six_wings", "Шесть крыльев", 150, 7, 1.4, 11), slam("frozen_tears", "Слёзы шести глаз", 240, 4, 1.8, 9),
             field("permafrost", "Вечная мерзлота", 60, 5, 7, 13), curse("ice_prison", "Ледяная темница", "move_speed", 85, 2.5, 14),
             curse("abyss_cold", "Холод бездны", "aspd", 40, 6, 15), curse("temptation", "Искушение", "defense", 60, 7, 17),
             curse("pride", "Гордыня", "attack_damage", 30, 6, 18), bolt("morning_star", "Взгляд Денницы", 200, 14, 6, 40),
             summon("traitors", "Предатели Каины", "frost_damned", 3, 18), summon("heralds", "Глашатаи Сурта", "surtr_herald", 1, 30, "ctx.hp_pct < 60"),
             knock("wingbeat", "Удар крыла", 160, 8), heal("tears", "Замёрзшие слёзы", 8, 26, "ctx.hp_pct < 40"),
             shield("ice_shell", "Ледяная скорлупа", 4, 30, "ctx.hp_pct < 50"),
             enrage("fallen", "Падший херувим", 50, 12, 30, "ctx.hp_pct < 35"),
             slam("muspel_fire", "Огонь Муспельхейма", 320, 6, 2.2, 22, "ctx.hp_pct < 50"),
             nova("last_winter", "Последняя зима", 450, 9, 3.0, 30, "ctx.hp_pct < 25"),
           } end },

    -- ====================================================== Орден Узла: теневые правители
    -- Вымышленное тайное общество, которое держит нити всех девяти миров:
    -- торговлю, войны, «героев» и сам цикл, перезапускающий мир. У каждого из
    -- совета своя правда - кто-то считает, что без Узла миры давно бы сгорели.
    boss { id = "grey_cardinal", name = "Серый кардинал Узла", role = "final", shape = "humanoid", size = 2.2,
           color = { 0.45, 0.45, 0.48, 1 }, health = 14000, damage = 64, defense = 22, speed = 5.0, exp_reward = 22000,
           dialog = { spawn = "Люцифер был удобен: на него смотрели все. На меня не смотрел никто.",
                      death = "Без нас короли перегрызли бы друг друга за век. Мы - порядок. Ты - хаос." },
           kit = function() return {
             strike("whisper", "Шёпот на ухо", 150, 3), curse("rumor", "Слух", "defense", 50, 6, 12),
             curse("doubt", "Сомнение", "crit_chance", 60, 8, 14), curse("bribe", "Подкуп", "attack_damage", 35, 6, 16),
             blink("backroom", "Задняя комната", 8), drain("tithe", "Тайная десятина", 150, 7),
             summon("agents", "Агенты Узла", "dark_elf", 3, 16), summon("zealots", "Фанатики", "fury", 1, 24, "ctx.hp_pct < 70"),
             field("smoke", "Дымовая завеса", 60, 5, 6, 13), slam("decree", "Тайный указ", 280, 4, 1.8, 10),
             nova("purge", "Чистка", 180, 6, 1.4, 14), pull("puppet", "Нить марионетки", 140, 11),
             shield("scapegoat", "Козёл отпущения", 3, 26), heal("favors", "Старые долги", 10, 22),
             enrage("true_power", "Настоящая власть", 50, 12, 30, "ctx.hp_pct < 35"),
             slam("coup", "Переворот", 400, 5.5, 2.6, 26, "ctx.hp_pct < 30"),
           } end },
    boss { id = "knot_treasurer", name = "Казначей Узла", role = "final", shape = "humanoid", size = 2.0,
           color = { 0.75, 0.62, 0.25, 1 }, health = 15000, damage = 66, defense = 24, speed = 4.5, exp_reward = 24000,
           dialog = { spawn = "Каждый караван, каждая монета, каждый твой сундук - от нас. Ты жил в долг.",
                      death = "Долг не исчезает. Его просто переписывают на другого." },
           kit = function() return {
             strike("ledger", "Удар счётной книгой", 150, 3), bolt("coin", "Монета-снаряд", 160, 11, 4, 30),
             curse("interest", "Проценты", "hp_regen", 100, 10, 14), curse("debt", "Долговая яма", "move_speed", 60, 4, 12),
             curse("tax", "Налог", "max_hp", 20, 10, 20), drain("collect", "Взыскание", 170, 7),
             summon("mercs", "Наёмники", "centaur_guard", 2, 18), summon("caravan_guard", "Стража караванов", "forge_guard", 1, 24),
             field("gold_rain", "Золотой дождь", 65, 5, 6, 13), slam("vault", "Хранилище", 300, 4, 1.8, 10),
             nova("audit", "Ревизия", 190, 6, 1.4, 14), shield("insurance", "Страховка", 3, 24),
             heal("dividends", "Дивиденды", 10, 20), knock("foreclose", "Изъятие", 170, 9),
             enrage("monopoly", "Монополия", 55, 12, 30, "ctx.hp_pct < 35"),
             slam("default", "Дефолт", 420, 6, 2.6, 26, "ctx.hp_pct < 30"),
           } end },
    boss { id = "faceless_architect", name = "Безликий Архитектор", role = "final", shape = "spirit", size = 3.0,
           color = { 0.9, 0.9, 0.95, 0.85 }, health = 20000, damage = 72, defense = 26, speed = 5.5, exp_reward = 40000,
           dialog = { spawn = "Я строю циклы. Этот мир уже сгорал - я собрал его заново. И соберу снова.",
                      death = "Убей меня - и цикл начнёт новый Архитектор. Может быть, ты?" },
           kit = function() return {
             strike("chisel", "Резец", 160, 3), blink("redraw", "Перерисовка", 7), pull("blueprint", "Чертёж", 150, 10),
             slam("keystone", "Замковый камень", 320, 4, 1.7, 9), nova("new_cycle", "Новый цикл", 200, 7, 1.5, 13),
             field("erasure", "Стирание", 70, 5, 6, 12), bolt("compass", "Циркуль", 170, 12, 4, 35),
             curse("forget", "Забвение", "aspd", 45, 6, 14), curse("unmake", "Разборка", "defense", 60, 6, 15),
             curse("vertigo", "Головокружение", "move_speed", 70, 3, 12), drain("recycle", "Переработка", 180, 8),
             summon("echoes", "Эхо прошлых героев", "wraith", 3, 18),
             summon("prototypes", "Прототипы", "golem_shard", 3, 22, "ctx.hp_pct < 70"),
             shield("scaffold", "Леса", 3.5, 26), heal("restore", "Восстановление", 8, 24, "ctx.hp_pct < 40"),
             knock("demolish", "Снос", 180, 9), enrage("vision", "Замысел", 55, 12, 30, "ctx.hp_pct < 35"),
             slam("ragnarok_plan", "План Рагнарёка", 460, 6.5, 2.8, 26, "ctx.hp_pct < 30"),
             nova("last_draft", "Последний чертёж", 520, 9, 3.2, 32, "ctx.hp_pct < 15"),
           } end },

    -- ====================================================== Постановка боя: Sukuna vs Gojo
    -- «Король проклятий» против «Сильнейшего шамана». Оба — финальные боссы одной арены:
    -- ИИ сам выбирает готовые навыки (кулдауны/когда), фазы решают when по hp_pct.
    -- Стиль Сукуны: рвёт броню «Разрывом», добивает доменом «Зловещий Храм».
    -- Стиль Годжо: держит бесконечность щитами, контролирует дистанцию (pull/knockback),
    -- копит ману под «Фиолетовую» и домен «Беспредельная Пустота».
    boss { id = "sukuna", name = "Рёмен Сукуна, Король проклятий", role = "final", shape = "humanoid", size = 2.3,
           color = { 0.35, 0.12, 0.12, 1 }, health = 16000, damage = 70, defense = 24, speed = 5.5, exp_reward = 30000,
           dialog = { spawn = "Ты хочешь умереть стоя перед королём? Тогда стой смирно.",
                      death = "Ха... достойно. Следующий, кто заслужит этот смех, - не ты." },
           kit = function() return {
             strike("slash", "Взмах клинком духа", 160, 3),
             { id = id("dismantle"), name = "Разрыв", tags = { "attack", "skill", "cursed" },
               range = { pct = 250, of = "attack_range" }, cooldown = 4,
               ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub", value = dmg(170) },
                       { kind = "mod", target = "enemy", stat = "defense", op = "add", value = { pct = -40 },
                         duration = { flat = 6 } } } },
             { id = id("world_cleave"), name = "Уничтожение", tags = { "attack", "skill", "cursed" },
               range = { pct = 160, of = "attack_range" }, cooldown = 7, needs_target = true,
               ops = { { kind = "deal", target = "area", center = "self", radius = 4.0, arc = 120, affects = "others",
                         stat = "hp", op = "sub", value = dmg(150) },
                       { kind = "move", target = "enemy", mode = "knockback", distance = 4 } } },
             bolt("arrow", "Стрела огня: Казадза-но-Ю", 200, 10, 6, 40),
             { id = id("shrine_guard"), name = "Малый ранговый барьер", tags = { "skill", "buff" }, cooldown = 26,
               when = "ctx.hp_pct < 55",
               ops = { { kind = "buff", target = "self", buff_id = id("shrine_guard"), flags = { "iframe" },
                         duration = { flat = 3 } },
                       { kind = "move", target = "area", center = "self", radius = 3.0, affects = "others",
                         mode = "knockback", distance = 4 } } },
             summon("wraiths", "Проклятые духи", "wraith", 2, 20, "ctx.hp_pct < 75"),
             blink("dash", "Шаг сквозь тени", 9),
             heal("feast", "Пир плоти", 10, 24, "ctx.hp_pct < 45"),
             enrage("grin", "Улыбка короля", 50, 12, 30, "ctx.hp_pct < 35"),
             { id = id("malevolent_shrine"), name = "Домен: Зловещий Храм",
               tags = { "skill", "aoe", "domain", "cursed" }, range = 12, cooldown = 45, cast_time = 2.5, radius = 6.5,
               when = "ctx.hp_pct < 60",
               ops = { { kind = "deal", target = "area", radius = 6.5, stat = "hp", op = "sub",
                         value = { pct = 70, of = "spell_power" }, every = 1, duration = { flat = 6 },
                         flags = { "true_damage" } } } },
           } end },
    boss { id = "gojo", name = "Сатору Годжо, Шести Глаз", role = "final", shape = "humanoid", size = 2.1,
           color = { 0.85, 0.9, 1.0, 1 }, health = 15000, damage = 66, defense = 20, speed = 6.0, exp_reward = 30000,
           stats = { accuracy = 40, evasion = 35 },
           dialog = { spawn = "Не переживай. Всё равно не сможешь меня коснуться.",
                      death = "Ах... вот оно что. Оказывается, можно было и по-другому." },
           kit = function() return {
             bolt("bolt", "Сгусток проклятой энергии", 150, 9, 2.5, nil),
             { id = id("infinity"), name = "Бесконечность", tags = { "skill", "buff" }, cooldown = 30,
               when = "ctx.hp_pct < 70",
               ops = { { kind = "buff", target = "self", buff_id = id("infinity"), flags = { "iframe" },
                         duration = { flat = 4 } } } },
             pull("blue", "Синяя: притяжение", 160, 8),
             knock("red", "Красная: отталкивание", 200, 10),
             { id = id("purple"), name = "Фиолетовая: мнимая масса", tags = { "skill", "spell", "aoe", "cursed" },
               range = 14, cooldown = 22, cast_time = 2.0, radius = 3.5,
               ops = { { kind = "deal", target = "area", radius = 3.5, stat = "hp", op = "sub",
                         value = { pct = 260, of = "spell_power" } } } },
             { id = id("reversal_heal"), name = "Обращённая техника: самоисцеление",
               tags = { "heal", "skill", "cursed" }, cooldown = 16, when = "ctx.hp_pct < 60",
               ops = { { kind = "heal", target = "self", stat = "hp", op = "add",
                         value = { pct = 18, of = "max_hp" } } } },
             curse("six_eyes", "Шесть Глаз: чтение", "attack_damage", 30, 6, 16),
             blink("step", "Шаг пустоты", 8),
             { id = id("black_flash"), name = "Чёрная Вспышка", tags = { "attack", "spell", "lightning", "cursed" },
               range = 12, cooldown = 25,
               ops = { { kind = "deal", target = "enemy", stat = "hp", op = "sub",
                         value = { pct = 240, of = "spell_power" } },
                       { kind = "mod", target = "enemy", stat = "damage_taken", op = "add", value = { pct = 20 },
                         duration = { flat = 5 } } } },
             enrage("hollow", "Съеденная пустота", 45, 12, 30, "ctx.hp_pct < 35"),
             { id = id("unlimited_void"), name = "Домен: Беспредельная Пустота",
               tags = { "skill", "spell", "domain", "cursed" }, range = 12, cooldown = 45, cast_time = 2.5,
               radius = 6.0, when = "ctx.hp_pct < 60",
               ops = { { kind = "deal", target = "area", radius = 6.0, stat = "hp", op = "sub",
                         value = { pct = 300, of = "spell_power" } },
                       { kind = "mod", target = "area", radius = 6.0, stat = "aspd", op = "add",
                         value = { pct = -50 }, duration = { flat = 5 } },
                       { kind = "mod", target = "area", radius = 6.0, stat = "move_speed", op = "add",
                         value = { pct = -40 }, duration = { flat = 5 } } } },
           } end },
  },
}
