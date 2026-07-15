#!/usr/bin/env python3
"""Render FreshGuard JSON into an extractive, source-bound Markdown digest."""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


def _read_input(path: str | None) -> str:
    if not path:
        return sys.stdin.read()
    raw = Path(path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def _date(value: str | None) -> str:
    if not value:
        return "date unverified"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%Y-%m-%d UTC")
    except ValueError:
        return "date unverified"


def _escape_markdown(value: object) -> str:
    """Render remote feed text as text, never executable Markdown syntax."""
    text = " ".join(str(value).split())
    return "".join(f"\\{char}" if char in "\\`*_[]<>!" else char for char in text)


def _safe_url(value: object) -> str:
    url = str(value)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or any(char.isspace() or char in "<>" for char in url):
        raise ValueError("evidence contains an invalid URL")
    return url


def _inline_code(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("`", "\\`")


def render(raw: str, title: str) -> str:
    if raw.strip() == "NO_NEW_CONTENT":
        return f"# {title}\n\n_No new items met the freshness threshold._\n"
    if raw.strip().startswith("SEARCH_"):
        raise ValueError(raw.strip())
    payload = json.loads(raw)
    lines = [f"# {_escape_markdown(title)}", "", f"Generated from {payload.get('fresh_count', 0)} fresh item(s)."]
    for item in payload.get("items", []):
        if item.get("fresh") is not True:
            continue
        lines.extend(
            [
                "",
                f"## {_escape_markdown(item.get('title', 'Untitled item'))}",
                f"{_escape_markdown(item.get('source_name', 'Unknown source'))} · {_escape_markdown(item.get('source_tier', 'unrated'))} · {_date(item.get('published_at'))}",
                f"Source: <{_safe_url(item.get('url', ''))}>",
                "",
                _escape_markdown(item["summary"]) if item.get("summary") else "_Title-only item; inspect the source before drawing conclusions._",
                "",
                f"Source label: `{_inline_code(item.get('_sl', 'unavailable'))}`",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Render FreshGuard JSON as an extractive Markdown digest.")
    parser.add_argument("--input", help="FreshGuard JSON file; omit to read stdin")
    parser.add_argument("--output", help="Markdown output file; omit to write stdout")
    parser.add_argument("--title", default="FreshGuard evidence digest")
    options = parser.parse_args()
    try:
        rendered = render(_read_input(options.input), options.title)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"RENDER_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
    if options.output:
        Path(options.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
