# 🎮 Training Room System - Complete Architecture

**Version:** 3.0 (Rust + Lua + Python + Flet UI)  
**Date:** 2026-09-23  
**Status:** ✅ Ready for Compilation & Testing

---

## 📐 Архитектурные Слои

```
┌─────────────────────────────────────────────────────────────┐
│                    L10: Web UI (Flet)                       │
│  - Visual Item Builder                                      │
│  - Training Room Controller                                 │
│  - Real-time Simulation Dashboard                           │
└─────────────────────────────────────────────────────────────┘
                            ↓ exports JSON/Lua
┌─────────────────────────────────────────────────────────────┐
│                 L9: Python Orchestration                    │
│  - Effect Manager                                           │
│  - CAS Engine V2 (Conditional Activation)                   │
│  - Training Room Python API                                 │
└─────────────────────────────────────────────────────────────┘
                            ↓ FFI calls
┌─────────────────────────────────────────────────────────────┐
│                  L1-L3: Rust Core Engine                    │
│  - TrainingRoomEngine (high-performance simulation)         │
│  - EffectContract deserialization                           │
│  - CAS trigger evaluation                                   │
│  - Entity state management                                  │
└─────────────────────────────────────────────────────────────┘
                            ↓ config loading
┌─────────────────────────────────────────────────────────────┐
│                L0: Lua Content Layer                        │
│  - Item definitions (sorrow_of_berserk.lua)                 │
│  - Effect contracts                                         │
│  - Mannequin/Bot configurations                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 Ключевые Компоненты

### 1. **Effect Contract** (Универсальный контракт)

```rust
pub struct EffectContract {
    pub id: String,              // UUID4 для уникальности
    pub name: String,
    pub effect_type: String,     // "buff", "debuff", "triggered", etc.
    
    // CAS подписки
    pub trigger_conditions: Vec<TriggerCondition>,
    
    // Модификаторы статов
    pub stats_modifiers: HashMap<String, f64>,
    
    // Тайминги
    pub duration: Option<f64>,
    pub cooldown: Option<f64>,
    pub max_stacks: Option<i32>,
    
    // Стоимость
    pub cost: Option<EffectCost>,
    
    // Спец-флаги
    pub is_cost_must_be_below_zero: bool,  // Может ли убить
    pub grants_iframe: bool,
    pub iframe_duration: Option<f64>,
    
    // Скалирование
    pub scaling_per_missing_percent: Option<ScalingConfig>,
}
```

### 2. **Sorrow of Berserk - Полная Спецификация**

| Эффект | Тип | Триггер | Стоимость | Особенности |
|--------|-----|---------|-----------|-------------|
| **Lost My Self** | Triggered Buff | HP < 40% | Нет | Скалирование 2x каждые 10% missing HP |
| **Blood Cost** | Passive Attack | Всегда | 0.5% HP → 1.5% dmg | `can_kill: false` (HP stops at 1) |
| **Safety Net** | Reactive Shield | cost > current_hp | Нет | HP→1, iframe 5s, cooldown 30s |
| **Low HP Sustain** | Passive Buff | HP < 40% | Нет | +20 HP regen, +5% vamp |

#### Таблица Скалирования Blood Cost:

| HP % | Cost | Damage | Trigger Safety Net? |
|------|------|--------|---------------------|
| 50%  | 0.5% | 1.5%   | ❌ No               |
| 35%  | 0.5% | 1.5%   | ❌ No               |
| 25%  | 1.0% | 3.0%   | ❌ No               |
| 15%  | 1.5% | 4.5%   | ❌ No               |
| 5%   | 2.0% | 6.0%   | ❌ No               |
| **1%**  | **2.0%** | **6.0%**   | **🛡️ YES! (HP→1)**  |

---

## 🚀 Запуск Системы

### Шаг 1: Компиляция Rust модуля

```bash
cd /workspace/rust_core

# Добавить зависимости в Cargo.toml:
# [dependencies]
# pyo3 = { version = "0.20", features = ["extension-module"] }
# serde = { version = "1.0", features = ["derive"] }
# serde_json = "1.0"
# uuid = { version = "1.0", features = ["v4"] }

cargo build --release
```

### Шаг 2: Установка Python зависимостей

```bash
pip install flet pyo3 luaparser uuid
```

### Шаг 3: Запуск Flet UI

```bash
python python_layer/l10_ui/flet_app/training_room_ui.py
# Откроется в браузере: http://localhost:8550
```

### Шаг 4: Создание предмета через UI

1. Ввести название эффекта (e.g., "Lost My Self")
2. Выбрать тип: `triggered_buff`
3. Добавить триггер: `hp_percent_lt < 40%`
4. Добавить стат модификаторы:
   - `strength_percent`: 20
   - `crit_rate_percent`: 5
   - и т.д.
5. Настроить стоимость (если есть):
   - HP Cost: 0.5%
   - Can Kill: ☐ (unchecked)
6. Спец-флаги:
   - Grants Iframe: ☑ (если нужен щит)
   - Iframe Duration: 5.0 sec
7. Нажать **"🔄 Generate JSON"**
8. Нажать **"💾 Export to Lua"** → сохранится в `/workspace/tools/flet_builds/`

### Шаг 5: Запуск симуляции

```python
from rust_core.training_room import TrainingRoomEngine
import json

engine = TrainingRoomEngine()

# Загрузить эффект из Lua/JSON
with open('tools/flet_builds/item_20260923_120000.lua') as f:
    # Parse Lua to JSON (use luaparser)
    effect_json = json.dumps(parsed_lua)

engine.register_effect(effect_json)

# Создать сущность
entity_config = json.dumps({
    "id": "test_bot_1",
    "entity_type": "immortal_bot",
    "max_hp": 10000,
    "current_hp": 3500,  # 35% HP for trigger
    "is_immortal": True,
})
engine.create_entity(entity_config)

# Запустить симуляцию на 10 секунд
result = engine.simulate(duration=10.0, tick_rate=0.1)

print(f"DPS: {result.dps:.2f}")
print(f"Triggers: {len(result.effect_triggers)}")
print(f"Iframe uptime: {result.iframe_uptime_percent:.1f}%")
```

---

## 🧪 Тестирование

### Unit Tests (Rust)

```rust
#[cfg(test)]
mod tests {
    use super::*;
    
    #[test]
    fn test_sorrow_of_berserk_registration() {
        let mut engine = TrainingRoomEngine::new();
        let effect_json = include_str!("../../lua_content/items/contracts/sorrow_of_berserk.json");
        
        let result = engine.register_effect(effect_json);
        assert!(result.is_ok());
    }
    
    #[test]
    fn test_cas_trigger_hp_threshold() {
        let entity = SimulationEntity {
            current_hp: 3500.0,
            max_hp: 10000.0,
            ..Default::default()
        };
        
        let effect = EffectContract {
            trigger_conditions: vec![
                TriggerCondition {
                    condition_type: "hp_percent_lt".to_string(),
                    threshold: 40.0,
                    ..Default::default()
                }
            ],
            ..Default::default()
        };
        
        let engine = TrainingRoomEngine::new();
        assert!(engine.check_cas_trigger(&entity, &effect));
    }
    
    #[test]
    fn test_cost_cannot_kill() {
        // Verify HP stops at 1 when can_kill=false
    }
    
    #[test]
    fn test_iframe_extension_on_kill() {
        // Verify iframe extends by 5s on kill
    }
}
```

### Integration Tests (Python)

```bash
pytest tests/test_training_room_rust.py -v
pytest tests/test_cas_engine_v2.py -v
pytest tests/test_flet_ui.py -v
```

---

## 📁 Структура Файлов

```
/workspace/
├── rust_core/
│   ├── src/
│   │   ├── training_room/
│   │   │   └── mod.rs          # ✅ Rust Engine (288 строк)
│   │   └── ffi/mod.rs          # PyO3 bindings
│   └── Cargo.toml              # Обновить зависимости
│
├── lua_content/
│   └── items/contracts/
│       └── sorrow_of_berserk.lua  # ✅ Полный контракт (201 строка)
│
├── python_layer/
│   └── l10_ui/
│       └── flet_app/
│           └── training_room_ui.py  # ✅ Flet UI (370 строк)
│
├── tools/
│   └── flet_builds/            # Экспортированные предметы
│
└── docs/
    └── TRAINING_ROOM_V3.md     # ✅ Эта документация
```

---

## 🎯 Преимущества Архитектуры

| Принцип | Реализация |
|---------|------------|
| **SOLID** | Каждый эффект - независимый контракт |
| **DRY** | Переиспользование CAS Engine для всех предметов |
| **Мультиязычность** | Rust (скорость), Lua (конфиги), Python (оркестрация), Flet (UI) |
| **SRP** | Effect Manager управляет эффектами, CAS только триггерит |
| **Token Optimization** | Агрегированные результаты вместо полных логов |

---

## 🔮 Roadmap

1. ✅ **Effect Contracts** - Универсальная структура завершена
2. ✅ **Sorrow of Berserk** - Полный пример реализован
3. ✅ **Flet UI** - Визуальный билдер готов
4. ⏳ **Rust Compilation** - Требует сборки
5. ⏳ **Integration Tests** - Ожидает компиляции
6. ⏳ **Dev Probe Integration** - Авто-запуск при изменениях кода

---

*Документ создан: 2026-09-23*  
*Следующий шаг: `cargo build --release` и запуск тестов*
