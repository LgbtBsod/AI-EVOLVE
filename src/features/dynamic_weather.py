"""
Dynamic Weather & Environment System
Changes battlefield conditions affecting AI behavior and combat stats.

Исправления:
- Внедрён RNGManager вместо прямого random.* (SSOT, воспроизводимость тестов)
- Добавлены type hints (Python 3.10+ стиль)
- Оптимизированы аллокации в game loop
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from src.core.architecture import BaseComponent, ComponentType, Priority
from src.core.event_system import Event, EventSystem
from src.core.rng_manager import RNGManager

if TYPE_CHECKING:
    from collections.abc import Sequence


class WeatherType(Enum):
    CLEAR = "clear"
    RAIN = "rain"
    STORM = "storm"
    FOG = "fog"
    SANDSTORM = "sandstorm"


@dataclass(slots=True)
class WeatherEffect:
    weather_type: WeatherType
    visibility_mod: float  # -1.0 to 1.0
    speed_mod: float       # -1.0 to 1.0
    accuracy_mod: float    # -1.0 to 1.0
    duration: float
    special_effects: list[str] = field(default_factory=list)


class DynamicWeatherSystem(BaseComponent):
    """
    Manages dynamic weather conditions that affect gameplay.
    Forces AI to adapt strategies based on environmental changes.
    """

    __slots__ = (
        '_rng', 'current_weather', 'weather_history', 'transition_timer',
        'next_weather_duration', 'weather_profiles'
    )

    def __init__(self, rng: RNGManager | None = None) -> None:
        super().__init__(ComponentType.SYSTEM, Priority.NORMAL)
        self._rng = rng or RNGManager()
        self.current_weather: WeatherEffect | None = None
        self.weather_history: list[WeatherEffect] = []
        self.transition_timer: float = 0.0
        self.next_weather_duration: float = 30.0  # seconds

        self.weather_profiles: dict[WeatherType, WeatherEffect] = {
            WeatherType.CLEAR: WeatherEffect(
                WeatherType.CLEAR, 0.0, 0.0, 0.0, 60.0, ["normal_visibility"]
            ),
            WeatherType.RAIN: WeatherEffect(
                WeatherType.RAIN, -0.2, -0.1, -0.15, 45.0, ["wet_ground", "reduced_visibility"]
            ),
            WeatherType.STORM: WeatherEffect(
                WeatherType.STORM, -0.5, -0.3, -0.4, 30.0, ["lightning_risk", "mud", "loud_thunder"]
            ),
            WeatherType.FOG: WeatherEffect(
                WeatherType.FOG, -0.7, 0.0, -0.2, 40.0, ["hidden_units", "ambush_bonus"]
            ),
            WeatherType.SANDSTORM: WeatherEffect(
                WeatherType.SANDSTORM, -0.8, -0.4, -0.5, 25.0, ["damage_over_time", "disorientation"]
            )
        }

    def _on_initialize(self) -> bool:
        logging.info("Dynamic Weather System initialized.")
        self._change_weather(WeatherType.CLEAR)
        return True

    def _change_weather(self, weather_type: WeatherType) -> None:
        """Apply new weather conditions."""
        effect = self.weather_profiles[weather_type]
        self.current_weather = effect
        self.weather_history.append(effect)

        # Broadcast event
        if EventSystem.instance:
            EventSystem.instance.trigger_event(Event(
                event_type="WEATHER_CHANGED",
                data={
                    "weather": weather_type.value,
                    "visibility": effect.visibility_mod,
                    "speed": effect.speed_mod,
                    "accuracy": effect.accuracy_mod,
                    "effects": effect.special_effects
                }
            ))

        logging.info("Weather changed to %s. Effects: %s", weather_type.value, effect.special_effects)

    def _on_update(self, delta_time: float) -> None:
        """Update weather system with deterministic RNG."""
        self.transition_timer += delta_time

        if self.transition_timer >= self.next_weather_duration:
            self.transition_timer = 0.0
            # Randomly select new weather (weighted towards clear/fog for variety)
            weights: Sequence[float] = [0.4, 0.2, 0.1, 0.2, 0.1]  # Clear, Rain, Storm, Fog, Sandstorm
            choices = list(WeatherType)
            new_weather = self._rng.choices(choices, weights=weights)[0]
            self._change_weather(new_weather)

            # Randomize next duration
            self.next_weather_duration = self._rng.uniform(20.0, 60.0)

    def get_environmental_bonus(self, entity_tags: list[str]) -> dict[str, float]:
        """Calculate bonuses/penalties based on weather and entity traits."""
        if not self.current_weather:
            return {}

        bonuses: dict[str, float] = {}
        weather = self.current_weather

        # Example logic: some units thrive in certain weather
        if "stealth_unit" in entity_tags and weather.weather_type == WeatherType.FOG:
            bonuses["stealth"] = 0.5  # 50% harder to detect

        if "heavy_armor" in entity_tags and weather.weather_type == WeatherType.RAIN:
            bonuses["speed"] = -0.2  # Slowed by mud

        if "electric_attack" in entity_tags and weather.weather_type == WeatherType.STORM:
            bonuses["damage"] = 0.3  # Lightning amplifies electric attacks

        return bonuses
