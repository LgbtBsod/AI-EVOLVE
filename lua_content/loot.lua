-- lua_content/loot.lua
-- Добыча: что лежит в сундуках, что враги носят с собой (и умеют этим
-- пользоваться: пьют зелья, надевают оружие) и что выпадает при смерти.
--   gold      = { min, max }
--   rolls     - сколько случайных предметов, drop_chance - шанс каждого
--   kinds     - какие виды предметов могут выпасть (items.kind)
--   max_rarity- потолок редкости
--   carries   - предметы, с которыми враг появляется (в сумке)
--   equip     - что враг надевает: { weapon = { варианты }, armor = { ... } }
return {
  chest = { gold = { 10, 40 }, rolls = 2, drop_chance = 1.0,
            kinds = { "equipment", "consumable", "map", "artifact" }, max_rarity = "epic" },
  enemies = {
    basic  = { gold = { 1, 6 },  rolls = 1, drop_chance = 0.15, kinds = { "consumable" }, max_rarity = "common" },
    strong = { gold = { 4, 12 }, rolls = 1, drop_chance = 0.35, kinds = { "consumable", "equipment" }, max_rarity = "rare",
               carries = { "health_potion" } },
    elite  = { gold = { 10, 30 }, rolls = 2, drop_chance = 0.8, kinds = { "consumable", "equipment", "map" }, max_rarity = "epic",
               carries = { "health_potion", "health_potion", "rage_tonic" },
               equip = { weapon = { "iron_sword", "venom_dagger", "executioner_axe" }, armor = { "leather_armor", "chainmail" } } },
    boss   = { gold = { 60, 150 }, rolls = 3, drop_chance = 1.0, kinds = { "equipment", "artifact", "map" }, max_rarity = "legendary",
               carries = { "greater_health_potion", "greater_health_potion", "rage_tonic" },
               equip = { weapon = { "stormcaller", "executioner_axe" }, armor = { "mantle_of_thorns" },
                         amulet = { "sorrow_of_berserk", "amulet_of_vigor" } } },
  },
}
