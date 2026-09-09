"""Task 6A unwired provider-disabled workflow tests."""

import ast
import json
from hashlib import sha256
from pathlib import Path

import asklegal_legal_processing_worker.v1_infrastructure as infrastructure_module
import asklegal_legal_processing_worker.v1_pipeline as pipeline_module
import pytest
from _v1_semantic_profile_fixture import exact_semantic_profiles
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_legal_processing_worker.hk_case_workflow import (
    HKCaseWorkflowStatus,
    admit_complete_cases_manifest_for_withheld_work,
    withhold_hk_case_work,
)
from asklegal_management_register_ports.hk_case_work import (
    HKCaseWorkCheckpoint,
    HKCaseWorkCheckpointFactory,
    HKCaseWorkError,
    HKCaseWorkErrorCode,
    HKCaseWorkRequest,
    HKCaseWorkStage,
    InMemoryHKCaseWorkCheckpointStore,
    build_hk_case_work_identity,
    canonical_hk_case_work_checkpoint,
)

_FP = "sha256:" + "a" * 64
_TASK5_BLOCKERS = (
    "AUTHENTIC_INVENTORY_NOT_ADMITTED",
    "CURRENT_AUTHORITY_NOT_ESTABLISHED",
    "REGISTER_IDENTITY_ISSUANCE_UNAVAILABLE",
    "SEMANTIC_WORKFLOW_NOT_ADMITTED",
)


def _request() -> HKCaseWorkRequest:
    return HKCaseWorkRequest(
        "hk-cases-work/v1",
        "cycle:a",
        _FP,
        "accounting:a",
        _FP,
        "withholding:a",
        _FP,
        "listing-a",
        HKCaseWorkStage.PROPOSITION_DECISION,
        _FP,
        _FP,
    )


def test_task6a_returns_only_disabled_negative_scheduler_primitives() -> None:
    """The result is bounded opaque accounting, never processed work or release output."""
    result = withhold_hk_case_work(_request(), InMemoryHKCaseWorkCheckpointStore())
    assert result == {
        "status": "WITHHELD_NOT_PROCESSED",
        "reason": "SEMANTIC_CAPABILITY_DISABLED",
        "work_item_id": result["work_item_id"],
        "checkpoint_fingerprint": result["checkpoint_fingerprint"],
        "blocker_codes": (*_TASK5_BLOCKERS, "SEMANTIC_CAPABILITY_DISABLED"),
        "semantic_invocation_count": 0,
    }
    assert all(type(value) in (str, int, tuple) for value in result.values())
    blocker_codes = result["blocker_codes"]
    assert type(blocker_codes) is tuple
    assert all(type(code) is str and len(code) <= 512 for code in blocker_codes)
    assert not any(
        word in key
        for key in result
        for word in ("ready", "release", "candidate", "completed", "result", "judgment", "prompt")
    )


def test_complete_cases_manifest_can_enter_only_the_provider_disabled_work_boundary() -> None:
    """A partial acquisition manifest must never be treated as processable Case work."""
    body = {
        "cycle_id": "cyc_cases_1",
        "discrepancy_refs": [],
        "earliest_decision_date": "1997-07-01",
        "journal_head_fingerprint": _FP,
        "judgment_bundle_refs": ["cases/judgment-bundles/sha256/" + "1" * 64 + ".json"],
        "observation_cutoff": "1997-12-31T00:00:00Z",
        "result": "COMPLETE",
        "year_dispositions": [
            {
                "discovered_judgments": 1,
                "final_page": 1,
                "first_in_scope_date": "1997-07-01",
                "result": "COMPLETE",
                "retryable_items": 0,
                "verified_judgments": 1,
                "verified_listing_pages": 1,
                "year": 1997,
            }
        ],
    }
    body["fingerprint"] = "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()

    accepted = admit_complete_cases_manifest_for_withheld_work(
        canonicalize(checked_json_value(body))
    )

    assert accepted["status"] == "WITHHELD_NOT_PROCESSED"
    assert accepted["semantic_invocation_count"] == 0
    body["result"] = "INCOMPLETE_RETRYABLE"
    with pytest.raises(ValueError, match="ACQUISITION_MANIFEST_INVALID"):
        admit_complete_cases_manifest_for_withheld_work(
            json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
        )


def test_task5_withholding_is_preserved_not_reinterpreted() -> None:
    """All four Task 5 blockers survive and Task 6 adds only its disabled blocker."""
    result = withhold_hk_case_work(_request(), InMemoryHKCaseWorkCheckpointStore())
    blocker_codes = result["blocker_codes"]
    assert type(blocker_codes) is tuple
    assert blocker_codes[:-1] == _TASK5_BLOCKERS
    assert result["status"] != "WITHHELD_NOT_RELEASED"
    assert "AUTHENTIC_INVENTORY_NOT_ADMITTED" in blocker_codes


def test_recreated_service_replays_exact_checkpoint_with_zero_semantic_calls() -> None:
    """A retained port yields the same deterministic negative result after recreation."""
    store = InMemoryHKCaseWorkCheckpointStore()
    first = withhold_hk_case_work(_request(), store)
    restarted = withhold_hk_case_work(_request(), store)
    assert restarted == first
    assert restarted["semantic_invocation_count"] == 0


class _MutatingStore(InMemoryHKCaseWorkCheckpointStore):
    def __init__(self, request: HKCaseWorkRequest, *, restore: bool) -> None:
        super().__init__()
        self._request = request
        self._restore = restore

    def record_checkpoint(
        self, checkpoint: HKCaseWorkCheckpoint, expected_canonical: bytes
    ) -> HKCaseWorkCheckpoint:
        object.__setattr__(self._request, "listing_id", "listing-b")
        if self._restore:
            object.__setattr__(self._request, "listing_id", "listing-a")
        return super().record_checkpoint(checkpoint, expected_canonical)


def test_input_is_snapshotted_before_store_callback_and_permanent_drift_rejects() -> None:
    """A callback cannot rewrite the work identity to match later caller state."""
    request = _request()
    with pytest.raises(HKCaseWorkError) as caught:
        withhold_hk_case_work(request, _MutatingStore(request, restore=False))
    assert caught.value.code is HKCaseWorkErrorCode.REPLAY_MISMATCH


def test_transient_input_mutation_cannot_influence_detached_result() -> None:
    """A->B->A mutation observes only the phase-one A snapshot."""
    request = _request()
    baseline = withhold_hk_case_work(request, InMemoryHKCaseWorkCheckpointStore())
    transient = withhold_hk_case_work(request, _MutatingStore(request, restore=True))
    assert transient == baseline


def _replacement_checkpoint() -> HKCaseWorkCheckpoint:
    request = _request()
    object.__setattr__(request, "listing_id", "listing-b")
    identity = build_hk_case_work_identity(request)
    return HKCaseWorkCheckpointFactory().issue_blocked(
        identity,
        (*_TASK5_BLOCKERS, "SEMANTIC_CAPABILITY_DISABLED"),
    )


class _ResealingStore(InMemoryHKCaseWorkCheckpointStore):
    def __init__(self, replacement: HKCaseWorkCheckpoint, *, restore: bool = False) -> None:
        super().__init__()
        self._replacement = replacement
        self._restore = restore

    def record_checkpoint(
        self, checkpoint: HKCaseWorkCheckpoint, expected_canonical: bytes
    ) -> HKCaseWorkCheckpoint:
        original = (
            checkpoint.identity,
            checkpoint.blocker_codes,
            checkpoint.checkpoint_fingerprint,
        )
        object.__setattr__(checkpoint, "identity", self._replacement.identity)
        object.__setattr__(checkpoint, "blocker_codes", self._replacement.blocker_codes)
        object.__setattr__(
            checkpoint, "checkpoint_fingerprint", self._replacement.checkpoint_fingerprint
        )
        if self._restore:
            object.__setattr__(checkpoint, "identity", original[0])
            object.__setattr__(checkpoint, "blocker_codes", original[1])
            object.__setattr__(checkpoint, "checkpoint_fingerprint", original[2])
        return super().record_checkpoint(checkpoint, expected_canonical)


def test_port_cannot_coherently_reseal_work_identity_or_adopt_replacement() -> None:
    """A callback's valid B identity cannot replace the private captured A checkpoint."""
    request = _request()
    expected_id = build_hk_case_work_identity(request).work_item_id
    replacement = _replacement_checkpoint()
    store = _ResealingStore(replacement)
    with pytest.raises(HKCaseWorkError) as caught:
        withhold_hk_case_work(request, store)
    assert caught.value.code in (
        HKCaseWorkErrorCode.CHECKPOINT_INVALID,
        HKCaseWorkErrorCode.REPLAY_MISMATCH,
    )
    for work_item_id in (expected_id, replacement.identity.work_item_id):
        with pytest.raises(HKCaseWorkError) as missing:
            store.get_checkpoint(work_item_id)
        assert missing.value.code is HKCaseWorkErrorCode.CHECKPOINT_MISSING


class _BlockerResealingStore(InMemoryHKCaseWorkCheckpointStore):
    def record_checkpoint(
        self, checkpoint: HKCaseWorkCheckpoint, expected_canonical: bytes
    ) -> HKCaseWorkCheckpoint:
        document = json.loads(canonical_hk_case_work_checkpoint(checkpoint))
        document["blocker_codes"] = ["SEMANTIC_CAPABILITY_DISABLED"]
        document.pop("checkpoint_fingerprint")
        encoded = json.dumps(
            document, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        object.__setattr__(checkpoint, "blocker_codes", ("SEMANTIC_CAPABILITY_DISABLED",))
        object.__setattr__(
            checkpoint, "checkpoint_fingerprint", f"sha256:{sha256(encoded).hexdigest()}"
        )
        return super().record_checkpoint(checkpoint, expected_canonical)


def test_port_cannot_remove_task5_blockers_and_coherently_reseal() -> None:
    """A matching replacement digest cannot omit any Task 5 withholding blocker."""
    request = _request()
    expected_id = build_hk_case_work_identity(request).work_item_id
    store = _BlockerResealingStore()
    with pytest.raises(HKCaseWorkError) as caught:
        withhold_hk_case_work(request, store)
    assert caught.value.code in (
        HKCaseWorkErrorCode.CHECKPOINT_INVALID,
        HKCaseWorkErrorCode.REPLAY_MISMATCH,
    )
    with pytest.raises(HKCaseWorkError) as missing:
        store.get_checkpoint(expected_id)
    assert missing.value.code is HKCaseWorkErrorCode.CHECKPOINT_MISSING


def test_port_transient_reseal_restoration_cannot_influence_output() -> None:
    """A->B->A checkpoint mutation observes and persists only captured A facts."""
    baseline = withhold_hk_case_work(_request(), InMemoryHKCaseWorkCheckpointStore())
    transient = withhold_hk_case_work(
        _request(), _ResealingStore(_replacement_checkpoint(), restore=True)
    )
    assert transient == baseline


def test_public_checkpoint_copy_cannot_substitute_valid_b(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expected A, port input, persistence, and result never derive from a public copy hook."""
    request = _request()
    expected_id = build_hk_case_work_identity(request).work_item_id
    replacement = _replacement_checkpoint()

    def substitute(checkpoint: HKCaseWorkCheckpoint) -> HKCaseWorkCheckpoint:
        del checkpoint
        return replacement

    monkeypatch.setattr(HKCaseWorkCheckpoint, "__copy__", substitute)
    store = InMemoryHKCaseWorkCheckpointStore()
    result = withhold_hk_case_work(request, store)
    assert result["work_item_id"] == expected_id
    assert store.get_checkpoint(expected_id).identity.work_item_id == expected_id
    with pytest.raises(HKCaseWorkError) as missing:
        store.get_checkpoint(replacement.identity.work_item_id)
    assert missing.value.code is HKCaseWorkErrorCode.CHECKPOINT_MISSING


def test_transient_public_copy_substitution_cannot_influence_a(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A copy hook's B-then-A sequence is never observed by snapshot derivation."""
    request = _request()
    expected_id = build_hk_case_work_identity(request).work_item_id
    first = _replacement_checkpoint()
    a_factory = HKCaseWorkCheckpointFactory()
    a_value = a_factory.issue_blocked(
        build_hk_case_work_identity(request),
        (*_TASK5_BLOCKERS, "SEMANTIC_CAPABILITY_DISABLED"),
    )
    calls = 0

    def transient(checkpoint: HKCaseWorkCheckpoint) -> HKCaseWorkCheckpoint:
        nonlocal calls
        del checkpoint
        calls += 1
        return first if calls == 1 else a_value

    monkeypatch.setattr(HKCaseWorkCheckpoint, "__copy__", transient)
    store = InMemoryHKCaseWorkCheckpointStore()
    result = withhold_hk_case_work(request, store)
    assert result["work_item_id"] == expected_id
    assert calls == 0
    assert store.get_checkpoint(expected_id).identity.work_item_id == expected_id


def test_public_copy_baseexception_hook_is_not_invoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unused public reconstruction hook cannot become a hidden pre-I/O callback."""

    class CopyHookInvoked(BaseException):
        pass

    def explode(checkpoint: HKCaseWorkCheckpoint) -> HKCaseWorkCheckpoint:
        del checkpoint
        raise CopyHookInvoked

    monkeypatch.setattr(HKCaseWorkCheckpoint, "__copy__", explode)
    result = withhold_hk_case_work(_request(), InMemoryHKCaseWorkCheckpointStore())
    assert result["status"] == "WITHHELD_NOT_PROCESSED"


class _OrdinaryFailureStore(InMemoryHKCaseWorkCheckpointStore):
    def record_checkpoint(
        self, checkpoint: HKCaseWorkCheckpoint, expected_canonical: bytes
    ) -> HKCaseWorkCheckpoint:
        del checkpoint, expected_canonical
        details = "hostile diagnostics"
        raise RuntimeError(details)


class _ProcessControlFailure(BaseException):
    pass


class _ProcessControlStore(InMemoryHKCaseWorkCheckpointStore):
    def record_checkpoint(
        self, checkpoint: HKCaseWorkCheckpoint, expected_canonical: bytes
    ) -> HKCaseWorkCheckpoint:
        del checkpoint, expected_canonical
        raise _ProcessControlFailure


def test_ordinary_port_failure_is_closed_without_diagnostics() -> None:
    """Ordinary adapter errors become one sanitized closed workflow failure."""
    with pytest.raises(HKCaseWorkError) as caught:
        withhold_hk_case_work(_request(), _OrdinaryFailureStore())
    assert caught.value.code is HKCaseWorkErrorCode.REPLAY_MISMATCH
    assert "hostile" not in str(caught.value)


def test_process_control_baseexception_remains_visible() -> None:
    """Process-control failures are never normalized into ordinary business errors."""
    with pytest.raises(_ProcessControlFailure):
        withhold_hk_case_work(_request(), _ProcessControlStore())


def test_request_subclass_and_malformed_refs_fail_closed() -> None:
    """Only exact request and bounded opaque references cross the worker boundary."""

    class RequestSubclass(HKCaseWorkRequest):
        pass

    request = _request()
    subclass = RequestSubclass(
        *(object.__getattribute__(request, name) for name in request.__slots__)
    )
    malformed = _request()
    object.__setattr__(malformed, "source_cycle_ref", "x" * 513)
    for invalid in (subclass, malformed):
        with pytest.raises(HKCaseWorkError) as caught:
            withhold_hk_case_work(invalid, InMemoryHKCaseWorkCheckpointStore())
        assert caught.value.code is HKCaseWorkErrorCode.REQUEST_INVALID


def test_worker_module_has_no_provider_source_or_positive_runtime_boundary() -> None:
    """The unwired module cannot import any effect-capable or positive-output package."""
    assert tuple(HKCaseWorkflowStatus) == (HKCaseWorkflowStatus.WITHHELD_NOT_PROCESSED,)
    tree = ast.parse(
        Path(__file__)
        .parents[1]
        .joinpath("src/asklegal_legal_processing_worker/hk_case_workflow.py")
        .read_text(encoding="utf-8")
    )
    imports = {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    forbidden = ("azure", "source_connectors", "corpus", "promotion", "durabletask", "processing")
    assert not any(any(word in name for word in forbidden) for name in imports)


def test_verified_cases_batch_prepares_one_deterministic_provider_disabled_request(
    tmp_path: Path,
) -> None:
    """Mutation caught: verified Case work can otherwise be lost until full reconciliation."""
    evidence_body = canonicalize(
        checked_json_value(
            {
                "language": "en",
                "subject_id": "facv-1-paragraph-7",
                "text": "The inert verified judgment paragraph.",
            }
        )
    )
    evidence_fingerprint = f"sha256:{sha256(evidence_body).hexdigest()}"
    evidence_type = pipeline_module.VerifiedBatchEvidence
    input_type = pipeline_module.VerifiedBatchInput
    store = infrastructure_module.LocalVerifiedBatchStore(tmp_path / "prepared")
    semantic_profiles = exact_semantic_profiles()
    request = input_type(
        material_family="CASES",
        scope_id="HK-CASE-BINDING-POST-1997",
        batch_id="cases-facv-1",
        observation_cutoff="1997-12-31T00:00:00Z",
        acquisition_manifest_fingerprint="sha256:" + "a" * 64,
        journal_head_fingerprint="sha256:" + "b" * 64,
        semantic_profiles=semantic_profiles,
        evidence_items=(
            evidence_type(
                evidence_ref="evidence/cases/facv-1-paragraph-7",
                content=evidence_body,
                fingerprint=evidence_fingerprint,
            ),
        ),
    )

    prepared = pipeline_module.prepare_verified_batch(request, store)
    document = parse_json_bytes(prepared.content, max_bytes=1_000_000)
    assert type(document) is dict
    model_requests = document["model_requests"]
    assert type(model_requests) is list
    first_request = model_requests[0]
    assert type(first_request) is dict

    assert document["material_family"] == "CASES"
    assert document["scope_id"] == "HK-CASE-BINDING-POST-1997"
    assert document["provider_invocation_count"] == 0
    assert document["release_state"] == "WITHHELD_PENDING_TWO_FAMILY_RECONCILIATION"
    assert document["model_requests"] == [
        {
            "evidence_fingerprint": evidence_fingerprint,
            "evidence_ref": "evidence/cases/facv-1-paragraph-7",
            "request_id": first_request["request_id"],
            "semantic_profile_fingerprint": semantic_profiles.fingerprint,
            "subject_id": "facv-1-paragraph-7",
        }
    ]
    assert (
        store.read_exact(prepared.artifact_ref, prepared.artifact_fingerprint) == prepared.content
    )
