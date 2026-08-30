# Skylark BI Agent

A conversational Business Intelligence agent that answers founder-level business questions by querying live monday.com data from Work Orders and Deals boards.

Example questions:

* "How many work orders do we currently have?"
* "What's our pipeline looking like this quarter?"
* "What's our total delivered revenue by sector?"
* "Which work orders look overdue?"
* "Who are the top owners by revenue?"
* "Prepare a leadership update on current performance."

The agent interprets the question, selects the appropriate BI tool(s), retrieves live data from monday.com, cleans and normalizes the data, computes the required metrics in Python, and converts the results into a concise business-oriented answer.

The LLM is not responsible for performing the underlying business arithmetic. Business calculations are performed deterministically by Python tools using the live board data.

---

## Architecture

```text
User (browser)
      |
      v
Streamlit Chat UI (app.py)
      |
      v
Gemini BIAgent (agent/gemini_agent.py)
      |
      | Gemini function/tool calling
      v
BI Tools (agent/tools.py)
      |
      +-- pipeline_summary
      +-- revenue_summary
      +-- operational_metrics
      +-- cross_reference_sector
      +-- get_raw_records
      +-- list_available_fields
      |
      v
Data Pipeline
(data/pipeline.py)
      |
      v
Cleaning + Canonical Models
(data/cleaning.py, data/models.py)
      |
      v
MondayClient
(monday/client.py)
      |
      | Read-only GraphQL API
      v
monday.com
```

### Flow of a Question

1. The user asks a business question through the Streamlit chat interface.
2. Gemini determines which BI tool(s) are required.
3. The selected tool queries the live monday.com boards.
4. Raw records pass through the data-cleaning and normalization pipeline.
5. Business metrics are computed deterministically in Python.
6. Tool results, including relevant data-quality caveats, are returned to Gemini.
7. Gemini produces the final natural-language business answer.

See `DECISION_LOG.md` for the major design decisions and trade-offs.

---

## Repository Structure

```text
skylark-bi-agent/
│
├── .devcontainer/
│
├── agent/
│   ├── gemini_agent.py
│   ├── system_prompt.py
│   └── tools.py
│
├── data/
│   ├── cleaning.py
│   ├── models.py
│   └── pipeline.py
│
├── monday/
│   └── client.py
│
├── tests/
│   └── test_cleaning.py
│
├── app.py
├── requirements.txt
├── README.md
├── DECISION_LOG.md
└── Decision_Log.pdf
```

---

## Features

### 1. monday.com Integration

* Direct monday.com GraphQL API integration
* Read-only access
* Pagination for board data
* Authentication through environment variables or Streamlit secrets
* No business data is hardcoded into the agent

### 2. Data Resilience

The source data contains real-world inconsistencies. The pipeline handles:

* Missing and null values
* Inconsistent date formats
* Currency/value normalization
* Naming variations
* Duplicate records
* Corrupted records
* Multi-value text fields
* Embedded units in quantity fields
* Missing financial and scheduling information

When data is insufficient for a reliable calculation, the agent communicates the limitation instead of inventing a value.

### 3. Query Understanding

The agent supports founder-level natural-language questions and determines which data and calculations are required.

Examples:

```text
How many work orders do we currently have?

Which work orders look overdue?

What's our total delivered revenue by sector?

Who are the top owners by revenue?

How is the pipeline looking for a particular sector?
```

### 4. Business Intelligence

The agent provides analysis across:

* Revenue and financial metrics
* Pipeline health
* Deal stages
* Sector performance
* Work-order status
* Operational metrics
* Owner / BD performance
* Cross-board analysis where supported
* Data-quality caveats and context

### 5. Leadership Updates

The optional leadership-update requirement is interpreted as generating a structured executive brief containing:

* Headline metrics
* Key business insights
* Areas requiring attention
* Important data-quality caveats

The system focuses on decision-useful information rather than generating presentation files.

---

## Setting Up monday.com

### 1. Create the Boards

Create two monday.com boards:

1. **Work Orders**
2. **Deals**

Import the provided datasets into separate boards.

The source data is intentionally messy, so the application performs cleaning and normalization after retrieving the data.

### 2. Get the Board IDs

Open each board in monday.com.

The numeric value in the board URL is the board ID.

For example:

```text
https://yourteam.monday.com/boards/5030968649
```

The board ID is:

```text
5030968649
```

### 3. Generate a monday.com API Token

Generate a Personal API Token from monday.com.

The application only performs read operations against monday.com. It does not create, modify, or delete board data.

---

## Configuration

The application requires the following environment variables:

```text
GEMINI_API_KEY
MONDAY_API_TOKEN
MONDAY_WORK_ORDERS_BOARD_ID
MONDAY_DEALS_BOARD_ID
```

Optional:

```text
GEMINI_MODEL
```

If `GEMINI_MODEL` is not provided, the application uses the default model defined in `agent/gemini_agent.py`.

### Local Configuration

Create a `.env` file locally:

```text
GEMINI_API_KEY="your_gemini_api_key"
MONDAY_API_TOKEN="your_monday_api_token"
MONDAY_WORK_ORDERS_BOARD_ID="5030968649"
MONDAY_DEALS_BOARD_ID="5030968714"
```

Do not commit `.env` or API keys to GitHub.

### Streamlit Cloud Configuration

For the hosted deployment, add the same variables under:

```text
Streamlit Cloud
→ Manage app
→ Settings
→ Secrets
```

Use TOML format:

```toml
GEMINI_API_KEY = "your_gemini_api_key"
MONDAY_API_TOKEN = "your_monday_api_token"
MONDAY_WORK_ORDERS_BOARD_ID = "5030968649"
MONDAY_DEALS_BOARD_ID = "5030968714"
```

If `GEMINI_MODEL` is required or customized, it can also be added:

```toml
GEMINI_MODEL = "your_model_name"
```

---

## Running Locally

Create and activate a virtual environment:

```bash
python -m venv .venv
```

### macOS / Linux

```bash
source .venv/bin/activate
```

### Windows

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Set the required environment variables and run:

```bash
streamlit run app.py
```

---

## Running Tests

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
pytest tests/ -v
```

The test suite covers the data-cleaning logic.

---

## Deployment

The application is deployed as a hosted Streamlit prototype.

Deployment steps:

1. Push the repository to GitHub.
2. Open Streamlit Community Cloud.
3. Create a new app.
4. Select this GitHub repository.
5. Set `app.py` as the main file.
6. Add the required secrets.
7. Deploy.

The resulting public Streamlit URL provides access to the working prototype without requiring local setup.

---

## Data and Integration Design

The application intentionally does not hardcode the supplied business data.

Every business query retrieves the current data from monday.com through the read-only GraphQL client.

The data pipeline then:

1. Retrieves paginated board records.
2. Maps board columns to canonical fields.
3. Normalizes dates, currency, categories, and quantities.
4. Detects problematic records.
5. Computes deterministic business metrics.
6. Returns structured results and relevant data-quality information.

This keeps the prototype usable when the underlying monday.com data changes.

---

## Error Handling

The application is designed to handle both data and API-level failures.

Examples include:

* Missing or incomplete source data
* Invalid or unexpected field values
* Unknown tool requests
* Tool execution errors
* API failures
* Temporary model availability or quota errors

Where possible, the application exposes meaningful error information or data-quality caveats rather than silently returning unreliable results.

---

## Known Limitations

* Data is cached in memory during a session and can be manually refreshed.
* There is no multi-user authentication layer beyond the hosting platform.
* Category normalization uses fuzzy matching designed for the relatively small number of categories in the supplied data.
* Some source records contain missing financial or scheduling information. Therefore, certain metrics may legitimately be unavailable or incomplete.
* Automated tests use the application's data-processing logic rather than a continuously running production monday.com sandbox.
* The hosted prototype is intended as a proof of concept rather than a production-scale BI platform.

---

## Security Notes

API credentials are stored through environment variables locally and Streamlit secrets in the hosted deployment.

Credentials must never be committed to the repository.

The monday.com integration is read-only and does not issue mutation operations.
