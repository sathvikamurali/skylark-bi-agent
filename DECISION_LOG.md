# Decision Log — Skylark BI Agent

## 1. Key Assumptions

### Dynamic board schema
The agent is designed to work against the live monday.com boards without
hardcoding the exact board schema. Since column names can vary, the system
maps live column titles to canonical fields using an alias layer in
`data/models.py`.

For example, variations such as `Deal Value`, `Value`, `Amount`, or
`Opportunity Value` can resolve to the canonical `deal_value` field.

This makes the agent more resilient to minor schema changes while keeping
the analytical layer independent of monday.com's exact column naming.

### Unknown category taxonomies
Sector, deal stage, and execution status values are not hardcoded. Instead,
the system observes the values present in the live board and applies
lightweight fuzzy clustering to collapse obvious near-duplicates such as
differences in capitalization, spacing, or wording.

This avoids silently forcing real business categories into an assumed
taxonomy.

### Missing data is not treated as zero
A missing financial, date, or categorical value is represented as `None`
rather than zero or an invented value.

This is important for business reporting because a missing deal value does
not mean that the deal is worth ₹0, and a missing date does not mean that
the date is unknown or irrelevant.

The cleaning layer also produces a `DataQualityReport` so the agent can
surface limitations instead of presenting incomplete figures as fully
reliable.

### Time-based questions use the current date
Queries such as "overdue", "this year", or "this quarter" are interpreted
relative to the current date available to the application. The resulting
date assumption is surfaced in responses where it materially affects the
answer.

### Read-only data access
The monday.com integration is intentionally read-only. The agent retrieves
and analyzes business data but never modifies the source boards.

This reduces the risk of an incorrectly interpreted natural-language query
causing unintended changes to operational data.

---

## 2. Trade-offs Chosen and Why

| Decision | Chosen Approach | Alternative | Why |
|---|---|---|---|
| monday.com integration | Direct GraphQL API | monday.com MCP | A direct API keeps the application self-contained and avoids operating an additional MCP server. This was simpler and better suited to the limited implementation time. |
| LLM | Gemini API with tool use | Let the LLM answer directly from raw board data | Tool use allows the model to reason about which business operation is required while deterministic Python functions perform data retrieval, filtering, aggregation, and calculations. This reduces arithmetic and data-selection errors. |
| Analytical approach | Deterministic aggregation tools + raw-record fallback | Put the entire dataset into the LLM context | Sending every row to the model would increase context size and make numerical answers less reliable. Aggregation tools return compact, computed results while the raw-record tool preserves flexibility for questions that require record-level inspection. |
| Data cleaning | Typed cleaning layer for dates, currencies, and text | Use raw monday.com strings throughout | monday.com column values arrive as text. Converting them into typed Python values makes date comparisons, currency aggregation, and missing-value handling substantially more reliable. |
| Missing values | Preserve as missing and surface data-quality caveats | Convert missing values to zero/defaults | Treating missing financial values as zero would materially distort revenue and pipeline reporting. Explicit caveats are safer for business decisions. |
| Schema resilience | Alias-based canonical fields | Hardcode exact monday.com column names | Alias mapping makes the system tolerant of reasonable column renames without requiring changes throughout the application. |
| Category normalization | Dynamic fuzzy clustering | Hardcoded sector/stage lists | The actual business taxonomy should come from the board rather than assumptions made during development. The trade-off is that fuzzy matching remains heuristic and should be spot-checked. |
| Frontend | Streamlit | React/Next.js frontend | Streamlit provided a fast path to a usable, deployable conversational BI interface within the project time constraint. The trade-off is less frontend customization than a dedicated web stack. |
| Data freshness | Live monday.com retrieval with application-level refresh behavior | Webhook-driven synchronization | Webhooks would provide a stronger production architecture but add infrastructure and implementation complexity that was not justified for this prototype. |
| Agent behavior | Tool-use orchestration loop with bounded rounds and retries | Single model call | BI questions frequently require multiple steps: retrieve data, execute one or more tools, inspect the results, and formulate the answer. The orchestration loop supports this while bounding execution with a maximum number of tool rounds. |

---

## 3. What I'd Do Differently With More Time

### 1. Stronger semantic validation of business definitions
Some business questions depend on organization-specific definitions.

For example, "active pipeline" requires deciding whether stages such as
`Project Won`, `Work Order Received`, or `Invoice Sent` should be considered
active opportunities.

With more time, I would encode these business definitions as explicit,
configurable policies rather than relying primarily on the model to infer
them from the question.

### 2. Better category validation
The current fuzzy-clustering approach is intentionally lightweight. A
production version should expose which raw values were grouped together and
why, along with a confidence score.

This would make it easier to detect an incorrect merge before it affects a
leadership-level metric.

### 3. More robust date semantics
The current cleaning layer handles multiple common date formats, including
ISO dates and Indian-style day-first dates. With more time, I would add
explicit validation against impossible or suspicious dates and strengthen
handling of timezone and business-calendar semantics.

### 4. Automated integration tests against a sandbox monday.com board
The cleaning and analytical logic can be unit tested independently, but a
production-quality system should also regularly test the complete pipeline
against a sandboxed monday.com board.

This would catch API response-shape changes and schema drift before they
reach users.

### 5. Richer analytical outputs
The current agent focuses on conversational answers and tables. A future
version could generate visualizations such as pipeline funnels, revenue by
sector, execution-status distributions, and trend charts when those visuals
provide more value than text.

### 6. Persistent conversation and caching
A production deployment could persist conversation state and introduce
smarter cache invalidation so repeated questions can reuse the same board
snapshot while still reflecting important source-data changes quickly.

---

## 4. Interpretation of "Leadership Updates"

I interpreted "prepare data for leadership updates" as the ability to turn
operational BI data into a concise, decision-oriented executive summary
rather than simply returning raw records.

When asked for a leadership update, the agent is expected to prioritize:

1. **Headline metrics** — revenue, pipeline, order counts, and execution
   metrics.
2. **Key business insights** — concentration by sector, pipeline
   composition, execution performance, or other material patterns.
3. **Risks and exceptions** — overdue work orders, unusually large
   opportunities, or other items requiring attention.
4. **Data-quality caveats** — missing values, missing dates, unavailable
   ownership information, and other limitations that could affect the
   interpretation of the numbers.

The objective is that a founder or business leader can use the response as
a starting point for a management update without having to manually
interpret hundreds of operational records.

I deliberately chose a conversational executive brief rather than building
a PPT/PDF generator. The assignment's higher-value problem is extracting
and interpreting the relevant business information; formatting that
information into a presentation can be handled separately once the analysis
is trustworthy.
