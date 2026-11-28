"""Synthetic SEC companyfacts data for the fictional company SampleCo (fiscal years 2097-2099).

The structure follows the SEC companyfacts API; every value is invented.
"""

from typing import Any

from finrag.sec_facts import SecCompany

SAMPLE_SEC_COMPANY = SecCompany("SampleCo (synthetic)", 9_999_999, "SAMPLECO")
ACCN_2098 = "0009999999-99-000001"
ACCN_2099 = "0009999999-00-000002"


def _value(
    start: str | None, end: str, val: float, accn: str, fy: int, form: str = "10-K", fp: str = "FY"
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "end": end,
        "val": val,
        "accn": accn,
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": f"{fy + 1}-02-15" if fy < 2099 else "2099-12-31",
    }
    if start:
        entry["start"] = start
    return entry


def companyfacts() -> dict[str, Any]:
    """Return a companyfacts document with two 10-Ks and one 10-Q.

    The FY2099 10-K repeats the FY2098 values as comparatives, as real filings do.
    """
    capex = [
        _value("2097-01-01", "2097-12-31", 70, ACCN_2098, 2098),
        _value("2098-01-01", "2098-12-31", 80, ACCN_2098, 2098),
        _value("2098-01-01", "2098-12-31", 80, ACCN_2099, 2099),
        _value("2099-01-01", "2099-12-31", 90, ACCN_2099, 2099),
        # Fourth quarter inside the annual report: not an annual value.
        _value("2099-10-01", "2099-12-31", 25, ACCN_2099, 2099),
        _value("2099-01-01", "2099-03-31", 20, "0009999999-99-000003", 2099, "10-Q", "Q1"),
    ]
    assets = [
        _value(None, "2097-12-31", 900, ACCN_2098, 2098),
        _value(None, "2098-12-31", 1000, ACCN_2098, 2098),
        _value(None, "2098-12-31", 1000, ACCN_2099, 2099),
        _value(None, "2099-12-31", 1100, ACCN_2099, 2099),
    ]
    return {
        "cik": SAMPLE_SEC_COMPANY.cik,
        "entityName": "SAMPLECO (SYNTHETIC) INC",
        "facts": {
            "us-gaap": {
                "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": capex}},
                "Assets": {"units": {"USD": assets}},
                # Lower-priority revenue tag only in FY2098; the preferred tag in FY2099.
                "SalesRevenueNet": {
                    "units": {"USD": [_value("2098-01-01", "2098-12-31", 500, ACCN_2098, 2098)]}
                },
                "Revenues": {
                    "units": {"USD": [_value("2099-01-01", "2099-12-31", 600, ACCN_2099, 2099)]}
                },
                "EarningsPerShareDiluted": {
                    "units": {
                        "USD/shares": [_value("2099-01-01", "2099-12-31", 1.25, ACCN_2099, 2099)]
                    }
                },
                "UnusedTag": {"units": {"USD": [_value(None, "2099-12-31", 1, ACCN_2099, 2099)]}},
            },
            "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": []}}},
        },
    }
