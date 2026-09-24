-- Training Room Mannequin Configurations
-- Lua конфигурация для манекенов и тест-сценариев

-- ============================================================================
-- MANNEQUIN TYPES
-- ============================================================================

mannequins = {
    -- Стандартный манекен без сопротивлений
    dummy = {
        name = "Target Dummy",
        type = "dummy",
        max_hp = 100000,
        defense = 0,
        resistances = {},
        dodge_chance = 0,
        crit_resistance = 0,
        special_abilities = {}
    },
    
    -- Танк с высокой защитой
    tank = {
        name = "Tank Bot",
        type = "tank",
        max_hp = 50000,
        defense = 500,
        resistances = {
            physical = 20,
            fire = 10,
            ice = 10
        },
        dodge_chance = 5,
        crit_resistance = 30,
        special_abilities = {"damage_reflect"}
    },
    
    -- Стеклянная пушка
    glass_cannon = {
        name = "Glass Cannon",
        type = "glass_cannon",
        max_hp = 20000,
        defense = 0,
        resistances = {},
        dodge_chance = 0,
        crit_resistance = 0,
        special_abilities = {"vulnerable"}
    },
    
    -- Босс для длительных тестов
    boss = {
        name = "Raid Boss",
        type = "boss",
        max_hp = 500000,
        defense = 1000,
        resistances = {
            physical = 30,
            fire = 50,
            ice = 50,
            lightning = 50,
            void = 20
        },
        dodge_chance = 10,
        crit_resistance = 50,
        special_abilities = {"phase_shift", "enrage", "cleave"}
    }
}

-- ============================================================================
-- TEST SCENARIOS
-- ============================================================================

scenarios = {
    -- Быстрый DPS тест
    quick_dps = {
        name = "Quick DPS Check",
        description = "10-second DPS measurement",
        duration_seconds = 10,
        attacks_per_second = 1.0,
        enable_crits = true,
        enable_specials = true,
        log_every_hit = false
    },
    
    -- Длительный тест на выносливость
    endurance = {
        name = "Endurance Test",
        description = "60-second sustained DPS with resource management",
        duration_seconds = 60,
        attacks_per_second = 1.5,
        enable_crits = true,
        enable_specials = true,
        log_every_hit = false
    },
    
    -- Тест爆发 урона (burst damage)
    burst = {
        name = "Burst Damage Test",
        description = "5-second all-in burst rotation",
        duration_seconds = 5,
        attacks_per_second = 3.0,
        enable_crits = true,
        enable_specials = true,
        log_every_hit = true
    },
    
    -- Сравнение предметов
    item_comparison = {
        name = "Item Comparison",
        description = "Compare different item sets",
        duration_seconds = 30,
        attacks_per_second = 1.0,
        enable_crits = true,
        enable_specials = true,
        log_every_hit = false,
        compare_items = {"set_a", "set_b", "set_c"}
    }
}

-- ============================================================================
-- ITEM SETS FOR TESTING
-- ============================================================================

item_sets = {
    -- Сет для критического урона
    crit_build = {
        name = "Crit Master",
        items = {
            {id = "bane_necklace", slot = "neck"},
            {id = "crit_ring_1", slot = "ring1"},
            {id = "crit_ring_2", slot = "ring2"}
        },
        expected_stats = {
            crit_chance = 75,
            crit_damage = 200,
            attack_speed = 40
        }
    },
    
    -- Сет для выживания
    survival_build = {
        name = "Immortal",
        items = {
            {id = "sorrow_chest", slot = "chest"},
            {id = "armor_boots", slot = "boots"},
            {id = "defense_shield", slot = "offhand"}
        },
        expected_stats = {
            max_hp = 5000,
            defense = 800,
            vampirism = 30
        }
    },
    
    -- Гибридный сет
    hybrid_build = {
        name = "Balanced Warrior",
        items = {
            {id = "bane_necklace", slot = "neck"},
            {id = "sorrow_chest", slot = "chest"},
            {id = "balanced_sword", slot = "mainhand"}
        },
        expected_stats = {
            crit_chance = 40,
            attack_power = 150,
            max_hp = 3000
        }
    }
}

-- ============================================================================
-- THRESHOLDS & ALERTS
-- ============================================================================

thresholds = {
    -- Минимальный приемлемый DPS
    min_dps = {
        early_game = 100,
        mid_game = 500,
        late_game = 2000,
        endgame = 5000
    },
    
    -- Целевые показатели крита
    crit_targets = {
        minimum = 30,      -- Ниже - плохо
        optimal = 60,      -- Цель
        cap = 100          -- Максимум
    },
    
    -- Предупреждения
    alerts = {
        low_dps = "DPS ниже ожидаемого - проверьте ротацию",
        no_crits = "Криты не происходят - проверьте шанс крита",
        resource_issue = "Проблемы с ресурсами - не хватает маны/ярости",
        death_detected = "Персонаж умер во время теста"
    }
}

-- ============================================================================
-- EXPORT HELPER
-- ============================================================================

function get_mannequin(name)
    return mannequins[name] or mannequins.dummy
end

function get_scenario(name)
    return scenarios[name] or scenarios.quick_dps
end

function get_item_set(name)
    return item_sets[name]
end

print("Training Room Lua config loaded successfully")
