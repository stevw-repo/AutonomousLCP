"""Fail-closed tests for the not-yet-admitted HKeL authenticity boundary."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from types import SimpleNamespace

import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_evidence_vault import ExactObjectReference, VaultName
from asklegal_legal_desks import hk_legislation_authentic as authentic_module
from asklegal_legal_desks.hk_legislation_authentic import (
    HkelAuthenticAdmissionReceipt,
    HKLegislationEvidenceEnvelope,
    HKLegislationEvidenceError,
    admit_retained_hkel_observation,
    load_authentic_legislation_bundle,
)

_CYCLE_ID = "hk-v1-daily-20260826"
_CUTOFF = "2026-08-26T00:00:00Z"
_INSTRUMENT_ID = "hk-cap-001"
_SOURCE_ID = "HK-LEG-HKEL-CURRENT-INVENTORY"


class _Reader:
    def __init__(self, values: dict[ExactObjectReference, bytes]) -> None:
        self._values = values
        self.calls: list[ExactObjectReference] = []

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        self.calls.append(reference)
        return self._values[reference]

    def raw(self, reference: ExactObjectReference) -> bytes:
        return self._values[reference]

    def rebind(
        self,
        prior: ExactObjectReference,
        successor: ExactObjectReference,
        raw: bytes,
    ) -> None:
        self._values.pop(prior)
        self._values[successor] = raw


class _AdmissionReader:
    """Typed inert reader for tests that replace both retained parsers."""

    def open_exact(self, reference: object) -> BytesIO:
        del reference
        return BytesIO()


class _FailingReader:
    def read_exact(self, reference: ExactObjectReference) -> bytes:
        del reference
        message = "raw reader failure must not escape"
        raise RuntimeError(message)


class _BaseExceptionReader:
    def read_exact(self, reference: ExactObjectReference) -> bytes:
        del reference
        raise KeyboardInterrupt


class _ReferenceMutatingReader:
    def __init__(self, raw: bytes, *, relabel_only: bool = False) -> None:
        self._raw = raw
        self._relabel_only = relabel_only
        self.calls: list[ExactObjectReference] = []

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        self.calls.append(reference)
        object.__setattr__(reference, "logical_key", "unrelated/reader/relabel")
        if not self._relabel_only:
            object.__setattr__(reference, "fingerprint", "sha256:" + sha256(self._raw).hexdigest())
            object.__setattr__(reference, "byte_length", len(self._raw))
        return self._raw


def _canonical(value: JsonValue) -> bytes:
    return canonicalize(checked_json_value(value))


def _reference(logical_key: str, raw: bytes, version: str) -> ExactObjectReference:
    return ExactObjectReference(
        VaultName.PRIMARY,
        logical_key,
        "v" + version * 64,
        "sha256:" + sha256(raw).hexdigest(),
        len(raw),
    )


def _cycle_manifest_key(cycle_id: str) -> str:
    raw = cycle_id.encode()
    return "/".join(
        (
            "hk-v1",
            "due-cycles",
            "cycle",
            "sha256-" + sha256(raw).hexdigest(),
            "hex-" + raw.hex(),
            "manifest.json",
        )
    )


def _current_candidate() -> tuple[HKLegislationEvidenceEnvelope, _Reader]:
    member_raw = b"source-neutral member"
    member = _reference("poc/source/hkel/hk-cap-001/en.xml", member_raw, "4")
    plan_inputs: dict[str, JsonValue] = {
        "authentic_source_admitted": False,
        "instrument_id": _INSTRUMENT_ID,
        "inventory_fingerprint": "sha256:" + "1" * 64,
        "members": [
            {
                "archive_member": None,
                "artifact_id": "hkel-en-xml",
                "declared_sha256": None,
                "endpoint_id": "hkel-current-en",
                "endpoint_version": "1.0.0",
                "inventory_member_fingerprint": "sha256:" + "2" * 64,
                "instrument_id": _INSTRUMENT_ID,
                "language": "EN",
                "locator": "fixture://hkel/en.xml",
                "resource_id": "hkel-en-xml",
                "role": "ENGLISH_XML",
                "source_id": _SOURCE_ID,
                "source_disposition": "SOURCE_NEUTRAL_TEST_FIXTURE",
                "status_signal": "CURRENT",
                "version_signal": "2026-08-26",
            }
        ],
        "missing_member_ids": [],
        "observation_cutoff": _CUTOFF,
        "projection_fingerprint": "sha256:" + "3" * 64,
        "source_register_fingerprint": "sha256:" + "5" * 64,
        "source_register_id": "hsr_" + "6" * 48,
    }
    plan_fingerprint = "sha256:" + sha256(_canonical(plan_inputs)).hexdigest()
    plan_document: dict[str, JsonValue] = {
        **plan_inputs,
        "parser_profile": "SYNTHETIC_COMPLETE_INVENTORY",
        "plan_fingerprint": plan_fingerprint,
        "schema_id": "asklegal.hkel-evidence-plan",
        "schema_version": "1.0.0",
    }
    plan_raw = _canonical(plan_document)
    plan = _reference(
        "poc/report/hkel-evidence-plan/"
        + _INSTRUMENT_ID
        + "/"
        + plan_fingerprint.removeprefix("sha256:"),
        plan_raw,
        "1",
    )
    attempt_raw = _canonical(
        {
            "complete": True,
            "instrument_id": _INSTRUMENT_ID,
            "members": [
                {
                    "code": "CAPTURED",
                    "evidence": {
                        "byte_length": member.byte_length,
                        "fingerprint": member.fingerprint,
                        "logical_key": member.logical_key,
                        "vault": member.vault.value,
                        "version_id": member.version_id,
                    },
                    "role": "ENGLISH_XML",
                }
            ],
            "observation_cutoff": _CUTOFF,
            "plan_fingerprint": plan_fingerprint,
            "release_blocking": False,
            "schema_id": "asklegal.hkel-evidence-attempt",
            "schema_version": "1.0.0",
            "source_inventory_fingerprint": "sha256:" + "1" * 64,
            "source_register_fingerprint": "sha256:" + "5" * 64,
        }
    )
    attempt = _reference(
        "poc/report/hkel-evidence-attempt/"
        + _INSTRUMENT_ID
        + "/"
        + sha256(attempt_raw).hexdigest(),
        attempt_raw,
        "2",
    )
    cycle_raw = _canonical(
        {
            "accounting_complete": True,
            "cycle_id": _CYCLE_ID,
            "cycle_kind": "DAILY_CURRENT_LAW",
            "observation_cutoff": _CUTOFF,
            "release_blocking": False,
            "schema_id": "asklegal.hk-v1-due-cycle-report",
            "schema_version": "1.0.0",
        }
    )
    cycle = _reference(_cycle_manifest_key(_CYCLE_ID), cycle_raw, "3")
    envelope = HKLegislationEvidenceEnvelope(
        schema_id="asklegal.hk-legislation-authentic-envelope",
        schema_version="1.0.0",
        cycle_id=_CYCLE_ID,
        cycle_kind="DAILY_CURRENT_LAW",
        source_id=_SOURCE_ID,
        instrument_id=_INSTRUMENT_ID,
        observation_cutoff=_CUTOFF,
        source_cycle_manifest_reference=cycle,
        plan_manifest_reference=plan,
        terminal_attempt_reference=attempt,
        admission_result_reference=None,
        member_references=(member,),
    )
    return envelope, _Reader(
        {
            plan: plan_raw,
            attempt: attempt_raw,
            cycle: cycle_raw,
            member: member_raw,
        }
    )


def test_retained_admission_runs_full_index_and_structure_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authentic admission composes the hostile ZIP/body and XML structure readers."""
    archive_endpoints = tuple(
        SimpleNamespace(
            endpoint_id=f"sep_{index:048x}",
            media_type="application/zip",
            reference=SimpleNamespace(fingerprint="sha256:" + f"{index:x}" * 64),
        )
        for index in range(1, 13)
    )
    index = SimpleNamespace(
        attempt_id="retained-attempt",
        observation_cutoff="2026-08-28T22:20:23+08:00",
        report_fingerprint="sha256:" + "1" * 64,
        source_observation_fingerprint="sha256:" + "2" * 64,
        publication_profile_fingerprint="sha256:" + "3" * 64,
        endpoint_objects=(*archive_endpoints, *(object() for _ in range(44))),
        archive_members=tuple(object() for _ in range(12_858)),
        bilingual_xml_pairs=tuple(object() for _ in range(3_157)),
        publication_specifications=tuple(object() for _ in range(7)),
    )
    structure = SimpleNamespace(
        profile_fingerprint="sha256:" + "4" * 64,
        bilingual_records=tuple(object() for _ in range(3_157)),
        issue_counts=(SimpleNamespace(issue_code=SimpleNamespace(value="ROOT_LANGUAGE"), count=2),),
        review_required_pair_count=2,
        admission_authority="NONE",
    )
    calls: list[str] = []

    def indexer(reference: object, reader: object) -> object:
        del reference, reader
        calls.append("index")
        return index

    def profiler(value: object, reader: object) -> object:
        del reader
        assert value is index
        calls.append("profile")
        return structure

    monkeypatch.setattr(authentic_module, "index_retained_hkel_observation", indexer)
    monkeypatch.setattr(authentic_module, "profile_retained_hkel_structure", profiler)

    receipt = admit_retained_hkel_observation(object(), _AdmissionReader())

    assert calls == ["index", "profile"]
    assert receipt.archive_member_count == 12_858
    assert receipt.bilingual_pair_count == 3_157
    assert receipt.publication_specification_count == 7
    assert len(receipt.archive_reuse_keys) == 12
    assert receipt.review_issue_refs == ("hkel-structure/ROOT_LANGUAGE/2",)
    assert HkelAuthenticAdmissionReceipt.from_json(receipt.to_json()) == receipt


def test_retained_admission_rejects_incomplete_structural_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A structural parse that did not cover every pair cannot be called admitted."""
    index = SimpleNamespace(
        attempt_id="retained-attempt",
        observation_cutoff="2026-08-28T22:20:23+08:00",
        report_fingerprint="sha256:" + "1" * 64,
        source_observation_fingerprint="sha256:" + "2" * 64,
        publication_profile_fingerprint="sha256:" + "3" * 64,
        endpoint_objects=tuple(object() for _ in range(56)),
        archive_members=tuple(object() for _ in range(12_858)),
        bilingual_xml_pairs=tuple(object() for _ in range(3_157)),
        publication_specifications=tuple(object() for _ in range(7)),
    )
    structure = SimpleNamespace(
        profile_fingerprint="sha256:" + "4" * 64,
        bilingual_records=(),
        issue_counts=(),
        review_required_pair_count=0,
        admission_authority="NONE",
    )

    def indexer(_reference: object, _reader: object) -> object:
        return index

    def profiler(_index: object, _reader: object) -> object:
        return structure

    monkeypatch.setattr(authentic_module, "index_retained_hkel_observation", indexer)
    monkeypatch.setattr(authentic_module, "profile_retained_hkel_structure", profiler)

    with pytest.raises(HKLegislationEvidenceError, match="RETAINED_ADMISSION_INVALID"):
        admit_retained_hkel_observation(object(), _AdmissionReader())


def test_current_candidate_hkel_attempt_cannot_be_loaded_as_authentic() -> None:
    """Terminal completeness cannot upgrade a source-neutral plan to authentic."""
    envelope, reader = _current_candidate()

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(envelope, reader)

    assert caught.value.code == "AUTHENTIC_SOURCE_NOT_ADMITTED"
    assert reader.calls == [envelope.plan_manifest_reference]


def test_missing_plan_reference_is_closed_before_any_read() -> None:
    envelope, reader = _current_candidate()

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(replace(envelope, plan_manifest_reference=None), reader)

    assert caught.value.code == "HK_LEGISLATION_PLAN_REFERENCE_REQUIRED"
    assert reader.calls == []


@pytest.mark.parametrize(
    "logical_key",
    [
        "unrelated/plan.json",
        "poc/report/hkel-evidence-plan/other-instrument/" + "a" * 64,
        "poc/report/hkel-evidence-plan/hk-cap-001/not-a-fingerprint",
    ],
)
def test_unrelated_plan_reference_is_rejected_before_reader_call(logical_key: str) -> None:
    envelope, reader = _current_candidate()
    prior = envelope.plan_manifest_reference
    assert prior is not None
    unrelated = replace(prior, logical_key=logical_key)
    reader.rebind(prior, unrelated, reader.raw(prior))

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(
            replace(envelope, plan_manifest_reference=unrelated), reader
        )

    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_REFERENCE_INVALID"
    assert reader.calls == []


def test_non_primary_plan_reference_is_rejected_before_reader_call() -> None:
    envelope, reader = _current_candidate()
    prior = envelope.plan_manifest_reference
    assert prior is not None
    recovery = replace(prior, vault=VaultName.RECOVERY)
    reader.rebind(prior, recovery, reader.raw(prior))

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(
            replace(envelope, plan_manifest_reference=recovery), reader
        )

    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_REFERENCE_INVALID"
    assert reader.calls == []


def test_impossible_utc_cutoff_is_rejected_before_reader_call() -> None:
    envelope, reader = _current_candidate()

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(
            replace(envelope, observation_cutoff="2026-99-99T99:99:99Z"), reader
        )

    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_ENVELOPE_INVALID"
    assert reader.calls == []


def test_cycle_id_must_match_the_exact_cycle_manifest_reference_before_read() -> None:
    envelope, reader = _current_candidate()

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(
            replace(envelope, cycle_id="hk-v1-daily-20260827"), reader
        )

    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_REFERENCE_INVALID"
    assert reader.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_id", "asklegal.hk-case-authentic-envelope"),
        ("schema_version", "2.0.0"),
        ("cycle_id", "bad/cycle"),
        ("cycle_kind", "WEEKLY_RELEASE"),
        ("source_id", "HK-LEG-GLD-EGAZETTE"),
        ("observation_cutoff", "2026-08-26"),
    ],
)
def test_wrong_schema_cycle_source_or_cutoff_is_closed_before_read(field: str, value: str) -> None:
    envelope, reader = _current_candidate()

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(replace(envelope, **{field: value}), reader)

    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_ENVELOPE_INVALID"
    assert reader.calls == []


def test_equality_liar_and_frozen_envelope_mutation_do_not_relabel_provenance() -> None:
    class EqualityLiar(str):
        __slots__ = ()
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            return True

    envelope, reader = _current_candidate()
    object.__setattr__(envelope, "schema_id", EqualityLiar(envelope.schema_id))

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(envelope, reader)

    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_ENVELOPE_INVALID"
    assert reader.calls == []


def test_loose_json_and_deleted_envelope_leaf_fail_with_the_closed_code() -> None:
    envelope, reader = _current_candidate()
    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle({"schema_id": envelope.schema_id}, reader)
    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_ENVELOPE_INVALID"
    assert reader.calls == []

    object.__delattr__(envelope, "source_id")
    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(envelope, reader)
    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_ENVELOPE_INVALID"
    assert reader.calls == []


def test_mutated_or_copied_references_cannot_change_bound_identity() -> None:
    envelope, reader = _current_candidate()
    plan_reference = envelope.plan_manifest_reference
    assert plan_reference is not None
    object.__setattr__(plan_reference, "byte_length", -1)

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(envelope, reader)

    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_REFERENCE_INVALID"
    assert reader.calls == []

    envelope, reader = _current_candidate()
    copied_attempt = replace(
        envelope.terminal_attempt_reference,
        logical_key="poc/report/hkel-evidence-attempt/copied/"
        + envelope.terminal_attempt_reference.fingerprint.removeprefix("sha256:"),
    )
    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(
            replace(envelope, terminal_attempt_reference=copied_attempt), reader
        )

    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_REFERENCE_INVALID"
    assert reader.calls == []


def test_wrong_plan_cutoff_is_a_closed_provenance_mismatch() -> None:
    envelope, reader = _current_candidate()
    changed = replace(envelope, observation_cutoff="2026-08-27T00:00:00Z")

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(changed, reader)

    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_PROVENANCE_MISMATCH"
    assert reader.calls == [envelope.plan_manifest_reference]


def test_reader_failure_never_leaks_a_raw_error_or_reads_later_references() -> None:
    envelope, _reader = _current_candidate()

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(envelope, _FailingReader())

    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_READ_FAILED"


def test_reader_cannot_reseal_malicious_bytes_by_mutating_disposable_reference() -> None:
    envelope, _reader = _current_candidate()
    reader = _ReferenceMutatingReader(b"{}")

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(envelope, reader)

    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_READ_FAILED"
    assert len(reader.calls) == 1


def test_reader_reference_relabel_cannot_change_terminal_admission_code() -> None:
    envelope, original = _current_candidate()
    plan_reference = envelope.plan_manifest_reference
    assert plan_reference is not None
    reader = _ReferenceMutatingReader(original.raw(plan_reference), relabel_only=True)

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(envelope, reader)

    assert caught.value.code == "AUTHENTIC_SOURCE_NOT_ADMITTED"
    assert plan_reference.logical_key.startswith("poc/report/hkel-evidence-plan/hk-cap-001/")


def test_reader_base_exception_remains_observable() -> None:
    envelope, _reader = _current_candidate()

    with pytest.raises(KeyboardInterrupt):
        load_authentic_legislation_bundle(envelope, _BaseExceptionReader())


def test_duplicate_json_is_not_a_loose_plan_copy() -> None:
    envelope, reader = _current_candidate()
    prior = envelope.plan_manifest_reference
    assert prior is not None
    raw = b'{"schema_id":"asklegal.hkel-evidence-plan",' + reader.raw(prior)[1:]
    copied = _reference(prior.logical_key, raw, "7")
    reader.rebind(prior, copied, raw)

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(replace(envelope, plan_manifest_reference=copied), reader)

    assert caught.value.code == "HK_LEGISLATION_EVIDENCE_PLAN_INVALID"
    assert reader.calls == [copied]


def test_direct_synthetic_true_candidate_still_has_no_authentic_path() -> None:
    envelope, reader = _current_candidate()
    prior = envelope.plan_manifest_reference
    assert prior is not None
    document = parse_json_bytes(reader.raw(prior), max_bytes=prior.byte_length)
    assert type(document) is dict
    document["authentic_source_admitted"] = True
    fingerprint_fields = (
        "authentic_source_admitted",
        "instrument_id",
        "inventory_fingerprint",
        "members",
        "missing_member_ids",
        "observation_cutoff",
        "projection_fingerprint",
        "source_register_fingerprint",
        "source_register_id",
    )
    fingerprint_body: dict[str, JsonValue] = {
        field: document[field] for field in fingerprint_fields
    }
    plan_fingerprint = "sha256:" + sha256(_canonical(fingerprint_body)).hexdigest()
    document["plan_fingerprint"] = plan_fingerprint
    raw = _canonical(document)
    forged = _reference(
        f"poc/report/hkel-evidence-plan/{_INSTRUMENT_ID}/"
        f"{plan_fingerprint.removeprefix('sha256:')}",
        raw,
        "8",
    )
    reader.rebind(prior, forged, raw)

    with pytest.raises(HKLegislationEvidenceError) as caught:
        load_authentic_legislation_bundle(replace(envelope, plan_manifest_reference=forged), reader)

    assert caught.value.code == "AUTHENTIC_SOURCE_NOT_ADMITTED"
    assert reader.calls == [forged]
