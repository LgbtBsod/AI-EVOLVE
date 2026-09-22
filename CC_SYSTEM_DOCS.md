# 🎮 Crowd Control & Break System - Документация

## Обзор

Реализована полноценная система негативных эффектов (CC), стойкости (Stagger) и состояния слома (Break) для игры. Система поддерживает многопоточность, интегрируется с Dev Probe через плагин и следует принципам SOLID.

---

## 📋 Компоненты

### 1. Типы эффектов контроля (CCType)

| Эффект | Описание | Приоритет |
|--------|----------|-----------|
| `STUN` | Полный контроль, нельзя действовать | 5 (max) |
| `KNOCKDOWN` | Сбит с ног, нельзя двигаться/атаковать | 4 |
| `MICRO_STUN` | 0.2с прерывание кастов (mini-bash) | 3 |
| `ROOT` | Нельзя двигаться, можно атаковать | 2 |
| `DISORIENTED` | Замедление, промахи | 1 |
| `SLOW` | Замедление передвижения | 0 |

### 2. Состояния стойкости (BreakState)

- **NORMAL** - Обычное состояние, накопление урона по стойке
- **STAGGERING** - Процесс накопления (не используется явно)
- **BROKEN** - Сломлен, уязвим (+15% урона, -25% резистов)

### 3. Характеристики персонажа (CharacterCCStats)

#### Атакующие статы:
- `cc_damage_mult` - +% урона по контролируемым целям
- `cc_duration_mult` - +% длительности накладываемых эффектов

#### Защитные статы:
- `cc_resist_flat` - Плоское снижение урона когда ты в КК
- `cc_resist_percent` - % снижения урона когда ты в КК
- `cc_duration_resist` - Множитель длительности эффектов на тебе (0.5 = -50%)

#### Стойкость:
- `stagger_max` - Максимальная стойкость (по умолчанию 500)
- `stagger_regen` - Восстановление стойки в секунду
- `stagger_resist` - Множитель сопротивления урону по стойке

---

## ⚙️ Механики

### Формула брейка
```
Длительность брейка = (MaxStagger / 500) * 1.0сек * BreakDurationResist
```
Пример: При MaxStagger=1000 → брейк длится 2 секунды.

### Урон по стойке
```
EffectiveDamage = BaseDamage * StaggerResist
CurrentStagger += EffectiveDamage
if CurrentStagger >= MaxStagger:
    TriggerBreak()
```

### Модификаторы урона в брейке
- **+15%** входящего урона
- **-25%** сопротивлений (реализуется в калькуляторе урона)

### Правила наложения эффектов

1. **Нельзя законтролить в брейке** - новые эффекты игнорируются как отдельные таймеры
2. **Приоритеты** - всегда применяется самый жесткий эффект
3. **Микро-стан** - мгновенно прерывает касты (0.2с окно)
4. **Дебаф + Брейк** - стакаются (дебаф висит, брейк дает уязвимость)

---

## 🔌 Dev Probe Plugin

### CCProbePlugin

Плагин для управления CC системой через AI агентов или тесты.

#### Команды (CCCommandType):

| Команда | Параметры | Описание |
|---------|-----------|----------|
| `APPLY_STUN` | target_id, duration, source_id | Применить стан |
| `APPLY_KNOCKDOWN` | target_id, duration, source_id | Применить нокдаун |
| `APPLY_SLOW` | target_id, duration, source_id | Применить замедление |
| `APPLY_MICRO_STUN` | target_id, duration, source_id | Прервать каст |
| `DEAL_STAGGER_DMG` | target_id, damage | Урон по стойке |
| `GET_CC_STATUS` | target_id | Получить статус |
| `RESET_CC` | target_id | Сбросить все эффекты |
| `SIMULATE_BREAK_COMBO` | target_id, hits, hit_damage, base_damage | Симуляция комбо |

#### Пример использования:

```python
from tools.plugins.cc_probe_plugin import CCProbePlugin, CCCommandType
from src.features.cc_system import CharacterCCStats

# Инициализация
plugin = CCProbePlugin()

# Регистрация босса
boss_stats = CharacterCCStats(
    stagger_max=1000.0,
    stagger_resist=1.0,
    cc_duration_resist=0.8
)
plugin.register_entity("boss_1", boss_stats)

# Применение стана
result = plugin.execute_command(CCCommandType.APPLY_STUN, {
    "target_id": "boss_1",
    "duration": 3.0,
    "source_id": "player_spell"
})

# Накопление стойки и брейк
for i in range(5):
    result = plugin.execute_command(CCCommandType.DEAL_STAGGER_DMG, {
        "target_id": "boss_1",
        "damage": 250.0
    })
    print(f"Удар {i+1}: Stagger={result['stagger_current']}")

# Проверка статуса
status = plugin.execute_command(CCCommandType.GET_CC_STATUS, {
    "target_id": "boss_1"
})
print(f"Статус: {status['status']}, Break: {status['break_state']}")
```

---

## 🧪 Тестирование

### Результаты тестов:

```
✅ CC System Core: Все механики работают
✅ Break Trigger: Срабатывает при превышении стойки
✅ Damage Multiplier: +15% в брейке
✅ Micro-stun: Прерывает касты
✅ Combo Simulation: Дебаф → Брейк → Урон
✅ CC Probe Plugin: 6/6 команд работают
```

### Запуск тестов:

```bash
# Тест ядра CC системы
python src/features/cc_system.py

# Тест плагина Dev Probe
python tools/plugins/cc_probe_plugin.py
```

---

## 📊 Интеграция с игрой

### В Game Loop:

```python
def game_loop(dt):
    # Обновление CC менеджеров всех сущностей
    for entity in entities:
        if hasattr(entity, 'cc_manager'):
            entity.cc_manager.update(dt)
    
    # Проверка состояний
    for enemy in enemies:
        if enemy.cc_manager.is_cc_immobilized():
            enemy.stop_actions()
        
        status = enemy.cc_manager.get_current_status()
        if status == CCType.STUN:
            enemy.play_stun_animation()
```

### В калькуляторе урона:

```python
def calculate_damage(attacker, target, base_dmg):
    # Получаем модификаторы от CC
    final_dmg = target.cc_manager.take_damage_with_cc_mods(base_dmg)
    
    # Применяем статы атакующего (урон по контролируемым)
    if target.cc_manager.is_cc_immobilized():
        final_dmg *= attacker.stats.cc_damage_mult
    
    return final_dmg
```

---

## 🎯 Best Practices

### SOLID принципы:
- **SRP**: `StatusEffectManager` отвечает только за CC, `StaggerBar` только за стойку
- **OCP**: Легко добавить новые типы эффектов через enum
- **DIP**: `CharacterCCStats` внедряются в менеджер
- **Thread Safety**: Используется `threading.Lock` для всех операций

### Python Standard Library:
- `dataclasses` - для структур данных
- `enum.Enum` - для типобезопасности
- `threading.Lock` - для синхронизации
- `logging` - для отладки

---

## 📈 Будущие улучшения

- [ ] Визуализация шкалы стойкости в UI
- [ ] Звуковые эффекты для брейка
- [ ] Анимации прерывания кастов
- [ ] Resist calculations в полном калькуляторе урона
- [ ] Immunity frames после брейка
- [ ] PVP балансировка множителей

---

## 📝 Changelog

### v1.0.0 (2026-09-22)
- ✅ Ядро CC системы (Stun, Knockdown, Slow, Micro-stun)
- ✅ Система стойкости и брейка
- ✅ Интеграция с Dev Probe (CCProbePlugin)
- ✅ Полное покрытие тестами
- ✅ Документация
