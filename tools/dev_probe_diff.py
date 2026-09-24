#!/usr/bin/env python3
"""Delta-only comparison between two tools/dev_probe.py runs.

Without this, comparing "before my fix" vs "after my fix" means opening both
summary.md files in full (Config/Timeline/Combat totals/Player HP/Issues
detected/Screenshots - typically 20-60 lines each) and reasoning over the
diff yourself. This reads each run's summary.json instead (a few plain
fields dev_probe.py already computed in finish()) and prints ONLY what
changed - usually a handful of lines, sometimes "No differences" - no image
opening involved even when screenshot counts differ (see --before/--after
screenshot reason counts, not the images themselves).

--frames additionally compares the screenshots pairwise (frame_NNN of both
runs - with --fast --seed they are taken at identical game times): perceptual
hash distance (rust_core.ProbeAnalyzer when built) + share of changed pixels
and their bounding box, printed as text. An image is produced ONLY for frames
that actually changed (frames_diff.jpg: before | after | changes in red), so
an unchanged visual costs zero image tokens.

Usage:
    .venv/Scripts/python.exe tools/dev_probe_diff.py --before dev_probe_output/2026...aaa --after dev_probe_output/2026...bbb
    python tools/dev_probe_diff.py --before A --after B --frames
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _dev_probe_compare import diff_is_empty, diff_summaries, format_diff  # noqa: E402


def load_summary(run_dir):
    path = Path(run_dir) / "summary.json"
    if not path.exists():
        print(f"error: {path} not found (run tools/dev_probe.py first, or check the path)", file=sys.stderr)
        sys.exit(2)
    return json.loads(path.read_text(encoding="utf-8"))


# Порог "кадр изменился": измерено на детерминированных прогонах (--fast --seed):
# один seed даёт <=17 бит из 256 и <=0.4% пикселей (дрожит анимация героя).
HASH_CHANGED_BITS = 24
PIXELS_CHANGED_RATIO = 0.01
PIXEL_DELTA = 24  # 0-255 после размытия - шум JPEG ниже


def _frame_pairs(before, after):
    names = sorted(p.name for p in Path(before).glob("frame_*.jpg"))
    return [(Path(before) / n, Path(after) / n) for n in names if (Path(after) / n).exists()]


def compare_frames(before, after, out_image=None):
    """-> (lines, changed_count). Текст для агента + картинка только изменений."""
    try:
        from PIL import Image, ImageChops, ImageFilter
    except ImportError:
        return ["frames: skipped (needs Pillow: pip install -r tools/requirements-dev.txt)"], 0
    try:
        from rust_core import ProbeAnalyzer
    except ImportError:
        ProbeAnalyzer = None
    pairs = _frame_pairs(before, after)
    if not pairs:
        return ["frames: none to compare (run dev_probe with --render offscreen/window)"], 0
    rows, changed = [], []
    for a, b in pairs:
        ham = None
        if ProbeAnalyzer is not None:
            ha = ProbeAnalyzer(None).analyze_frame(a.read_bytes()).get("perceptual_hash")
            hb = ProbeAnalyzer(None).analyze_frame(b.read_bytes()).get("perceptual_hash")
            if ha and hb:
                ham = ProbeAnalyzer.hamming_distance(ha, hb)
        with Image.open(a) as ia, Image.open(b) as ib:
            ga = ia.convert("L").filter(ImageFilter.BoxBlur(2))
            gb = ib.convert("L").resize(ga.size).filter(ImageFilter.BoxBlur(2))
            mask = ImageChops.difference(ga, gb).point(lambda v: 255 if v > PIXEL_DELTA else 0)
            ratio = mask.histogram()[255] / (ga.width * ga.height)
            bbox = mask.getbbox()
            is_changed = ratio > PIXELS_CHANGED_RATIO or (ham is not None and ham > HASH_CHANGED_BITS)
            rows.append((a.name, ham, ratio, bbox, is_changed))
            if is_changed:
                changed.append((ia.convert("RGB"), ib.convert("RGB").resize(ia.size), mask, a.name))
    lines = [f"frames: {len(pairs)} compared, {len(changed)} visually changed "
             f"(hash >{HASH_CHANGED_BITS}/256 bits or >{PIXELS_CHANGED_RATIO:.0%} pixels)"]
    for name, ham, ratio, bbox, is_changed in rows:
        if is_changed:
            lines.append(f"  {name}: CHANGED {ratio:.1%} px" + (f", hash {ham} bits" if ham is not None else "")
                         + (f", region {bbox}" if bbox else ""))
    if changed and out_image:
        thumb_w = 360
        cells = []
        for ia, ib, mask, name in changed[:6]:
            h = int(ia.height * thumb_w / ia.width)
            red = Image.new("RGB", ia.size, (255, 0, 0))
            overlay = Image.composite(red, ib, mask.convert("L"))
            cells.append([im.resize((thumb_w, h)) for im in (ia, ib, Image.blend(ib, overlay, 0.6))])
        h = cells[0][0].height
        sheet = Image.new("RGB", (thumb_w * 3, h * len(cells)), (20, 20, 20))
        for r, row in enumerate(cells):
            for c, im in enumerate(row):
                sheet.paste(im, (c * thumb_w, r * h))
        sheet.save(out_image, quality=85)
        lines.append(f"  side-by-side of changed frames (before | after | diff): {out_image}")
    return lines, len(changed)


def main():
    if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--before", required=True, help="a dev_probe.py output directory (the earlier run)")
    parser.add_argument("--after", required=True, help="a dev_probe.py output directory (the later run)")
    parser.add_argument("--frames", action="store_true",
                        help="also compare screenshots pairwise; an image is written only for changed frames")
    args = parser.parse_args()

    before = load_summary(args.before)
    after = load_summary(args.after)
    diff = diff_summaries(before, after)

    print(f"Comparing {args.before} -> {args.after}\n")
    print(format_diff(diff, before_label=args.before, after_label=args.after))
    frames_changed = 0
    if args.frames:
        lines, frames_changed = compare_frames(args.before, args.after, Path(args.after) / "frames_diff.jpg")
        print("\n".join(lines))
    sys.exit(0 if diff_is_empty(diff) and not frames_changed else 1)


if __name__ == "__main__":
    main()
