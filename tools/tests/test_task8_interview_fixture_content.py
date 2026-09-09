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


def test_fixture_freezes_three_explicitly_synthetic_realistic_legal_changes(
    tmp_path: Path,
) -> None:
    """Case treatment and amendment facts reach the reviewed desired state."""
    write_task8_interview_review_fixture(tmp_path, _ROOT)

    inventory = _document(tmp_path / "change-inventory/change-inventory.json")
    desired = _document(tmp_path / "desired-state-inventories/inventories.json")
    raw_records = desired["records"]
    assert isinstance(raw_records, list)
    records = [_record(record) for record in raw_records]
    assert len(records) == 3
    records_by_id = {record["record_id"]: record for record in records}
    case_b_id = "rec_" + "3" * 48
    case_b = records_by_id[case_b_id]
    case_a = next(
        record
        for record in records
        if _text(record, "authority_note").startswith("Synthetic case-treatment update:")
    )
    legislation = next(record for record in records if record["material_type"] == "Legislation")
    assert inventory["additions"] == [case_b["record_id"]]
    assert inventory["replacements"] == [case_a["record_id"], legislation["record_id"]]

    assert case_a["material_type"] == "Case"
    assert case_a["source"] == "Synthetic Hong Kong Judiciary demo fixture"
    case_a_text = _text(case_a, "text")
    assert "SYNTHETIC DEMO EXAMPLE" in case_a_text
    assert "Later treatment" in case_a_text
    assert "followed that proposition" in case_a_text
    assert "distinguished its application" in case_a_text
    assert "No real Hong Kong judgment is represented" in case_a_text
    assert _text(case_a, "authority_note").startswith("Synthetic case-treatment update:")
    assert case_a["evidence_refs"] == ["evi_" + "1" * 48, "evi_" + "3" * 48]

    assert case_b["material_type"] == "Case"
    assert case_b["source"] == "Synthetic Hong Kong Judiciary demo fixture"
    case_b_text = _text(case_b, "text")
    assert "SYNTHETIC DEMO EXAMPLE" in case_b_text
    assert "Demo Court of Appeal Case B" in case_b_text
    assert "must give intelligible reasons" in case_b_text
    assert "urgent interim relief depend on context" in case_b_text
    assert "followed Case A's general" in case_b_text
    assert "distinguished Case A's non-urgent context" in case_b_text
    assert "No real Hong Kong judgment is represented" in case_b_text
    assert _text(case_b, "authority_note").startswith("No later treatment")
    assert case_b["evidence_refs"] == ["evi_" + "3" * 48]

    assert legislation["material_type"] == "Legislation"
    assert legislation["source"] == "Synthetic Hong Kong e-Legislation demo fixture"
    legislation_text = _text(legislation, "text")
    assert "SYNTHETIC DEMO EXAMPLE" in legislation_text
    assert "before amendment" in legislation_text
    assert "within 14 days" in legislation_text
    assert "after amendment" in legislation_text
    assert "within 21 days" in legislation_text
    assert "fictional effective date 2026-08-01" in legislation_text
    assert "No real Hong Kong enactment is represented" in legislation_text
    assert _text(legislation, "authority_note").startswith("Synthetic legislation amendment:")
