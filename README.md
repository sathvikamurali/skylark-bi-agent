# Skylark BI Agent

A conversational agent that answers founder-level business questions
("How's our energy pipeline looking this quarter?") by querying two live
monday.com boards — Work Orders (delivery) and Deals (pipeline) — cleaning
the messy data on the fly, and reasoning over real computed numbers.

## Architecture

```
User (browser)
   │
   ▼
Streamlit chat UI (app.py)
   │
   ▼
BIAgent (agent/claude_agent.py)
   │  Claude Sonnet 5, tool-use loop
   ▼
Tools (agent/tools.py)          ──────► DataQualityReport (caveats)
   │  pipeline_summary, revenue_summary,
   │  operational_metrics, cross_reference_sector,
   │  get_raw_records, list_available_fields
   ▼
Pipeline (data/pipeline.py)
   │  maps board columns -> canonical fields (data/models.py)
   │  cleans dates/currency/categories (data/cleaning.py)
   ▼
MondayClient (monday/client.py)
   │  GraphQL, read-only, paginated
   ▼
monday.com API (live — never hardcoded)
```

**Flow of a question:** the user asks something in chat → Claude decides
which tool(s) to call → each tool fetches fresh data from monday.com (cached
in-memory for the rest of the session), runs it through the cleaning
pipeline, computes real aggregates in Python, and returns a compact JSON
summary (including a data-quality caveat string) → Claude turns that into a
plain-English answer, citing caveats where they matter.

See `DECISION_LOG.md` for why it's built this way and what trade-offs were made.

## Repo layout

```
app.py                    Streamlit chat front-end
agent/
  claude_agent.py         Tool-use orchestration loop
  system_prompt.py        Agent persona / ground rules
  tools.py                BI aggregation tools exposed to Claude
data/
  cleaning.py             Date/currency/category normalization
  models.py                WorkOrder / Deal dataclasses + column-alias mapping
  pipeline.py             monday.com raw rows -> cleaned records
monday/
  client.py               Read-only GraphQL client (auth, pagination, retries)
tests/
  test_cleaning.py        Unit tests for the cleaning logic (7 tests, all passing)
requirements.txt
.env.example
```

## Setting up monday.com

1. Create a monday.com account (or use an existing one) and open two boards.
2. Import `Work_Order_Tracker Data.xlsx` into one board and
   `Deal funnel Data.xlsx` into the other (**Board → ⋮ → Import data**).
   Let monday.com auto-detect column types; you don't need to match the
   canonical field names below exactly — see "Column naming" below.
3. Note each board's ID: open the board, and it's the numeric segment in the
   URL (`https://yourteam.monday.com/boards/1234567890`).
4. Generate a personal API token: **Avatar → Admin → API** (or
   **Developers → My Access Tokens**). This app only ever issues GraphQL
   *queries*, never mutations, so a read-capable token is sufficient.

### Column naming

The pipeline matches columns by title using a small alias table
(`data/models.py: WORK_ORDER_FIELD_ALIASES`, `DEAL_FIELD_ALIASES`), so your
board doesn't need exact column names — "Deal Value", "Value", and "Amount"
all map to the same canonical field, for example. If a column name isn't
recognized, extend the alias list (no other code changes needed) or ask the
agent to call `list_available_fields` to see exactly what it currently sees.

## Configuration

Copy `.env.example` to `.env` and fill in:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `ANTHROPIC_MODEL` | defaults to `claude-sonnet-5`; override if needed |
| `MONDAY_API_TOKEN` | monday.com → Admin → API |
| `MONDAY_WORK_ORDERS_BOARD_ID` | numeric ID from the board URL |
| `MONDAY_DEALS_BOARD_ID` | numeric ID from the board URL |

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export $(cat .env | xargs)   # or use python-dotenv / your shell's env loader
streamlit run app.py
```

## Run tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Deploy (hosted prototype, ~10 minutes)

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in, click
   **New app**, point it at this repo and `app.py`.
3. Under **Advanced settings → Secrets**, paste the same four variables from
   `.env.example` (Streamlit secrets use TOML format, e.g.
   `ANTHROPIC_API_KEY = "sk-ant-..."`).
4. Deploy. You get a public `*.streamlit.app` URL — testable without any
   local setup, satisfying the "hosted prototype" requirement.

## Known limitations (see DECISION_LOG.md for full list)

- Data is cached in-memory per session and refreshed on demand (sidebar
  button) rather than via webhooks — fine for a founder asking a handful of
  questions, not built for high-frequency polling.
- Category clustering (sector/stage names) is a greedy fuzzy-match, tuned
  for the small cardinality typical of these fields — it isn't a general
  clustering algorithm.
- No multi-user auth — anyone with the Streamlit URL and no separate
  password can query the connected boards. Add `st.secrets` based auth or a
  Streamlit "protected app" if this needs to be restricted.
