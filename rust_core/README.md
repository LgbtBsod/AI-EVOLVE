# Rust Core Layer (L3, L2, L1)

## Назначение
Ядро симуляции, генерация мира, работа с SQLite, pathfinding, батч-степпинг.

## Структура
```
rust_core/
├── Cargo.toml              # Зависимости: pyo3, rusqlite, rand_chacha, nalgebra
├── src/
│   ├── lib.rs              # PyO3 экспорты
│   ├── simulation/         # L3: Симуляция мира
│   │   ├── mod.rs
│   │   ├── grid.rs         # Тайловая сетка, навигация
│   │   ├── entities.rs     # ECS компоненты
│   │   ├── tick.rs         # Детерминированный шаг мира
│   │   ├── pathfinding.rs  # A*, flow field
│   │   └── batch.rs        # step_batch для обучения
│   ├── generator/          # L2: Генератор мира
│   │   ├── mod.rs
│   │   ├── world_gen.rs    # Процедурная генерация 80 карт
│   │   ├── prng.rs         # rand_chacha с сидами
│   │   └── bricks.rs       # Загрузка кирпичей из Lua
│   ├── storage/            # L1: Хранилище SQLite
│   │   ├── mod.rs
│   │   ├── database.rs     # rusqlite обёртка
│   │   ├── schema.rs       # SQL схема
│   │   └── snapshot.rs     # Сериализация состояния
│   └── ffi/                # Python ↔ Rust интерфейс
│       ├── mod.rs
│       ├── gym_env.rs      # Gym-обёрка (reset, step)
│       └── types.rs        # Общие типы
├── tests/                  # Rust тесты
└── build.rs                # Сборка PyO3
```

## Принципы
- **Детерминизм:** Один сид = один мир на всех ОС
- **Без Python:** Не знает о PyTorch, рендере, Panda3D
- **GIL-free:** Батч-операции отпускают GIL
- **ECS:** Массивы компонентов, не ООП

## API для Python
```python
# Импорт через PyO3
from rust_core import WorldGenerator, SimulationEnv, Database

gen = WorldGenerator(seed=42, version="1.0.0")
world = gen.generate(bricks_config)

env = SimulationEnv(world)
obs, reward, done, info = env.step(actions)

db = Database("save_uuid.db")
db.save_state(env.snapshot())
```

## Следующие шаги
1. Инициализировать Rust проект: `cargo init --lib rust_core`
2. Добавить зависимости в Cargo.toml
3. Реализовать базовую структуру ECS
4. Настроить PyO3 биндинги
