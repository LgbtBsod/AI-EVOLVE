"""qa.py gauntlet - стенд боссов (tools/boss_gauntlet.py) из общей точки входа.

    qa.py gauntlet                              # все боссы, герой уровня босса
    qa.py gauntlet --campaign --lives 5 --trace # сессия с 1-го уровня, разум учится между жизнями
"""
from __future__ import annotations

import argparse

import boss_gauntlet


def register(sub) -> None:
    p = sub.add_parser("gauntlet", help="hero vs every boss (or a whole campaign), results in probe_db",
                       description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    boss_gauntlet.add_arguments(p)
    p.set_defaults(func=boss_gauntlet.run)
