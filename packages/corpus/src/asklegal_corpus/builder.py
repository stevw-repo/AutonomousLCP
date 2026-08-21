"""Deterministic M6 release, desired-state, coverage, and proposal builders."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from hashlib import sha256

from asklegal_contracts import ContractViolation, canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value

from .model import (
    CorpusError,
    CorpusErrorCode,
    CorpusRelease,
    CorpusReleaseInput,
    CoverageScopeStatus,
    CoverageState,
    CoverageStatusManifest,
    CoverageWarning,
    DesiredStateInventory,
    FlattenedRecord,
    ProposalArtifact,
    ProposalPackage,
    ProposalPackageInput,
    ReleaseRecordEntry,
    ServingRecord,
    SourceCoverageCycleBinding,
)

PROPOSAL_ROLE_PATHS: dict[str, str] = {
    "CHANGE_INVENTORY": "change-inventory/change-inventory.json",
    "CORPUS_RELEASES": "corpus-releases/releases.json",
    "COST_AND_CAPACITY": "cost-and-capacity/admission.json",
    "COVERAGE_STATUS": "coverage-status/coverage.json",
    "DESIRED_STATE_INVENTORIES": "desired-state-inventories/inventories.json",
    "PROMOTION_MANIFEST": "promotion-manifest/promotion-manifest.json",
    "RECORD_TRACEABILITY": "record-traceability/lookup.json",
    "RECOVERY_READINESS": "recovery-readiness/readiness.json",
    "REVIEW_REPORT": "review-report/report.json",
    "SERVING_STATE_DEFINITION": "serving-state-definition/definition.json",
    "VALIDATION": "validation/results.json",
}


def _fingerprint(raw: bytes) -> str:
    return f"sha256:{sha256(raw).hexdigest()}"


def _stable_id(prefix: str, *values: str) -> str:
    digest = sha256("\x1f".join(values).encode()).hexdigest()[:48]
    return f"{prefix}_{digest}"


def _canonical(value: object) -> bytes:
    return canonicalize(checked_json_value(value))


def _record_payload(record: ServingRecord) -> dict[str, object]:
    return {
        "authority_note": record.authority_note,
        "country": record.country,
        "jurisdiction": record.jurisdiction,
        "source": record.source,
        "text": record.text,
        "type": record.material_type,
    }


def serving_payload_fingerprint(record: ServingRecord) -> str:
    """Fingerprint exactly the six-field metadata payload, excluding identity."""
    if type(record) is not ServingRecord or any(
        not value
        for value in (
            record.record_id,
            record.text,
            record.country,
            record.jurisdiction,
            record.material_type,
            record.source,
            record.authority_note,
            record.artifact_ref,
        )
    ):
        raise CorpusError(CorpusErrorCode.FINGERPRINT_MISMATCH, "serving record")
    return _fingerprint(_canonical(_record_payload(record)))


def freeze_corpus_release(
    inputs: CorpusReleaseInput,
    records: Sequence[ServingRecord],
) -> CorpusRelease:
    """Seal one complete scope snapshot or reject incomplete empty accounting."""
    ordered = tuple(sorted(records, key=lambda item: item.record_id))
    ids = tuple(record.record_id for record in ordered)
    if len(ids) != len(set(ids)):
        raise CorpusError(CorpusErrorCode.DUPLICATE_RECORD)
    if not inputs.evidence_refs or not inputs.validation_refs:
        raise CorpusError(CorpusErrorCode.INVENTORY_MISMATCH, "release evidence")
    if not ordered and not inputs.zero_record_justification_refs and not inputs.withholding_refs:
        raise CorpusError(CorpusErrorCode.ZERO_RECORD_UNJUSTIFIED)
    entries = tuple(
        ReleaseRecordEntry(record, serving_payload_fingerprint(record)) for record in ordered
    )
    records_bytes = _canonical(
        [
            {
                "content_fingerprint": entry.serving_payload_fingerprint,
                "record_id": entry.record.record_id,
            }
            for entry in entries
        ]
    )
    records_fingerprint = _fingerprint(records_bytes)
    release_body = {
        "evidence_refs": list(inputs.evidence_refs),
        "observation_cutoff": inputs.observation_cutoff,
        "records_fingerprint": records_fingerprint,
        "scope_id": inputs.scope_id,
        "validation_refs": list(inputs.validation_refs),
        "withholding_refs": list(inputs.withholding_refs),
        "zero_record_justification_refs": list(inputs.zero_record_justification_refs),
    }
    release_fingerprint = _fingerprint(_canonical(release_body))
    return CorpusRelease(
        _stable_id("rel", inputs.scope_id, inputs.observation_cutoff, release_fingerprint),
        inputs.scope_id,
        inputs.observation_cutoff,
        entries,
        inputs.evidence_refs,
        inputs.validation_refs,
        inputs.withholding_refs,
        inputs.zero_record_justification_refs,
        records_fingerprint,
        release_fingerprint,
    )


def compose_desired_state(
    required_scope_ids: tuple[str, ...],
    releases: Sequence[CorpusRelease],
    *,
    target_key: str,
    observation_cutoff: str,
) -> DesiredStateInventory:
    """Compose one exact release per required non-overlapping scope."""
    if len(required_scope_ids) != len(set(required_scope_ids)):
        raise CorpusError(CorpusErrorCode.RELEASE_SCOPE_MISMATCH, "duplicate required scope")
    by_scope = {release.scope_id: release for release in releases}
    if len(by_scope) != len(releases) or set(by_scope) != set(required_scope_ids):
        raise CorpusError(CorpusErrorCode.RELEASE_SCOPE_MISMATCH)
    flattened = tuple(
        sorted(
            (
                FlattenedRecord(
                    entry.record.record_id,
                    entry.serving_payload_fingerprint,
                    scope_id,
                    by_scope[scope_id].release_id,
                    entry.record,
                )
                for scope_id in sorted(required_scope_ids)
                for entry in by_scope[scope_id].records
            ),
            key=lambda item: item.record_id,
        )
    )
    record_ids = tuple(item.record_id for item in flattened)
    if len(record_ids) != len(set(record_ids)):
        raise CorpusError(CorpusErrorCode.DUPLICATE_RECORD)
    records_fingerprint = _fingerprint(
        _canonical(
            [
                {
                    "content_fingerprint": item.content_fingerprint,
                    "record_id": item.record_id,
                    "release_id": item.release_id,
                    "scope_id": item.scope_id,
                }
                for item in flattened
            ]
        )
    )
    selections = tuple((scope_id, by_scope[scope_id].release_id) for scope_id in sorted(by_scope))
    inventory_fingerprint = _fingerprint(
        _canonical(
            {
                "observation_cutoff": observation_cutoff,
                "records_fingerprint": records_fingerprint,
                "scope_releases": [list(item) for item in selections],
                "target_key": target_key,
            }
        )
    )
    return DesiredStateInventory(
        _stable_id("dsi", target_key, observation_cutoff, inventory_fingerprint),
        target_key,
        observation_cutoff,
        selections,
        flattened,
        records_fingerprint,
        inventory_fingerprint,
    )


_WARNING_BY_STATE = {
    CoverageState.CURRENT: CoverageWarning.NONE,
    CoverageState.KNOWN_GAP: CoverageWarning.KNOWN_GAP,
    CoverageState.NOT_READY: CoverageWarning.NOT_READY,
    CoverageState.WITHHELD: CoverageWarning.WITHHELD,
}


def freeze_coverage_status(
    serving_state_id: str,
    observation_cutoff: str,
    expected_scope_ids: tuple[str, ...],
    statuses: Sequence[CoverageScopeStatus],
    *,
    source_cycle: SourceCoverageCycleBinding | None = None,
) -> CoverageStatusManifest:
    """Freeze complete fail-visible coverage for every required scope."""
    ordered = tuple(sorted(statuses, key=lambda item: item.scope_id))
    if tuple(item.scope_id for item in ordered) != tuple(sorted(expected_scope_ids)):
        raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE)
    for item in ordered:
        evidence_count = (
            len(item.gap_refs) + len(item.quarantine_refs) + len(item.source_failure_refs)
        )
        if (
            item.warning is not _WARNING_BY_STATE[item.status]
            or (item.status is CoverageState.CURRENT and evidence_count != 0)
            or (item.status is not CoverageState.CURRENT and evidence_count == 0)
        ):
            raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, item.scope_id)
    if source_cycle is not None:
        _validate_source_cycle_binding(source_cycle, observation_cutoff)
    body: dict[str, object] = {
        "observation_cutoff": observation_cutoff,
        "scopes": [
            {
                "gap_refs": list(item.gap_refs),
                "last_verified_at": item.last_verified_at,
                "quarantine_refs": list(item.quarantine_refs),
                "scope_id": item.scope_id,
                "source_failure_refs": list(item.source_failure_refs),
                "status": item.status.value,
                "warning": item.warning.value,
            }
            for item in ordered
        ],
        "serving_state_id": serving_state_id,
    }
    if source_cycle is not None:
        body["source_cycle"] = _source_cycle_body(source_cycle)
    content = _canonical(body)
    fingerprint = _fingerprint(content)
    return CoverageStatusManifest(
        _stable_id("csm", serving_state_id, fingerprint),
        serving_state_id,
        observation_cutoff,
        ordered,
        source_cycle,
        content,
        fingerprint,
    )


def freeze_v1_coverage_status(
    serving_state_id: str,
    observation_cutoff: str,
    expected_scope_ids: tuple[str, ...],
    statuses: Sequence[CoverageScopeStatus],
    source_cycle: SourceCoverageCycleBinding,
) -> CoverageStatusManifest:
    """Freeze V1 coverage while surfacing a blocking or incomplete source cycle."""
    _validate_source_cycle_binding(source_cycle, observation_cutoff)
    source_blocked = not source_cycle.accounting_complete or source_cycle.release_blocking
    normalized = tuple(statuses)
    if source_blocked:
        source_reference = _source_cycle_reference(source_cycle)
        normalized = tuple(
            CoverageScopeStatus(
                scope_id=status.scope_id,
                status=CoverageState.NOT_READY,
                last_verified_at=status.last_verified_at,
                gap_refs=status.gap_refs,
                quarantine_refs=status.quarantine_refs,
                source_failure_refs=tuple(sorted({*status.source_failure_refs, source_reference})),
                warning=CoverageWarning.NOT_READY,
            )
            for status in statuses
        )
    return freeze_coverage_status(
        serving_state_id,
        observation_cutoff,
        expected_scope_ids,
        normalized,
        source_cycle=source_cycle,
    )


def verify_v1_coverage_release_gate(manifest: CoverageStatusManifest) -> None:
    """Reject release activation without one complete nonblocking exact source cycle."""
    if type(manifest) is not CoverageStatusManifest or manifest.source_cycle is None:
        raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, "source cycle missing")
    _validate_source_cycle_binding(manifest.source_cycle, manifest.observation_cutoff)
    if not manifest.source_cycle.accounting_complete:
        raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, "source cycle accounting")
    if manifest.source_cycle.release_blocking:
        raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, "source cycle blocking")


def _validate_source_cycle_binding(
    source_cycle: SourceCoverageCycleBinding,
    observation_cutoff: str,
) -> None:
    if type(source_cycle) is not SourceCoverageCycleBinding:
        raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, "source cycle type")
    if (
        source_cycle.vault != "PRIMARY"
        or not source_cycle.logical_key.startswith("poc/report/source-coverage-cycle/")
        or not source_cycle.version_id
        or re.fullmatch(r"sha256:[0-9a-f]{64}", source_cycle.fingerprint) is None
        or source_cycle.byte_length < 1
        or source_cycle.observation_cutoff != observation_cutoff
        or type(source_cycle.accounting_complete) is not bool
        or type(source_cycle.release_blocking) is not bool
    ):
        raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, "source cycle identity")
    for values in (
        source_cycle.missing_source_ids,
        source_cycle.duplicate_source_ids,
        source_cycle.gap_source_ids,
    ):
        if (
            type(values) is not tuple
            or values != tuple(sorted(set(values)))
            or any(type(value) is not str or not value for value in values)
        ):
            raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, "source cycle sources")
    incomplete_ids = source_cycle.missing_source_ids + source_cycle.duplicate_source_ids
    if source_cycle.accounting_complete == bool(incomplete_ids):
        raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, "source cycle accounting drift")


def _source_cycle_body(source_cycle: SourceCoverageCycleBinding) -> dict[str, object]:
    return {
        "accounting_complete": source_cycle.accounting_complete,
        "byte_length": source_cycle.byte_length,
        "duplicate_source_ids": list(source_cycle.duplicate_source_ids),
        "fingerprint": source_cycle.fingerprint,
        "gap_source_ids": list(source_cycle.gap_source_ids),
        "logical_key": source_cycle.logical_key,
        "missing_source_ids": list(source_cycle.missing_source_ids),
        "observation_cutoff": source_cycle.observation_cutoff,
        "release_blocking": source_cycle.release_blocking,
        "vault": source_cycle.vault,
        "version_id": source_cycle.version_id,
    }


def _source_cycle_reference(source_cycle: SourceCoverageCycleBinding) -> str:
    return (
        f"{source_cycle.vault}:{source_cycle.logical_key}@{source_cycle.version_id}"
        f"#{source_cycle.fingerprint}:{source_cycle.byte_length}"
    )


def source_coverage_cycle_binding_from_json(value: object) -> SourceCoverageCycleBinding:
    """Parse the exact acquisition-worker handoff into the corpus boundary type."""
    try:
        document = checked_json_value(value)
    except ContractViolation as error:
        raise CorpusError(
            CorpusErrorCode.COVERAGE_INCOMPLETE,
            "source cycle handoff",
        ) from error
    expected = {
        "accounting_complete",
        "byte_length",
        "duplicate_source_ids",
        "fingerprint",
        "gap_source_ids",
        "logical_key",
        "missing_source_ids",
        "observation_cutoff",
        "release_blocking",
        "vault",
        "version_id",
    }
    if not isinstance(document, dict) or set(document) != expected:
        raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, "source cycle handoff")
    binding = SourceCoverageCycleBinding(
        _json_text(document, "vault"),
        _json_text(document, "logical_key"),
        _json_text(document, "version_id"),
        _json_text(document, "fingerprint"),
        _json_integer(document, "byte_length"),
        _json_text(document, "observation_cutoff"),
        _json_boolean(document, "accounting_complete"),
        _json_boolean(document, "release_blocking"),
        _json_strings(document, "missing_source_ids"),
        _json_strings(document, "duplicate_source_ids"),
        _json_strings(document, "gap_source_ids"),
    )
    _validate_source_cycle_binding(binding, binding.observation_cutoff)
    return binding


def _json_text(document: dict[str, JsonValue], field: str) -> str:
    value = document.get(field)
    if type(value) is not str or not value:
        raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, field)
    return value


def _json_integer(document: dict[str, JsonValue], field: str) -> int:
    value = document.get(field)
    if type(value) is not int:
        raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, field)
    return value


def _json_boolean(document: dict[str, JsonValue], field: str) -> bool:
    value = document.get(field)
    if type(value) is not bool:
        raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, field)
    return value


def _json_strings(document: dict[str, JsonValue], field: str) -> tuple[str, ...]:
    value = document.get(field)
    if not isinstance(value, list) or any(type(item) is not str for item in value):
        raise CorpusError(CorpusErrorCode.COVERAGE_INCOMPLETE, field)
    return tuple(item for item in value if type(item) is str)


def freeze_proposal_package(
    contents_by_role: Mapping[str, bytes],
    inputs: ProposalPackageInput,
) -> ProposalPackage:
    """Verify all exact members, then commit one manifest last."""
    if set(contents_by_role) != set(PROPOSAL_ROLE_PATHS):
        raise CorpusError(CorpusErrorCode.INVENTORY_MISMATCH, "proposal roles")
    if _fingerprint(contents_by_role["PROMOTION_MANIFEST"]) != (
        inputs.promotion_manifest_fingerprint
    ):
        raise CorpusError(CorpusErrorCode.FINGERPRINT_MISMATCH, "promotion manifest")
    artifacts = tuple(
        ProposalArtifact(
            role,
            PROPOSAL_ROLE_PATHS[role],
            "application/json",
            contents_by_role[role],
            _fingerprint(contents_by_role[role]),
        )
        for role in sorted(PROPOSAL_ROLE_PATHS)
    )
    inventory = [
        {
            "byte_size": len(item.content),
            "fingerprint": item.fingerprint,
            "media_type": item.media_type,
            "path": item.path,
            "role": item.role,
        }
        for item in artifacts
    ]
    package_id = _stable_id(
        "ppk",
        inputs.observation_cutoff,
        inputs.promotion_manifest_id,
        _fingerprint(_canonical(inventory)),
    )
    report = next(item for item in artifacts if item.role == "REVIEW_REPORT")
    manifest_bytes = _canonical(
        {
            "artifact_inventory": inventory,
            "base_serving_state_ref": {
                "fingerprint": inputs.base_serving_state_fingerprint,
                "ref_id": inputs.base_serving_state_id,
                "ref_type": "SERVING_STATE",
            },
            "candidate_serving_state_ref": {
                "fingerprint": inputs.candidate_serving_state_fingerprint,
                "ref_id": inputs.candidate_serving_state_id,
                "ref_type": "SERVING_STATE",
            },
            "created_at": inputs.observation_cutoff,
            "immutable": True,
            "observation_cutoff": inputs.observation_cutoff,
            "promotion_manifest_ref": {
                "fingerprint": inputs.promotion_manifest_fingerprint,
                "ref_id": inputs.promotion_manifest_id,
                "ref_type": "PROMOTION_MANIFEST",
            },
            "proposal_package_id": package_id,
            "review_report_ref": {
                "fingerprint": report.fingerprint,
                "ref_id": _stable_id("art", report.path, report.fingerprint),
                "ref_type": "ARTIFACT",
            },
            "schema_id": "asklegal.proposal-package-manifest",
            "schema_version": "1.0.0",
            "status": "REVIEW_READY",
        }
    )
    return ProposalPackage(
        package_id,
        inputs.observation_cutoff,
        inputs.promotion_manifest_id,
        inputs.promotion_manifest_fingerprint,
        inputs.base_serving_state_id,
        inputs.candidate_serving_state_id,
        artifacts,
        manifest_bytes,
        _fingerprint(manifest_bytes),
    )
