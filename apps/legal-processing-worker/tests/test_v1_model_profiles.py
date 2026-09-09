"""Semantic capability composition boundary."""

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, cast

import pytest
from _v1_semantic_profile_fixture import exact_semantic_profiles
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import ImmutableReference, ReferenceType
from asklegal_durable_task import ActivityContext
from asklegal_evidence_vault import LocalImmutableVault, VaultName
from asklegal_legal_processing_worker.v1_pipeline import (
    CurrentSemanticCapabilityEvidence,
    SemanticCapabilityRequirement,
    build_activities,
    compose_admitted_azure_semantic_runner,
    compose_semantic_runner,
)
from asklegal_processing import (
    AzureDeployment,
    DisabledSemanticTaskRunner,
    ExactTokenCounter,
    ProcessingError,
    SemanticProfileSet,
    SemanticTaskRequest,
)


class _ExplodingCredential:
    """Fails if disabled composition tries to inspect staged provider material."""

    def reveal(self) -> bytes:
        message = "disabled composition inspected a provider credential"
        raise AssertionError(message)


class _Reader:
    """One injected reader double that returns exactly its configured result."""

    def __init__(self, result: object) -> None:
        self.result = result

    def read_current(self, requirement: SemanticCapabilityRequirement) -> object:
        del requirement
        return self.result


class _DuckCounter:
    """Shape-compatible counter that lacks immutable resource authority."""

    tokenizer_id = "o200k_base"

    def __init__(self, count: int = 10) -> None:
        self.value = count
        self.inputs: list[str] = []

    def count(self, text: str) -> int:
        self.inputs.append(text)
        return self.value


class _ModelTransport:
    """No-network transport that records exact provider requests."""

    def __init__(self, content: dict[str, JsonValue]) -> None:
        self.content = content
        self.calls: list[dict[str, JsonValue]] = []

    def post_json(self, url: str, headers: dict[str, str], body: JsonValue) -> dict[str, JsonValue]:
        del url, headers
        recorded = checked_json_value(body)
        assert isinstance(recorded, dict)
        self.calls.append(recorded)
        return {
            "id": "provider-request-fixture-1",
            "choices": [{"message": {"content": json.dumps(self.content)}}],
        }


def _counter(profiles: SemanticProfileSet) -> ExactTokenCounter:
    resource = (
        Path(__file__).parents[3]
        / "packages/processing/src/asklegal_processing/_resources/o200k_base.tiktoken"
    ).read_bytes()
    return ExactTokenCounter(profiles, "o200k_base", resource)


def _semantic_request(
    profile_id: str,
    task: str,
    *,
    phase: Literal["DECISION", "CHALLENGE"] = "DECISION",
    evidence_bytes: bytes = b"Exact inert evidence.",
) -> SemanticTaskRequest:
    return SemanticTaskRequest(
        "request-1",
        task,
        phase,
        profile_id,
        "sha256:" + "1" * 64,
        "subject-1",
        ("evidence-1",),
        evidence_bytes,
        "sha256:" + "2" * 64,
    )


def test_admitted_azure_composition_preflights_exact_tokens_and_strict_output() -> None:
    """Bypassing token preflight or strict output parsing would let model drift through."""
    profiles = exact_semantic_profiles()
    profile = profiles.profiles[0]
    counter = _counter(profiles)
    transport = _ModelTransport(
        {
            "decision_code": "SUPPORTED",
            "supporting_evidence_refs": ["evidence-1"],
            "unresolved_facts": [],
            "challenge_code": "NOT_APPLICABLE",
        }
    )
    runner = compose_admitted_azure_semantic_runner(
        profiles,
        counter,
        AzureDeployment(
            "https://example.openai.azure.com",
            profile.deployment_name,
            profile.api_contract,
            "k",
        ),
        transport,
    )

    result = runner.invoke(profile, _semantic_request(profile.profile_id, profile.task))

    assert result.decision_code == "SUPPORTED"
    assert len(transport.calls) == 1


def test_budget_or_profile_drift_stops_before_model_transport() -> None:
    """An oversized request or non-member profile cannot consume provider capacity."""
    profiles = exact_semantic_profiles()
    profile = profiles.profiles[0]
    transport = _ModelTransport({})
    with pytest.raises(ProcessingError):
        compose_admitted_azure_semantic_runner(
            profiles,
            cast("ExactTokenCounter", _DuckCounter(10_000)),
            AzureDeployment(
                "https://example.openai.azure.com",
                profile.deployment_name,
                profile.api_contract,
                "k",
            ),
            transport,
        )

    assert transport.calls == []


def test_extra_model_output_field_is_never_repaired() -> None:
    """A plausible answer with one uncontracted field remains malformed legal output."""
    profiles = exact_semantic_profiles()
    profile = profiles.profiles[0]
    transport = _ModelTransport(
        {
            "decision_code": "SUPPORTED",
            "supporting_evidence_refs": ["evidence-1"],
            "unresolved_facts": [],
            "challenge_code": "NOT_APPLICABLE",
            "explanation": "must not be repaired away",
        }
    )
    runner = compose_admitted_azure_semantic_runner(
        profiles,
        _counter(profiles),
        AzureDeployment(
            "https://example.openai.azure.com",
            profile.deployment_name,
            profile.api_contract,
            "k",
        ),
        transport,
    )

    with pytest.raises(ProcessingError, match=r"^MODEL_OUTPUT_FIELDS_UNEXPECTED$"):
        runner.invoke(profile, _semantic_request(profile.profile_id, profile.task))


@pytest.mark.parametrize(
    ("mutation", "reply"),
    [
        (
            "TASK",
            {
                "decision_code": "SUPPORTED",
                "supporting_evidence_refs": [],
                "unresolved_facts": [],
                "challenge_code": "NOT_APPLICABLE",
            },
        ),
        (
            "PHASE",
            {
                "decision_code": "SUPPORTED",
                "supporting_evidence_refs": [],
                "unresolved_facts": [],
                "challenge_code": "NOT_APPLICABLE",
            },
        ),
        (
            "EVIDENCE",
            {
                "decision_code": "SUPPORTED",
                "supporting_evidence_refs": [],
                "unresolved_facts": [],
                "challenge_code": "NOT_APPLICABLE",
            },
        ),
        (
            "CODE",
            {
                "decision_code": "TOTALLY_UNKNOWN",
                "supporting_evidence_refs": [],
                "unresolved_facts": [],
                "challenge_code": "NOT_APPLICABLE",
            },
        ),
    ],
)
def test_task_owned_contract_rejects_cross_task_phase_evidence_and_code_drift(
    mutation: str,
    reply: dict[str, JsonValue],
) -> None:
    """Every task contract is closed before transport or strict decode."""
    profiles = exact_semantic_profiles()
    profile = profiles.profiles[0]
    request = _semantic_request(profile.profile_id, profile.task)
    if mutation == "TASK":
        request = replace(request, task=profiles.profiles[1].task)
    elif mutation == "PHASE":
        request = replace(request, phase="CHALLENGE")
    elif mutation == "EVIDENCE":
        request = replace(request, evidence_bytes=b"x" * (profile.evidence_budget_bytes + 1))
    transport = _ModelTransport(reply)
    runner = compose_admitted_azure_semantic_runner(
        profiles,
        _counter(profiles),
        AzureDeployment(
            "https://example.openai.azure.com",
            profile.deployment_name,
            profile.api_contract,
            "k",
        ),
        transport,
    )

    with pytest.raises(ProcessingError):
        runner.invoke(profile, request)

    assert len(transport.calls) == (1 if mutation == "CODE" else 0)


def test_aggregate_budget_is_rejected_before_the_first_batch_transport() -> None:
    """A batch cannot reset quota or cost accounting for each request."""
    profiles = exact_semantic_profiles()
    profile = profiles.profiles[0]
    transport = _ModelTransport(
        {
            "decision_code": "SUPPORTED",
            "supporting_evidence_refs": [],
            "unresolved_facts": [],
            "challenge_code": "NOT_APPLICABLE",
        }
    )
    runner = compose_admitted_azure_semantic_runner(
        profiles,
        _counter(profiles),
        AzureDeployment(
            "https://example.openai.azure.com",
            profile.deployment_name,
            profile.api_contract,
            "k",
        ),
        transport,
    )
    requests = tuple(
        (
            profile,
            replace(
                _semantic_request(profile.profile_id, profile.task), request_id=f"request-{index}"
            ),
        )
        for index in range(profiles.request_quota + 1)
    )

    with pytest.raises(ProcessingError):
        runner.invoke_batch(requests)

    assert transport.calls == []


def test_every_batch_contract_is_validated_before_the_first_transport() -> None:
    """A later malformed request must not let an earlier request reach Azure."""
    profiles = exact_semantic_profiles()
    profile = profiles.profiles[0]
    transport = _ModelTransport(
        {
            "decision_code": "SUPPORTED",
            "supporting_evidence_refs": [],
            "unresolved_facts": [],
            "challenge_code": "NOT_APPLICABLE",
        }
    )
    runner = compose_admitted_azure_semantic_runner(
        profiles,
        _counter(profiles),
        AzureDeployment(
            "https://example.openai.azure.com",
            profile.deployment_name,
            profile.api_contract,
            "k",
        ),
        transport,
    )
    valid = _semantic_request(profile.profile_id, profile.task)
    invalid = replace(valid, request_id="request-2", phase="CHALLENGE")

    with pytest.raises(ProcessingError, match=r"^SEMANTIC_TASK_PHASE_INVALID$"):
        runner.invoke_batch(((profile, valid), (profile, invalid)))

    assert transport.calls == []


@dataclass(frozen=True, slots=True)
class _Infrastructure:
    """The disabled boundary must need only a vault, never provider material."""

    primary_vault: LocalImmutableVault
    model_provider_credential: _ExplodingCredential
    model_egress_proxy_credential: _ExplodingCredential


def _reference(kind: ReferenceType, prefix: str, digit: str) -> ImmutableReference:
    return ImmutableReference(kind, f"{prefix}_{digit * 48}", f"sha256:{digit * 64}")


def _requirement() -> SemanticCapabilityRequirement:
    return SemanticCapabilityRequirement(
        _reference(ReferenceType.WORKFLOW_PROFILE, "wap", "1"),
        "LEGAL_PROCESSING_WORKER",
        "generative_llm_provider",
        "HK_LATER_TREATMENT_DISCOVERY",
        "2026-08-27T00:00:00Z",
    )


def _evidence(
    requirement: SemanticCapabilityRequirement | None = None,
) -> CurrentSemanticCapabilityEvidence:
    expected = requirement or _requirement()
    return CurrentSemanticCapabilityEvidence(
        expected.profile_ref,
        expected.profile_ref.fingerprint,
        expected.application,
        expected.role,
        expected.task,
        expected.cutoff,
        admitted=True,
        valid_from="2026-08-26T00:00:00Z",
        valid_until="2026-08-28T00:00:00Z",
        evidence_ref=_reference(ReferenceType.EVIDENCE, "evi", "2"),
    )


def _infrastructure(root: Path) -> _Infrastructure:
    return _Infrastructure(
        LocalImmutableVault(root, VaultName.PRIMARY),
        _ExplodingCredential(),
        _ExplodingCredential(),
    )


def test_missing_evidence_disables_before_any_provider_credential_or_adapter_is_used(
    tmp_path: Path,
) -> None:
    """Catch a regression that rebuilds the retired hard-coded real-model path."""
    activities = build_activities(
        _infrastructure(tmp_path),
        {
            "ASKLEGAL_ENABLE_REAL_MODEL": "1",
            "ASKLEGAL_HK_V1_LEGISLATION_SPOOL_ROOT": str(tmp_path / "spool"),
        },
    )

    assert isinstance(activities.semantic_runner, DisabledSemanticTaskRunner)
    with pytest.raises(ProcessingError, match=r"^SEMANTIC_CAPABILITY_DISABLED$"):
        activities.analyse_evidence(ActivityContext("synthetic", 1), {})


def test_application_composition_injects_current_evidence_without_creating_an_adapter(
    tmp_path: Path,
) -> None:
    """Catch `build_activities()` bypassing the exact reader boundary."""
    activities = build_activities(
        _infrastructure(tmp_path),
        {"ASKLEGAL_HK_V1_LEGISLATION_SPOOL_ROOT": str(tmp_path / "spool")},
        semantic_requirement=_requirement(),
        semantic_evidence_reader=_Reader(_evidence()),
    )

    assert isinstance(activities.semantic_runner, DisabledSemanticTaskRunner)


@pytest.mark.parametrize(
    "result",
    [
        None,
        replace(_evidence(), admitted=False),
        replace(_evidence(), profile_fingerprint="sha256:" + "3" * 64),
        replace(_evidence(), application="PROMOTION_WORKER"),
        replace(_evidence(), role="embedding_provider"),
        replace(_evidence(), task="HK_REGULATORY_RECORD_ANALYSIS"),
        replace(_evidence(), cutoff="2026-08-26T00:00:00Z"),
        replace(_evidence(), valid_until="2026-08-27T00:00:00Z"),
        replace(
            _evidence(),
            profile_ref=_reference(ReferenceType.WORKFLOW_PROFILE, "wap", "3"),
        ),
        (_evidence(),),
    ],
)
def test_unadmitted_or_mismatched_current_evidence_never_enables_a_semantic_runner(
    result: object,
    tmp_path: Path,
) -> None:
    """Catch every evidence branch that could otherwise become a provider capability."""
    activities = build_activities(
        _infrastructure(tmp_path),
        {"ASKLEGAL_HK_V1_LEGISLATION_SPOOL_ROOT": str(tmp_path / "spool")},
        semantic_requirement=_requirement(),
        semantic_evidence_reader=_Reader(result),
    )

    assert isinstance(activities.semantic_runner, DisabledSemanticTaskRunner)
    with pytest.raises(ProcessingError, match=r"^SEMANTIC_CAPABILITY_DISABLED$"):
        activities.analyse_evidence(ActivityContext("synthetic", 1), {})


def test_direct_or_replaced_evidence_never_becomes_adapter_authority() -> None:
    """Catch treating a self-fingerprinted local value as current provider evidence."""
    direct = compose_semantic_runner(_requirement(), _Reader(_evidence()))
    replaced = compose_semantic_runner(_requirement(), _Reader(replace(_evidence())))

    assert isinstance(direct, DisabledSemanticTaskRunner)
    assert isinstance(replaced, DisabledSemanticTaskRunner)


def test_subclassed_or_container_evidence_never_becomes_adapter_authority() -> None:
    """Catch accepting a callback-controlled type or container as exact evidence."""

    class _EvidenceSubclass(CurrentSemanticCapabilityEvidence):
        pass

    direct = _evidence()
    subclassed = _EvidenceSubclass(
        direct.profile_ref,
        direct.profile_fingerprint,
        direct.application,
        direct.role,
        direct.task,
        direct.cutoff,
        direct.admitted,
        direct.valid_from,
        direct.valid_until,
        direct.evidence_ref,
    )

    assert isinstance(
        compose_semantic_runner(_requirement(), _Reader(subclassed)), DisabledSemanticTaskRunner
    )
    assert isinstance(
        compose_semantic_runner(_requirement(), _Reader([direct])), DisabledSemanticTaskRunner
    )


def test_reader_receives_a_snapshot_and_cannot_change_the_required_cutoff() -> None:
    """Catch a callback mutating its input before evidence comparison."""
    requirement = _requirement()

    class _MutatingReader:
        def read_current(self, requirement: SemanticCapabilityRequirement) -> object:
            assert requirement is not original
            object.__setattr__(requirement, "cutoff", "2099-01-01T00:00:00Z")
            return replace(_evidence(original), cutoff=requirement.cutoff)

    original = requirement
    runner = compose_semantic_runner(original, _MutatingReader())

    assert requirement.cutoff == "2026-08-27T00:00:00Z"
    assert isinstance(runner, DisabledSemanticTaskRunner)


def test_ordinary_reader_error_leaves_the_runner_disabled() -> None:
    """Catch a reader failure escaping into a permissive fallback or real adapter path."""

    class _FailingReader:
        def read_current(self, requirement: SemanticCapabilityRequirement) -> object:
            del requirement
            message = "unavailable"
            raise ValueError(message)

    assert isinstance(
        compose_semantic_runner(_requirement(), _FailingReader()), DisabledSemanticTaskRunner
    )


@pytest.mark.parametrize(
    "error",
    [AttributeError("missing"), KeyError("missing"), Exception("ordinary")],
)
def test_every_ordinary_reader_exception_stays_disabled_at_the_activity_boundary(
    error: Exception,
    tmp_path: Path,
) -> None:
    """Catch a narrowed wrapper letting common reader failures escape unnormalized."""

    class _FailingReader:
        def read_current(self, requirement: SemanticCapabilityRequirement) -> object:
            del requirement
            raise error

    activities = build_activities(
        _infrastructure(tmp_path),
        {"ASKLEGAL_HK_V1_LEGISLATION_SPOOL_ROOT": str(tmp_path / "spool")},
        semantic_requirement=_requirement(),
        semantic_evidence_reader=_FailingReader(),
    )

    assert isinstance(activities.semantic_runner, DisabledSemanticTaskRunner)
    with pytest.raises(ProcessingError, match=r"^SEMANTIC_CAPABILITY_DISABLED$"):
        activities.analyse_evidence(ActivityContext("synthetic", 1), {})


def test_exact_class_evidence_shell_with_missing_fields_stays_disabled() -> None:
    """Catch a raw AttributeError when a reader returns an uninitialized exact class."""
    shell = object.__new__(CurrentSemanticCapabilityEvidence)

    assert isinstance(
        compose_semantic_runner(_requirement(), _Reader(shell)), DisabledSemanticTaskRunner
    )


def test_exact_class_reference_shell_with_missing_fields_stays_disabled() -> None:
    """Catch a raw AttributeError from an uninitialized immutable-reference leaf."""
    malformed = object.__new__(ImmutableReference)
    result = replace(_evidence(), evidence_ref=malformed)

    assert isinstance(
        compose_semantic_runner(_requirement(), _Reader(result)), DisabledSemanticTaskRunner
    )


@pytest.mark.parametrize("error", [KeyboardInterrupt(), SystemExit(2)])
def test_reader_base_exception_is_not_relabelled_as_disabled_evidence(
    error: BaseException,
) -> None:
    """Catch an overbroad callback wrapper that swallows process-control signals."""

    class _InterruptingReader:
        def read_current(self, requirement: SemanticCapabilityRequirement) -> object:
            del requirement
            raise error

    with pytest.raises(type(error)):
        compose_semantic_runner(_requirement(), _InterruptingReader())
