# Tokdash API Reference

Tokdash exposes a local HTTP API (FastAPI) for querying token usage, costs, and session data across Claude Code, Codex, OpenClaw, and other supported tools.

- **Default bind:** `127.0.0.1:55423`
- **Start:** `tokdash serve --bind 127.0.0.1 --port 55423`
- **OpenAPI schema:** `GET /openapi.json`
- **Interactive docs:** `GET /docs` (Swagger UI), `GET /redoc`

All endpoints return JSON. No authentication — tokdash is intended to bind to loopback only.

---

## Endpoint Summary

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness probe |
| `GET` | `/api/usage` | Aggregated token usage and cost across all tools |
| `GET` | `/api/tools` | Per-tool usage breakdown (coding apps only) |
| `GET` | `/api/sessions` | List sessions for a given tool |
| `GET` | `/api/session` | Detailed turns for a single session |
| `GET` | `/api/codex/sessions` | Convenience wrapper: Codex sessions |
| `GET` | `/api/codex/session` | Convenience wrapper: single Codex session |
| `GET` | `/api/openclaw` | OpenClaw model breakdown |
| `GET` | `/api/stats` | Annual stats aggregation |
| `GET` | `/api/pricing-db` | Current pricing database snapshot |
| `PUT` | `/api/pricing-db` | Update the pricing database |
| `GET` | `/` | Web dashboard (HTML) |

---

## Period parameter

Most endpoints accept a `period` query parameter. Supported values:

| Value | Meaning |
|---|---|
| `today` (default) | Current day (00:00 local time → now) |
| `3days` | Last 3 days |
| `week` | Last 7 days |
| `14days` | Last 14 days |
| `month` | Current calendar month (1st → today) |
| `<integer>` | Last N days (e.g. `"30"` for 30 days) |

For arbitrary ranges, use `date_from` and `date_to` (format `YYYY-MM-DD`) where supported.

---

## `GET /health`

Liveness check.

**Response**
```json
{ "status": "ok" }
```

---

## `GET /api/usage`

Aggregated token usage and cost across all configured tools.

**Query parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `period` | string | no | `"today"` | See [Period parameter](#period-parameter) |
| `date_from` | string | no | – | Start date (`YYYY-MM-DD`). Overrides `period` when paired with `date_to`. |
| `date_to` | string | no | – | End date (`YYYY-MM-DD`). |

**Response fields**

| Field | Type | Description |
|---|---|---|
| `period` | string | Period that was queried |
| `total_tokens` | int | Total tokens across all tools |
| `total_cost` | float | Total cost in USD |
| `total_messages` | int | Total assistant/user message count |
| `by_tool` | object | Per-tool aggregates: `{ tool_name: { tokens, cost } }` |
| `apps` | object | Per-app detailed breakdown (includes `tokens_in`, `tokens_out`, `tokens_cache`, `cost`, `messages`, `models[]`) |
| `coding_apps` | object | Same shape as `apps`, filtered to coding tools (excludes browser/research tools) |
| `coding_models` | array | Flat list of models from coding apps, each tagged with `source` |
| `top_models` | array | Top N models by token usage |
| `openclaw_models` | array | OpenClaw-specific model breakdown |
| `combined_models` | array | All models from all sources, merged and ranked |
| `comparison` | object | Comparison vs previous period: `tokens_prev`, `cost_prev`, `messages_prev`, `tokens_pct`, `cost_pct`, `messages_pct` |
| `timestamp` | string | ISO 8601 timestamp when the response was generated |

**Per-app object shape**

```jsonc
{
  "tokens": 45990135,        // total tokens
  "tokens_in": 7786995,      // input tokens (non-cache)
  "tokens_out": 375005,      // output tokens
  "tokens_cache": 37828135,  // cache read + write tokens
  "cost": 39.52,             // USD
  "messages": 566,
  "models": [
    {
      "name": "anthropic/claude-opus-4-7",
      "tokens": 23980934,
      "tokens_in": 1468105,
      "tokens_out": 233771,
      "tokens_cache": 22279058,
      "cost": 26.15,
      "messages": 196
    }
  ]
}
```

**Example**
```bash
curl -s http://127.0.0.1:55423/api/usage?period=today | jq '{total_tokens, total_cost}'
# { "total_tokens": 71091234, "total_cost": 56.4 }
```

---

## `GET /api/tools`

Per-tool breakdown limited to coding apps (excludes auxiliary tools like browser/research).

**Query parameters**

| Name | Type | Required | Default |
|---|---|---|---|
| `period` | string | no | `"today"` |

**Response fields**

| Field | Type | Description |
|---|---|---|
| `total_tokens` | int | Sum across coding tools |
| `total_cost` | float | Sum in USD |
| `total_messages` | int | Message count |
| `apps` | object | Same per-app shape as `/api/usage` `apps` field |

---

## `GET /api/sessions`

List of sessions for a specific tool.

**Query parameters**

| Name | Type | Required | Default | Description |
|---|---|---|---|---|
| `tool` | string | **yes** | – | Tool name (e.g. `claude`, `codex`, `openclaw`) |
| `period` | string | no | `"today"` | See [Period parameter](#period-parameter) |
| `date_from` | string | no | – | Start date (`YYYY-MM-DD`) |
| `date_to` | string | no | – | End date (`YYYY-MM-DD`) |

**Response fields**

| Field | Type | Description |
|---|---|---|
| `tool` | string | Echo of tool param |
| `tool_label` | string | Human-readable name (e.g. `"Claude Code"`) |
| `period` | string | Period queried |
| `latest_session` | object | Most recent session (same shape as items in `sessions[]`) |
| `sessions` | array | All sessions in the period, sorted by `last_seen_at` desc |

**Session object shape**

```jsonc
{
  "tool": "claude",
  "session_id": "5a8aafce-67f6-4e08-8963-c01eebf9f520",
  "project": "howard",
  "model": "claude-opus-4-7",
  "token_events": 14,         // number of recorded API calls
  "tokens_in": 72528,
  "tokens_cache": 1136969,
  "tokens_out": 6161,
  "tokens_reasoning": 0,
  "tokens": 1215658,           // sum of in + cache + out + reasoning
  "cache_ratio": 0.9353,       // tokens_cache / tokens (0.0–1.0)
  "cost": 1.085,
  "started_at": "2026-05-21T20:41:54.357000+00:00",
  "last_seen_at": "2026-05-21T20:44:22.891000+00:00"
}
```

---

## `GET /api/session`

Detailed view of a single session including per-turn breakdown.

**Query parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `tool` | string | **yes** | Tool name |
| `session_id` | string | **yes** | Session UUID |

**Response fields**

| Field | Type | Description |
|---|---|---|
| `session` | object | Same shape as `latest_session` from `/api/sessions` |
| `turns` | array | Per-turn token + cost records |

**Turn object shape**

```jsonc
{
  "turn_index": 1,
  "model": "claude-sonnet-4-6",
  "tokens_in": 23361,
  "tokens_cache": 0,
  "tokens_out": 118,
  "tokens_reasoning": 0,
  "tokens": 23479,
  "cost": 0.0718,
  "timestamp": "2026-05-20T16:02:07.514000+00:00"
}
```

---

## `GET /api/codex/sessions`

Convenience wrapper for Codex sessions. Equivalent to `/api/sessions?tool=codex`.

**Query parameters**

| Name | Type | Required | Default |
|---|---|---|---|
| `period` | string | no | `"today"` |

---

## `GET /api/codex/session`

Convenience wrapper for a single Codex session. Equivalent to `/api/session?tool=codex&...`.

**Query parameters**

| Name | Type | Required |
|---|---|---|
| `session_id` | string | **yes** |

---

## `GET /api/openclaw`

OpenClaw-specific model breakdown.

**Query parameters**

| Name | Type | Required | Default |
|---|---|---|---|
| `period` | string | no | `"today"` |

**Response fields**

| Field | Type | Description |
|---|---|---|
| `total_tokens` | int | Sum across all OpenClaw models |
| `total_cost` | float | Sum in USD |
| `total_messages` | int | Message count |
| `models` | object | `{ model_name: { tokens, tokens_in, tokens_out, tokens_cache, cost, messages } }` |

---

## `GET /api/stats`

Yearly stats aggregation.

**Query parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `year` | integer | no | Year to query. Defaults to current year if omitted. |

---

## `GET /api/pricing-db`

Returns the current pricing database snapshot.

**Response fields**

| Field | Type | Description |
|---|---|---|
| `path` | string | Filesystem path of the pricing JSON |
| `data` | object | The pricing database (versions, aliases, model rates) |

The `data` object contains:
- `version` — pricing DB version
- `lastUpdated` — ISO timestamp
- `note` — description string
- `aliases` — `{ alias: canonical_name }` for model name normalization
- `models` — `{ model_name: { input, output, cache_read, cache_write } }` (USD per million tokens)

## `PUT /api/pricing-db`

Replaces the pricing database. Body must match the GET response `data` shape.

---

## Integration Example: Claude Code Status Line

Tokdash's `/api/usage` endpoint is well suited for embedding daily totals into the Claude Code status line. The snippet below queries today's usage with a 1-second timeout, falls back silently if tokdash is unreachable, and renders a compact summary like `📊 69.9M ($55.64) today`.

### Status line script (`~/.claude/scripts/statusline.sh`)

```bash
#!/bin/bash
input=$(cat)

MODEL=$(echo "$input" | jq -r '.model.display_name')
DIR=$(echo "$input" | jq -r '.workspace.current_dir')

# Fetch tokdash totals — fail silently if unreachable
TOKDASH_STR=""
TOKDASH_JSON=$(curl -s -m 1 "http://127.0.0.1:55423/api/usage?period=today" 2>/dev/null)
if [ -n "$TOKDASH_JSON" ]; then
  TODAY_TOKENS=$(echo "$TOKDASH_JSON" | jq -r '.total_tokens // 0' 2>/dev/null)
  TODAY_COST=$(echo "$TOKDASH_JSON" | jq -r '.total_cost // 0' 2>/dev/null)
  if [ -n "$TODAY_TOKENS" ] && [ "$TODAY_TOKENS" != "0" ]; then
    if [ "$TODAY_TOKENS" -ge 1000000 ]; then
      TOK_FMT=$(awk "BEGIN {printf \"%.1fM\", $TODAY_TOKENS/1000000}")
    elif [ "$TODAY_TOKENS" -ge 1000 ]; then
      TOK_FMT="$(( (TODAY_TOKENS + 500) / 1000 ))k"
    else
      TOK_FMT="$TODAY_TOKENS"
    fi
    COST_TODAY=$(printf '$%.2f' "$TODAY_COST")
    TOKDASH_STR=" | 📊 ${TOK_FMT} (${COST_TODAY}) today"
  fi
fi

echo "[$MODEL] 📁 ${DIR##*/}${TOKDASH_STR}"
```

### Claude Code settings (`~/.claude/settings.json`)

```json
{
  "statusLine": {
    "type": "command",
    "command": "bash ~/.claude/scripts/statusline.sh",
    "refreshInterval": 30
  }
}
```

`refreshInterval` (added in Claude Code 2.1.97) re-runs the script every N seconds so the totals stay live even while you're idle.

### Output

```
[Claude Sonnet 4.6] 📁 myproject | 📊 69.9M ($55.64) today
```

### Notes

- Keep the curl timeout small (`-m 1`) so the status line doesn't stall if tokdash is restarting.
- The `📊 ...` segment is omitted entirely when tokdash returns nothing — no error noise in the status bar.
- For per-tool detail, swap in `.by_tool.claude.tokens` or similar from the same response.
- For weekly/monthly totals, change `period=today` to `period=week` or `period=month`.

---

## Other Integration Patterns

### Shell alias for quick check

```bash
alias tokens-today='curl -s http://127.0.0.1:55423/api/usage?period=today | jq "{tokens: .total_tokens, cost: .total_cost, by_tool}"'
```

### Polling for cost alerts

```bash
#!/bin/bash
# Warn when daily spend crosses $50
COST=$(curl -s http://127.0.0.1:55423/api/usage?period=today | jq -r '.total_cost')
if (( $(echo "$COST > 50" | bc -l) )); then
  notify-send "Tokdash" "Daily spend has exceeded \$50 ($COST)"
fi
```

### Prometheus / metrics scraping

For richer monitoring setups, the `/api/usage` JSON can be parsed by a small exporter sidecar. The `comparison` block gives period-over-period deltas without extra requests.
