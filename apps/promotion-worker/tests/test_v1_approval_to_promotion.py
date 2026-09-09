"""Task 8 real-effect composition remains exact and effect-free until execution."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
import test_m6_promotion as m6
from _v1_serving_profile_fixture import exact_serving_profile
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import (
    EffectIntent,
    EffectType,
    ImmutableReference,
    ReferenceType,
)
from asklegal_management_register_ports import (
    ApprovalConsumption,
    ApprovalError,
    ApprovalProjection,
    ManifestSnapshot,
)
from asklegal_promotion import (
    EmbeddingRequest,
    EmbeddingRequestInput,
    HKV1TargetMember,
    LocalBackupStore,
    LocalCoverageStore,
    LocalEmbeddingAdapter,
    LocalRoutingStore,
    LocalServingStateStore,
    LocalServingTargetStore,
    PromotionActionAuthority,
    PromotionError,
    PromotionErrorCode,
    PromotionPlan,
    ProviderResponse,
    ServingCapabilityProfile,
    embedding_request,
    freeze_generic_promotion_manifest,
    freeze_v1_promotion_manifest,
    pinecone_index_name,
    verify_hk_v1_approved_package,
)
from asklegal_promotion.backup import (
    BackupAcknowledgement,
    BackupReadback,
    BackupRequest,
    BackupRole,
    NativeBackupPort,
    RecoveryCopyPort,
    freeze_backup_request,
)
from asklegal_promotion_worker.local_intents import (
    LocalRetainedEffectIntentSource,
    local_effect_intent_ledger_bytes,
    retain_v1_effect_intents,
)
from asklegal_promotion_worker.real_effects import (
    V1RealEffectAuthority,
    approved_v1_backup_request,
    compose_v1_real_effects,
    issue_v1_real_effect_authority,
)
from asklegal_promotion_worker.service import (
    PromotionDependencies,
    PromotionExecutionContext,
    PromotionService,
)
from asklegal_promotion_worker.v1_infrastructure import compose_independent_backup_adapter
from test_v1_serving_profiles import proposal_fixture


class _ApprovedPackageSource:
    """Exact retained package fake keyed by the named Approval identity."""

    def __init__(self, proposal: bytes, readiness: bytes) -> None:
        self.proposal = proposal
        self.readiness = readiness

    def approved_package(self, approval_id: str) -> tuple[bytes, bytes]:
        assert approval_id.startswith("apr_")
        return self.proposal, self.readiness


def _task8_now() -> datetime:
    """Return the retained fixture's exact pre-deadline execution instant."""
    return datetime.fromisoformat(m6.TASK8_AT.removesuffix("Z") + "+00:00")


def _readiness(  # noqa: PLR0913 - exact immutable Review readiness fixture.
    proposal: bytes,
    members: tuple[HKV1TargetMember, ...],
    zero_record_scope_ids: tuple[str, ...],
    *,
    serving_profile_fingerprint: str = "sha256:" + "8" * 64,
    embedding_profile_fingerprint: str,
    namespace: str = "synthetic-v1",
    backup_profile_fingerprint: str = "sha256:" + "3" * 64,
    target_name: str = "asklegal-dev-candidate",
) -> bytes:
    parsed = parse_json_bytes(proposal, max_bytes=1_000_000)
    assert isinstance(parsed, dict)
    proposal_fingerprint = parsed["fingerprint"]
    assert isinstance(proposal_fingerprint, str)
    member_scopes = {item.scope_id for item in members}
    body = checked_json_value(
        {
            "backup_profile_fingerprint": backup_profile_fingerprint,
            "embedding_profile_fingerprint": embedding_profile_fingerprint,
            "limitations": ["HKEX remains outside V1."],
            "model_evaluation_ref": "evaluation/model.json",
            "model_profile_fingerprint": parsed["model_profile_fingerprint"],
            "native_backup_ref": "backup/native.json",
            "proposal_fingerprint": proposal_fingerprint,
            "recovery_backup_ref": "backup/recovery.json",
            "retrieval_evaluation_ref": "evaluation/retrieval.json",
            "retryable_count": 0,
            "rollback_state_id": "srv_" + "8" * 48,
            "schema_id": "asklegal.hk-v1-review-readiness/v1",
            "scope_dispositions": [
                {
                    "result": "NO_CHANGE" if scope in zero_record_scope_ids else "COMPLETE",
                    "retryable_count": 0,
                    "scope_id": scope,
                }
                for scope in (
                    "HK-CASE-BINDING-POST-1997",
                    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
                    "HK-LEG-ORDINANCES",
                    "HK-LEG-SUBSIDIARY",
                )
            ],
            "serving_profile_fingerprint": serving_profile_fingerprint,
            "target_members": [
                {
                    "material_family": item.material_family,
                    "record_id": item.record_id,
                    "scope_id": item.scope_id,
                }
                for item in members
            ],
            "target_name": target_name,
            "target_namespace": namespace,
            "zero_record_scope_ids": list(zero_record_scope_ids),
        }
    )
    assert member_scopes.isdisjoint(zero_record_scope_ids)
    assert isinstance(body, dict)
    unsigned = dict(body)
    unsigned.pop("schema_id")
    fingerprint = f"sha256:{sha256(canonicalize(checked_json_value(unsigned))).hexdigest()}"
    completed = dict(body)
    completed["fingerprint"] = fingerprint
    return canonicalize(checked_json_value(completed))


class _Transport:
    """Deterministic provider-call fake with no network capability."""

    def __init__(self, timeout_seconds: int = 60) -> None:
        """Start with an empty local call ledger."""
        self.calls: list[tuple[str, str]] = []
        self.timeout_seconds = timeout_seconds

    def send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: JsonValue | None = None,
    ) -> ProviderResponse:
        """Record one synthetic request without opening a connection."""
        del headers, body
        self.calls.append((method, url))
        return ProviderResponse(200, {}, "request-1", 1)


def _azure(profile: ServingCapabilityProfile) -> bytes:
    deployment = profile.embedding.deployment_name
    contract = profile.embedding.api_contract
    return json.dumps(
        {
            "endpoint": "https://example.openai.azure.com",
            "deployment": deployment,
            "api_version": contract,
            "api_key": "synthetic-key",
        }
    ).encode()


def _pinecone(
    profile: ServingCapabilityProfile,
    index: str = "asklegal-dev-candidate",
) -> bytes:
    return json.dumps(
        {
            "api_key": "synthetic-key",
            "control_plane_host": "https://api.pinecone.io",
            "index": index,
            "project_id": profile.pinecone_project_id,
        }
    ).encode()


class _IntentSource:
    """Retained intent projection used to issue real-effect authority offline."""

    def __init__(self, intents: tuple[EffectIntent, ...]) -> None:
        self._intents = intents

    def effect_intents(self, execution_lineage_id: str) -> tuple[EffectIntent, ...]:
        assert execution_lineage_id == "exe_" + "1" * 48
        return self._intents


def _ref(kind: ReferenceType, prefix: str, digit: str) -> ImmutableReference:
    return ImmutableReference(kind, f"{prefix}_{digit * 48}", f"sha256:{digit * 64}")


def _intent(
    action: PromotionActionAuthority,
    digit: str,
) -> EffectIntent:
    lineage = _ref(ReferenceType.EXECUTION_LINEAGE, "exe", "1")
    return EffectIntent(
        f"efi_{digit * 48}",
        "2026-08-16T01:00:00Z",
        action.effect_type,
        action.owning_application,
        lineage,
        _ref(ReferenceType.COMMAND, "cmd", digit),
        lineage,
        action.permitted_checkpoint,
        action.input_refs,
        action.effect_command_fingerprint,
        action.required_capability,
        action.capability_profile_ref,
        action.destination_class,
        action.stable_idempotency_key,
        action.retry_class,
        action.attempt_ceiling,
        action.deadline,
        action.stop_conditions,
        action.expected_remote_precondition_ref,
        action.success_postcondition_ref,
        action.compensation,
    )


def _authority_from_consumed(
    profile: ServingCapabilityProfile,
    consumed: ApprovalProjection,
    manifest: m6.PromotionManifest,
) -> V1RealEffectAuthority:
    actions = tuple(
        item
        for item in manifest.actions
        if item.effect_type
        in {
            EffectType.EMBEDDING_PROVIDER_CALL,
            EffectType.PINECONE_MUTATION,
            EffectType.BACKUP_MUTATION,
        }
    )
    source = _IntentSource(
        (
            _intent(actions[0], "1"),
            _intent(actions[1], "2"),
            _intent(actions[2], "3"),
        )
    )
    return issue_v1_real_effect_authority(
        consumed,
        source,
        profile,
        manifest,
        m6.TASK8_TOKEN_COUNTER,
        execution_lineage_id="exe_" + "1" * 48,
    )


def _real_manifest(profile: ServingCapabilityProfile) -> m6.PromotionManifest:
    base = m6.task8_v1_manifest_fixture()
    return freeze_v1_promotion_manifest(
        replace(
            m6.task8_plan_from_manifest(base),
            embedding_profile=profile.embedding,
            batch_size=profile.batch_size,
            project_id=profile.pinecone_project_id,
            actions=m6.task8_no_routing_actions(base.desired_state, profile.embedding),
        )
    )


def test_effect_authority_is_preconsumption_exact_and_single_use() -> None:
    """Adapter composition cannot pre-consume Approval or reuse effect authority."""
    profile = exact_serving_profile()
    manifest = _real_manifest(profile)
    approvals, approval_id = m6.task8_approval(manifest)
    approved = approvals.get(approval_id)
    authority = _authority_from_consumed(profile, approved, manifest)
    assert approvals.get(approval_id).state.value == "APPROVAL_APPROVED"

    target_transport = _Transport(profile.target_timeout_seconds)
    effects = compose_v1_real_effects(
        profile,
        _azure(profile),
        _pinecone(profile),
        _Transport(profile.provider_timeout_seconds),
        target_transport,
        authority=authority,
        backup_profile_ref=profile.backup_profile_ref,
    )
    with pytest.raises(PromotionError, match="precedes Approval consumption"):
        effects.targets.contains("asklegal-dev-candidate")
    assert target_transport.calls == []
    with pytest.raises(PromotionError):
        compose_v1_real_effects(
            profile,
            _azure(profile),
            _pinecone(profile),
            _Transport(profile.provider_timeout_seconds),
            _Transport(profile.target_timeout_seconds),
            authority=authority,
            backup_profile_ref=profile.backup_profile_ref,
        )


def test_effect_authority_compares_every_retained_intent_with_approved_action() -> None:
    """A self-consistent but action-drifted intent cannot mint write authority."""
    profile = exact_serving_profile()
    manifest = _real_manifest(profile)
    approvals, approval_id = m6.task8_approval(manifest)
    actions = tuple(
        item
        for item in manifest.actions
        if item.effect_type
        in {
            EffectType.EMBEDDING_PROVIDER_CALL,
            EffectType.PINECONE_MUTATION,
            EffectType.BACKUP_MUTATION,
        }
    )
    bad = replace(
        _intent(actions[0], "1"),
        stable_idempotency_key="drifted-but-well-formed",
    )
    source = _IntentSource((bad, _intent(actions[1], "2"), _intent(actions[2], "3")))

    with pytest.raises(PromotionError, match="do not authorize exact V1 writes"):
        issue_v1_real_effect_authority(
            approvals.get(approval_id),
            source,
            profile,
            manifest,
            m6.TASK8_TOKEN_COUNTER,
            execution_lineage_id="exe_" + "1" * 48,
        )


def test_real_effect_authority_rereads_canonical_retained_intents(tmp_path: Path) -> None:
    """Production composition has a retained source and detects post-bind drift."""
    profile = exact_serving_profile()
    manifest = _real_manifest(profile)
    approvals, approval_id = m6.task8_approval(manifest)
    actions = tuple(
        item
        for item in manifest.actions
        if item.effect_type
        in {
            EffectType.EMBEDDING_PROVIDER_CALL,
            EffectType.PINECONE_MUTATION,
            EffectType.BACKUP_MUTATION,
        }
    )
    intents = (
        _intent(actions[0], "1"),
        _intent(actions[1], "2"),
        _intent(actions[2], "3"),
    )
    state_path = tmp_path / "effect-intents.json"
    state_path.write_bytes(local_effect_intent_ledger_bytes("exe_" + "1" * 48, intents))
    source = LocalRetainedEffectIntentSource(state_path)

    authority = issue_v1_real_effect_authority(
        approvals.get(approval_id),
        source,
        profile,
        manifest,
        m6.TASK8_TOKEN_COUNTER,
        execution_lineage_id="exe_" + "1" * 48,
    )

    assert authority.effect_intent_ids == tuple(item.effect_intent_id for item in intents)
    state_path.write_bytes(state_path.read_bytes() + b"\n")
    with pytest.raises(PromotionError, match="retained intent state drift"):
        source.effect_intents("exe_" + "1" * 48)


def test_effect_intents_are_derived_and_retained_from_approved_owner_facts(
    tmp_path: Path,
) -> None:
    """The live preflight needs no caller-authored Effect Intent ledger facts."""
    profile = exact_serving_profile()
    manifest = _real_manifest(profile)
    approvals, approval_id = m6.task8_approval(manifest)
    lineage = "exe_" + "1" * 48
    intent_root = tmp_path / "effect-intents"
    intent_root.mkdir()

    source = retain_v1_effect_intents(
        intent_root,
        approval_id=approval_id,
        execution_lineage_id=lineage,
        execution_time="2026-08-16T01:00:00Z",
        manifest=manifest,
        profile=profile,
    )
    retained = source.effect_intents(lineage)
    replay = retain_v1_effect_intents(
        intent_root,
        approval_id=approval_id,
        execution_lineage_id=lineage,
        execution_time="2026-08-16T01:00:00Z",
        manifest=manifest,
        profile=profile,
    )

    authority = issue_v1_real_effect_authority(
        approvals.get(approval_id),
        replay,
        profile,
        manifest,
        m6.TASK8_TOKEN_COUNTER,
        execution_lineage_id=lineage,
    )
    assert tuple(item.effect_type for item in retained) == (
        EffectType.EMBEDDING_PROVIDER_CALL,
        EffectType.PINECONE_MUTATION,
        EffectType.BACKUP_MUTATION,
    )
    assert authority.effect_intent_ids == tuple(item.effect_intent_id for item in retained)
    assert len(tuple(intent_root.iterdir())) == 1

    with pytest.raises(PromotionError, match="retained intent state drift"):
        retain_v1_effect_intents(
            intent_root,
            approval_id="apr_" + "9" * 48,
            execution_lineage_id=lineage,
            execution_time="2026-08-16T01:00:00Z",
            manifest=manifest,
            profile=profile,
        )


def test_same_consumed_lineage_can_reissue_retry_authority() -> None:
    """A failed durable activity can resume, but no competing lineage gains authority."""
    profile = exact_serving_profile()
    manifest = _real_manifest(profile)
    approvals, approval_id = m6.task8_approval(manifest)
    lineage = "exe_" + "1" * 48
    consumed = approvals.consume(
        approval_id,
        lineage,
        ManifestSnapshot(
            manifest.manifest_id,
            manifest.fingerprint,
            manifest.base_serving_state_id,
            manifest.valid_from,
            manifest.valid_until,
            manifest.validity_predicates,
        ),
        ApprovalConsumption(
            manifest.base_serving_state_id,
            manifest.validity_predicates,
            "2026-08-16T01:00:00Z",
        ),
    )
    actions = tuple(
        item
        for item in manifest.actions
        if item.effect_type
        in {
            EffectType.EMBEDDING_PROVIDER_CALL,
            EffectType.PINECONE_MUTATION,
            EffectType.BACKUP_MUTATION,
        }
    )
    source = _IntentSource(
        (_intent(actions[0], "1"), _intent(actions[1], "2"), _intent(actions[2], "3"))
    )

    authority = issue_v1_real_effect_authority(
        consumed,
        source,
        profile,
        manifest,
        m6.TASK8_TOKEN_COUNTER,
        execution_lineage_id=lineage,
    )

    assert authority.execution_lineage_id == lineage
    with pytest.raises(PromotionError, match="not bound to this execution lineage"):
        issue_v1_real_effect_authority(
            consumed,
            source,
            profile,
            manifest,
            m6.TASK8_TOKEN_COUNTER,
            execution_lineage_id="exe_" + "9" * 48,
        )


def test_embedding_gate_rejects_token_count_drift_before_transport() -> None:
    """The approved exact local count is checked before any provider request."""
    profile = exact_serving_profile()
    manifest = _real_manifest(profile)
    approvals, approval_id = m6.task8_approval(manifest)
    lineage = "exe_" + "1" * 48
    authority = _authority_from_consumed(profile, approvals.get(approval_id), manifest)
    transport = _EmbeddingTransport()
    effects = compose_v1_real_effects(
        profile,
        _azure(profile),
        _pinecone(profile),
        transport,
        _Transport(profile.target_timeout_seconds),
        authority=authority,
        backup_profile_ref=profile.backup_profile_ref,
        now=_task8_now,
    )
    consumed = approvals.consume(
        approval_id,
        lineage,
        ManifestSnapshot(
            manifest.manifest_id,
            manifest.fingerprint,
            manifest.base_serving_state_id,
            manifest.valid_from,
            manifest.valid_until,
            manifest.validity_predicates,
        ),
        ApprovalConsumption(
            manifest.base_serving_state_id,
            manifest.validity_predicates,
            m6.TASK8_AT,
        ),
    )
    effects.activation.activate(consumed)
    item = manifest.desired_state.records[0]
    batch_id = "art_" + sha256(f"{lineage}\x1f0".encode()).hexdigest()[:48]
    approved = embedding_request(
        EmbeddingRequestInput(
            item.record_id,
            item.content_fingerprint,
            item.record.text,
            batch_id,
            0,
        ),
        profile.embedding,
        m6.TASK8_TOKEN_COUNTER,
    )

    with pytest.raises(PromotionError, match="outside exact approved work"):
        effects.embeddings.embed(
            profile.embedding,
            replace(approved, token_count=approved.token_count + 1),
        )

    assert transport.calls == []


def test_effect_gate_rechecks_current_deadline_before_each_provider_call() -> None:
    """A later effect cannot borrow the activity's earlier pre-deadline timestamp."""
    profile = exact_serving_profile()
    manifest = _real_manifest(profile)
    approvals, approval_id = m6.task8_approval(manifest)
    lineage = "exe_" + "1" * 48
    authority = _authority_from_consumed(profile, approvals.get(approval_id), manifest)
    transport = _EmbeddingTransport()
    clock = [datetime.fromisoformat(m6.TASK8_AT.removesuffix("Z") + "+00:00")]
    effects = compose_v1_real_effects(
        profile,
        _azure(profile),
        _pinecone(profile),
        transport,
        _Transport(profile.target_timeout_seconds),
        authority=authority,
        backup_profile_ref=profile.backup_profile_ref,
        now=lambda: clock[0],
    )
    consumed = approvals.consume(
        approval_id,
        lineage,
        ManifestSnapshot(
            manifest.manifest_id,
            manifest.fingerprint,
            manifest.base_serving_state_id,
            manifest.valid_from,
            manifest.valid_until,
            manifest.validity_predicates,
        ),
        ApprovalConsumption(
            manifest.base_serving_state_id,
            manifest.validity_predicates,
            m6.TASK8_AT,
        ),
    )
    effects.activation.activate(consumed)
    item = manifest.desired_state.records[0]
    request = embedding_request(
        EmbeddingRequestInput(
            item.record_id,
            item.content_fingerprint,
            item.record.text,
            "art_" + sha256(f"{lineage}\x1f0".encode()).hexdigest()[:48],
            0,
        ),
        profile.embedding,
        m6.TASK8_TOKEN_COUNTER,
    )
    clock[0] = datetime(2026, 8, 18, tzinfo=UTC)

    with pytest.raises(PromotionError, match="effect deadline closed"):
        effects.embeddings.embed(profile.embedding, request)

    assert transport.calls == []


@pytest.mark.parametrize("drift", ["TARGET_DEFINITION", "SOURCE_EXPORT"])
def test_backup_gate_rejects_complete_request_drift_before_write(drift: str) -> None:
    """Neither backup path receives a self-consistent request outside the manifest."""
    profile = exact_serving_profile()
    manifest = _real_manifest(profile)
    authority = _real_authority(profile)
    effects = compose_v1_real_effects(
        profile,
        _azure(profile),
        _pinecone(profile),
        _Transport(profile.provider_timeout_seconds),
        _Transport(profile.target_timeout_seconds),
        authority=authority,
        backup_profile_ref=profile.backup_profile_ref,
    )
    approved = approved_v1_backup_request(profile, manifest)
    target_ref = approved.target_definition_ref
    source_ref = approved.source_export_ref
    if drift == "TARGET_DEFINITION":
        target_ref = replace(target_ref, fingerprint="sha256:" + "9" * 64)
    else:
        source_ref = replace(source_ref, fingerprint="sha256:" + "8" * 64)
    drifted = freeze_backup_request(
        target_name=approved.target_name,
        target_definition_ref=target_ref,
        desired_inventory_fingerprint=approved.desired_inventory_fingerprint,
        backup_profile_ref=approved.backup_profile_ref,
        source_export_ref=source_ref,
    )

    with pytest.raises(PromotionError, match="outside exact approved work"):
        compose_independent_backup_adapter(
            profile,
            drifted,
            _NativeBackup(),
            _RecoveryBackup(),
            activation=effects.activation,
        )


def _real_authority(profile: ServingCapabilityProfile) -> V1RealEffectAuthority:
    manifest = _real_manifest(profile)
    approvals, approval_id = m6.task8_approval(manifest)
    return _authority_from_consumed(profile, approvals.get(approval_id), manifest)


class _EmbeddingTransport:
    """State-free exact Azure embedding transport fake."""

    timeout_seconds = 60

    def __init__(self) -> None:
        self.calls: list[str] = []

    def send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: JsonValue | None = None,
    ) -> ProviderResponse:
        del headers
        assert method == "POST"
        assert url.endswith("/embeddings?api-version=2026-08-01")
        assert isinstance(body, dict)
        text = body["input"]
        assert isinstance(text, str)
        self.calls.append(text)
        count = m6.TASK8_TOKEN_COUNTER.count(text)
        return ProviderResponse(
            200,
            {
                "data": [{"embedding": [0.5, 0.5, 0.5, 0.5]}],
                "usage": {"prompt_tokens": count, "total_tokens": count},
            },
            f"embedding-{len(self.calls)}",
            1,
        )


class _PineconeTransport:
    """Stateful no-network Pinecone control/data-plane transport fake."""

    timeout_seconds = 60

    def __init__(self, index: str) -> None:
        self.index = index
        self.created = False
        self.records: dict[str, dict[str, JsonValue]] = {}
        self.calls: list[tuple[str, str]] = []

    def send(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: JsonValue | None = None,
    ) -> ProviderResponse:
        del headers
        self.calls.append((method, url))
        host = f"{self.index}.svc.synthetic.pinecone.io"
        if method == "GET" and url == "https://api.pinecone.io/indexes":
            indexes: list[JsonValue] = []
            if self.created:
                indexes.append(
                    {"name": self.index, "dimension": 4, "metric": "cosine", "host": host}
                )
            return ProviderResponse(200, {"indexes": indexes}, "pinecone-list", 1)
        if method == "POST" and url == "https://api.pinecone.io/indexes":
            self.created = True
            return ProviderResponse(201, {"name": self.index}, "pinecone-create", 1)
        if method == "POST" and url == f"https://{host}/vectors/upsert":
            assert isinstance(body, dict)
            assert body["namespace"] == "synthetic-v1"
            vectors = body["vectors"]
            assert isinstance(vectors, list)
            for vector in vectors:
                assert isinstance(vector, dict)
                identifier = vector["id"]
                assert isinstance(identifier, str)
                self.records[identifier] = vector
            return ProviderResponse(200, {"upsertedCount": len(vectors)}, "pinecone-upsert", 1)
        if method == "GET" and "/vectors/list?" in url:
            return ProviderResponse(
                200,
                {"vectors": [{"id": item} for item in sorted(self.records)], "pagination": {}},
                "pinecone-enumerate",
                1,
            )
        if method == "GET" and "/vectors/fetch?" in url:
            selected = {
                identifier: value
                for identifier, value in self.records.items()
                if f"ids={identifier}" in url
            }
            return ProviderResponse(
                200,
                checked_json_value({"vectors": selected}),
                "pinecone-fetch",
                1,
            )
        if method == "POST" and url.endswith("/query"):
            assert isinstance(body, dict)
            assert body["namespace"] == "synthetic-v1"
            assert body["topK"] == 1
            raw_filter = body["filter"]
            assert isinstance(raw_filter, dict)
            text_filter = raw_filter["text"]
            assert isinstance(text_filter, dict)
            text = text_filter["$eq"]

            def matches_text(value: dict[str, JsonValue]) -> bool:
                metadata = value.get("metadata")
                return isinstance(metadata, dict) and metadata.get("text") == text

            match = next(
                (value for value in self.records.values() if matches_text(value)),
                None,
            )
            return ProviderResponse(
                200,
                checked_json_value({"matches": [] if match is None else [match]}),
                "pinecone-query",
                1,
            )
        raise AssertionError((method, url, body))


class _NativeBackup(NativeBackupPort):
    """Offline nominal native backup fake with exact readback."""

    @property
    def backend_id(self) -> str:
        return "native-backup-a"

    def write_native(self, request: BackupRequest) -> BackupAcknowledgement:
        return _backup_ack(BackupRole.NATIVE, self.backend_id, request, "5")

    def read_native(self, request: BackupRequest) -> BackupReadback:
        return _backup_readback(BackupRole.NATIVE, self.backend_id, request, "5")


class _RecoveryBackup(RecoveryCopyPort):
    """Offline separately administered recovery fake with exact readback."""

    @property
    def backend_id(self) -> str:
        return "recovery-copy-b"

    def write_recovery(self, request: BackupRequest) -> BackupAcknowledgement:
        return _backup_ack(BackupRole.RECOVERY, self.backend_id, request, "6")

    def read_recovery(self, request: BackupRequest) -> BackupReadback:
        return _backup_readback(BackupRole.RECOVERY, self.backend_id, request, "6")


def _backup_ack(
    role: BackupRole,
    backend_id: str,
    request: BackupRequest,
    digit: str,
) -> BackupAcknowledgement:
    return BackupAcknowledgement(
        role,
        backend_id,
        request.request_fingerprint,
        _ref(ReferenceType.EFFECT_RECEIPT, "efr", digit),
        _ref(ReferenceType.EVIDENCE, "evi", digit),
    )


def _backup_readback(
    role: BackupRole,
    backend_id: str,
    request: BackupRequest,
    digit: str,
) -> BackupReadback:
    return BackupReadback(
        role,
        backend_id,
        request.request_fingerprint,
        request.target_name,
        request.target_definition_ref,
        request.desired_inventory_fingerprint,
        request.backup_profile_ref,
        request.source_export_ref,
        _ref(ReferenceType.ARTIFACT, "art", digit),
        _ref(ReferenceType.EFFECT_RECEIPT, "efr", digit),
        _ref(ReferenceType.EVIDENCE, "evi", digit),
    )


def test_issued_profile_composes_exact_azure_and_single_pinecone_target_without_calls() -> None:
    """Composition must not itself consume Approval or touch either provider."""
    profile = exact_serving_profile()
    embedding_transport = _Transport()
    target_transport = _Transport()

    effects = compose_v1_real_effects(
        profile,
        _azure(profile),
        _pinecone(profile),
        embedding_transport,
        target_transport,
        authority=_real_authority(profile),
        backup_profile_ref=profile.backup_profile_ref,
    )

    assert effects.serving_profile_fingerprint == profile.fingerprint
    assert effects.target_name == "asklegal-dev-candidate"
    assert embedding_transport.calls == []
    assert target_transport.calls == []


def test_profile_credential_drift_fails_before_transport() -> None:
    """A credential for a second target cannot silently redirect approved writes."""
    profile = exact_serving_profile()
    embedding_transport = _Transport()
    target_transport = _Transport()

    with pytest.raises(PromotionError) as failure:
        compose_v1_real_effects(
            profile,
            _azure(profile),
            _pinecone(profile, "other-target"),
            embedding_transport,
            target_transport,
            authority=_real_authority(profile),
            backup_profile_ref=profile.backup_profile_ref,
        )

    assert failure.value.code is PromotionErrorCode.PROFILE_INVALID
    assert embedding_transport.calls == []
    assert target_transport.calls == []


def test_all_serving_profile_operational_facts_are_bound_before_composition() -> None:
    """Project, page size, timeouts, and backup profile cannot be ignored."""
    profile = exact_serving_profile()
    bad_backup = _ref(ReferenceType.CAPABILITY_PROFILE, "cap", "9")

    with pytest.raises(PromotionError) as wrong_timeout:
        compose_v1_real_effects(
            profile,
            _azure(profile),
            _pinecone(profile),
            _Transport(profile.provider_timeout_seconds + 1),
            _Transport(profile.target_timeout_seconds),
            authority=_real_authority(profile),
            backup_profile_ref=profile.backup_profile_ref,
        )
    assert wrong_timeout.value.code is PromotionErrorCode.PROFILE_INVALID

    with pytest.raises(PromotionError) as wrong_backup:
        compose_v1_real_effects(
            profile,
            _azure(profile),
            _pinecone(profile),
            _Transport(profile.provider_timeout_seconds),
            _Transport(profile.target_timeout_seconds),
            authority=_real_authority(profile),
            backup_profile_ref=bad_backup,
        )
    assert wrong_backup.value.code is PromotionErrorCode.PROFILE_INVALID


def test_real_adapters_execute_end_to_end_only_under_retained_authority() -> None:
    """PromotionService drives exact Azure/Pinecone adapters through offline transports."""
    profile = exact_serving_profile()
    base = m6.task8_v1_manifest_fixture()
    proposal = proposal_fixture(embedding_profile_fingerprint=profile.embedding.profile_fingerprint)
    parsed = parse_json_bytes(proposal, max_bytes=1_000_000)
    assert isinstance(parsed, dict)
    proposal_fingerprint = parsed["fingerprint"]
    assert isinstance(proposal_fingerprint, str)
    record_ids = tuple(item.record_id for item in base.desired_state.records)
    members = (
        HKV1TargetMember(record_ids[0], "HK-CASE-BINDING-POST-1997", "CASES"),
        HKV1TargetMember(record_ids[1], "HK-LEG-ORDINANCES", "LEGISLATION"),
    )
    zero_record_scopes = (
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-LEG-SUBSIDIARY",
    )
    readiness = _readiness(
        proposal,
        members,
        zero_record_scopes,
        serving_profile_fingerprint=profile.fingerprint,
        embedding_profile_fingerprint=profile.embedding.profile_fingerprint,
        namespace=profile.namespace,
        backup_profile_fingerprint=profile.backup_profile_ref.fingerprint,
        target_name=pinecone_index_name(
            base.environment,
            base.jurisdiction,
            base.freeze_date,
            base.candidate_serving_state_fingerprint,
            profile.pinecone_project_id,
        ),
    )
    readiness_document = parse_json_bytes(readiness, max_bytes=1_000_000)
    assert isinstance(readiness_document, dict)
    readiness_fingerprint = readiness_document["fingerprint"]
    assert isinstance(readiness_fingerprint, str)
    predicates = tuple(
        sorted(
            (
                *base.validity_predicates,
                ("HK_V1_TWO_FAMILY_PROPOSAL", "1.0.0", proposal_fingerprint),
                ("HK_V1_REVIEW_READINESS", "1.0.0", readiness_fingerprint),
            )
        )
    )
    manifest = freeze_v1_promotion_manifest(
        replace(
            m6.task8_plan_from_manifest(base),
            embedding_profile=profile.embedding,
            batch_size=profile.batch_size,
            project_id=profile.pinecone_project_id,
            validity_predicates=predicates,
            actions=m6.task8_no_routing_actions(base.desired_state, profile.embedding),
        )
    )
    approvals, approval_id = m6.task8_approval(manifest)
    lineage = "exe_" + "1" * 48
    authority = _authority_from_consumed(profile, approvals.get(approval_id), manifest)
    target_name = pinecone_index_name(
        manifest.environment,
        manifest.jurisdiction,
        manifest.freeze_date,
        manifest.candidate_serving_state_fingerprint,
        manifest.project_id,
    )
    embedding_transport = _EmbeddingTransport()
    target_transport = _PineconeTransport(target_name)
    effects = compose_v1_real_effects(
        profile,
        _azure(profile),
        _pinecone(profile, target_name),
        embedding_transport,
        target_transport,
        authority=authority,
        backup_profile_ref=profile.backup_profile_ref,
        now=_task8_now,
    )
    backup_request = approved_v1_backup_request(profile, manifest)
    backups = compose_independent_backup_adapter(
        profile,
        backup_request,
        _NativeBackup(),
        _RecoveryBackup(),
        activation=effects.activation,
    )
    with pytest.raises(PromotionError, match="precedes Approval consumption"):
        backups.create_and_verify(
            target_name,
            manifest.desired_state.inventory_fingerprint,
            profile.backup_profile_ref,
        )
    states = LocalServingStateStore(m6.TASK8_BASE)
    service = PromotionService(
        PromotionDependencies(
            approvals,
            effects.embeddings,
            m6.TASK8_TOKEN_COUNTER,
            effects.targets,
            backups,
            LocalRoutingStore(m6.TASK8_BASE),
            LocalCoverageStore(manifest.coverage_status),
            states,
            profile,
            profile.backup_profile_ref,
            effects.activation,
            _ApprovedPackageSource(proposal, readiness),
        )
    )

    _composition, result = service.execute_hk_v1(
        manifest,
        approval_id,
        lineage,
        PromotionExecutionContext(m6.TASK8_BASE, predicates, m6.TASK8_AT),
    )

    assert result.state == "EXECUTION_SUCCEEDED"
    assert len(embedding_transport.calls) == len(record_ids)
    assert set(target_transport.records) == set(record_ids)
    readbacks = (
        url for method, url in target_transport.calls if method == "GET" and "/vectors/" in url
    )
    assert all("namespace=synthetic-v1" in url for url in readbacks)
    calls_before_unapproved = len(embedding_transport.calls)
    unapproved = EmbeddingRequest(
        "emr_" + "9" * 48,
        "rec_" + "9" * 48,
        "sha256:" + "9" * 64,
        "not in the approved desired state",
        "sha256:" + "8" * 64,
        1,
        profile.embedding.profile_id,
        "art_" + "9" * 48,
        0,
        "sha256:" + "7" * 64,
    )
    with pytest.raises(PromotionError, match="outside exact approved work"):
        effects.embeddings.embed(profile.embedding, unapproved)
    assert len(embedding_transport.calls) == calls_before_unapproved
    with pytest.raises(PromotionError, match="outside exact approved work"):
        backups.create_and_verify(
            target_name,
            manifest.desired_state.inventory_fingerprint,
            profile.backup_profile_ref,
        )
    with pytest.raises(PromotionError) as deletion:
        effects.targets.delete_exact(target_name, target_name)
    assert deletion.value.code is PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN


def test_azure_manifest_without_loader_issued_serving_profile_does_not_consume_approval() -> None:
    """Hash-valid Azure coordinates alone cannot wake provider or target effects."""
    profile = exact_serving_profile()
    base = m6.task8_manifest_fixture()
    manifest = freeze_generic_promotion_manifest(
        PromotionPlan(
            profile.environment,
            base.jurisdiction,
            base.freeze_date,
            base.valid_from,
            base.valid_until,
            base.base_serving_state_id,
            base.candidate_serving_state_id,
            base.candidate_serving_state_fingerprint,
            base.rollback_serving_state_id,
            base.desired_state,
            base.coverage_status,
            profile.embedding,
            base.validity_predicates,
            profile.batch_size,
            profile.pinecone_project_id,
            base.action_contract_version,
            m6.task8_actions(base.desired_state, profile.embedding),
        )
    )
    approvals, approval_id = m6.task8_approval(manifest)
    embeddings = LocalEmbeddingAdapter()
    targets = LocalServingTargetStore()
    service = PromotionService(
        PromotionDependencies(
            approvals,
            embeddings,
            m6.TASK8_TOKEN_COUNTER,
            targets,
            LocalBackupStore(),
            LocalRoutingStore(m6.TASK8_BASE),
            LocalCoverageStore(manifest.coverage_status),
        )
    )

    with pytest.raises(PromotionError) as failure:
        service.execute(
            manifest,
            approval_id,
            "lin_" + "1" * 48,
            PromotionExecutionContext(m6.TASK8_BASE, m6.TASK8_PREDICATES, m6.TASK8_AT),
        )

    assert failure.value.code is PromotionErrorCode.PROFILE_INVALID
    assert approvals.get(approval_id).state.value == "APPROVAL_APPROVED"
    assert embeddings.calls == []


def test_exact_named_approval_executes_once_for_the_bound_two_family_proposal() -> None:
    """A proposal-bound Approval produces one replacement state and exact replay only."""
    base = m6.task8_v1_manifest_fixture()
    proposal = proposal_fixture(
        embedding_profile_fingerprint=base.embedding_profile.profile_fingerprint
    )
    parsed = parse_json_bytes(proposal, max_bytes=1_000_000)
    assert isinstance(parsed, dict)
    proposal_fingerprint = parsed["fingerprint"]
    assert isinstance(proposal_fingerprint, str)
    record_ids = tuple(item.record_id for item in base.desired_state.records)
    members = (
        HKV1TargetMember(record_ids[0], "HK-CASE-BINDING-POST-1997", "CASES"),
        HKV1TargetMember(record_ids[1], "HK-LEG-ORDINANCES", "LEGISLATION"),
    )
    zero_record_scopes = (
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-LEG-SUBSIDIARY",
    )
    readiness = _readiness(
        proposal,
        members,
        zero_record_scopes,
        embedding_profile_fingerprint=base.embedding_profile.profile_fingerprint,
        target_name=pinecone_index_name(
            base.environment,
            base.jurisdiction,
            base.freeze_date,
            base.candidate_serving_state_fingerprint,
            base.project_id,
        ),
    )
    readiness_document = parse_json_bytes(readiness, max_bytes=1_000_000)
    assert isinstance(readiness_document, dict)
    readiness_fingerprint = readiness_document["fingerprint"]
    assert isinstance(readiness_fingerprint, str)
    predicates = tuple(
        sorted(
            (
                *base.validity_predicates,
                ("HK_V1_TWO_FAMILY_PROPOSAL", "1.0.0", proposal_fingerprint),
                ("HK_V1_REVIEW_READINESS", "1.0.0", readiness_fingerprint),
            )
        )
    )
    manifest = freeze_v1_promotion_manifest(
        replace(m6.task8_plan_from_manifest(base), validity_predicates=predicates)
    )
    approvals, approval_id = m6.task8_approval(manifest)
    states = LocalServingStateStore(m6.TASK8_BASE)
    embeddings = LocalEmbeddingAdapter()
    package_source = _ApprovedPackageSource(proposal, readiness)
    service = PromotionService(
        PromotionDependencies(
            approvals,
            embeddings,
            m6.TASK8_TOKEN_COUNTER,
            LocalServingTargetStore(),
            LocalBackupStore(),
            LocalRoutingStore(m6.TASK8_BASE),
            LocalCoverageStore(manifest.coverage_status),
            states,
            approved_package_source=package_source,
        )
    )

    package_source.proposal = proposal_fixture(
        model_profile_fingerprint="sha256:" + "9" * 64,
        embedding_profile_fingerprint=base.embedding_profile.profile_fingerprint,
    )
    with pytest.raises(PromotionError) as drift:
        service.execute_hk_v1(
            manifest,
            approval_id,
            "exe_" + "9" * 48,
            PromotionExecutionContext(m6.TASK8_BASE, predicates, m6.TASK8_AT),
        )

    assert drift.value.code is PromotionErrorCode.MANIFEST_DRIFT
    assert approvals.get(approval_id).state.value == "APPROVAL_APPROVED"
    assert embeddings.calls == []
    package_source.proposal = proposal

    package_source.readiness = _readiness(
        proposal,
        (
            HKV1TargetMember(record_ids[0], "HK-LEG-ORDINANCES", "LEGISLATION"),
            HKV1TargetMember(record_ids[1], "HK-CASE-BINDING-POST-1997", "CASES"),
        ),
        zero_record_scopes,
        embedding_profile_fingerprint=base.embedding_profile.profile_fingerprint,
        target_name=pinecone_index_name(
            base.environment,
            base.jurisdiction,
            base.freeze_date,
            base.candidate_serving_state_fingerprint,
            base.project_id,
        ),
    )
    with pytest.raises(PromotionError) as reassigned:
        service.execute_hk_v1(
            manifest,
            approval_id,
            "exe_" + "8" * 48,
            PromotionExecutionContext(m6.TASK8_BASE, predicates, m6.TASK8_AT),
        )
    assert reassigned.value.code is PromotionErrorCode.MANIFEST_DRIFT
    assert approvals.get(approval_id).state.value == "APPROVAL_APPROVED"
    package_source.readiness = readiness

    composition, result = service.execute_hk_v1(
        manifest,
        approval_id,
        "exe_" + "1" * 48,
        PromotionExecutionContext(m6.TASK8_BASE, predicates, m6.TASK8_AT),
    )
    replay = service.execute_hk_v1(
        manifest,
        approval_id,
        "exe_" + "1" * 48,
        PromotionExecutionContext(m6.TASK8_BASE, predicates, m6.TASK8_AT),
    )

    assert result.state == "EXECUTION_SUCCEEDED"
    assert composition.proposal_fingerprint == proposal_fingerprint
    assert replay == (composition, result)
    assert states.active_state_id == manifest.candidate_serving_state_id
    with pytest.raises(PromotionError) as replay_drift:
        service.execute_hk_v1(
            manifest,
            approval_id,
            "exe_" + "1" * 48,
            PromotionExecutionContext(m6.TASK8_BASE, predicates, "2026-08-16T00:00:01Z"),
        )
    assert replay_drift.value.code is PromotionErrorCode.MANIFEST_DRIFT
    with pytest.raises(ApprovalError):
        service.execute_hk_v1(
            manifest,
            approval_id,
            "exe_" + "2" * 48,
            PromotionExecutionContext(m6.TASK8_BASE, predicates, m6.TASK8_AT),
        )


def test_hk_v1_entry_point_rejects_a_fingerprint_valid_routing_manifest() -> None:
    """The HK V1 entry point can never fall back to generic routing authority."""
    base = m6.task8_v1_manifest_fixture()
    routing_manifest = freeze_generic_promotion_manifest(
        replace(
            m6.task8_plan_from_manifest(base),
            actions=m6.task8_actions(base.desired_state, base.embedding_profile),
        )
    )
    approvals, approval_id = m6.task8_approval(routing_manifest)
    routing = LocalRoutingStore(m6.TASK8_BASE)
    service = PromotionService(
        PromotionDependencies(
            approvals,
            LocalEmbeddingAdapter(),
            m6.TASK8_TOKEN_COUNTER,
            LocalServingTargetStore(),
            LocalBackupStore(),
            routing,
            LocalCoverageStore(routing_manifest.coverage_status),
            LocalServingStateStore(m6.TASK8_BASE),
            approved_package_source=_ApprovedPackageSource(b"{}", b"{}"),
        )
    )

    with pytest.raises(PromotionError) as failure:
        service.execute_hk_v1(
            routing_manifest,
            approval_id,
            "exe_" + "7" * 48,
            PromotionExecutionContext(
                m6.TASK8_BASE,
                routing_manifest.validity_predicates,
                m6.TASK8_AT,
            ),
        )

    assert failure.value.code is PromotionErrorCode.MANIFEST_DRIFT
    assert approvals.get(approval_id).state.value == "APPROVAL_APPROVED"
    assert routing.active_state_id == m6.TASK8_BASE


def test_approved_readiness_model_profile_must_equal_frozen_proposal() -> None:
    """The model profile shown to the human cannot drift from Task 7."""
    base = m6.task8_v1_manifest_fixture()
    proposal = proposal_fixture(
        embedding_profile_fingerprint=base.embedding_profile.profile_fingerprint
    )
    members = tuple(
        HKV1TargetMember(
            item.record_id,
            "HK-CASE-BINDING-POST-1997" if index == 0 else "HK-LEG-ORDINANCES",
            "CASES" if index == 0 else "LEGISLATION",
        )
        for index, item in enumerate(base.desired_state.records)
    )
    readiness = _readiness(
        proposal,
        members,
        (
            "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
            "HK-LEG-SUBSIDIARY",
        ),
        embedding_profile_fingerprint=base.embedding_profile.profile_fingerprint,
    )
    document = parse_json_bytes(readiness, max_bytes=1_000_000)
    assert isinstance(document, dict)
    document["model_profile_fingerprint"] = "sha256:" + "9" * 64
    unsigned = dict(document)
    unsigned.pop("fingerprint")
    unsigned.pop("schema_id")
    document["fingerprint"] = (
        f"sha256:{sha256(canonicalize(checked_json_value(unsigned))).hexdigest()}"
    )
    drifted = canonicalize(checked_json_value(document))

    with pytest.raises(PromotionError) as failure:
        verify_hk_v1_approved_package(
            proposal,
            drifted,
            tuple(item.record_id for item in base.desired_state.records),
        )

    assert failure.value.code is PromotionErrorCode.INVENTORY_MISMATCH
