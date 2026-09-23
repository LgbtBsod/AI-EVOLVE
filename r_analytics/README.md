# R Analytics Layer

## Назначение
Лаборатория: аналитика логов, баланс, win-rate, графики.

## Структура
```
r_analytics/
├── scripts/
│   ├── analyze_runs.R        # Анализ серий забегов
│   ├── win_rate_curves.R     # Кривые обучения по чекпоинтам
│   ├── death_heatmap.R       # Heatmap смертей на картах
│   ├── skill_balance.R       # Баланс скиллов (pick rate, win rate)
│   ├── enemy_difficulty.R    # Сложность врагов по типам
│   └── reward_analysis.R     # Анализ reward функций
├── libs/
│   ├── metrics.R             # Общие метрики
│   ├── plots.R               # Функции визуализации
│   └── data_loader.R         # Загрузка parquet в R
├── reports/                  # Сгенерированные отчёты
│   ├── weekly_balance.md     # Еженедельный баланс-отчёт
│   └── session_summary.Rmd   # Шаблон отчёта по сессии
└── data/                     # Входные данные (parquet)
    ├── agent_progress/       # Прогресс агента
    ├── combat_logs/          # Логи боёв
    └── world_stats/          # Статистика мира
```

## Пример скрипта: кривая обучения
```r
# scripts/win_rate_curves.R
library(tidyverse)
library(arrow)  # parquet
library(ggplot2)

load_agent_data <- function(save_path) {
  read_parquet(file.path(save_path, "agent_progress.parquet"))
}

plot_win_rate <- function(data) {
  data %>%
    group_by(checkpoint_id) %>%
    summarize(
      win_rate = mean(reward > 0),
      deaths = mean(deaths),
      time = mean(time_seconds)
    ) %>%
    ggplot(aes(x = checkpoint_id)) +
    geom_line(aes(y = win_rate, color = "Win Rate")) +
    geom_line(aes(y = 1 - deaths/10, color = "Survival")) +
    labs(title = "Learning Curve", x = "Checkpoint", y = "Rate") +
    theme_minimal()
}

# Использование
data <- load_agent_data("saves/session_001/")
ggsave("win_rate.png", plot_win_rate(data))
```

## Пример: heatmap смертей
```r
# scripts/death_heatmap.R
library(ggplot2)
library(dplyr)
library(viridis)

plot_death_heatmap <- function(death_logs, map_id) {
  death_logs %>%
    filter(map == map_id) %>%
    count(tile_x, tile_y) %>%
    ggplot(aes(x = tile_x, y = tile_y, fill = n)) +
    geom_tile() +
    scale_fill_viridis(option = "plasma") +
    labs(title = paste("Death Heatmap - Map", map_id)) +
    theme_void()
}
```

## Интеграция с Python/Rust
1. **Экспорт логов:** Python пишет в parquet (`pyarrow`)
2. **Запуск R:** Python вызывает `Rscript` через subprocess
3. **Результаты:** Графики сохраняются в `/reports/`, метрики в JSON

```python
# python_layer/utils/analytics_runner.py
import subprocess
import pandas as pd
import pyarrow.parquet as pq

def export_to_parquet(data, path):
    pq.write_table(pa.Table.from_pandas(data), path)

def run_r_script(script_name, data_path):
    subprocess.run([
        "Rscript",
        f"r_analytics/scripts/{script_name}",
        data_path
    ])
```

## Метрики для анализа
| Метрика | Описание | Цель |
|---|---|---|
| Win Rate | % побед на карте | 40-60% (баланс) |
| Death Count | Среднее число смертей | < 5 на карту |
| Time to Complete | Время прохождения | 2-5 мин на карту |
| Skill Pick Rate | Частота использования скилла | Равномерное |
| Reward per Minute | Награда за минуту | Растёт с обучением |
| Enemy Difficulty | Сложность врагов (K/D) | 1.0-1.5 |

## Следующие шаги
1. Установить R и пакеты (tidyverse, arrow, ggplot2)
2. Создать шаблоны скриптов
3. Настроить экспорт parquet из Python
4. Автоматизировать запуск после сессии
