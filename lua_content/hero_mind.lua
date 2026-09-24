-- lua_content/hero_mind.lua
-- Что движет героем. Игрок не управляет им напрямую: он выбирает ЭМОЦИЮ (сдвиг
-- весов целей) и даёт ПОДСКАЗКИ (интерес к направлению или цели). Решает всё
-- равно герой - по полезности целей (src/gameplay/hero_drive.py).
--
-- Цели ИИ героя: fight (бой), loot (сундуки, мешки добычи), exit (выход),
-- hint (карты и NPC с подсказками), explore (исследование).
return {
  -- базовая «ценность» цели; итог = база(ситуация) x вес эмоции + бонус подсказки
  goals = { fight = 1.4, loot = 0.8, exit = 0.7, hint = 0.5, explore = 0.25 },
  stickiness = 0.15,       -- текущая цель ценнее на столько: без метаний выход <-> подсказка

  emotions = {
    calm      = { name = "Спокойствие", key = "f1", thought = "Спокойно, по порядку.",
                  weights = {}, retreat_hp = 0.30, heal_at = 0.35 },
    rage      = { name = "Ярость", key = "f2", thought = "Разорву любого!",
                  weights = { fight = 1.8, loot = 0.5, exit = 0.6, hint = 0.5 },
                  retreat_hp = 0.15, heal_at = 0.20, press_bias = 0.35 },
    fear      = { name = "Страх", key = "f3", thought = "Надо выбираться отсюда...",
                  weights = { fight = 0.5, exit = 1.5, hint = 1.2, explore = 0.6 },
                  retreat_hp = 0.50, heal_at = 0.50 },
    curiosity = { name = "Любопытство", key = "f4", thought = "А что там дальше?",
                  weights = { explore = 3.0, hint = 1.6, loot = 1.3, exit = 0.6 },
                  retreat_hp = 0.30, heal_at = 0.35 },
    greed     = { name = "Жадность", key = "f5", thought = "Золото само себя не соберёт.",
                  weights = { loot = 2.2, fight = 1.1, exit = 0.7 },
                  retreat_hp = 0.25, heal_at = 0.30 },
    resolve   = { name = "Решимость", key = "f6", thought = "Вперёд, к выходу.",
                  weights = { exit = 1.8, hint = 1.3, fight = 0.8, loot = 0.5 },
                  retreat_hp = 0.25, heal_at = 0.35 },
  },

  -- подсказки игрока: не приказ, а интерес. dir - сторона света (x, y), goal - к чему тянет.
  -- Интерес затухает за duration секунд; strength - сколько добавляет к полезности цели.
  directives = {
    strength = 0.6, duration = 30,
    north = { name = "на север",  key = "arrow_up",    dir = { 0, 1 } },
    south = { name = "на юг",     key = "arrow_down",  dir = { 0, -1 } },
    east  = { name = "на восток", key = "arrow_right", dir = { 1, 0 } },
    west  = { name = "на запад",  key = "arrow_left",  dir = { -1, 0 } },
    chest = { name = "поищи сундук", key = "c", goal = "loot" },
    exit  = { name = "к выходу",     key = "x", goal = "exit" },
    npc   = { name = "найди NPC",    key = "n", goal = "hint" },
    none  = { name = "без подсказки", key = "z" },
  },
}
