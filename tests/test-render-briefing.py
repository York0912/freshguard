import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("render_briefing", ROOT / "scripts" / "render_briefing.py")
renderer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(renderer)

PASS = 0
FAIL = 0


def check(name, ok):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


def test_extract_rendering():
    payload = {
        "fresh_count": 1,
        "items": [{
            "title": "Example title",
            "url": "https://example.com/item",
            "published_at": "2026-07-15T08:00:00+00:00",
            "fresh": True,
            "source_name": "Example source",
            "source_tier": "primary",
            "summary": "Extractive source summary.",
            "_sl": "[S:example.com|D:2026-07-15|F:Y]",
        }],
    }
    rendered = renderer.render(json.dumps(payload), "Test digest")
    check("Renderer keeps summary, tier, date, and source label", all(value in rendered for value in ("Extractive source summary.", "primary", "2026-07-15 UTC", "[S:example.com|D:2026-07-15|F:Y]")))


def test_silent_rendering():
    rendered = renderer.render("NO_NEW_CONTENT", "Test digest")
    check("Renderer produces an explicit silent artifact", "No new items met the freshness threshold" in rendered)


def test_windows_utf16_input():
    payload = json.dumps({"fresh_count": 0, "items": []})
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "evidence.json"
        path.write_bytes(b"\xff\xfe" + payload.encode("utf-16-le"))
        rendered = renderer.render(renderer._read_input(str(path)), "Test digest")
    check("Renderer accepts PowerShell UTF-16 redirection", "Generated from 0 fresh item(s)." in rendered)


def test_untrusted_markdown_is_escaped():
    payload = {
        "fresh_count": 1,
        "items": [{
            "title": "Unsafe](https://bad.example)",
            "url": "https://example.com/item",
            "fresh": True,
            "source_name": "Source",
            "summary": "![tracker](https://bad.example/pixel)",
            "_sl": "[S:https://example.com/item|D:|F:Y]",
        }],
    }
    rendered = renderer.render(json.dumps(payload), "Test digest")
    check("Renderer escapes remote Markdown", "![tracker]" not in rendered and "Unsafe](https" not in rendered and "Source: <https://example.com/item>" in rendered)
    payload["items"][0]["url"] = "javascript:alert(1)"
    try:
        renderer.render(json.dumps(payload), "Test digest")
        invalid_rejected = False
    except ValueError:
        invalid_rejected = True
    check("Renderer rejects invalid evidence URLs", invalid_rejected)


if __name__ == "__main__":
    print("\n=== FreshGuard Renderer Test Suite ===\n")
    test_extract_rendering()
    test_silent_rendering()
    test_windows_utf16_input()
    test_untrusted_markdown_is_escaped()
    print(f"\n=== Result: {PASS} passed, {FAIL} failed ===\n")
    sys.exit(1 if FAIL else 0)
