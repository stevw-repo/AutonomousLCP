"""M6 exact replacement-target promotion and failure proofs."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from asklegal_contracts import SchemaRegistry, fingerprint, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value
from asklegal_corpus import (
    CorpusError,
    CorpusReleaseInput,
    CoverageScopeStatus,
    CoverageState,
    CoverageWarning,
    DesiredStateInventory,
    ServingRecord,
    SourceCoverageCycleBinding,
    compose_desired_state,
    freeze_corpus_release,
    freeze_coverage_status,
    freeze_v1_coverage_status,
)
from asklegal_domain import (
    ApplicationCode,
    ContractReference,
    DeclaredCompensation,
    DestinationClass,
    EffectCapability,
    EffectType,
    ImmutableReference,
    NoCompensation,
    ReferenceType,
    RetryClass,
    StopCondition,
)
from asklegal_management_register_ports import (
    ApprovalError,
    ApprovalErrorCode,
    InMemoryApprovalRegister,
    ManifestSnapshot,
    ReviewerPrincipal,
)
from asklegal_promotion import (
    EmbeddedVector,
    EmbeddingPort,
    EmbeddingProfile,
    EmbeddingProfileInput,
    EmbeddingRequest,
    EmbeddingRequestInput,
    LocalBackupStore,
    LocalCoverageStore,
    LocalEmbeddingAdapter,
    LocalFailurePlan,
    LocalRoutingStore,
    LocalServingTargetStore,
    PromotionActionAuthority,
    PromotionError,
    PromotionErrorCode,
    PromotionExecutionResult,
    PromotionManifest,
    PromotionPlan,
    TargetDefinition,
    embedding_request,
    freeze_embedding_profile,
    freeze_promotion_manifest,
    freeze_v1_promotion_manifest,
    pinecone_index_name,
    promotion_approval_snapshot_from_bytes,
    promotion_manifest_bytes,
)
from asklegal_promotion_worker import (
    PromotionDependencies,
    PromotionExecutionContext,
    PromotionService,
)

_NOW = "2026-08-16T00:00:00Z"
_AT = "2026-08-16T01:00:00Z"
_BASE = "srv_" + "a" * 48
_CANDIDATE = "srv_" + "b" * 48
_STATE_FP = "sha256:" + "b" * 64
_PREDICATES = (("configuration", "1.0.0", "sha256:" + "c" * 64),)


def _action_contract(name: str, digit: str) -> ContractReference:
    return ContractReference(name, "1.0.0", "sha256:" + digit * 64)


def _action_reference(
    ref_type: ReferenceType,
    ref_id: str,
    ref_fingerprint: str,
) -> ImmutableReference:
    return ImmutableReference(ref_type, ref_id, ref_fingerprint)


def _actions(
    desired: DesiredStateInventory,
    profile: EmbeddingProfile,
) -> tuple[PromotionActionAuthority, ...]:
    desired_ref = _action_reference(
        ReferenceType.DESIRED_STATE_INVENTORY,
        desired.inventory_id,
        desired.inventory_fingerprint,
    )
    profile_ref = _action_reference(
        ReferenceType.EMBEDDING_PROFILE,
        profile.profile_id,
        profile.profile_fingerprint,
    )
    state_ref = _action_reference(ReferenceType.SERVING_STATE, _CANDIDATE, _STATE_FP)
    stops = tuple(StopCondition)
    specifications = (
        (
            "EMBED_RECORDS",
            EffectType.EMBEDDING_PROVIDER_CALL,
            EffectCapability.CALL_EMBEDDING_PROVIDER,
            DestinationClass.EMBEDDING_PROVIDER,
            (desired_ref, profile_ref),
            RetryClass.RECONCILE_BEFORE_RETRY,
            3,
            NoCompensation(),
        ),
        (
            "BUILD_TARGET",
            EffectType.PINECONE_MUTATION,
            EffectCapability.MUTATE_PINECONE,
            DestinationClass.SERVING_TARGET,
            (desired_ref, profile_ref, state_ref),
            RetryClass.RECONCILE_BEFORE_RETRY,
            3,
            NoCompensation(),
        ),
        (
            "CREATE_BACKUPS",
            EffectType.BACKUP_MUTATION,
            EffectCapability.MANAGE_BACKUP,
            DestinationClass.BACKUP_STORE,
            (state_ref,),
            RetryClass.RECONCILE_BEFORE_RETRY,
            2,
            NoCompensation(),
        ),
        (
            "ACTIVATE_ROUTING",
            EffectType.ROUTING_ACTIVATION,
            EffectCapability.ACTIVATE_ROUTING,
            DestinationClass.ROUTING_TARGET,
            (state_ref,),
            RetryClass.NEVER,
            1,
            DeclaredCompensation(_action_contract("asklegal.routing-reverse-swap", "9")),
        ),
    )
    return tuple(
        PromotionActionAuthority(
            sequence,
            action_id,
            effect_type,
            ApplicationCode.PROMOTION_WORKER,
            action_id,
            input_refs,
            "sha256:" + str(sequence) * 64,
            capability,
            _action_reference(
                ReferenceType.CAPABILITY_PROFILE,
                "cap_" + str(sequence) * 48,
                "sha256:" + str(sequence + 4) * 64,
            ),
            destination,
            f"synthetic-{sequence}-{action_id.lower()}",
            retry_class,
            ceiling,
            "2026-08-17T00:00:00Z",
            stops,
            _action_contract(f"asklegal.{action_id.lower()}-precondition", "a"),
            _action_contract(f"asklegal.{action_id.lower()}-postcondition", "b"),
            compensation,
        )
        for sequence, (
            action_id,
            effect_type,
            capability,
            destination,
            input_refs,
            retry_class,
            ceiling,
            compensation,
        ) in enumerate(specifications, start=1)
    )


def _profile(*, cost_limit: int = 10_000) -> EmbeddingProfile:
    return freeze_embedding_profile(
        EmbeddingProfileInput(
            "LOCAL_FAKE",
            "LOCAL_ONLY",
            "LOCAL_ONLY",
            "synthetic-embedding",
            "synthetic-model",
            "1.0.0",
            "local-v1",
            "UTF8_BYTES",
            4,
            "FLOAT32",
            "NONE",
            "COSINE",
            1_000,
            cost_limit,
            "2027-01-01T00:00:00Z",
            ("dev",),
        )
    )


def _manifest(
    *,
    profile: EmbeddingProfile | None = None,
    retirements: tuple[str, ...] = (),
) -> PromotionManifest:
    records = tuple(
        ServingRecord(
            "rec_" + identity * 48,
            f"Synthetic legal text {identity}.",
            "ZZZ",
            "zzz",
            "TEST_LEGAL_MATERIAL",
            "synthetic-source",
            "Synthetic authority only.",
            "art_" + identity * 48,
            ("evi_" + identity * 48,),
        )
        for identity in ("1", "2")
    )
    release = freeze_corpus_release(
        CorpusReleaseInput("scope-a", _NOW, ("evi_" + "f" * 48,), ("val_" + "f" * 48,)),
        records,
    )
    desired = compose_desired_state(
        ("scope-a",), (release,), target_key="zzz-test", observation_cutoff=_NOW
    )
    coverage = freeze_coverage_status(
        _CANDIDATE,
        _NOW,
        ("scope-a",),
        (
            CoverageScopeStatus(
                "scope-a", CoverageState.CURRENT, _NOW, (), (), (), CoverageWarning.NONE
            ),
        ),
    )
    selected_profile = profile or _profile()
    return freeze_promotion_manifest(
        PromotionPlan(
            "dev",
            "zzz",
            "20260816",
            _NOW,
            "2026-08-17T00:00:00Z",
            _BASE,
            _CANDIDATE,
            _STATE_FP,
            _BASE,
            desired,
            coverage,
            selected_profile,
            _PREDICATES,
            2,
            "project1",
            "1.0.0",
            _actions(desired, selected_profile),
            retirements,
        )
    )


def _plan_from_manifest(manifest: PromotionManifest) -> PromotionPlan:
    """Rebuild one immutable plan so the alternate V1 freeze can be exercised."""
    return PromotionPlan(
        manifest.environment,
        manifest.jurisdiction,
        manifest.freeze_date,
        manifest.valid_from,
        manifest.valid_until,
        manifest.base_serving_state_id,
        manifest.candidate_serving_state_id,
        manifest.candidate_serving_state_fingerprint,
        manifest.rollback_serving_state_id,
        manifest.desired_state,
        manifest.coverage_status,
        manifest.embedding_profile,
        manifest.validity_predicates,
        manifest.batch_size,
        manifest.project_id,
        manifest.action_contract_version,
        manifest.actions,
        manifest.exact_retirement_target_ids,
    )


def test_canonical_manifest_bytes_recover_the_exact_approval_snapshot() -> None:
    """Review facts come from the executable bytes, not an identity-only wrapper."""
    manifest = _manifest()
    content = promotion_manifest_bytes(manifest)

    snapshot = promotion_approval_snapshot_from_bytes(
        content,
        expected_manifest_id=manifest.manifest_id,
        expected_fingerprint=manifest.fingerprint,
    )

    assert snapshot.manifest_id == manifest.manifest_id
    assert snapshot.fingerprint == manifest.fingerprint
    assert snapshot.expected_base_serving_state_id == manifest.base_serving_state_id
    assert snapshot.candidate_serving_state_id == manifest.candidate_serving_state_id
    assert snapshot.validity_predicates == manifest.validity_predicates

    document = parse_json_bytes(content, max_bytes=1_000_000)
    assert isinstance(document, dict)
    assert document["action_contract_version"] == "1.0.0"
    assert "actions" in document
    assert "action_ids" not in document
    assert "capability_enabled" not in document


def test_manifest_rejects_effect_binding_or_profile_input_invention() -> None:
    """Freeze cannot repair a wrong capability or stale action input at runtime."""
    manifest = _manifest()
    plan = _plan_from_manifest(manifest)
    first = plan.actions[0]
    wrong_capability = replace(first, required_capability=EffectCapability.MANAGE_BACKUP)
    with pytest.raises(PromotionError, match="action effect binding"):
        freeze_promotion_manifest(replace(plan, actions=(wrong_capability, *plan.actions[1:])))

    changed_profile = _profile(cost_limit=9_999)
    with pytest.raises(PromotionError, match="action input binding"):
        freeze_promotion_manifest(replace(plan, embedding_profile=changed_profile))


def test_manifest_rejects_missing_stop_or_broadened_never_retry() -> None:
    """Approval bytes cannot omit a stop rule or broaden a one-shot effect."""
    manifest = _manifest()
    plan = _plan_from_manifest(manifest)
    first = plan.actions[0]
    missing_stop = replace(first, stop_conditions=first.stop_conditions[:-1])
    with pytest.raises(PromotionError, match="action completion authority"):
        freeze_promotion_manifest(replace(plan, actions=(missing_stop, *plan.actions[1:])))

    last = plan.actions[-1]
    broadened = replace(last, attempt_ceiling=2)
    with pytest.raises(PromotionError, match="action retry authority"):
        freeze_promotion_manifest(replace(plan, actions=(*plan.actions[:-1], broadened)))


@pytest.mark.parametrize("drift", ["BYTES", "IDENTITY", "FINGERPRINT"])
def test_approval_snapshot_rejects_any_manifest_binding_drift(drift: str) -> None:
    """No changed bytes, identity, or fingerprint can become Review authority."""
    manifest = _manifest()
    content = promotion_manifest_bytes(manifest)
    expected_id = manifest.manifest_id
    expected_fingerprint = manifest.fingerprint
    if drift == "BYTES":
        content += b"\n"
    elif drift == "IDENTITY":
        expected_id = "pmn_" + "0" * 48
    else:
        expected_fingerprint = "sha256:" + "0" * 64

    with pytest.raises(PromotionError) as error:
        promotion_approval_snapshot_from_bytes(
            content,
            expected_manifest_id=expected_id,
            expected_fingerprint=expected_fingerprint,
        )

    assert error.value.code is PromotionErrorCode.MANIFEST_DRIFT


def test_v1_manifest_freeze_requires_complete_nonblocking_source_cycle() -> None:
    """The V1 promotion envelope cannot omit or bypass source-cycle eligibility."""
    legacy = _manifest()
    with pytest.raises(CorpusError, match="source cycle missing"):
        freeze_v1_promotion_manifest(_plan_from_manifest(legacy))

    cycle = SourceCoverageCycleBinding(
        vault="PRIMARY",
        logical_key="poc/report/source-coverage-cycle/full_periodic/" + "a" * 64,
        version_id="v" + "b" * 64,
        fingerprint="sha256:" + "a" * 64,
        byte_length=1024,
        observation_cutoff=_NOW,
        accounting_complete=True,
        release_blocking=False,
        missing_source_ids=(),
        duplicate_source_ids=(),
        gap_source_ids=(),
    )
    coverage = freeze_v1_coverage_status(
        _CANDIDATE,
        _NOW,
        ("scope-a",),
        (
            CoverageScopeStatus(
                "scope-a", CoverageState.CURRENT, _NOW, (), (), (), CoverageWarning.NONE
            ),
        ),
        cycle,
    )
    frozen = freeze_v1_promotion_manifest(
        replace(_plan_from_manifest(legacy), coverage_status=coverage)
    )

    assert frozen.coverage_status.source_cycle == cycle


def _approval(
    manifest: PromotionManifest,
) -> tuple[InMemoryApprovalRegister, str]:
    approvals = InMemoryApprovalRegister({"person-1": frozenset({"PipelineAdministrator"})})
    snapshot = ManifestSnapshot(
        manifest.manifest_id,
        manifest.fingerprint,
        manifest.base_serving_state_id,
        manifest.valid_from,
        manifest.valid_until,
        manifest.validity_predicates,
    )
    result = approvals.decide(
        ReviewerPrincipal(
            "person-1",
            delegated_human=True,
            roles=frozenset({"PipelineAdministrator"}),
        ),
        snapshot,
        decision="APPROVED",
        reason="Reviewed exact synthetic proposal",
        decision_time=_NOW,
    )
    return approvals, result.decision.approval_id


def _service(
    manifest: PromotionManifest,
    *,
    plan: LocalFailurePlan | None = None,
    coverage: LocalCoverageStore | None = None,
    embeddings: EmbeddingPort | None = None,
) -> tuple[
    PromotionService,
    str,
    LocalServingTargetStore,
    LocalRoutingStore,
    LocalBackupStore,
]:
    selected = plan or LocalFailurePlan()
    approvals, approval_id = _approval(manifest)
    targets = LocalServingTargetStore(selected)
    routing = LocalRoutingStore(_BASE, selected)
    backups = LocalBackupStore(selected)
    service = PromotionService(
        PromotionDependencies(
            approvals,
            embeddings or LocalEmbeddingAdapter(selected),
            targets,
            backups,
            routing,
            coverage or LocalCoverageStore(manifest.coverage_status),
        )
    )
    return service, approval_id, targets, routing, backups


def _execute(
    service: PromotionService,
    manifest: PromotionManifest,
    approval_id: str,
    lineage: str = "lin_" + "1" * 48,
) -> PromotionExecutionResult:
    return service.execute(
        manifest,
        approval_id,
        lineage,
        PromotionExecutionContext(_BASE, _PREDICATES, _AT),
    )


def test_complete_replacement_target_is_verified_backed_up_and_cut_over() -> None:
    """The success path performs one complete generation swap and exact replay."""
    manifest = _manifest()
    service, approval_id, targets, routing, backups = _service(manifest)
    result = _execute(service, manifest, approval_id)
    assert result.state == "EXECUTION_SUCCEEDED"
    assert len(result.embedding_receipt_ids) == 2
    assert targets.contains(result.target_name)
    assert routing.active_state_id == _CANDIDATE
    assert len(backups.receipts) == 1
    assert result.native_backup_receipt_ref.startswith("efr_")
    assert result.recovery_receipt_ref.startswith("efr_")
    assert backups.receipts[0].native_verified
    assert backups.receipts[0].recovery_verified
    assert _execute(service, manifest, approval_id) == result


def test_embedding_profile_request_and_receipt_match_normative_contracts() -> None:
    """Provider-bound runtime values serialize without schema drift or extra fields."""
    registry = SchemaRegistry.from_contracts_root(Path(__file__).parents[3] / "contracts")
    profile = _profile()
    profile_value = {
        "schema_id": "asklegal.embedding-profile",
        "schema_version": "1.0.0",
        "embedding_profile_id": profile.profile_id,
        "provider": profile.provider,
        "resource_class": profile.resource_class,
        "geography_class": profile.geography_class,
        "deployment_name": profile.deployment_name,
        "model_id": profile.model_id,
        "model_version": profile.model_version,
        "api_contract": profile.api_contract,
        "tokenizer": profile.tokenizer,
        "dimensions": profile.dimensions,
        "encoding": profile.encoding,
        "normalization": profile.normalization,
        "metric": profile.metric,
        "max_input_tokens": profile.max_input_tokens,
        "cost_limit_microunits": profile.cost_limit_microunits,
        "expires_at": profile.expires_at,
        "stateful_features": profile.stateful_features,
        "allowed_environments": list(profile.allowed_environments),
        "immutable": True,
    }
    profile_json = checked_json_value(profile_value)
    registry.validate(
        profile_json,
        "schemas/promotion-domain.schema.json#/$defs/embedding_profile",
    )
    request = embedding_request(
        EmbeddingRequestInput(
            "rec_" + "1" * 48,
            "sha256:" + "2" * 64,
            "Exact metadata text",
            "art_" + "3" * 48,
            0,
        ),
        profile,
    )
    request_value = {
        "schema_id": "asklegal.embedding-request",
        "schema_version": "1.0.0",
        "embedding_request_id": request.request_id,
        "search_record_id": request.record_id,
        "serving_payload_fingerprint": request.serving_payload_fingerprint,
        "text": request.text,
        "text_fingerprint": request.text_fingerprint,
        "token_count": request.token_count,
        "embedding_profile_ref": {
            "ref_type": "EMBEDDING_PROFILE",
            "ref_id": profile.profile_id,
            "fingerprint": profile.profile_fingerprint,
        },
        "batch_id": request.batch_id,
        "batch_position": request.batch_position,
        "cache_key": request.cache_key,
        "immutable": True,
    }
    request_json = checked_json_value(request_value)
    registry.validate(
        request_json,
        "schemas/promotion-domain.schema.json#/$defs/embedding_request",
    )
    receipt = LocalEmbeddingAdapter().embed(profile, request).receipt
    receipt_value = {
        "schema_id": "asklegal.embedding-receipt",
        "schema_version": "1.0.0",
        "embedding_receipt_id": receipt.receipt_id,
        "embedding_request_ref": {
            "ref_type": "EMBEDDING_REQUEST",
            "ref_id": request.request_id,
            "fingerprint": fingerprint(request_json),
        },
        "provider_request_id": receipt.provider_request_id,
        "vector_count": 1,
        "dimensions": receipt.dimensions,
        "normalized_vector_bytes_fingerprint": receipt.vector_fingerprint,
        "input_tokens": receipt.input_tokens,
        "latency_milliseconds": receipt.latency_milliseconds,
        "result": receipt.result,
        "immutable": True,
    }
    registry.validate(
        checked_json_value(receipt_value),
        "schemas/promotion-domain.schema.json#/$defs/embedding_receipt",
    )


@pytest.mark.parametrize(
    ("plan", "code"),
    [
        (LocalFailurePlan(partial_batch=True), PromotionErrorCode.INVENTORY_MISMATCH),
        (LocalFailurePlan(vector_mismatch=True), PromotionErrorCode.VECTOR_INVALID),
        (LocalFailurePlan(unknown_remote_record=True), PromotionErrorCode.UNKNOWN_REMOTE_RECORD),
        (LocalFailurePlan(retrieval_failure=True), PromotionErrorCode.RETRIEVAL_GATE_FAILED),
        (LocalFailurePlan(backup_failure=True), PromotionErrorCode.BACKUP_FAILED),
        (LocalFailurePlan(recovery_failure=True), PromotionErrorCode.BACKUP_FAILED),
        (
            LocalFailurePlan(routing_cas_loss=True),
            PromotionErrorCode.ROUTING_COMPARE_AND_SET_LOST,
        ),
        (
            LocalFailurePlan(swap_preflight_failure=True),
            PromotionErrorCode.SWAP_PREFLIGHT_FAILED,
        ),
        (LocalFailurePlan(warmup_failure=True), PromotionErrorCode.WARMUP_FAILED),
    ],
)
def test_every_pre_cutover_fault_fails_closed(
    plan: LocalFailurePlan, code: PromotionErrorCode
) -> None:
    """Partial or unverifiable replacement state never becomes active."""
    manifest = _manifest()
    service, approval_id, _targets, routing, _backups = _service(manifest, plan=plan)
    with pytest.raises(PromotionError) as failure:
        _execute(service, manifest, approval_id)
    assert failure.value.code is code
    assert routing.active_state_id == _BASE


def test_lost_ack_is_reconciled_against_exact_remote_state() -> None:
    """A committed batch with a lost acknowledgement is safely recognized."""
    manifest = _manifest()
    service, approval_id, _targets, routing, _backups = _service(
        manifest, plan=LocalFailurePlan(lost_ack_once=True)
    )
    result = _execute(service, manifest, approval_id)
    assert result.state == "EXECUTION_SUCCEEDED"
    assert routing.active_state_id == _CANDIDATE


def test_cost_base_coverage_and_approval_validity_stop_before_effects() -> None:
    """Current admission facts are revalidated before replacement mutation."""
    costly = _manifest(profile=_profile(cost_limit=1))
    service, approval_id, targets, _routing, _backups = _service(costly)
    with pytest.raises(PromotionError) as cost:
        _execute(service, costly, approval_id)
    assert cost.value.code is PromotionErrorCode.COST_LIMIT_EXCEEDED
    assert not targets.contains(
        pinecone_index_name("dev", "zzz", "20260816", _STATE_FP, "project1")
    )

    manifest = _manifest()
    service, approval_id, _targets, _routing, _backups = _service(manifest)
    with pytest.raises(PromotionError) as base:
        service.execute(
            manifest,
            approval_id,
            "lin_" + "2" * 48,
            PromotionExecutionContext("srv_" + "f" * 48, _PREDICATES, _AT),
        )
    assert base.value.code is PromotionErrorCode.BASE_STATE_DRIFT

    service, approval_id, _targets, _routing, _backups = _service(manifest)
    with pytest.raises(ApprovalError) as stale:
        service.execute(
            manifest,
            approval_id,
            "lin_" + "3" * 48,
            PromotionExecutionContext(_BASE, _PREDICATES, "2026-08-18T00:00:00Z"),
        )
    assert stale.value.code is ApprovalErrorCode.MANIFEST_INVALID


def test_coverage_fingerprint_and_generation_cache_behavior_are_fail_visible() -> None:
    """Activation needs protected bytes; requests may use only matching verified cache."""
    manifest = _manifest()
    wrong = replace(manifest.coverage_status, fingerprint="sha256:" + "f" * 64)
    service, approval_id, _targets, _routing, _backups = _service(
        manifest, coverage=LocalCoverageStore(wrong)
    )
    with pytest.raises(PromotionError) as mismatch:
        _execute(service, manifest, approval_id)
    assert mismatch.value.code is PromotionErrorCode.COVERAGE_FINGERPRINT_MISMATCH

    store = LocalCoverageStore(manifest.coverage_status)
    store.set_available(available=False)
    service, approval_id, _targets, _routing, _backups = _service(manifest, coverage=store)
    with pytest.raises(PromotionError) as unavailable:
        _execute(service, manifest, approval_id)
    assert unavailable.value.code is PromotionErrorCode.COVERAGE_UNAVAILABLE

    store.set_available(available=True)
    store.load_for_request(_CANDIDATE, manifest.coverage_status.fingerprint)
    store.set_available(available=False)
    assert (
        store.load_for_request(_CANDIDATE, manifest.coverage_status.fingerprint)
        == manifest.coverage_status
    )
    with pytest.raises(PromotionError):
        store.load_for_request("srv_" + "f" * 48, manifest.coverage_status.fingerprint)


def test_post_cutover_failure_reverse_swaps_and_rollback_failure_is_visible() -> None:
    """Only the exact retained predecessor is used for post-cutover rollback."""
    manifest = _manifest()
    service, approval_id, _targets, routing, _backups = _service(
        manifest, plan=LocalFailurePlan(post_cutover_failure=True)
    )
    result = _execute(service, manifest, approval_id)
    assert result.state == "EXECUTION_ROLLED_BACK"
    assert result.rollback_receipt_ref
    assert routing.active_state_id == _BASE

    service, approval_id, _targets, _routing, _backups = _service(
        manifest,
        plan=LocalFailurePlan(post_cutover_failure=True, rollback_failure=True),
    )
    with pytest.raises(PromotionError) as incident:
        _execute(service, manifest, approval_id)
    assert incident.value.code is PromotionErrorCode.POST_CUTOVER_FAILED


class _BlockingEmbedding:
    """Deterministic adapter that exposes a safe overlap-test rendezvous."""

    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.delegate = LocalEmbeddingAdapter()

    def embed(self, profile: EmbeddingProfile, request: EmbeddingRequest) -> EmbeddedVector:
        """Wait until the competing lineage attempts the same manifest."""
        self.entered.set()
        self.release.wait(timeout=5)
        return self.delegate.embed(profile, request)


def test_overlapping_execution_is_denied_before_second_consumption() -> None:
    """Only one execution lineage may run one exact manifest concurrently."""
    manifest = _manifest()
    blocker = _BlockingEmbedding()
    service, approval_id, _targets, _routing, _backups = _service(manifest, embeddings=blocker)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(_execute, service, manifest, approval_id)
        assert blocker.entered.wait(timeout=5)
        with pytest.raises(PromotionError) as overlap:
            _execute(service, manifest, approval_id, "lin_" + "2" * 48)
        blocker.release.set()
        assert first.result().state == "EXECUTION_SUCCEEDED"
    assert overlap.value.code is PromotionErrorCode.OVERLAPPING_EXECUTION


def test_retirement_has_no_broad_selector_and_never_deletes_active_target() -> None:
    """Only one manifest-declared inactive exact name can be retired."""
    manifest = _manifest(retirements=("old-exact-index",))
    service, approval_id, targets, _routing, _backups = _service(manifest)
    result = _execute(service, manifest, approval_id)
    targets.create(
        TargetDefinition("old-exact-index", "sha256:" + "e" * 64, 4, "COSINE", "default")
    )
    assert service.retire_exact(manifest, "old-exact-index").startswith("efr_")
    with pytest.raises(PromotionError) as broad:
        service.retire_exact(manifest, "old-*")
    assert broad.value.code is PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN
    active_manifest = _manifest(retirements=(result.target_name,))
    with pytest.raises(PromotionError):
        service.retire_exact(active_manifest, result.target_name)
