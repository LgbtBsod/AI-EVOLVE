-- lua_content/formulas/damage_curves.lua
-- Формулы урона и кривые прогрессии

return {
  -- Линейный рост урона оружия
  linear_damage = function(base_damage, level)
    return base_damage * (1 + 0.1 * (level - 1))
  end,

  -- Экспоненциальный рост для боссов
  exponential_damage = function(base_damage, level)
    return base_damage * math.pow(1.05, level - 1)
  end,

  -- S-образная кривая для баланса
  sigmoid_damage = function(base_damage, level, midpoint, steepness)
    midpoint = midpoint or 40
    steepness = steepness or 0.1
    local x = (level - midpoint) * steepness
    local sigmoid = 1 / (1 + math.exp(-x))
    return base_damage * (0.5 + sigmoid)
  end,

  -- Урон с уменьшающейся отдачей
  diminishing_damage = function(base_damage, level)
    return base_damage * math.sqrt(level)
  end,

  -- Множитель редкости
  rarity_multipliers = {
    common = 1.0,
    uncommon = 1.3,
    rare = 1.7,
    epic = 2.3,
    legendary = 3.2,
  },

  -- Множитель качества
  quality_multipliers = {
    normal = 1.0,
    superior = 1.1,
    masterwork = 1.25,
    artifact = 1.5,
  },

  -- Формула критического урона
  crit_damage = function(base_damage, crit_multiplier, crit_chance)
    return base_damage * (1 + (crit_multiplier - 1) * crit_chance)
  end,

  -- Формула защиты (процент снижения урона)
  damage_reduction = function(armor, enemy_level)
    local armor_factor = armor / (armor + 100 + 10 * enemy_level)
    return math.min(armor_factor, 0.85)  -- Максимум 85% снижение
  end,

  -- Эффективность элемента против типа врага
  elemental_effectiveness = {
    fire = { ice = 2.0, water = 0.5, nature = 1.2 },
    ice = { fire = 0.5, water = 1.0, nature = 1.5 },
    water = { fire = 1.5, ice = 1.0, lightning = 0.5 },
    lightning = { water = 2.0, earth = 1.0, air = 0.5 },
    earth = { lightning = 1.0, fire = 0.8, air = 1.2 },
    nature = { ice = 0.5, fire = 0.8, water = 1.3 },
    holy = { unholy = 2.0, dark = 1.5 },
    unholy = { holy = 0.5, dark = 1.2 },
  },

  -- Расчет итогового урона
  calculate_final_damage = function(params)
    local base = params.base_damage or 0
    local level = params.level or 1
    local rarity = params.rarity or "common"
    local quality = params.quality or "normal"
    local element = params.element
    local enemy_type = params.enemy_type
    local armor = params.enemy_armor or 0
    local enemy_level = params.enemy_level or 1

    -- Применяем кривую уровня
    local damage = linear_damage(base, level)

    -- Применяем множители
    damage = damage * rarity_multipliers[rarity]
    damage = damage * quality_multipliers[quality]

    -- Элементальная эффективность
    if element and enemy_type and elemental_effectiveness[element] then
      local eff = elemental_effectiveness[element][enemy_type] or 1.0
      damage = damage * eff
    end

    -- Защита врага
    local reduction = damage_reduction(armor, enemy_level)
    damage = damage * (1 - reduction)

    return math.floor(damage * 100) / 100
  end,
}
