# Архитектура мультиязычного проекта

## Слои (Layers)

```
┌─────────────────────────────────────────────────────────────┐
│  L7. Игрок-тренер (Python + Panda3D)                        │  python_layer/l7_trainer/
│      - изометрия, панели, редактор сцены                    │
│      - спавн: враги, ловушки, сундуки, ландшафт             │
│      - директивы (кнопки), эмоции (модификаторы)            │
└──────────────────────────┬──────────────────────────────────┘
                           │ вызовы
┌──────────────────────────▼──────────────────────────────────┐
│  L6. Curriculum / Тренер (Python)                           │  python_layer/l6_curriculum/
│      - оценка текущего агента (win-rate, deaths, time)      │
│      - подсказки игроку, где ИИ проседает                   │
│      - награда игроку за прогресс агента                    │
└──────────────────────────┬──────────────────────────────────┘
                           │ вызовы
┌──────────────────────────▼──────────────────────────────────┐
│  L5. Обучение (Python + PyTorch)                            │  python_layer/l5_learning/
│      - PPO / ES / self-play                                 │
│      - батч-инференс для врагов в рантайме                  │
│      - чекпоинты политик персонажа и врагов                 │
└──────────────────────────┬──────────────────────────────────┘
                           │ вызовы
┌──────────────────────────▼──────────────────────────────────┐
│  L4. Gym-обёртка (Python ↔ Rust)                            │  python_layer/l4_gym/
│      - reset / step / step_batch                            │
│      - observation, reward, done                            │
│      - seed-контроль, domain randomization                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ FFI (PyO3)
┌──────────────────────────▼──────────────────────────────────┐
│  L3. Симуляция (Rust core, PyO3)                            │  rust_core/src/simulation/
│      - grid / navmesh, tick(dt), коллизии, FOV              │
│      - pathfinding (A*, flow field)                         │
│      - инвентарь, скиллы, эффекты (данные)                  │
│      - детерминизм, снапшоты, батч эпизодов                 │
└──────────────────────────┬──────────────────────────────────┘
                           │ загрузка
┌──────────────────────────▼──────────────────────────────────┐
│  L2. Генератор мира (Rust)                                  │  rust_core/src/generator/
│      - сид + кирпичи + правила → 5к сущностей               │
│      - 80 карт, биомы, сложность                            │
│      - детерминированный PRNG (rand_chacha)                 │
└──────────────────────────┬──────────────────────────────────┘
                           │ загрузка
┌──────────────────────────▼──────────────────────────────────┐
│  L1. Хранилище (Rust → SQLite)                              │  rust_core/src/storage/
│      - save_<uuid>.db на каждый сейв                        │
│      - meta, entities, world_state, progress                │
│      - версионирование генератора и кирпичей                │
└──────────────────────────┬──────────────────────────────────┘
                           │ загрузка
┌──────────────────────────▼──────────────────────────────────┐
│  L0. Контент (Lua через mlua)                               │  lua_content/
│      - кирпичи: свойства, эффекты, имена, формулы           │
│      - правила комбинации и валидации                       │
│      - моддинг без пересборки Rust                          │
└─────────────────────────────────────────────────────────────┘

Отдельные слои:
- R Analytics (r_analytics/) — аналитика логов (запускается после сессии)
- GLSL Shaders (glsl_shaders/) — шейдеры для Panda3D
```

## Правила зависимостей

### Сверху вниз (вызовы)
- **L7 → L6 → L5 → L4 → L3 → L2 → L1 → L0**
- Верхний слой вызывает нижний только через публичный API
- Нижний слой не знает о существовании верхнего

### Снизу вверх (данные)
- **L0 ← L1 ← L2 ← L3 ← L4 ← L5 ← L6 ← L7**
- Нижний слой возвращает только данные (структуры, снапшоты)
- Нижний слой не вызывает методы верхнего

### Изоляция по языкам
| Язык | Знает о | Не знает о |
|---|---|---|
| **Python** | Rust (через PyO3), PyTorch, Panda3D | Lua, SQLite напрямую |
| **Rust** | Lua (через mlua), SQLite | Python, PyTorch, Panda3D |
| **Lua** | Ничего (песочница) | Rust, Python, файлы |
| **R** | Parquet файлы | Игра в рантайме |
| **GLSL** | Uniforms от Python | Логика игры |

## Границы слоёв (Boundaries)

### L4 ↔ L3 (Python ↔ Rust)
```python
# python_layer/l4_gym/env_wrapper.py
from rust_core import SimulationEnv  # PyO3 импорт

class GymWrapper:
    def __init__(self, seed):
        self.env = SimulationEnv.new(seed)  # Rust конструктор
        
    def step(self, actions):
        obs, reward, done, info = self.env.step_batch(actions)
        return self._convert_obs(obs), reward, done, info
```

```rust
// rust_core/src/ffi/gym_env.rs
#[pyclass]
pub struct SimulationEnv {
    world: World,
    state: State,
}

#[pymethods]
impl SimulationEnv {
    #[new]
    fn new(seed: u64) -> Self { ... }
    
    fn step_batch(&mut self, actions: Vec<Action>) -> PyResult<(Vec<Obs>, Vec<f32>, Vec<bool>, Vec<Info>)> {
        // Детерминированный шаг, отпускание GIL
        py.allow_threads(|| {
            self.tick()
        })
    }
}
```

### L3 ↔ L0 (Rust ↔ Lua)
```rust
// rust_core/src/generator/bricks.rs
use mlua::Lua;

pub fn load_bricks(lua_path: &str) -> BricksConfig {
    let lua = Lua::new();
    let globals = lua.load_file(lua_path)?;
    let table: Table = globals.call(())?;
    
    // Парсинг Lua таблиц в Rust структуры
    BricksConfig::from_lua_table(table)
}
```

```lua
-- lua_content/bricks/items.lua
return {
  sword_base = {
    kind = "weapon",
    base_stats = { damage_min = 5, damage_max = 8 },
  }
}
```

### L5 ↔ L4 (PyTorch ↔ Gym)
```python
# python_layer/l5_learning/ppo_trainer.py
from stable_baselines3 import PPO
from l4_gym import GymWrapper

env = GymWrapper(seed=42)
model = PPO("MultiInputPolicy", env, verbose=1)
model.learn(total_timesteps=1_000_000)
model.save("checkpoint_001")
```

## Миграция существующего кода

### Фаза 1: Подготовка (неделя 1)
- [ ] Создать структуру директорий
- [ ] Настроить Rust проект (Cargo.toml, PyO3)
- [ ] Перенести конфиги в Lua
- [ ] Настроить CI/CD для мультиязычной сборки

### Фаза 2: Ядро (недели 2-3)
- [ ] Реализовать ECS в Rust
- [ ] Перенести combat_mechanics.py в Rust
- [ ] Перенести cc_system.py в Rust
- [ ] Настроить PyO3 биндинги
- [ ] Tests: Rust unit tests + Python integration tests

### Фаза 3: Gym обёртка (неделя 4)
- [ ] Реализовать reset() / step() / step_batch()
- [ ] Observation space (визуальный + векторный)
- [ ] Action space (иерархический)
- [ ] Reward shaping функции
- [ ] Tests: Gym compatibility tests

### Фаза 4: Обучение (недели 5-6)
- [ ] Интеграция SB3 PPO
- [ ] Чекпоинт менеджер
- [ ] Батч-инференс для врагов
- [ ] Self-play каркас
- [ ] Tests: Training convergence tests

### Фаза 5: Рендер (недели 7-8)
- [ ] Panda3D изометрия
- [ ] GLSL шейдеры
- [ ] UI тренера (спавн, директивы, эмоции)
- [ ] Автобалансер
- [ ] Tests: Visual regression tests

### Фаза 6: Аналитика (неделя 9)
- [ ] Экспорт логов в parquet
- [ ] R скрипты для анализа
- [ ] Графики win-rate, heatmap смертей
- [ ] Автоматические отчёты
- [ ] Tests: Data validation tests

## Структура проекта (итоговая)

```
/workspace/
├── rust_core/              # L3, L2, L1: Rust ядро
│   ├── Cargo.toml
│   └── src/
├── python_layer/           # L7, L6, L5, L4: Python слой
│   ├── l7_trainer/
│   ├── l6_curriculum/
│   ├── l5_learning/
│   ├── l4_gym/
│   └── utils/
├── lua_content/            # L0: Lua контент
│   ├── bricks/
│   ├── rules/
│   └── formulas/
├── r_analytics/            # R аналитика
│   ├── scripts/
│   └── libs/
├── glsl_shaders/           # GLSL шейдеры
│   ├── isometric/
│   ├── effects/
│   └── postprocess/
├── config/                 # Общие конфиги (JSON, TOML)
├── saves/                  # SQLite сейвы
├── logs/                   # Parquet логи
└── tests/                  # Интеграционные тесты
```

## Принципы (SSOT, SRP, DRY, SOLID)

### SSOT (Single Source of Truth)
- **Мир:** Rust `World` структура — единственный источник истины
- **Сейв:** SQLite файл — единственное хранилище состояния
- **Формулы:** Lua файлы — единственное место определения правил
- **Чекпоинты:** PyTorch `.zip` файлы — единственное место весов

### SRP (Single Responsibility Principle)
- **Rust:** Только симуляция, генерация, хранение
- **Python:** Только обучение, рендер, оркестрация
- **Lua:** Только данные правил
- **R:** Только аналитика
- **GLSL:** Только визуализация

### DRY (Don't Repeat Yourself)
- Формулы только в Lua, не дублировать в Rust/Python
- Логика боя только в Rust, не дублировать в Python
- Шейдеры только в GLSL, не писать логику рендера на Python

### SOLID
- **S (SRP):** См. выше
- **O (Open/Closed):** Lua кирпичи расширяются без изменения Rust
- **L (Liskov):** Gym wrapper совместим с SB3 интерфейсом
- **I (Interface Segregation):** Узкие PyO3 интерфейсы для каждого слоя
- **D (Dependency Inversion):** Python зависит от абстракции Gym, не от Rust напрямую

## Следующие шаги

1. **Создать структуру директорий** ✅
2. **Инициализировать Rust проект**
   ```bash
   cd rust_core && cargo init --lib
   ```
3. **Добавить зависимости в Cargo.toml**
   ```toml
   [dependencies]
   pyo3 = { version = "0.20", features = ["extension-module"] }
   mlua = { version = "0.9", features = ["lua54"] }
   rusqlite = { version = "0.30", features = ["bundled"] }
   rand_chacha = "0.3"
   nalgebra = "0.32"
   serde = { version = "1.0", features = ["derive"] }
   ```
4. **Перенести первые модули в Rust** (combat_mechanics, cc_system)
5. **Настроить PyO3 биндинги**
6. **Создать тесты для каждого слоя**
