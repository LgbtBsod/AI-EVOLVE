# Инструкция по сборке мультиязычного проекта

## Структура проекта

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
├── glsl_shaders/           # GLSL шейдеры
└── MULTILANG_ARCHITECTURE.md  # Полная документация
```

## Шаг 1: Установка зависимостей

### Rust (для rust_core)
```bash
# Linux/Mac
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# Проверка
rustc --version
cargo --version
```

### Python зависимости
```bash
cd /workspace
pip install torch stable-baselines3 gymnasium numpy pandas pyarrow panda3d
```

### R (опционально, для аналитики)
```bash
# Ubuntu
sudo apt-get install r-base r-base-dev

# Пакеты R
R -e "install.packages(c('tidyverse', 'arrow', 'ggplot2'))"
```

## Шаг 2: Сборка Rust ядра

```bash
cd /workspace/rust_core

# Отладочная сборка
cargo build

# Релизная сборка (оптимизированная)
cargo build --release

# Сборка Python модуля
pip install maturin
maturin develop
```

## Шаг 3: Проверка Python слоя

```bash
cd /workspace

# Проверка импортов
python -c "from python_layer import GymWrapper; print('OK')"

# Запуск тестов
pytest python_layer/tests/ -v
```

## Шаг 4: Создание Lua контента

Пример создания кирпича предмета:

```lua
-- lua_content/bricks/items.lua
return {
  sword_base = {
    kind = "weapon",
    slot = "main_hand",
    base_stats = {
      damage_min = 5,
      damage_max = 8,
      attack_speed = 1.2,
    },
    tags = { "melee", "slashing" },
  }
}
```

## Шаг 5: Запуск обучения

```python
from python_layer import GymWrapper, PPOTrainer

# Создание среды
env = GymWrapper(seed=42)

# Обучение
trainer = PPOTrainer(env)
trainer.learn(total_timesteps=1_000_000)
trainer.save("checkpoint_001")
```

## Шаг 6: Аналитика в R

```bash
# Экспорт логов из Python
python tools/export_logs.py --output logs/session_001.parquet

# Запуск анализа
Rscript r_analytics/scripts/win_rate_curves.R logs/session_001/
```

## Тестирование

### Rust тесты
```bash
cd rust_core
cargo test
```

### Python тесты
```bash
pytest python_layer/ -v
```

### Интеграционные тесты
```bash
pytest tests/integration/ -v
```

## Производительность

### Бенчмарки Rust
```bash
cd rust_core
cargo bench
```

### Профилирование Python
```bash
python -m cProfile -o profile.stats main.py
snakeviz profile.stats
```

## Развертывание

### Docker контейнер
```dockerfile
FROM rust:1.75 as rust-builder
COPY rust_core /app/rust_core
RUN cd /app/rust_core && cargo build --release

FROM python:3.11-slim
COPY --from=rust-builder /app/rust_core/target/release/librust_core.so /usr/local/lib/
COPY python_layer /app/python_layer
RUN pip install torch stable-baselines3
```

## CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
name: CI

on: [push, pull_request]

jobs:
  test-rust:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions-rs/toolchain@v1
        with:
          toolchain: stable
      - run: cd rust_core && cargo test

  test-python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt
      - run: pytest python_layer/ -v

  build:
    needs: [test-rust, test-python]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: cargo build --release
      - run: pip install maturin && maturin develop
```

## Отладка

### Логирование Rust
```rust
use log::{info, debug, error};

info!("World generated: {:?}", world);
debug!("Entity count: {}", entities.len());
error!("Failed to load bricks: {}", err);
```

### Логирование Python
```python
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info(f"Episode reward: {total_reward}")
logger.debug(f"Observation shape: {obs['vector'].shape}")
```

## Миграция существующего кода

| Текущий модуль | Новый слой | Статус |
|---|---|---|
| `src/core/combat_mechanics.py` | `rust_core/simulation/` | ⏳ Ожидает |
| `src/core/cc_system.py` | `rust_core/simulation/` | ⏳ Ожидает |
| `src/ml_agents/` | `python_layer/l5_learning/` | ⏳ Ожидает |
| `config/*.json` | `lua_content/bricks/` | ⏳ Ожидает |

## Следующие шаги

1. ✅ Создать структуру директорий
2. ✅ Создать README для каждого слоя
3. ✅ Инициализировать Rust проект (Cargo.toml)
4. ✅ Создать stub-модули Rust
5. ✅ Создать базовые Python модули L4
6. ⏳ Реализовать ECS в Rust
7. ⏳ Перенести combat_mechanics в Rust
8. ⏳ Настроить PyO3 биндинги
9. ⏳ Создать тесты для каждого слоя
10. ⏳ Интегрировать с текущим кодом

## Поддержка

- Документация: `MULTILANG_ARCHITECTURE.md`
- Rust docs: `rust_core/README.md`
- Python docs: `python_layer/README.md`
- Lua docs: `lua_content/README.md`
- R docs: `r_analytics/README.md`
- GLSL docs: `glsl_shaders/README.md`
