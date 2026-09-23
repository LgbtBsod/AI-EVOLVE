# Python Layer (L7, L6, L5, L4)

## Назначение
Мозги (PyTorch), лицо (Panda3D), оркестрация, Gym-обёртка, обучение.

## Структура
```
python_layer/
├── __init__.py
├── l7_trainer/           # L7: Игрок-тренер (Panda3D)
│   ├── __init__.py
│   ├── scene_editor.py   # Изометрия, панели, спавн
│   ├── directive_ui.py   # Кнопки директив
│   ├── emotion_ui.py     # Модификаторы эмоций
│   ├── budget_manager.py # Бюджет челленджа
│   └── auto_balancer.py  # Автобаланс сложности
├── l6_curriculum/        # L6: Curriculum / Тренер
│   ├── __init__.py
│   ├── evaluator.py      # Оценка агента (win-rate, deaths)
│   ├── advisor.py        # Подсказки игроку
│   └── reward_tracker.py # Награда за прогресс
├── l5_learning/          # L5: Обучение (PyTorch)
│   ├── __init__.py
│   ├── ppo_trainer.py    # PPO из SB3
│   ├── es_trainer.py     # ES / CMA-ES
│   ├── selfplay.py       # Self-play + league
│   ├── opponent_model.py # Opponent modeling
│   └── checkpoint_mgr.py # Чекпоинты политик
├── l4_gym/               # L4: Gym-обёртка (Python ↔ Rust)
│   ├── __init__.py
│   ├── env_wrapper.py    # reset / step / step_batch
│   ├── observation.py    # Визуальный + векторный канал
│   ├── action_space.py   # Иерархический action space
│   └── reward_shaping.py # Reward функции
└── utils/
    ├── config_loader.py  # Загрузка конфигов
    └── logger.py         # Логирование в parquet
```

## Принципы
- **Оркестрация:** Вызывает Rust для симуляции, не лезет в SQLite напрямую
- **ML-изолированность:** PyTorch только в L5, не в симуляции
- **Рендер-отделённость:** Panda3D только читает снапшоты из Rust
- **Gym-стандарт:** Совместимость с OpenAI Gym API

## Зависимости
```
torch>=2.0
stable-baselines3>=2.0
panda3d>=1.10
gymnasium>=0.28
numpy>=1.24
pandas>=2.0
pyarrow>=12.0  # parquet
```

## Миграция существующего кода
| Текущий файл | Новый слой | Примечание |
|---|---|---|
| `src/core/game_core.py` | `l4_gym/env_wrapper.py` | Обёртка над Rust |
| `src/core/combat_mechanics.py` | `rust_core/simulation/` | Перенести в Rust |
| `src/core/cc_system.py` | `rust_core/simulation/` | Перенести в Rust |
| `src/ml_agents/` | `l5_learning/` | Рефакторинг под PPO |
| `src/ui/` | `l7_trainer/` | Интеграция с Panda3D |
| `src/plugins/` | Распределить | По функционалу |

## Следующие шаги
1. Создать структуру директорий
2. Выделить Gym-обёртку из текущего кода
3. Рефакторинг ML-агентов под SB3
4. Интеграция Panda3D рендера
