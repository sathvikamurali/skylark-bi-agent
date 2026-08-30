"""
Typed, cleaned representations of the two boards. Field names here are our
own canonical names — they're mapped from whatever column titles actually
exist on the monday.com board via FIELD_ALIASES, so minor renames on the
board don't break the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional


# Column-title aliases -> canonical field name.
# Matching is case-insensitive and ignores surrounding whitespace.
WORK_ORDER_FIELD_ALIASES: dict[str, list[str]] = {
    "order_name": [
        "name",
        "work order",
        "order name",
        "project name",
    ],
    "client": [
        "client",
        "customer",
        "account",
        "customer name code",
    ],
    "sector": [
        "sector",
        "industry",
        "vertical",
    ],
    "status": [
        "status",
        "project status",
        "execution status",
    ],
    "start_date": [
        "start date",
        "kickoff date",
        "project start",
        "probable start date",
    ],
    "end_date": [
        "end date",
        "completion date",
        "delivery date",
        "probable end date",
    ],
    "order_value": [
        "order value",
        "revenue",
        "contract value",
        "value",
        "amount in rupees (excl of gst) (masked)",
    ],
    "location": [
        "location",
        "site",
        "region",
    ],
    "owner": [
        "owner",
        "bd/kam personnel code",
    ],
}


DEAL_FIELD_ALIASES: dict[str, list[str]] = {
    "deal_name": [
        "name",
        "deal name",
        "opportunity",
    ],
    "client": [
        "client",
        "customer",
        "account",
        "client code",
    ],
    "sector": [
        "sector",
        "industry",
        "vertical",
        "sector/service",
    ],
    "stage": [
        "stage",
        "deal stage",
        "pipeline stage",
    ],
    "deal_value": [
        "deal value",
        "value",
        "amount",
        "opportunity value",
        "masked deal value",
    ],
    "expected_close_date": [
        "expected close date",
        "close date",
        "target close",
        "close date (a)",
    ],
    "owner": [
        "owner",
        "sales owner",
        "deal owner",
        "rep",
        "owner code",
    ],
    "created_date": [
        "created date",
        "created",
        "date created",
    ],
}


def build_alias_lookup(
    raw_column_titles: list[str],
    aliases: dict[str, list[str]],
) -> dict[str, str]:
    """Map canonical field -> actual column title found on the live board."""
    lookup: dict[str, str] = {}

    normalized_titles = {
        title.strip().lower(): title
        for title in raw_column_titles
    }

    for canonical, options in aliases.items():
        for option in options:
            normalized_option = option.strip().lower()

            if normalized_option in normalized_titles:
                lookup[canonical] = normalized_titles[normalized_option]
                break

    return lookup


@dataclass
class WorkOrder:
    item_id: str
    order_name: str
    client: Optional[str]
    sector: Optional[str]
    status: Optional[str]
    start_date: Optional[date]
    end_date: Optional[date]
    order_value: Optional[float]
    location: Optional[str]
    owner: Optional[str]
    quality_flags: list[str]


@dataclass
class Deal:
    item_id: str
    deal_name: str
    client: Optional[str]
    sector: Optional[str]
    stage: Optional[str]
    deal_value: Optional[float]
    expected_close_date: Optional[date]
    owner: Optional[str]
    created_date: Optional[date]
    quality_flags: list[str]
