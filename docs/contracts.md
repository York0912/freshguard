# FreshGuard Contracts / 契约规范

## 1. Search Script Contract

### CLI Interface

```
my-search.py [OPTIONS]

Options:
  --hours HOURS       Freshness window (default: 48)
  --min COUNT         Minimum fresh items (default: 2)
  --state-file PATH   SQLite path for dedup (optional)
  --force-if-critical KEYWORDS  Comma-separated bypass keywords (optional)
```

### stdout Contract

stdout must contain exactly one of:

| Signal | Format | Exit Code |
|--------|--------|:---------:|
| JSON data | `{"version": "2.1.0", "schema_version": "1.0", "items": [...], "fresh_count": N, ...}` | 0 |
| No fresh content | `NO_NEW_CONTENT` | 0 |
| Search error | `SEARCH_ERROR` | 1 |

> Exit codes 2–8 are reserved for future detailed error signals (timeout, auth, rate-limit, etc.).

### stderr Contract

- Diagnostics only (warnings, progress, debug)
- Never parsed by downstream
- Example: `[warn] source X timeout, using cached data`
- Example: `[info] dedup: skipped 3 previously reported URLs`

### Search Output JSON Schema

See [schemas/search-output.schema.json](../schemas/search-output.schema.json).

```json
{
  "version": "2.1.0",
  "schema_version": "1.0",
  "elapsed_ms": 1234,
  "items": [
    {
      "title": "string (required)",
      "url": "string (required, must be unique in batch)",
      "published_at": "string (normalized ISO 8601) or null",
      "source_name": "string (optional)",
      "source_type": "string (optional)",
      "source_tier": "primary|official|curated|unrated (optional; declared provenance)",
      "summary": "string (optional; extractive source feed summary)"
    }
  ],
  "fresh_count": "integer",
  "total_count": "integer",
  "window_hours": "integer",
  "min_items": "integer"
}
```

---

## 2. Evidence Contract

Every item entering LLM analysis is an Evidence Object.

### Evidence Object Schema

See [schemas/evidence.schema.json](../schemas/evidence.schema.json).

```json
{
  "id": "string (unique, format: ev_{counter})",
  "title": "string",
  "url": "string (must be a valid URL)",
  "source_name": "string (optional)",
  "source_type": "enum: news|government|academic|social|blog|other",
  "source_tier": "enum: primary|official|curated|unrated (declared provenance only)",
  "summary": "string (extractive source feed summary; optional)",
  "published_at": "string (ISO 8601 or null)",
  "retrieved_at": "string (ISO 8601)",
  "fresh": "boolean or null",
  "_sl": "string (format: [S:url|D:date|F:Y/N/?])",
  "_cutoff": "string (ISO 8601)"
}
```

### Fields

| Field | Required | Description |
|-------|:--------:|-------------|
| `id` | ✅ | Unique evidence identifier |
| `title` | ✅ | Human-readable title |
| `url` | ✅ | Source URL (citation anchor) |
| `source_name` | ❌ | Human-readable source name |
| `source_type` | ❌ | Category of source |
| `source_tier` | ❌ | Declared provenance cue; not a truth guarantee |
| `summary` | ❌ | Extractive feed summary; title-only when absent |
| `published_at` | ❌ | Original publication time (null = unknown) |
| `retrieved_at` | ✅ | When this item was fetched |
| `fresh` | ✅ | `true` (within window), `false` (stale), `null` (unknown) |
| `_sl` | ✅ | Source label for LLM citation |
| `_cutoff` | ✅ | Freshness window boundary timestamp |

---

## 3. LLM Prompt Contract

### Input Structure

```
# Search Data (sourced by search script — LLM did NOT search)
<evidence objects here>

# Fields in JSON Items
- `_sl`: source label [S:url|D:date|F:Y/N/?] — use as citation
- `_cutoff`: freshness window boundary — context only
- `fresh`: true (within window), false (stale), null (unknown)

# Possible Input Prefixes
- JSON data → analyze it
- `NO_NEW_CONTENT` → output [SILENT]
- `SEARCH_*` errors → output nothing
```

### Must Rules

1. [SOURCED ONLY] Use only data from the search results above
2. [CITE EVERY CLAIM] Every claim must cite `_sl` from the data
3. [NO SOURCE = NO WRITE] Do not write anything without a source
4. [FRESH OVER STALE] Items with `fresh: false` → background only
5. [UNKNOWN DATE] Items with `fresh: null` → note "date unverified"
6. [SILENT IF EMPTY] Input = `NO_NEW_CONTENT` → output `[SILENT]`
7. [DON'T ANALYZE ERRORS] Input = `SEARCH_*` → output nothing
8. [NO META] No "the report is complete" or similar
9. [EXTRACTIVE] Derive claims only from an item's `title` and `summary`; title-only items may only be described as titles.

### Must Not Rules

- Do not add facts from training memory
- Do not fabricate URLs or citations
- Do not treat stale items as fresh
- Do not write meta-commentary

### Output Format

```
## 🔴 <Section Title> · <Date>

**<Headline>** [S:<url>|<date>|F:<Y/N/?>]
<One-sentence key finding>

## 🟡 <Section Title> · <Date>
...
```

---

## 4. LLM Output Validation Contract

After LLM analysis, validate:

| Check | Description | Failure Action |
|-------|-------------|:-------------:|
| Citation binding | Every `[S:...]` references a real URL from input | Reject output |
| Freshness dominance | Fresh items outnumber stale items | Warn + re-rank |
| No meta-commentary | No "report complete" boilerplate | Auto-strip |
| Format compliance | Output matches structured format | Auto-format |
| Silent compliance | `[SILENT]` when input = `NO_NEW_CONTENT` | Pass |
