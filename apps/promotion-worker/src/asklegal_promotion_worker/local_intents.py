"""Canonical file-backed Effect Intent projection for local V1 promotion."""

from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path
from secrets import token_hex
from typing import Never, TypeIs

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_domain import (
    ApplicationCode,
    ContractReference,
    DeclaredCompensation,
    DestinationClass,
    EffectCapability,
    EffectIntent,
    EffectType,
    ImmutableReference,
    NoCompensation,
    ReferenceType,
    RetryClass,
    StopCondition,
)
from asklegal_promotion import (
    PromotionError,
    PromotionErrorCode,
    PromotionManifest,
    ServingCapabilityProfile,
    promotion_action_authority_document,
    promotion_action_authority_fingerprint,
    validate_serving_capability_profile_authority,
)

from .registered_execution_begin import effect_intent_document

_SCHEMA_ID = "asklegal.local-promotion-effect-intents/v1"
_INTENT_FIELDS = {
    "aggregate_ref",
    "attempt_ceiling",
    "capability_profile_ref",
    "command_ref",
    "compensation",
    "created_at",
    "deadline",
    "destination_class",
    "effect_command_fingerprint",
    "effect_intent_id",
    "effect_type",
    "execution_lineage_ref",
    "expected_remote_precondition_ref",
    "immutable",
    "input_refs",
    "owning_application",
    "permitted_checkpoint",
    "required_capability",
    "retry_class",
    "schema_id",
    "schema_version",
    "stable_idempotency_key",
    "stop_conditions",
    "success_postcondition_ref",
}
_REQUIRED_EFFECTS = (
    EffectType.EMBEDDING_PROVIDER_CALL,
    EffectType.PINECONE_MUTATION,
    EffectType.BACKUP_MUTATION,
)


def local_effect_intent_ledger_bytes(
    execution_lineage_id: str, intents: tuple[EffectIntent, ...]
) -> bytes:
    """Freeze one exact lineage's retained local Effect Intent projection."""
    if (
        type(execution_lineage_id) is not str
        or not execution_lineage_id
        or type(intents) is not tuple
        or not intents
        or any(
            type(item) is not EffectIntent
            or item.execution_lineage_ref.ref_id != execution_lineage_id
            for item in intents
        )
        or len({item.effect_intent_id for item in intents}) != len(intents)
    ):
        _fail("invalid retained intent ledger input")
    return canonicalize(
        checked_json_value(
            {
                "effect_intents": [effect_intent_document(item) for item in intents],
                "execution_lineage_id": execution_lineage_id,
                "schema_id": _SCHEMA_ID,
            }
        )
    )


def retain_v1_effect_intents(  # noqa: PLR0913 - exact authority lineage.
    root: Path,
    *,
    approval_id: str,
    execution_lineage_id: str,
    execution_time: str,
    manifest: PromotionManifest,
    profile: ServingCapabilityProfile,
) -> LocalRetainedEffectIntentSource:
    """Derive and atomically retain exact intents from approved package/profile facts."""
    try:
        validate_serving_capability_profile_authority(profile)
    except Exception as error:
        raise PromotionError(
            PromotionErrorCode.PROFILE_INVALID, "serving profile invalid"
        ) from error
    actions = tuple(item for item in manifest.actions if item.effect_type in _REQUIRED_EFFECTS)
    if (
        not root.is_absolute()
        or root.is_symlink()
        or not root.is_dir()
        or tuple(item.effect_type for item in actions) != _REQUIRED_EFFECTS
        or manifest.embedding_profile != profile.embedding
        or manifest.environment != profile.environment
    ):
        _fail("effect intent authority invalid")
    lineage_material = canonicalize(
        checked_json_value(
            {
                "approval_id": approval_id,
                "execution_lineage_id": execution_lineage_id,
                "manifest_fingerprint": manifest.fingerprint,
                "serving_profile_fingerprint": profile.fingerprint,
            }
        )
    )
    lineage_fingerprint = "sha256:" + sha256(lineage_material).hexdigest()
    lineage_ref = ImmutableReference(
        ReferenceType.EXECUTION_LINEAGE,
        execution_lineage_id,
        lineage_fingerprint,
    )
    intents: list[EffectIntent] = []
    for action in actions:
        action_fingerprint = promotion_action_authority_fingerprint(action)
        command_material = canonicalize(
            checked_json_value(
                {
                    "action": promotion_action_authority_document(action),
                    "action_fingerprint": action_fingerprint,
                    "approval_id": approval_id,
                    "execution_lineage_id": execution_lineage_id,
                    "manifest_fingerprint": manifest.fingerprint,
                    "serving_profile_fingerprint": profile.fingerprint,
                }
            )
        )
        command_fingerprint = "sha256:" + sha256(command_material).hexdigest()
        command_id = (
            "cmd_" + sha256((execution_lineage_id + action.action_id).encode()).hexdigest()[:48]
        )
        effect_intent_id = (
            "efi_"
            + sha256(
                (execution_lineage_id + action_fingerprint + command_fingerprint).encode()
            ).hexdigest()[:48]
        )
        intents.append(
            EffectIntent(
                effect_intent_id,
                execution_time,
                action.effect_type,
                action.owning_application,
                lineage_ref,
                ImmutableReference(ReferenceType.COMMAND, command_id, command_fingerprint),
                lineage_ref,
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
        )
    content = local_effect_intent_ledger_bytes(execution_lineage_id, tuple(intents))
    path = root / f"{execution_lineage_id}.json"
    _atomic_create_or_match(path, content)
    source = LocalRetainedEffectIntentSource(path)
    if source.effect_intents(execution_lineage_id) != tuple(intents):
        _fail("retained intent readback invalid")
    return source


def _atomic_create_or_match(path: Path, content: bytes) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            _fail("retained intent state drift")
        return
    temporary = path.parent / f".{path.name}.{token_hex(16)}.tmp"
    descriptor = -1
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("retained intent write failed")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                _fail("retained intent state drift")
        if path.read_bytes() != content:
            _fail("retained intent readback invalid")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


class LocalRetainedEffectIntentSource:
    """Reread exact canonical Effect Intents from one explicit local state file."""

    def __init__(self, state_path: Path) -> None:
        """Bind one non-symlinked regular state file without caching its bytes."""
        if state_path.is_symlink() or not state_path.is_file():
            _fail("retained intent state unavailable")
        self._state_path = state_path

    def effect_intents(self, execution_lineage_id: str) -> tuple[EffectIntent, ...]:
        """Reread and strictly reconstruct one exact lineage on every request."""
        try:
            content = self._state_path.read_bytes()
            value = parse_json_bytes(content, max_bytes=5_000_000)
        except (OSError, ContractViolation) as error:
            raise PromotionError(
                PromotionErrorCode.PROFILE_INVALID, "retained intent state invalid"
            ) from error
        if not _object(value):
            _fail("retained intent state drift")
        document = value
        if (
            set(document) != {"effect_intents", "execution_lineage_id", "schema_id"}
            or document.get("schema_id") != _SCHEMA_ID
            or document.get("execution_lineage_id") != execution_lineage_id
            or canonicalize(document) != content
        ):
            _fail("retained intent state drift")
        raw_intents_value = document.get("effect_intents")
        if not _array(raw_intents_value) or not raw_intents_value:
            _fail("retained intents missing")
        try:
            intents = tuple(_intent(item) for item in raw_intents_value)
        except (KeyError, TypeError, ValueError) as error:
            raise PromotionError(
                PromotionErrorCode.PROFILE_INVALID, "retained intent contract invalid"
            ) from error
        if any(
            item.execution_lineage_ref.ref_id != execution_lineage_id for item in intents
        ) or len({item.effect_intent_id for item in intents}) != len(intents):
            _fail("retained intent lineage drift")
        return intents


def _intent(value: JsonValue) -> EffectIntent:
    if not isinstance(value, dict) or set(value) != _INTENT_FIELDS:
        _invalid()
    if (
        value.get("schema_id") != "asklegal.effect-intent"
        or value.get("schema_version") != "1.0.0"
        or value.get("immutable") is not True
    ):
        _invalid()
    raw_inputs = value.get("input_refs")
    raw_stops = value.get("stop_conditions")
    if not isinstance(raw_inputs, list) or not isinstance(raw_stops, list):
        raise TypeError
    return EffectIntent(
        _text(value, "effect_intent_id"),
        _text(value, "created_at"),
        EffectType(_text(value, "effect_type")),
        ApplicationCode(_text(value, "owning_application")),
        _reference(value.get("aggregate_ref")),
        _reference(value.get("command_ref")),
        _reference(value.get("execution_lineage_ref")),
        _text(value, "permitted_checkpoint"),
        tuple(_reference(item) for item in raw_inputs),
        _text(value, "effect_command_fingerprint"),
        EffectCapability(_text(value, "required_capability")),
        _reference(value.get("capability_profile_ref")),
        DestinationClass(_text(value, "destination_class")),
        _text(value, "stable_idempotency_key"),
        RetryClass(_text(value, "retry_class")),
        _integer(value, "attempt_ceiling"),
        _text(value, "deadline"),
        tuple(StopCondition(_list_text(item)) for item in raw_stops),
        _contract(value.get("expected_remote_precondition_ref")),
        _contract(value.get("success_postcondition_ref")),
        _compensation(value.get("compensation")),
    )


def _reference(value: JsonValue | None) -> ImmutableReference:
    if not isinstance(value, dict) or set(value) != {"fingerprint", "ref_id", "ref_type"}:
        _invalid()
    return ImmutableReference(
        ReferenceType(_text(value, "ref_type")),
        _text(value, "ref_id"),
        _text(value, "fingerprint"),
    )


def _contract(value: JsonValue | None) -> ContractReference:
    if not isinstance(value, dict) or set(value) != {"contract_id", "fingerprint", "version"}:
        _invalid()
    return ContractReference(
        _text(value, "contract_id"),
        _text(value, "version"),
        _text(value, "fingerprint"),
    )


def _compensation(value: JsonValue | None) -> NoCompensation | DeclaredCompensation:
    if isinstance(value, dict) and value == {"mode": "NO_COMPENSATION"}:
        return NoCompensation()
    if (
        isinstance(value, dict)
        and set(value) == {"contract_ref", "mode"}
        and value.get("mode") == "DECLARED_COMPENSATION"
    ):
        return DeclaredCompensation(_contract(value.get("contract_ref")))
    return _invalid()


def _text(value: dict[str, JsonValue], field: str) -> str:
    item = value.get(field)
    if type(item) is not str or not item or item.strip() != item:
        raise TypeError(field)
    return item


def _list_text(value: JsonValue) -> str:
    if type(value) is not str or not value or value.strip() != value:
        raise TypeError
    return value


def _integer(value: dict[str, JsonValue], field: str) -> int:
    item = value.get(field)
    if type(item) is not int:
        raise TypeError(field)
    return item


def _object(value: object) -> TypeIs[dict[str, JsonValue]]:
    return isinstance(value, dict)


def _array(value: object) -> TypeIs[list[JsonValue]]:
    return isinstance(value, list)


def _invalid() -> Never:
    raise ValueError


def _fail(detail: str) -> Never:
    raise PromotionError(PromotionErrorCode.PROFILE_INVALID, detail)
