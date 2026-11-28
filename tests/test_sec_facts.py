"""Tests for SEC companyfacts selection, manifest entries and the FinanceBench check helpers."""

import json
from datetime import date
from decimal import Decimal

import pytest

from finrag import sec_facts
from finrag.sec_facts import (
    COMPANIES,
    CONCEPTS,
    SnapshotError,
    check_entity,
    company_by_name,
    edgar_url,
    filing_row,
    fiscal_year_of,
    manifest_entry,
    parse_answer,
    pipeline_version,
    sec_user_agent,
    select_annual_facts,
    within_tolerance,
)
from tests.sec_fixture import ACCN_2098, ACCN_2099, SAMPLE_SEC_COMPANY, companyfacts


def _facts(filing):
    return {f.concept: f for f in filing.facts}


def test_one_filing_per_annual_report_oldest_first():
    filings = select_annual_facts(companyfacts())
    assert [(f.accession, f.fiscal_year) for f in filings] == [
        (ACCN_2098, 2098),
        (ACCN_2099, 2099),
    ]
    assert filings[1].period_end == date(2099, 12, 31)


def test_keeps_only_current_period_values():
    """Comparatives of earlier years and the fourth-quarter value are dropped."""
    latest = _facts(select_annual_facts(companyfacts())[1])
    assert latest["capex"].value == Decimal(90)
    assert latest["capex"].period_start == date(2099, 1, 1)
    assert latest["total_assets"].value == Decimal(1100)
    assert latest["total_assets"].period_start is None


def test_each_value_is_stored_once():
    filings = select_annual_facts(companyfacts())
    capex = [(f.fiscal_year, _facts(f)["capex"].value) for f in filings]
    assert capex == [(2098, Decimal(80)), (2099, Decimal(90))]


def test_quarterly_reports_are_ignored():
    filings = select_annual_facts(companyfacts())
    assert all(f.accession != "0009999999-99-000003" for f in filings)


def test_tag_priority_and_fallback():
    first, latest = select_annual_facts(companyfacts())
    assert _facts(first)["revenue"].raw_tag == "SalesRevenueNet"
    assert _facts(latest)["revenue"].raw_tag == "Revenues"


def test_unit_is_kept():
    latest = _facts(select_annual_facts(companyfacts())[1])
    assert latest["eps_diluted"].unit == "USD/shares"
    assert latest["eps_diluted"].value == Decimal("1.25")


def test_unmapped_tags_are_not_loaded():
    for filing in select_annual_facts(companyfacts()):
        assert all(f.raw_tag != "UnusedTag" for f in filing.facts)


def test_conflicting_values_are_reported_not_loaded():
    data = companyfacts()
    capex = data["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]["units"]["USD"]
    capex.append(dict(capex[3], val=95))
    latest = select_annual_facts(data)[1]
    assert "capex" not in _facts(latest)
    assert latest.conflicts and "capex" in latest.conflicts[0]


def test_53_week_year_counts_as_annual():
    data = companyfacts()
    capex = data["facts"]["us-gaap"]["PaymentsToAcquirePropertyPlantAndEquipment"]["units"]["USD"]
    capex[:] = [
        {
            "start": "2098-02-01",
            "end": "2099-02-06",
            "val": 7,
            "accn": ACCN_2099,
            "fy": 2099,
            "fp": "FY",
            "form": "10-K",
            "filed": "2099-03-20",
        }
    ]
    data["facts"]["us-gaap"] = {
        "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": capex}}
    }
    (filing,) = select_annual_facts(data)
    assert filing.period_end == date(2099, 2, 6)
    assert _facts(filing)["capex"].value == Decimal(7)


def test_fiscal_year_comes_from_period_end_not_sec_fy():
    """The SEC fy field can repeat the previous year; the period end date decides."""
    data = companyfacts()
    for values in data["facts"]["us-gaap"].values():
        for unit_values in values["units"].values():
            for entry in unit_values:
                if entry["accn"] == ACCN_2099:
                    entry["fy"] = 2098
    latest = select_annual_facts(data)[1]
    assert latest.fiscal_year == 2099
    assert latest.sec_fiscal_year == 2098


@pytest.mark.parametrize(
    "period_end, year",
    [
        (date(2099, 12, 31), 2099),
        (date(2099, 12, 26), 2099),
        (date(2099, 1, 30), 2099),
        (date(2099, 2, 3), 2099),
        (date(2099, 1, 2), 2098),
        (date(2099, 1, 7), 2098),
        (date(2099, 1, 8), 2099),
    ],
)
def test_fiscal_year_of(period_end, year):
    assert fiscal_year_of(period_end) == year


def test_malformed_entry_is_an_error():
    data = companyfacts()
    del data["facts"]["us-gaap"]["Assets"]["units"]["USD"][0]["val"]
    with pytest.raises(SnapshotError, match="malformed"):
        select_annual_facts(data)


def test_filing_without_annual_values_is_skipped():
    data = {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "end": "2099-12-31",
                                "val": 1,
                                "accn": "x",
                                "fy": 2099,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2099-12-31",
                            }
                        ]
                    }
                }
            }
        }
    }
    assert select_annual_facts(data) == []


def test_check_entity_accepts_matching_file():
    assert check_entity(SAMPLE_SEC_COMPANY, companyfacts()) == "SAMPLECO (SYNTHETIC) INC"


@pytest.mark.parametrize(
    "change", [{"cik": 1}, {"entityName": "OTHERCO INC"}, {"cik": None, "entityName": None}]
)
def test_check_entity_rejects_other_company(change):
    data = companyfacts() | {k: v for k, v in change.items() if v is not None}
    for key, value in change.items():
        if value is None:
            data.pop(key)
    with pytest.raises(SnapshotError):
        check_entity(SAMPLE_SEC_COMPANY, data)


def test_manifest_entry_records_hash_and_size():
    data = json.dumps(companyfacts()).encode()
    entry = manifest_entry(SAMPLE_SEC_COMPANY, data)
    assert entry["path"] == "CIK0009999999.json"
    assert entry["url"].endswith("/CIK0009999999.json")
    assert entry["bytes"] == len(data)
    assert len(entry["sha256"]) == 64


def test_build_manifest_names_source_and_date():
    manifest = sec_facts.build_manifest([], "2099-01-02")
    assert manifest["source"]["retrieved"] == "2099-01-02"
    assert manifest["source"]["api"].startswith("https://data.sec.gov/")


def test_filing_row_and_edgar_url():
    filing = select_annual_facts(companyfacts())[1]
    row = filing_row(SAMPLE_SEC_COMPANY, filing, "abc", prefix="TEST-SEC-")
    assert row["filing_id"] == f"TEST-SEC-{ACCN_2099}"
    assert row["fiscal_year"] == 2099
    assert row["form"] == "10-K"
    assert row["source_url"] == edgar_url(9_999_999, ACCN_2099)
    assert row["source_url"].endswith("/9999999/000999999900000002/0009999999-00-000002-index.htm")


def test_pipeline_version_changes_with_concepts(monkeypatch):
    before = pipeline_version()
    monkeypatch.setattr(sec_facts, "CONCEPTS", CONCEPTS + (("extra", ("ExtraTag",)),))
    assert pipeline_version() != before


def test_concept_tags_are_unique():
    tags = [tag for _, tags in CONCEPTS for tag in tags]
    assert len(tags) == len(set(tags))


def test_companies_match_financebench_names():
    assert [c.name for c in COMPANIES] == [
        "3M",
        "American Express",
        "Best Buy",
        "JPMorgan",
        "PepsiCo",
    ]
    assert company_by_name("3M").file_name == "CIK0000066740.json"
    with pytest.raises(KeyError):
        company_by_name("OtherCo")


@pytest.mark.parametrize("value", ["", "no address", None])
def test_user_agent_requires_contact(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    else:
        monkeypatch.setenv("SEC_USER_AGENT", value)
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        sec_user_agent()


def test_user_agent_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("SEC_USER_AGENT", "finRAG research someone@example.com")
    assert sec_user_agent() == "finRAG research someone@example.com"


@pytest.mark.parametrize(
    "text, expected",
    [("$1577.00", Decimal("1577.00")), ("$4.60", Decimal("4.60")), ("1,234", Decimal(1234))],
)
def test_parse_answer(text, expected):
    assert parse_answer(text) == expected


def test_parse_answer_rejects_text():
    with pytest.raises(ValueError):
        parse_answer("2.8%")


@pytest.mark.parametrize(
    "computed, expected, ok",
    [
        (Decimal("8.74"), Decimal("8.70"), True),
        (Decimal("8.80"), Decimal("8.70"), False),
        (Decimal(0), Decimal(0), True),
        (Decimal(1), Decimal(0), False),
    ],
)
def test_within_tolerance(computed, expected, ok):
    assert within_tolerance(computed, expected) is ok
