-- lua_content/bricks/items.lua
-- Кирпичи предметов: оружие, броня, расходники

return {
  -- Базовое оружие
  sword_base = {
    kind = "weapon",
    slot = "main_hand",
    base_stats = {
      damage_min = 5,
      damage_max = 8,
      attack_speed = 1.2,
      range = 1.5,
    },
    tags = { "melee", "slashing" },
    effects = {},
    rarity_weights = {
      common = 0.5,
      uncommon = 0.3,
      rare = 0.15,
      epic = 0.04,
      legendary = 0.01,
    },
  },

  axe_base = {
    kind = "weapon",
    slot = "main_hand",
    base_stats = {
      damage_min = 7,
      damage_max = 10,
      attack_speed = 0.9,
      range = 1.5,
    },
    tags = { "melee", "slashing", "heavy" },
    effects = {},
    rarity_weights = {
      common = 0.5,
      uncommon = 0.3,
      rare = 0.15,
      epic = 0.04,
      legendary = 0.01,
    },
  },

  staff_base = {
    kind = "weapon",
    slot = "two_hand",
    base_stats = {
      damage_min = 3,
      damage_max = 6,
      attack_speed = 1.0,
      range = 6.0,
      magic_power = 10,
    },
    tags = { "ranged", "magic" },
    effects = {},
    rarity_weights = {
      common = 0.5,
      uncommon = 0.3,
      rare = 0.15,
      epic = 0.04,
      legendary = 0.01,
    },
  },

  -- Броня
  cloth_armor_base = {
    kind = "armor",
    slot = "chest",
    base_stats = {
      defense = 2,
      magic_resist = 5,
      health_bonus = 10,
    },
    tags = { "light", "cloth" },
    effects = {},
    rarity_weights = {
      common = 0.6,
      uncommon = 0.25,
      rare = 0.10,
      epic = 0.04,
      legendary = 0.01,
    },
  },

  plate_armor_base = {
    kind = "armor",
    slot = "chest",
    base_stats = {
      defense = 15,
      magic_resist = 3,
      health_bonus = 50,
      movement_penalty = -0.2,
    },
    tags = { "heavy", "plate" },
    effects = {},
    rarity_weights = {
      common = 0.4,
      uncommon = 0.35,
      rare = 0.15,
      epic = 0.07,
      legendary = 0.03,
    },
  },

  -- Расходники
  health_potion = {
    kind = "consumable",
    slot = "inventory",
    effect = {
      type = "heal",
      value = 50,
      duration = 0,
    },
    tags = { "potion", "healing" },
    stack_size = 20,
    cooldown = 1.0,
  },

  mana_potion = {
    kind = "consumable",
    slot = "inventory",
    effect = {
      type = "restore_mana",
      value = 30,
      duration = 0,
    },
    tags = { "potion", "mana" },
    stack_size = 20,
    cooldown = 1.0,
  },

  strength_elixir = {
    kind = "consumable",
    slot = "inventory",
    effect = {
      type = "buff",
      stat = "strength",
      multiplier = 1.2,
      duration = 60.0,
    },
    tags = { "elixir", "buff" },
    stack_size = 5,
    cooldown = 5.0,
  },

  -- Энчанты
  fire_enchantment = {
    kind = "enchantment",
    effect = {
      type = "burn",
      damage_per_tick = 2,
      duration = 3.0,
      tick_interval = 0.5,
    },
    tags = { "fire", "dot" },
    incompatible_with = { "ice_enchantment", "frost_enchantment" },
  },

  ice_enchantment = {
    kind = "enchantment",
    effect = {
      type = "chill",
      slow_percent = 0.3,
      duration = 2.0,
    },
    tags = { "ice", "slow" },
    incompatible_with = { "fire_enchantment", "flame_enchantment" },
  },

  vampiric_enchantment = {
    kind = "enchantment",
    effect = {
      type = "lifesteal",
      percent = 0.15,
    },
    tags = { "vampiric", "sustain" },
    synergies = { "blade_enchantment" },
  },
}
