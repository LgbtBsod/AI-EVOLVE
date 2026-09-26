"""Плагины tools/qa.py: каждый модуль здесь - подкоманды qa.py.

Контракт: register(sub) - добавить подпарсер(ы) в argparse-subparsers и
задать обработчик через set_defaults(func=...); обработчик возвращает код
выхода. qa.py находит модули сам (pkgutil), правка qa.py не нужна.

Перед новым плагином/инструментом: `qa.py tools --find "слова"` (не строить второй раз); у нового - строка purpose
(help= подпарсера / docstring / TOOL = {...} / строка tools.rows в qa.lua), иначе `qa.py check --name tools` падает.
"""
