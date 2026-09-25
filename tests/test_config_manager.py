"""Модульные тесты для src/core/config_manager.py - конфиги и скейлинг врагов."""
import json

import pytest

from src.core.config_manager import (
    AudioConfig,
    CharacterStatsConfig,
    ConfigManager,
    DisplayConfig,
    GameplayConfig,
)


@pytest.fixture()
def cm(tmp_path):
    return ConfigManager(tmp_path / "cfg")


class TestBasics:
    def test_config_dir_created(self, tmp_path):
        target = tmp_path / "nested" / "cfg"
        ConfigManager(target)
        assert target.is_dir()

    def test_default_dataclasses(self, cm):
        assert (cm.display.width, cm.display.height) == (1600, 900)
        assert cm.audio.master_volume == 1.0
        assert cm.gameplay.difficulty == "normal"
        assert cm.character_stats.health == 100.0
        assert isinstance(cm.display, DisplayConfig)
        assert isinstance(cm.audio, AudioConfig)
        assert isinstance(cm.gameplay, GameplayConfig)
        assert isinstance(cm.character_stats, CharacterStatsConfig)

    def test_save_load_roundtrip_utf8(self, cm):
        payload = {"имя": "Гоблин", "hp": 50}
        cm.save("monster", payload)
        assert cm.load("monster") == payload
        # файл реально JSON с не-ASCII без экранирования
        raw = json.loads((cm.config_dir / "monster.json").read_text(encoding="utf-8"))
        assert raw == payload

    def test_load_missing_returns_empty(self, cm):
        assert cm.load("nope") == {}

    def test_save_defaults_writes_three_files(self, cm):
        cm.save_defaults()
        for name in ("display_config", "audio_config", "gameplay_config"):
            assert (cm.config_dir / f"{name}.json").exists()
        assert cm.load("display_config")["width"] == 1600


class TestDotNotationGetSet:
    def test_get_unknown_key_returns_default(self, cm):
        assert cm.get("totally.unknown", "dflt") == "dflt"

    def test_set_and_get_characters(self, cm):
        assert cm.set("characters.base.health", 120) is True
        assert cm.get("characters.base.health") == 120
        # ВНИМАНИЕ (квирк реализации): set/save сохраняют на диск содержимое
        # кэша БЕЗ префикса root-ключа, а get читает файл через keys[1:].
        # Поэтому "characters.base.health" пишется в файл как {"health": 120},
        # и для roundtrip через диск нужно использовать удвоенный ключ.
        disk = cm.load("character_stats")
        assert disk["health"] == 120

    def test_disk_roundtrip_flat_format(self, cm):
        # КВИРК РЕАЛИЗАЦИИ (задокументировано): set("enemies.enemies.X") кладёт
        # словарь в кэш по полному пути и пишет на диск СООДЕРЖИМОЕ КЭША БЕЗ
        # префикса, поэтому на диске получается плоский формат {"X": {...}},
        # который корректно читается УКРОЧЕННЫМ путём "enemies.X" (первый
        # сегмент — имя файла). Удвоенный путь после перезагрузки возвращает None.
        cm.set("enemies.enemies.goblin", {"health": 50})
        assert json.loads((cm.config_dir / "enemy_stats.json").read_text()) == {
            "goblin": {"health": 50}
        }
        # в живом менеджере удвоенный путь работает из кэша:
        assert cm.get("enemies.enemies.goblin.health") == 50
        fresh = ConfigManager(cm.config_dir)
        # а новый менеджер читает диск укороченным путём:
        assert fresh.get("enemies.goblin.health") == 50
        assert fresh.get("enemies.enemies.goblin.health") is None

    def test_set_creates_intermediate_dicts(self, cm):
        cm.set("characters.deep.nested.value", 7)
        assert cm.get("characters.deep.nested.value") == 7

    def test_cache_picks_up_own_set_without_reload(self, cm):
        cm.set("characters.a.b", 1)
        cm.set("characters.a.b", 2)   # повторный set видит свежий кэш
        assert cm.get("characters.a.b") == 2

    def test_external_file_change_requires_reload(self, cm):
        # файл в формате, который get читает без двойного ключа: "characters.a.b"
        cm.save("character_stats", {"a": {"b": 1}})
        assert cm.get("characters.a.b") == 1  # кэш загружен
        # правим файл в обход менеджера - кэш не видит изменений
        disk = cm.load("character_stats")
        disk["a"]["b"] = 999
        cm.save("character_stats", disk)
        assert cm.get("characters.a.b") == 1     # старый кэш
        cm.reload("character_stats")
        assert cm.get("characters.a.b") == 999   # после reload свежее

    def test_reload_all_clears_cache(self, cm):
        cm.save("enemy_stats", {"enemies": {"goblin": {"health": 50}}})
        assert cm.get("enemies.enemies.goblin.health") == 50  # грузим в кэш
        cm.save("enemy_stats", {"enemies": {"goblin": {"health": 77}}})
        assert cm.get("enemies.enemies.goblin.health") == 50  # всё ещё кэш
        cm.reload()                                           # clear всех
        assert cm.get("enemies.enemies.goblin.health") == 77  # перечитано с диска

    def test_get_enemy_stats_scale_l5(self, cm):
        cm.set("enemies.enemies.goblin", {
            "health": 50, "damage": 10, "defense": 2, "exp_reward": 20, "level": 1,
        })
        cm.set("enemies.scaling", {
            "health_per_level": 15, "damage_per_level": 5,
            "defense_per_level": 2, "exp_multiplier": 1.3,
        })
        s = cm.get_enemy_stats("goblin", 5)
        assert s["health"] == 110      # 50 + 4*15
        assert s["damage"] == 30       # 10 + 4*5
        assert s["defense"] == 10      # 2 + 4*2
        assert s["exp_reward"] == int(20 * 1.3 ** 4)  # 57

    def test_get_enemy_stats_level1_no_scaling(self, cm):
        cm.set("enemies.enemies.goblin", {"health": 50, "damage": 10, "level": 1})
        s = cm.get_enemy_stats("goblin", 1)
        assert s["health"] == 50

    def test_get_enemy_stats_unknown_type(self, cm):
        assert cm.get_enemy_stats("unicorn") == {}

    def test_get_class_stats(self, cm):
        cm.set("characters.classes.paladin", {"strength": 2})
        assert cm.get_class_stats("paladin") == {"strength": 2}
        assert cm.get_class_stats("nobody") == {}
