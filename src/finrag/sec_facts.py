"""SEC XBRL company facts: snapshot download, current-period selection and loading (ADR 0010).

Source: the SEC "companyfacts" API, one JSON file per company. Each 10-K also repeats the
values of earlier years, and every entry carries the fiscal year of the filing (fy), not the
year of the value. Only current-period values are kept: annual values that end on the
filing's period end date, and balance sheet values dated on that day.

The fiscal year of a filing is derived from its period end date (fiscal_year_of), because
the SEC fy field is not always right: Best Buy's 10-K for the year ended 2021-01-30 has
fy 2020, the same as the year before.
"""

import hashlib
import json
import os
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

import psycopg
from psycopg.rows import DictRow

API_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
TAXONOMY = "us-gaap"
ANNUAL_FORM = "10-K"
ANNUAL_PERIOD = "FY"
# A fiscal year lasts 52 or 53 weeks (364 or 371 days) or one calendar year (364 or 365
# days between start and end). The range leaves a small margin around these values.
ANNUAL_DAYS = range(350, 381)
FILING_PREFIX = "SEC-"
SELECTION_VERSION = "current-period v1"

Record = dict[str, Any]


@dataclass(frozen=True)
class SecCompany:
    """A company in the corpus: the name used in filings, its CIK, and a name check."""

    name: str
    cik: int
    entity_keyword: str  # must appear in the entityName returned by the SEC

    @property
    def url(self) -> str:
        """Return the companyfacts URL of this company."""
        return API_URL.format(cik=self.cik)

    @property
    def file_name(self) -> str:
        """Return the local snapshot file name, for example CIK0000066740.json."""
        return f"CIK{self.cik:010d}.json"


COMPANIES: tuple[SecCompany, ...] = (
    SecCompany("3M", 66740, "3M"),
    SecCompany("American Express", 4962, "AMERICAN EXPRESS"),
    SecCompany("Best Buy", 764478, "BEST BUY"),
    SecCompany("JPMorgan", 19617, "JPMORGAN"),
    SecCompany("PepsiCo", 77476, "PEPSICO"),
)

# Normalized concepts and their us-gaap tags, in priority order: for each filing the first
# tag that has a current-period value is used. The list was chosen with knowledge of the
# FinanceBench questions (see ADR 0010 and the evaluation integrity rules in CLAUDE.md).
CONCEPTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "revenue",
        (
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "RevenuesNetOfInterestExpense",
            "SalesRevenueNet",
        ),
    ),
    ("cost_of_revenue", ("CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold")),
    ("gross_profit", ("GrossProfit",)),
    ("operating_income", ("OperatingIncomeLoss",)),
    ("net_income", ("NetIncomeLoss",)),
    ("eps_diluted", ("EarningsPerShareDiluted",)),
    ("total_assets", ("Assets",)),
    ("total_liabilities", ("Liabilities",)),
    ("stockholders_equity", ("StockholdersEquity",)),
    ("cash", ("CashAndCashEquivalentsAtCarryingValue",)),
    ("inventory", ("InventoryNet",)),
    ("ppe_net", ("PropertyPlantAndEquipmentNet",)),
    ("long_term_debt", ("LongTermDebtNoncurrent", "LongTermDebt")),
    ("operating_cash_flow", ("NetCashProvidedByUsedInOperatingActivities",)),
    ("capex", ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets")),
    (
        "depreciation_amortization",
        (
            "DepreciationDepletionAndAmortization",
            "DepreciationAndAmortization",
            "DepreciationAmortizationAndAccretionNet",
        ),
    ),
    ("dividends_paid", ("PaymentsOfDividendsCommonStock", "PaymentsOfDividends")),
    ("share_repurchases", ("PaymentsForRepurchaseOfCommonStock",)),
)
CONCEPT_NAMES: tuple[str, ...] = tuple(name for name, _ in CONCEPTS)


class SnapshotError(ValueError):
    """A companyfacts file does not belong to the expected company or is malformed."""


@dataclass(frozen=True)
class Entry:
    """One raw companyfacts value of one tag and unit."""

    tag: str
    unit: str
    start: date | None
    end: date
    value: Decimal
    accession: str
    fiscal_year: int
    filed: date


@dataclass(frozen=True)
class Fact:
    """One selected current-period value, ready to store."""

    concept: str
    raw_tag: str
    period_start: date | None
    period_end: date
    value: Decimal
    unit: str


@dataclass(frozen=True)
class AnnualFiling:
    """One 10-K with its fiscal year, period end date and current-period facts."""

    accession: str
    fiscal_year: int  # derived from period_end (fiscal_year_of)
    sec_fiscal_year: int  # the fy field of the SEC entries, kept for comparison
    period_end: date
    filed: date
    facts: tuple[Fact, ...]
    conflicts: tuple[str, ...] = ()  # concepts skipped because one tag had several values


def concepts_digest() -> str:
    """Return a short hash of the concept map; a change forces a reload."""
    text = json.dumps(CONCEPTS, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def pipeline_version() -> str:
    """Describe everything that changes the stored facts."""
    return f"sec companyfacts {SELECTION_VERSION}; concepts {concepts_digest()}"


def sec_user_agent() -> str:
    """Return the User-Agent for SEC requests from SEC_USER_AGENT.

    The SEC asks automated clients to name themselves and give a contact email address.
    Raises RuntimeError when the variable is missing or has no email address.
    """
    agent = os.environ.get("SEC_USER_AGENT", "").strip()
    if "@" not in agent:
        raise RuntimeError(
            'SEC_USER_AGENT is not set. Add SEC_USER_AGENT="finRAG research <email>" to .env.'
        )
    return agent


def check_entity(company: SecCompany, data: Record) -> str:
    """Return the entityName of a companyfacts file; raise SnapshotError on a mismatch."""
    name = str(data.get("entityName", ""))
    if int(data.get("cik", -1)) != company.cik or company.entity_keyword not in name.upper():
        raise SnapshotError(f"{company.file_name}: expected {company.name}, got {name!r}")
    return name


def _entries(data: Record, tags: Iterable[str]) -> list[Entry]:
    """Return the 10-K annual entries of the given us-gaap tags."""
    facts = data.get("facts", {}).get(TAXONOMY, {})
    entries: list[Entry] = []
    for tag in tags:
        for unit, values in facts.get(tag, {}).get("units", {}).items():
            for raw in values:
                if raw.get("form") != ANNUAL_FORM or raw.get("fp") != ANNUAL_PERIOD:
                    continue
                entries.append(_entry(tag, unit, raw))
    return entries


def _entry(tag: str, unit: str, raw: Record) -> Entry:
    try:
        return Entry(
            tag=tag,
            unit=unit,
            start=date.fromisoformat(raw["start"]) if raw.get("start") else None,
            end=date.fromisoformat(raw["end"]),
            value=Decimal(str(raw["val"])),
            accession=str(raw["accn"]),
            fiscal_year=int(raw["fy"]),
            filed=date.fromisoformat(raw["filed"]),
        )
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise SnapshotError(f"{tag}: malformed entry {raw!r}") from exc


def fiscal_year_of(period_end: date) -> int:
    """Return the fiscal year named by the calendar year in which the fiscal year ends.

    A 52/53-week year that ends in the first seven days of January belongs to the
    previous year (for example, a year ending 2021-01-02 is fiscal 2020).
    """
    if period_end.month == 1 and period_end.day <= 7:
        return period_end.year - 1
    return period_end.year


def is_annual(entry: Entry) -> bool:
    """True for a duration value of about one year."""
    return entry.start is not None and (entry.end - entry.start).days in ANNUAL_DAYS


def is_current(entry: Entry, period_end: date) -> bool:
    """True for an annual value ending on period_end, or an instant value on period_end."""
    return entry.end == period_end and (entry.start is None or is_annual(entry))


def _pick(concept: str, tags: tuple[str, ...], current: list[Entry]) -> Fact | None:
    """Return the value of the first tag with a current value; None if no tag has one.

    Raises ValueError when that tag has different values for the same period.
    """
    for tag in tags:
        found = [e for e in current if e.tag == tag]
        if not found:
            continue
        distinct = {(e.unit, e.start, e.value) for e in found}
        if len(distinct) > 1:
            raise ValueError(f"{concept}: {tag} has {len(distinct)} different values")
        e = found[0]
        return Fact(concept, tag, e.start, e.end, e.value, e.unit)
    return None


def _annual_filing(accession: str, entries: list[Entry]) -> AnnualFiling | None:
    annual = [e for e in entries if is_annual(e)]
    if not annual:
        return None
    period_end = max(e.end for e in annual)
    current = [e for e in entries if is_current(e, period_end)]
    facts: list[Fact] = []
    conflicts: list[str] = []
    for concept, tags in CONCEPTS:
        try:
            fact = _pick(concept, tags, current)
        except ValueError as exc:
            conflicts.append(str(exc))
            continue
        if fact is not None:
            facts.append(fact)
    return AnnualFiling(
        accession=accession,
        fiscal_year=fiscal_year_of(period_end),
        sec_fiscal_year=max(e.fiscal_year for e in entries),
        period_end=period_end,
        filed=min(e.filed for e in entries),
        facts=tuple(facts),
        conflicts=tuple(conflicts),
    )


def select_annual_facts(data: Record) -> list[AnnualFiling]:
    """Return one AnnualFiling per 10-K with its current-period facts, oldest first.

    Values that a 10-K repeats for earlier years are dropped: each value is stored once,
    with the filing that reports it as current.
    """
    all_tags = [tag for _, tags in CONCEPTS for tag in tags]
    by_accession: dict[str, list[Entry]] = defaultdict(list)
    for entry in _entries(data, all_tags):
        by_accession[entry.accession].append(entry)
    filings = [_annual_filing(accn, entries) for accn, entries in by_accession.items()]
    return sorted((f for f in filings if f is not None), key=lambda f: (f.period_end, f.accession))


def filing_id(accession: str, prefix: str = FILING_PREFIX) -> str:
    """Return the filings.filing_id of an SEC filing, for example SEC-0001558370-19-000470."""
    return f"{prefix}{accession}"


def edgar_url(cik: int, accession: str) -> str:
    """Return the EDGAR index page of a filing."""
    return (
        f"https://www.sec.gov/Archives/edgar/data/{cik}/"
        f"{accession.replace('-', '')}/{accession}-index.htm"
    )


def filing_row(
    company: SecCompany, filing: AnnualFiling, sha256: str, prefix: str = FILING_PREFIX
) -> dict[str, Any]:
    """Map an AnnualFiling to a filings row."""
    return {
        "filing_id": filing_id(filing.accession, prefix),
        "company": company.name,
        "cik": str(company.cik),
        "form": ANNUAL_FORM,
        "fiscal_year": filing.fiscal_year,
        "period_end": filing.period_end,
        "source_url": edgar_url(company.cik, filing.accession),
        "source_sha256": sha256,
    }


def sync_aliases(conn: psycopg.Connection[DictRow]) -> list[str]:
    """Store every tag of the concept map in concept_aliases. Return the tags added."""
    added: list[str] = []
    with conn.transaction():
        for concept, tags in CONCEPTS:
            for tag in tags:
                row = conn.execute(
                    "insert into concept_aliases (raw_tag, concept) values (%s, %s) "
                    "on conflict (raw_tag) do update set concept = excluded.concept "
                    "returning (xmax = 0) as inserted",
                    (tag, concept),
                ).fetchone()
                if row and row["inserted"]:
                    added.append(tag)
    return added


def load_annual_filing(
    conn: psycopg.Connection[DictRow], row: dict[str, Any], facts: Iterable[Fact], version: str
) -> None:
    """Replace one SEC filing and its facts in a single transaction."""
    with conn.transaction():
        conn.execute(
            "insert into filings (filing_id, company, cik, form, fiscal_year, period_end, "
            "source_url, source_sha256, pipeline_version) "
            "values (%(filing_id)s, %(company)s, %(cik)s, %(form)s, %(fiscal_year)s, "
            "%(period_end)s, %(source_url)s, %(source_sha256)s, %(version)s) "
            "on conflict (filing_id) do update set company = excluded.company, "
            "cik = excluded.cik, form = excluded.form, fiscal_year = excluded.fiscal_year, "
            "period_end = excluded.period_end, source_url = excluded.source_url, "
            "source_sha256 = excluded.source_sha256, "
            "pipeline_version = excluded.pipeline_version, ingested_at = now()",
            row | {"version": version},
        )
        conn.execute("delete from facts where filing_id = %s", (row["filing_id"],))
        with conn.cursor() as cursor:
            cursor.executemany(
                "insert into facts (filing_id, concept, raw_tag, period_start, period_end, "
                "value, unit, source, confidence) "
                "values (%s, %s, %s, %s, %s, %s, %s, 'xbrl', 1.0)",
                [
                    (
                        row["filing_id"],
                        f.concept,
                        f.raw_tag,
                        f.period_start,
                        f.period_end,
                        f.value,
                        f.unit,
                    )
                    for f in facts
                ],
            )


# --- Snapshot manifest -------------------------------------------------------------------

Fetcher = Callable[[str], bytes]


def manifest_entry(company: SecCompany, data: bytes) -> Record:
    """Check a downloaded file and return its manifest entry."""
    entity = check_entity(company, json.loads(data))
    return {
        "company": company.name,
        "cik": company.cik,
        "entity_name": entity,
        "url": company.url,
        "path": company.file_name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }


def build_manifest(entries: list[Record], retrieved: str) -> Record:
    """Build the snapshot manifest. retrieved is the UTC download date (YYYY-MM-DD)."""
    return {
        "source": {
            "api": "https://data.sec.gov/api/xbrl/companyfacts/",
            "documentation": "https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
            "retrieved": retrieved,
            "note": "SEC data changes over time; this file records the snapshot that was loaded.",
        },
        "companies": entries,
    }


def company_by_name(name: str) -> SecCompany:
    """Return the configured company with this name; raise KeyError if unknown."""
    for company in COMPANIES:
        if company.name == name:
            return company
    raise KeyError(name)


# --- Verification against FinanceBench (labels used for scoring only) --------------------


@dataclass(frozen=True)
class FactCheck:
    """A FinanceBench question whose answer is a sum of stored facts, used to check loading.

    terms are (concept, sign) pairs; scale converts USD to the unit of the answer.
    """

    question_id: str
    company: str
    fiscal_year: int
    terms: tuple[tuple[str, int], ...]
    scale: Decimal


MILLIONS = Decimal(1_000_000)
BILLIONS = Decimal(1_000_000_000)
TOLERANCE = Decimal("0.01")  # FinanceBench answers are rounded; allow 1 percent

FACT_CHECKS: tuple[FactCheck, ...] = (
    FactCheck("financebench_id_03029", "3M", 2018, (("capex", 1),), MILLIONS),
    FactCheck("financebench_id_04672", "3M", 2018, (("ppe_net", 1),), BILLIONS),
    FactCheck("financebench_id_04417", "Best Buy", 2019, (("inventory", 1),), MILLIONS),
    FactCheck("financebench_id_04980", "PepsiCo", 2021, (("capex", 1),), BILLIONS),
    FactCheck(
        "financebench_id_03620",
        "PepsiCo",
        2022,
        (("operating_income", 1), ("depreciation_amortization", 1), ("capex", -1)),
        MILLIONS,
    ),
)


def parse_answer(text: str) -> Decimal:
    """Parse a FinanceBench numeric answer such as '$1577.00' or '$4.60'."""
    cleaned = text.strip().removeprefix("$").replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"not a plain number: {text!r}") from exc


def within_tolerance(computed: Decimal, expected: Decimal) -> bool:
    """True when computed is within TOLERANCE of expected (relative)."""
    if expected == 0:
        return computed == 0
    return abs(computed - expected) / abs(expected) <= TOLERANCE
