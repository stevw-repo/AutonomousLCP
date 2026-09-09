"""Fail-closed composition of the admitted Azure and Pinecone boundaries."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Never, Protocol
from weakref import ref

from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_domain import (
    ApplicationCode,
    ContractReference,
    EffectIntent,
    EffectType,
    ImmutableReference,
    ReferenceType,
)
from asklegal_management_register_ports import ApprovalProjection, ApprovalState
from asklegal_promotion import (
    AzureOpenAIConfig,
    AzureOpenAIEmbeddingAdapter,
    BackupPort,
    EmbeddedVector,
    EmbeddingProfile,
    EmbeddingRequest,
    EmbeddingTokenCounter,
    PineconeConfig,
    PineconeServingTargetStore,
    ProfileError,
    PromotionActionAuthority,
    PromotionError,
    PromotionErrorCode,
    PromotionManifest,
    TargetDefinition,
    TargetRecord,
    pinecone_index_name,
    target_state_fingerprint,
    validate_serving_capability_profile_authority,
)
from asklegal_promotion.backup import BackupRequest, freeze_backup_request

if TYPE_CHECKING:
    from asklegal_corpus import FlattenedRecord
    from asklegal_promotion import ServingCapabilityProfile
    from asklegal_promotion.backup import IndependentBackupAdapter
    from asklegal_promotion.model import BackupVerification
    from asklegal_promotion.remote import ProviderCall


class RetainedEffectIntentSource(Protocol):
    """Read the exact retained intent projection for one consumed lineage."""

    def effect_intents(self, execution_lineage_id: str) -> tuple[EffectIntent, ...]:
        """Return retained immutable intents for exactly one lineage."""
        ...


@dataclass(frozen=True, slots=True, weakref_slot=True, init=False, eq=False)
class V1RealEffectAuthority:
    """Non-transferable authority derived from retained Approval and intent state."""

    approval_id: str
    execution_lineage_id: str
    manifest_fingerprint: str
    serving_profile_fingerprint: str
    effect_intent_ids: tuple[str, ...]
    effect_intent_fingerprints: tuple[str, ...]
    fingerprint: str
    _witness: object | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class _ExpectedEmbedding:
    request_id: str
    record_id: str
    serving_payload_fingerprint: str
    text: str
    text_fingerprint: str
    profile_id: str
    batch_id: str
    batch_position: int
    cache_key: str
    token_count: int


@dataclass(frozen=True, slots=True)
class _EffectPolicy:
    embedding_profile: EmbeddingProfile
    expected_embeddings: tuple[_ExpectedEmbedding, ...]
    desired_records: tuple[FlattenedRecord, ...]
    target_definition: TargetDefinition
    expected_batches: tuple[tuple[str, ...], ...]
    expected_record_ids: tuple[str, ...]
    inventory_fingerprint: str
    backup_profile_ref: ImmutableReference
    backup_request: BackupRequest
    effect_deadlines: tuple[tuple[EffectType, str], ...]


_ISSUED: dict[
    int,
    tuple[ref[V1RealEffectAuthority], str, _EffectPolicy],
] = {}
_REQUIRED_EFFECT_INTENT_COUNT = 3


def _authority_fail(detail: str) -> Never:
    raise PromotionError(PromotionErrorCode.PROFILE_INVALID, detail)


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"


def issue_v1_real_effect_authority(  # noqa: PLR0913 - exact retained authority inputs.
    approval: ApprovalProjection,
    intents: RetainedEffectIntentSource,
    profile: ServingCapabilityProfile,
    manifest: PromotionManifest,
    token_counter: EmbeddingTokenCounter,
    *,
    execution_lineage_id: str,
) -> V1RealEffectAuthority:
    """Issue one lineage-scoped write authority from retained single-use facts."""
    validate_serving_capability_profile_authority(profile)
    approved_for_lineage = type(approval) is ApprovalProjection and (
        (approval.state is ApprovalState.APPROVED and not approval.execution_lineage_id)
        or (
            approval.state is ApprovalState.CONSUMED
            and approval.execution_lineage_id == execution_lineage_id
        )
    )
    if (
        type(approval) is not ApprovalProjection
        or not approved_for_lineage
        or type(manifest) is not PromotionManifest
        or approval.decision.manifest_id != manifest.manifest_id
        or approval.decision.manifest_fingerprint != manifest.fingerprint
    ):
        _authority_fail("retained Approval is not bound to this execution lineage")
    retained = intents.effect_intents(execution_lineage_id)
    expected = (
        EffectType.EMBEDDING_PROVIDER_CALL,
        EffectType.PINECONE_MUTATION,
        EffectType.BACKUP_MUTATION,
    )
    actions = tuple(item for item in manifest.actions if item.effect_type in expected)
    if (
        type(retained) is not tuple
        or tuple(item.effect_type for item in retained) != expected
        or len(actions) != _REQUIRED_EFFECT_INTENT_COUNT
        or any(type(item) is not EffectIntent for item in retained)
        or any(
            not _intent_matches_action(intent, action, execution_lineage_id, manifest)
            for intent, action in zip(retained, actions, strict=True)
        )
    ):
        _authority_fail("retained effect intents do not authorize exact V1 writes")
    intent_ids = tuple(item.effect_intent_id for item in retained)
    intent_fingerprints = tuple(_effect_intent_fingerprint(item) for item in retained)
    raw = canonicalize(
        checked_json_value(
            {
                "approval_id": approval.decision.approval_id,
                "approval_manifest_fingerprint": approval.decision.manifest_fingerprint,
                "execution_lineage_id": execution_lineage_id,
                "intent_fingerprints": list(intent_fingerprints),
                "serving_profile_fingerprint": profile.fingerprint,
            }
        )
    )
    fingerprint = f"sha256:{sha256(raw).hexdigest()}"
    policy = _effect_policy(
        profile,
        manifest,
        execution_lineage_id,
        token_counter,
        retained,
    )
    value = object.__new__(V1RealEffectAuthority)
    object.__setattr__(value, "approval_id", approval.decision.approval_id)
    object.__setattr__(value, "execution_lineage_id", execution_lineage_id)
    object.__setattr__(value, "manifest_fingerprint", manifest.fingerprint)
    object.__setattr__(value, "serving_profile_fingerprint", profile.fingerprint)
    object.__setattr__(value, "effect_intent_ids", intent_ids)
    object.__setattr__(value, "effect_intent_fingerprints", intent_fingerprints)
    object.__setattr__(value, "fingerprint", fingerprint)
    witness = object()
    object.__setattr__(value, "_witness", witness)
    key = id(value)

    def discard(_item: object) -> None:
        _ISSUED.pop(key, None)

    _ISSUED[key] = (ref(value, discard), fingerprint, policy)
    return value


def _effect_policy(
    profile: ServingCapabilityProfile,
    manifest: PromotionManifest,
    execution_lineage_id: str,
    token_counter: EmbeddingTokenCounter,
    intents: tuple[EffectIntent, ...],
) -> _EffectPolicy:
    embedding = manifest.embedding_profile
    if (
        profile.embedding != embedding
        or profile.environment != manifest.environment
        or profile.batch_size != manifest.batch_size
        or profile.pinecone_project_id != manifest.project_id
        or token_counter.tokenizer_id != embedding.tokenizer
    ):
        _authority_fail("serving profile does not match approved manifest")
    target_name = pinecone_index_name(
        manifest.environment,
        manifest.jurisdiction,
        manifest.freeze_date,
        manifest.candidate_serving_state_fingerprint,
        manifest.project_id,
    )
    expected: list[_ExpectedEmbedding] = []
    record_ids: list[str] = []
    for index, item in enumerate(manifest.desired_state.records):
        text = item.record.text
        token_count = token_counter.count(text)
        if type(token_count) is not int or not 1 <= token_count <= embedding.max_input_tokens:
            _authority_fail("exact embedding token count is invalid")
        text_fingerprint = f"sha256:{sha256(text.encode()).hexdigest()}"
        cache_material = (text_fingerprint + embedding.profile_fingerprint).encode()
        cache_key = f"sha256:{sha256(cache_material).hexdigest()}"
        batch_id = _stable_id("art", execution_lineage_id, str(index // manifest.batch_size))
        position = index % manifest.batch_size
        expected.append(
            _ExpectedEmbedding(
                _stable_id(
                    "emr",
                    item.record_id,
                    item.content_fingerprint,
                    cache_key,
                    batch_id,
                    str(position),
                ),
                item.record_id,
                item.content_fingerprint,
                text,
                text_fingerprint,
                embedding.profile_id,
                batch_id,
                position,
                cache_key,
                token_count,
            )
        )
        record_ids.append(item.record_id)
    batches = tuple(
        tuple(record_ids[start : start + manifest.batch_size])
        for start in range(0, len(record_ids), manifest.batch_size)
    )
    return _EffectPolicy(
        embedding,
        tuple(expected),
        tuple(manifest.desired_state.records),
        TargetDefinition(
            target_name,
            target_state_fingerprint(
                target_name,
                embedding.dimensions,
                embedding.metric,
                profile.namespace,
            ),
            embedding.dimensions,
            embedding.metric,
            profile.namespace,
        ),
        batches,
        tuple(record_ids),
        manifest.desired_state.inventory_fingerprint,
        profile.backup_profile_ref,
        approved_v1_backup_request(profile, manifest),
        tuple((intent.effect_type, intent.deadline) for intent in intents),
    )


def approved_v1_backup_request(
    profile: ServingCapabilityProfile,
    manifest: PromotionManifest,
) -> BackupRequest:
    """Derive the sole exact backup request authorized by one frozen V1 manifest."""
    target_name = pinecone_index_name(
        manifest.environment,
        manifest.jurisdiction,
        manifest.freeze_date,
        manifest.candidate_serving_state_fingerprint,
        manifest.project_id,
    )
    target_fingerprint = target_state_fingerprint(
        target_name,
        manifest.embedding_profile.dimensions,
        manifest.embedding_profile.metric,
        profile.namespace,
    )
    return freeze_backup_request(
        target_name=target_name,
        target_definition_ref=ImmutableReference(
            ReferenceType.PINECONE_INDEX_GENERATION,
            _stable_id("pgi", target_name, target_fingerprint),
            target_fingerprint,
        ),
        desired_inventory_fingerprint=manifest.desired_state.inventory_fingerprint,
        backup_profile_ref=profile.backup_profile_ref,
        source_export_ref=ImmutableReference(
            ReferenceType.ARTIFACT,
            _stable_id(
                "art",
                manifest.candidate_serving_state_id,
                manifest.desired_state.inventory_id,
                manifest.desired_state.inventory_fingerprint,
            ),
            manifest.desired_state.inventory_fingerprint,
        ),
    )


def _intent_matches_action(
    intent: EffectIntent,
    action: object,
    execution_lineage_id: str,
    manifest: PromotionManifest,
) -> bool:
    """Compare every approved static action fact and bounded runtime identity."""
    if type(action) is not PromotionActionAuthority:
        return False
    return (
        intent.effect_type is action.effect_type
        and intent.owning_application is ApplicationCode.PROMOTION_WORKER
        and intent.owning_application is action.owning_application
        and intent.permitted_checkpoint == action.permitted_checkpoint
        and intent.input_refs == action.input_refs
        and intent.effect_command_fingerprint == action.effect_command_fingerprint
        and intent.required_capability is action.required_capability
        and intent.capability_profile_ref == action.capability_profile_ref
        and intent.destination_class is action.destination_class
        and intent.stable_idempotency_key == action.stable_idempotency_key
        and intent.retry_class is action.retry_class
        and intent.attempt_ceiling == action.attempt_ceiling
        and intent.deadline == action.deadline
        and intent.stop_conditions == action.stop_conditions
        and intent.expected_remote_precondition_ref == action.expected_remote_precondition_ref
        and intent.success_postcondition_ref == action.success_postcondition_ref
        and intent.compensation == action.compensation
        and manifest.valid_from <= intent.created_at <= intent.deadline
        and intent.aggregate_ref.ref_type is ReferenceType.EXECUTION_LINEAGE
        and intent.aggregate_ref == intent.execution_lineage_ref
        and intent.execution_lineage_ref.ref_id == execution_lineage_id
        and intent.command_ref.ref_type is ReferenceType.COMMAND
    )


def _effect_intent_fingerprint(intent: EffectIntent) -> str:
    """Bind every retained Effect Intent field into one canonical identity."""

    def references(values: tuple[ImmutableReference, ...]) -> list[dict[str, str]]:
        return [
            {
                "ref_type": item.ref_type.value,
                "ref_id": item.ref_id,
                "fingerprint": item.fingerprint,
            }
            for item in values
        ]

    def contract(item: ContractReference) -> dict[str, str]:
        return {
            "contract_id": item.contract_id,
            "version": item.version,
            "fingerprint": item.fingerprint,
        }

    document = checked_json_value(
        {
            "aggregate_ref": references((intent.aggregate_ref,))[0],
            "attempt_ceiling": intent.attempt_ceiling,
            "capability_profile_ref": references((intent.capability_profile_ref,))[0],
            "command_ref": references((intent.command_ref,))[0],
            "compensation": repr(intent.compensation),
            "created_at": intent.created_at,
            "deadline": intent.deadline,
            "destination_class": intent.destination_class.value,
            "effect_command_fingerprint": intent.effect_command_fingerprint,
            "effect_intent_id": intent.effect_intent_id,
            "effect_type": intent.effect_type.value,
            "execution_lineage_ref": references((intent.execution_lineage_ref,))[0],
            "expected_remote_precondition_ref": contract(intent.expected_remote_precondition_ref),
            "input_refs": references(intent.input_refs),
            "owning_application": intent.owning_application.value,
            "permitted_checkpoint": intent.permitted_checkpoint,
            "required_capability": intent.required_capability.value,
            "retry_class": intent.retry_class.value,
            "stable_idempotency_key": intent.stable_idempotency_key,
            "stop_conditions": [item.value for item in intent.stop_conditions],
            "success_postcondition_ref": contract(intent.success_postcondition_ref),
        }
    )
    return f"sha256:{sha256(canonicalize(document)).hexdigest()}"


def _empty_embedded_vectors() -> dict[str, tuple[float, ...]]:
    return {}


@dataclass(slots=True)
class _EffectGate:
    """One-shot exact effect policy closed until the Approval is consumed."""

    policy: _EffectPolicy
    active: bool = False
    embedding_requests: dict[str, _ExpectedEmbedding] = field(init=False)
    embedded_vectors: dict[str, tuple[float, ...]] = field(default_factory=_empty_embedded_vectors)
    remaining_batches: list[tuple[str, ...]] = field(init=False)
    create_available: bool = True
    backup_available: bool = True
    verification_available: bool = True
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC), repr=False)

    def __post_init__(self) -> None:
        self.embedding_requests = {
            item.request_id: item for item in self.policy.expected_embeddings
        }
        self.remaining_batches = list(self.policy.expected_batches)

    def require_write(self, operation: str) -> None:
        """Serve the delegate's second check after the wrapper claimed exact work."""
        if not self.active:
            _authority_fail(f"{operation} precedes Approval consumption")

    def require_current(self, effect_type: EffectType, operation: str) -> None:
        """Recheck the owner-issued deadline immediately before each effect call."""
        self.require_write(operation)
        observed = self.now()
        deadlines = tuple(
            deadline
            for retained_type, deadline in self.policy.effect_deadlines
            if retained_type is effect_type
        )
        if (
            type(observed) is not datetime
            or observed.tzinfo is None
            or observed.utcoffset() is None
            or len(deadlines) != 1
        ):
            _authority_fail(f"{operation} deadline is invalid")
        try:
            deadline = datetime.fromisoformat(deadlines[0].removesuffix("Z") + "+00:00")
        except ValueError as error:
            raise PromotionError(
                PromotionErrorCode.PROFILE_INVALID,
                f"{operation} deadline is invalid",
            ) from error
        if observed.astimezone(UTC) >= deadline.astimezone(UTC):
            _authority_fail(f"{operation} deadline closed")

    def require_all_current(self, operation: str) -> None:
        """Require every effect window still open before Serving-State activation."""
        for effect_type, _deadline in self.policy.effect_deadlines:
            self.require_current(effect_type, operation)

    def activate(self) -> None:
        if self.active:
            _authority_fail("real-effect authority is already active")
        self.active = True

    def claim_embedding(self, profile: EmbeddingProfile, request: EmbeddingRequest) -> None:
        self.require_current(EffectType.EMBEDDING_PROVIDER_CALL, "embedding effect")
        expected = self.embedding_requests.pop(request.request_id, None)
        observed = (
            request.request_id,
            request.record_id,
            request.serving_payload_fingerprint,
            request.text,
            request.text_fingerprint,
            request.profile_id,
            request.batch_id,
            request.batch_position,
            request.cache_key,
            request.token_count,
        )
        if (
            profile != self.policy.embedding_profile
            or expected is None
            or observed
            != (
                expected.request_id,
                expected.record_id,
                expected.serving_payload_fingerprint,
                expected.text,
                expected.text_fingerprint,
                expected.profile_id,
                expected.batch_id,
                expected.batch_position,
                expected.cache_key,
                expected.token_count,
            )
        ):
            _authority_fail("embedding request is outside exact approved work")

    def record_embedding(self, request: EmbeddingRequest, result: EmbeddedVector) -> None:
        if (
            result.receipt.request_id != request.request_id
            or len(result.values) != self.policy.embedding_profile.dimensions
            or any(not math.isfinite(value) for value in result.values)
            or request.record_id in self.embedded_vectors
        ):
            _authority_fail("embedding result is outside exact approved work")
        self.embedded_vectors[request.record_id] = result.values

    def claim_create(self, definition: TargetDefinition) -> None:
        self.require_current(EffectType.PINECONE_MUTATION, "target creation")
        if not self.create_available or definition != self.policy.target_definition:
            _authority_fail("target creation is outside exact approved work")
        self.create_available = False

    def require_target(self, name: str) -> None:
        self.require_write("target access")
        if name != self.policy.target_definition.name:
            _authority_fail("target access is outside exact approved work")

    def claim_upsert(self, name: str, records: tuple[TargetRecord, ...]) -> None:
        self.require_current(EffectType.PINECONE_MUTATION, "target upsert")
        self.require_target(name)
        if not self.remaining_batches:
            _authority_fail("target upsert exceeds exact approved work")
        expected_ids = self.remaining_batches.pop(0)
        if tuple(item.record_id for item in records) != expected_ids:
            _authority_fail("target upsert is outside exact approved batch")
        desired = {item.record_id: item for item in self.policy.desired_records}
        for item in records:
            approved = desired.get(item.record_id)
            if (
                approved is None
                or item.content_fingerprint != approved.content_fingerprint
                or item.metadata_text != approved.record.text
                or item.country != approved.record.country
                or item.jurisdiction != approved.record.jurisdiction
                or item.material_type != approved.record.material_type
                or item.source != approved.record.source
                or item.authority_note != approved.record.authority_note
                or self.embedded_vectors.get(item.record_id) != item.vector
            ):
                _authority_fail("target record is outside exact approved work")

    def claim_verification(self, name: str, record_ids: tuple[str, ...]) -> None:
        self.require_current(EffectType.PINECONE_MUTATION, "target verification")
        self.require_target(name)
        if not self.verification_available or record_ids != self.policy.expected_record_ids:
            _authority_fail("target verification is outside exact approved work")
        self.verification_available = False

    def claim_backup(
        self,
        request: BackupRequest,
        target_name: str,
        inventory_fingerprint: str,
        backup_profile_ref: ImmutableReference | None,
    ) -> None:
        self.require_current(EffectType.BACKUP_MUTATION, "backup effect")
        if (
            not self.backup_available
            or request != self.policy.backup_request
            or target_name != self.policy.target_definition.name
            or inventory_fingerprint != self.policy.inventory_fingerprint
            or backup_profile_ref != self.policy.backup_profile_ref
        ):
            _authority_fail("backup request is outside exact approved work")
        self.backup_available = False

    def require_delete(self, operation: str) -> None:
        """V1 never converts ordinary promotion authority into deletion authority."""
        raise PromotionError(PromotionErrorCode.BROAD_RETIREMENT_FORBIDDEN, operation)


@dataclass(frozen=True, slots=True)
class V1RealEffectActivation:
    """One composed authority opened only by the matching consumed Approval."""

    approval_id: str
    execution_lineage_id: str
    manifest_fingerprint: str
    serving_profile_fingerprint: str
    _gate: _EffectGate = field(repr=False, compare=False)

    def activate(self, approval: ApprovalProjection) -> None:
        """Open the adapters only after exact durable Approval consumption."""
        if (
            type(approval) is not ApprovalProjection
            or approval.state is not ApprovalState.CONSUMED
            or approval.decision.approval_id != self.approval_id
            or approval.decision.manifest_fingerprint != self.manifest_fingerprint
            or approval.execution_lineage_id != self.execution_lineage_id
        ):
            _authority_fail("consumed Approval does not activate real effects")
        self._gate.activate()

    def bind_backup(
        self,
        request: BackupRequest,
        adapter: IndependentBackupAdapter,
    ) -> BackupPort:
        """Bind the exact backup adapter to this same one-shot Approval policy."""
        if request != self._gate.policy.backup_request:
            _authority_fail("backup request is outside exact approved work")
        return _ApprovalGatedBackup(adapter, request, self._gate)

    def require_current(self) -> None:
        """Block Serving-State activation after any approved effect deadline closes."""
        self._gate.require_all_current("Serving-State activation")


def _consume_authority(
    value: V1RealEffectAuthority,
    profile: ServingCapabilityProfile,
    now: Callable[[], datetime],
) -> tuple[V1RealEffectActivation, _EffectGate]:
    record = _ISSUED.get(id(value))
    if (
        type(value) is not V1RealEffectAuthority
        or record is None
        or record[0]() is not value
        or record[1] != value.fingerprint
        or value.serving_profile_fingerprint != profile.fingerprint
        or len(value.effect_intent_ids) != _REQUIRED_EFFECT_INTENT_COUNT
        or len(value.effect_intent_fingerprints) != _REQUIRED_EFFECT_INTENT_COUNT
    ):
        _authority_fail("real-effect authority invalid")
    _ISSUED.pop(id(value), None)
    gate = _EffectGate(record[2], now=now)
    activation = V1RealEffectActivation(
        value.approval_id,
        value.execution_lineage_id,
        value.manifest_fingerprint,
        value.serving_profile_fingerprint,
        gate,
    )
    return activation, gate


@dataclass(frozen=True, slots=True)
class _ApprovalGatedEmbedding:
    """Embedding port that is inert until its exact Approval is consumed."""

    _delegate: AzureOpenAIEmbeddingAdapter
    _gate: _EffectGate

    @property
    def serving_profile_fingerprint(self) -> str | None:
        return self._delegate.serving_profile_fingerprint

    @property
    def deployment_name(self) -> str:
        return self._delegate.deployment_name

    @property
    def api_contract(self) -> str:
        return self._delegate.api_contract

    @property
    def timeout_seconds(self) -> int | None:
        return self._delegate.timeout_seconds

    def embed(self, profile: EmbeddingProfile, request: EmbeddingRequest) -> EmbeddedVector:
        self._gate.claim_embedding(profile, request)
        result = self._delegate.embed(profile, request)
        self._gate.record_embedding(request, result)
        return result


@dataclass(frozen=True, slots=True)
class _ApprovalGatedTarget:
    """Serving-target port closed across reads and writes until consumption."""

    _delegate: PineconeServingTargetStore
    _gate: _EffectGate

    @property
    def target_name(self) -> str:
        return self._delegate.target_name

    @property
    def project_id(self) -> str:
        return self._delegate.project_id

    @property
    def namespace(self) -> str:
        return self._delegate.namespace

    @property
    def page_size(self) -> int:
        return self._delegate.page_size

    @property
    def timeout_seconds(self) -> int | None:
        return self._delegate.timeout_seconds

    def create(self, definition: TargetDefinition) -> None:
        self._gate.claim_create(definition)
        self._delegate.create(definition)

    def describe(self, name: str) -> TargetDefinition:
        self._gate.require_target(name)
        return self._delegate.describe(name)

    def upsert_batch(self, name: str, records: tuple[TargetRecord, ...]) -> None:
        self._gate.claim_upsert(name, records)
        self._delegate.upsert_batch(name, records)

    def enumerate(self, name: str) -> tuple[TargetRecord, ...]:
        self._gate.require_target(name)
        return self._delegate.enumerate(name)

    def delete_exact(self, name: str, exact_name: str) -> str:
        self._gate.require_delete(f"deleting index {name}")
        return self._delegate.delete_exact(name, exact_name)

    def contains(self, name: str) -> bool:
        self._gate.require_target(name)
        return self._delegate.contains(name)

    def verify_queries(self, name: str, expected_record_ids: tuple[str, ...]) -> None:
        self._gate.claim_verification(name, expected_record_ids)
        self._delegate.verify_queries(name, expected_record_ids)


@dataclass(frozen=True, slots=True)
class _ApprovalGatedBackup:
    """Independent backup port bound to the same exact one-shot authority."""

    _delegate: IndependentBackupAdapter
    _request: BackupRequest
    _gate: _EffectGate

    @property
    def backup_profile_ref(self) -> ImmutableReference:
        return self._delegate.backup_profile_ref

    def create_and_verify(
        self,
        target_name: str,
        inventory_fingerprint: str,
        backup_profile_ref: ImmutableReference | None,
    ) -> BackupVerification:
        self._gate.claim_backup(
            self._request,
            target_name,
            inventory_fingerprint,
            backup_profile_ref,
        )
        return self._delegate.create_and_verify(
            target_name,
            inventory_fingerprint,
            backup_profile_ref,
        )


@dataclass(frozen=True, slots=True)
class V1RealPromotionEffects:
    """Composed provider adapters; construction performs no provider operation."""

    embeddings: _ApprovalGatedEmbedding
    targets: _ApprovalGatedTarget
    activation: V1RealEffectActivation
    serving_profile_fingerprint: str
    target_name: str


def compose_v1_real_effects(  # noqa: PLR0913 - two credentials, two transports, authority.
    profile: ServingCapabilityProfile,
    azure_credential: bytes,
    pinecone_credential: bytes,
    embedding_transport: ProviderCall,
    target_transport: ProviderCall,
    *,
    authority: V1RealEffectAuthority,
    backup_profile_ref: ImmutableReference,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> V1RealPromotionEffects:
    """Compose only exact profile-matched adapters, with deletion always disabled."""
    try:
        validate_serving_capability_profile_authority(profile)
        profile.validate()
    except (ProfileError, TypeError, ValueError) as error:
        raise PromotionError(
            PromotionErrorCode.PROFILE_INVALID, "serving profile authority"
        ) from error
    activation, gate = _consume_authority(authority, profile, now)
    azure = AzureOpenAIConfig.from_credential_json(azure_credential)
    pinecone = PineconeConfig.from_credential_json(pinecone_credential)
    embedding = profile.embedding
    if (
        azure.deployment != embedding.deployment_name
        or azure.api_version != embedding.api_contract
        or not pinecone.index.startswith(profile.index_prefix)
        or pinecone.project_id != profile.pinecone_project_id
        or backup_profile_ref != profile.backup_profile_ref
        or getattr(embedding_transport, "timeout_seconds", None) != profile.provider_timeout_seconds
        or getattr(target_transport, "timeout_seconds", None) != profile.target_timeout_seconds
    ):
        raise PromotionError(PromotionErrorCode.PROFILE_INVALID, "credential/profile drift")
    embedding_adapter = AzureOpenAIEmbeddingAdapter(
        azure,
        embedding_transport,
        serving_profile_fingerprint=profile.fingerprint,
    )
    target_adapter = PineconeServingTargetStore(
        pinecone,
        target_transport,
        operation_gate=gate,
        namespace=profile.namespace,
        page_size=profile.readback_page_size,
    )
    return V1RealPromotionEffects(
        _ApprovalGatedEmbedding(embedding_adapter, gate),
        _ApprovalGatedTarget(target_adapter, gate),
        activation,
        profile.fingerprint,
        pinecone.index,
    )
