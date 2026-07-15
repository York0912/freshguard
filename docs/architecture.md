# FreshGuard Architecture / 架构文档

## Overview / 概述

FreshGuard implements a dual-layer pipeline that separates data collection (deterministic) from data analysis (LLM), with a freshness gate in between.

```
Trigger (cron/systemd/scheduler)
    ↓
┌──────────────────────────────────────────────────┐
│ L1: Search Layer                                  │
│                                                    │
│  Fetcher → Normalizer → Validator → [Dedup]       │
│                                       ↓            │
│                          FreshnessEvaluator        │
│                                       ↓            │
│                          EvidenceBuilder           │
│                                       ↓            │
│                          stdout (JSON or status)   │
└──────────────────────────────────────────────────┘
               ↓
         ┌──────────┐
         │ Freshness │  Gate (L1.5)
         │   Gate    │
         └────┬─────┘
    ≥ threshold ↓      ↓ < threshold / error
┌──────────────┐  ┌──────────────┐
│ L2: LLM      │  │ [SILENT]     │
│ Analysis     │  │ ~100-200 tok │
└──────────────┘  └──────────────┘

---

## State Machine / 状态机

```
                    ┌──────────┐
                    │   IDLE   │
                    └────┬─────┘
                         │ trigger
                         ↓
                    ┌──────────┐
                    │ SEARCHING│
                    └──┬───┬───┘
                       │   │
               success │   │ error
                       ↓   ↓
              ┌──────────┐ ┌──────────────┐
              │ VALIDATING│ │ SEARCH_ERROR │──→ RETRYING ──→ ABORTED
              └─────┬────┘ └──────────────┘
                    │
           ┌────────┼────────┐
           │        │        │
      fresh │   stale │   invalid
           ↓        ↓        ↓
    ┌──────────┐ ┌────┐  ┌────────┐
    │ EVIDENCE │ │SILENT│ │ ABORTED│
    │ BUILDING │ │exit 0│ │(alert) │
    └────┬─────┘ └────┘  └────────┘
         │
         ↓
    ┌──────────┐
    │ ANALYZING│
    └──┬───┬───┘
       │   │
  pass │   │ reject
       ↓   ↓
  ┌──────┐ ┌──────────┐
  │DONE  │ │ ABORTED  │
  │(send)│ │(no send) │
  └──────┘ └──────────┘
```

### State Descriptions

| State | Description |
|-------|-------------|
| `IDLE` | Waiting for trigger |
| `SEARCHING` | Running fetch() |
| `SEARCH_ERROR` | fetch() raised or timed out |
| `SEARCH_EMPTY` | fetch() returned no results |
| `VALIDATING` | Checking freshness, schema, dedup |
| `FRESH` | Items passed freshness gate |
| `STALE` | No items within threshold |
| `EVIDENCE_BUILDING` | Structuring items for LLM |
| `ANALYZING` | LLM processing |
| `ANALYSIS_REJECTED` | LLM output failed validation |
| `DONE` | Output delivered |
| `ABORTED` | Pipeline aborted (silent or alert) |

---

## Module Boundaries / 模块边界

```
┌─────────────────────────────────────────────────────┐
│              Search Layer (L1)                       │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌──────┐  │
│  │ Fetcher │→ │Normalizer│→ │Validator│→ │Dedup │  │
│  └─────────┘  └──────────┘  └─────────┘  └──┬───┘  │
│                                              ↓       │
│  ┌───────────────────┐  ┌──────────────────┐        │
│  │FreshnessEvaluator │→ │ EvidenceBuilder  │→ stdout│
│  └───────────────────┘  └──────────────────┘        │
└─────────────────────────────────────────────────────┘
```

### Fetcher
- **Responsibility**: Call search provider, return raw bytes/string
- **Input**: None (or config from globals)
- **Output**: Raw response string
- **Constraint**: No parsing, no validation, no LLM
- **User overrides**: `fetch()`

### Normalizer
- **Responsibility**: Convert provider-specific output to uniform list[dict]
- **Input**: Raw string
- **Output**: `[{title, url, pub_date, ...}]`
- **Constraint**: No validation, no freshness logic
- **User overrides**: `parse()`

### Validator
- **Responsibility**: Schema, URL format, timestamp parseability (NOT freshness)
- **Input**: Normalized items
- **Output**: Filtered valid items
- **Checks**: title/url presence, URL protocol, date parseability
- **Constraint**: Does NOT check freshness — that's FreshnessEvaluator's job

### Dedup (optional)
- **Responsibility**: Cross-round URL dedup via SQLite state file
- **Input**: Validated items
- **Output**: Deduplicated items
- **Constraint**: Only active when `--state-file` provided

### FreshnessEvaluator
- **Responsibility**: Evaluate freshness per item against configurable window
- **Input**: Items with pub_date
- **Output**: Items tagged with `fresh` (bool|None) and `_cutoff`
- **Decision**: `is_acceptable()` — threshold check + critical keyword bypass
- **Constraint**: Pure freshness logic. No schema, no URL, no building.

### EvidenceBuilder
- **Responsibility**: Build output JSON conforming to evidence.schema.json
- **Input**: Freshness-tagged items
- **Output**: `{"items": [...], "fresh_count": N, ...}`
- **Actions**: Assign `id`, attach `_sl` source labels, count fresh items

### Gate Layer
- **Responsibility**: Validate freshness, dedup, schema
- **Input**: Parsed items with timestamps
- **Output**: Filtered item list or abort signal
- **Components**: Freshness check, dedup (optional), critical bypass

### L2: LLM Analysis
- **Responsibility**: Interpret and summarize passed data
- **Input**: Evidence items with source labels
- **Output**: Structured briefing or `[SILENT]`
- **Constraint**: Only cites data from L1, never adds outside knowledge

---

## Design Decisions / 设计决策

### D1: Search before analysis, not "search while writing"
**Why**: LLMs will pretend-search using training data. Deterministic search guarantees traceability.
**Cost**: One extra execution step. Negligible compared to LLM cost.

### D2: Source binding at data layer, not prompt layer
**Why**: "Please cite sources" in prompts is unreliable. Embedding `_sl` labels before LLM injection makes citation unavoidable.
**Trade-off**: Uses ~30 bytes per item for the label. Acceptable.

### D3: Abort cost awareness
**Why**: Running LLM on empty/stale data wastes tokens and produces garbage.
**Cost**: ~100-200 tokens to read a status signal vs 2-5K for a fabricated report.

### D4: Self-verification loop
**Why**: LLM output needs a second check before delivery.
**Implementation**: Post-analysis validation of citation counts, source freshness, format.

### D5: Failure pattern registry
**Why**: Each incident is a learning signal. Accumulating patterns reduces recurrence.
**Format**: Timestamped entries with trigger, root cause, fix action, occurrence count.

---

## Assumptions / 假设

- Search API is reachable and returns structured data
- Items have parseable timestamps (ISO 8601, RFC 2822, or Chinese format)
- LLM respects prompt constraints (verified via testing)
- Cron/systemd timer is reliable (retry handled at scheduler level)

## Known Limitations / 已知局限

- No source trust scoring (v2 candidate)
- No confidence estimation (v2 candidate)
- State-file DB grows unbounded (add VACUUM for high-frequency pipelines)
- Binary freshness gate (1 item can be more important than 10)
- Dedup before critical-check: already-reported critical items won't retrigger
