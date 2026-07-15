import importlib.util
import io
import json
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rss_guard", ROOT / "scripts" / "rss_guard.py")
rss_guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rss_guard)

PASS = 0
FAIL = 0

RSS = b"""<?xml version='1.0'?><rss><channel><title>Example RSS</title><item><title>Fresh RSS item</title><link>https://example.com/rss-item</link><pubDate>Tue, 15 Jul 2026 08:00:00 +0000</pubDate><description>Short <b>extractive</b> summary.</description></item></channel></rss>"""
ATOM = b"""<?xml version='1.0'?><feed xmlns='http://www.w3.org/2005/Atom'><title>Example Atom</title><entry><title>Fresh Atom item</title><link href='https://example.com/atom-item'/><published>2026-07-15T08:00:00Z</published><summary>Atom summary.</summary></entry></feed>"""


def check(name, ok):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


def test_parsers():
    feed = {"url": "https://example.com/rss", "source_type": "academic", "source_tier": "primary"}
    rss_item = rss_guard.parse_feed(RSS, feed)[0]
    check(
        "RSS preserves extractive summary and provenance",
        rss_item["summary"] == "Short extractive summary." and rss_item["source_tier"] == "primary",
    )
    atom_item = rss_guard.parse_feed(ATOM, feed)[0]
    check(
        "Atom item normalized",
        atom_item["url"] == "https://example.com/atom-item" and atom_item["pub_date"].endswith("Z"),
    )
    check(
        "arXiv feed wrapper is removed from summaries",
        rss_guard.clean_summary("arXiv:2607.00001v1 Announce Type: new Abstract: Useful abstract.") == "Useful abstract.",
    )
    try:
        rss_guard.parse_feed(b"<!DOCTYPE rss [<!ENTITY bomb 'x'>]><rss/>", feed)
        blocked_xml = False
    except ValueError:
        blocked_xml = True
    check("XML entity declarations are rejected", blocked_xml)
    try:
        rss_guard.validate_feed_url("http://example.com/feed")
        blocked_http = False
    except ValueError:
        blocked_http = True
    check("HTTPS is required by default", blocked_http and rss_guard.validate_feed_url("https://example.com/feed") == "https://example.com/feed")


def test_profile_loader():
    profile = {
        "name": "Fixture profile",
        "freshness": {"hours": 72, "min_items": 1, "max_items": 3},
        "feeds": [{"url": "https://example.com/rss", "source_type": "academic", "source_tier": "primary"}],
    }
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "profile.json"
        path.write_text(json.dumps(profile), encoding="utf-8")
        name, feeds, freshness = rss_guard.load_profile(str(path))
    check("Profile validates defaults", name == "Fixture profile" and feeds[0]["source_tier"] == "primary" and freshness["hours"] == 72)
    insecure = {**profile, "feeds": [{"url": "http://example.com/rss"}]}
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "insecure-profile.json"
        path.write_text(json.dumps(insecure), encoding="utf-8")
        try:
            rss_guard.load_profile(str(path))
            rejected = False
        except ValueError:
            rejected = True
    check("Profile rejects insecure HTTP by default", rejected)


def test_cli():
    now = datetime.now(timezone.utc).isoformat()
    fresh_items = [
        {"title": "Newest feed item", "url": "https://example.com/new", "pub_date": now, "source_name": "Fixture", "source_type": "news", "source_tier": "official", "summary": "Verified fixture summary."},
        {"title": "Another fresh item", "url": "https://example.com/another", "pub_date": now, "source_name": "Fixture", "source_type": "news", "source_tier": "official"},
    ]
    old_argv = sys.argv
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        sys.argv = ["rss_guard.py", "--feed", "https://example.com/rss", "--hours", "48", "--min", "1", "--max-items", "1"]
        with patch.object(rss_guard, "_fetch_feed", return_value=fresh_items), redirect_stdout(stdout), redirect_stderr(stderr):
            rss_guard.main()
    finally:
        sys.argv = old_argv
    payload = json.loads(stdout.getvalue())
    item = payload["items"][0]
    check(
        "CLI emits bounded source-bound evidence",
        payload["fresh_count"] == 1 and payload["total_count"] == 1 and item["source_tier"] == "official" and item["summary"] == "Verified fixture summary.",
    )
    check("CLI diagnostics stay on stderr", "[profile]" in stderr.getvalue())


if __name__ == "__main__":
    print("\n=== FreshGuard RSS Test Suite ===\n")
    test_parsers()
    test_profile_loader()
    test_cli()
    print(f"\n=== Result: {PASS} passed, {FAIL} failed ===\n")
    sys.exit(1 if FAIL else 0)
