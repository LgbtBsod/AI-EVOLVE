-- lua_content/world.lua
-- Мир из 80 уровней: 8 актов по 10. Путь героя идёт по Девяти мирам сверху
-- вниз, всё глубже - от Мидгарда к огню Муспельхейма. Сердце Муспельхейма -
-- девятый круг ада: замёрзшее озеро Коцит, в котором заточён Люцифер
-- (уровень 80, финал). Последние уровни акта 8 - четыре пояса Коцита по Данте:
-- Каина, Антенора, Птоломея, Джудекка.
--
-- Поля акта:
--   levels   = { первый, последний }
--   biome    - вид земли и декораций (src/render/biomes: ground, props, light)
--   enemies  - обычные враги (бестиарий lua_content/bestiary.lua), elites - элиты
--   boss     - босс последнего уровня акта (lua_content/bosses.lua); miniboss - на 5-м уровне акта
--   weather  - погода, которая может выпасть на уровне акта (lua_content/weather.lua)
--   towns    - уровни с городом (торговцы, мастерская, караваны), относительно начала акта
--   lore     - что говорят NPC об этом месте
return {
  max_level = 80,

  -- Прогрессия. Уровень врага = уровень мира + cycle_level_bonus * (пройденные циклы)
  -- + 1 за каждые minutes_per_enemy_level минут сессии. Очки характеристик за уровень
  -- (выше 1-го): герой 5 (распределяет сам), обычный враг 10, элита 15, босс +10 к
  -- каждой характеристике. Опыт герой получает только за активности (xp).
  progression = {
    hero_points_per_level = 5,
    enemy_points_per_level = { normal = 10, elite = 15 },
    boss_points_per_attribute = 10,
    minutes_per_enemy_level = 5,
    cycle_level_bonus = 20,
    exp_growth = 0.12,       -- награда за врага растёт на 12% за его уровень
    xp = { chest = 50, trap_disarm = 15, hint = 10, exit = 120, boss_kill = 300,
           trick_dodge = 25, trick_multikill = 30, trick_clutch = 40, trick_overkill = 10,
           quest = 150, craft = 12, caravan = 80 },
  },

  acts = {
    { id = "midgard", name = "Мидгард: Опушка", levels = { 1, 10 }, biome = "forest",
      enemies = { "slime", "goblin", "wolf" }, elites = { "goblin_chief" },
      miniboss = "bandit_captain", boss = "forest_warden",
      weather = { "clear", "clear", "rain", "fog" }, towns = { 1, 6 },
      lore = { "За лесом, говорят, земля уходит вниз - к старым мирам.",
               "Хранитель леса не пускает чужаков к переходу.",
               "Караваны ходят с узлом на знамени. Никто не помнит, чей это знак." } },

    { id = "jotunheim", name = "Йотунхейм: Ледяные пустоши", levels = { 11, 20 }, biome = "tundra",
      enemies = { "frost_wolf", "ice_troll", "skeleton" }, elites = { "frost_giant" },
      miniboss = "rime_witch", boss = "frost_jarl",
      weather = { "snow", "snow", "blizzard", "clear" }, towns = { 2, 7 },
      lore = { "Йотуны помнят времена до людей. И до богов.",
               "В метель не видно даже собственного меча.",
               "Ярлов меняют, а советники при них - всегда те же лица." } },

    { id = "svartalfheim", name = "Свартальфхейм: Кузни тёмных альвов", levels = { 21, 30 }, biome = "caves",
      enemies = { "dark_elf", "cave_spider", "golem_shard" }, elites = { "forge_guard" },
      miniboss = "spider_queen", boss = "forge_golem",
      weather = { "dust", "clear", "clear" }, towns = { 3, 8 },
      lore = { "Альвы куют то, что не должно существовать.",
               "Здесь продают карты, но половина - ложь.",
               "Альвы куют на заказ. Заказчик платит узелковым серебром." } },

    { id = "vanaheim", name = "Ванахейм: Топи", levels = { 31, 40 }, biome = "swamp",
      enemies = { "bog_lurker", "wisp", "goblin" }, elites = { "swamp_shaman" },
      miniboss = "mire_hag", boss = "bog_hydra",
      weather = { "rain", "fog", "fog", "storm" }, towns = { 2, 7 },
      lore = { "Огни в тумане ведут к выходу. Или в трясину.",
               "Гидра отращивает головы быстрее, чем их рубят.",
               "Говорят, героев до тебя было много. Их имена кто-то вычёркивает." } },

    { id = "helheim", name = "Хельхейм: Сумерки мёртвых", levels = { 41, 50 }, biome = "necropolis",
      enemies = { "skeleton", "ghoul", "wraith" }, elites = { "death_knight" },
      miniboss = "bone_colossus", boss = "hel_matron",
      weather = { "fog", "ashfall", "clear" }, towns = { 4 },
      lore = { "Отсюда никто не уходил. Ты будешь первым.",
               "Хель правит половиной мёртвых. Другая половина ниже.",
               "Мёртвые шепчут про Архитектора: он строил этот мир не в первый раз." } },

    { id = "limbo", name = "Преддверие: Круги Лимба и Похоти", levels = { 51, 60 }, biome = "limbo",
      enemies = { "lost_soul", "wraith", "tempest_shade" }, elites = { "harpy" },
      miniboss = "minos_judge", boss = "cerberus",
      weather = { "storm", "ashfall", "fog" }, towns = { 3 },
      lore = { "Здесь начинаются круги ада. Первый - ещё без мук.",
               "Минос обвивает хвост столько раз, сколько кругов тебе спускаться.",
               "Суд здесь продажный. Кто платит - тот и не грешник." } },

    { id = "dis", name = "Дит: Город огня", levels = { 61, 70 }, biome = "dis",
      enemies = { "fire_imp", "heretic_flame", "centaur_guard" }, elites = { "fury" },
      miniboss = "minotaur", boss = "geryon",
      weather = { "ashfall", "heatwave", "heatwave" }, towns = { 2 },
      lore = { "Стены Дита горят вечно - так начинается нижний ад.",
               "Герион спустит тебя к обманщикам. Если захочет.",
               "Все дороги ада выложены камнем с одним и тем же клеймом - узлом." } },

    { id = "muspelheim", name = "Муспельхейм: Огонь над Коцитом", levels = { 71, 80 }, biome = "muspelheim",
      enemies = { "fire_giant", "fire_imp", "frost_damned" }, elites = { "surtr_herald" },
      miniboss = "surtr", boss = "lucifer",
      -- финал: Люцифер лишь первый - за ним теневые правители Ордена Узла (по очереди)
      final_sequence = { "lucifer", "grey_cardinal", "knot_treasurer", "faceless_architect" },
      weather = { "heatwave", "ashfall", "frost_breath" }, towns = { 1 },
      -- последние уровни: пояса девятого круга (замёрзшее озеро в огненном мире)
      circles = { [76] = "Каина", [77] = "Антенора", [78] = "Птоломея", [79] = "Джудекка", [80] = "Джудекка: сердце Коцита" },
      lore = { "Муспельхейм горит снаружи. А в сердце - лёд, крепче любого огня.",
               "Люцифер вмёрз в озеро по грудь. Крылья его и морозят Коцит.",
               "Предателей держит лёд. Ниже - только он сам.",
               "Люцифер - только страж на виду. Смотри, кто стоит в тени за троном." } },
  },
}
