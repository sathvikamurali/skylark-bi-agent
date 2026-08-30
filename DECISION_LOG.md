# Decision Log — Skylark BI Agent

## Key Assumptions

- **Dynamic board schema:** The exact monday.com schema was not known during development. I therefore used canonical fields with an alias-mapping layer (`data/models.py`) so variations such as `Deal Value`, `Amount`, or `Value` can map to the same field. The agent can also inspect available fields when needed.
- **Dynamic categories:** Sector, stage, and status values are not hardcoded. They are normalized using fuzzy matching to handle minor variations in capitalization, spacing, or naming.
- **Date interpretation:** “This quarter” and “this year” use the current calendar period and are stated explicitly in responses.
- **Currency:** The cleaning layer supports INR formats including ₹, lakh/crore, as well as common currency symbols and plain numeric values.
- **Read-only data access:** The agent only reads monday.com data and never modifies the source boards.

## Trade-offs

| Decision | Choice | Why |
|---|---|---|
| monday.com integration | Direct GraphQL API | Keeps the application as a single deployable Streamlit app without the additional complexity of an MCP server. |
| LLM data access | Aggregation tools + raw-record fallback | Python performs sums, counts, and rankings to reduce arithmetic errors and token usage. Raw records remain available for less-structured questions. |
| Category handling | Dynamic fuzzy clustering | Avoids hardcoding a taxonomy that may not match the actual board. |
| Frontend | Streamlit | Fast to build, easy to deploy, and sufficient for a functional prototype within the time constraint. |
| Data freshness | Session-level fetch + manual refresh | Balances data freshness with API usage and response speed. Webhooks would be preferable in production. |
| Date parsing | Explicit ISO handling + fuzzy fallback | Prevents ambiguous date-parsing errors while supporting inconsistent real-world formats. |

## What I'd Do Differently With More Time

- Add **automated tests against a sandboxed live monday.com board** rather than relying primarily on mocked data.
- Add **confidence/explanations for fuzzy category matches** so users can verify how values were normalized.
- Replace manual refresh with **webhook-based cache invalidation** for near-real-time updates.
- Add **visual analytics**, such as pipeline funnels and revenue-by-sector charts.
- Add **persistent conversation history** across sessions.

## Interpretation of “Leadership Updates”

I interpreted “prepare data for leadership updates” as the ability to generate a **concise, decision-oriented executive brief** on request.

The agent therefore prioritizes:

1. **Headline metrics** — revenue, pipeline, and operational performance.
2. **Key insights** — the most important trends or risks.
3. **Data-quality caveats** — missing values, dates, or attribution that could affect decisions.

This produces a summary that can be directly used as the basis for a leadership meeting, email, or presentation without requiring a separate slide-generation workflow.
