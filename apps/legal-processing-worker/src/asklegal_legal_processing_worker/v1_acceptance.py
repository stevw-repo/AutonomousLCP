# ruff: noqa: BLE001, C901, EM101, PLR0912, PLR0913, PLR0915, PLR0917, PLR2004, TRY301
"""Legal-owned positive two-family acceptance boundary for Hong Kong V1."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_contracts.proposal_members import (
    ProposalMemberBindings,
    validate_v1_proposal_members,
)
from asklegal_corpus import (
    PROPOSAL_ROLE_PATHS,
    AuthorityNoteEvidence,
    CorpusRelease,
    CorpusReleaseInput,
    DesiredStateInventory,
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
from asklegal_evidence_vault import (
    ExactObjectReference,
    RetentionProfile,
    VaultName,
    VaultWriteReceipt,
)
from asklegal_legal_desks.hk_case_judgment import (
    accept_complete_cases_acquisition_manifest,
)
from asklegal_legal_desks.hk_case_output import HKCaseProposedServingRecord
from asklegal_legal_desks.hk_legislation_events import HKLegislationDisposition
from asklegal_legal_desks.hk_legislation_records import (
    HKLegislationInventoryOutcome,
    HKLegislationTraceabilityReference,
    hk_legislation_candidate_set_from_bytes,
)

from asklegal_legal_processing_worker.hk_case_release import (
    HKCasePositiveReleaseRequest,
    HKCaseRecordTraceabilityBinding,
    HKCaseReleaseCandidate,
    build_hk_case_corpus_release,
    build_hk_case_record_traceability,
)
from asklegal_legal_processing_worker.hk_legislation_release import (
    HKLegislationAllocatedIdentitySet,
    HKLegislationPriorRecordFact,
    HKLegislationRecordAllocation,
    HKLegislationReleaseSet,
    HKLegislationReleaseSetRequest,
    HKLegislationScopeReleaseRequest,
    accept_hk_legislation_acquisition_manifest,
    build_hk_legislation_scope_release,
    freeze_hk_legislation_release_set,
)
from asklegal_legal_processing_worker.v1_cases_acceptance import (
    CasesAcceptanceError,
    load_verified_case_judgments,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_VERSION = "1.0.0"
_FAMILIES = ("CASES", "LEGISLATION")
_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)
_LEGISLATION_BUILD_ORDER = (
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
)
_ROOT_FILES = (
    "hk-v1-two-family-proposal.json",
    "hk-v1-review-readiness.json",
    "hk-v1-review-package.json",
)
_MAX_ARTIFACT_BYTES = 4_194_304
_REQUEST_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "kind",
        "cutoff_key",
        "observation_cutoff",
        "cases_manifest_fingerprint",
        "legislation_manifest_fingerprint",
        "authentic_changed_families",
        "cutoff_selection_fingerprint",
        "matrix_revision",
        "matrix_fingerprint",
        "families",
        "scope_ids",
        "command_id",
        "operation_id",
        "command_fingerprint",
    }
)
_ACQUISITION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "operation_id",
        "command_fingerprint",
        "observation_cutoff",
        "scope_ids",
        "family_manifests",
        "result",
    }
)
_FAMILY_ACQUISITION_FIELDS = frozenset(
    {
        "schema_id",
        "schema_version",
        "root_cycle_id",
        "root_plan_fingerprint",
        "evidence_reference",
        "children",
    }
)
_EXACT_REFERENCE_FIELDS = frozenset(
    {"vault", "logical_key", "version_id", "fingerprint", "byte_length"}
)
_FAMILY_CHILD_FIELDS = frozenset(
    {
        "source_family",
        "cycle_id",
        "journal_ref",
        "manifest_fingerprint",
        "journal_head_fingerprint",
        "manifest_reference",
        "result",
    }
)


class AcceptanceLegalError(ValueError):
    """One sanitized positive-boundary rejection."""


@dataclass(frozen=True, slots=True)
class TwoFamilyAcceptanceInputs:
    """Already retained, explicit candidate and identity inputs for one operation."""

    operation_id: str
    command_fingerprint: str
    observation_cutoff: str
    cases_manifest_fingerprint: str
    legislation_manifest_fingerprint: str
    case_request: HKCasePositiveReleaseRequest
    legislation_scope_requests: tuple[HKLegislationScopeReleaseRequest, ...]
    legislation_target_key: str
    legislation_lookup_input: RecordTraceabilityLookupInput
    legislation_lookup_shards: tuple[TraceabilityScopeShardInput, ...]
    case_serving_profile: ServingRecordProfile | None
    case_traceability_bindings: tuple[HKCaseRecordTraceabilityBinding, ...]
    package_lookup_input: RecordTraceabilityLookupInput
    package_lookup_shards: tuple[TraceabilityScopeShardInput, ...]


@dataclass(frozen=True, slots=True)
class TwoFamilyAcceptanceReleases:
    """The exact four release snapshots produced by the two owning mappers."""

    case_release: CorpusRelease
    legislation_release_set: HKLegislationReleaseSet


class AcceptanceLegalInputReader(Protocol):
    """Restart-safe retained candidate/identity input boundary."""

    def read_exact(self, operation_id: str) -> TwoFamilyAcceptanceInputs:
        """Read and revalidate one exact operation input."""
        ...


class AcceptanceInputMaterializer(Protocol):
    """Legal-owned canonical writer for exact staged acceptance inputs."""

    def materialize_exact(self, payload: Mapping[str, JsonValue]) -> None:
        """Validate one staged envelope and create-or-match retained files."""
        ...


class AcceptanceInputProducer(Protocol):
    """Legal-owned assembler for retained mapper outputs and policy facts."""

    def produce_exact(self, payload: Mapping[str, JsonValue]) -> None:
        """Create-or-match one staged materialization envelope."""
        ...


class AcceptanceComponentPreparer(Protocol):
    """Compose family-owned release inputs after verified acquisition retention."""

    def prepare_exact(self, payload: Mapping[str, JsonValue], operation_root: Path) -> None:
        """Create-or-match family component documents for one operation."""
        ...


class _CurrentPrimaryVault(Protocol):
    def resolve_current(self, logical_key: str) -> ExactObjectReference | None: ...

    def read_exact(self, reference: ExactObjectReference) -> bytes: ...


class LocalAcceptanceInputProducer:
    """Assemble staged inputs from separate fingerprinted Legal output records."""

    def __init__(
        self,
        processed_root: Path,
        staged_root: Path,
        acquisition_journal_root: Path | None = None,
        primary_vault: _CurrentPrimaryVault | None = None,
        component_preparer: AcceptanceComponentPreparer | None = None,
    ) -> None:
        """Bind distinct retained component and staged-envelope roots."""
        if (
            not processed_root.is_absolute()
            or not staged_root.is_absolute()
            or processed_root.is_symlink()
            or staged_root.is_symlink()
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_CONFIGURATION_INVALID")
        self._processed_root = processed_root
        self._staged_root = staged_root
        self._acquisition_journal_root = acquisition_journal_root
        self._primary_vault = primary_vault
        self._component_preparer = component_preparer

    def produce_exact(self, payload: Mapping[str, JsonValue]) -> None:
        """Bind actual retained component outputs to the Control handoff."""
        request = _object(payload["request"], _REQUEST_FIELDS)
        acquisition = _object(payload["acquisition"], _ACQUISITION_FIELDS)
        _validate_handoff(request, acquisition)
        operation_id = _text(request["operation_id"])
        source = self._processed_root / operation_id
        family = payload.get("family_acquisition_evidence")
        if family is None:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_ACQUISITION_EVIDENCE_NOT_READY")
        self._retain_verified_acquisition_inputs(request, family, source)
        if self._component_preparer is not None:
            self._component_preparer.prepare_exact(payload, source)
        children = self._family_children(_object(family, _FAMILY_ACQUISITION_FIELDS)["children"])
        required_components = (
            "case-release-input.json",
            "legislation-release-input.json",
            "package-traceability-input.json",
            "package-policy-facts.json",
        )
        if not all((source / name).is_file() for name in required_components):
            family_components = (
                source / "case-release-input.json",
                source / "legislation-release-input.json",
            )
            if all(path.is_file() for path in family_components):
                blocker = "LEGAL_PROCESSING_ACCEPTANCE_PACKAGE_FACTS_NOT_READY"
            else:
                blocker = (
                    "LEGAL_PROCESSING_ACCEPTANCE_CURRENT_RELEASE_NOT_READY"
                    if any(child["result"] == "NO_CHANGE" for child in children)
                    else "LEGAL_PROCESSING_ACCEPTANCE_SEMANTIC_OUTPUT_NOT_READY"
                )
            raise AcceptanceLegalError(blocker)
        case = self._component(
            source / "case-release-input.json",
            "asklegal.hk-v1-case-release-input/v1",
            {
                "case_release",
                "case_traceability",
                "cases_manifest_fingerprint",
            },
            request,
        )
        legislation = self._component(
            source / "legislation-release-input.json",
            "asklegal.hk-v1-legislation-release-input/v1",
            {
                "legislation_scopes",
                "legislation_target_key",
                "legislation_lookup_input",
                "legislation_lookup_shards",
                "legislation_manifest_fingerprint",
                "artifacts",
            },
            request,
        )
        traceability = self._component(
            source / "package-traceability-input.json",
            "asklegal.hk-v1-package-traceability-input/v1",
            {"package_lookup_input", "package_lookup_shards"},
            request,
        )
        policy = self._component(
            source / "package-policy-facts.json",
            "asklegal.hk-v1-package-policy-facts/v1",
            {
                "title",
                "base_serving_state_fingerprint",
                "task7_proposal",
                "coverage_status",
                "promotion_manifest",
                "readiness",
                "estimated_cost_microunits",
                "review_statement",
            },
            request,
        )
        if (
            case["cases_manifest_fingerprint"] != request["cases_manifest_fingerprint"]
            or legislation["legislation_manifest_fingerprint"]
            != request["legislation_manifest_fingerprint"]
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PRODUCER_DRIFT")
        legal_body: dict[str, JsonValue] = {
            "schema_id": "asklegal.hk-v1-retained-acceptance-input/v1",
            "schema_version": _VERSION,
            "operation_id": operation_id,
            "command_fingerprint": request["command_fingerprint"],
            "observation_cutoff": request["observation_cutoff"],
            "cases_manifest_fingerprint": request["cases_manifest_fingerprint"],
            "legislation_manifest_fingerprint": request["legislation_manifest_fingerprint"],
            "case_release": case["case_release"],
            "case_traceability": case["case_traceability"],
            "legislation_scopes": legislation["legislation_scopes"],
            "legislation_target_key": legislation["legislation_target_key"],
            "legislation_lookup_input": legislation["legislation_lookup_input"],
            "legislation_lookup_shards": legislation["legislation_lookup_shards"],
            "package_lookup_input": traceability["package_lookup_input"],
            "package_lookup_shards": traceability["package_lookup_shards"],
        }
        policy_body: dict[str, JsonValue] = {
            "schema_id": "asklegal.hk-v1-package-policy-input/v1",
            "schema_version": _VERSION,
            "operation_id": operation_id,
            "observation_cutoff": request["observation_cutoff"],
            **{
                field: policy[field]
                for field in (
                    "title",
                    "base_serving_state_fingerprint",
                    "task7_proposal",
                    "coverage_status",
                    "promotion_manifest",
                    "readiness",
                    "estimated_cost_microunits",
                    "review_statement",
                )
            },
        }
        raw_artifacts = legislation["artifacts"]
        raw_scopes = legislation["legislation_scopes"]
        if type(raw_artifacts) is not list or type(raw_scopes) is not list:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PRODUCER_INVALID")
        declared = {
            _text(_object(item, {"path", "fingerprint", "byte_length"})["path"])
            for item in raw_artifacts
        }
        referenced = {
            _text(
                _object(
                    item,
                    {
                        "scope_id",
                        "candidate_set_path",
                        "candidate_set_fingerprint",
                        "allocated_identities",
                        "serving_profile",
                        "release_evidence_refs",
                        "release_validation_refs",
                        "prior_release",
                        "prior_traceability_entries",
                        "prior_inventory_outcomes",
                        "unchanged",
                    },
                )["candidate_set_path"]
            )
            for item in raw_scopes
        }
        if declared != referenced:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PRODUCER_INVALID")
        target = self._staged_root / operation_id
        artifacts: list[JsonValue] = []
        for raw in raw_artifacts:
            item = _object(raw, {"path", "fingerprint", "byte_length"})
            relative = _safe_relative_path(_text(item["path"]))
            content = _read_regular(source.joinpath(*relative.parts), allow_empty=True)
            size = item["byte_length"]
            if (
                type(size) is not int
                or size < 0
                or len(content) != size
                or _bytes_fingerprint(content) != _exact_fingerprint(item["fingerprint"])
            ):
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PRODUCER_DRIFT")
            _atomic_create_or_match(target.joinpath(*relative.parts), content)
            artifacts.append(item)
        envelope: dict[str, JsonValue] = {
            "schema_id": "asklegal.hk-v1-acceptance-materialization/v1",
            "schema_version": _VERSION,
            "operation_id": operation_id,
            "command_fingerprint": request["command_fingerprint"],
            "observation_cutoff": request["observation_cutoff"],
            "cases_manifest_fingerprint": request["cases_manifest_fingerprint"],
            "legislation_manifest_fingerprint": request["legislation_manifest_fingerprint"],
            "legal_input_body": legal_body,
            "package_policy_body": policy_body,
            "artifacts": artifacts,
        }
        _atomic_create_or_match(
            target / "acceptance-materialization.json",
            _canonical_with_fingerprint(envelope),
        )

    def _retain_verified_acquisition_inputs(
        self,
        request: dict[str, JsonValue],
        value: JsonValue,
        target: Path,
    ) -> None:
        if self._acquisition_journal_root is None or self._primary_vault is None:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_NOT_COMPOSED")
        family = _object(value, _FAMILY_ACQUISITION_FIELDS)
        reference_raw = _object(family["evidence_reference"], _EXACT_REFERENCE_FIELDS)
        size = reference_raw["byte_length"]
        if reference_raw["vault"] != "PRIMARY" or type(size) is not int or size < 1:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_EVIDENCE_INVALID")
        reference = ExactObjectReference(
            VaultName.PRIMARY,
            _text(reference_raw["logical_key"]),
            _text(reference_raw["version_id"]),
            _exact_fingerprint(reference_raw["fingerprint"]),
            size,
        )
        content = self._primary_vault.read_exact(reference)
        evidence = _canonical_object(content)
        original_fields = {
            "schema_id",
            "schema_version",
            "root_instruction",
            "root_plan_fingerprint",
            "children",
        }
        instruction = _object(
            evidence.get("root_instruction"),
            {
                "cycle_id",
                "cycle_kind",
                "scheduled_at",
                "observation_cutoff",
                "matrix_revision",
                "matrix_fingerprint",
            },
        )
        children = self._family_children(family["children"])
        original_children = self._family_children(evidence.get("children"))
        if (
            frozenset(evidence) != frozenset(original_fields)
            or family["schema_id"] != "asklegal.hk-v1.acceptance-family-acquisition-evidence"
            or family["schema_version"] != _VERSION
            or evidence["schema_id"] != "asklegal.hk-v1.scheduled-family-acquisitions"
            or evidence["schema_version"] != _VERSION
            or len(content) != reference.byte_length
            or _bytes_fingerprint(content) != reference.fingerprint
            or family["root_cycle_id"] != instruction["cycle_id"]
            or family["root_plan_fingerprint"] != evidence["root_plan_fingerprint"]
            or instruction["observation_cutoff"] != request["observation_cutoff"]
            or instruction["matrix_revision"] != request["matrix_revision"]
            or instruction["matrix_fingerprint"] != request["matrix_fingerprint"]
            or children != original_children
            or children[0]["manifest_fingerprint"] != request["cases_manifest_fingerprint"]
            or children[1]["manifest_fingerprint"] != request["legislation_manifest_fingerprint"]
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_EVIDENCE_DRIFT")
        verified: list[JsonValue] = []
        for child in children:
            manifest_bytes, manifest_reference = self._verified_manifest(child, target)
            journal = self._verified_journal(child)
            journal["manifest_reference"] = manifest_reference
            journal["manifest_path"] = f"manifests/{_text(child['source_family']).casefold()}.json"
            if child["source_family"] == "CASES" and child["result"] == "COMPLETE":
                journal["normalized_judgments"] = self._normalize_cases(
                    manifest_bytes,
                    target,
                )
            verified.append(journal)
        body: dict[str, JsonValue] = {
            "schema_id": "asklegal.hk-v1-verified-acquisition-inputs/v1",
            "schema_version": _VERSION,
            "operation_id": request["operation_id"],
            "command_fingerprint": request["command_fingerprint"],
            "observation_cutoff": request["observation_cutoff"],
            "family_evidence_reference": reference_raw,
            "families": verified,
        }
        _atomic_create_or_match(
            target / "verified-acquisition-inputs.json",
            _canonical_with_fingerprint(body),
        )

    def _verified_manifest(
        self,
        child: dict[str, JsonValue],
        target: Path,
    ) -> tuple[bytes, dict[str, JsonValue]]:
        vault = self._primary_vault
        if vault is None:  # pragma: no cover - guarded by caller.
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_NOT_COMPOSED")
        raw = _object(child["manifest_reference"], _EXACT_REFERENCE_FIELDS)
        size = raw["byte_length"]
        if raw["vault"] != "PRIMARY" or type(size) is not int or size < 1:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_MANIFEST_INVALID")
        try:
            reference = ExactObjectReference(
                VaultName.PRIMARY,
                _text(raw["logical_key"]),
                _text(raw["version_id"]),
                _exact_fingerprint(raw["fingerprint"]),
                size,
            )
            content = vault.read_exact(reference)
        except (
            AcceptanceLegalError,
            ContractViolation,
            OSError,
            RuntimeError,
            ValueError,
        ) as error:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_MANIFEST_NOT_READY") from error
        if (
            len(content) != size
            or _bytes_fingerprint(content) != reference.fingerprint
            or canonicalize(parse_json_bytes(content, max_bytes=_MAX_ARTIFACT_BYTES)) != content
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_MANIFEST_DRIFT")
        try:
            if child["source_family"] == "CASES":
                accepted = accept_complete_cases_acquisition_manifest(content)
                accepted_cycle = accepted.cycle_id
                accepted_fingerprint = accepted.manifest_fingerprint
            else:
                accepted_legislation = accept_hk_legislation_acquisition_manifest(content)
                accepted_cycle = accepted_legislation.cycle_id
                accepted_fingerprint = accepted_legislation.acquisition_manifest_fingerprint
        except Exception as error:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_MANIFEST_INVALID") from error
        if (
            accepted_cycle != child["cycle_id"]
            or accepted_fingerprint != child["manifest_fingerprint"]
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_MANIFEST_DRIFT")
        _atomic_create_or_match(
            target / "manifests" / f"{_text(child['source_family']).casefold()}.json",
            content,
        )
        return content, raw

    def _normalize_cases(self, manifest: bytes, target: Path) -> list[JsonValue]:
        vault = self._primary_vault
        if vault is None:  # pragma: no cover - guarded by caller.
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_NOT_COMPOSED")
        try:
            judgments = load_verified_case_judgments(manifest, vault)
        except CasesAcceptanceError as error:
            raise AcceptanceLegalError(str(error)) from error
        normalized: list[JsonValue] = []
        for item in judgments:
            artifact_fingerprint = _bytes_fingerprint(item.normalized_artifact)
            relative = f"cases-normalized/{artifact_fingerprint.removeprefix('sha256:')}.json"
            _atomic_create_or_match(target.joinpath(*relative.split("/")), item.normalized_artifact)
            normalized.append(
                {
                    "path": relative,
                    "artifact_fingerprint": artifact_fingerprint,
                    "bundle_fingerprint": item.bundle.bundle_fingerprint,
                    "wrapper_reference": _reference_document(item.wrapper_reference),
                    "capture_reference": _reference_document(item.capture_reference),
                }
            )
        return normalized

    def _family_children(self, value: JsonValue) -> tuple[dict[str, JsonValue], ...]:
        if type(value) is not list or len(value) != 2:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_EVIDENCE_INVALID")
        children = tuple(_object(item, _FAMILY_CHILD_FIELDS) for item in value)
        if tuple(item["source_family"] for item in children) != ("CASES", "LEGISLATION"):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_EVIDENCE_INVALID")
        for child in children:
            _text(child["cycle_id"])
            _exact_fingerprint(child["manifest_fingerprint"])
            _exact_fingerprint(child["journal_head_fingerprint"])
            if child["result"] not in {"COMPLETE", "NO_CHANGE"}:
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_EVIDENCE_INVALID")
        return children

    def _verified_journal(self, child: dict[str, JsonValue]) -> dict[str, JsonValue]:
        journal_ref = _text(child["journal_ref"])
        cycle_id = _text(child["cycle_id"])
        if journal_ref != f"acquisition-journals/{cycle_id}":
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_JOURNAL_INVALID")
        root = self._acquisition_journal_root
        vault = self._primary_vault
        if root is None or vault is None:  # pragma: no cover - guarded by caller.
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_NOT_COMPOSED")
        entries_root = root.joinpath(*journal_ref.split("/"), "entries")
        if entries_root.is_symlink() or not entries_root.is_dir():
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_JOURNAL_NOT_READY")
        paths = sorted(entries_root.glob("*.json"))
        previous = "sha256:" + "0" * 64
        latest: dict[str, dict[str, JsonValue]] = {}
        for sequence, path in enumerate(paths, start=1):
            if path.name != f"{sequence:020d}.json":
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_JOURNAL_INVALID")
            entry = _canonical_object(_read_regular(path))
            expected = {
                "schema_id",
                "schema_version",
                "sequence",
                "previous_entry_fingerprint",
                "work_item",
                "transition",
                "payload",
                "fingerprint",
            }
            unsigned = dict(entry)
            supplied = unsigned.pop("fingerprint", None)
            work_item = _json_object(entry["work_item"])
            work_item_id = _text(work_item.get("work_item_id"))
            if (
                frozenset(entry) != frozenset(expected)
                or entry["schema_id"] != "asklegal.acquisition-journal-entry"
                or entry["schema_version"] != _VERSION
                or entry["sequence"] != sequence
                or entry["previous_entry_fingerprint"] != previous
                or supplied != _bytes_fingerprint(canonicalize(checked_json_value(unsigned)))
            ):
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_JOURNAL_INVALID")
            previous = _exact_fingerprint(entry["fingerprint"])
            latest[work_item_id] = entry
        if previous != child["journal_head_fingerprint"]:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_JOURNAL_DRIFT")
        captures: list[JsonValue] = []
        for _work_item_id, entry in sorted(latest.items()):
            if entry["transition"] not in {"CAPTURED_VERIFIED", "IMPORTED_CAPTURE_VERIFIED"}:
                continue
            payload = _json_object(entry["payload"])
            object_ref = _text(payload.get("object_ref"))
            fingerprint = _exact_fingerprint(payload.get("content_fingerprint"))
            byte_length = payload.get("body_length")
            if (
                type(byte_length) is not int
                or byte_length < 1
                or payload.get("read_back_verified") is not True
            ):
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_JOURNAL_INVALID")
            resolved = vault.resolve_current(object_ref)
            if resolved is None:
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_OBJECT_NOT_READY")
            body = vault.read_exact(resolved)
            if len(body) != byte_length or _bytes_fingerprint(body) != fingerprint:
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_OBJECT_DRIFT")
            captures.append(
                {
                    "logical_key": object_ref,
                    "version_id": resolved.version_id,
                    "content_fingerprint": fingerprint,
                    "body_length": byte_length,
                }
            )
        if child["result"] == "COMPLETE" and not captures:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_OBJECT_NOT_READY")
        return {
            "source_family": child["source_family"],
            "cycle_id": cycle_id,
            "manifest_fingerprint": child["manifest_fingerprint"],
            "journal_head_fingerprint": child["journal_head_fingerprint"],
            "result": child["result"],
            "verified_objects": captures,
        }

    def _component(
        self,
        path: Path,
        schema_id: str,
        fields: set[str],
        request: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        try:
            document = _canonical_object(_read_regular(path))
        except AcceptanceLegalError:
            raise
        except (ContractViolation, ValueError) as error:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PRODUCER_INVALID") from error
        common = {
            "schema_id",
            "schema_version",
            "operation_id",
            "command_fingerprint",
            "observation_cutoff",
            "fingerprint",
        }
        if frozenset(document) != frozenset(common | fields):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PRODUCER_INVALID")
        unsigned = dict(document)
        supplied = unsigned.pop("fingerprint", None)
        if (
            document["schema_id"] != schema_id
            or document["schema_version"] != _VERSION
            or document["operation_id"] != request["operation_id"]
            or document["command_fingerprint"] != request["command_fingerprint"]
            or document["observation_cutoff"] != request["observation_cutoff"]
            or supplied != _bytes_fingerprint(canonicalize(checked_json_value(unsigned)))
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PRODUCER_DRIFT")
        return document


class LocalAcceptanceInputMaterializer:
    """Materialize fingerprinted bodies and exact artifacts without policy defaults."""

    def __init__(self, staged_root: Path, retained_root: Path) -> None:
        """Bind distinct staged-envelope and final retained-input roots."""
        if (
            not staged_root.is_absolute()
            or not retained_root.is_absolute()
            or staged_root.is_symlink()
            or retained_root.is_symlink()
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_CONFIGURATION_INVALID")
        self._staged_root = staged_root
        self._retained_root = retained_root

    def materialize_exact(self, payload: Mapping[str, JsonValue]) -> None:
        """Create-or-match canonical retained inputs after exact validation."""
        request = _object(payload["request"], _REQUEST_FIELDS)
        acquisition = _object(payload["acquisition"], _ACQUISITION_FIELDS)
        _validate_handoff(request, acquisition)
        operation_id = _text(request["operation_id"])
        source = self._staged_root / operation_id
        envelope = _canonical_object(_read_regular(source / "acceptance-materialization.json"))
        expected = {
            "schema_id",
            "schema_version",
            "operation_id",
            "command_fingerprint",
            "observation_cutoff",
            "cases_manifest_fingerprint",
            "legislation_manifest_fingerprint",
            "legal_input_body",
            "package_policy_body",
            "artifacts",
            "fingerprint",
        }
        unsigned = dict(envelope)
        supplied = unsigned.pop("fingerprint", None)
        if (
            frozenset(envelope) != frozenset(expected)
            or envelope["schema_id"] != "asklegal.hk-v1-acceptance-materialization/v1"
            or envelope["schema_version"] != _VERSION
            or envelope["operation_id"] != operation_id
            or envelope["command_fingerprint"] != request["command_fingerprint"]
            or envelope["observation_cutoff"] != request["observation_cutoff"]
            or envelope["cases_manifest_fingerprint"] != request["cases_manifest_fingerprint"]
            or envelope["legislation_manifest_fingerprint"]
            != request["legislation_manifest_fingerprint"]
            or supplied != _bytes_fingerprint(canonicalize(checked_json_value(unsigned)))
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_MATERIALIZATION_DRIFT")
        target = self._retained_root / operation_id
        raw_artifacts = envelope["artifacts"]
        if type(raw_artifacts) is not list:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_MATERIALIZATION_INVALID")
        for raw in raw_artifacts:
            item = _object(raw, {"path", "fingerprint", "byte_length"})
            relative = _safe_relative_path(_text(item["path"]))
            content = _read_regular(source.joinpath(*relative.parts), allow_empty=True)
            size = item["byte_length"]
            if (
                type(size) is not int
                or size < 0
                or len(content) != size
                or _bytes_fingerprint(content) != _exact_fingerprint(item["fingerprint"])
            ):
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_MATERIALIZATION_DRIFT")
            _atomic_create_or_match(target.joinpath(*relative.parts), content)
        legal_body = _json_object(envelope["legal_input_body"])
        policy_body = _json_object(envelope["package_policy_body"])
        legal_content = _canonical_with_fingerprint(legal_body)
        policy_content = _canonical_with_fingerprint(policy_body)
        _atomic_create_or_match(target / "legal-input.json", legal_content)
        _atomic_create_or_match(target / "package-policy.json", policy_content)
        LocalAcceptanceLegalInputReader(self._retained_root).read_exact(operation_id)
        _read_package_policy(target / "package-policy.json", operation_id)


class LocalAcceptanceLegalInputReader:
    """Strict filesystem reader for one fingerprinted restart-safe operation input."""

    def __init__(self, root: Path) -> None:
        """Bind one explicit non-symlink retained-input root."""
        if not root.is_absolute() or root.is_symlink():
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_CONFIGURATION_INVALID")
        self._root = root

    def read_exact(self, operation_id: str) -> TwoFamilyAcceptanceInputs:
        """Reissue candidate snapshots and reconstruct explicit identity allocations."""
        operation_root = self._root / operation_id
        content = _read_regular(operation_root / "legal-input.json")
        document = _canonical_object(content)
        expected = {
            "schema_id",
            "schema_version",
            "operation_id",
            "command_fingerprint",
            "observation_cutoff",
            "cases_manifest_fingerprint",
            "legislation_manifest_fingerprint",
            "case_release",
            "legislation_scopes",
            "legislation_target_key",
            "legislation_lookup_input",
            "legislation_lookup_shards",
            "case_traceability",
            "package_lookup_input",
            "package_lookup_shards",
            "fingerprint",
        }
        if frozenset(document) != frozenset(expected):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
        unsigned = dict(document)
        supplied = unsigned.pop("fingerprint", None)
        if (
            document["schema_id"] != "asklegal.hk-v1-retained-acceptance-input/v1"
            or document["schema_version"] != _VERSION
            or document["operation_id"] != operation_id
            or supplied != _bytes_fingerprint(canonicalize(checked_json_value(unsigned)))
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
        raw_scopes = document["legislation_scopes"]
        raw_shards = document["legislation_lookup_shards"]
        raw_package_shards = document["package_lookup_shards"]
        if (
            type(raw_scopes) is not list
            or type(raw_shards) is not list
            or type(raw_package_shards) is not list
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
        requests = tuple(_decode_legislation_scope(operation_root, raw) for raw in raw_scopes)
        lookup = _object(
            document["legislation_lookup_input"],
            {
                "lookup_revision_id",
                "manifest_schema_fingerprint",
                "entry_schema_fingerprint",
            },
        )
        package_lookup = _object(
            document["package_lookup_input"],
            {
                "lookup_revision_id",
                "manifest_schema_fingerprint",
                "entry_schema_fingerprint",
            },
        )
        case_profile, case_bindings = _decode_case_traceability(document["case_traceability"])
        return TwoFamilyAcceptanceInputs(
            operation_id,
            _exact_fingerprint(document["command_fingerprint"]),
            _text(document["observation_cutoff"]),
            _exact_fingerprint(document["cases_manifest_fingerprint"]),
            _exact_fingerprint(document["legislation_manifest_fingerprint"]),
            _decode_case_release(document["case_release"]),
            requests,
            _text(document["legislation_target_key"]),
            RecordTraceabilityLookupInput(
                _text(lookup["lookup_revision_id"]),
                _exact_fingerprint(lookup["manifest_schema_fingerprint"]),
                _exact_fingerprint(lookup["entry_schema_fingerprint"]),
            ),
            tuple(_decode_lookup_shard(raw) for raw in raw_shards),
            case_profile,
            case_bindings,
            RecordTraceabilityLookupInput(
                _text(package_lookup["lookup_revision_id"]),
                _exact_fingerprint(package_lookup["manifest_schema_fingerprint"]),
                _exact_fingerprint(package_lookup["entry_schema_fingerprint"]),
            ),
            tuple(_decode_lookup_shard(raw) for raw in raw_package_shards),
        )


class AcceptanceProposalFreezer(Protocol):
    """Freeze and read back the complete Review package for four releases."""

    def freeze_exact(
        self,
        payload: Mapping[str, JsonValue],
        releases: TwoFamilyAcceptanceReleases,
        inputs: TwoFamilyAcceptanceInputs,
    ) -> ExactObjectReference:
        """Return the exact Primary-vault root only after Review-root read-back."""
        ...


class _AcceptanceVault(Protocol):
    @property
    def vault_name(self) -> VaultName: ...

    def conditional_create(
        self, logical_key: str, content: bytes, retention: RetentionProfile
    ) -> VaultWriteReceipt: ...

    def read_exact(self, reference: ExactObjectReference) -> bytes: ...


class LocalReviewArtifactFreezer:
    """Manifest-last local Review freeze with exact member and vault read-back."""

    def __init__(
        self,
        staged_root: Path,
        review_root: Path,
        primary_vault: _AcceptanceVault,
        retention: RetentionProfile,
    ) -> None:
        """Bind explicit roots; construction performs no read or write."""
        if (
            not staged_root.is_absolute()
            or not review_root.is_absolute()
            or staged_root.is_symlink()
            or review_root.is_symlink()
            or primary_vault.vault_name is not VaultName.PRIMARY
            or type(retention) is not RetentionProfile
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_CONFIGURATION_INVALID")
        self._staged_root = staged_root
        self._review_root = review_root
        self._vault = primary_vault
        self._retention = retention

    def freeze_exact(
        self,
        payload: Mapping[str, JsonValue],
        releases: TwoFamilyAcceptanceReleases,
        inputs: TwoFamilyAcceptanceInputs,
    ) -> ExactObjectReference:
        """Build the closed bundle from releases and retained policy, then commit it."""
        request = _object(payload["request"], _REQUEST_FIELDS)
        operation_id = _text(request["operation_id"])
        source = self._staged_root / operation_id
        policy = _read_package_policy(source / "package-policy.json", operation_id)
        contents, shards, task7, readiness, package_content = _build_review_package(
            request,
            releases,
            inputs,
            policy,
        )
        package = _canonical_object(package_content)
        bindings = ProposalMemberBindings(
            _text(package["observation_cutoff"]),
            _text(package["promotion_manifest_id"]),
            _exact_fingerprint(package["promotion_manifest_fingerprint"]),
            _text(package["base_serving_state_id"]),
            _text(package["candidate_serving_state_id"]),
            _exact_fingerprint(package["candidate_serving_state_fingerprint"]),
        )
        validate_v1_proposal_members(contents, bindings, shards)
        _validate_release_member(contents["CORPUS_RELEASES"], releases)
        _validate_root_bindings(task7, readiness, package, releases)
        generation = _prepare_review_generation(
            self._review_root,
            _text(package["package_fingerprint"]),
            contents,
            shards,
            task7,
            readiness,
            package_content,
        )
        receipt = self._vault.conditional_create(
            (
                f"hk-v1/proposals/{operation_id}/"
                f"{_text(package['package_fingerprint']).removeprefix('sha256:')}.json"
            ),
            package_content,
            self._retention,
        )
        if self._vault.read_exact(receipt.reference) != package_content:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PROPOSAL_READBACK_FAILED")
        _publish_review_generation(self._review_root, generation)
        return receipt.reference


def build_two_family_acceptance_releases(
    inputs: TwoFamilyAcceptanceInputs,
) -> TwoFamilyAcceptanceReleases:
    """Run the Case mapper and existing three-scope Legislation builders."""
    if type(inputs) is not TwoFamilyAcceptanceInputs:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    try:
        case_release = build_hk_case_corpus_release(inputs.case_request)
        requests = inputs.legislation_scope_requests
        if (
            type(requests) is not tuple
            or tuple(item.candidate_set.legislation_scope_code for item in requests)
            != _LEGISLATION_BUILD_ORDER
        ):
            raise TypeError
        scope_results = tuple(build_hk_legislation_scope_release(item) for item in requests)
        legislation = freeze_hk_legislation_release_set(
            HKLegislationReleaseSetRequest(
                scope_results,
                inputs.legislation_target_key,
                inputs.observation_cutoff,
                inputs.legislation_lookup_input,
                inputs.legislation_lookup_shards,
            )
        )
        if case_release.observation_cutoff != inputs.observation_cutoff:
            raise TypeError
        return TwoFamilyAcceptanceReleases(case_release, legislation)
    except AcceptanceLegalError:
        raise
    except (AttributeError, TypeError, ValueError) as error:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_RELEASE_INVALID") from error


def preview_generated_family_releases(operation_root: Path) -> TwoFamilyAcceptanceReleases:
    """Rebuild both releases from generated component files before package-fact issuance."""
    try:
        case_document = _canonical_object(_read_regular(operation_root / "case-release-input.json"))
        legislation_document = _canonical_object(
            _read_regular(operation_root / "legislation-release-input.json")
        )
        raw_scopes = legislation_document.get("legislation_scopes")
        raw_shards = legislation_document.get("legislation_lookup_shards")
        raw_lookup = legislation_document.get("legislation_lookup_input")
        if (
            type(raw_scopes) is not list
            or type(raw_shards) is not list
            or type(raw_lookup) is not dict
        ):
            raise TypeError
        case_release = build_hk_case_corpus_release(
            _decode_case_release(case_document["case_release"])
        )
        requests = tuple(_decode_legislation_scope(operation_root, item) for item in raw_scopes)
        scope_results = tuple(build_hk_legislation_scope_release(item) for item in requests)
        legislation = freeze_hk_legislation_release_set(
            HKLegislationReleaseSetRequest(
                scope_results,
                _text(legislation_document["legislation_target_key"]),
                _text(legislation_document["observation_cutoff"]),
                RecordTraceabilityLookupInput(
                    _text(raw_lookup["lookup_revision_id"]),
                    _exact_fingerprint(raw_lookup["manifest_schema_fingerprint"]),
                    _exact_fingerprint(raw_lookup["entry_schema_fingerprint"]),
                ),
                tuple(_decode_lookup_shard(item) for item in raw_shards),
            )
        )
        return TwoFamilyAcceptanceReleases(case_release, legislation)
    except AcceptanceLegalError:
        raise
    except Exception as error:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_RELEASE_INVALID") from error


def start_hk_v1_acceptance_legal_processing(
    payload: object,
    reader: AcceptanceLegalInputReader,
    freezer: AcceptanceProposalFreezer,
    materializer: AcceptanceInputMaterializer | None = None,
) -> dict[str, JsonValue]:
    """Revalidate Control handoff, build four releases, and freeze one proposal."""
    request: dict[str, JsonValue] | None = None
    try:
        root = _acceptance_payload(payload)
        request = _object(root["request"], _REQUEST_FIELDS)
        acquisition = _object(root["acquisition"], _ACQUISITION_FIELDS)
        _validate_handoff(request, acquisition)
        operation_id = _text(request["operation_id"])
        if materializer is not None:
            materializer.materialize_exact(root)
        inputs = reader.read_exact(operation_id)
        _validate_retained_bindings(request, inputs)
        releases = build_two_family_acceptance_releases(inputs)
        reference = freezer.freeze_exact(root, releases, inputs)
        if type(reference) is not ExactObjectReference or reference.vault is not VaultName.PRIMARY:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PROPOSAL_INVALID")
        return _result(request, releases, reference)
    except AcceptanceLegalError as error:
        return _not_ready(request, str(error))
    except Exception:
        return _not_ready(request, "LEGAL_PROCESSING_ACCEPTANCE_INTERNAL_INVALID")


def unavailable_hk_v1_acceptance_legal_processing(payload: object) -> dict[str, JsonValue]:
    """Return an exact Control-compatible non-success before any downstream call."""
    request: dict[str, JsonValue] | None = None
    try:
        root = _acceptance_payload(payload)
        request = _object(root["request"], _REQUEST_FIELDS)
        acquisition = _object(root["acquisition"], _ACQUISITION_FIELDS)
        _validate_handoff(request, acquisition)
    except AcceptanceLegalError, AttributeError, TypeError, ValueError:
        pass
    return _not_ready(request, "LEGAL_PROCESSING_ACCEPTANCE_NOT_COMPOSED")


def prepare_hk_v1_acceptance_inputs(
    payload: object,
    producer: AcceptanceInputProducer | None,
) -> dict[str, JsonValue]:
    """Produce staged inputs or return the exact sanitized Legal result."""
    request: dict[str, JsonValue] | None = None
    try:
        root = _acceptance_payload(payload)
        request = _object(root["request"], _REQUEST_FIELDS)
        acquisition = _object(root["acquisition"], _ACQUISITION_FIELDS)
        _validate_handoff(request, acquisition)
        if producer is None:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_NOT_COMPOSED")
        producer.produce_exact(root)
        return {
            "schema_id": "asklegal.hk-v1-acceptance-input-preparation-result",
            "schema_version": _VERSION,
            "operation_id": request["operation_id"],
            "command_fingerprint": request["command_fingerprint"],
            "result": "INPUTS_READY",
            "blocker_codes": [],
        }
    except AcceptanceLegalError as error:
        return _not_ready(request, str(error))
    except Exception:
        return _not_ready(request, "LEGAL_PROCESSING_ACCEPTANCE_INTERNAL_INVALID")


def _validate_handoff(request: dict[str, JsonValue], acquisition: dict[str, JsonValue]) -> None:
    if (
        request["schema_id"] != "asklegal.hk-v1.acceptance-cycle-request"
        or request["schema_version"] != _VERSION
        or request["families"] != list(_FAMILIES)
        or request["scope_ids"] != list(_SCOPES)
        or acquisition["schema_id"] != "asklegal.hk-v1.acceptance-acquisition-result"
        or acquisition["schema_version"] != _VERSION
        or acquisition["operation_id"] != request["operation_id"]
        or acquisition["command_fingerprint"] != request["command_fingerprint"]
        or acquisition["observation_cutoff"] != request["observation_cutoff"]
        or acquisition["scope_ids"] != list(_SCOPES)
        or acquisition["result"] != "COMPLETE"
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PAYLOAD_INVALID")
    families = acquisition["family_manifests"]
    if type(families) is not list or len(families) != 2:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PAYLOAD_INVALID")
    expected = (
        ("CASES", request["cases_manifest_fingerprint"]),
        ("LEGISLATION", request["legislation_manifest_fingerprint"]),
    )
    for raw, (family, fingerprint) in zip(families, expected, strict=True):
        item = _object(
            raw,
            {
                "material_family",
                "manifest_fingerprint",
                "result",
                "retryable_count",
                "rejected_count",
            },
        )
        if (
            item["material_family"] != family
            or item["manifest_fingerprint"] != fingerprint
            or item["result"] not in {"COMPLETE", "NO_CHANGE"}
            or item["retryable_count"] != 0
            or item["rejected_count"] != 0
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PAYLOAD_INVALID")


def _validate_retained_bindings(
    request: dict[str, JsonValue], inputs: TwoFamilyAcceptanceInputs
) -> None:
    if (
        type(inputs) is not TwoFamilyAcceptanceInputs
        or inputs.operation_id != request["operation_id"]
        or inputs.command_fingerprint != request["command_fingerprint"]
        or inputs.observation_cutoff != request["observation_cutoff"]
        or inputs.cases_manifest_fingerprint != request["cases_manifest_fingerprint"]
        or inputs.legislation_manifest_fingerprint != request["legislation_manifest_fingerprint"]
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_DRIFT")


def _result(
    request: dict[str, JsonValue],
    releases: TwoFamilyAcceptanceReleases,
    reference: ExactObjectReference,
) -> dict[str, JsonValue]:
    legislation = {
        item.legislation_scope_code: item.release
        for item in releases.legislation_release_set.scope_results
    }
    by_scope = {"HK-CASE-BINDING-POST-1997": releases.case_release, **legislation}
    scope_results: list[JsonValue] = []
    for scope_id in _SCOPES:
        release = by_scope[scope_id]
        refs = tuple(release.zero_record_justification_refs)
        if (not release.records) != bool(refs):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_RELEASE_INVALID")
        scope_results.append(
            {
                "scope_id": scope_id,
                "result": "COMPLETE",
                "record_count": len(release.records),
                "release_id": release.release_id,
                "release_fingerprint": release.release_fingerprint,
                "zero_record_justification_refs": list(refs),
            }
        )
    return {
        "schema_id": "asklegal.hk-v1.acceptance-legal-result",
        "schema_version": _VERSION,
        "operation_id": request["operation_id"],
        "command_fingerprint": request["command_fingerprint"],
        "observation_cutoff": request["observation_cutoff"],
        "families": list(_FAMILIES),
        "scope_results": scope_results,
        "proposal_reference": {
            "vault": reference.vault.value,
            "logical_key": reference.logical_key,
            "version_id": reference.version_id,
            "fingerprint": reference.fingerprint,
            "byte_length": reference.byte_length,
        },
        "blocker_codes": [],
        "result": "PROPOSAL_READY",
    }


def _not_ready(
    request: dict[str, JsonValue] | None,
    blocker_code: str,
) -> dict[str, JsonValue]:
    valid = request is not None
    return {
        "schema_id": "asklegal.hk-v1.acceptance-legal-result",
        "schema_version": _VERSION,
        "operation_id": _safe(request, "operation_id") if valid else "invalid",
        "command_fingerprint": (
            _safe(request, "command_fingerprint") if valid else "sha256:" + "0" * 64
        ),
        "observation_cutoff": (
            _safe(request, "observation_cutoff") if valid else "1970-01-01T00:00:00Z"
        ),
        "families": list(_FAMILIES),
        "scope_results": [],
        "proposal_reference": None,
        "blocker_codes": [blocker_code],
        "result": "NOT_READY",
    }


def _object(value: JsonValue, fields: set[str] | frozenset[str]) -> dict[str, JsonValue]:
    if type(value) is not dict or frozenset(value) != frozenset(fields):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PAYLOAD_INVALID")
    return value


def _acceptance_payload(payload: object) -> dict[str, JsonValue]:
    value = checked_json_value(payload)
    if type(value) is not dict or frozenset(value) not in {
        frozenset({"request", "acquisition"}),
        frozenset({"request", "acquisition", "family_acquisition_evidence"}),
    }:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PAYLOAD_INVALID")
    return value


def _text(value: JsonValue) -> str:
    if type(value) is not str or not value:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PAYLOAD_INVALID")
    return value


def _safe(document: dict[str, JsonValue] | None, field: str) -> str:
    value = None if document is None else document.get(field)
    return value if type(value) is str and value else "invalid"


def _decode_case_release(value: JsonValue) -> HKCasePositiveReleaseRequest:
    document = _object(
        value,
        {
            "observation_cutoff",
            "candidates",
            "release_evidence_refs",
            "release_validation_refs",
            "zero_record_justification_refs",
        },
    )
    raw_candidates = document["candidates"]
    if type(raw_candidates) is not list:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    return HKCasePositiveReleaseRequest(
        _text(document["observation_cutoff"]),
        tuple(_decode_case_candidate(item) for item in raw_candidates),
        _texts(document["release_evidence_refs"]),
        _texts(document["release_validation_refs"]),
        _texts(document["zero_record_justification_refs"]),
    )


def _decode_case_candidate(value: JsonValue) -> HKCaseReleaseCandidate:
    document = _object(value, {"proposed_record", "artifact_ref", "evidence_refs"})
    record = _object(
        document["proposed_record"],
        {
            "record_id",
            "proposition_id",
            "ledger_fingerprint",
            "renderer_proposition_id",
            "text",
            "country",
            "jurisdiction",
            "material_type",
            "source",
            "authority_note",
            "text_token_count",
            "payload_byte_count",
            "payload_fingerprint",
        },
    )
    return HKCaseReleaseCandidate(
        HKCaseProposedServingRecord(
            _text(record["record_id"]),
            _text(record["proposition_id"]),
            _exact_fingerprint(record["ledger_fingerprint"]),
            _text(record["renderer_proposition_id"]),
            _text(record["text"]),
            _text(record["country"]),
            _text(record["jurisdiction"]),
            _text(record["material_type"]),
            _text(record["source"]),
            _text(record["authority_note"]),
            _integer(record["text_token_count"]),
            _integer(record["payload_byte_count"]),
            _exact_fingerprint(record["payload_fingerprint"]),
        ),
        _text(document["artifact_ref"]),
        _texts(document["evidence_refs"]),
    )


def _decode_legislation_scope(
    operation_root: Path, value: JsonValue
) -> HKLegislationScopeReleaseRequest:
    document = _object(
        value,
        {
            "scope_id",
            "candidate_set_path",
            "candidate_set_fingerprint",
            "allocated_identities",
            "serving_profile",
            "release_evidence_refs",
            "release_validation_refs",
            "prior_release",
            "prior_traceability_entries",
            "prior_inventory_outcomes",
            "unchanged",
        },
    )
    scope = _text(document["scope_id"])
    path = _text(document["candidate_set_path"])
    expected_path = f"legislation/{scope}/candidate-set.json"
    if path != expected_path:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    candidate_content = _read_regular(operation_root.joinpath(*path.split("/")))
    if _bytes_fingerprint(candidate_content) != _exact_fingerprint(
        document["candidate_set_fingerprint"]
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_DRIFT")
    candidate_set = hk_legislation_candidate_set_from_bytes(candidate_content)
    if candidate_set.legislation_scope_code != scope:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_DRIFT")
    unchanged = document["unchanged"]
    if type(unchanged) is not bool:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    prior_release: CorpusRelease | None = None
    prior_traceability: tuple[TraceabilityEntry, ...] | None = None
    prior_outcomes: tuple[HKLegislationInventoryOutcome, ...] | None = None
    if unchanged:
        prior_release = _decode_prior_release(document["prior_release"])
        raw_traceability = document["prior_traceability_entries"]
        raw_outcomes = document["prior_inventory_outcomes"]
        if type(raw_traceability) is not list or type(raw_outcomes) is not list:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
        prior_traceability = tuple(_decode_traceability_entry(item) for item in raw_traceability)
        prior_outcomes = tuple(_decode_inventory_outcome(item) for item in raw_outcomes)
    elif any(
        document[field] is not None
        for field in (
            "prior_release",
            "prior_traceability_entries",
            "prior_inventory_outcomes",
        )
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    profile = _object(
        document["serving_profile"],
        {"serving_record_profile_id", "schema_version", "schema_fingerprint"},
    )
    return HKLegislationScopeReleaseRequest(
        candidate_set=candidate_set,
        allocated_identities=_decode_allocated_identities(document["allocated_identities"], scope),
        serving_profile=ServingRecordProfile(
            _text(profile["serving_record_profile_id"]),
            _text(profile["schema_version"]),
            _exact_fingerprint(profile["schema_fingerprint"]),
        ),
        release_evidence_refs=_texts(document["release_evidence_refs"]),
        release_validation_refs=_texts(document["release_validation_refs"]),
        prior_release=prior_release,
        prior_traceability_entries=prior_traceability,
        prior_inventory_outcomes=prior_outcomes,
        unchanged=unchanged,
    )


def _decode_allocated_identities(value: JsonValue, scope: str) -> HKLegislationAllocatedIdentitySet:
    document = _object(
        value,
        {"corpus_scope_id", "allocations", "lookup_revision_id", "lookup_shard_id"},
    )
    if document["corpus_scope_id"] != scope:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    allocations = document["allocations"]
    if type(allocations) is not list:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    result: list[HKLegislationRecordAllocation] = []
    for raw in allocations:
        item = _object(
            raw,
            {
                "legislation_scope_code",
                "candidate_key",
                "search_record_id",
                "continuity",
                "predecessor_record_id",
                "predecessor_payload_fingerprint",
                "predecessor_record_fact",
            },
        )
        continuity = _continuity(item["continuity"])
        if item["legislation_scope_code"] != scope:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
        predecessor_id = _optional_text(item["predecessor_record_id"])
        predecessor_fingerprint = (
            None
            if item["predecessor_payload_fingerprint"] is None
            else _exact_fingerprint(item["predecessor_payload_fingerprint"])
        )
        predecessor_fact = _decode_prior_record_fact(item["predecessor_record_fact"])
        if (continuity == "INITIAL") != (
            predecessor_id is None and predecessor_fingerprint is None and predecessor_fact is None
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
        result.append(
            HKLegislationRecordAllocation(
                scope,
                _text(item["candidate_key"]),
                _text(item["search_record_id"]),
                continuity,
                predecessor_id,
                predecessor_fingerprint,
                predecessor_fact,
            )
        )
    return HKLegislationAllocatedIdentitySet(
        _text(document["corpus_scope_id"]),
        tuple(result),
        _optional_text(document["lookup_revision_id"]),
        _optional_text(document["lookup_shard_id"]),
    )


def _decode_lookup_shard(value: JsonValue) -> TraceabilityScopeShardInput:
    document = _object(value, {"release_scope_id", "corpus_release_id", "lookup_shard_id"})
    return TraceabilityScopeShardInput(
        _text(document["release_scope_id"]),
        _text(document["corpus_release_id"]),
        _text(document["lookup_shard_id"]),
    )


def _decode_prior_record_fact(value: JsonValue) -> HKLegislationPriorRecordFact | None:
    if value is None:
        return None
    document = _object(value, {"corpus_scope_id", "record"})
    return HKLegislationPriorRecordFact(
        _text(document["corpus_scope_id"]),
        _decode_serving_record(document["record"]),
    )


def _decode_serving_record(value: JsonValue) -> ServingRecord:
    document = _object(
        value,
        {
            "record_id",
            "text",
            "country",
            "jurisdiction",
            "material_type",
            "source",
            "authority_note",
            "artifact_ref",
            "evidence_refs",
        },
    )
    return ServingRecord(
        _text(document["record_id"]),
        _text(document["text"]),
        _text(document["country"]),
        _text(document["jurisdiction"]),
        _text(document["material_type"]),
        _text(document["source"]),
        _text(document["authority_note"]),
        _text(document["artifact_ref"]),
        _texts(document["evidence_refs"]),
    )


def _decode_prior_release(value: JsonValue) -> CorpusRelease:
    document = _object(
        value,
        {
            "release_id",
            "scope_id",
            "observation_cutoff",
            "records",
            "evidence_refs",
            "validation_refs",
            "withholding_refs",
            "zero_record_justification_refs",
            "records_fingerprint",
            "release_fingerprint",
        },
    )
    raw_records = document["records"]
    if type(raw_records) is not list:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    records: list[ServingRecord] = []
    for raw in raw_records:
        item = _object(raw, {"record", "serving_payload_fingerprint"})
        record = _decode_serving_record(item["record"])
        if _exact_fingerprint(item["serving_payload_fingerprint"]) != (
            _bytes_fingerprint(
                canonicalize(
                    checked_json_value(
                        {
                            "authority_note": record.authority_note,
                            "country": record.country,
                            "jurisdiction": record.jurisdiction,
                            "source": record.source,
                            "text": record.text,
                            "type": record.material_type,
                        }
                    )
                )
            )
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_DRIFT")
        records.append(record)
    release = freeze_corpus_release(
        CorpusReleaseInput(
            _text(document["scope_id"]),
            _text(document["observation_cutoff"]),
            _texts(document["evidence_refs"]),
            _texts(document["validation_refs"]),
            _texts(document["withholding_refs"]),
            _texts(document["zero_record_justification_refs"]),
        ),
        tuple(records),
    )
    if (
        release.release_id != document["release_id"]
        or release.records_fingerprint != document["records_fingerprint"]
        or release.release_fingerprint != document["release_fingerprint"]
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_DRIFT")
    return release


def _decode_traceability_entry(value: JsonValue) -> TraceabilityEntry:
    document = _object(
        value,
        {
            "search_record_id",
            "serving_payload_fingerprint",
            "serving_record_profile_id",
            "legal_item_id",
            "official_version_ids",
            "legal_location_ids",
            "release_scope_id",
            "corpus_release_id",
            "evidence_refs",
            "authority_note_evidence",
            "grouping_ids",
            "display_citation_ids",
        },
    )
    authority = _object(
        document["authority_note_evidence"],
        {"rendered_value_fingerprint", "decision_ref", "supporting_evidence_refs"},
    )
    raw_evidence = document["evidence_refs"]
    raw_supporting = authority["supporting_evidence_refs"]
    if type(raw_evidence) is not list or type(raw_supporting) is not list:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    return TraceabilityEntry(
        _text(document["search_record_id"]),
        _exact_fingerprint(document["serving_payload_fingerprint"]),
        _text(document["serving_record_profile_id"]),
        _text(document["legal_item_id"]),
        _texts(document["official_version_ids"]),
        _texts(document["legal_location_ids"]),
        _text(document["release_scope_id"]),
        _text(document["corpus_release_id"]),
        tuple(_decode_traceability_reference(item) for item in raw_evidence),
        AuthorityNoteEvidence(
            _exact_fingerprint(authority["rendered_value_fingerprint"]),
            _decode_traceability_reference(authority["decision_ref"]),
            tuple(_decode_traceability_reference(item) for item in raw_supporting),
        ),
        _texts(document["grouping_ids"]),
        _texts(document["display_citation_ids"]),
    )


def _decode_inventory_outcome(value: JsonValue) -> HKLegislationInventoryOutcome:
    document = _object(
        value,
        {
            "inventory_item_id",
            "legal_disposition",
            "outcome_kind",
            "reason_code",
            "draft_keys",
            "supporting_refs",
        },
    )
    raw_refs = document["supporting_refs"]
    if type(raw_refs) is not list:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    refs = tuple(
        HKLegislationTraceabilityReference(item.ref_type, item.ref_id, item.fingerprint)
        for item in (_decode_traceability_reference(raw) for raw in raw_refs)
    )
    try:
        disposition = HKLegislationDisposition(_text(document["legal_disposition"]))
    except ValueError as error:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID") from error
    kind = _outcome_kind(document["outcome_kind"])
    return HKLegislationInventoryOutcome(
        _text(document["inventory_item_id"]),
        disposition,
        kind,
        _text(document["reason_code"]),
        _texts(document["draft_keys"]),
        refs,
    )


def _decode_case_traceability(
    value: JsonValue,
) -> tuple[ServingRecordProfile | None, tuple[HKCaseRecordTraceabilityBinding, ...]]:
    document = _object(value, {"serving_profile", "bindings"})
    raw_bindings = document["bindings"]
    if type(raw_bindings) is not list:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    if document["serving_profile"] is None:
        if raw_bindings:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
        return None, ()
    profile = _object(
        document["serving_profile"],
        {"serving_record_profile_id", "schema_version", "schema_fingerprint"},
    )
    return (
        ServingRecordProfile(
            _text(profile["serving_record_profile_id"]),
            _text(profile["schema_version"]),
            _exact_fingerprint(profile["schema_fingerprint"]),
        ),
        tuple(_decode_case_traceability_binding(item) for item in raw_bindings),
    )


def _decode_case_traceability_binding(value: JsonValue) -> HKCaseRecordTraceabilityBinding:
    document = _object(
        value,
        {
            "record_id",
            "serving_profile_id",
            "legal_item_id",
            "official_version_ids",
            "legal_location_ids",
            "evidence_refs",
            "authority_note_evidence",
            "grouping_ids",
            "display_citation_ids",
        },
    )
    authority = _object(
        document["authority_note_evidence"],
        {"rendered_value_fingerprint", "decision_ref", "supporting_evidence_refs"},
    )
    raw_evidence = document["evidence_refs"]
    raw_supporting = authority["supporting_evidence_refs"]
    if type(raw_evidence) is not list or type(raw_supporting) is not list:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    return HKCaseRecordTraceabilityBinding(
        _text(document["record_id"]),
        _text(document["serving_profile_id"]),
        _text(document["legal_item_id"]),
        _texts(document["official_version_ids"]),
        _texts(document["legal_location_ids"]),
        tuple(_decode_traceability_reference(item) for item in raw_evidence),
        AuthorityNoteEvidence(
            _exact_fingerprint(authority["rendered_value_fingerprint"]),
            _decode_traceability_reference(authority["decision_ref"]),
            tuple(_decode_traceability_reference(item) for item in raw_supporting),
        ),
        _texts(document["grouping_ids"]),
        _texts(document["display_citation_ids"]),
    )


def _decode_traceability_reference(value: JsonValue) -> TraceabilityReference:
    document = _object(value, {"ref_type", "ref_id", "fingerprint"})
    return TraceabilityReference(
        _text(document["ref_type"]),
        _text(document["ref_id"]),
        _exact_fingerprint(document["fingerprint"]),
    )


def _texts(value: JsonValue) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    result = tuple(item for item in value if type(item) is str)
    if result != tuple(sorted(set(result))):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    return result


def _integer(value: JsonValue) -> int:
    if type(value) is not int or value < 0:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    return value


def _optional_text(value: JsonValue) -> str | None:
    if value is None:
        return None
    return _text(value)


def _continuity(value: JsonValue) -> Literal["INITIAL", "REUSE", "SUCCESSOR"]:
    if value == "INITIAL":
        return "INITIAL"
    if value == "REUSE":
        return "REUSE"
    if value == "SUCCESSOR":
        return "SUCCESSOR"
    raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")


def _outcome_kind(
    value: JsonValue,
) -> Literal["EMITTED", "WAITING_ROOM", "EVIDENCE_ONLY", "HISTORICAL", "QUARANTINE"]:
    if value == "EMITTED":
        return "EMITTED"
    if value == "WAITING_ROOM":
        return "WAITING_ROOM"
    if value == "EVIDENCE_ONLY":
        return "EVIDENCE_ONLY"
    if value == "HISTORICAL":
        return "HISTORICAL"
    if value == "QUARANTINE":
        return "QUARANTINE"
    raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")


def _bytes_fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _reference_document(reference: ExactObjectReference) -> dict[str, JsonValue]:
    return {
        "vault": reference.vault.value,
        "logical_key": reference.logical_key,
        "version_id": reference.version_id,
        "fingerprint": reference.fingerprint,
        "byte_length": reference.byte_length,
    }


def _canonical_with_fingerprint(body: dict[str, JsonValue]) -> bytes:
    if "fingerprint" in body:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_MATERIALIZATION_INVALID")
    unsigned = canonicalize(checked_json_value(body))
    return canonicalize(checked_json_value({**body, "fingerprint": _bytes_fingerprint(unsigned)}))


def _safe_relative_path(value: str) -> Path:
    path = Path(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or value in {"legal-input.json", "package-policy.json"}
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_MATERIALIZATION_INVALID")
    return path


def _exact_fingerprint(value: JsonValue) -> str:
    if type(value) is not str or _FINGERPRINT.fullmatch(value) is None:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PROPOSAL_INVALID")
    return value


def _read_regular(path: Path, *, allow_empty: bool = False) -> bytes:
    try:
        if path.is_symlink() or not path.is_file():
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_NOT_READY")
        content = path.read_bytes()
    except AcceptanceLegalError:
        raise
    except OSError as error:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_NOT_READY") from error
    if (not content and not allow_empty) or len(content) > _MAX_ARTIFACT_BYTES:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_NOT_READY")
    return content


def _canonical_object(content: bytes) -> dict[str, JsonValue]:
    value = parse_json_bytes(content, max_bytes=_MAX_ARTIFACT_BYTES)
    if type(value) is not dict or canonicalize(value) != content:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PROPOSAL_INVALID")
    return value


def _read_package_policy(path: Path, operation_id: str) -> dict[str, JsonValue]:
    document = _canonical_object(_read_regular(path))
    expected = {
        "schema_id",
        "schema_version",
        "operation_id",
        "observation_cutoff",
        "title",
        "base_serving_state_fingerprint",
        "task7_proposal",
        "coverage_status",
        "promotion_manifest",
        "readiness",
        "estimated_cost_microunits",
        "review_statement",
        "fingerprint",
    }
    if frozenset(document) != frozenset(expected):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_INVALID")
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    if (
        document["schema_id"] != "asklegal.hk-v1-package-policy-input/v1"
        or document["schema_version"] != _VERSION
        or document["operation_id"] != operation_id
        or supplied != _bytes_fingerprint(canonicalize(checked_json_value(unsigned)))
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_INVALID")
    return document


def _build_review_package(
    request: dict[str, JsonValue],
    releases: TwoFamilyAcceptanceReleases,
    inputs: TwoFamilyAcceptanceInputs,
    policy: dict[str, JsonValue],
) -> tuple[dict[str, bytes], dict[str, bytes], bytes, bytes, bytes]:
    """Build all eleven members and three roots without inventing policy facts."""
    if policy["observation_cutoff"] != request["observation_cutoff"]:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_DRIFT")
    release_inventory = _release_inventory(releases)
    desired = compose_desired_state(
        _SCOPES,
        tuple(release_inventory[scope] for scope in _SCOPES),
        target_key=inputs.legislation_target_key,
        observation_cutoff=inputs.observation_cutoff,
    )
    legislation_results = releases.legislation_release_set.scope_results
    case_entries: tuple[TraceabilityEntry, ...] = ()
    profile_by_id: dict[str, ServingRecordProfile] = {}
    for result in legislation_results:
        prior = profile_by_id.setdefault(
            result.serving_profile.serving_record_profile_id,
            result.serving_profile,
        )
        if prior != result.serving_profile:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_DRIFT")
    if releases.case_release.records:
        if inputs.case_serving_profile is None:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
        case_entries = build_hk_case_record_traceability(
            releases.case_release,
            inputs.case_serving_profile,
            inputs.case_traceability_bindings,
        )
        prior = profile_by_id.setdefault(
            inputs.case_serving_profile.serving_record_profile_id,
            inputs.case_serving_profile,
        )
        if prior != inputs.case_serving_profile:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_DRIFT")
    elif inputs.case_serving_profile is not None or inputs.case_traceability_bindings:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_INPUT_INVALID")
    lookup = freeze_record_traceability_lookup(
        inputs.package_lookup_input,
        desired,
        (
            *case_entries,
            *(entry for result in legislation_results for entry in result.traceability_entries),
        ),
        tuple(profile_by_id.values()),
        inputs.package_lookup_shards,
    )
    coverage_document = _json_object(policy["coverage_status"])
    coverage_content = canonicalize(checked_json_value(coverage_document))
    promotion_document = _json_object(policy["promotion_manifest"])
    promotion_content = canonicalize(checked_json_value(promotion_document))
    promotion_fingerprint = _bytes_fingerprint(promotion_content)
    promotion_id = _stable_id("pmn", promotion_fingerprint)
    candidate_id = _text(promotion_document.get("candidate_serving_state_id"))
    candidate_fingerprint = _exact_fingerprint(
        promotion_document.get("candidate_serving_state_fingerprint")
    )
    base_id = _text(promotion_document.get("base_serving_state_id"))
    coverage_fingerprint = _bytes_fingerprint(coverage_content)
    if (
        promotion_document.get("desired_state_fingerprint") != desired.inventory_fingerprint
        or promotion_document.get("coverage_fingerprint") != coverage_fingerprint
        or promotion_document.get("rollback_serving_state_id") != base_id
        or coverage_document.get("observation_cutoff") != inputs.observation_cutoff
        or coverage_document.get("serving_state_id") != candidate_id
        or _coverage_scope_ids(coverage_document) != tuple(sorted(_SCOPES))
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_DRIFT")
    task7 = canonicalize(checked_json_value(_json_object(policy["task7_proposal"])))
    task7_document = _canonical_object(task7)
    task7_unsigned = dict(task7_document)
    task7_fingerprint = task7_unsigned.pop("fingerprint", None)
    if (
        task7_fingerprint != _bytes_fingerprint(canonicalize(checked_json_value(task7_unsigned)))
        or task7_document.get("observation_cutoff") != inputs.observation_cutoff
        or task7_document.get("embedding_profile_fingerprint")
        != promotion_document.get("embedding_profile_fingerprint")
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_DRIFT")
    readiness_input = _object(
        policy["readiness"],
        {
            "limitations",
            "model_evaluation_ref",
            "model_evaluation_fingerprint",
            "retrieval_evaluation_ref",
            "retrieval_evaluation_fingerprint",
            "model_profile_fingerprint",
            "embedding_profile_fingerprint",
            "serving_profile_fingerprint",
            "target_namespace",
            "backup_profile_fingerprint",
            "target_name",
            "native_backup_ref",
            "native_backup_fingerprint",
            "recovery_backup_ref",
            "recovery_backup_fingerprint",
            "rollback_state_id",
        },
    )
    _validate_readiness_policy(readiness_input, promotion_document, task7_document)
    readiness_body = _readiness_body(
        readiness_input,
        desired,
        release_inventory,
        _text(task7_fingerprint),
    )
    readiness_fingerprint = _bytes_fingerprint(canonicalize(checked_json_value(readiness_body)))
    readiness = canonicalize(
        checked_json_value(
            {
                "schema_id": "asklegal.hk-v1-review-readiness/v1",
                **readiness_body,
                "fingerprint": readiness_fingerprint,
            }
        )
    )
    contents = _proposal_member_contents(
        release_inventory,
        desired,
        lookup.manifest_bytes,
        coverage_content,
        promotion_content,
        promotion_document,
        coverage_fingerprint,
        policy,
    )
    shards = {shard.path: shard.content for shard in lookup.shards}
    artifacts = [
        {
            "byte_length": len(contents[role]),
            "fingerprint": _bytes_fingerprint(contents[role]),
            "media_type": "application/json",
            "path": PROPOSAL_ROLE_PATHS[role],
            "role": role,
        }
        for role in sorted(contents)
    ]
    evidence_fingerprint = _bytes_fingerprint(
        canonicalize(
            checked_json_value(
                {
                    "artifacts": artifacts,
                    "task7_proposal_fingerprint": task7_fingerprint,
                    "readiness_fingerprint": readiness_fingerprint,
                }
            )
        )
    )
    predicates = promotion_document.get("validity_predicates")
    if type(predicates) is not list:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_INVALID")
    package_unsigned = {
        "artifacts": artifacts,
        "base_serving_state_fingerprint": _exact_fingerprint(
            policy["base_serving_state_fingerprint"]
        ),
        "base_serving_state_id": base_id,
        "candidate_serving_state_fingerprint": candidate_fingerprint,
        "candidate_serving_state_id": candidate_id,
        "observation_cutoff": inputs.observation_cutoff,
        "promotion_manifest_fingerprint": promotion_fingerprint,
        "promotion_manifest_id": promotion_id,
        "proposal_id": _stable_id("ppk", promotion_fingerprint, evidence_fingerprint),
        "schema_id": "asklegal.hk-v1-local-review-package/v1",
        "title": _text(policy["title"]),
        "valid_from": _text(promotion_document.get("valid_from")),
        "valid_until": _text(promotion_document.get("valid_until")),
        "validity_predicates": [
            {"contract_id": item[0], "version": item[1], "fingerprint": item[2]}
            for item in predicates
            if type(item) is list and len(item) == 3
        ],
    }
    if len(package_unsigned["validity_predicates"]) != len(predicates):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_INVALID")
    package_fingerprint = _bytes_fingerprint(canonicalize(checked_json_value(package_unsigned)))
    package = canonicalize(
        checked_json_value({**package_unsigned, "package_fingerprint": package_fingerprint})
    )
    return contents, shards, task7, readiness, package


def _proposal_member_contents(
    releases: dict[str, CorpusRelease],
    desired: DesiredStateInventory,
    traceability: bytes,
    coverage: bytes,
    promotion: bytes,
    promotion_document: dict[str, JsonValue],
    coverage_fingerprint: str,
    policy: dict[str, JsonValue],
) -> dict[str, bytes]:
    state = desired
    records = state.records
    cutoff = state.observation_cutoff
    release_rows = [
        {
            "evidence_refs": list(releases[scope].evidence_refs),
            "observation_cutoff": releases[scope].observation_cutoff,
            "record_ids": [item.record.record_id for item in releases[scope].records],
            "release_id": releases[scope].release_id,
            "scope_id": scope,
            "validation_refs": list(releases[scope].validation_refs),
        }
        for scope in sorted(releases)
    ]
    all_refs = sorted(
        {
            ref
            for release in releases.values()
            for ref in (*release.evidence_refs, *release.validation_refs)
        }
    )
    batch_size = promotion_document.get("batch_size")
    estimated = policy["estimated_cost_microunits"]
    if type(batch_size) is not int or batch_size < 1 or type(estimated) is not int or estimated < 0:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_INVALID")
    raw: dict[str, object] = {
        "CHANGE_INVENTORY": {
            "additions": [item.record_id for item in records],
            "carried_forward": [],
            "observation_cutoff": cutoff,
            "replacements": [],
            "retirements": [],
            "unchanged": [],
            "withholdings": [],
        },
        "CORPUS_RELEASES": {"observation_cutoff": cutoff, "releases": release_rows},
        "COST_AND_CAPACITY": {
            "batch_size": batch_size,
            "embedding_profile_fingerprint": promotion_document.get(
                "embedding_profile_fingerprint"
            ),
            "estimated_cost_microunits": estimated,
            "record_count": len(records),
            "result": "PASS",
        },
        "DESIRED_STATE_INVENTORIES": {
            "inventory_fingerprint": state.inventory_fingerprint,
            "inventory_id": state.inventory_id,
            "observation_cutoff": cutoff,
            "records_fingerprint": state.records_fingerprint,
            "records": [
                {
                    "artifact_ref": item.record.artifact_ref,
                    "authority_note": item.record.authority_note,
                    "country": item.record.country,
                    "evidence_refs": list(item.record.evidence_refs),
                    "jurisdiction": item.record.jurisdiction,
                    "material_type": item.record.material_type,
                    "record_id": item.record_id,
                    "release_id": item.release_id,
                    "scope_id": item.scope_id,
                    "serving_payload_fingerprint": item.content_fingerprint,
                    "source": item.record.source,
                    "text": item.record.text,
                }
                for item in records
            ],
            "scope_releases": [list(item) for item in state.scope_releases],
            "target_key": state.target_key,
        },
        "RECOVERY_READINESS": {
            "candidate_serving_state_id": promotion_document.get("candidate_serving_state_id"),
            "predecessor_retained": True,
            "rollback_serving_state_id": promotion_document.get("rollback_serving_state_id"),
            "two_copy_backup_required": True,
        },
        "REVIEW_REPORT": {
            "coverage_fingerprint": coverage_fingerprint,
            "desired_state_fingerprint": state.inventory_fingerprint,
            "record_count": len(records),
            "result": "READY",
            "statement": _text(policy["review_statement"]),
        },
        "SERVING_STATE_DEFINITION": {
            "coverage_manifest_id": _stable_id(
                "csm",
                _text(promotion_document.get("candidate_serving_state_id")),
                coverage_fingerprint,
            ),
            "desired_state_inventory_id": state.inventory_id,
            "serving_state_fingerprint": promotion_document.get(
                "candidate_serving_state_fingerprint"
            ),
            "serving_state_id": promotion_document.get("candidate_serving_state_id"),
        },
        "VALIDATION": {
            "checks": [
                {"check_id": check, "evidence_refs": all_refs, "result": "PASS"}
                for check in (
                    "EVIDENCE_BOUND",
                    "SCOPE_COMPLETE",
                    "TRACEABILITY_COMPLETE",
                )
            ],
            "result": "PASS",
        },
    }
    contents = {role: canonicalize(checked_json_value(value)) for role, value in raw.items()}
    contents["COVERAGE_STATUS"] = coverage
    contents["PROMOTION_MANIFEST"] = promotion
    contents["RECORD_TRACEABILITY"] = traceability
    return contents


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    if type(value) is not dict:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_INVALID")
    return value


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


def _coverage_scope_ids(document: dict[str, JsonValue]) -> tuple[str, ...]:
    raw = document.get("scopes")
    if type(raw) is not list:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_INVALID")
    result: list[str] = []
    for item in raw:
        if type(item) is not dict:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_INVALID")
        result.append(_text(item.get("scope_id")))
    return tuple(result)


def _validate_readiness_policy(
    readiness: dict[str, JsonValue],
    promotion: dict[str, JsonValue],
    task7: dict[str, JsonValue],
) -> None:
    for field in (
        "model_evaluation_fingerprint",
        "retrieval_evaluation_fingerprint",
        "model_profile_fingerprint",
        "embedding_profile_fingerprint",
        "serving_profile_fingerprint",
        "backup_profile_fingerprint",
        "native_backup_fingerprint",
        "recovery_backup_fingerprint",
    ):
        _exact_fingerprint(readiness[field])
    for field in (
        "model_evaluation_ref",
        "retrieval_evaluation_ref",
        "target_namespace",
        "target_name",
        "native_backup_ref",
        "recovery_backup_ref",
        "rollback_state_id",
    ):
        _text(readiness[field])
    limitations = readiness["limitations"]
    if (
        type(limitations) is not list
        or not limitations
        or any(type(item) is not str or not item for item in limitations)
        or readiness["model_profile_fingerprint"] != task7.get("model_profile_fingerprint")
        or readiness["embedding_profile_fingerprint"]
        != promotion.get("embedding_profile_fingerprint")
        or readiness["embedding_profile_fingerprint"] != task7.get("embedding_profile_fingerprint")
        or readiness["rollback_state_id"] != promotion.get("rollback_serving_state_id")
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_DRIFT")
    predicates = promotion.get("validity_predicates")
    required = {
        ("HK_V1_MODEL_EVALUATION", _text(readiness["model_evaluation_fingerprint"])),
        (
            "HK_V1_RETRIEVAL_EVALUATION",
            _text(readiness["retrieval_evaluation_fingerprint"]),
        ),
        ("HK_V1_NATIVE_BACKUP", _text(readiness["native_backup_fingerprint"])),
        ("HK_V1_RECOVERY_BACKUP", _text(readiness["recovery_backup_fingerprint"])),
    }
    if type(predicates) is not list:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_INVALID")
    observed = {
        (item[0], item[2])
        for item in predicates
        if type(item) is list and len(item) == 3 and type(item[0]) is str and type(item[2]) is str
    }
    if not required.issubset(observed):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_POLICY_DRIFT")


def _readiness_body(
    policy: dict[str, JsonValue],
    desired: DesiredStateInventory,
    releases: dict[str, CorpusRelease],
    task7_fingerprint: str,
) -> dict[str, object]:
    zero_scopes = tuple(sorted(scope for scope, release in releases.items() if not release.records))
    return {
        "backup_profile_fingerprint": policy["backup_profile_fingerprint"],
        "embedding_profile_fingerprint": policy["embedding_profile_fingerprint"],
        "limitations": policy["limitations"],
        "model_evaluation_ref": policy["model_evaluation_ref"],
        "model_profile_fingerprint": policy["model_profile_fingerprint"],
        "native_backup_ref": policy["native_backup_ref"],
        "proposal_fingerprint": task7_fingerprint,
        "recovery_backup_ref": policy["recovery_backup_ref"],
        "retrieval_evaluation_ref": policy["retrieval_evaluation_ref"],
        "retryable_count": 0,
        "rollback_state_id": policy["rollback_state_id"],
        "scope_dispositions": [
            {
                "result": "NO_CHANGE" if scope in zero_scopes else "COMPLETE",
                "retryable_count": 0,
                "scope_id": scope,
            }
            for scope in _SCOPES
        ],
        "serving_profile_fingerprint": policy["serving_profile_fingerprint"],
        "target_members": [
            {
                "material_family": ("CASES" if item.scope_id == _SCOPES[0] else "LEGISLATION"),
                "record_id": item.record_id,
                "scope_id": item.scope_id,
            }
            for item in desired.records
        ],
        "target_name": policy["target_name"],
        "target_namespace": policy["target_namespace"],
        "zero_record_scope_ids": list(zero_scopes),
    }


def _release_inventory(
    releases: TwoFamilyAcceptanceReleases,
) -> dict[str, CorpusRelease]:
    return {
        "HK-CASE-BINDING-POST-1997": releases.case_release,
        **{
            result.legislation_scope_code: result.release
            for result in releases.legislation_release_set.scope_results
        },
    }


def _validate_release_member(content: bytes, releases: TwoFamilyAcceptanceReleases) -> None:
    document = _canonical_object(content)
    raw_releases = document.get("releases")
    if (
        document.get("observation_cutoff") != releases.case_release.observation_cutoff
        or type(raw_releases) is not list
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PROPOSAL_INVALID")
    expected = _release_inventory(releases)
    observed: set[str] = set()
    for raw in raw_releases:
        item = _object(
            raw,
            {
                "evidence_refs",
                "observation_cutoff",
                "record_ids",
                "release_id",
                "scope_id",
                "validation_refs",
            },
        )
        scope = _text(item["scope_id"])
        release = expected.get(scope)
        if (
            release is None
            or scope in observed
            or item["observation_cutoff"] != release.observation_cutoff
            or item["release_id"] != release.release_id
            or item["record_ids"] != [entry.record.record_id for entry in release.records]
            or item["evidence_refs"] != list(release.evidence_refs)
            or item["validation_refs"] != list(release.validation_refs)
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PROPOSAL_INVALID")
        observed.add(scope)
    if observed != set(_SCOPES):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PROPOSAL_INVALID")


def _validate_root_bindings(
    task7_content: bytes,
    readiness_content: bytes,
    package: dict[str, JsonValue],
    releases: TwoFamilyAcceptanceReleases,
) -> None:
    task7 = _canonical_object(task7_content)
    readiness = _canonical_object(readiness_content)
    task7_body = dict(task7)
    task7_fingerprint = task7_body.pop("fingerprint", None)
    readiness_body = dict(readiness)
    readiness_fingerprint = readiness_body.pop("fingerprint", None)
    readiness_body.pop("schema_id", None)
    zero_scopes = sorted(
        scope for scope, release in _release_inventory(releases).items() if not release.records
    )
    if (
        task7.get("schema_id") != "asklegal.hk-v1-two-family-proposal-manifest/v1"
        or task7.get("observation_cutoff") != package["observation_cutoff"]
        or task7_fingerprint != _bytes_fingerprint(canonicalize(checked_json_value(task7_body)))
        or readiness.get("schema_id") != "asklegal.hk-v1-review-readiness/v1"
        or readiness.get("proposal_fingerprint") != task7_fingerprint
        or readiness.get("zero_record_scope_ids") != zero_scopes
        or readiness_fingerprint
        != _bytes_fingerprint(canonicalize(checked_json_value(readiness_body)))
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PROPOSAL_INVALID")


def _atomic_store(path: Path, content: bytes) -> None:
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink() or path.is_symlink():
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_REVIEW_ROOT_INVALID")
        temporary = path.with_name(f".{path.name}.{sha256(content).hexdigest()}.tmp")
        if temporary.exists():
            if temporary.is_symlink() or temporary.read_bytes() != content:
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_REVIEW_ROOT_INVALID")
        else:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        temporary.replace(path)
        if path.is_symlink() or path.read_bytes() != content:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PROPOSAL_READBACK_FAILED")
    except AcceptanceLegalError:
        raise
    except OSError as error:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_REVIEW_ROOT_INVALID") from error


def _prepare_review_generation(
    review_root: Path,
    package_fingerprint: str,
    contents: dict[str, bytes],
    shards: dict[str, bytes],
    task7: bytes,
    readiness: bytes,
    package: bytes,
) -> Path:
    """Create-or-match a complete unpublished generation directory."""
    generation_name = package_fingerprint.removeprefix("sha256:")
    generations = review_root / ".generations"
    generation = generations / generation_name
    expected = {
        **{PROPOSAL_ROLE_PATHS[role]: contents[role] for role in sorted(contents)},
        **{f"record-traceability/{path}": shards[path] for path in sorted(shards)},
        _ROOT_FILES[0]: task7,
        _ROOT_FILES[1]: readiness,
        _ROOT_FILES[2]: package,
    }
    if generation.is_dir() and not generation.is_symlink():
        for relative, content in expected.items():
            path = generation.joinpath(*relative.split("/"))
            if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PROPOSAL_DRIFT")
        return generation
    generations.mkdir(mode=0o700, parents=True, exist_ok=True)
    if generations.is_symlink() or generation.exists():
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_REVIEW_ROOT_INVALID")
    temporary = generations / f".{generation_name}.{os.getpid()}.tmp"
    if temporary.exists() and (temporary.is_symlink() or not temporary.is_dir()):
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_REVIEW_ROOT_INVALID")
    temporary.mkdir(mode=0o700, exist_ok=True)
    for relative, content in expected.items():
        _atomic_store(temporary.joinpath(*relative.split("/")), content)
    try:
        temporary.replace(generation)
    except FileExistsError:
        if temporary.is_dir():
            for relative, content in expected.items():
                path = generation.joinpath(*relative.split("/"))
                if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                    raise AcceptanceLegalError(
                        "LEGAL_PROCESSING_ACCEPTANCE_PROPOSAL_DRIFT"
                    ) from None
    return generation


def _publish_review_generation(review_root: Path, generation: Path) -> None:
    """Atomically point Review at one already complete immutable generation."""
    current = review_root / "current"
    temporary = review_root / f".current.{os.getpid()}.tmp"
    relative = generation.relative_to(review_root)
    try:
        review_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if temporary.exists() or temporary.is_symlink():
            if not temporary.is_symlink() or temporary.readlink() != relative:
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_REVIEW_ROOT_INVALID")
        else:
            temporary.symlink_to(relative)
        temporary.replace(current)
        if not current.is_symlink() or current.resolve(strict=True) != generation.resolve(
            strict=True
        ):
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PROPOSAL_READBACK_FAILED")
    except AcceptanceLegalError:
        raise
    except OSError as error:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_REVIEW_ROOT_INVALID") from error


def _atomic_create_or_match(path: Path, content: bytes) -> None:
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.parent.is_symlink() or path.is_symlink():
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_MATERIALIZATION_INVALID")
        if path.exists():
            if not path.is_file() or path.read_bytes() != content:
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_MATERIALIZATION_DRIFT")
            return
        temporary = path.with_name(f".{path.name}.{sha256(content).hexdigest()}.tmp")
        if temporary.exists():
            if temporary.is_symlink() or temporary.read_bytes() != content:
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_MATERIALIZATION_DRIFT")
        else:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        os.link(temporary, path)
        temporary.unlink()
        if path.read_bytes() != content:
            raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_MATERIALIZATION_DRIFT")
    except AcceptanceLegalError:
        raise
    except FileExistsError:
        if not path.is_file() or path.read_bytes() != content:
            raise AcceptanceLegalError(
                "LEGAL_PROCESSING_ACCEPTANCE_MATERIALIZATION_DRIFT"
            ) from None
    except OSError as error:
        raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_MATERIALIZATION_INVALID") from error
