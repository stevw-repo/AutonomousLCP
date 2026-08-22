"""Durable authorization of one consumed-Approval promotion execution lineage."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

from asklegal_contracts import SchemaRegistry, canonicalize, fingerprint
from asklegal_contracts.json_types import checked_json_value
from asklegal_management_register import (
    RegisteredExecutionAuthorizationCommand,
    V1CommandResult,
)

from .registered_approval import (
    RegisteredApprovalCandidate,
    RegisteredApprovalCandidateSource,
)

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_COMMAND_ID = re.compile(r"^cmd_[0-9a-f]{48}$")
_LINEAGE_ID = re.compile(r"^exe_[0-9a-f]{48}$")
_IDENTIFIER = re.compile(r"^[a-z][a-z0-9]{2}_[0-9a-f]{48}$")


class RegisteredExecutionAuthorizationErrorCode(StrEnum):
    """Closed no-effect execution-authorization failures."""

    INVALID = "REGISTERED_EXECUTION_AUTHORIZATION_INVALID"
    NOT_APPROVED = "REGISTERED_EXECUTION_AUTHORIZATION_NOT_APPROVED"
    REJECTED = "REGISTERED_EXECUTION_AUTHORIZATION_REJECTED"


class RegisteredExecutionAuthorizationError(RuntimeError):
    """One safe execution-authorization failure."""

    def __init__(self, code: RegisteredExecutionAuthorizationErrorCode) -> None:
        """Create one closed failure without source data."""
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True, slots=True)
class RegisteredExecutionAuthorizationContext:
    """Exact no-effect facts bound to the authorization transition."""

    at: str
    command_expires_at: str
    execution_lineage_id: str
    execution_lineage_fingerprint: str
    validation_evidence_id: str
    validation_evidence_fingerprint: str
    promotion_worker_identity_id: str
    promotion_worker_identity_fingerprint: str


class RegisteredExecutionAuthorizationWriter(Protocol):
    """Specialized Promotion-owned execution-authorization command."""

    def authorize(
        self,
        command: RegisteredExecutionAuthorizationCommand,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Authorize once or exactly resolve a committed command."""
        ...


class RegisteredExecutionAuthorizationService:
    """Create the durable PLANNED-to-AUTHORIZED transition after consumption."""

    def __init__(
        self,
        candidates: RegisteredApprovalCandidateSource,
        writer: RegisteredExecutionAuthorizationWriter,
        schemas: SchemaRegistry,
    ) -> None:
        """Bind complete proposal reread, specialized writer, and schemas."""
        self._candidates = candidates
        self._writer = writer
        self._schemas = schemas

    def authorize(
        self,
        proposal_package_id: str,
        command_id: str,
        context: RegisteredExecutionAuthorizationContext,
        *,
        simulate_lost_ack: bool = False,
    ) -> V1CommandResult:
        """Authorize one consumed lineage without creating or claiming an effect."""
        candidate = self._candidates.approved(proposal_package_id)
        if candidate is None:
            raise RegisteredExecutionAuthorizationError(
                RegisteredExecutionAuthorizationErrorCode.NOT_APPROVED
            )
        _validate_inputs(candidate, proposal_package_id, command_id, context)
        authorization_fingerprint = _authorization_fingerprint(candidate, context)
        event_id = _stable_id(
            "pex",
            candidate.approval_id,
            context.execution_lineage_id,
            authorization_fingerprint,
        )
        event = checked_json_value(
            {
                "action_id": "AUTHORIZE",
                "approval_ref": _reference(
                    "APPROVAL",
                    candidate.approval_id,
                    candidate.decision_fingerprint,
                ),
                "attempt_number": 0,
                "event_time": context.at,
                "execution_lineage_id": context.execution_lineage_id,
                "external_effects": "NONE",
                "failure_codes": [],
                "from_state": "EXECUTION_PLANNED",
                "idempotency": {
                    "idempotency_key": f"authorize:{context.execution_lineage_id}",
                    "input_fingerprint": authorization_fingerprint,
                },
                "immutable": True,
                "promotion_execution_event_id": event_id,
                "promotion_manifest_ref": _reference(
                    "PROMOTION_MANIFEST",
                    candidate.manifest.manifest_id,
                    candidate.manifest.fingerprint,
                ),
                "reason_codes": [
                    "APPROVAL_EXACTLY_BOUND",
                    "TRANSITION_ALLOWED",
                    "VALIDATION_COMPLETE",
                ],
                "receipt_refs": [],
                "result_code": "SUCCEEDED",
                "schema_id": "asklegal.promotion-execution-event",
                "schema_version": "1.0.0",
                "to_state": "EXECUTION_AUTHORIZED",
            }
        )
        self._schemas.validate(
            event,
            "schemas/promotion-domain.schema.json#/$defs/promotion_execution_event",
        )
        command_document = checked_json_value(
            {
                "action": "AUTHORIZE_REGISTERED_PROMOTION_EXECUTION",
                "approval_id": candidate.approval_id,
                "authorization_fingerprint": authorization_fingerprint,
                "decision_fingerprint": candidate.decision_fingerprint,
                "execution_lineage_fingerprint": context.execution_lineage_fingerprint,
                "execution_lineage_id": context.execution_lineage_id,
                "manifest_fingerprint": candidate.manifest.fingerprint,
                "manifest_id": candidate.manifest.manifest_id,
                "promotion_worker_identity_fingerprint": (
                    context.promotion_worker_identity_fingerprint
                ),
                "promotion_worker_identity_id": context.promotion_worker_identity_id,
                "proposal_package_id": candidate.proposal_package_id,
                "validation_evidence_fingerprint": context.validation_evidence_fingerprint,
                "validation_evidence_id": context.validation_evidence_id,
            }
        )
        result = self._writer.authorize(
            RegisteredExecutionAuthorizationCommand(
                command_id,
                canonicalize(command_document),
                candidate.approval_id,
                candidate.proposal_package_id,
                bytes.fromhex(candidate.decision_fingerprint.removeprefix("sha256:")),
                candidate.manifest.manifest_id,
                candidate.manifest.fingerprint,
                context.execution_lineage_id,
                context.execution_lineage_fingerprint,
                authorization_fingerprint,
                context.command_expires_at,
                event_id,
                canonicalize(event),
            ),
            simulate_lost_ack=simulate_lost_ack,
        )
        if result.result_code != "APPLIED" or result.authoritative_version != 1:
            raise RegisteredExecutionAuthorizationError(
                RegisteredExecutionAuthorizationErrorCode.REJECTED
            )
        return result


def _authorization_fingerprint(
    candidate: RegisteredApprovalCandidate,
    context: RegisteredExecutionAuthorizationContext,
) -> str:
    return fingerprint(
        checked_json_value(
            {
                "approval_id": candidate.approval_id,
                "decision_fingerprint": candidate.decision_fingerprint,
                "execution_lineage_fingerprint": context.execution_lineage_fingerprint,
                "execution_lineage_id": context.execution_lineage_id,
                "manifest_fingerprint": candidate.manifest.fingerprint,
                "manifest_id": candidate.manifest.manifest_id,
                "promotion_worker_identity_fingerprint": (
                    context.promotion_worker_identity_fingerprint
                ),
                "promotion_worker_identity_id": context.promotion_worker_identity_id,
                "proposal_package_id": candidate.proposal_package_id,
                "validation_evidence_fingerprint": context.validation_evidence_fingerprint,
                "validation_evidence_id": context.validation_evidence_id,
            }
        )
    )


def _validate_inputs(
    candidate: RegisteredApprovalCandidate,
    proposal_package_id: str,
    command_id: str,
    context: RegisteredExecutionAuthorizationContext,
) -> None:
    identifiers = (
        candidate.proposal_package_id,
        candidate.approval_id,
        candidate.manifest.manifest_id,
        context.validation_evidence_id,
        context.promotion_worker_identity_id,
    )
    fingerprints = (
        candidate.decision_fingerprint,
        candidate.manifest.fingerprint,
        context.execution_lineage_fingerprint,
        context.validation_evidence_fingerprint,
        context.promotion_worker_identity_fingerprint,
    )
    if (
        candidate.proposal_package_id != proposal_package_id
        or _COMMAND_ID.fullmatch(command_id) is None
        or _LINEAGE_ID.fullmatch(context.execution_lineage_id) is None
        or any(_IDENTIFIER.fullmatch(value) is None for value in identifiers)
        or any(_FINGERPRINT.fullmatch(value) is None for value in fingerprints)
        or not context.at
        or context.at >= context.command_expires_at
    ):
        raise RegisteredExecutionAuthorizationError(
            RegisteredExecutionAuthorizationErrorCode.INVALID
        )


def _reference(reference_type: str, reference_id: str, reference_fingerprint: str) -> object:
    return {
        "fingerprint": reference_fingerprint,
        "ref_id": reference_id,
        "ref_type": reference_type,
    }


def _stable_id(prefix: str, *values: str) -> str:
    return f"{prefix}_{sha256(chr(31).join(values).encode()).hexdigest()[:48]}"
