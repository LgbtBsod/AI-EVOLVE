-- lua_content/rules/combinations.lua
-- Правила комбинации и валидации сущностей

return {
  -- Правила для оружия
  weapon = {
    required_tags = { "weapon" },
    allowed_effects_max = 2,
    stat_curve = "linear_damage",
    incompatible_combos = {
      { "fire", "ice" },
      { "holy", "unholy" },
    },
  },

  -- Правила для брони
  armor = {
    required_tags = { "armor" },
    allowed_effects_max = 1,
    stat_curve = "diminishing_defense",
    incompatible_combos = {
      { "light", "heavy" },
    },
  },

  -- Правила для расходников
  consumable = {
    required_tags = { "consumable" },
    allowed_effects_max = 1,
    stack_size_max = 99,
  },

  -- Правила для энчантов
  enchantment = {
    required_tags = { "enchantment" },
    max_per_item = 3,
    check_incompatibilities = true,
  },

  -- Глобальная валидация
  validate = function(entity)
    -- Проверка на несовместимые теги
    if entity.tags then
      local has_fire = false
      local has_ice = false
      
      for _, tag in ipairs(entity.tags) do
        if tag == "fire" then has_fire = true end
        if tag == "ice" then has_ice = true end
      end
      
      if has_fire and has_ice then
        return false, "Fire and ice are incompatible"
      end
    end
    
    -- Проверка на дубликаты эффектов
    if entity.effects and #entity.effects > 0 then
      local effect_names = {}
      for _, effect in ipairs(entity.effects) do
        if effect.type then
          if effect_names[effect.type] then
            return false, "Duplicate effect: " .. effect.type
          end
          effect_names[effect.type] = true
        end
      end
    end
    
    return true
  end,

  -- Синергии между эффектами
  synergies = {
    {
      tags = { "vampiric", "slashing" },
      bonus = { lifesteal_percent = 0.05 },
      description = "Vampiric blade: +5% lifesteal",
    },
    {
      tags = { "fire", "oil" },
      bonus = { damage_multiplier = 1.5 },
      description = "Fire on oil: +50% damage",
    },
    {
      tags = { "ice", "water" },
      bonus = { freeze_chance = 0.1 },
      description = "Ice on water: 10% freeze chance",
    },
  },

  -- Пороги тиров
  tier_gates = {
    tier_1 = { max_item_level = 10, allowed_rarities = { "common", "uncommon" } },
    tier_2 = { max_item_level = 30, allowed_rarities = { "common", "uncommon", "rare" } },
    tier_3 = { max_item_level = 50, allowed_rarities = { "uncommon", "rare", "epic" } },
    tier_4 = { max_item_level = 80, allowed_rarities = { "rare", "epic", "legendary" } },
  },
}
