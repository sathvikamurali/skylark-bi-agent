"""
Tool implementations exposed to Claude via tool-use.

Design choice: rather than dumping raw board rows into the model's context
(expensive, invites arithmetic hallucination on totals/averages), each tool
does the actual aggregation in Python with real numbers, and returns a
compact JSON summary. A fallback raw-record tool exists for genuinely
ad-hoc questions the fixed aggregations don't cover. See DECISION_LOG.md.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import date

from data.models import Deal, WorkOrder
from data.pipeline import load_deals, load_work_orders
from monday.client import MondayClient

WORK_ORDERS_BOARD_ID = os.environ.get("MONDAY_WORK_ORDERS_BOARD_ID", "")
DEALS_BOARD_ID = os.environ.get("MONDAY_DEALS_BOARD_ID", "")

# ---------------------------------------------------------------------------
# Tiny in-process cache so a multi-tool-call turn (e.g. cross-board query)
# doesn't refetch the same board twice. Cleared per Streamlit session, and
# always at most a few minutes old — this is a BI agent, not a live ticker,
# and re-fetching on every new user message keeps data "fresh enough" without
# needing webhooks (a documented "with more time" improvement).
# ---------------------------------------------------------------------------
_cache: dict[str, tuple] = {}


def _get_client() -> MondayClient:
    return MondayClient()


def _get_work_orders():
    if "work_orders" not in _cache:
        client = _get_client()
        _cache["work_orders"] = load_work_orders(client, WORK_ORDERS_BOARD_ID)
    return _cache["work_orders"]


def _get_deals():
    if "deals" not in _cache:
        client = _get_client()
        _cache["deals"] = load_deals(client, DEALS_BOARD_ID)
    return _cache["deals"]


def clear_cache():
    _cache.clear()


def _quarter_of(d: date) -> tuple[int, int]:
    return d.year, (d.month - 1) // 3 + 1


def _in_quarter(d: date | None, year: int, quarter: int) -> bool:
    if d is None:
        return False
    return _quarter_of(d) == (year, quarter)


def _matches_sector(record_sector: str | None, wanted: str | None) -> bool:
    if wanted is None:
        return True
    if record_sector is None:
        return False
    return wanted.strip().lower() in record_sector.strip().lower()


# ---------------------------------------------------------------------------
# Tool: list_available_fields
# ---------------------------------------------------------------------------
def list_available_fields() -> str:
    """Report what boards/columns actually exist right now, plus row counts
    and data-quality caveats. The agent should call this first in a new
    conversation, or whenever a query references a field it's unsure about."""
    client = _get_client()
    schemas = client.get_boards_schema([WORK_ORDERS_BOARD_ID, DEALS_BOARD_ID])
    orders, wo_report = _get_work_orders()
    deals, deal_report = _get_deals()

    out = {
        "boards": [
            {"name": s.name, "columns": [c["title"] for c in s.columns], "row_count": s.items_count}
            for s in schemas
        ],
        "work_orders_loaded": len(orders),
        "deals_loaded": len(deals),
        "work_orders_data_quality": wo_report.summary(),
        "deals_data_quality": deal_report.summary(),
        "distinct_sectors_seen": sorted(
            {o.sector for o in orders if o.sector} | {d.sector for d in deals if d.sector}
        ),
        "distinct_deal_stages_seen": sorted({d.stage for d in deals if d.stage}),
        "distinct_work_order_statuses_seen": sorted({o.status for o in orders if o.status}),
    }
    return json.dumps(out, indent=2)


# ---------------------------------------------------------------------------
# Tool: pipeline_summary
# ---------------------------------------------------------------------------
def pipeline_summary(sector: str | None = None, year: int | None = None, quarter: int | None = None) -> str:
    """Summarize the deals pipeline: total/open/won/lost value and counts by
    stage, optionally filtered by sector and/or a specific year+quarter
    (based on expected_close_date)."""
    deals, report = _get_deals()

    filtered: list[Deal] = []
    for d in deals:
        if not _matches_sector(d.sector, sector):
            continue
        if year and quarter and not _in_quarter(d.expected_close_date, year, quarter):
            continue
        filtered.append(d)

    by_stage: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_value": 0.0, "missing_value_count": 0})
    for d in filtered:
        stage = d.stage or "(unspecified stage)"
        by_stage[stage]["count"] += 1
        if d.deal_value is not None:
            by_stage[stage]["total_value"] += d.deal_value
        else:
            by_stage[stage]["missing_value_count"] += 1

    total_value = sum(v["total_value"] for v in by_stage.values())

    result = {
        "filters_applied": {"sector": sector, "year": year, "quarter": quarter},
        "matching_deal_count": len(filtered),
        "total_matching_deals_excluded_missing_data": sum(
            v["missing_value_count"] for v in by_stage.values()
        ),
        "total_pipeline_value": round(total_value, 2),
        "by_stage": {k: {"count": v["count"], "total_value": round(v["total_value"], 2),
                          "rows_missing_value": v["missing_value_count"]} for k, v in by_stage.items()},
        "data_quality_note": report.summary(),
    }
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tool: revenue_summary
# ---------------------------------------------------------------------------
def revenue_summary(sector: str | None = None, year: int | None = None, quarter: int | None = None) -> str:
    """Summarize realized/executed revenue from Work Orders, optionally
    filtered by sector and/or year+quarter (based on start_date)."""
    orders, report = _get_work_orders()

    filtered: list[WorkOrder] = []
    for o in orders:
        if not _matches_sector(o.sector, sector):
            continue
        if year and quarter and not _in_quarter(o.start_date, year, quarter):
            continue
        filtered.append(o)

    by_sector: dict[str, dict] = defaultdict(lambda: {"count": 0, "total_value": 0.0})
    for o in filtered:
        key = o.sector or "(unspecified sector)"
        by_sector[key]["count"] += 1
        if o.order_value is not None:
            by_sector[key]["total_value"] += o.order_value

    total_value = sum(v["total_value"] for v in by_sector.values())
    missing_value_rows = sum(1 for o in filtered if o.order_value is None)

    result = {
        "filters_applied": {"sector": sector, "year": year, "quarter": quarter},
        "matching_order_count": len(filtered),
        "rows_missing_order_value": missing_value_rows,
        "total_revenue": round(total_value, 2),
        "by_sector": {k: {"count": v["count"], "total_value": round(v["total_value"], 2)}
                      for k, v in by_sector.items()},
        "data_quality_note": report.summary(),
    }
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tool: operational_metrics
# ---------------------------------------------------------------------------
def operational_metrics(sector: str | None = None) -> str:
    """Operational health of Work Orders: status breakdown, count of
    overdue-looking orders (end_date in the past but status not
    completed-sounding), and average project duration where both start and
    end dates are known."""
    orders, report = _get_work_orders()
    filtered = [o for o in orders if _matches_sector(o.sector, sector)]

    by_status: dict[str, int] = defaultdict(int)
    durations = []
    overdue = []
    today = date.today()

    for o in filtered:
        by_status[o.status or "(unspecified status)"] += 1
        if o.start_date and o.end_date and o.end_date >= o.start_date:
            durations.append((o.end_date - o.start_date).days)
        status_lower = (o.status or "").lower()
        looks_done = any(k in status_lower for k in ("complete", "done", "closed", "delivered"))
        if o.end_date and o.end_date < today and not looks_done:
            overdue.append({"order_name": o.order_name, "client": o.client, "end_date": str(o.end_date),
                             "status": o.status})

    result = {
        "filters_applied": {"sector": sector},
        "total_orders": len(filtered),
        "by_status": dict(by_status),
        "avg_project_duration_days": round(sum(durations) / len(durations), 1) if durations else None,
        "orders_with_known_duration": len(durations),
        "possibly_overdue_orders": overdue[:20],
        "possibly_overdue_count": len(overdue),
        "data_quality_note": report.summary(),
    }
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# Tool: cross_reference_sector
# ---------------------------------------------------------------------------
def cross_reference_sector(sector: str) -> str:
    """Combined pipeline + delivery view for one sector — useful for
    'how's X sector doing overall' style founder questions that span both
    boards."""
    pipeline = json.loads(pipeline_summary(sector=sector))
    revenue = json.loads(revenue_summary(sector=sector))
    ops = json.loads(operational_metrics(sector=sector))
    return json.dumps({"sector": sector, "pipeline": pipeline, "delivered_revenue": revenue,
                        "operations": ops}, indent=2)


# ---------------------------------------------------------------------------
# Tool: get_raw_records — escape hatch for ad-hoc questions
# ---------------------------------------------------------------------------
def get_raw_records(board: str, sector: str | None = None, limit: int = 30) -> str:
    """Fallback tool for questions the fixed aggregations don't cover.
    Returns cleaned (not raw-from-API) individual rows from either board,
    capped at `limit` rows to control token usage. board must be
    'work_orders' or 'deals'."""
    if board == "work_orders":
        orders, _ = _get_work_orders()
        filtered = [o for o in orders if _matches_sector(o.sector, sector)]
        rows = [
            {"order_name": o.order_name, "client": o.client, "sector": o.sector, "status": o.status,
             "start_date": str(o.start_date) if o.start_date else None,
             "end_date": str(o.end_date) if o.end_date else None,
             "order_value": o.order_value, "location": o.location}
            for o in filtered[:limit]
        ]
    elif board == "deals":
        deals, _ = _get_deals()
        filtered = [d for d in deals if _matches_sector(d.sector, sector)]
        rows = [
            {"deal_name": d.deal_name, "client": d.client, "sector": d.sector, "stage": d.stage,
             "deal_value": d.deal_value,
             "expected_close_date": str(d.expected_close_date) if d.expected_close_date else None,
             "owner": d.owner}
            for d in filtered[:limit]
        ]
    else:
        return json.dumps({"error": "board must be 'work_orders' or 'deals'"})

    return json.dumps({"board": board, "returned_rows": len(rows),
                        "truncated": len(filtered) > limit, "rows": rows}, indent=2)


TOOL_DEFINITIONS = [
    {
        "name": "list_available_fields",
        "description": (
            "Discover what columns/fields actually exist on the live monday.com "
            "boards right now, plus row counts and data quality caveats. Call this "
            "first if unsure what fields, sectors, stages, or statuses exist."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "pipeline_summary",
        "description": "Summarize the sales pipeline (Deals board): value and counts by stage.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {"type": "string", "description": "Filter to deals matching this sector (substring match)."},
                "year": {"type": "integer", "description": "Filter to this calendar year of expected close date."},
                "quarter": {"type": "integer", "description": "1-4. Requires year to also be set."},
            },
        },
    },
    {
        "name": "revenue_summary",
        "description": "Summarize executed/delivered revenue (Work Orders board), by sector.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sector": {"type": "string"},
                "year": {"type": "integer", "description": "Calendar year of order start date."},
                "quarter": {"type": "integer", "description": "1-4. Requires year to also be set."},
            },
        },
    },
    {
        "name": "operational_metrics",
        "description": "Operational health of Work Orders: status breakdown, overdue orders, avg project duration.",
        "input_schema": {"type": "object", "properties": {"sector": {"type": "string"}}},
    },
    {
        "name": "cross_reference_sector",
        "description": "Combined pipeline + revenue + operations view for one sector, spanning both boards.",
        "input_schema": {
            "type": "object",
            "properties": {"sector": {"type": "string"}},
            "required": ["sector"],
        },
    },
    {
        "name": "get_raw_records",
        "description": (
            "Fallback for ad-hoc questions the other tools don't cover. Returns "
            "individual cleaned rows (capped) from one board."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "board": {"type": "string", "enum": ["work_orders", "deals"]},
                "sector": {"type": "string"},
                "limit": {"type": "integer", "default": 30},
            },
            "required": ["board"],
        },
    },
]

TOOL_IMPLEMENTATIONS = {
    "list_available_fields": list_available_fields,
    "pipeline_summary": pipeline_summary,
    "revenue_summary": revenue_summary,
    "operational_metrics": operational_metrics,
    "cross_reference_sector": cross_reference_sector,
    "get_raw_records": get_raw_records,
}
