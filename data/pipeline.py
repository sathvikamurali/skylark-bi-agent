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


def load_work_orders(
    client: MondayClient,
    board_id: str,
) -> tuple[list[WorkOrder], DataQualityReport]:
    """Load, normalize, and clean work-order records from monday.com."""

    raw_rows = client.get_all_items(board_id)
    report = DataQualityReport(total_rows=len(raw_rows))

    if not raw_rows:
        return [], report

    column_titles = list({key for row in raw_rows for key in row.keys()})
    lookup = build_alias_lookup(
        column_titles,
        WORK_ORDER_FIELD_ALIASES,
    )

    sector_col = lookup.get("sector")
    sector_map = (
        cluster_category_values(
            [
                row.get(sector_col, "")
                for row in raw_rows
                if row.get(sector_col)
            ]
        )
        if sector_col
        else {}
    )

    status_col = lookup.get("status")
    status_map = (
        cluster_category_values(
            [
                row.get(status_col, "")
                for row in raw_rows
                if row.get(status_col)
            ]
        )
        if status_col
        else {}
    )

    orders: list[WorkOrder] = []

    for row in raw_rows:
        flags: list[str] = []

        # -------------------------
        # Text fields
        # -------------------------

        name_col = lookup.get("order_name")
        order_name = (
            clean_text(row.get(name_col))
            if name_col
            else None
        )

        if order_name is None:
            order_name = "(unnamed)"

        client_col = lookup.get("client")
        client = (
            clean_text(row.get(client_col))
            if client_col
            else None
        )

        location_col = lookup.get("location")
        location = (
            clean_text(row.get(location_col))
            if location_col
            else None
        )

        owner_col = lookup.get("owner")
        owner = (
            clean_text(row.get(owner_col))
            if owner_col
            else None
        )

        # -------------------------
        # Financial fields
        # -------------------------

        value_col = lookup.get("order_value")

        order_value = (
            clean_currency(row.get(value_col))
            if value_col
            else None
        )

        if value_col and order_value is None:
            flags.append("order_value")
            report.flag("order_value")

        # -------------------------
        # Date fields
        # -------------------------

        start_col = lookup.get("start_date")
        start_date = (
            clean_date(row.get(start_col))
            if start_col
            else None
        )

        if start_col and start_date is None:
            flags.append("start_date")
            report.flag("start_date")

        end_col = lookup.get("end_date")
        end_date = (
            clean_date(row.get(end_col))
            if end_col
            else None
        )

        if end_col and end_date is None:
            flags.append("end_date")
            report.flag("end_date")

        # -------------------------
        # Categories
        # -------------------------

        raw_sector = (
            clean_text(row.get(sector_col))
            if sector_col
            else None
        )

        sector = (
            sector_map.get(raw_sector, raw_sector)
            if raw_sector
            else None
        )

        if sector_col and raw_sector is None:
            flags.append("sector")
            report.flag("sector")

        raw_status = (
            clean_text(row.get(status_col))
            if status_col
            else None
        )

        status = (
            status_map.get(raw_status, raw_status)
            if raw_status
            else None
        )

        if status_col and raw_status is None:
            flags.append("status")
            report.flag("status")

        # -------------------------
        # Build WorkOrder
        # -------------------------

        orders.append(
            WorkOrder(
                item_id=row["_item_id"],
                order_name=order_name,
                client=client,
                sector=sector,
                status=status,
                start_date=start_date,
                end_date=end_date,
                order_value=order_value,
                location=location,
                owner=owner,
                quality_flags=flags,
            )
        )

    return orders, report


def load_deals(
    client: MondayClient,
    board_id: str,
) -> tuple[list[Deal], DataQualityReport]:
    """Load, normalize, and clean deal records from monday.com."""

    raw_rows = client.get_all_items(board_id)
    report = DataQualityReport(total_rows=len(raw_rows))

    if not raw_rows:
        return [], report

    column_titles = list({key for row in raw_rows for key in row.keys()})
    lookup = build_alias_lookup(
        column_titles,
        DEAL_FIELD_ALIASES,
    )

    # -------------------------
    # Category normalization
    # -------------------------

    sector_col = lookup.get("sector")

    sector_map = (
        cluster_category_values(
            [
                row.get(sector_col, "")
                for row in raw_rows
                if row.get(sector_col)
            ]
        )
        if sector_col
        else {}
    )

    stage_col = lookup.get("stage")

    stage_map = (
        cluster_category_values(
            [
                row.get(stage_col, "")
                for row in raw_rows
                if row.get(stage_col)
            ]
        )
        if stage_col
        else {}
    )

    deals: list[Deal] = []

    for row in raw_rows:
        flags: list[str] = []

        # -------------------------
        # Text fields
        # -------------------------

        name_col = lookup.get("deal_name")

        deal_name = (
            clean_text(row.get(name_col))
            if name_col
            else None
        )

        if deal_name is None:
            deal_name = "(unnamed)"

        client_col = lookup.get("client")

        client = (
            clean_text(row.get(client_col))
            if client_col
            else None
        )

        owner_col = lookup.get("owner")

        owner = (
            clean_text(row.get(owner_col))
            if owner_col
            else None
        )

        # -------------------------
        # Financial fields
        # -------------------------

        value_col = lookup.get("deal_value")

        deal_value = (
            clean_currency(row.get(value_col))
            if value_col
            else None
        )

        if value_col and deal_value is None:
            flags.append("deal_value")
            report.flag("deal_value")

        # -------------------------
        # Dates
        # -------------------------

        close_col = lookup.get("expected_close_date")

        close_date = (
            clean_date(row.get(close_col))
            if close_col
            else None
        )

        if close_col and close_date is None:
            flags.append("expected_close_date")
            report.flag("expected_close_date")

        created_col = lookup.get("created_date")

        created_date = (
            clean_date(row.get(created_col))
            if created_col
            else None
        )

        if created_col and created_date is None:
            flags.append("created_date")
            report.flag("created_date")

        # -------------------------
        # Sector
        # -------------------------

        raw_sector = (
            clean_text(row.get(sector_col))
            if sector_col
            else None
        )

        sector = (
            sector_map.get(raw_sector, raw_sector)
            if raw_sector
            else None
        )

        if sector_col and raw_sector is None:
            flags.append("sector")
            report.flag("sector")

        # -------------------------
        # Deal stage
        # -------------------------

        raw_stage = (
            clean_text(row.get(stage_col))
            if stage_col
            else None
        )

        stage = (
            stage_map.get(raw_stage, raw_stage)
            if raw_stage
            else None
        )

        if stage_col and raw_stage is None:
            flags.append("stage")
            report.flag("stage")

        # -------------------------
        # Build Deal
        # -------------------------

        deals.append(
            Deal(
                item_id=row["_item_id"],
                deal_name=deal_name,
                client=client,
                sector=sector,
                stage=stage,
                deal_value=deal_value,
                expected_close_date=close_date,
                owner=owner,
                created_date=created_date,
                quality_flags=flags,
            )
        )

    return deals, report
