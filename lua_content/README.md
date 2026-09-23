# Lua Content Layer (L0)

## Назначение
Правила мира, контент, моддинг. Геймдизайнер крутит без пересборки Rust.

## Структура
```
lua_content/
├── bricks/               # Кирпичи: свойства сущностей
│   ├── items.lua         # Предметы: оружие, броня, расходники
│   ├── skills.lua        # Скиллы: активные, пассивные, комбо
│   ├── enemies.lua       # Враги: типы, мутации, экипировка
│   ├── traps.lua         # Ловушки: триггеры, эффекты
│   └── quests.lua        # Квесты: условия, награды
├── rules/                # Правила комбинации и валидации
│   ├── combinations.lua  # "меч = оружие + урон + 1-2 эффекта"
│   ├── compatibility.lua # "ледяной ≠ огненный"
│   ├── tier_gates.lua    # "эпик не на карте 1"
│   └── synergies.lua     # "вампирский + клинок → +lifesteal"
├── formulas/             # Формулы и кривые
│   ├── damage_curves.lua # Кривая урона по уровням
│   ├── rarity_mults.lua  # Множители редкости
│   └── stat_formulas.lua # Формулы статов
├── names/                # Генерация имён
│   ├── prefixes.lua      # Префиксы ("Огненный", "Ледяной")
│   ├── roots.lua         # Корни ("Клинок", "Молот")
│   └── suffixes.lua      # Суффиксы ("+1", "Мастера")
└── config.lua            # Общий конфиг для всех модулей
```

## Пример: кирпич предмета
```lua
-- bricks/items.lua
return {
  sword_base = {
    kind = "weapon",
    slot = "main_hand",
    base_stats = {
      damage_min = 5,
      damage_max = 8,
      attack_speed = 1.2,
    },
    tags = { "melee", " slashing" },
    effects = {},
    rarity_weights = {
      common = 0.5,
      uncommon = 0.3,
      rare = 0.15,
      epic = 0.04,
      legendary = 0.01,
    },
  },
  
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
}
```

## Пример: правило комбинации
```lua
-- rules/combinations.lua
return {
  weapon = {
    required_tags = { "weapon" },
    allowed_effects_max = 2,
    stat_curve = "linear_damage",
  },
  
  armor = {
    required_tags = { "armor" },
    allowed_effects_max = 1,
    stat_curve = "diminishing_defense",
  },
  
  -- Валидация после генерации
  validate = function(entity)
    if entity.tags:contains("fire") and entity.tags:contains("ice") then
      return false, "Fire and ice are incompatible"
    end
    return true
  end,
}
```

## Интеграция с Rust
Rust загружает Lua через `mlua` или `rsgwasm-lua`:
```rust
// rust_core/src/generator/bricks.rs
use mlua::{Lua, Result};

pub fn load_bricks(lua_path: &str) -> BricksConfig {
    let lua = Lua::new();
    let globals = lua.load_file(lua_path);
    // Парсинг таблиц в Rust структуры
}
```

## Принципы
- **Безопасная песочница:** Lua не имеет доступа к файловой системе
- **Горячая перезагрузка:** Можно менять без рестарта игры
- **Валидация:** Rust проверяет сгенерированные сущности
- **Моддинг:** Игроки могут добавлять свои кирпичи

## Следующие шаги
1. Создать структуру директорий
2. Перенести текущие JSON конфиги в Lua
3. Настроить загрузчик Lua в Rust (mlua)
4. Добавить валидацию правил
