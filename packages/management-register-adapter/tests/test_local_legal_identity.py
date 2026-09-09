"""Shared local legal identity Register proofs."""

from pathlib import Path

from asklegal_management_register import LocalLegalIdentityRegister
from asklegal_management_register_ports import (
    LegalIdentityKind,
    LegalIdentityRequest,
    SearchRecordIdentityRequest,
)


def test_identity_and_search_continuity_survive_restart(tmp_path: Path) -> None:
    """Both legal families receive stable IDs and explicit successor lineage."""
    path = tmp_path / "identity-register.json"
    first = LocalLegalIdentityRegister(path)
    legal_item = first.issue_identity(
        LegalIdentityRequest(LegalIdentityKind.LEGAL_ITEM, "HK:cap-1")
    )
    initial = first.issue_search_record(
        SearchRecordIdentityRequest("HK-LEG-ORDINANCES", "cap-1:s1:part-1", "sha256:" + "1" * 64)
    )
    first.commit()

    replay = LocalLegalIdentityRegister(path)
    assert (
        replay.issue_identity(LegalIdentityRequest(LegalIdentityKind.LEGAL_ITEM, "HK:cap-1"))
        == legal_item
    )
    reused = replay.issue_search_record(
        SearchRecordIdentityRequest("HK-LEG-ORDINANCES", "cap-1:s1:part-1", "sha256:" + "1" * 64)
    )
    successor = replay.issue_search_record(
        SearchRecordIdentityRequest("HK-LEG-ORDINANCES", "cap-1:s1:part-1", "sha256:" + "2" * 64)
    )
    replay.commit()

    assert initial.continuity == "INITIAL"
    assert reused.continuity == "REUSE"
    assert reused.search_record_id == initial.search_record_id
    assert successor.continuity == "SUCCESSOR"
    assert successor.search_record_id != initial.search_record_id
    assert successor.predecessor_record_id == initial.search_record_id
    assert successor.predecessor_payload_fingerprint == "sha256:" + "1" * 64
