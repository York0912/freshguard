import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from reference.python import search_template as fg

FAIL = 0
PASS = 0


def check(name, ok):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


def run_main(items, args):
    """Run the public CLI with deterministic fixture data and capture stdout."""
    original = {
        "fetch": fg.fetch,
        "parse": fg.parse,
        "argv": sys.argv,
        "window": fg.WINDOW_HOURS,
        "minimum": fg.MIN_ITEMS,
        "state": fg.STATE_FILE,
        "keywords": fg.FORCE_KEYWORDS,
    }
    stdout, stderr = io.StringIO(), io.StringIO()
    try:
        fg.fetch = lambda: "fixture"
        fg.parse = lambda raw: [dict(item) for item in items]
        sys.argv = ["freshguard", *args]
        with redirect_stdout(stdout), redirect_stderr(stderr):
            fg.main()
        return stdout.getvalue().strip(), stderr.getvalue().strip()
    finally:
        fg.fetch = original["fetch"]
        fg.parse = original["parse"]
        sys.argv = original["argv"]
        fg.WINDOW_HOURS = original["window"]
        fg.MIN_ITEMS = original["minimum"]
        fg.STATE_FILE = original["state"]
        fg.FORCE_KEYWORDS = original["keywords"]


def test_date_parsing():
    check("ISO 8601 with Z", fg.parse_datetime("2026-07-14T08:00:00Z") is not None)
    check("ISO 8601 with offset", fg.parse_datetime("2026-07-14T08:00:00+08:00") is not None)
    check("RFC 2822", fg.parse_datetime("Tue, 14 Jul 2026 08:00:00 +0000") is not None)
    check("Chinese format", fg.parse_datetime("2026-07-14 08:00:00") is not None)
    check("Date only", fg.parse_datetime("2026-07-14") is not None)
    check("Invalid returns None", fg.parse_datetime("not a date") is None)


def test_freshness():
    items = [
        {"pub_date": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()},
        {"pub_date": (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()},
        {"pub_date": None},
    ]
    checked = fg.check_freshness(items)
    check("Fresh item", checked[0].get("fresh") is True)
    check("Stale item", checked[1].get("fresh") is False)
    check("Unknown date", checked[2].get("fresh") is None)


def test_end_to_end():
    now = datetime.now(timezone.utc).isoformat()
    fresh = [{"title": "Fresh sample", "url": "https://example.com/fresh", "pub_date": now}]

    stdout, stderr = run_main(fresh, ["--hours", "48", "--min", "1"])
    payload = json.loads(stdout)
    evidence = payload["items"][0]
    check("Fresh data emits JSON", payload["fresh_count"] == 1 and stderr == "")
    check(
        "Evidence fields are complete",
        all(evidence.get(key) for key in ("id", "title", "url", "retrieved_at", "_sl", "_cutoff"))
        and evidence["fresh"] is True,
    )

    stale = [{"title": "Old sample", "url": "https://example.com/old", "pub_date": "2020-01-01T00:00:00Z"}]
    stdout, _ = run_main(stale, ["--hours", "48", "--min", "1"])
    check("Stale data stays silent", stdout == "NO_NEW_CONTENT")

    critical = [{"title": "Service outage reported", "url": "https://example.com/outage", "pub_date": now}]
    stdout, _ = run_main(critical, ["--hours", "48", "--min", "2", "--force-if-critical", "outage,incident"])
    check("Fresh critical item bypasses threshold", json.loads(stdout)["fresh_count"] == 1)

    with tempfile.TemporaryDirectory() as temp_dir:
        state_file = os.path.join(temp_dir, "seen.sqlite")
        run_main(fresh, ["--hours", "48", "--min", "1", "--state-file", state_file])
        stdout, _ = run_main(fresh, ["--hours", "48", "--min", "1", "--state-file", state_file])
        check("Duplicate item stays silent", stdout == "NO_NEW_CONTENT")


if __name__ == "__main__":
    print("\n=== FreshGuard Test Suite ===\n")
    test_date_parsing()
    test_freshness()
    test_end_to_end()
    print(f"\n=== Result: {PASS} passed, {FAIL} failed ===\n")
    sys.exit(1 if FAIL else 0)
