#!/usr/bin/env python3
"""Render the committed FreshGuard terminal demo GIF.

Maintainer-only helper: requires Pillow. It is intentionally separate from the
zero-dependency FreshGuard runtime.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "assets" / "freshguard-demo.gif"
WIDTH, HEIGHT = 960, 540
BG = "#0b1020"
PANEL = "#111a2e"
PANEL_EDGE = "#263653"
TEXT = "#dbeafe"
MUTED = "#93a4be"
GREEN = "#5eead4"
YELLOW = "#fde68a"
RED = "#fca5a5"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    names = ("consolab.ttf", "Consolas Bold.ttf") if bold else ("consola.ttf", "Consolas.ttf")
    for name in names:
        path = Path("C:/Windows/Fonts") / name
        if path.exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


FONT = _font(20)
SMALL = _font(15)
TITLE = _font(25, bold=True)


def _terminal(lines: list[tuple[str, str]], footer: str) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((54, 42, WIDTH - 54, HEIGHT - 42), radius=18, fill=PANEL, outline=PANEL_EDGE, width=2)
    draw.rounded_rectangle((54, 42, WIDTH - 54, 94), radius=18, fill="#17233d")
    draw.rectangle((54, 76, WIDTH - 54, 94), fill="#17233d")
    for x, color in ((82, "#fb7185"), (108, "#fbbf24"), (134, "#4ade80")):
        draw.ellipse((x, 60, x + 14, 74), fill=color)
    draw.text((170, 57), "FreshGuard  /  deterministic demo", font=SMALL, fill=MUTED)
    y = 124
    for text, color in lines:
        draw.text((86, y), text, font=FONT, fill=color)
        y += 38
    draw.line((86, HEIGHT - 94, WIDTH - 86, HEIGHT - 94), fill=PANEL_EDGE, width=1)
    draw.text((86, HEIGHT - 78), footer, font=SMALL, fill=MUTED)
    return image


def frames() -> tuple[list[Image.Image], list[int]]:
    """Return a deterministic 17-second narrative with no live feed content."""
    scenes = [
        ([
            ("FRESHGUARD", GREEN),
            ("Collect. Gate. Render. Or stay silent.", TEXT),
            ("", TEXT),
            ("A short, deterministic terminal walkthrough", MUTED),
        ], "No network request is made in this demo."),
        ([
            ("$ python scripts/rss_guard.py --profile profiles/ai-research.json", TEXT),
            ("  --state-file .freshguard/seen.sqlite > evidence.json", TEXT),
            ("", TEXT),
            ("Collecting curated public RSS / Atom sources...", MUTED),
        ], "Input: portable profile  |  Output: source-bound evidence JSON"),
        ([
            ("$ python scripts/rss_guard.py --profile profiles/ai-research.json", TEXT),
            ("[PASS] 3 FRESH ITEMS / 3 DECLARED SOURCES", GREEN),
            ("[PASS] HTTPS + size + XML safety checks", GREEN),
            ("[PASS] provenance labels preserved", GREEN),
        ], "Only evidence that meets the gate continues."),
        ([
            ("evidence.json", YELLOW),
            ("  title        Example research update", TEXT),
            ("  source_tier  primary", TEXT),
            ("  published_at 2026-07-14 UTC", TEXT),
            ("  _sl          [S:source.example|D:2026-07-14|F:Y]", TEXT),
        ], "Illustrative fixture only — not a live result."),
        ([
            ("$ python scripts/render_briefing.py --input evidence.json", TEXT),
            ("  --output digest.md --title \"AI research watch\"", TEXT),
            ("", TEXT),
            ("Rendering extractive Markdown — no new claims added...", MUTED),
        ], "The renderer carries the source label forward."),
        ([
            ("# AI research watch", YELLOW),
            ("Generated from 3 fresh item(s).", TEXT),
            ("## Example research update", TEXT),
            ("Primary source · primary · 2026-07-14 UTC", MUTED),
            ("Source label: [S:source.example|D:2026-07-14|F:Y]", GREEN),
        ], "Output is reviewable before any LLM or delivery step."),
        ([
            ("$ python scripts/rss_guard.py ...", TEXT),
            ("NO_NEW_CONTENT", YELLOW),
            ("", TEXT),
            ("No briefing is invented. No external message is sent.", TEXT),
            ("→ stay silent", GREEN),
        ], "FreshGuard keeps silence distinct from SEARCH_ERROR."),
    ]
    durations = [2300, 2100, 2400, 2600, 2100, 2900, 2600]
    return [_terminal(lines, footer) for lines, footer in scenes], durations


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the deterministic FreshGuard demo GIF.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    options = parser.parse_args()
    images, durations = frames()
    options.output.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        options.output,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(f"Wrote {options.output} ({sum(durations) / 1000:.1f}s, {len(images)} frames)")


if __name__ == "__main__":
    main()
