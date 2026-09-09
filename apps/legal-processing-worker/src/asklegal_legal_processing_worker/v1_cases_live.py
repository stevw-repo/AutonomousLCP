# ruff: noqa: D102, EM101, PLR0913, PLR0917, TRY301
"""Live, restart-safe Case acceptance composition from retained acquisition bytes."""

from __future__ import annotations

import os
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts import fingerprint as contract_fingerprint
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import ServingRecordProfile
from asklegal_legal_desks.hk_case_proposition import (
    HKCasePropositionRequestAuthorities,
    HKCasePropositionSemanticRequest,
    bind_hk_case_proposition_challenge,
)
from asklegal_legal_desks.hk_case_semantic_task import HKCaseSemanticWorkflowComponent
from asklegal_management_register import LocalLegalIdentityRegister
from asklegal_management_register_ports import LegalIdentityKind, LegalIdentityRequest
from asklegal_processing import SemanticTaskRequest

from .v1_cases_acceptance import (
    CasesAcceptanceError,
    CurrentPrimaryVault,
    PreparedCaseReleaseComponent,
    admit_case_semantic_outputs,
    case_admission_token_counter,
    combine_case_release_components,
    load_verified_case_judgments,
    parse_case_semantic_decision,
    persist_case_release_component,
    prepare_case_release_component,
    prepare_case_semantic_work,
)

if TYPE_CHECKING:
    from asklegal_legal_desks import SemanticTaskProfile

_DECISION_SCHEMA = "asklegal.hk-case-proposition-decision-output/v1"
_CHALLENGE_SCHEMA = "asklegal.hk-case-proposition-challenge-output/v1"
_TREATMENT_SCHEMA = "asklegal.hk-case-later-treatment-proof/v1"
_ROLES = frozenset(
    {
        "COVERAGE_LEDGER",
        "MODEL_SETTINGS",
        "OUTPUT_SCHEMA",
        "PARSER_PROFILE",
        "PROCESSING_BUILD",
        "PROMPT",
        "SEGMENTATION_CONTRACT",
        "SOURCE_RULEBOOK",
        "STRUCTURE_CONTRACT",
        "VALIDATOR",
    }
)


class ExactJsonSemanticRunner(Protocol):
    """Already admitted task-specific semantic invocation boundary."""

    def invoke_exact_json(
        self,
        profile: object,
        request: SemanticTaskRequest,
        *,
        output_schema: str,
    ) -> bytes: ...


class SemanticProfiles(Protocol):
    """Exact profile sequence consumed by live Case selection."""

    @property
    def profiles(self) -> tuple[SemanticTaskProfile, ...]: ...


class CaseTokenCounter(Protocol):
    """Exact counter surface consumed by Case admission."""

    @property
    def tokenizer_id(self) -> str: ...

    def count(self, text: str) -> int: ...


def prepare_hk_v1_cases_acceptance_component(
    operation_id: str,
    manifest: bytes,
    verified_inputs: Mapping[str, JsonValue],
    primary_vault: CurrentPrimaryVault,
    profiles: SemanticProfiles,
    counter: CaseTokenCounter,
    runner: ExactJsonSemanticRunner,
    policy_path: Path,
    *,
    state_root: Path,
    output_root: Path,
) -> dict[str, JsonValue]:
    """Run/replay typed Case semantics and retain the positive Case component."""
    try:
        policy = _policy(policy_path)
        command = _text(verified_inputs.get("command_fingerprint"))
        cutoff = _text(verified_inputs.get("observation_cutoff"))
        if verified_inputs.get("operation_id") != operation_id:
            raise CasesAcceptanceError("CASES_VERIFIED_INPUTS_INVALID")
        selected = _profiles(profiles)
        serving = _serving_profile(policy)
        judgments = load_verified_case_judgments(manifest, primary_vault)
        if not judgments:
            raise CasesAcceptanceError("CASES_ACQUISITION_EMPTY")
        register_path = state_root / "case-identities.json"
        semantic_root = state_root / "case-semantic" / operation_id
        components: list[PreparedCaseReleaseComponent] = []
        for judgment in judgments:
            register = LocalLegalIdentityRegister(register_path)
            official_version = register.issue_identity(
                LegalIdentityRequest(
                    LegalIdentityKind.OFFICIAL_VERSION,
                    f"case:{judgment.capture_reference.fingerprint}",
                )
            ).identity_id
            register.commit()
            authorities = HKCasePropositionRequestAuthorities(
                cutoff[:10],
                _text(policy.get("source_snapshot_id")),
                judgment.acquisition_manifest_fingerprint,
                judgment.bundle.bundle_fingerprint,
                official_version,
                judgment.capture_reference.fingerprint,
                _components(policy.get("decision_workflow_components")),
                _components(policy.get("challenge_workflow_components")),
                _positive_int(policy.get("output_budget_bytes")),
            )
            work = prepare_case_semantic_work(judgment, (selected[0], selected[1]), authorities)
            key = judgment.capture_reference.fingerprint.removeprefix("sha256:")
            decision_path = semantic_root / key / "decision.json"
            decision = _invoke_or_replay(
                decision_path,
                runner,
                selected[0],
                _request(work.pair.decision, judgment.bundle.bundle_fingerprint),
                _DECISION_SCHEMA,
            )
            parsed = parse_case_semantic_decision(work, decision)
            challenge_request = bind_hk_case_proposition_challenge(
                work.pair.challenge,
                parsed.proposal_fingerprint,
                authorities,
            )
            challenge = _invoke_or_replay(
                semantic_root / key / "challenge.json",
                runner,
                selected[1],
                _request(challenge_request, judgment.bundle.bundle_fingerprint),
                _CHALLENGE_SCHEMA,
            )
            admission = admit_case_semantic_outputs(
                work,
                decision,
                challenge,
                counter=case_admission_token_counter(work, counter),
            )
            treatment_request = SemanticTaskRequest(
                request_id="req_"
                + contract_fingerprint(
                    checked_json_value(
                        {
                            "judgment": judgment.bundle.bundle_fingerprint,
                            "proposal": admission.proposal_fingerprint,
                            "task": selected[2].task,
                        }
                    )
                ).removeprefix("sha256:")[:48],
                task=selected[2].task,
                phase="DECISION",
                profile_id=selected[2].profile_id,
                package_fingerprint=judgment.bundle.bundle_fingerprint,
                subject_id=work.pair.decision.semantic_task.judicial_decision_id,
                evidence_refs=work.pair.decision.evidence_refs,
                evidence_bytes=work.pair.decision.evidence_bytes,
                input_fingerprint=contract_fingerprint(
                    checked_json_value(
                        {
                            "judgment": judgment.bundle.bundle_fingerprint,
                            "proposal": admission.proposal_fingerprint,
                        }
                    )
                ),
            )
            treatment = _invoke_or_replay(
                semantic_root / key / "treatment.json",
                runner,
                selected[2],
                treatment_request,
                _TREATMENT_SCHEMA,
            )
            components.append(
                prepare_case_release_component(
                    judgment,
                    admission,
                    decision,
                    challenge,
                    treatment,
                    cutoff if cutoff.endswith("Z") else cutoff.removesuffix("+00:00") + "Z",
                    serving,
                    LocalLegalIdentityRegister(register_path),
                )
            )
        combined = combine_case_release_components(tuple(components))
        path = persist_case_release_component(
            output_root / operation_id,
            operation_id,
            command,
            judgments[0].acquisition_manifest_fingerprint,
            combined,
        )
        content = path.read_bytes()
        return {
            "schema_id": "asklegal.hk-v1-cases-acceptance-result/v1",
            "schema_version": "1.0.0",
            "operation_id": operation_id,
            "result": "COMPLETE",
            "component_path": str(path),
            "component_fingerprint": _raw_fingerprint(content),
        }
    except CasesAcceptanceError:
        raise
    except Exception as error:
        raise CasesAcceptanceError("CASES_LIVE_COMPOSITION_INVALID") from error


def _profiles(
    profiles: SemanticProfiles,
) -> tuple[SemanticTaskProfile, SemanticTaskProfile, SemanticTaskProfile]:
    expected = (
        ("HK_CASE_PROPOSITION_ANALYSIS", _DECISION_SCHEMA),
        ("HK_CASE_PROPOSITION_CHALLENGE", _CHALLENGE_SCHEMA),
        ("HK_LATER_TREATMENT_DISCOVERY", _TREATMENT_SCHEMA),
    )
    selected: list[SemanticTaskProfile] = []
    for task, schema in expected:
        matches = [p for p in profiles.profiles if p.task == task and p.output_schema == schema]
        if len(matches) != 1:
            raise CasesAcceptanceError("CASES_SEMANTIC_PROFILE_NOT_READY")
        selected.append(matches[0])
    return selected[0], selected[1], selected[2]


def _request(
    request: HKCasePropositionSemanticRequest, package_fingerprint: str
) -> SemanticTaskRequest:
    return SemanticTaskRequest(
        request.request_id,
        request.task,
        "CHALLENGE" if request.phase == "CHALLENGE" else "DECISION",
        request.profile_id,
        package_fingerprint,
        request.subject_id,
        request.evidence_refs,
        request.evidence_bytes,
        request.input_fingerprint,
    )


def _invoke_or_replay(
    path: Path,
    runner: ExactJsonSemanticRunner,
    profile: SemanticTaskProfile,
    request: SemanticTaskRequest,
    schema: str,
) -> bytes:
    if path.exists():
        content = path.read_bytes()
        parsed = parse_json_bytes(content, max_bytes=2_000_000)
        if canonicalize(parsed) != content:
            raise CasesAcceptanceError("CASES_SEMANTIC_OUTPUT_DRIFT")
        return content
    content = runner.invoke_exact_json(profile, request, output_schema=schema)
    parsed = parse_json_bytes(content, max_bytes=2_000_000)
    canonical = canonicalize(parsed)
    if canonical != content:
        raise CasesAcceptanceError("CASES_SEMANTIC_OUTPUT_INVALID")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    if path.read_bytes() != content:
        raise CasesAcceptanceError("CASES_SEMANTIC_OUTPUT_READBACK_FAILED")
    return content


def _policy(path: Path) -> dict[str, JsonValue]:
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise CasesAcceptanceError("CASES_PROCESSING_POLICY_NOT_READY")
    raw = path.read_bytes()
    try:
        value = parse_json_bytes(raw, max_bytes=1_000_000)
    except Exception as error:
        raise CasesAcceptanceError("CASES_PROCESSING_POLICY_INVALID") from error
    expected = {
        "schema_id",
        "schema_version",
        "source_snapshot_id",
        "output_budget_bytes",
        "decision_workflow_components",
        "challenge_workflow_components",
        "serving_profile",
    }
    if (
        type(value) is not dict
        or canonicalize(value) != raw
        or frozenset(value) != frozenset(expected)
        or value.get("schema_id") != "asklegal.hk-v1-case-processing-policy/v1"
        or value.get("schema_version") != "1.0.0"
    ):
        raise CasesAcceptanceError("CASES_PROCESSING_POLICY_INVALID")
    return value


def _components(value: JsonValue | None) -> tuple[HKCaseSemanticWorkflowComponent, ...]:
    if type(value) is not list:
        raise CasesAcceptanceError("CASES_PROCESSING_POLICY_INVALID")
    items: list[HKCaseSemanticWorkflowComponent] = []
    for raw in value:
        if type(raw) is not dict or frozenset(raw) != frozenset({"component_role", "fingerprint"}):
            raise CasesAcceptanceError("CASES_PROCESSING_POLICY_INVALID")
        items.append(
            HKCaseSemanticWorkflowComponent(
                _text(raw.get("component_role")), _text(raw.get("fingerprint"))
            )
        )
    if frozenset(item.component_role for item in items) != _ROLES:
        raise CasesAcceptanceError("CASES_PROCESSING_POLICY_INVALID")
    return tuple(items)


def _serving_profile(policy: Mapping[str, JsonValue]) -> ServingRecordProfile:
    raw = policy.get("serving_profile")
    if type(raw) is not dict or frozenset(raw) != frozenset(
        {
            "serving_record_profile_id",
            "schema_version",
            "schema_fingerprint",
        }
    ):
        raise CasesAcceptanceError("CASES_PROCESSING_POLICY_INVALID")
    return ServingRecordProfile(
        _text(raw.get("serving_record_profile_id")),
        _text(raw.get("schema_version")),
        _text(raw.get("schema_fingerprint")),
    )


def _text(value: object) -> str:
    if type(value) is not str or not value:
        raise CasesAcceptanceError("CASES_LIVE_INPUT_INVALID")
    return value


def _positive_int(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise CasesAcceptanceError("CASES_PROCESSING_POLICY_INVALID")
    return value


def _raw_fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"
