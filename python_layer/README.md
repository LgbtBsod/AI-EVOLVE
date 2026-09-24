# Python Layer - Мультиязычная архитектура

## Структура слоёв

```
python_layer/
├── l4_gym/              # Gym-обёртка (Python ↔ Rust FFI)
│   ├── __init__.py
│   ├── env_wrapper.py   # Gym интерфейс к Rust симуляции
│   ├── observation.py   # Пространство обсерваций
│   ├── action_space.py  # Пространство действий
│   └── reward_shaping.py # Функции наград
│
├── l5_training/         # Обучение (PyTorch + SB3)
│   ├── __init__.py
│   ├── ppo_trainer.py   # PPO тренер с мониторингом
│   ├── checkpoint_manager.py  # Управление чекпоинтами
│   ├── batch_inference.py     # Батч-инференс для врагов
│   └── self_play.py     # Self-play арена с Elo рейтингом
│
├── l6_curriculum/       # Curriculum Learning
│   ├── __init__.py
│   └── curriculum_manager.py  # Прогрессия сложности + подсказки
│
└── l7_render/           # Рендер (Panda3D)
    ├── __init__.py
    └── renderer.py      # Изометрия, UI, редактор сцены
```

## Статус реализации

| Слой | Компоненты | Статус |
|------|-----------|--------|
| L4 - Gym Wrapper | env_wrapper, observation, action_space, reward_shaping | ✅ Готово |
| L5 - Training | ppo_trainer, checkpoint_manager, batch_inference, self_play | ✅ Готово |
| L6 - Curriculum | curriculum_manager, PlayerCoachInterface | ✅ Готово |
| L7 - Render | IsometricCamera, SceneEditor, TrainerUI | ✅ Каркас готов |

## Быстрый старт

```python
from python_layer.l4_gym import GymWrapper
from python_layer.l5_training import PPOTrainer
from python_layer.l6_curriculum import CurriculumManager

# Создание среды
env = GymWrapper(seed=42)

# Настройка обучения
trainer = PPOTrainer(env, checkpoint_dir="checkpoints")

# Curriculum менеджмент
curriculum = CurriculumManager(agent_id="hero_001")

# Обучение
trainer.train(total_timesteps=100_000)
```

## Документация

- [MULTILANG_ARCHITECTURE.md](../MULTILANG_ARCHITECTURE.md) - Полная архитектура
- [MULTILANG_INTEGRATION_REPORT.md](../MULTILANG_INTEGRATION_REPORT.md) - Отчёт интеграции
