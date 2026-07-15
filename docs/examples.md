# FreshGuard Integration Examples / 集成示例

## Example 1: Daily Industry Briefing (Hermes)

```bash
hermes cron create \
  --name "Daily Briefing" \
  --schedule "0 9 * * 1-5" \
  --script "search-briefing.py --hours 48 --min 3 --state-file /tmp/briefing-state.db" \
  --deliver "origin" \
  "$(cat <<'PROMPT'
Analyze the search results above.
Rules: sourced data only, cite URLs, SILENT if empty.
PROMPT
)"
```

Output when fresh data exists:
```
## 🔴 Industry Briefing · Jul 14

**Company A announced quarterly results** [S:https://reuters.com/article/xyz|D:2026-07-14|F:Y]
Revenue up 12% YoY, beating estimates. Driven by APAC growth.

**New regulation proposed** [S:https://gov-example.com/policy/2026-07|D:2026-07-13|F:Y]
Covers data privacy requirements for SaaS providers. Comment period 60 days.
```

---

## Example 2: Critical-Keyword Bypass

When an outage or incident occurs, you can't wait for "enough" fresh results:

```bash
python3 search.py --hours 48 --min 3 --force-if-critical "outage,incident,recall"
# Even with only 1 fresh item, if title contains "outage" → bypass gate
```

---

## Example 3: Weekend / Low-Frequency Mode

Looser threshold for weekends or slow periods:

```bash
python3 search.py --hours 72 --min 1
```

---

## Example 4: Claude Code + systemd Timer

```
# /etc/systemd/system/daily-briefing.service
[Unit]
Description=Daily Industry Briefing
OnFailure=notify@%i.service

[Service]
ExecStart=/usr/local/bin/freshguard-briefing.sh
Type=oneshot
```

```bash
#!/usr/bin/env bash
# /usr/local/bin/freshguard-briefing.sh
set -euo pipefail
OUTPUT=$(python3 /opt/freshguard/search.py --hours 48 --min 2)

case "$OUTPUT" in
  NO_NEW_CONTENT) exit 0 ;;
  SEARCH_ERROR)   exit 1 ;;
  *)
    claude -p "$(cat <<PROMPT
Analyze the following search data:
$OUTPUT
Rules: sourced only, cite URLs.
PROMPT
)"
    ;;
esac
```

---

## Example 5: Bare Crontab

```bash
# crontab -e
0 8 * * 1-5 OUTPUT=$(python3 /opt/freshguard/search.py --hours 48 --min 2) && \
  [ "$OUTPUT" != "NO_NEW_CONTENT" ] && [ "$OUTPUT" != "SEARCH_ERROR" ] && \
  echo "$OUTPUT" | python3 /opt/freshguard/analyze.py
```

---

## Example 6: Codex CLI / WorkBuddy

```yaml
# .workbuddy/tasks/daily-scan.yaml
name: Daily Industry Scan
schedule: "0 9 * * 1-5"
steps:
  - name: search
    run: python3 search.py --hours 72 --min 3
  - name: guard
    if: '{{steps.search.output != "NO_NEW_CONTENT" and steps.search.output != "SEARCH_ERROR"}}'
    run: echo "{{steps.search.output}}" | codex -f analysis-prompt.md
```
