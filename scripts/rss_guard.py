#!/usr/bin/env python3
"""Run FreshGuard against curated RSS or Atom feeds without external packages.

Examples:
  python scripts/rss_guard.py --profile profiles/ai-research.json
  python scripts/rss_guard.py --feed https://export.arxiv.org/rss/cs.AI --hours 168 --min 1
"""
import argparse
import ipaddress
import json
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reference.python import search_template as freshguard

ALLOWED_SOURCE_TYPES = {"news", "government", "academic", "social", "blog", "other"}
ALLOWED_SOURCE_TIERS = {"primary", "official", "curated", "unrated"}
FEEDS: list[dict] = []
TIMEOUT_SECONDS = 20
MAX_ITEMS = 20
SUMMARY_CHARS = 600
MAX_FEED_BYTES = 2 * 1024 * 1024
ALLOW_HTTP = False
NETWORK_ATTEMPTS = 2


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def clean_text(value: str | None, limit: int = SUMMARY_CHARS) -> str | None:
    if not value:
        return None
    parser = _TextExtractor()
    parser.feed(value)
    text = " ".join(" ".join(parser.parts).split())
    if not text:
        return None
    return f"{text[:limit - 1].rstrip()}…" if len(text) > limit else text


def clean_summary(value: str | None) -> str | None:
    """Remove arXiv's feed wrapper while retaining the extractive abstract."""
    text = clean_text(value, limit=SUMMARY_CHARS)
    if text and text.startswith("arXiv:") and "Abstract:" in text:
        return text.split("Abstract:", 1)[1].strip() or None
    return text


def _local_name(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1].lower()


def _child(element: ET.Element, *names: str) -> ET.Element | None:
    wanted = {name.lower() for name in names}
    return next((node for node in element if _local_name(node) in wanted), None)


def _child_text(element: ET.Element, *names: str) -> str | None:
    node = _child(element, *names)
    return " ".join(node.itertext()).strip() if node is not None else None


def validate_feed_url(url: str, allow_http: bool = False) -> str:
    """Accept public HTTP(S) feed URLs; HTTPS is the safe default."""
    if not isinstance(url, str) or not url:
        raise ValueError("feed URL must be a non-empty string")
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("feed URL has an invalid port") from exc
    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if parsed.scheme not in allowed_schemes or not parsed.hostname or parsed.username or parsed.password:
        expected = "HTTP(S)" if allow_http else "HTTPS"
        raise ValueError(f"feed URL must be a public {expected} URL without embedded credentials")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("feed URL has an invalid port")
    host = parsed.hostname.lower()
    if host == "localhost" or host.endswith(".local"):
        raise ValueError("local feed hosts are not allowed")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError("non-public feed IP addresses are not allowed")
    except ValueError as exc:
        if str(exc) == "non-public feed IP addresses are not allowed":
            raise
    return url


def _validate_xml_input(raw: bytes) -> None:
    if len(raw) > MAX_FEED_BYTES:
        raise ValueError(f"feed exceeds {MAX_FEED_BYTES} byte safety limit")
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("feed contains forbidden XML entity declarations")


def parse_feed(raw: bytes, feed: dict) -> list[dict]:
    """Normalize RSS 2.0 and Atom XML into source-bound FreshGuard items."""
    _validate_xml_input(raw)
    root = ET.fromstring(raw)
    channel = _child(root, "channel")
    feed_root = channel if channel is not None else root
    source_url = feed["url"]
    source_name = feed.get("source_name") or _child_text(feed_root, "title") or urlparse(source_url).netloc
    entries = [node for node in root.iter() if _local_name(node) in {"item", "entry"}]
    items: list[dict] = []

    for entry in entries:
        title = clean_text(_child_text(entry, "title"), limit=300)
        link_node = _child(entry, "link")
        url = None
        if link_node is not None:
            url = link_node.get("href") or clean_text(link_node.text, limit=2000)
        published_at = _child_text(entry, "pubdate", "published", "updated", "date")
        summary = clean_summary(_child_text(entry, "description", "summary", "content"))
        if title and url:
            item = {
                "title": title,
                "url": url,
                "pub_date": published_at,
                "source_name": source_name,
                "source_type": feed.get("source_type", "news"),
                "source_tier": feed.get("source_tier", "unrated"),
            }
            if summary:
                item["summary"] = summary
            items.append(item)
    return items


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_feed_url(newurl, allow_http=ALLOW_HTTP)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch_feed(feed: dict) -> list[dict]:
    validate_feed_url(feed["url"], allow_http=ALLOW_HTTP)
    request = urllib.request.Request(
        feed["url"], headers={"User-Agent": "FreshGuard/2.0 (+https://github.com/York0912/freshguard)"}
    )
    for attempt in range(NETWORK_ATTEMPTS):
        try:
            opener = urllib.request.build_opener(_SafeRedirectHandler())
            with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                content_length = response.headers.get("Content-Length")
                if content_length and content_length.isdigit() and int(content_length) > MAX_FEED_BYTES:
                    raise ValueError(f"feed exceeds {MAX_FEED_BYTES} byte safety limit")
                raw = response.read(MAX_FEED_BYTES + 1)
            return parse_feed(raw, feed)
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt + 1 == NETWORK_ATTEMPTS:
                raise
            time.sleep(0.5)
    raise RuntimeError("unreachable")


def fetch() -> str:
    """Fetch configured feeds; fail loudly only when every source fails."""
    items: list[dict] = []
    failures: list[str] = []
    for feed in FEEDS:
        try:
            items.extend(_fetch_feed(feed))
        except Exception as exc:
            failures.append(f"{feed['url']}: {exc}")
    for failure in failures:
        print(f"  [rss] {failure}", file=sys.stderr)
    if not items and failures:
        raise RuntimeError("all feeds failed")
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    items.sort(key=lambda item: freshguard.parse_datetime(item.get("pub_date")) or minimum, reverse=True)
    return json.dumps(items[:MAX_ITEMS], ensure_ascii=False)


def parse(raw: str) -> list[dict]:
    return json.loads(raw)


def load_profile(path: str, allow_http: bool = False) -> tuple[str, list[dict], dict]:
    """Load and validate a portable JSON feed profile."""
    try:
        profile = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load profile: {exc}") from exc
    feeds = profile.get("feeds")
    if not isinstance(feeds, list) or not feeds:
        raise ValueError("profile must contain a non-empty feeds list")
    normalized = []
    for index, feed in enumerate(feeds, 1):
        if not isinstance(feed, dict):
            raise ValueError(f"profile feed {index} must be an object")
        try:
            url = validate_feed_url(feed.get("url"), allow_http=allow_http)
        except ValueError as exc:
            raise ValueError(f"profile feed {index}: {exc}") from exc
        source_type = feed.get("source_type", "news")
        source_tier = feed.get("source_tier", "unrated")
        if source_type not in ALLOWED_SOURCE_TYPES:
            raise ValueError(f"profile feed {index} has invalid source_type: {source_type}")
        if source_tier not in ALLOWED_SOURCE_TIERS:
            raise ValueError(f"profile feed {index} has invalid source_tier: {source_tier}")
        normalized.append({**feed, "url": url, "source_type": source_type, "source_tier": source_tier})
    return profile.get("name", Path(path).stem), normalized, profile.get("freshness", {})


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch curated RSS/Atom feeds, then run FreshGuard's evidence gate.")
    parser.add_argument("--profile", help="JSON feed profile")
    parser.add_argument("--feed", action="append", default=[], help="RSS or Atom URL; repeat for multiple feeds")
    parser.add_argument("--timeout", type=int, default=20, help="per-feed timeout in seconds")
    parser.add_argument("--allow-http", action="store_true", help="allow HTTP feeds (unsafe; HTTPS is the default)")
    parser.add_argument("--max-items", type=int, help="maximum newest items passed to the LLM")
    parser.add_argument("--summary-chars", type=int, default=600, help="maximum extracted summary length per item")
    parser.add_argument("--hours", type=int, help="freshness window; overrides profile default")
    parser.add_argument("--min", dest="minimum", type=int, help="minimum fresh items; overrides profile default")
    parser.add_argument("--state-file", help="SQLite path for cross-run URL deduplication")
    parser.add_argument("--force-if-critical", default="", help="comma-separated fresh-title bypass keywords")
    options = parser.parse_args()
    if options.timeout < 1 or options.summary_chars < 1:
        parser.error("--timeout and --summary-chars must be at least 1")

    profile_name, profile_feeds, profile_freshness = "Custom feeds", [], {}
    if options.profile:
        try:
            profile_name, profile_feeds, profile_freshness = load_profile(options.profile, allow_http=options.allow_http)
        except ValueError as exc:
            parser.error(str(exc))
    try:
        direct_feeds = [{"url": validate_feed_url(url, options.allow_http), "source_type": "news", "source_tier": "unrated"} for url in options.feed]
    except ValueError as exc:
        parser.error(str(exc))
    selected_feeds = [*profile_feeds, *direct_feeds]
    if not selected_feeds:
        parser.error("provide --profile or at least one --feed")

    hours = options.hours if options.hours is not None else profile_freshness.get("hours", 48)
    minimum = options.minimum if options.minimum is not None else profile_freshness.get("min_items", 2)
    max_items = options.max_items if options.max_items is not None else profile_freshness.get("max_items", 20)
    if not all(isinstance(value, int) and value >= 1 for value in (hours, minimum, max_items)):
        parser.error("hours, min_items, and max_items must be positive integers")

    global FEEDS, TIMEOUT_SECONDS, MAX_ITEMS, SUMMARY_CHARS, ALLOW_HTTP
    FEEDS = selected_feeds
    TIMEOUT_SECONDS = options.timeout
    MAX_ITEMS = max_items
    SUMMARY_CHARS = options.summary_chars
    ALLOW_HTTP = options.allow_http
    freshguard.fetch = fetch
    freshguard.parse = parse
    freshguard.VERSION = "2.1.0"
    sys.argv = [sys.argv[0], "--hours", str(hours), "--min", str(minimum)]
    if options.state_file:
        sys.argv.extend(["--state-file", options.state_file])
    if options.force_if_critical:
        sys.argv.extend(["--force-if-critical", options.force_if_critical])
    print(f"  [profile] {profile_name}: {len(selected_feeds)} feed(s), max {max_items} items", file=sys.stderr)
    freshguard.main()


if __name__ == "__main__":
    main()
