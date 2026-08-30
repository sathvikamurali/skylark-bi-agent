"""
Glue layer: monday.com raw rows -> cleaned WorkOrder / Deal objects, with a
DataQualityReport built alongside so caveats can be surfaced to the user.

Nothing here caches to disk or hardcodes CSV content — every call re-reads
from the live monday.com client passed in.
"""

from __future__ import annotations

from data.cleaning import (
    DataQualityReport,
    clean_currency,
    clean_date,
    clean_text,
    cluster_category_values,
)
from data.models import (
    DEAL_FIELD_ALIASES,
    WORK_ORDER_FIELD_ALIASES,
    Deal,
    WorkOrder,
    build_alias_lookup,
)
from monday.client import MondayClient


def load_work_orders(client: MondayClient, board_id: str) -> tuple[list[WorkOrder], DataQualityReport]:
    raw_rows = client.get_all_items(board_id)
    report = DataQualityReport(total_rows=len(raw_rows))
    if not raw_rows:
        return [], report

    column_titles = list({k for row in raw_rows for k in row.keys()})
    lookup = build_alias_lookup(column_titles, WORK_ORDER_FIELD_ALIASES)

    sector_col = lookup.get("sector")
    sector_map = (
        cluster_category_values([r.get(sector_col, "") for r in raw_rows if r.get(sector_col)])
        if sector_col
        else {}
    )
    status_col = lookup.get("status")
    status_map = (
        cluster_category_values([r.get(status_col, "") for r in raw_rows if r.get(status_col)])
        if status_col
        else {}
    )

    orders: list[WorkOrder] = []
    for row in raw_rows:
        flags: list[str] = []

        order_value = clean_currency(row.get(lookup.get("order_value", ""), None))
        if lookup.get("order_value") and order_value is None:
            flags.append("order_value")
            report.flag("order_value")

        start_date = clean_date(row.get(lookup.get("start_date", ""), None))
        if lookup.get("start_date") and start_date is None:
            flags.append("start_date")
            report.flag("start_date")

        end_date = clean_date(row.get(lookup.get("end_date", ""), None))
        if lookup.get("end_date") and end_date is None:
            flags.append("end_date")
            report.flag("end_date")

        raw_sector = clean_text(row.get(sector_col, None)) if sector_col else None
        sector = sector_map.get(raw_sector, raw_sector)
        if sector_col and raw_sector is None:
            report.flag("sector")

        raw_status = clean_text(row.get(status_col, None)) if status_col else None
        status = status_map.get(raw_status, raw_status)

        orders.append(
            WorkOrder(
                item_id=row["_item_id"],
                order_name=row.get("name", "(unnamed)"),
                client=clean_text(row.get(lookup.get("client", ""), None)),
                sector=sector,
                status=status,
                start_date=start_date,
                end_date=end_date,
                order_value=order_value,
                location=clean_text(row.get(lookup.get("location", ""), None)),
                quality_flags=flags,
            )
        )

    return orders, report


def load_deals(client: MondayClient, board_id: str) -> tuple[list[Deal], DataQualityReport]:
    raw_rows = client.get_all_items(board_id)
    report = DataQualityReport(total_rows=len(raw_rows))
    if not raw_rows:
        return [], report

    column_titles = list({k for row in raw_rows for k in row.keys()})
    lookup = build_alias_lookup(column_titles, DEAL_FIELD_ALIASES)

    sector_col = lookup.get("sector")
    sector_map = (
        cluster_category_values([r.get(sector_col, "") for r in raw_rows if r.get(sector_col)])
        if sector_col
        else {}
    )
    stage_col = lookup.get("stage")
    stage_map = (
        cluster_category_values([r.get(stage_col, "") for r in raw_rows if r.get(stage_col)])
        if stage_col
        else {}
    )

    deals: list[Deal] = []
    for row in raw_rows:
        flags: list[str] = []

        deal_value = clean_currency(row.get(lookup.get("deal_value", ""), None))
        if lookup.get("deal_value") and deal_value is None:
            flags.append("deal_value")
            report.flag("deal_value")

        close_date = clean_date(row.get(lookup.get("expected_close_date", ""), None))
        if lookup.get("expected_close_date") and close_date is None:
            flags.append("expected_close_date")
            report.flag("expected_close_date")

        created_date = clean_date(row.get(lookup.get("created_date", ""), None))

        raw_sector = clean_text(row.get(sector_col, None)) if sector_col else None
        sector = sector_map.get(raw_sector, raw_sector)
        if sector_col and raw_sector is None:
            report.flag("sector")

        raw_stage = clean_text(row.get(stage_col, None)) if stage_col else None
        stage = stage_map.get(raw_stage, raw_stage)
        if stage_col and raw_stage is None:
            flags.append("stage")
            report.flag("stage")

        deals.append(
            Deal(
                item_id=row["_item_id"],
                deal_name=row.get("name", "(unnamed)"),
                client=clean_text(row.get(lookup.get("client", ""), None)),
                sector=sector,
                stage=stage,
                deal_value=deal_value,
                expected_close_date=close_date,
                owner=clean_text(row.get(lookup.get("owner", ""), None)),
                created_date=created_date,
                quality_flags=flags,
            )
        )

    return deals, report
