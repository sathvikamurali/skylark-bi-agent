"""
Data resilience layer.

monday.com returns every column's `text` value as a plain string regardless
of the column's configured type — a date column with a bad row still comes
back as a string like "N/A" or "15/03" (no year). This module turns that raw
text into clean, typed Python values and — just as importantly — keeps a
record of *what couldn't be cleaned*, so the agent can surface caveats
instead of silently dropping or misrepresenting bad rows.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from dateutil import parser as dateparser
from rapidfuzz import fuzz, process

NULL_TOKENS = {"", "n/a", "na", "none", "null", "-", "--", "tbd", "unknown", "?"}

CURRENCY_SUFFIX_MULTIPLIERS = {
    "k": 1_000,
    "l": 100_000,
    "lac": 100_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "cr": 10_000_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "m": 1_000_000,
    "mn": 1_000_000,
}


@dataclass
class DataQualityReport:
    """Accumulates cleaning issues across a whole board so the agent can
    report caveats like '12 of 340 deals had unparseable close dates'."""

    total_rows: int = 0
    field_issue_counts: dict[str, int] = field(default_factory=dict)
    unmapped_category_values: dict[str, set] = field(default_factory=dict)

    def flag(self, field_name: str):
        self.field_issue_counts[field_name] = self.field_issue_counts.get(field_name, 0) + 1

    def flag_unmapped_category(self, category_field: str, raw_value: str):
        self.unmapped_category_values.setdefault(category_field, set()).add(raw_value)

    def summary(self) -> str:
        if not self.field_issue_counts and not self.unmapped_category_values:
            return "No data quality issues detected."
        lines = [f"Data quality caveats (of {self.total_rows} rows):"]
        for f, count in sorted(self.field_issue_counts.items(), key=lambda x: -x[1]):
            pct = (count / self.total_rows * 100) if self.total_rows else 0
            lines.append(f"  - '{f}': {count} rows ({pct:.0f}%) missing or unparseable")
        for f, vals in self.unmapped_category_values.items():
            if vals:
                lines.append(f"  - '{f}': untranslated values seen — {sorted(vals)}")
        return "\n".join(lines)


def is_null_token(raw: Optional[str]) -> bool:
    if raw is None:
        return True
    return raw.strip().lower() in NULL_TOKENS


def clean_text(raw: Optional[str]) -> Optional[str]:
    """Collapse whitespace, strip, and treat placeholder tokens as missing."""
    if is_null_token(raw):
        return None
    return re.sub(r"\s+", " ", raw.strip())


def clean_date(raw: Optional[str], default_day_first: bool = True) -> Optional[date]:
    """Parse dates from wildly inconsistent formats: '15/03/2026',
    '2026-03-15', 'March 15 2026', Excel serials like '45732', etc.
    Returns None (never raises) if nothing plausible can be extracted —
    callers should treat None as 'missing', not 'zero'."""
    if is_null_token(raw):
        return None
    raw = raw.strip()

    # Excel serial date (days since 1899-12-30), often leaks through when a
    # date cell was typed/pasted as plain text.
    if re.fullmatch(r"\d{5}", raw):
        try:
            serial = int(raw)
            if 20000 < serial < 60000:  # sane range: ~1954-2064
                base = datetime(1899, 12, 30)
                return (base + timedelta(days=serial)).date()
        except (ValueError, OverflowError):
            pass

    # Unambiguous ISO format (YYYY-MM-DD, optionally with a time component).
    # Must be checked before the dayfirst fallback below: dateutil's
    # dayfirst=True flag applies even to YYYY-MM-DD strings and silently
    # swaps month/day when both are <=12 (e.g. "2025-12-01" -> Jan 12, not
    # Dec 1). ISO order is never ambiguous, so parse it directly.
    iso_match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if iso_match:
        try:
            y, m, d = (int(x) for x in iso_match.groups())
            return date(y, m, d)
        except ValueError:
            pass  # fall through to fuzzy parsing below

    try:
        parsed = dateparser.parse(raw, dayfirst=default_day_first, fuzzy=True)
        return parsed.date()
    except (ValueError, OverflowError, TypeError):
        return None


def clean_currency(raw: Optional[str]) -> Optional[float]:
    """Parse amounts like '₹12,50,000', '$45K', '1.2 Cr', '(5000)' (accounting
    negative), '45000.00 INR'. Returns None if no number could be found."""
    if is_null_token(raw):
        return None
    text = raw.strip().lower()

    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")

    # Strip currency symbols/codes, keep digits, separators, and unit letters.
    text = re.sub(r"[₹$€£]|inr|usd|rs\.?|/-", "", text).strip()

    match = re.search(r"([\d,]+\.?\d*)\s*([a-z]*)", text)
    if not match:
        return None
    number_part, suffix = match.groups()
    number_part = number_part.replace(",", "")
    if not number_part or number_part == ".":
        return None

    try:
        value = float(number_part)
    except ValueError:
        return None

    multiplier = CURRENCY_SUFFIX_MULTIPLIERS.get(suffix.strip())
    if multiplier:
        value *= multiplier

    return -value if negative else value


def cluster_category_values(
    raw_values: list[str], similarity_threshold: int = 85
) -> dict[str, str]:
    """
    Build a raw -> canonical mapping for a categorical field WITHOUT assuming
    a known taxonomy ahead of time (we don't know the real sector/stage
    vocabulary until we see the data). Groups near-duplicate strings
    ("Energy", "energy ", "ENERGY-SECTOR") and picks the most frequent
    original spelling in each group as the canonical label.

    This is intentionally simple (greedy clustering) rather than a full
    clustering algorithm — appropriate for the small cardinality of
    sector/stage/status fields. See DECISION_LOG.md for the trade-off vs. a
    hardcoded canonical list.
    """
    cleaned = [clean_text(v) for v in raw_values]
    counts: dict[str, int] = {}
    for v in cleaned:
        if v:
            counts[v] = counts.get(v, 0) + 1

    unique_values = sorted(counts.keys(), key=lambda v: -counts[v])
    mapping: dict[str, str] = {}
    canonical_pool: list[str] = []

    for value in unique_values:
        if not canonical_pool:
            canonical_pool.append(value)
            mapping[value] = value
            continue

        match, score, _ = process.extractOne(
            value.lower(),
            canonical_pool,
            scorer=fuzz.token_sort_ratio,
            processor=lambda s: s.lower(),
        )
        if score >= similarity_threshold:
            mapping[value] = match
        else:
            canonical_pool.append(value)
            mapping[value] = value

    return mapping
