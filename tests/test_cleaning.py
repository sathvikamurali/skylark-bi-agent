"""
Unit tests for data/cleaning.py using synthetic messy inputs — these are
fixtures for testing the cleaning LOGIC only. They are never used as a data
source for the running agent (which always reads from monday.com live).
"""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.cleaning import (
    clean_currency,
    clean_date,
    clean_text,
    cluster_category_values,
    is_null_token,
)


def test_is_null_token():
    assert is_null_token("")
    assert is_null_token("N/A")
    assert is_null_token("  n/a  ")
    assert is_null_token("-")
    assert not is_null_token("Energy")


def test_clean_text_collapses_whitespace_and_strips():
    assert clean_text("  Energy   Sector  ") == "Energy Sector"
    assert clean_text("N/A") is None
    assert clean_text(None) is None


def test_clean_date_handles_multiple_formats():
    assert clean_date("2026-03-15") == date(2026, 3, 15)
    assert clean_date("15/03/2026") == date(2026, 3, 15)
    assert clean_date("March 15, 2026") == date(2026, 3, 15)
    assert clean_date("TBD") is None
    assert clean_date("") is None
    assert clean_date(None) is None


def test_clean_date_iso_format_not_misread_as_dayfirst():
    # Regression test: dateutil's dayfirst=True flag will silently swap
    # month/day on an ISO string like "2025-12-01" (treating it as day=12,
    # month=01) unless ISO format is detected and parsed explicitly first.
    assert clean_date("2025-12-01") == date(2025, 12, 1)
    assert clean_date("2025-01-05") == date(2025, 1, 5)


def test_clean_date_excel_serial():
    # 45732 == 2025-03-15 in Excel's 1899-12-30 epoch
    result = clean_date("45732")
    assert result is not None
    assert result.year == 2025


def test_clean_currency_variants():
    assert clean_currency("₹12,50,000") == 1_250_000.0
    assert clean_currency("$45,000") == 45_000.0
    assert clean_currency("1.2 Cr") == 12_000_000.0
    assert clean_currency("45K") == 45_000.0
    assert clean_currency("(5000)") == -5000.0
    assert clean_currency("N/A") is None
    assert clean_currency("") is None


def test_cluster_category_values_groups_near_duplicates():
    raw = ["Energy", "energy", " ENERGY ", "Energy", "Agriculture", "agriculture "]
    mapping = cluster_category_values(raw)
    canonical_values = set(mapping.values())
    # near-duplicates of "energy" should collapse to one canonical label
    energy_labels = {v for k, v in mapping.items() if k.lower().strip() == "energy"}
    assert len(canonical_values) <= 3  # roughly: Energy cluster + Agriculture cluster
    assert len(energy_labels) == 1


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-v"]))
