# Codex usage counting: subagent replay de-duplication

How Tokdash avoids double-counting Codex usage when Codex MultiAgent V2 spawns subagents.
Observed against **Codex CLI 0.144.1**.

## The problem

Codex writes one JSONL rollout file per thread under `~/.codex/sessions/YYYY/MM/DD/`. When a
session spawns a subagent (MultiAgent V2 `thread_spawn`, e.g. via `spawn_agent`), the subagent
gets its own rollout file that **replays the parent thread's history** so the subagent has the
parent's context available. Concretely, a subagent file:

1. Opens with its **own** `session_meta` — carrying `source.subagent.thread_spawn`
   (`parent_thread_id`, `depth`, `agent_path`, …) and the subagent's own `id`.
2. Then re-emits the **parent's** `session_meta` (with the parent's `id`) and replays the
   parent's `turn_context` and `token_count` events — all attributed to the **parent's**
   session id, not the subagent's.

Those replayed `token_count` events are **log artifacts**, not new API calls — the parent
thread already billed them. A naive parser that counts every `token_count` line double-counts:

- **Overview tab** — each replayed event becomes a separate usage entry (entry ids are
  per-file, so cross-file replays are not de-duplicated). With several subagents replaying the
  same parent, a model's reported usage can inflate several-fold.
- **Sessions tab** — because a subagent file's turns resolve to the *parent's* session id, and
  the Codex session loader keys sessions by id, a subagent file's replay can **overwrite** the
  parent session's real turns with a partial replayed subset.

This mirrors a known issue in the sibling project ccusage
([#950](https://github.com/ryoppippi/ccusage/issues/950),
[#1218](https://github.com/ccusage/ccusage/pull/1218)).

Note there are two *distinct* subagent file shapes in the wild:

- **own-usage** files — the subagent did its own model/tool work, logged under its **own**
  session id. This is real usage and must be **kept**.
- **replay-only** files — the subagent's file contains only the replayed parent history. This
  must be **skipped**.

Tokdash distinguishes them by session-id ownership (below), so it keeps real subagent work and
drops only the replays.

## How Tokdash handles it

Both the Overview parser (`src/tokdash/sources/coding_tools.py`, `CodexParser._parse_all`) and
the Sessions parser (`src/tokdash/sessions.py`, `_parse_codex_session_file`) apply the same rule
while streaming each rollout file:

1. Record the file's **own** session id = the `id` of the **first** `session_meta` line.
2. Detect the **thread_spawn gate**: if that first `session_meta` carries
   `source.subagent.thread_spawn`, the file is a subagent rollout; capture its declared
   `parent_thread_id`.
3. Track the **current** session id (updated on every subsequent `session_meta`).
4. **Skip a `token_count` event only when** the file is a thread_spawn subagent **and** the
   current session id equals the declared `parent_thread_id` (falling back to "current id ≠ own
   id" if `parent_thread_id` is absent).

Consequences:

- Ordinary primary sessions and guardian (`codex-auto-review`, `source.subagent.other ==
  "guardian"`) sessions are **never gated**, so their events are always counted — even if a
  primary session legitimately changes session id mid-file (e.g. compaction).
- A subagent's own real events (current id == own id) are **kept**; only events attributed to
  the declared parent are dropped.
- On any **unrecognized** future format change (renamed fields, re-attributed replays), the gate
  fails closed to *False* → nothing is skipped → the parser degrades to **over-counting (loud,
  user-visible)** rather than silently dropping real usage. Tokdash counts the skipped events
  (`CodexParser.replay_events_skipped`) so a regression is observable.

## Known limitation: nested subagents

The skip matches the **direct** `parent_thread_id`. For a **nested** subagent (depth > 1, which
requires a non-default `agents.max_depth`), the file also replays its *grandparent's* history
under the grandparent's id — which differs from the direct parent — so those grandparent replays
are **not** skipped and may still be over-counted (and could overwrite the root session on the
Sessions tab).

This is a **known, accepted limitation**, not a regression:

- It only occurs with nested subagents; `agents.max_depth` defaults to `1`.
- It errs toward over-counting — the loud, user-visible direction — never silent data loss.
- A corpus scan of local `thread_spawn` files found **no** nested (third-id) cases in practice.

If nested subagents become common, the fix is to skip events whose current id is any **ancestor**
id rather than only the direct parent.

## Operational note: the store rebuilds itself on upgrade

The Overview tab is backed by a persistent usage store, which is a *parse cache* — not a source
of truth. Each cached file's key includes a signature of the parser module itself (its path,
size, and mtime; see `parser_code_signature` in `src/tokdash/usage_store.py`, folded into every
file's stored signature by `sync_files`). So when Tokdash is upgraded — or the parser is edited
locally — that signature changes, every Codex rollout file is detected as *changed* on the next
sync, and its rows are deleted and reparsed with the corrected parser. **Previously counted
replays are therefore purged automatically; no manual step is required.** `tokdash db resync`
forces a full rebuild but is not needed for this fix to take effect.

## References

- ccusage [#950](https://github.com/ryoppippi/ccusage/issues/950) /
  [#1218](https://github.com/ccusage/ccusage/pull/1218) — the analogous fix in the sibling project.
- Codex subagents: <https://developers.openai.com/codex/concepts/subagents>
