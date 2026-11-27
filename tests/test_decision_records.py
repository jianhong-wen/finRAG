"""Checks that the decision records are complete and agree with the code.

No database or network needed.
"""

import re
from pathlib import Path

from finrag.config import EMBED_DIM

ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = ROOT / "docs" / "adr"
ADR_NAME = re.compile(r"^(\d{4})-[a-z0-9-]+\.md$")
STATUS = re.compile(r"Status: (proposed|accepted|deprecated|superseded by ADR (\d{4}))\.")
SECTIONS = ("## Context", "## Decision", "## Alternatives considered", "## Consequences")


def adr_files() -> dict[str, Path]:
    """Return {number: path} for every ADR, excluding the index and the template."""
    records: dict[str, Path] = {}
    for path in sorted(ADR_DIR.glob("*.md")):
        if path.name == "README.md":
            continue
        match = ADR_NAME.match(path.name)
        assert match, f"{path.name}: the name must look like 0004-short-title.md"
        number = match.group(1)
        if number == "0000":  # the template
            continue
        assert number not in records, f"ADR {number} is used by more than one file"
        records[number] = path
    return records


def status_of(path: Path) -> tuple[str, str | None]:
    match = STATUS.search(path.read_text(encoding="utf-8"))
    assert match, f"{path.name}: needs a line like 'Date: 2026-11-27. Status: accepted.'"
    return match.group(1), match.group(2)


def test_there_is_at_least_one_adr():
    assert adr_files()


def test_every_adr_has_a_valid_status():
    for path in adr_files().values():
        status_of(path)


def test_every_adr_has_the_required_sections():
    for path in adr_files().values():
        text = path.read_text(encoding="utf-8")
        missing = [s for s in SECTIONS if s not in text]
        assert not missing, f"{path.name}: missing sections {missing}"


def test_superseded_adrs_point_to_an_existing_newer_adr():
    records = adr_files()
    for number, path in records.items():
        status, replacement = status_of(path)
        if not status.startswith("superseded"):
            continue
        assert replacement in records, f"{path.name}: ADR {replacement} does not exist"
        assert replacement > number, f"{path.name}: must be replaced by a newer ADR"
        newer = records[replacement].read_text(encoding="utf-8")
        assert f"Supersedes ADR {number}" in newer, (
            f"{records[replacement].name}: must say 'Supersedes ADR {number}.'"
        )


def test_index_lists_every_adr():
    index = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    missing = [p.name for p in adr_files().values() if f"({p.name})" not in index]
    assert not missing, f"docs/adr/README.md does not list {missing}"


def test_schema_vector_dimension_matches_config():
    schema = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
    dims = {int(d) for d in re.findall(r"vector\((\d+)\)", schema)}
    assert dims == {EMBED_DIM}, f"schema.sql uses vector{sorted(dims)}, config uses {EMBED_DIM}"


def test_an_accepted_adr_records_the_embedding_dimension():
    pattern = re.compile(rf"\b{EMBED_DIM}[- ]dimension|vector\({EMBED_DIM}\)")
    recorded = [
        path.name
        for path in adr_files().values()
        if status_of(path)[0] == "accepted" and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert recorded, f"No accepted ADR records the {EMBED_DIM}-dimension embedding decision"
