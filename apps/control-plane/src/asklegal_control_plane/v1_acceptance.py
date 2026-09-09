"""Deterministic Task 10 Control acceptance-cycle coordination."""

from __future__ import annotations

import os
import re
from collections.abc import Generator
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path, PurePath
from typing import TYPE_CHECKING, Never, Protocol, TypeIs

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_durable_task import OrchestrationStatus, V1SchedulerSettings
from asklegal_evidence_vault import ExactObjectReference, VaultName
from asklegal_reporting import (
    FamilyAcquisitionCoverage,
    HongKongV1CoverageMatrix,
    HongKongV1DueCycleInstruction,
    is_hk_v1_coverage_matrix_policy_approved,
    parse_hk_v1_cases_acquisition_manifest,
    parse_hk_v1_legislation_acquisition_manifest,
)

from asklegal_control_plane.v1_pipeline import rebuild_hk_v1_due_handoff

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from asklegal_durable_task import ActivityContext, OrchestrationContext, Task

ACCEPTANCE_ACQUISITION_ACTIVITY = "start_hk_v1_acceptance_acquisition"
ACCEPTANCE_LEGAL_ACTIVITY = "start_hk_v1_acceptance_legal_processing"
DUE_ACCEPTANCE_ACTIVITY = "continue_hk_v1_due_acceptance"
_LEGAL_ORCHESTRATION = "run_hk_v1_acceptance_legal_processing"
_VERSION = "1.0.0"
_FINGERPRINT_LENGTH = 71
_MAX_MANIFEST_BYTES = 4_194_304
_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:Z|\+00:00|\+08:00)\Z"
)
_FAMILIES = ("CASES", "LEGISLATION")
_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)
_REQUEST_FIELDS = {
    "schema_id",
    "schema_version",
    "kind",
    "cutoff_key",
    "observation_cutoff",
    "cases_manifest_fingerprint",
    "legislation_manifest_fingerprint",
    "authentic_changed_families",
    "family_acquisition_evidence",
    "cutoff_selection_fingerprint",
    "matrix_revision",
    "matrix_fingerprint",
    "families",
    "scope_ids",
    "command_id",
    "operation_id",
    "command_fingerprint",
}
_ACQUISITION_FIELDS = {
    "schema_id",
    "schema_version",
    "operation_id",
    "command_fingerprint",
    "observation_cutoff",
    "scope_ids",
    "family_manifests",
    "result",
}
_FAMILY_FIELDS = {
    "material_family",
    "manifest_fingerprint",
    "result",
    "retryable_count",
    "rejected_count",
}
_LEGAL_FIELDS = {
    "schema_id",
    "schema_version",
    "operation_id",
    "command_fingerprint",
    "observation_cutoff",
    "families",
    "scope_results",
    "proposal_reference",
    "blocker_codes",
    "result",
}
_PROPOSAL_FIELDS = {"vault", "logical_key", "version_id", "fingerprint", "byte_length"}
_CYCLE_RESULT_FIELDS = {
    "schema_id",
    "schema_version",
    "kind",
    "operation_id",
    "command_fingerprint",
    "observation_cutoff",
    "families",
    "scope_ids",
    "result",
    "blocker_codes",
    "proposal_reference",
}
_FAMILY_EVIDENCE_FIELDS = {
    "schema_id",
    "schema_version",
    "root_instruction",
    "root_plan_fingerprint",
    "children",
}
_FAMILY_CHILD_FIELDS = {
    "source_family",
    "cycle_id",
    "journal_ref",
    "manifest_fingerprint",
    "journal_head_fingerprint",
    "result",
    "manifest_reference",
}
_ACCEPTANCE_FAMILY_EVIDENCE_FIELDS = {
    "schema_id",
    "schema_version",
    "root_cycle_id",
    "root_plan_fingerprint",
    "evidence_reference",
    "children",
}
_DUE_ACTIVITY_FIELDS = {"instruction", "due_result"}
_LEGAL_TIMEOUT_SECONDS = 900


class _VaultReader(Protocol):
    def read_exact(self, reference: ExactObjectReference) -> bytes: ...


class AcceptanceCoordinatorError(ValueError):
    """One closed acceptance request or stage-result failure."""


def _fail(code: str) -> Never:
    raise AcceptanceCoordinatorError(code)


class UnavailableAcceptanceActivities:
    """Fail-visible production boundaries until exact downstream adapters are composed."""

    def start_hk_v1_acceptance_acquisition(
        self, _context: ActivityContext, payload: object
    ) -> object:
        """Reject before claiming an acquisition resume that cannot be identified exactly."""
        _request(payload)
        _fail("HK_V1_ACCEPTANCE_ACQUISITION_NOT_READY")

    def start_hk_v1_acceptance_legal_processing(
        self, _context: ActivityContext, payload: object
    ) -> dict[str, JsonValue]:
        """Return an exact non-success while the legal positive adapter is unavailable."""
        request, _acquisition_result, _family_evidence = _legal_activity_payload(payload)
        return {
            "schema_id": "asklegal.hk-v1.acceptance-legal-result",
            "schema_version": _VERSION,
            "operation_id": _text(request["operation_id"], "ACCEPTANCE_REQUEST_INVALID"),
            "command_fingerprint": _fingerprint(
                request["command_fingerprint"], "ACCEPTANCE_REQUEST_INVALID"
            ),
            "observation_cutoff": _text(
                request["observation_cutoff"], "ACCEPTANCE_REQUEST_INVALID"
            ),
            "families": list(_FAMILIES),
            "scope_results": [],
            "proposal_reference": None,
            "blocker_codes": ["LEGAL_PROCESSING_ACCEPTANCE_ADAPTER_UNAVAILABLE"],
            "result": "NOT_READY",
        }


class LocalAcceptanceActivities(UnavailableAcceptanceActivities):
    """Reuse the exact frozen local manifests selected for one acceptance cycle."""

    def __init__(
        self,
        configuration: AcceptanceConfiguration,
        matrix: HongKongV1CoverageMatrix,
        primary_vault: _VaultReader | None = None,
    ) -> None:
        """Bind the retained cutoff root and currently approved Matrix exactly once."""
        if (
            type(configuration) is not AcceptanceConfiguration
            or type(matrix) is not HongKongV1CoverageMatrix
            or not is_hk_v1_coverage_matrix_policy_approved(matrix)
        ):
            _fail("HK_V1_ACCEPTANCE_CONFIGURATION_INVALID")
        self._configuration = configuration
        self._matrix = matrix
        self._primary_vault = primary_vault

    def start_hk_v1_acceptance_acquisition(
        self, _context: ActivityContext, payload: object
    ) -> dict[str, JsonValue]:
        """Read and revalidate the selected pair without recapturing either source."""
        request = _request(payload)
        if (
            request["matrix_revision"] != self._matrix.revision
            or request["matrix_fingerprint"] != self._matrix.fingerprint
        ):
            _fail("ACCEPTANCE_REQUEST_INVALID")
        label = _text(request["cutoff_key"], "ACCEPTANCE_REQUEST_INVALID")
        cases, cases_result = _retained_manifest(
            self._configuration.retained_root,
            label,
            "cases-acquisition-manifest.json",
            parse_hk_v1_cases_acquisition_manifest,
        )
        legislation, legislation_result = _retained_manifest(
            self._configuration.retained_root,
            label,
            "legislation-acquisition-manifest.json",
            parse_hk_v1_legislation_acquisition_manifest,
        )
        _verify_selected_manifest(request, cases, "CASES")
        _verify_selected_manifest(request, legislation, "LEGISLATION")
        result = "NO_CHANGE" if cases_result == legislation_result == "NO_CHANGE" else "COMPLETE"
        document: dict[str, JsonValue] = {
            "schema_id": "asklegal.hk-v1.acceptance-acquisition-result",
            "schema_version": _VERSION,
            "operation_id": request["operation_id"],
            "command_fingerprint": request["command_fingerprint"],
            "observation_cutoff": request["observation_cutoff"],
            "scope_ids": list(_SCOPES),
            "family_manifests": [
                _family_result(cases, cases_result),
                _family_result(legislation, legislation_result),
            ],
            "result": result,
        }
        return document

    def start_hk_v1_acceptance_legal_processing(
        self, _context: ActivityContext, payload: object
    ) -> dict[str, JsonValue]:
        """Dispatch the exact accepted handoff onto Legal's separately owned hub."""
        request, acquisition, family_evidence = _legal_activity_payload(payload)
        return _dispatch_legal_processing(request, acquisition, family_evidence)

    def continue_hk_v1_due_acceptance(
        self, _context: ActivityContext, payload: object
    ) -> dict[str, object]:
        """Convert one verified successful due result into a replay-stable acceptance result."""
        if self._primary_vault is None:
            _fail("HK_V1_DUE_ACCEPTANCE_NOT_READY")
        root = _object(payload, _DUE_ACTIVITY_FIELDS, "HK_V1_DUE_ACCEPTANCE_INVALID")
        instruction, due_result = rebuild_hk_v1_due_handoff(root["instruction"], root["due_result"])
        if (
            due_result["accounting_complete"] is not True
            or due_result["release_blocking"] is not False
            or due_result["disposition"] != "COMPLETE"
        ):
            _fail("HK_V1_DUE_ACCEPTANCE_INVALID")
        evidence = _read_due_family_evidence(
            self._primary_vault,
            due_result,
            instruction,
        )
        request = _ordinary_request(instruction, due_result, evidence, self._matrix)
        acquisition = _ordinary_acquisition(request, evidence)
        if acquisition["result"] == "NO_CHANGE":
            return _result(request, "NO_CHANGE", (), None)
        legal = _legal(
            _dispatch_legal_processing(
                request,
                acquisition,
                _acceptance_family_evidence(due_result, evidence),
            ),
            request,
        )
        blockers = _texts(legal["blocker_codes"], "ACCEPTANCE_LEGAL_RESULT_INVALID")
        if legal["result"] == "NOT_READY":
            return _result(request, "NOT_READY", blockers, None)
        proposal = _object(
            legal["proposal_reference"], _PROPOSAL_FIELDS, "ACCEPTANCE_LEGAL_RESULT_INVALID"
        )
        return _result(request, "PROPOSAL_READY", (), proposal)


class AcceptanceConfiguration:
    """Explicit read-only local root holding the selector's frozen T1/T2 pairs."""

    def __init__(self, retained_root: Path) -> None:
        """Reject inferred or lexically ambiguous local authorities."""
        code = "HK_V1_ACCEPTANCE_CONFIGURATION_INVALID"
        lexical = PurePath(retained_root)
        if (
            not retained_root.is_absolute()
            or retained_root == Path(retained_root.anchor)
            or any(part in {"", ".", ".."} for part in lexical.parts[1:])
        ):
            _fail(code)
        try:
            if (
                retained_root.is_symlink()
                or not retained_root.is_dir()
                or retained_root.resolve(strict=True) != retained_root
                or not os.access(retained_root, os.R_OK | os.X_OK)
            ):
                _fail(code)
        except AcceptanceCoordinatorError:
            raise
        except OSError as error:
            raise AcceptanceCoordinatorError(code) from error
        self.retained_root = retained_root

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> AcceptanceConfiguration:
        """Require one explicit mounted cutoff root; never infer a production fallback."""
        value = environment.get("ASKLEGAL_HK_V1_ACCEPTANCE_CUTOFF_ROOT")
        if value is None or not value or value != value.strip():
            _fail("HK_V1_ACCEPTANCE_CONFIGURATION_INVALID")
        return cls(Path(value))


def _read_due_family_evidence(
    vault: _VaultReader,
    due_result: dict[str, object],
    instruction: HongKongV1DueCycleInstruction,
) -> dict[str, JsonValue]:
    code = "HK_V1_DUE_ACCEPTANCE_INVALID"
    binding = _object(
        due_result["family_acquisition_evidence"],
        {"cycle_id", "evidence_reference", "evidence_created"},
        code,
    )
    if binding["cycle_id"] != instruction.cycle_id or type(binding["evidence_created"]) is not bool:
        _fail(code)
    raw_reference = _object(binding["evidence_reference"], _PROPOSAL_FIELDS, code)
    document = _read_due_evidence_document(vault, raw_reference, code)
    if (
        document["schema_id"] != "asklegal.hk-v1.scheduled-family-acquisitions"
        or document["schema_version"] != _VERSION
        or document["root_plan_fingerprint"] != due_result["plan_fingerprint"]
        or document["root_instruction"] != _due_instruction_document(instruction)
    ):
        _fail(code)
    children = document["children"]
    if type(children) is not list or len(children) != len(_FAMILIES):
        _fail(code)
    for expected_family, raw_child in zip(_FAMILIES, children, strict=True):
        child = _object(
            raw_child,
            _FAMILY_CHILD_FIELDS,
            code,
        )
        cycle_id = _text(child["cycle_id"], code)
        if (
            child["source_family"] != expected_family
            or child["journal_ref"] != f"acquisition-journals/{cycle_id}"
            or not _fingerprint(child["manifest_fingerprint"], code)
            or not _fingerprint(child["journal_head_fingerprint"], code)
            or child["result"] not in {"COMPLETE", "NO_CHANGE"}
        ):
            _fail(code)
        _verify_due_child_manifest(vault, child, instruction, expected_family, code)
    return document


def _read_due_evidence_document(
    vault: _VaultReader, raw_reference: dict[str, JsonValue], code: str
) -> dict[str, JsonValue]:
    try:
        reference = ExactObjectReference(
            VaultName.PRIMARY,
            _text(raw_reference["logical_key"], code),
            _text(raw_reference["version_id"], code),
            _fingerprint(raw_reference["fingerprint"], code),
            _nonnegative_integer(raw_reference["byte_length"], code),
        )
        if raw_reference["vault"] != VaultName.PRIMARY.value:
            _fail(code)
        content = vault.read_exact(reference)
        if (
            type(content) is not bytes
            or len(content) != reference.byte_length
            or f"sha256:{sha256(content).hexdigest()}" != reference.fingerprint
        ):
            _fail(code)
        document = _object(
            parse_json_bytes(content, max_bytes=_MAX_MANIFEST_BYTES),
            _FAMILY_EVIDENCE_FIELDS,
            code,
        )
        if canonicalize(document) != content:
            _fail(code)
    except AcceptanceCoordinatorError:
        raise
    except Exception as error:
        raise AcceptanceCoordinatorError(code) from error
    return document


def _verify_due_child_manifest(
    vault: _VaultReader,
    child: dict[str, JsonValue],
    instruction: HongKongV1DueCycleInstruction,
    family: str,
    code: str,
) -> None:
    raw_reference = _object(child["manifest_reference"], _PROPOSAL_FIELDS, code)
    try:
        reference = ExactObjectReference(
            VaultName.PRIMARY,
            _text(raw_reference["logical_key"], code),
            _text(raw_reference["version_id"], code),
            _fingerprint(raw_reference["fingerprint"], code),
            _nonnegative_integer(raw_reference["byte_length"], code),
        )
        if raw_reference[
            "vault"
        ] != VaultName.PRIMARY.value or reference.logical_key != _due_family_manifest_key(
            instruction.cycle_id, family
        ):
            _fail(code)
        content = vault.read_exact(reference)
        if (
            type(content) is not bytes
            or len(content) != reference.byte_length
            or f"sha256:{sha256(content).hexdigest()}" != reference.fingerprint
        ):
            _fail(code)
        parser = (
            parse_hk_v1_cases_acquisition_manifest
            if family == "CASES"
            else parse_hk_v1_legislation_acquisition_manifest
        )
        manifest = parser(content)
        document = parse_json_bytes(content, max_bytes=_MAX_MANIFEST_BYTES)
    except AcceptanceCoordinatorError:
        raise
    except Exception as error:
        raise AcceptanceCoordinatorError(code) from error
    if (
        manifest.material_family != family
        or manifest.cycle_id != child["cycle_id"]
        or manifest.observation_cutoff != instruction.observation_cutoff
        or manifest.manifest_fingerprint != child["manifest_fingerprint"]
        or manifest.journal_head_fingerprint != child["journal_head_fingerprint"]
        or type(document) is not dict
        or document.get("result") != child["result"]
    ):
        _fail(code)


def _due_family_manifest_key(root_cycle_id: str, source_family: str) -> str:
    if source_family not in _FAMILIES:
        _fail("HK_V1_DUE_ACCEPTANCE_INVALID")
    return (
        f"poc/report/hk-v1-due-cycle/{root_cycle_id}/family-manifests/{source_family.lower()}.json"
    )


def _due_instruction_document(
    instruction: HongKongV1DueCycleInstruction,
) -> dict[str, JsonValue]:
    return {
        "cycle_id": instruction.cycle_id,
        "cycle_kind": instruction.cycle_kind.value,
        "scheduled_at": instruction.scheduled_at,
        "observation_cutoff": instruction.observation_cutoff,
        "matrix_revision": instruction.matrix_revision,
        "matrix_fingerprint": instruction.matrix_fingerprint,
    }


def _ordinary_request(
    instruction: HongKongV1DueCycleInstruction,
    due_result: dict[str, object],
    evidence: dict[str, JsonValue],
    matrix: HongKongV1CoverageMatrix,
) -> dict[str, JsonValue]:
    code = "HK_V1_DUE_ACCEPTANCE_INVALID"
    children = evidence["children"]
    if type(children) is not list:
        _fail(code)
    family_fingerprints: dict[str, str] = {}
    changed: list[str] = []
    for raw in children:
        child = _object(
            raw,
            _FAMILY_CHILD_FIELDS,
            code,
        )
        family = _text(child["source_family"], code)
        family_fingerprints[family] = _fingerprint(child["manifest_fingerprint"], code)
        if child["result"] == "COMPLETE":
            changed.append(family)
    evidence_binding = _object(
        due_result["family_acquisition_evidence"],
        {"cycle_id", "evidence_reference", "evidence_created"},
        code,
    )
    reference = _object(evidence_binding["evidence_reference"], _PROPOSAL_FIELDS, code)
    family_evidence = _acceptance_family_evidence(due_result, evidence)
    identity: dict[str, JsonValue] = {
        "kind": "UPDATE",
        "cutoff_key": "t2",
        "observation_cutoff": instruction.observation_cutoff,
        "cases_manifest_fingerprint": family_fingerprints["CASES"],
        "legislation_manifest_fingerprint": family_fingerprints["LEGISLATION"],
        "authentic_changed_families": checked_json_value(sorted(changed)),
        "family_acquisition_evidence": family_evidence,
        "cutoff_selection_fingerprint": _fingerprint(reference["fingerprint"], code),
        "matrix_revision": matrix.revision,
        "matrix_fingerprint": matrix.fingerprint,
        "families": list(_FAMILIES),
        "scope_ids": list(_SCOPES),
    }
    identifier = sha256(canonicalize(identity)).hexdigest()[:48]
    command_id = f"cmd_{identifier}"
    operation_id = f"cyc_{identifier}"
    command_identity: dict[str, JsonValue] = {
        **identity,
        "command_id": command_id,
        "operation_id": operation_id,
    }
    request: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-v1.acceptance-cycle-request",
        "schema_version": _VERSION,
        **command_identity,
        "command_fingerprint": f"sha256:{sha256(canonicalize(command_identity)).hexdigest()}",
    }
    return _request(request)


def _ordinary_acquisition(
    request: dict[str, JsonValue], evidence: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    code = "HK_V1_DUE_ACCEPTANCE_INVALID"
    raw_children = evidence["children"]
    if type(raw_children) is not list:
        _fail(code)
    families: list[JsonValue] = []
    statuses: list[str] = []
    for raw in raw_children:
        child = _object(
            raw,
            _FAMILY_CHILD_FIELDS,
            code,
        )
        status = _text(child["result"], code)
        statuses.append(status)
        families.append(
            {
                "material_family": child["source_family"],
                "manifest_fingerprint": child["manifest_fingerprint"],
                "result": status,
                "retryable_count": 0,
                "rejected_count": 0,
            }
        )
    document: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-v1.acceptance-acquisition-result",
        "schema_version": _VERSION,
        "operation_id": request["operation_id"],
        "command_fingerprint": request["command_fingerprint"],
        "observation_cutoff": request["observation_cutoff"],
        "scope_ids": list(_SCOPES),
        "family_manifests": families,
        "result": "NO_CHANGE" if all(item == "NO_CHANGE" for item in statuses) else "COMPLETE",
    }
    return _acquisition(document, request)


def _acceptance_family_evidence(
    due_result: dict[str, object], evidence: dict[str, JsonValue]
) -> dict[str, JsonValue]:
    code = "HK_V1_DUE_ACCEPTANCE_INVALID"
    binding = _object(
        due_result["family_acquisition_evidence"],
        {"cycle_id", "evidence_reference", "evidence_created"},
        code,
    )
    reference = _object(binding["evidence_reference"], _PROPOSAL_FIELDS, code)
    children = evidence["children"]
    if type(children) is not list:
        _fail(code)
    return {
        "schema_id": "asklegal.hk-v1.acceptance-family-acquisition-evidence",
        "schema_version": _VERSION,
        "root_cycle_id": binding["cycle_id"],
        "root_plan_fingerprint": evidence["root_plan_fingerprint"],
        "evidence_reference": reference,
        "children": children,
    }


def _dispatch_legal_processing(
    request: dict[str, JsonValue],
    acquisition: dict[str, JsonValue],
    family_acquisition_evidence: dict[str, JsonValue] | None = None,
) -> dict[str, JsonValue]:
    code = "HK_V1_ACCEPTANCE_LEGAL_DISPATCH_INVALID"
    payload: dict[str, JsonValue] = {"request": request, "acquisition": acquisition}
    if family_acquisition_evidence is not None:
        payload["family_acquisition_evidence"] = family_acquisition_evidence
    try:
        settings = V1SchedulerSettings.for_application("LEGAL_PROCESSING_WORKER")
        if settings.scheduler_service != "dts-general" or settings.task_hub != "legal-processing":
            _fail(code)
        client = settings.create_client(default_version=_VERSION)
        operation_id = _text(request["operation_id"], code)
        state = client.get_orchestration_state(operation_id)
        if state is None:
            instance_id = client.schedule_new_orchestration(
                _LEGAL_ORCHESTRATION,
                input=payload,
                instance_id=operation_id,
                version=_VERSION,
            )
            if type(instance_id) is not str or instance_id != operation_id:
                _fail(code)
        state = client.wait_for_orchestration_completion(
            operation_id, timeout=_LEGAL_TIMEOUT_SECONDS
        )
        if (
            state is None
            or state.runtime_status is not OrchestrationStatus.COMPLETED
            or type(state.serialized_output) is not str
            or not state.serialized_output
        ):
            _fail(code)
        value = parse_json_bytes(
            state.serialized_output.encode("utf-8"), max_bytes=_MAX_MANIFEST_BYTES
        )
        return _legal(value, request)
    except AcceptanceCoordinatorError:
        raise
    except Exception as error:
        raise AcceptanceCoordinatorError(code) from error


def _retained_manifest(
    root: Path,
    label: str,
    filename: str,
    parser: Callable[[bytes], FamilyAcquisitionCoverage],
) -> tuple[FamilyAcquisitionCoverage, str]:
    code = "HK_V1_ACCEPTANCE_ACQUISITION_NOT_READY"
    path = root / label / filename
    try:
        if (
            root.is_symlink()
            or not root.is_dir()
            or root.resolve(strict=True) != root
            or path.is_symlink()
            or not path.is_file()
            or path.resolve(strict=True) != path
            or not path.is_relative_to(root)
        ):
            _fail(code)
        content = path.read_bytes()
        if not content or len(content) > _MAX_MANIFEST_BYTES:
            _fail(code)
        projection = parser(content)
        document = parse_json_bytes(content, max_bytes=_MAX_MANIFEST_BYTES)
        if type(document) is not dict or document.get("result") not in {
            "COMPLETE",
            "NO_CHANGE",
        }:
            _fail(code)
        result = _text(document["result"], code)
    except AcceptanceCoordinatorError:
        raise
    except (OSError, ValueError) as error:
        raise AcceptanceCoordinatorError(code) from error
    return projection, result


def _verify_selected_manifest(
    request: dict[str, JsonValue],
    manifest: FamilyAcquisitionCoverage,
    family: str,
) -> None:
    expected_fingerprint = request[
        "cases_manifest_fingerprint" if family == "CASES" else "legislation_manifest_fingerprint"
    ]
    expected_scopes = _SCOPES[:1] if family == "CASES" else _SCOPES[1:]
    if (
        manifest.material_family != family
        or manifest.manifest_fingerprint != expected_fingerprint
        or manifest.observation_cutoff != request["observation_cutoff"]
        or manifest.scope_ids != expected_scopes
        or manifest.retryable_count != 0
    ):
        _fail("ACCEPTANCE_ACQUISITION_INVALID")


def _family_result(manifest: FamilyAcquisitionCoverage, result: str) -> dict[str, JsonValue]:
    return {
        "material_family": manifest.material_family,
        "manifest_fingerprint": manifest.manifest_fingerprint,
        "result": result,
        "retryable_count": manifest.retryable_count,
        "rejected_count": 0,
    }


def run_hk_v1_acceptance_cycle(
    context: OrchestrationContext,
    payload: object,
) -> Generator[Task[object], object, dict[str, object]]:
    """Coordinate exact acquisition then legal readiness without manufacturing artifacts."""
    request = _request(payload)
    acquisition_value = yield context.call_activity(ACCEPTANCE_ACQUISITION_ACTIVITY, input=request)
    acquisition = _acquisition(acquisition_value, request)
    if acquisition["result"] == "NO_CHANGE":
        return _result(request, "NO_CHANGE", (), None)
    legal_payload: dict[str, JsonValue] = {
        "request": request,
        "acquisition": acquisition,
        "family_acquisition_evidence": request["family_acquisition_evidence"],
    }
    legal_value = yield context.call_activity(ACCEPTANCE_LEGAL_ACTIVITY, input=legal_payload)
    legal = _legal(legal_value, request)
    result = _text(legal["result"], "ACCEPTANCE_LEGAL_RESULT_INVALID")
    blockers = _texts(legal["blocker_codes"], "ACCEPTANCE_LEGAL_RESULT_INVALID")
    proposal = legal["proposal_reference"]
    if result == "NOT_READY":
        return _result(request, "NOT_READY", blockers, None)
    return _result(
        request,
        "PROPOSAL_READY",
        (),
        _object(proposal, _PROPOSAL_FIELDS, "ACCEPTANCE_LEGAL_RESULT_INVALID"),
    )


def _request(value: object) -> dict[str, JsonValue]:
    code = "ACCEPTANCE_REQUEST_INVALID"
    document = _object(value, _REQUEST_FIELDS, code)
    if (
        document["schema_id"] != "asklegal.hk-v1.acceptance-cycle-request"
        or document["schema_version"] != _VERSION
        or _texts(document["families"], code) != _FAMILIES
        or _texts(document["scope_ids"], code) != _SCOPES
    ):
        _fail(code)
    kind = _text(document["kind"], code)
    cutoff_key = _text(document["cutoff_key"], code)
    changed = _texts(document["authentic_changed_families"], code)
    cases_fingerprint = _fingerprint(document["cases_manifest_fingerprint"], code)
    legislation_fingerprint = _fingerprint(document["legislation_manifest_fingerprint"], code)
    family_evidence = _validate_acceptance_family_evidence(
        document["family_acquisition_evidence"],
        cases_fingerprint,
        legislation_fingerprint,
        code,
    )
    if (
        kind not in {"BASELINE", "UPDATE"}
        or cutoff_key != ("t1" if kind == "BASELINE" else "t2")
        or changed != tuple(sorted(set(changed)))
        or any(item not in _FAMILIES for item in changed)
        or (kind == "BASELINE" and changed)
    ):
        _fail(code)
    identity: dict[str, JsonValue] = {
        "kind": kind,
        "cutoff_key": cutoff_key,
        "observation_cutoff": _timestamp(document["observation_cutoff"], code),
        "cases_manifest_fingerprint": cases_fingerprint,
        "legislation_manifest_fingerprint": legislation_fingerprint,
        "authentic_changed_families": list(changed),
        "family_acquisition_evidence": family_evidence,
        "cutoff_selection_fingerprint": _fingerprint(
            document["cutoff_selection_fingerprint"], code
        ),
        "matrix_revision": _text(document["matrix_revision"], code),
        "matrix_fingerprint": _fingerprint(document["matrix_fingerprint"], code),
        "families": list(_FAMILIES),
        "scope_ids": list(_SCOPES),
    }
    digest = sha256(canonicalize(identity)).hexdigest()
    identifier = digest[:48]
    command_id = f"cmd_{identifier}"
    operation_id = f"cyc_{identifier}"
    command_identity: dict[str, JsonValue] = {
        **identity,
        "command_id": command_id,
        "operation_id": operation_id,
    }
    expected_fingerprint = f"sha256:{sha256(canonicalize(command_identity)).hexdigest()}"
    if (
        document["command_id"] != command_id
        or document["operation_id"] != operation_id
        or document["command_fingerprint"] != expected_fingerprint
    ):
        _fail(code)
    return document


def _acquisition(value: object, request: dict[str, JsonValue]) -> dict[str, JsonValue]:
    code = "ACCEPTANCE_ACQUISITION_INVALID"
    document = _object(value, _ACQUISITION_FIELDS, code)
    if (
        document["schema_id"] != "asklegal.hk-v1.acceptance-acquisition-result"
        or document["schema_version"] != _VERSION
        or document["operation_id"] != request["operation_id"]
        or document["command_fingerprint"] != request["command_fingerprint"]
        or document["observation_cutoff"] != request["observation_cutoff"]
        or _texts(document["scope_ids"], code) != _SCOPES
    ):
        _fail(code)
    raw_families = document["family_manifests"]
    if type(raw_families) is not list or len(raw_families) != len(_FAMILIES):
        _fail(code)
    expected_fingerprints = {
        "CASES": request["cases_manifest_fingerprint"],
        "LEGISLATION": request["legislation_manifest_fingerprint"],
    }
    statuses: list[str] = []
    for expected_family, raw in zip(_FAMILIES, raw_families, strict=True):
        family = _object(raw, _FAMILY_FIELDS, code)
        status = _text(family["result"], code)
        if (
            family["material_family"] != expected_family
            or family["manifest_fingerprint"] != expected_fingerprints[expected_family]
            or status not in {"COMPLETE", "NO_CHANGE"}
            or family["retryable_count"] != 0
            or family["rejected_count"] != 0
        ):
            _fail(code)
        statuses.append(status)
    result = _text(document["result"], code)
    if (result == "COMPLETE" and "COMPLETE" not in statuses) or (
        result == "NO_CHANGE" and any(status != "NO_CHANGE" for status in statuses)
    ):
        _fail(code)
    if result not in {"COMPLETE", "NO_CHANGE"}:
        _fail(code)
    _validate_acquisition_correlation(document, request, tuple(statuses), code)
    return document


def _validate_acquisition_correlation(
    document: dict[str, JsonValue],
    request: dict[str, JsonValue],
    statuses: tuple[str, ...],
    code: str,
) -> None:
    result = _text(document["result"], code)
    changed = _texts(request["authentic_changed_families"], code)
    completed_families = tuple(
        family for family, status in zip(_FAMILIES, statuses, strict=True) if status == "COMPLETE"
    )
    if request["kind"] == "BASELINE":
        if result != "COMPLETE" or completed_families != _FAMILIES:
            _fail(code)
    elif changed:
        if result != "COMPLETE" or completed_families != changed:
            _fail(code)
    elif result != "NO_CHANGE" or completed_families:
        _fail(code)


def _legal(value: object, request: dict[str, JsonValue]) -> dict[str, JsonValue]:
    code = "ACCEPTANCE_LEGAL_RESULT_INVALID"
    document = _object(value, _LEGAL_FIELDS, code)
    if (
        document["schema_id"] != "asklegal.hk-v1.acceptance-legal-result"
        or document["schema_version"] != _VERSION
        or document["operation_id"] != request["operation_id"]
        or document["command_fingerprint"] != request["command_fingerprint"]
        or document["observation_cutoff"] != request["observation_cutoff"]
        or _texts(document["families"], code) != _FAMILIES
    ):
        _fail(code)
    result = _text(document["result"], code)
    blockers = _texts(document["blocker_codes"], code)
    scopes = document["scope_results"]
    if result == "NOT_READY":
        if not blockers or scopes != [] or document["proposal_reference"] is not None:
            _fail(code)
        return document
    if (
        result != "PROPOSAL_READY"
        or blockers
        or type(scopes) is not list
        or len(scopes) != len(_SCOPES)
    ):
        _fail(code)
    for expected_scope, raw in zip(_SCOPES, scopes, strict=True):
        scope = _object(
            raw,
            {
                "scope_id",
                "result",
                "record_count",
                "release_id",
                "release_fingerprint",
                "zero_record_justification_refs",
            },
            code,
        )
        record_count = scope["record_count"]
        justification_refs = _texts(scope["zero_record_justification_refs"], code)
        if (
            scope["scope_id"] != expected_scope
            or scope["result"] != "COMPLETE"
            or type(record_count) is not int
            or record_count < 0
            or not _text(scope["release_id"], code)
            or not _fingerprint(scope["release_fingerprint"], code)
            or justification_refs != tuple(sorted(set(justification_refs)))
            or any(
                not _valid_zero_record_reference(expected_scope, reference)
                for reference in justification_refs
            )
            or (record_count == 0 and not justification_refs)
            or (record_count > 0 and justification_refs)
        ):
            _fail(code)
    proposal = _object(document["proposal_reference"], _PROPOSAL_FIELDS, code)
    if (
        proposal["vault"] != "PRIMARY"
        or not _text(proposal["logical_key"], code)
        or not _text(proposal["version_id"], code)
        or not _fingerprint(proposal["fingerprint"], code)
        or type(proposal["byte_length"]) is not int
        or proposal["byte_length"] < 1
    ):
        _fail(code)
    return document


def _valid_zero_record_reference(scope_id: str, reference: str) -> bool:
    """Enforce the distinct Case-vault and Desk-issued Legislation identities."""
    if scope_id == _SCOPES[0]:
        return (
            re.fullmatch(
                rf"hk-v1/legal-processing/zero-record/{re.escape(scope_id)}"
                r"/sha256/[0-9a-f]{64}\.json",
                reference,
            )
            is not None
        )
    return re.fullmatch(r"[a-z][a-z0-9]{2}_[0-9a-f]{48}@sha256:[0-9a-f]{64}", reference) is not None


def _validate_acceptance_family_evidence(
    value: object,
    cases_manifest_fingerprint: str,
    legislation_manifest_fingerprint: str,
    code: str,
) -> dict[str, JsonValue]:
    evidence = _object(value, _ACCEPTANCE_FAMILY_EVIDENCE_FIELDS, code)
    if (
        evidence["schema_id"] != "asklegal.hk-v1.acceptance-family-acquisition-evidence"
        or evidence["schema_version"] != _VERSION
        or not _text(evidence["root_cycle_id"], code)
    ):
        _fail(code)
    _fingerprint(evidence["root_plan_fingerprint"], code)
    _exact_reference(evidence["evidence_reference"], code)
    raw_children = evidence["children"]
    if type(raw_children) is not list or len(raw_children) != len(_FAMILIES):
        _fail(code)
    expected_fingerprints = (cases_manifest_fingerprint, legislation_manifest_fingerprint)
    for family, expected_fingerprint, raw_child in zip(
        _FAMILIES, expected_fingerprints, raw_children, strict=True
    ):
        child = _object(raw_child, _FAMILY_CHILD_FIELDS, code)
        cycle_id = _text(child["cycle_id"], code)
        if (
            child["source_family"] != family
            or child["journal_ref"] != f"acquisition-journals/{cycle_id}"
            or child["manifest_fingerprint"] != expected_fingerprint
            or child["result"] not in {"COMPLETE", "NO_CHANGE"}
        ):
            _fail(code)
        _fingerprint(child["journal_head_fingerprint"], code)
        _exact_reference(child["manifest_reference"], code)
    return evidence


def _exact_reference(value: object, code: str) -> dict[str, JsonValue]:
    reference = _object(value, _PROPOSAL_FIELDS, code)
    if (
        reference["vault"] != "PRIMARY"
        or not _text(reference["logical_key"], code)
        or not _text(reference["version_id"], code)
        or _nonnegative_integer(reference["byte_length"], code) < 1
    ):
        _fail(code)
    _fingerprint(reference["fingerprint"], code)
    return reference


def _legal_activity_payload(
    value: object,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue], dict[str, JsonValue]]:
    document = _object(
        value,
        {"request", "acquisition", "family_acquisition_evidence"},
        "ACCEPTANCE_LEGAL_RESULT_INVALID",
    )
    request = _request(document["request"])
    acquisition = _acquisition(document["acquisition"], request)
    family_evidence = _validate_acceptance_family_evidence(
        document["family_acquisition_evidence"],
        _fingerprint(request["cases_manifest_fingerprint"], "ACCEPTANCE_LEGAL_RESULT_INVALID"),
        _fingerprint(
            request["legislation_manifest_fingerprint"], "ACCEPTANCE_LEGAL_RESULT_INVALID"
        ),
        "ACCEPTANCE_LEGAL_RESULT_INVALID",
    )
    if family_evidence != request["family_acquisition_evidence"]:
        _fail("ACCEPTANCE_LEGAL_RESULT_INVALID")
    return request, acquisition, family_evidence


def _result(
    request: dict[str, JsonValue],
    result: str,
    blocker_codes: tuple[str, ...],
    proposal_reference: dict[str, JsonValue] | None,
) -> dict[str, object]:
    return {
        "schema_id": "asklegal.hk-v1.acceptance-cycle-result",
        "schema_version": _VERSION,
        "kind": request["kind"],
        "operation_id": request["operation_id"],
        "command_fingerprint": request["command_fingerprint"],
        "observation_cutoff": request["observation_cutoff"],
        "families": list(_FAMILIES),
        "scope_ids": list(_SCOPES),
        "result": result,
        "blocker_codes": list(blocker_codes),
        "proposal_reference": proposal_reference,
    }


def validate_hk_v1_acceptance_cycle_result(value: object) -> dict[str, JsonValue]:
    """Rebuild one exact acceptance result received by the due orchestrator."""
    code = "HK_V1_DUE_ACCEPTANCE_RESULT_INVALID"
    document = _object(value, _CYCLE_RESULT_FIELDS, code)
    result = _text(document["result"], code)
    blockers = _texts(document["blocker_codes"], code)
    proposal = document["proposal_reference"]
    if (
        document["schema_id"] != "asklegal.hk-v1.acceptance-cycle-result"
        or document["schema_version"] != _VERSION
        or document["kind"] not in {"BASELINE", "UPDATE"}
        or not _text(document["operation_id"], code).startswith("cyc_")
        or not _fingerprint(document["command_fingerprint"], code)
        or not _timestamp(document["observation_cutoff"], code)
        or _texts(document["families"], code) != _FAMILIES
        or _texts(document["scope_ids"], code) != _SCOPES
        or result not in {"NO_CHANGE", "NOT_READY", "PROPOSAL_READY"}
    ):
        _fail(code)
    if result == "NO_CHANGE" and (blockers or proposal is not None):
        _fail(code)
    if result == "NOT_READY" and (not blockers or proposal is not None):
        _fail(code)
    if result == "PROPOSAL_READY":
        if blockers:
            _fail(code)
        _object(proposal, _PROPOSAL_FIELDS, code)
    return document


def _object(value: object, fields: set[str], code: str) -> dict[str, JsonValue]:
    try:
        checked = checked_json_value(value)
    except ValueError as error:
        raise AcceptanceCoordinatorError(code) from error
    if type(checked) is not dict or set(checked) != fields:
        _fail(code)
    return checked


def _texts(value: object, code: str) -> tuple[str, ...]:
    if not _is_object_list(value):
        _fail(code)
    items: list[str] = []
    for item in value:
        if type(item) is not str:
            _fail(code)
        items.append(_text(item, code))
    return tuple(items)


def _is_object_list(value: object) -> TypeIs[list[object]]:
    return type(value) is list


def _text(value: object, code: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail(code)
    return value


def _nonnegative_integer(value: object, code: str) -> int:
    if type(value) is not int or value < 0:
        _fail(code)
    return value


def _fingerprint(value: object, code: str) -> str:
    text = _text(value, code)
    if (
        len(text) != _FINGERPRINT_LENGTH
        or not text.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in text[7:])
    ):
        _fail(code)
    return text


def _timestamp(value: object, code: str) -> str:
    text = _text(value, code)
    if _TIMESTAMP.fullmatch(text) is None:
        _fail(code)
    try:
        instant = datetime.fromisoformat(
            text.removesuffix("Z") + ("+00:00" if text.endswith("Z") else "")
        )
    except ValueError as error:
        raise AcceptanceCoordinatorError(code) from error
    if instant.utcoffset() not in {timedelta(0), timedelta(hours=8)} or instant.microsecond != 0:
        _fail(code)
    return text


__all__ = [
    "ACCEPTANCE_ACQUISITION_ACTIVITY",
    "ACCEPTANCE_LEGAL_ACTIVITY",
    "DUE_ACCEPTANCE_ACTIVITY",
    "AcceptanceConfiguration",
    "AcceptanceCoordinatorError",
    "LocalAcceptanceActivities",
    "UnavailableAcceptanceActivities",
    "run_hk_v1_acceptance_cycle",
    "validate_hk_v1_acceptance_cycle_result",
]
