"""Semantic V1 proposal-member contract proofs."""

from dataclasses import replace
from hashlib import sha256

import pytest
from asklegal_contracts import (
    ProposalMemberViolation,
    canonicalize,
    parse_json_bytes,
    validate_v1_proposal_members,
)
from asklegal_contracts.json_types import JsonValue, checked_json_value

from tools.tests.proposal_member_fixture import semantic_proposal_fixture


def _changed(content: bytes, field: str, value: JsonValue) -> bytes:
    document = parse_json_bytes(content, max_bytes=1_000_000)
    assert isinstance(document, dict)
    document[field] = value
    return canonicalize(document)


def test_complete_semantic_proposal_is_admitted() -> None:
    """Every member can be recovered as one coherent review package."""
    fixture = semantic_proposal_fixture()

    validate_v1_proposal_members(fixture.contents, fixture.bindings, fixture.traceability_shards)


def test_traceability_reads_every_declared_shard_including_a_zero_entry_scope() -> None:
    """A proved-empty selected scope remains an exact zero-byte package member."""
    fixture = semantic_proposal_fixture(include_empty_scope=True)

    validate_v1_proposal_members(fixture.contents, fixture.bindings, fixture.traceability_shards)

    empty_path = next(path for path, content in fixture.traceability_shards.items() if not content)
    missing = dict(fixture.traceability_shards)
    del missing[empty_path]
    with pytest.raises(ProposalMemberViolation, match="shard inventory"):
        validate_v1_proposal_members(fixture.contents, fixture.bindings, missing)


def test_traceability_shard_tamper_and_undeclared_content_are_rejected() -> None:
    """The lookup root digest cannot substitute for every exact transitive byte."""
    fixture = semantic_proposal_fixture()
    path = next(iter(fixture.traceability_shards))
    tampered = dict(fixture.traceability_shards)
    tampered[path] += b"\n"
    undeclared = dict(fixture.traceability_shards)
    undeclared["entries/rts_" + "0" * 48 + ".ndjson"] = b""

    with pytest.raises(ProposalMemberViolation, match="shard fingerprint"):
        validate_v1_proposal_members(fixture.contents, fixture.bindings, tampered)
    with pytest.raises(ProposalMemberViolation, match="shard inventory"):
        validate_v1_proposal_members(fixture.contents, fixture.bindings, undeclared)


def test_traceability_payload_binding_must_equal_desired_state() -> None:
    """An exact shard cannot carry a different six-field payload fingerprint."""
    fixture = semantic_proposal_fixture()
    desired = parse_json_bytes(fixture.contents["DESIRED_STATE_INVENTORIES"], max_bytes=1_000_000)
    assert isinstance(desired, dict)
    records = desired["records"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    record["serving_payload_fingerprint"] = "sha256:" + "8" * 64
    contents = dict(fixture.contents)
    contents["DESIRED_STATE_INVENTORIES"] = canonicalize(desired)

    with pytest.raises(ProposalMemberViolation, match="desired-state binding"):
        validate_v1_proposal_members(contents, fixture.bindings, fixture.traceability_shards)


@pytest.mark.parametrize(
    ("role", "field", "value"),
    [
        ("DESIRED_STATE_INVENTORIES", "inventory_fingerprint", "sha256:" + "0" * 64),
        ("CORPUS_RELEASES", "observation_cutoff", "2026-08-21T00:00:00Z"),
        ("RECOVERY_READINESS", "predecessor_retained", False),
        ("REVIEW_REPORT", "record_count", 2),
        ("SERVING_STATE_DEFINITION", "serving_state_id", "srv_" + "0" * 48),
        ("VALIDATION", "result", "FAILED"),
    ],
)
def test_cross_member_or_admission_drift_is_rejected(
    role: str,
    field: str,
    value: JsonValue,
) -> None:
    """Correctly hashed JSON cannot override the package's linked facts."""
    fixture = semantic_proposal_fixture()
    contents = dict(fixture.contents)
    contents[role] = _changed(contents[role], field, value)

    with pytest.raises(ProposalMemberViolation):
        validate_v1_proposal_members(contents, fixture.bindings, fixture.traceability_shards)


def test_placeholder_and_noncanonical_member_bytes_are_rejected() -> None:
    """Byte integrity alone is not accepted as semantic evidence."""
    fixture = semantic_proposal_fixture()
    placeholder = dict(fixture.contents)
    placeholder["CHANGE_INVENTORY"] = canonicalize(checked_json_value({"role": "CHANGE_INVENTORY"}))
    noncanonical = dict(fixture.contents)
    noncanonical["CHANGE_INVENTORY"] += b"\n"

    with pytest.raises(ProposalMemberViolation, match="placeholder"):
        validate_v1_proposal_members(placeholder, fixture.bindings, fixture.traceability_shards)
    with pytest.raises(ProposalMemberViolation, match="canonical object"):
        validate_v1_proposal_members(noncanonical, fixture.bindings, fixture.traceability_shards)


def test_release_record_and_coverage_evidence_drift_are_rejected() -> None:
    """Desired records and CURRENT coverage must remain fully accounted."""
    fixture = semantic_proposal_fixture()
    releases = parse_json_bytes(fixture.contents["CORPUS_RELEASES"], max_bytes=1_000_000)
    assert isinstance(releases, dict)
    release_rows = releases["releases"]
    assert isinstance(release_rows, list)
    first_release = release_rows[0]
    assert isinstance(first_release, dict)
    first_release["record_ids"] = ["rec_" + "0" * 48]
    release_drift = dict(fixture.contents)
    release_drift["CORPUS_RELEASES"] = canonicalize(releases)

    coverage = parse_json_bytes(fixture.contents["COVERAGE_STATUS"], max_bytes=1_000_000)
    assert isinstance(coverage, dict)
    scopes = coverage["scopes"]
    assert isinstance(scopes, list)
    first_scope = scopes[0]
    assert isinstance(first_scope, dict)
    first_scope["gap_refs"] = ["gap_" + "0" * 48]
    coverage_drift = dict(fixture.contents)
    coverage_drift["COVERAGE_STATUS"] = canonicalize(coverage)

    with pytest.raises(ProposalMemberViolation, match="release inventory binding"):
        validate_v1_proposal_members(release_drift, fixture.bindings, fixture.traceability_shards)
    with pytest.raises(ProposalMemberViolation, match="scope evidence"):
        validate_v1_proposal_members(coverage_drift, fixture.bindings, fixture.traceability_shards)


def test_executable_manifest_requires_exact_root_identity_and_base() -> None:
    """Re-hashing a changed executable manifest cannot alter the frozen root facts."""
    fixture = semantic_proposal_fixture()
    changed_manifest = _changed(
        fixture.contents["PROMOTION_MANIFEST"],
        "base_serving_state_id",
        "srv_" + "0" * 48,
    )
    changed_fingerprint = f"sha256:{sha256(changed_manifest).hexdigest()}"
    changed_id = "pmn_" + sha256(changed_fingerprint.encode()).hexdigest()[:48]
    contents = dict(fixture.contents)
    contents["PROMOTION_MANIFEST"] = changed_manifest
    bindings = replace(
        fixture.bindings,
        promotion_manifest_id=changed_id,
        promotion_manifest_fingerprint=changed_fingerprint,
    )

    with pytest.raises(ProposalMemberViolation, match="base state"):
        validate_v1_proposal_members(contents, bindings, fixture.traceability_shards)


@pytest.mark.parametrize(
    "drift",
    ["EFFECT_BINDING", "INPUT_BINDING", "STOP_CONDITION", "EXTRA_FIELD"],
)
def test_executable_manifest_rejects_incomplete_action_authority(drift: str) -> None:
    """Re-hashing cannot legitimize runtime-invented effect authority."""
    fixture = semantic_proposal_fixture()
    document = parse_json_bytes(fixture.contents["PROMOTION_MANIFEST"], max_bytes=1_000_000)
    assert isinstance(document, dict)
    actions = document["actions"]
    assert isinstance(actions, list)
    action = actions[0]
    assert isinstance(action, dict)
    if drift == "EFFECT_BINDING":
        action["required_capability"] = "MANAGE_BACKUP"
    elif drift == "INPUT_BINDING":
        inputs = action["input_refs"]
        assert isinstance(inputs, list)
        action["input_refs"] = inputs[:1]
    elif drift == "STOP_CONDITION":
        stops = action["stop_conditions"]
        assert isinstance(stops, list)
        action["stop_conditions"] = stops[:-1]
    else:
        action["runtime_override"] = True
    changed_manifest = canonicalize(document)
    changed_fingerprint = f"sha256:{sha256(changed_manifest).hexdigest()}"
    changed_id = "pmn_" + sha256(changed_fingerprint.encode()).hexdigest()[:48]
    contents = dict(fixture.contents)
    contents["PROMOTION_MANIFEST"] = changed_manifest
    bindings = replace(
        fixture.bindings,
        promotion_manifest_id=changed_id,
        promotion_manifest_fingerprint=changed_fingerprint,
    )

    with pytest.raises(ProposalMemberViolation, match="PROMOTION_MANIFEST"):
        validate_v1_proposal_members(contents, bindings, fixture.traceability_shards)
