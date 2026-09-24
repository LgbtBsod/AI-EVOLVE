"""qa.py lua - Lua-контент проекта через tools/lua_bridge.py.

    qa.py lua check                  # каждый lua_content/**/*.lua всеми бэкендами: исполняется, данные совпадают
    qa.py lua show PATH [--key a.b]  # данные файла (или поддерево) компактным JSON - вместо чтения Lua
    qa.py lua show PATH --keys       # только ключи верхнего уровня и размер каждого
    qa.py lua bench PATH             # мс на загрузку каждым бэкендом и из кэша
"""
from __future__ import annotations

import json
import time

import lua_bridge
from probe_settings import ROOT

CONTENT = ROOT / "lua_content"
TRAINING_GLOBALS = ("mannequins", "scenarios", "item_sets", "thresholds")


def _load(path, backend=None):
    # файлы комнаты объявляют глобальные таблицы вместо return
    globals_ = TRAINING_GLOBALS if "training_room" in path.parts else ()
    return lua_bridge.load(path, globals=globals_, backend=backend)


def cmd_check(args) -> int:
    backends = lua_bridge.available_backends()
    bad = 0
    for path in sorted(CONTENT.rglob("*.lua")):
        rel = path.relative_to(ROOT).as_posix()
        results, times = {}, {}
        for b in backends:
            t0 = time.perf_counter()
            try:
                results[b] = _load(path, b)
            except Exception as exc:  # noqa: BLE001
                results[b] = exc
            times[b] = (time.perf_counter() - t0) * 1000
        errors = {b: r for b, r in results.items() if isinstance(r, Exception)}
        values = [r for r in results.values() if not isinstance(r, Exception)]
        same = all(v == values[0] for v in values[1:])
        if errors or not same:
            bad += 1
            why = "; ".join(f"{b}: {e}" for b, e in errors.items()) or "backends return different data"
            print(f"BAD {rel}: {why}")
        elif args.verbose:
            print(f"ok  {rel} ({', '.join(f'{b} {ms:.1f} ms' for b, ms in times.items())})")
    total = len(list(CONTENT.rglob("*.lua")))
    print(f"lua: {total - bad}/{total} files ok with {', '.join(backends) or 'no backend'}")
    return 1 if bad else 0


def _size(v) -> str:
    if isinstance(v, dict):
        return f"table {len(v)} keys"
    if isinstance(v, list):
        return f"list {len(v)}"
    return json.dumps(v, ensure_ascii=False)[:60]


def cmd_show(args) -> int:
    data = _load(ROOT / args.path if not args.path.startswith("/") else args.path)
    for part in filter(None, (args.key or "").split(".")):
        data = data[int(part)] if isinstance(data, list) else data[part]
    if args.keys and isinstance(data, (dict, list)):
        items = data.items() if isinstance(data, dict) else enumerate(data)
        for k, v in items:
            print(f"{k}: {_size(v)}")
    else:
        print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return 0


def cmd_bench(args) -> int:
    print(json.dumps(lua_bridge.bench(ROOT / args.path, repeat=args.repeat)))
    return 0


def register(sub):
    p = sub.add_parser("lua", help="Lua content: check / show / bench")
    s = p.add_subparsers(dest="lua_cmd", required=True)
    c = s.add_parser("check", help="load every lua_content file with every backend")
    c.add_argument("-v", "--verbose", action="store_true")
    c.set_defaults(func=cmd_check)
    sh = s.add_parser("show", help="data of a Lua file as compact JSON")
    sh.add_argument("path")
    sh.add_argument("--key", help="dotted path into the data, e.g. effects.0.ops")
    sh.add_argument("--keys", action="store_true", help="list keys with sizes only")
    sh.set_defaults(func=cmd_show)
    b = s.add_parser("bench", help="load time per backend")
    b.add_argument("path")
    b.add_argument("--repeat", type=int, default=5)
    b.set_defaults(func=cmd_bench)
