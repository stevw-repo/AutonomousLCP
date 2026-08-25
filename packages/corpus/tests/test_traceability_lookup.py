"""Exact ADR 0078 Record Traceability Lookup construction proofs."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import SchemaRegistry, parse_json_bytes
from asklegal_corpus import (
    AuthorityNoteEvidence,
    CorpusError,
    CorpusErrorCode,
    CorpusReleaseInput,
    DesiredStateInventory,
    FlattenedRecord,
    RecordTraceabilityLookupInput,
    ServingRecord,
    ServingRecordProfile,
    TraceabilityEntry,
    TraceabilityReference,
    TraceabilityScopeShardInput,
    compose_desired_state,
    freeze_corpus_release,
    freeze_record_traceability_lookup,
)

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts"
NOW = "2026-08-24T00:00:00Z"


def _fp(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _scope(digit: str) -> str:
    return "rsc_" + digit * 48


def _record(digit: str, scope_id: str, *, note: str = "None") -> ServingRecord:
    return ServingRecord(
        "rec_" + digit * 48,
        f"Exact bilingual synthetic text for {scope_id}.",
        "Hong Kong",
        "Hong Kong",
        "Legislation",
        "HKeL",
        note,
        "art_" + digit * 48,
        ("evi_" + digit * 48,),
    )


def _desired(*records: tuple[str, ServingRecord]) -> DesiredStateInventory:
    releases = tuple(
        freeze_corpus_release(
            CorpusReleaseInput(
                scope_id,
                NOW,
                ("evi_" + record.record_id[-48:],),
                ("val_" + record.record_id[-48:],),
            ),
            (record,),
        )
        for scope_id, record in records
    )
    return compose_desired_state(
        tuple(scope_id for scope_id, _ in records),
        releases,
        target_key="hk-v1-local",
        observation_cutoff=NOW,
    )


def _reference(ref_type: str, prefix: str, digit: str) -> TraceabilityReference:
    return TraceabilityReference(
        ref_type,
        prefix + "_" + digit * 48,
        "sha256:" + digit * 64,
    )


def _entry(
    flattened: FlattenedRecord,
    digit: str,
    *,
    profile: str = "hk-legislation-1",
) -> TraceabilityEntry:
    decision = _reference("DECISION", "dec", digit)
    evidence = _reference("EVIDENCE", "evi", digit)
    return TraceabilityEntry(
        flattened.record_id,
        flattened.content_fingerprint,
        profile,
        "lit_" + digit * 48,
        ("ofv_" + digit * 48,),
        ("loc_" + digit * 48,),
        flattened.scope_id,
        flattened.release_id,
        (evidence,),
        AuthorityNoteEvidence(
            _fp(flattened.record.authority_note.encode()),
            decision,
            () if flattened.record.authority_note == "None" else (evidence,),
        ),
    )


def _profile(identifier: str = "hk-legislation-1") -> ServingRecordProfile:
    return ServingRecordProfile(identifier, "1.0.0", "sha256:" + "a" * 64)


def _inputs() -> RecordTraceabilityLookupInput:
    return RecordTraceabilityLookupInput(
        "rtl_" + "a" * 48,
        "sha256:" + "b" * 64,
        "sha256:" + "c" * 64,
    )


def _shards(desired: DesiredStateInventory) -> tuple[TraceabilityScopeShardInput, ...]:
    return tuple(
        TraceabilityScopeShardInput(scope_id, release_id, "rts_" + digit * 48)
        for digit, (scope_id, release_id) in zip(
            ("d", "e", "f"),
            desired.scope_releases,
            strict=False,
        )
    )


def test_lookup_is_complete_schema_valid_and_byte_reproducible() -> None:
    desired = _desired(
        (_scope("1"), _record("1", _scope("1"))),
        (_scope("2"), _record("2", _scope("2"), note="[WARNING: SYNTHETIC]")),
    )
    entries = tuple(
        _entry(flattened, digit)
        for flattened, digit in zip(desired.records, ("1", "2"), strict=True)
    )
    lookup = freeze_record_traceability_lookup(
        _inputs(),
        desired,
        tuple(reversed(entries)),
        (_profile(),),
        tuple(reversed(_shards(desired))),
    )
    repeated = freeze_record_traceability_lookup(
        _inputs(), desired, entries, (_profile(),), _shards(desired)
    )

    assert lookup == repeated
    assert lookup.total_entry_count == 2
    assert tuple(shard.release_scope_id for shard in lookup.shards) == tuple(
        scope_id for scope_id, _ in desired.scope_releases
    )
    registry = SchemaRegistry.from_contracts_root(CONTRACTS)
    manifest = parse_json_bytes(lookup.manifest_bytes, max_bytes=len(lookup.manifest_bytes))
    registry.validate(
        manifest, "schemas/serving-domain.schema.json#/$defs/traceability_lookup_manifest"
    )
    for shard in lookup.shards:
        assert shard.content.endswith(b"\n")
        for line in shard.content.splitlines():
            entry = parse_json_bytes(line, max_bytes=len(line))
            registry.validate(entry, "schemas/serving-domain.schema.json#/$defs/traceability_entry")


def test_lookup_declares_an_exact_zero_byte_shard_for_an_empty_scope() -> None:
    full_scope = _scope("1")
    empty_scope = _scope("2")
    release = freeze_corpus_release(
        CorpusReleaseInput(full_scope, NOW, ("evi_" + "1" * 48,), ("val_" + "1" * 48,)),
        (_record("1", full_scope),),
    )
    empty_release = freeze_corpus_release(
        CorpusReleaseInput(
            empty_scope,
            NOW,
            ("evi_" + "2" * 48,),
            ("val_" + "2" * 48,),
            zero_record_justification_refs=("dec_" + "2" * 48,),
        ),
        (),
    )
    desired = compose_desired_state(
        (full_scope, empty_scope),
        (release, empty_release),
        target_key="hk-v1-local",
        observation_cutoff=NOW,
    )
    lookup = freeze_record_traceability_lookup(
        _inputs(), desired, (_entry(desired.records[0], "1"),), (_profile(),), _shards(desired)
    )

    empty = next(shard for shard in lookup.shards if shard.release_scope_id == empty_scope)
    assert empty.content == b""
    assert empty.entry_count == 0
    assert empty.fingerprint == _fp(b"")


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "orphan"])
def test_lookup_rejects_missing_duplicate_or_orphan_entries(mutation: str) -> None:
    desired = _desired((_scope("1"), _record("1", _scope("1"))))
    entry = _entry(desired.records[0], "1")
    if mutation == "missing":
        entries = ()
    elif mutation == "duplicate":
        entries = (entry, entry)
    else:
        entries = (replace(entry, search_record_id="rec_" + "2" * 48),)

    with pytest.raises(CorpusError) as caught:
        freeze_record_traceability_lookup(
            _inputs(), desired, entries, (_profile(),), _shards(desired)
        )
    assert caught.value.code is CorpusErrorCode.TRACEABILITY_INCOMPLETE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("serving_payload_fingerprint", "sha256:" + "f" * 64),
        ("release_scope_id", _scope("2")),
        ("corpus_release_id", "rel_" + "f" * 48),
    ],
)
def test_lookup_rejects_desired_state_binding_drift(field: str, value: str) -> None:
    desired = _desired((_scope("1"), _record("1", _scope("1"))))
    entry = replace(_entry(desired.records[0], "1"), **{field: value})
    with pytest.raises(CorpusError, match="entry desired-state binding"):
        freeze_record_traceability_lookup(
            _inputs(), desired, (entry,), (_profile(),), _shards(desired)
        )


def test_lookup_rejects_authority_note_fingerprint_drift() -> None:
    desired = _desired((_scope("1"), _record("1", _scope("1"))))
    entry = _entry(desired.records[0], "1")
    bad_authority = replace(
        entry.authority_note_evidence,
        rendered_value_fingerprint="sha256:" + "f" * 64,
    )
    with pytest.raises(CorpusError, match="authority-note fingerprint"):
        freeze_record_traceability_lookup(
            _inputs(),
            desired,
            (replace(entry, authority_note_evidence=bad_authority),),
            (_profile(),),
            _shards(desired),
        )


def test_lookup_rejects_unsorted_identity_and_reference_arrays() -> None:
    desired = _desired((_scope("1"), _record("1", _scope("1"))))
    entry = _entry(desired.records[0], "1")
    unsorted_versions = ("ofv_" + "2" * 48, "ofv_" + "1" * 48)
    with pytest.raises(CorpusError, match="official versions"):
        freeze_record_traceability_lookup(
            _inputs(),
            desired,
            (replace(entry, official_version_ids=unsorted_versions),),
            (_profile(),),
            _shards(desired),
        )
    unsorted_refs = (
        _reference("EVIDENCE", "evi", "2"),
        _reference("EVIDENCE", "evi", "1"),
    )
    with pytest.raises(CorpusError, match="evidence references"):
        freeze_record_traceability_lookup(
            _inputs(),
            desired,
            (replace(entry, evidence_refs=unsorted_refs),),
            (_profile(),),
            _shards(desired),
        )


def test_lookup_rejects_missing_or_unused_serving_profiles() -> None:
    desired = _desired((_scope("1"), _record("1", _scope("1"))))
    entry = _entry(desired.records[0], "1")
    with pytest.raises(CorpusError, match="entry identity"):
        freeze_record_traceability_lookup(_inputs(), desired, (entry,), (), _shards(desired))
    with pytest.raises(CorpusError, match="unused or missing serving profile"):
        freeze_record_traceability_lookup(
            _inputs(), desired, (entry,), (_profile(), _profile("unused-profile")), _shards(desired)
        )


def test_lookup_rejects_missing_or_mismatched_scope_shards() -> None:
    desired = _desired((_scope("1"), _record("1", _scope("1"))))
    entry = _entry(desired.records[0], "1")
    with pytest.raises(CorpusError, match="shard scope inventory"):
        freeze_record_traceability_lookup(_inputs(), desired, (entry,), (_profile(),), ())
    bad = replace(_shards(desired)[0], corpus_release_id="rel_" + "f" * 48)
    with pytest.raises(CorpusError, match="shard identity"):
        freeze_record_traceability_lookup(_inputs(), desired, (entry,), (_profile(),), (bad,))
