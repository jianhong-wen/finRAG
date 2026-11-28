"""Tests for reading search filters from question text."""

import pytest

from finrag.query_filters import parse_company, parse_filters, parse_years


@pytest.mark.parametrize(
    "question, expected",
    [
        ("What is the FY2018 capital expenditure amount for 3M?", ("3M", 2018)),
        (
            "Which of JPM's business segments had the lowest net revenue in 2021 Q1?",
            ("JPMorgan", 2021),
        ),
        (
            "Does AMEX have an improving operating margin profile as of 2022?",
            ("American Express", 2022),
        ),
        ("Was there any change in Best Buy stores in Q2 of FY2024?", ("Best Buy", 2024)),
        ("How did Pepsico's tax rate change between FY2021 and FY2022?", ("PepsiCo", None)),
        ("Does 3M maintain a stable trend of dividend distribution?", ("3M", None)),
        ("Compare 3M and PepsiCo margins in 2022.", (None, 2022)),
        ("What is the capital of France?", (None, None)),
    ],
)
def test_parse_filters(question, expected):
    assert parse_filters(question) == expected


def test_alias_must_be_a_whole_word():
    assert parse_company("The PEPPER index rose in 2022.") is None
    assert parse_company("Revenue rose 13M dollars.") is None


def test_years_are_distinct_and_sorted():
    assert parse_years("FY2023, FY2022 and FY2021; also 2022") == [2021, 2022, 2023]
    assert parse_years("Order 120225 shipped") == []
