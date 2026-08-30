# Decision Log — Skylark BI Agent

## Key assumptions

- **Board schema is unknown at build time.** The two source files
  (`Work_Order_Tracker Data.xlsx`, `Deal funnel Data.xlsx`) weren't available
  to me while building, so I designed against a plausible schema — Work
  Orders: client, sector, status, start/end dates, order value, location;
  Deals: client, sector, stage, deal value, expected close date, owner —
  and built a column-alias mapping layer (`data/models.py`) so the pipeline
  tolerates the real board's actual column names without code changes, as
  long as they're reasonably close (e.g. "Amount" vs "Deal Value" both
  resolve to `deal_value`). If the real data has fields well outside this
  shape, `list_available_fields` is the escape hatch: the agent calls it to
  see exactly what exists rather than assuming.
- **Sector/stage/status taxonomies are unknown**, so instead of hardcoding a
  canonical list (e.g. `["Energy","Agriculture",...]`) that might not match
  reality, categories are fuzzy-clustered from whatever values actually
  appear on the board (`cluster_category_values`), collapsing near-duplicates
  like "Energy" / "energy " / "ENERGY-SECTOR".
- **"This quarter" / "this year"** default to the current calendar
  quarter/year relative to the server date, stated explicitly in the reply
  so the user can correct it — cheaper than a clarifying round-trip for the
  common case, reversible for the uncommon one.
- **Currency is assumed INR-first** (₹, lakh/crore suffixes are parsed) with
  $ and plain-number fallback, matching the likely context of an Indian
  drone-services company; genuinely mixed-currency data would need an
  explicit currency column, which isn't assumed to exist.
- **Read-only integration**, per the spec — no mutation calls are ever issued
  to monday.com, so this can't corrupt the source boards even if a query is
  misinterpreted.

## Trade-offs

| Decision | Chosen | Alternative | Why |
|---|---|---|---|
| monday.com access | Direct GraphQL API | monday.com MCP server | MCP would mean managing a second server process inside a single hosted Streamlit app — real complexity for zero capability gain here, since the spec explicitly allows either. Direct API keeps the whole thing a single deployable process. |
| How the LLM sees data | Discrete aggregation tools (`pipeline_summary`, `revenue_summary`, etc.) that compute real numbers in Python | Dump raw/cleaned rows into context and let Claude compute totals itself | Prevents arithmetic hallucination on sums/averages and keeps token usage low on large boards. Trade-off: fixed tools can't answer every conceivable ad-hoc question, so a `get_raw_records` fallback tool exists for anything the fixed aggregations don't cover. |
| Category normalization | Dynamic fuzzy clustering, no hardcoded taxonomy | Hardcoded canonical list per field | Real taxonomy was unknown ahead of time; a hardcoded list risks silently misclassifying real values that don't happen to match. Trade-off: clustering is a heuristic (threshold-based greedy match), not guaranteed-correct — worth a manual spot-check on first real run. |
| Frontend | Streamlit chat (`st.chat_message` / `st.chat_input`) | Custom React/Next.js chat UI | Built-in chat primitives + one-click free hosting (Streamlit Community Cloud) fit the 6-hour budget and "testable without local setup" requirement far better than standing up a separate frontend/backend/hosting pipeline. Trade-off: less visual polish and no persistent multi-session history (resets per browser session, matching Streamlit's default session model). |
| Data freshness | Fetch-and-cache per session, manual "refresh" button | Live fetch on every single message, or webhook-driven push updates | A per-turn re-fetch on every board would be wasteful and slower for a multi-question conversation about the same snapshot; webhooks would be the "real" production answer but are out of scope for a 6-hour prototype. |
| Date parsing | ISO format (`YYYY-MM-DD`) is detected and parsed explicitly before falling back to `dayfirst=True` fuzzy parsing | Always use `dateutil` with a single `dayfirst` setting | Caught in testing: `dateutil` with `dayfirst=True` silently misreads unambiguous ISO dates like `2025-12-01` as day=12/month=01. Indian-style `DD/MM/YYYY` data still needs `dayfirst=True`, so both formats needed explicit handling rather than one global flag. |

## What I'd do differently with more time

- **Validate against the real CSVs.** Everything here was validated with
  synthetic messy data (unit tests + an end-to-end smoke test) covering the
  cleaning logic and tool outputs, but the column-alias table and sector/
  stage assumptions should be checked against the actual imported boards on
  first real use.
- **Webhook-based cache invalidation** instead of a manual refresh button,
  so the agent reflects board edits within seconds without a full re-fetch.
- **Confidence surfacing on fuzzy-matched categories** — e.g. show the user
  which raw values got merged into which canonical label, so a bad merge is
  easy to catch rather than silently baked into a total.
- **Session persistence** (a small DB) so conversation history survives a
  page refresh or is shareable across a founder's devices.
- **Chart output**, not just text, for leadership-update mode — e.g. a
  pipeline-by-stage funnel chart alongside the narrative summary.
- **Automated tests against a real (sandboxed) monday.com board** rather
  than only a mocked client, to catch API-shape drift (e.g. monday.com
  changing `column_values` structure) before it reaches users.

## Interpreting "prepare data for leadership updates"

I read this as: **the agent should be able to produce a structured executive
brief on request**, not generate slides or files. The system prompt
instructs the agent that when asked to "prepare something for leadership" it
should respond with headline metrics, 3–5 bullet insights, and an explicit
caveats section — text a founder can paste directly into a slide, email, or
board update — rather than a raw data dump. I chose this over building a
PPTX/PDF generator because the highest-value part of "leadership update prep"
for a founder is almost always *deciding what the 3-5 things worth saying
are*, which is a reasoning task the agent is already positioned to do well;
turning that into a formatted deck is a comparatively mechanical last step
better left to whatever tool the founder already uses to build decks.
