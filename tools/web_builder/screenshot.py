"""Скриншоты веб-билдера (Flet web) через Playwright - без доступа к CDN Flutter.

Сервер билдера должен уже работать:
    python tools/web_builder/app.py --web --renderer canvaskit &
    python tools/web_builder/screenshot.py --out shot.png --template lost_my_self.attack \
        --click "Тест в тренировочной комнате" --click "Проверить предмет (itemcheck)"

Flutter грузит CanvasKit и шрифт Roboto с gstatic.com; здесь эти запросы
отдаются локально: CanvasKit - из пакета flet-web, шрифт - системный с
кириллицей (DejaVu Sans). Кнопки и поля нажимаются через дерево доступности
Flutter (flt-semantics), по тем же подписям, что видит человек.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

FONT_CANDIDATES = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                   "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
CHROMIUM = "/opt/pw-browsers/chromium"


def _canvaskit_dir() -> Path:
    import flet_web
    return Path(flet_web.__file__).parent / "web" / "canvaskit"


def _route_cdn(page):
    ck = _canvaskit_dir()
    font = next((Path(f) for f in FONT_CANDIDATES if Path(f).exists()), None)

    def canvaskit(route):
        rel = re.sub(r"^https://www\.gstatic\.com/flutter-canvaskit/[0-9a-f]+/", "", route.request.url)
        path = ck / rel
        if path.exists():
            ctype = "application/wasm" if path.suffix == ".wasm" else "text/javascript"
            route.fulfill(status=200, body=path.read_bytes(), headers={"content-type": ctype})
        else:
            route.abort()

    page.route(re.compile(r"https://www\.gstatic\.com/flutter-canvaskit/.*"), canvaskit)
    page.route(re.compile(r"https://fonts\.gstatic\.com/.*"),
               lambda r: r.fulfill(status=200, body=font.read_bytes(), headers={"content-type": "font/ttf"})
               if font else r.abort())


def shoot(url: str, out: str, templates: list[str] = (), clicks: list[str] = (), width: int = 1700,
          height: int = 2300, wait_ms: int = 4000) -> list[str]:
    """Высокий вьюпорт: Flutter отдаёт в дерево доступности только видимое,
    а кнопки действий внизу формы."""
    from playwright.sync_api import sync_playwright
    log = []
    with sync_playwright() as p:
        kwargs = {"executable_path": CHROMIUM} if Path(CHROMIUM).exists() else {}
        browser = p.chromium.launch(args=["--use-gl=swiftshader", "--enable-unsafe-swiftshader"], **kwargs)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.on("requestfailed", lambda r: log.append(f"failed: {r.url}"))
        _route_cdn(page)
        page.goto(url, wait_until="networkidle")
        page.wait_for_selector("flt-semantics-placeholder, flutter-view", timeout=30000)
        page.wait_for_timeout(wait_ms)
        placeholder = page.locator("flt-semantics-placeholder")
        if placeholder.count():  # включить дерево доступности Flutter (роли и подписи в DOM)
            placeholder.dispatch_event("click")
            page.wait_for_timeout(1000)
        for tid in templates:
            # у выпадающего списка шаблонов нет подписи в дереве доступности:
            # это кнопка сразу после «удалить эффект»; пункты меню - кнопки с именем шаблона
            buttons = page.get_by_role("button")
            texts = [buttons.nth(i).inner_text() for i in range(buttons.count())]
            buttons.nth(texts.index("удалить эффект") + 1).click()
            page.wait_for_timeout(1000)
            page.get_by_role("button", name=tid, exact=True).first.click()
            page.wait_for_timeout(1500)
            log.append(f"template: {tid}")
        for text in clicks:
            page.get_by_role("button", name=text).first.click()
            page.wait_for_timeout(2500)
            log.append(f"clicked: {text}")
        page.screenshot(path=out)
        browser.close()
    return log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default="http://127.0.0.1:8550/")
    ap.add_argument("--out", default="dev_probe_output/builder_web.png")
    ap.add_argument("--template", action="append", default=[], help="catalog template to add (repeatable)")
    ap.add_argument("--click", action="append", default=[], help="button text to click (repeatable)")
    args = ap.parse_args(argv)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    for line in shoot(args.url, args.out, args.template, args.click):
        print(line)
    print(f"screenshot: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
