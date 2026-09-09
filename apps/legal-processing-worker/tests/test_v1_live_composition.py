"""Fail-closed live legal-processing composition and resumable handoff tests."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Never, Protocol

import asklegal_legal_processing_worker.v1_service as service_module
import pytest
from _v1_semantic_profile_fixture import exact_semantic_profile_bytes, exact_semantic_profiles
from asklegal_application_runtime import CredentialMaterial, ServiceExitCode
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_durable_task import ActivityContext
from asklegal_evidence_vault import ExactObjectReference, RetentionProfile, VaultName
from asklegal_legal_processing_worker.v1_infrastructure import V1LegalProcessingInfrastructure
from asklegal_legal_processing_worker.v1_pipeline import (
    AdmittedAzureSemanticRunner,
    ProcessingPipelineError,
    build_live_activities,
)


class _Vault:
    vault_name = VaultName.PRIMARY

    def __init__(self, objects: dict[tuple[str, str, str, int], bytes] | None = None) -> None:
        self.objects = objects or {}
        self.calls: list[ExactObjectReference] = []

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        self.calls.append(reference)
        key = (
            reference.logical_key,
            reference.version_id,
            reference.fingerprint,
            reference.byte_length,
        )
        return self.objects[key]

    def resolve_current(self, logical_key: str) -> ExactObjectReference | None:
        matches = [
            ExactObjectReference(VaultName.PRIMARY, key[0], key[1], key[2], key[3])
            for key in self.objects
            if key[0] == logical_key
        ]
        assert len(matches) <= 1
        return matches[0] if matches else None

    def conditional_create(
        self, logical_key: str, content: bytes, retention: RetentionProfile
    ) -> Never:
        del logical_key, content, retention
        message = "composition must not write the vault"
        raise AssertionError(message)


class _Credential(Protocol):
    def reveal(self) -> bytes:
        """Return exact synthetic credential bytes."""
        ...


@dataclass(frozen=True, slots=True)
class _Infrastructure:
    primary_vault: _Vault
    model_provider_credential: _Credential
    model_egress_proxy_credential: _Credential
    scheduler: object | None = None


class _ExplodingCredential:
    def reveal(self) -> bytes:
        message = "invalid files must stop before credential inspection"
        raise AssertionError(message)


def _sealed_evidence(profile_raw: bytes) -> bytes:
    profile = parse_json_bytes(profile_raw, max_bytes=2_000_000)
    assert type(profile) is dict
    profiles = profile["profiles"]
    assert type(profiles) is list
    tasks: list[str] = []
    for item in profiles:
        assert type(item) is dict
        task = item["task"]
        assert type(task) is str
        tasks.append(task)
    tasks.sort()
    body = checked_json_value(
        {
            "admitted": True,
            "application": "LEGAL_PROCESSING_WORKER",
            "environment": profile["environment"],
            "profile_content_fingerprint": f"sha256:{sha256(profile_raw).hexdigest()}",
            "profile_fingerprint": exact_semantic_profiles().fingerprint,
            "role": "generative_llm_provider",
            "schema_id": "asklegal.hk-v1-current-semantic-capability-evidence/v1",
            "tasks": tasks,
            "valid_from": "2026-09-01T00:00:00Z",
            "valid_until": "2098-01-01T00:00:00Z",
        }
    )
    assert type(body) is dict
    fingerprint = f"sha256:{sha256(canonicalize(body)).hexdigest()}"
    return canonicalize({**body, "fingerprint": fingerprint})


def _configuration(tmp_path: Path) -> tuple[dict[str, str], bytes]:
    profile = exact_semantic_profile_bytes()
    profile_path = tmp_path / "semantic-profile.json"
    evidence_path = tmp_path / "semantic-evidence.json"
    profile_path.write_bytes(profile)
    evidence_path.write_bytes(_sealed_evidence(profile))
    case_policy_path = tmp_path / "case-processing-policy.json"
    roles = (
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
    )
    case_policy_path.write_bytes(
        canonicalize(
            {
                "schema_id": "asklegal.hk-v1-case-processing-policy/v1",
                "schema_version": "1.0.0",
                "source_snapshot_id": "source_snapshot_v1",
                "output_budget_bytes": 24000,
                "decision_workflow_components": [
                    {"component_role": role, "fingerprint": "sha256:" + "1" * 64} for role in roles
                ],
                "challenge_workflow_components": [
                    {"component_role": role, "fingerprint": "sha256:" + "2" * 64} for role in roles
                ],
                "serving_profile": {
                    "serving_record_profile_id": "srp_hk_case_v1",
                    "schema_version": "1.0.0",
                    "schema_fingerprint": "sha256:" + "3" * 64,
                },
            }
        )
    )
    acceptance_root = tmp_path / "acceptance-inputs"
    review_root = tmp_path / "review-artifacts"
    acceptance_root.mkdir()
    review_root.mkdir()
    return (
        {
            "ASKLEGAL_HK_V1_ACQUISITION_JOURNAL_ROOT": str(tmp_path / "acquisition-due-cycle"),
            "ASKLEGAL_HK_V1_ACCEPTANCE_INPUT_ROOT": str(acceptance_root),
            "ASKLEGAL_HK_V1_CASE_PROCESSING_POLICY_PATH": str(case_policy_path),
            "ASKLEGAL_HK_V1_PACKAGE_FACTS_ROOT": str(tmp_path / "package-facts"),
            "ASKLEGAL_HK_V1_SEMANTIC_PROFILE_PATH": str(profile_path),
            "ASKLEGAL_HK_V1_SEMANTIC_CAPABILITY_EVIDENCE_PATH": str(evidence_path),
            "ASKLEGAL_HK_V1_PROCESSING_STATE_ROOT": str(tmp_path / "state"),
            "ASKLEGAL_HK_V1_REVIEW_ARTIFACT_ROOT": str(review_root),
        },
        profile,
    )


def _infrastructure(vault: _Vault | None = None) -> _Infrastructure:
    return _Infrastructure(
        vault or _Vault(),
        CredentialMaterial(
            canonicalize(
                {
                    "api_key": "synthetic-key",
                    "api_version": "2026-08-01",
                    "deployment": "synthetic-semantic-v1",
                    "endpoint": "https://synthetic.openai.azure.com",
                }
            )
        ),
        CredentialMaterial(b"http://egress-model:3128"),
    )


def test_exact_profile_evidence_credentials_and_proxy_compose_without_a_call(
    tmp_path: Path,
) -> None:
    """Valid local authority composes the real runner without using it."""
    environment, _ = _configuration(tmp_path)
    vault = _Vault()

    activities = build_live_activities(
        _infrastructure(vault), environment, current_time="2026-09-08T00:00:00Z"
    )

    assert isinstance(activities.semantic_runner, AdmittedAzureSemanticRunner)
    assert activities.deployment == "synthetic-semantic-v1"
    assert vault.calls == []


def test_runtime_contract_mounts_only_explicit_processing_state_and_authority() -> None:
    """The runtime exposes only one writable state root and immutable authority files."""
    repository = Path(__file__).parents[3]
    runtime = json.loads(
        (repository / "infrastructure/poc/service_runtime_commands.json").read_text()
    )
    service = next(
        item for item in runtime["services"] if item["service_id"] == "legal-processing-worker"
    )

    assert service["environment"] == [
        {
            "name": "ASKLEGAL_HK_V1_ACQUISITION_JOURNAL_ROOT",
            "value": "/var/lib/asklegal/acquisition/due-cycle",
        },
        {
            "name": "ASKLEGAL_HK_V1_ACCEPTANCE_INPUT_ROOT",
            "value": "/var/lib/asklegal/processing/acceptance-inputs",
        },
        {
            "name": "ASKLEGAL_HK_V1_CASE_PROCESSING_POLICY_PATH",
            "value": "/etc/asklegal/config/hk-v1-legal-processing/case-processing-policy.json",
        },
        {
            "name": "ASKLEGAL_HK_V1_PACKAGE_FACTS_ROOT",
            "value": "/etc/asklegal/config/hk-v1-legal-processing/package-facts",
        },
        {
            "name": "ASKLEGAL_HK_V1_PROCESSING_STATE_ROOT",
            "value": "/var/lib/asklegal/processing",
        },
        {
            "name": "ASKLEGAL_HK_V1_REVIEW_ARTIFACT_ROOT",
            "value": "/var/lib/asklegal/review-artifacts",
        },
        {
            "name": "ASKLEGAL_HK_V1_SEMANTIC_CAPABILITY_EVIDENCE_PATH",
            "value": (
                "/etc/asklegal/config/hk-v1-legal-processing/semantic-capability-evidence.json"
            ),
        },
        {
            "name": "ASKLEGAL_HK_V1_SEMANTIC_PROFILE_PATH",
            "value": "/etc/asklegal/config/hk-v1-legal-processing/semantic-profile.json",
        },
    ]
    assert service["mounts"][:4] == [
        {
            "source": "/var/lib/asklegal/acquisition/due-cycle",
            "target": "/var/lib/asklegal/acquisition/due-cycle",
            "mode": "ro",
        },
        {
            "source": "/var/lib/asklegal/processing",
            "target": "/var/lib/asklegal/processing",
            "mode": "rw",
        },
        {
            "source": "/etc/asklegal/config/hk-v1-legal-processing",
            "target": "/etc/asklegal/config/hk-v1-legal-processing",
            "mode": "ro",
        },
        {
            "source": "/var/lib/asklegal/review-artifacts",
            "target": "/var/lib/asklegal/review-artifacts",
            "mode": "rw",
        },
    ]


@pytest.mark.parametrize(
    "missing",
    [
        "ASKLEGAL_HK_V1_SEMANTIC_PROFILE_PATH",
        "ASKLEGAL_HK_V1_SEMANTIC_CAPABILITY_EVIDENCE_PATH",
        "ASKLEGAL_HK_V1_PROCESSING_STATE_ROOT",
        "ASKLEGAL_HK_V1_ACQUISITION_JOURNAL_ROOT",
    ],
)
def test_missing_live_configuration_stops_before_credentials_or_state_creation(
    tmp_path: Path, missing: str
) -> None:
    """Any absent required path fails before secrets or writable state are touched."""
    environment, _ = _configuration(tmp_path)
    del environment[missing]
    infrastructure = _Infrastructure(_Vault(), _ExplodingCredential(), _ExplodingCredential())

    with pytest.raises(ProcessingPipelineError, match=r"^LIVE_SEMANTIC_CONFIGURATION_INVALID$"):
        build_live_activities(infrastructure, environment, current_time="2026-09-08T00:00:00Z")

    assert not (tmp_path / "state").exists()


def test_drifted_capability_evidence_stops_before_credentials_or_state_creation(
    tmp_path: Path,
) -> None:
    """A coherently re-fingerprinted but misbound evidence file still fails closed."""
    environment, _ = _configuration(tmp_path)
    evidence_path = Path(environment["ASKLEGAL_HK_V1_SEMANTIC_CAPABILITY_EVIDENCE_PATH"])
    evidence = parse_json_bytes(evidence_path.read_bytes(), max_bytes=100_000)
    assert type(evidence) is dict
    evidence["profile_fingerprint"] = "sha256:" + "f" * 64
    body = dict(evidence)
    body.pop("fingerprint")
    evidence["fingerprint"] = f"sha256:{sha256(canonicalize(body)).hexdigest()}"
    evidence_path.write_bytes(canonicalize(evidence))
    infrastructure = _Infrastructure(_Vault(), _ExplodingCredential(), _ExplodingCredential())

    with pytest.raises(ProcessingPipelineError, match=r"^LIVE_SEMANTIC_EVIDENCE_INVALID$"):
        build_live_activities(infrastructure, environment, current_time="2026-09-08T00:00:00Z")

    assert not (tmp_path / "state").exists()


def test_invalid_proxy_credential_returns_one_safe_composition_failure(tmp_path: Path) -> None:
    """A malformed proxy port cannot escape the NOT_READY error boundary."""
    environment, _ = _configuration(tmp_path)
    infrastructure = _Infrastructure(
        _Vault(),
        _infrastructure().model_provider_credential,
        CredentialMaterial(b"http://egress-model:not-a-port"),
    )

    with pytest.raises(ProcessingPipelineError, match=r"^LIVE_SEMANTIC_CREDENTIAL_INVALID$"):
        build_live_activities(infrastructure, environment, current_time="2026-09-08T00:00:00Z")


def test_authority_drift_after_startup_stops_before_request_or_provider_call(
    tmp_path: Path,
) -> None:
    """Every semantic invocation re-reads immutable authority before parsing its request."""
    environment, _ = _configuration(tmp_path)
    activities = build_live_activities(
        _infrastructure(), environment, current_time="2026-09-08T00:00:00Z"
    )
    evidence = Path(environment["ASKLEGAL_HK_V1_SEMANTIC_CAPABILITY_EVIDENCE_PATH"])
    evidence.write_bytes(evidence.read_bytes() + b"\n")

    with pytest.raises(ProcessingPipelineError, match=r"^LIVE_SEMANTIC_EVIDENCE_INVALID$"):
        activities.analyse_evidence(ActivityContext("instance", 1), {})


def _batch_payload(
    material_family: str,
    scope_id: str,
    evidence: bytes,
) -> tuple[dict[str, JsonValue], dict[tuple[str, str, str, int], bytes]]:
    fingerprint = f"sha256:{sha256(evidence).hexdigest()}"
    key = ("verified/item.json", "v" + "1" * 64, fingerprint, len(evidence))
    payload: dict[str, JsonValue] = {
        "acquisition_manifest_fingerprint": "sha256:" + "a" * 64,
        "batch_id": f"{material_family.lower()}-batch-1",
        "evidence_items": [
            {
                "byte_length": len(evidence),
                "evidence_ref": f"evidence/{material_family.lower()}/item-1",
                "fingerprint": fingerprint,
                "logical_key": key[0],
                "version_id": key[1],
            }
        ],
        "journal_head_fingerprint": "sha256:" + "b" * 64,
        "material_family": material_family,
        "observation_cutoff": "2026-09-08T00:00:00Z",
        "scope_id": scope_id,
    }
    return payload, {key: evidence}


@pytest.mark.parametrize(
    ("material_family", "scope_id", "method_name"),
    [
        ("CASES", "HK-CASE-BINDING-POST-1997", "prepare_cases_batch"),
        ("LEGISLATION", "HK-LEG-ORDINANCES", "prepare_legislation_batch"),
    ],
)
def test_two_family_preparation_persists_and_reads_back_across_restart(
    tmp_path: Path,
    material_family: str,
    scope_id: str,
    method_name: str,
) -> None:
    """Both family handoffs are immutable and replay identically after recreation."""
    environment, _ = _configuration(tmp_path)
    evidence = canonicalize(
        checked_json_value(
            {"language": "en", "subject_id": "item-1", "text": "Verified legal text."}
        )
    )
    payload, objects = _batch_payload(material_family, scope_id, evidence)
    first = build_live_activities(
        _infrastructure(_Vault(objects)), environment, current_time="2026-09-08T00:00:00Z"
    )
    first_result = getattr(first, method_name)(ActivityContext("instance", 1), payload)
    restarted = build_live_activities(
        _infrastructure(_Vault(objects)), environment, current_time="2026-09-08T00:00:00Z"
    )
    restarted_result = getattr(restarted, method_name)(ActivityContext("instance", 1), payload)

    assert restarted_result == first_result
    assert first_result["material_family"] == material_family
    assert first_result["provider_invocation_count"] == 0
    assert first_result["release_state"] == "WITHHELD_PENDING_TWO_FAMILY_RECONCILIATION"
    artifact = first_result["artifact_ref"]
    assert type(artifact) is str
    assert (tmp_path / "state" / "prepared-batches" / artifact).is_file()


def test_service_returns_not_ready_before_readiness_or_worker_on_live_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Invalid authority returns NOT_READY without reaching readiness probes or a worker."""
    readiness_called = False

    def fail_live(*_args: object, **_kwargs: object) -> Never:
        message = "LIVE_SEMANTIC_CONFIGURATION_INVALID"
        raise ProcessingPipelineError(message)

    def fake_load(_environment: Mapping[str, str]) -> V1LegalProcessingInfrastructure:
        return object.__new__(V1LegalProcessingInfrastructure)

    async def forbidden_service(*_args: object, **_kwargs: object) -> ServiceExitCode:
        nonlocal readiness_called
        readiness_called = True
        return ServiceExitCode.OK

    monkeypatch.setattr(service_module, "load_v1_infrastructure", fake_load)
    monkeypatch.setattr(service_module, "build_live_activities", fail_live)
    monkeypatch.setattr(service_module, "run_v1_service", forbidden_service)

    result = asyncio.run(service_module.run_with_environment({}))

    assert result is ServiceExitCode.NOT_READY
    assert readiness_called is False


class _NamedCallback(Protocol):
    __name__: str


class _Worker:
    def __init__(self) -> None:
        self.activities: list[str] = []
        self.orchestrators: list[str] = []

    def add_activity(self, callback: _NamedCallback) -> None:
        self.activities.append(callback.__name__)

    def add_orchestrator(self, callback: _NamedCallback) -> None:
        self.orchestrators.append(callback.__name__)

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


class _Scheduler:
    task_hub = "legal-processing"

    def __init__(self, worker: _Worker) -> None:
        self.worker = worker

    def create_worker(self, **_kwargs: object) -> _Worker:
        return self.worker


def _service_infrastructure(worker: _Worker) -> V1LegalProcessingInfrastructure:
    infrastructure = object.__new__(V1LegalProcessingInfrastructure)
    object.__setattr__(infrastructure, "scheduler", _Scheduler(worker))
    return infrastructure


def test_service_registers_both_family_activities_and_orchestrators(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker exposes both family activities and replay-safe orchestrators."""
    environment, _ = _configuration(tmp_path)
    worker = _Worker()
    infrastructure = _infrastructure()
    activities = build_live_activities(
        infrastructure, environment, current_time="2026-09-08T00:00:00Z"
    )
    shutdown = asyncio.Event()
    shutdown.set()

    async def immediate(callback: Callable[[], None]) -> None:
        callback()

    monkeypatch.setattr(service_module.asyncio, "to_thread", immediate)

    asyncio.run(service_module.build_serve(_service_infrastructure(worker), activities)(shutdown))

    assert {
        "prepare_cases_batch",
        "prepare_legislation_batch",
        "prepare_hk_v1_acceptance_inputs",
        "start_hk_v1_acceptance_legal_processing",
    } <= set(worker.activities)
    assert {
        "process_cases_batch",
        "process_legislation_batch",
        "run_hk_v1_acceptance_legal_processing",
    } <= set(worker.orchestrators)
