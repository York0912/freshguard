#!/usr/bin/env python3
"""
FreshGuard — Search Script Template (Python Reference Implementation)

Internal pipeline:
  Fetcher → Normalizer → Validator → [Dedup] → FreshnessEvaluator → EvidenceBuilder

Public interface (stable, override these):
  fetch()              collect raw data from sources
  parse()              convert raw data to list[dict]
  parse_datetime()     parse date strings
  check_freshness()    evaluate freshness per item
  deduplicate()        cross-round URL dedup
  has_critical()       bypass threshold for keywords

CLI: --hours --min --state-file --force-if-critical
Tests: import parse_datetime, check_freshness (unchanged)

stdout:
  JSON (with metadata + items)  → fresh data found, proceed to LLM
  NO_NEW_CONTENT                → no fresh data, LLM skips (exit 0)
  SEARCH_ERROR                  → infra failure (exit 1)

stderr: diagnostics only (never pollutes data stream)
"""
import json, sys, argparse, time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import sqlite3, pathlib, hashlib

VERSION = "2.1.0"
SCHEMA_VERSION = "1.0"


# ── Defaults (overridden by CLI) ──────────────────────────────
WINDOW_HOURS = 48
MIN_ITEMS = 2
STATE_FILE = None
FORCE_KEYWORDS = ""

CHINA_TZ = timezone(timedelta(hours=8))


# ══════════════════════════════════════════════════════════════
# Public API — override for your data sources
# ══════════════════════════════════════════════════════════════

def fetch() -> str:
    """Collect raw data from sources. Override for your API/RSS/DB."""
    raise NotImplementedError


def parse(raw: str) -> list[dict]:
    """Convert raw response to [{title, url, pub_date, ...}]. Override."""
    return []


# ══════════════════════════════════════════════════════════════
# Public Helpers — stable, used by tests directly
# ══════════════════════════════════════════════════════════════

def parse_datetime(dt_str: str) -> datetime | None:
    """Parse ISO 8601, RFC 2822, Chinese 'YYYY-MM-DD HH:MM:SS', or date-only.
    Naive dates → assume China time (UTC+8) → convert to UTC.
    """
    tz_strategies = [
        lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")),
        lambda s: parsedate_to_datetime(s),
    ]
    for fn in tz_strategies:
        try:
            result = fn(dt_str)
            if result.tzinfo is not None:
                return result.astimezone(timezone.utc)
        except (ValueError, TypeError, IndexError):
            continue
    naive_strategies = [
        lambda s: datetime.strptime(s.replace("T", " "), "%Y-%m-%d %H:%M:%S"),
        lambda s: datetime.strptime(s, "%Y-%m-%d"),
    ]
    for fn in naive_strategies:
        try:
            result = fn(dt_str)
            return result.replace(tzinfo=CHINA_TZ).astimezone(timezone.utc)
        except (ValueError, TypeError, IndexError):
            continue
    return None


def _item_get(item, key: str, default=None):
    """Read a field from a dict or the internal Evidence carrier."""
    if isinstance(item, dict):
        return item.get(key, default)
    if key == "pub_date":
        return getattr(item, "published_at", default)
    return getattr(item, key, default)


def _item_set(item, key: str, value) -> None:
    """Write a field to a dict or the internal Evidence carrier."""
    if isinstance(item, dict):
        item[key] = value
    else:
        setattr(item, key, value)


def check_freshness(items: list) -> list:
    """Tag each item with 'fresh' (bool|None) and '_cutoff'."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    for item in items:
        dt = _item_get(item, "pub_date")
        _item_set(item, "_cutoff", cutoff.isoformat())
        if dt:
            parsed = parse_datetime(dt)
            if parsed is not None:
                _item_set(item, "fresh", parsed >= cutoff)
                continue
        _item_set(item, "fresh", None)
    return items


def deduplicate(items: list) -> list:
    """Cross-round dedup via SQLite state file."""
    if not STATE_FILE:
        return items
    pathlib.Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(STATE_FILE)
    conn.execute("CREATE TABLE IF NOT EXISTS seen (url_hash TEXT PRIMARY KEY, first_seen TEXT)")
    deduped = []
    for item in items:
        url = _item_get(item, "url", "")
        h = hashlib.sha256(url.encode()).hexdigest()[:16]
        row = conn.execute("SELECT first_seen FROM seen WHERE url_hash = ?", (h,)).fetchone()
        if row:
            _item_set(item, "_dup", True)
        else:
            conn.execute("INSERT INTO seen (url_hash, first_seen) VALUES (?, ?)",
                         (h, datetime.now(timezone.utc).isoformat()))
            deduped.append(item)
    conn.commit()
    conn.close()
    if (n := len(items) - len(deduped)) > 0:
        print(f"  dedup: skipped {n} previously reported URLs", file=sys.stderr)
    return deduped


def has_critical(items: list, keywords_text: str | None = None) -> bool:
    """Bypass freshness threshold if a title contains a critical keyword."""
    keywords_text = FORCE_KEYWORDS if keywords_text is None else keywords_text
    if not keywords_text:
        return False
    keywords = [kw.strip() for kw in keywords_text.split(",") if kw.strip()]
    for item in items:
        if _item_get(item, "fresh") is True and any(kw in _item_get(item, "title", "") for kw in keywords):
            return True
    return False


# ══════════════════════════════════════════════════════════════
# Evidence Object — typed data carrier for the internal pipeline
# ══════════════════════════════════════════════════════════════

@dataclass
class Evidence:
    """Single evidence item conforming to schemas/evidence.schema.json."""
    id: str = ""
    title: str = ""
    url: str = ""
    source_name: str | None = None
    source_type: str | None = None
    source_tier: str | None = None
    summary: str | None = None
    published_at: str | None = None
    retrieved_at: str | None = None
    fresh: bool | None = None
    _sl: str | None = None
    _cutoff: str | None = None
    _dup: bool | None = None

    def __post_init__(self):
        # Preserve arbitrary fields from dict (pub_date, etc.)
        self._extra = {}

    @classmethod
    def from_dict(cls, d: dict) -> "Evidence":
        known = {"title", "url", "source_name", "source_type", "source_tier", "summary", "pub_date",
                 "published_at", "retrieved_at", "fresh", "_sl", "_cutoff", "_dup", "id"}
        raw_published_at = d.get("pub_date") or d.get("published_at")
        parsed_published_at = parse_datetime(raw_published_at) if raw_published_at else None
        obj = cls(
            title=d.get("title", ""),
            url=d.get("url", ""),
            source_name=d.get("source_name"),
            source_type=d.get("source_type"),
            source_tier=d.get("source_tier"),
            summary=d.get("summary"),
            published_at=parsed_published_at.isoformat() if parsed_published_at else None,
            retrieved_at=d.get("retrieved_at") or datetime.now(timezone.utc).isoformat(),
            fresh=d.get("fresh"),
            _sl=d.get("_sl"),
            _cutoff=d.get("_cutoff"),
            _dup=d.get("_dup"),
            id=d.get("id", ""),
        )
        obj._extra = {k: v for k, v in d.items() if k not in known}
        return obj

    def to_dict(self) -> dict:
        """Serialize to dict for JSON output."""
        d = {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "published_at": self.published_at,
            "retrieved_at": self.retrieved_at,
            "fresh": self.fresh,
        }
        if self.source_name is not None:
            d["source_name"] = self.source_name
        if self.source_type is not None:
            d["source_type"] = self.source_type
        if self.source_tier is not None:
            d["source_tier"] = self.source_tier
        if self.summary is not None:
            d["summary"] = self.summary
        if self._sl:
            d["_sl"] = self._sl
        if self._cutoff:
            d["_cutoff"] = self._cutoff
        if self._dup:
            d["_dup"] = True
        d.update(self._extra)
        return d


# ══════════════════════════════════════════════════════════════
# Internal Pipeline — single responsibility per step
# ══════════════════════════════════════════════════════════════

class Fetcher:
    """Step 1: Call search provider. Returns raw string."""
    def run(self) -> str:
        return fetch()


class Normalizer:
    """Step 2: Normalize provider output to uniform list[dict]."""
    def run(self, raw: str) -> list[dict]:
        return parse(raw)


class Validator:
    """Step 3: Schema, URL, timestamp validation only. No freshness logic."""
    def run(self, items: list[dict]) -> list[Evidence]:
        valid = []
        for d in items:
            if not d.get("title") or not d.get("url"):
                print(f"  [v] skipped: missing title or url", file=sys.stderr)
                continue
            url = d.get("url", "")
            if not url.startswith(("http://", "https://")):
                print(f"  [v] skipped: invalid protocol in URL", file=sys.stderr)
                continue
            pub = d.get("pub_date")
            if pub and parse_datetime(pub) is None:
                print(f"  [v] skipped: unparseable date: {pub[:50]}", file=sys.stderr)
                continue
            # Convert to Evidence object; internal pipeline uses Evidence from here
            valid.append(Evidence.from_dict(d))
        return valid


class FreshnessEvaluator:
    """Step 4: Evaluate freshness only."""
    def __init__(self, window_hours: int, min_items: int, force_keywords: str):
        self.window_hours = window_hours
        self.min_items = min_items
        self.force_keywords = force_keywords

    def run(self, items: list) -> list:
        return check_freshness(items)

    def is_acceptable(self, items: list) -> bool:
        fresh_count = sum(1 for item in items if _item_get(item, "fresh") is True)
        return fresh_count >= self.min_items or has_critical(items, self.force_keywords)


class EvidenceBuilder:
    """Step 5: Build search output with metadata and evidence array."""
    def run(self, items: list, start_time: float) -> dict:
        evidence_list = []
        for idx, item in enumerate(items, 1):
            # Accept both Evidence objects and raw dicts (backward compat)
            if isinstance(item, Evidence):
                ev = item
                ev.id = f"ev_{idx:03d}"
            else:
                ev = Evidence.from_dict(item)
                ev.id = f"ev_{idx:03d}"

            ev._sl = _build_source_label(ev)
            evidence_list.append(ev.to_dict())

        fresh_count = sum(1 for e in evidence_list if e.get("fresh") is True)

        return {
            "version": VERSION,
            "schema_version": SCHEMA_VERSION,
            "elapsed_ms": int((time.time() - start_time) * 1000),
            "fresh_count": fresh_count,
            "total_count": len(evidence_list),
            "window_hours": WINDOW_HOURS,
            "min_items": MIN_ITEMS,
            "items": evidence_list,
        }


def _build_source_label(ev: Evidence) -> str:
    date = ev.published_at or ""
    fresh = ("Y" if ev.fresh is True else "N" if ev.fresh is False else "?")
    return f"[S:{ev.url}|D:{date}|F:{fresh}]"


# ══════════════════════════════════════════════════════════════
# CLI Entry Point
# ══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="FreshGuard search script")
    parser.add_argument("--hours", type=int, default=48, help="Freshness window (hours)")
    parser.add_argument("--min", type=int, default=2, help="Minimum fresh items")
    parser.add_argument("--state-file", help="SQLite path for cross-round dedup")
    parser.add_argument("--force-if-critical", dest="force_if_critical",
                        default="", help="Bypass keywords")
    args = parser.parse_args()

    global WINDOW_HOURS, MIN_ITEMS, STATE_FILE, FORCE_KEYWORDS
    WINDOW_HOURS = args.hours
    MIN_ITEMS = args.min
    STATE_FILE = args.state_file
    FORCE_KEYWORDS = args.force_if_critical

    start = time.time()

    try:
        # Pipeline: Fetcher → Normalizer → Validator → [Dedup] → FreshnessEvaluator → EvidenceBuilder
        raw = Fetcher().run()
        items = Normalizer().run(raw)
        if not isinstance(items, list):
            raise TypeError("parse() must return list[dict]")
        evidence = Validator().run(items)      # returns list[Evidence]
        evidence = deduplicate(evidence)        # keeps list, compatible

        evaluator = FreshnessEvaluator(WINDOW_HOURS, MIN_ITEMS, FORCE_KEYWORDS)
        evidence = evaluator.run(evidence)

        if not evaluator.is_acceptable(evidence):
            print("NO_NEW_CONTENT")
            return

        output = EvidenceBuilder().run(evidence, start)
        print(json.dumps(output, ensure_ascii=False, indent=2))

    except Exception as e:
        print(f"SEARCH_ERROR: {e}", file=sys.stderr)
        print("SEARCH_ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()
