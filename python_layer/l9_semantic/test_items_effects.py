"""
Тестовые предметы и скиллы с сложными эффектами для Training Room

Демонстрация универсальности EffectConfig:
1. Earth Shatter Column - AoE атака с колоннами, DoT, slow
2. Vial of Eternal Regeneration - банка хила с HoT
3. Thunder God's Wrath - глобальная атака с chain lightning
"""

from python_layer.l9_semantic.cas_effect_system import (
    EffectConfig, EffectType, TargetingMode, 
    EffectArea, EffectTick, CrowdControl
)


# ============================================================================
# ПРЕДМЕТ 1: Earth Shatter Column (Шлем)
# ============================================================================
"""
При использовании создаёт 20 каменных колонн в радиусе 10 метров вокруг персонажа.
Каждая колонна:
- Наносит 20 физического урона в секунду всем врагам в радиусе 3м (DoT)
- Замедляет на 40% на 3 секунды (Crowd Control)
- Колонны стоят 8 секунд, тикают каждую секунду
"""

earth_shatter_config = EffectConfig(
    effect_type=EffectType.GROUND_TARGETED,
    targeting=TargetingMode.AREA_AROUND_SELF,
    
    # Область действия: 20 колонн в радиусе 10м
    area=EffectArea(
        shape="circle",
        radius=10.0,  # метры
        max_targets=20,  # лимит колонн
        friendly_fire=False
    ),
    
    # Периодический эффект от каждой колонны
    tick=EffectTick(
        tick_rate=1.0,        # тик каждую секунду
        tick_count=8,         # 8 тиков (колонны стоят 8 сек)
        can_stack=True,       # можно получить несколько колонок рядом
        max_stacks=5,         # максимум 5 колонок на одной цели
        stack_type="intensity",  # урон суммируется
        tick_event="damage"
    ),
    
    # Crowd Control: замедление
    cc=CrowdControl(
        type="slow",
        strength=0.40,        # 40% замедление
        duration=3.0,         # 3 секунды
        diminishing_returns=True,
        cc_type_group="movement"
    ),
    
    # Статы от предмета (пассивные)
    stat_modifiers={
        "defense_flat": 150.0,
        "max_hp_flat": 500.0,
        "str_flat": 25.0,
    },
    
    # Длительности
    duration=8.0,             # колонны стоят 8 сек
    cast_time=1.5,            # каст 1.5 сек
    cooldown=45.0,            # 45 сек перезарядка
    
    # Стоимость
    mana_cost=200.0,
    hp_cost=0.0,
    stamina_cost=50.0,
    can_kill=False,           # мана не может убить
    
    # Поведение
    can_stack=False,
    
    # Визуал
    visual_template="stone_columns_eruption_v2",
    sound_template="earth_shatter_boom",
    icon="items/helm_earthshatter.png",
    
    # Теги для поиска и фильтрации
    tags=["earth", "aoe", "dot", "slow", "column", "ground_targeted"],
    
    # Описание для игрока
    description=(
        "Разбивает землю, создавая 20 каменных колонн в радиусе 10м. "
        "Колонны наносят 20 физ. урона/сек и замедляют врагов на 40% на 3 сек. "
        "Длительность колонн: 8 сек."
    )
)


# ============================================================================
# ПРЕДМЕТ 2: Vial of Eternal Regeneration (Зелье)
# ============================================================================
"""
Банка хила с мощным HoT эффектом:
- Мгновенно восстанавливает 500 HP
- Затем лечит 150 HP/сек в течение 10 сек (HoT)
- Снимает все дебаффы типа "poison" и "bleed"
- Даёт бафф "Regeneration" (+20% к получаемому хилу на 15 сек)
"""

vial_regen_config = EffectConfig(
    effect_type=EffectType.HOT,
    targeting=TargetingMode.SELF,
    
    # Нет области, только на себя
    area=None,
    
    # Периодическое лечение
    tick=EffectTick(
        tick_rate=1.0,        # тик каждую секунду
        duration=10.0,        # 10 сек длительность
        can_stack=False,      # нельзя стакать (обновляет длительность)
        max_stacks=1,
        stack_type="time",    # продлевает время
        tick_event="heal"
    ),
    
    # Crowd Control: снятие дебаффов (реализуется через special effect)
    cc=CrowdControl(
        type="cleanse",       # специальный тип для очищения
        strength=1.0,         # снимает всё
        duration=0.0,         # мгновенно
        diminishing_returns=False,
        cc_type_group="control"
    ),
    
    # Статы от зелья (бафф после использования)
    stat_modifiers={
        "heal_received_percent": 0.20,  # +20% к получаемому хилу
    },
    
    # Длительности
    duration=15.0,            # бафф висит 15 сек
    cast_time=0.5,            # быстро выпить
    cooldown=30.0,            # 30 сек кулдаун
    
    # Стоимость (зелье платит заряды, а не ресурсы)
    mana_cost=0.0,
    hp_cost=0.0,
    stamina_cost=0.0,
    can_kill=False,
    
    # Поведение
    can_stack=False,
    max_stacks=1,
    
    # Визуал
    visual_template="potion_green_swirl_v3",
    sound_template="potion_drink_cleanse",
    icon="items/vial_eternal_regen.png",
    
    # Теги
    tags=["potion", "hot", "heal", "cleanse", "buff", "self"],
    
    # Описание
    description=(
        "Мгновенно восстанавливает 500 HP, затем лечит 150 HP/сек в течение 10 сек. "
        "Снимает яды и кровотечения. Даёт +20% к получаемому хилу на 15 сек."
    )
)


# ============================================================================
# СКИЛЛ 1: Thunder God's Wrath (Ульта)
# ============================================================================
"""
Глобальная атака по всем врагам на карте:
- Бьёт молнией всех видимых врагов
- Цепная реакция: прыгает с цели на цель (до 10 прыжков)
- Каждый прыжок усиливается на 15%
- Накладывает шок (cannot attack) на 1.5 сек
- При убийстве цели кулдаун снижается на 50%
"""

thunder_wrath_config = EffectConfig(
    effect_type=EffectType.CHAIN,
    targeting=TargetingMode.GLOBAL,  # вся карта
    
    # Область: глобально, но с лимитом целей
    area=EffectArea(
        shape="global",
        radius=0.0,
        max_targets=10,  # до 10 прыжков
        friendly_fire=False
    ),
    
    # Нет периодики, мгновенный урон
    tick=None,
    
    # Crowd Control: шок (stun для атак)
    cc=CrowdControl(
        type="shock",         # специальный тип - нельзя атаковать
        strength=1.0,         # полный запрет атак
        duration=1.5,         # 1.5 секунды
        diminishing_returns=True,
        cc_type_group="action"
    ),
    
    # Статы (пассивные от скилла, если есть)
    stat_modifiers={},
    
    # Условия активации (CAS триггеры)
    trigger_conditions=[
        {"type": "hp_percent_lt", "value": 0.5},  # можно использовать только при HP < 50%
        {"type": "has_debuff", "debuff": "enraged"},  # или если есть бафф ярости
    ],
    
    # Длительности
    duration=0.0,             # мгновенно
    cast_time=2.0,            # долгий каст 2 сек
    cooldown=120.0,           # 2 минуты
    
    # Стоимость
    mana_cost=500.0,
    hp_cost=0.0,
    stamina_cost=100.0,
    can_kill=False,
    
    # Поведение
    can_stack=False,
    
    # Визуал
    visual_template="lightning_global_chain_v5",
    sound_template="thunder_god_ultimate",
    icon="skills/thunder_wrath_ult.png",
    
    # Теги
    tags=["lightning", "chain", "global", "cc", "shock", "ultimate"],
    
    # Описание
    description=(
        "Бьёт молнией всех видимых врагов на карте. Цепная реакция прыгает "
        "между целями (до 10 раз), каждый прыжок +15% урона. "
        "Накладывает шок на 1.5 сек. При убийстве кулдаун -50%."
    )
)


# ============================================================================
# СКИЛЛ 2: Blood Moon Ritual (Ритуал)
# ============================================================================
"""
Каналируемый ритуал в течение 5 секунд:
- Каждую секунду наносит 5% от текущего HP всем врагам в радиусе 15м (DoT)
- За каждое нанесённое повреждение лечит кастера на 10% от нанесённого урона (vamp)
- Если прервать каст - теряется весь накопленный эффект
- После завершения даёт бафф "Blood Moon" (+30% spell damage на 20 сек)
"""

blood_moon_config = EffectConfig(
    effect_type=EffectType.CHANNELING,
    targeting=TargetingMode.AREA_AROUND_SELF,
    
    # Область: 15м вокруг
    area=EffectArea(
        shape="circle",
        radius=15.0,
        max_targets=0,  # без лимита
        friendly_fire=False
    ),
    
    # Периодический урон + вампиризм
    tick=EffectTick(
        tick_rate=1.0,        # тик каждую секунду
        tick_count=5,         # 5 тиков (канал 5 сек)
        can_stack=False,
        max_stacks=1,
        stack_type="intensity",
        tick_event="damage_vamp"  # специальный тип: урон + вампиризм
    ),
    
    # Нет CC, только урон
    cc=None,
    
    # Статы (бафф после завершения)
    stat_modifiers={
        "spell_damage_percent": 0.30,  # +30% маг урона
    },
    
    # Длительности
    duration=5.0,             # канал 5 сек
    cast_time=0.0,            # начинает сразу
    cooldown=60.0,            # 1 минута
    
    # Стоимость
    mana_cost=100.0,
    hp_cost=0.0,
    stamina_cost=0.0,
    can_kill=False,
    
    # Поведение
    can_stack=False,
    
    # Визуал
    visual_template="blood_moon_ritual_circle",
    sound_template="dark_ritual_channel",
    icon="skills/blood_moon_ritual.png",
    
    # Теги
    tags=["blood", "channeling", "aoe", "dot", "vamp", "ritual"],
    
    # Описание
    description=(
        "Каналирует ритуал 5 сек, нанося 5% от текущего HP всем врагам в радиусе 15м "
        "каждую секунду. Лечит на 10% от нанесённого урона. "
        "После завершения: +30% spell damage на 20 сек."
    )
)


# ============================================================================
# ЭКСПОРТ КОНФИГУРАЦИЙ
# ============================================================================

ALL_TEST_CONFIGS = {
    "earth_shatter_column": earth_shatter_config,
    "vial_eternal_regen": vial_regen_config,
    "thunder_god_wrath": thunder_wrath_config,
    "blood_moon_ritual": blood_moon_config,
}


def get_config_by_name(name: str) -> EffectConfig:
    """Получить конфигурацию по имени"""
    if name not in ALL_TEST_CONFIGS:
        raise ValueError(f"Unknown config: {name}. Available: {list(ALL_TEST_CONFIGS.keys())}")
    return ALL_TEST_CONFIGS[name]


def export_to_dict(config: EffectConfig) -> dict:
    """Экспорт конфигурации в dict (для JSON/Lua)"""
    return {
        "effect_type": config.effect_type.value,
        "targeting": config.targeting.value,
        "area": {
            "shape": config.area.shape,
            "radius": config.area.radius,
            "max_targets": config.area.max_targets,
            "friendly_fire": config.area.friendly_fire,
        } if config.area else None,
        "tick": {
            "tick_rate": config.tick.tick_rate,
            "duration": config.tick.duration,
            "can_stack": config.tick.can_stack,
            "max_stacks": config.tick.max_stacks,
            "stack_type": config.tick.stack_type,
            "tick_event": config.tick.tick_event,
        } if config.tick else None,
        "cc": {
            "type": config.cc.type,
            "strength": config.cc.strength,
            "duration": config.cc.duration,
            "diminishing_returns": config.cc.diminishing_returns,
            "cc_type_group": config.cc.cc_type_group,
        } if config.cc else None,
        "stat_modifiers": config.stat_modifiers,
        "trigger_conditions": config.trigger_conditions,
        "duration": config.duration,
        "cast_time": config.cast_time,
        "cooldown": config.cooldown,
        "mana_cost": config.mana_cost,
        "hp_cost": config.hp_cost,
        "stamina_cost": config.stamina_cost,
        "can_kill": config.can_kill,
        "can_stack": config.can_stack,
        "visual_template": config.visual_template,
        "sound_template": config.sound_template,
        "icon": config.icon,
        "tags": config.tags,
        "description": config.description,
    }


if __name__ == "__main__":
    print("📦 Тестовые предметы и скиллы:")
    print("=" * 60)
    
    for name, config in ALL_TEST_CONFIGS.items():
        print(f"\n🔹 {name}:")
        print(f"   Тип: {config.effect_type.value}")
        print(f"   Таргетинг: {config.targeting.value}")
        if config.area:
            print(f"   Область: {config.area.shape} r={config.area.radius}м")
        if config.tick:
            print(f"   Периодика: {config.tick.tick_rate}с x {config.tick.tick_count or config.tick.duration}сек")
        if config.cc:
            print(f"   CC: {config.cc.type} ({config.cc.strength*100:.0f}%) на {config.cc.duration}с")
        print(f"   Кулдаун: {config.cooldown}с")
        print(f"   Теги: {', '.join(config.tags)}")
    
    print("\n" + "=" * 60)
    print("✅ Все конфигурации созданы успешно!")
    print("\nПример использования:")
    print("  from test_items_effects import get_config_by_name")
    print("  config = get_config_by_name('earth_shatter_column')")
    print("  effect = create_effect_from_config(config)")
