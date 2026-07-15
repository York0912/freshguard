# Failure Patterns / 失败模式注册表

Log each fabrication incident or pipeline failure as a learning signal.

---

## Pattern: Stale Data Bleed

- **Occurrences**: 3
- **Trigger**: Historical items mixed into fresh analysis without distinction
- **Root cause**: No `fresh` tag comparison before LLM injection
- **Fix**: Add explicit `fresh` field to each item; prompt rule 4 (FRESH OVER STALE)
- **Detection**: Compare output dates against freshness window

---

## Pattern: Source URL Fabrication

- **Occurrences**: 1
- **Trigger**: LLM generates non-existent but correctly-formatted URLs
- **Root cause**: LLM has seen URL patterns in training data and reproduces them
- **Fix**: Pre-validate URL list against actual search results before injecting; embed `_sl` at data layer
- **Detection**: Regex check all `[S:...]` references against known URL list

---

## Pattern: Meta-Commentary Boilerplate

- **Occurrences**: 5+
- **Trigger**: LLM appends "The report is complete" or similar after analysis
- **Root cause**: Completion compulsion — LLM feels the need to signal task end
- **Fix**: Prompt rule 8 (NO META); auto-strip in validation layer
- **Detection**: Regex for "report is complete|here is a summary|in conclusion"

---

## Pattern: Timezone Misalignment

- **Occurrences**: 2 (China ECS)
- **Trigger**: Chinese news "2026-07-14 08:00:00" treated as UTC
- **Root cause**: Missing timezone info in source data; UTC default shifts items by -8h
- **Fix**: Assume UTC+8 for naive dates from Chinese sources; convert to UTC for comparison
- **Detection**: Compare item timestamps against server timezone

---

## Pattern: Rate Limit Silent Failure

- **Occurrences**: 1
- **Trigger**: Search API returns 429, `fetch()` catches and returns empty string
- **Root cause**: No distinction between "empty response" and "rate limited"
- **Fix**: Raise `SEARCH_RATE_LIMITED` (exit 8) instead of returning empty
- **Detection**: Monitor exit code 8 from cron/systemd

---

## To Add

- [ ] LLM ignores fresh/stale distinction
- [ ] Cross-source content duplication
- [ ] Multi-day silence without heartbeat
- [ ] Search API schema change
- [ ] Evidence object missing required field
