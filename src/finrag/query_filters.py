"""Read search filters (company, fiscal year) from the question text alone.

The parser uses only the question and the list of companies in the corpus, so it is
available at query time. It is deterministic and calls no model.
"""

import re
from collections.abc import Mapping, Sequence

# Names by which questions may refer to the corpus companies: legal or common names,
# ticker symbols and widely used short names. "AMEX" and "JPM" were added after reading
# the FinanceBench questions, which may make evaluation results slightly optimistic.
COMPANY_ALIASES: Mapping[str, Sequence[str]] = {
    "3M": ("3M", "MMM"),
    "American Express": ("American Express", "AMEX", "AXP"),
    "Best Buy": ("Best Buy", "BBY"),
    "JPMorgan": ("JPMorgan", "JP Morgan", "JPM"),
    "PepsiCo": ("PepsiCo", "Pepsi", "PEP"),
}

_YEAR = re.compile(r"(?<![0-9])(?:FY\s?)?((?:19|20)[0-9]{2})(?![0-9])", re.IGNORECASE)


def _alias_pattern(alias: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias)}(?![A-Za-z0-9])", re.IGNORECASE)


_PATTERNS = {
    company: [_alias_pattern(a) for a in aliases] for company, aliases in COMPANY_ALIASES.items()
}


def parse_company(question: str) -> str | None:
    """Return the one corpus company named in the question, or None if zero or several."""
    found = {c for c, patterns in _PATTERNS.items() if any(p.search(question) for p in patterns)}
    return found.pop() if len(found) == 1 else None


def parse_years(question: str) -> list[int]:
    """Return the distinct four-digit years in the question, sorted."""
    return sorted({int(match) for match in _YEAR.findall(question)})


def parse_filters(question: str) -> tuple[str | None, int | None]:
    """Return (company, fiscal_year) read from the question.

    A filter is set only when the question names exactly one company or exactly one year;
    otherwise it is None, so the search is not narrowed by a guess.
    """
    years = parse_years(question)
    return parse_company(question), years[0] if len(years) == 1 else None
