"""Simple configuration manager for project runtime settings."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict


@dataclass(slots=True)
class DisplayConfig:
    width: int = 1600
    height: int = 900
    fullscreen: bool = False
    vsync: bool = True


@dataclass(slots=True)
class AudioConfig:
    master_volume: float = 1.0
    music_volume: float = 0.7
    sfx_volume: float = 0.8


@dataclass(slots=True)
class GameplayConfig:
    difficulty: str = "normal"
    auto_save: bool = True
    save_interval: int = 300


class ConfigManager:
    def __init__(self, config_dir: Path | None = None):
        self.config_dir = config_dir or Path("config")
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.display = DisplayConfig()
        self.audio = AudioConfig()
        self.gameplay = GameplayConfig()

    def _path(self, name: str) -> Path:
        return self.config_dir / f"{name}.json"

    def load(self, name: str) -> Dict[str, Any]:
        path = self._path(name)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, name: str, payload: Dict[str, Any]) -> None:
        self._path(name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_defaults(self) -> None:
        self.save("display_config", asdict(self.display))
        self.save("audio_config", asdict(self.audio))
        self.save("gameplay_config", asdict(self.gameplay))
