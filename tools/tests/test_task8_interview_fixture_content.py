"""Focused proof that the local Review fixture tells an honest interview story."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from asklegal_contracts import parse_json_bytes

from tools.tests.task8_local_review_fixture import write_task8_interview_review_fixture

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_ROOT = Path(__file__).resolve().parents[2]


def _document(path: Path) -> dict[str, JsonValue]:
    value = parse_json_bytes(path.read_bytes(), max_bytes=1_000_000)
    assert isinstance(value, dict)
    return value


def _record(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _text(record: dict[str, JsonValue], field: str) -> str:
    value = record[field]
    assert isinstance(value, str)
    return value


def test_fixture_freezes_two_explicitly_synthetic_realistic_legal_changes(
    tmp_path: Path,
) -> None:
    """Case treatment and amendment facts reach the reviewed desired state."""
    write_task8_interview_review_fixture(tmp_path, _ROOT)

    inventory = _document(tmp_path / "change-inventory/change-inventory.json")
    desired = _document(tmp_path / "desired-state-inventories/inventories.json")
    raw_records = desired["records"]
    assert isinstance(raw_records, list)
    records = [_record(record) for record in raw_records]
    assert inventory["additions"] == []
    assert inventory["replacements"] == [record["record_id"] for record in records]

    case, legislation = records
    assert case["material_type"] == "Case"
    assert case["source"] == "Synthetic Hong Kong Judiciary demo fixture"
    case_text = _text(case, "text")
    assert "SYNTHETIC INTERVIEW EXAMPLE" in case_text
    assert "followed fictional Demo Case A" in case_text
    assert "distinguished it on urgent interim relief" in case_text
    assert "No real Hong Kong judgment is represented" in case_text
    assert _text(case, "authority_note").startswith("Synthetic case-treatment update:")

    assert legislation["material_type"] == "Legislation"
    assert legislation["source"] == "Synthetic Hong Kong e-Legislation demo fixture"
    legislation_text = _text(legislation, "text")
    assert "SYNTHETIC INTERVIEW EXAMPLE" in legislation_text
    assert "before amendment" in legislation_text
    assert "within 14 days" in legislation_text
    assert "after amendment" in legislation_text
    assert "within 21 days" in legislation_text
    assert "fictional effective date 2026-08-01" in legislation_text
    assert "No real Hong Kong enactment is represented" in legislation_text
    assert _text(legislation, "authority_note").startswith("Synthetic legislation amendment:")
