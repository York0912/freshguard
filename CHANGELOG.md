# Changelog

## Unreleased

### Documentation
- Add a deterministic 17-second terminal GIF plus a non-live evidence fixture that demonstrates collect → gate → render → silence without exposing live feed content, local paths, or account details.

## 2.1.0 (2026-07-15)

### Security and privacy
- Require HTTPS feeds by default, reject localhost and non-public literal IP feeds, and validate redirect targets.
- Bound fetched XML to 2 MiB and reject entity declarations before parsing.
- Escape remote content in Markdown output and harden the downstream prompt against indirect prompt injection.
- Ignore generated evidence/digest files, remove a machine-specific path from public documentation, and state the public-source-only workflow boundary.
- Pin GitHub Actions to immutable commit SHAs, declare read-only permissions, and reduce digest artifact retention to one day.
- Replace the Bash wrapper's string command execution with argument-array execution.
- Retry transient feed-network failures once without retrying safety or parsing failures.

## 2.0.0 (2026-07-15)

### Product
- Add portable source-profile JSON, including feed-level source type and declared provenance tier.
- Upgrade the RSS/Atom adapter to extract bounded summaries, validate profiles, merge feeds, and preserve partial-source failures as diagnostics.
- Add an extractive Markdown renderer that carries source labels and marks title-only evidence.
- Add a manually triggered GitHub Actions digest workflow that stores reviewable output as an artifact.

### Quality
- Promote `summary` and `source_tier` into the evidence data contract and JSON schemas.
- Add profile, provenance, summary, and renderer regression tests.
- Keep scheduled delivery and external publishing intentionally out of the default configuration.

## 1.6.0 (2026-07-15)

### Product
- Add `scripts/rss_guard.py`, a standard-library RSS/Atom adapter that runs without API keys or user-written provider code.
- Add a source-bound daily-briefing prompt and a Codex `agents/openai.yaml` entrypoint.
- Add GitHub Actions CI for the core and adapter test suites.

### Quality
- Add offline RSS, Atom, and end-to-end adapter tests.
- Document the boundary: freshness and source binding are not source-truth or interpretation guarantees.

## 1.5.1 (2026-07-15)

### Fixed
- Repaired the end-to-end `Evidence` pipeline: freshness evaluation, deduplication, and critical-keyword checks now work with typed evidence objects.
- Populate `retrieved_at`, normalize valid publication dates to UTC ISO 8601, and keep emitted evidence aligned with its JSON schema.
- Replace the Bash helper's source-string interpolation with JSON read from stdin, eliminating quote-driven Python code injection.

### Quality
- Add fresh, stale, deduplication, and critical-bypass end-to-end tests.
- Make Codex skill frontmatter valid and downgrade unverified platform claims to reference recipes.

## 1.5.0 (2026-07-15)

### Bugfix
- `parse_datetime()` now correctly returns UTC-aware datetime for Chinese format `YYYY-MM-DD HH:MM:SS`. Naive results from tz strategies are no longer returned as-is — they fall through to China-time strategies.

### Architecture
- Search Layer refactored into 5 single-responsibility steps: Fetcher → Normalizer → Validator → FreshnessEvaluator → EvidenceBuilder
- Internal Evidence dataclass introduced; pipeline steps pass typed Evidence objects internally
- Validator separated from FreshnessEvaluator (schema/URL checks ≠ freshness logic)

### Output
- Search output JSON now includes `version`, `schema_version`, `elapsed_ms` metadata fields
- Backward compatible: all existing fields (`items`, `fresh_count`, `total_count`) unchanged

### Documentation
- README rewritten as user-facing product page: one-line positioning, who should/not use, simplified arch diagram, release checklist
- SKILL.md stripped to pure spec (contracts, principles, capabilities, project reference)
- Architecture.md updated with full module boundaries
- Duplicate content removed across all docs; schema JSON duplicate property defs fixed

### Engineering
- Capabilities declaration added to SKILL.md metadata
- Compatibility matrix added to README
- Release checklist added to README
- Test suite: 16/16 passing
- No breaking changes to public API, CLI, or test imports
