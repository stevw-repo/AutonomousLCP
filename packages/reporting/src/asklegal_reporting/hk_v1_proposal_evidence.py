"""Shared canonical evidence contracts for Hong Kong V1 proposal readiness."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Literal, Never
from weakref import ReferenceType, ref

from asklegal_contracts import ContractViolation, canonicalize, parse_json_bytes
from asklegal_contracts.json_types import checked_json_value

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_FINGERPRINT = re.compile(r"^sha256:[0-9a-f]{64}$")
_BATCH_ID = re.compile(r"^[a-z0-9][a-z0-9-]{2,99}$")
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{2,1023}$")
_UTC = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")
_SCOPES = {
    "CASES": frozenset({"HK-CASE-BINDING-POST-1997"}),
    "LEGISLATION": frozenset(
        {
            "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
            "HK-LEG-ORDINANCES",
            "HK-LEG-SUBSIDIARY",
        }
    ),
}
_FIELDS = frozenset(
    {
        "schema_id",
        "material_family",
        "scope_id",
        "batch_id",
        "observation_cutoff",
        "acquisition_manifest_fingerprint",
        "journal_head_fingerprint",
        "semantic_profile_fingerprint",
        "capability_evidence_ref",
        "evidence_set_fingerprint",
        "evidence_items",
        "model_requests",
        "provider_invocation_count",
        "release_state",
        "fingerprint",
    }
)
_EVIDENCE_FIELDS = frozenset(
    {"evidence_ref", "fingerprint", "language", "subject_id", "text_fingerprint"}
)
_REQUEST_FIELDS = frozenset(
    {
        "evidence_fingerprint",
        "evidence_ref",
        "request_id",
        "semantic_profile_fingerprint",
        "subject_id",
    }
)
_PROFILE_FIELDS = frozenset(
    {
        "schema_id",
        "capability",
        "issuer_application",
        "profile_fingerprint",
        "status",
        "fingerprint",
    }
)
_CAPABILITY_FIELDS = frozenset(
    {
        "schema_id",
        "capability",
        "application",
        "role",
        "observation_cutoff",
        "profile_receipt_ref",
        "profile_receipt_fingerprint",
        "profile_fingerprint",
        "status",
        "fingerprint",
    }
)
_CAPABILITY_IDENTITIES = {
    "MODEL": ("LEGAL_PROCESSING_WORKER", "generative_llm_provider"),
    "EMBEDDING": ("PROMOTION_WORKER", "embedding_provider"),
}
_DISABLED_STATUS = "PROVIDER_DISABLED_PREPARATION_ONLY"


class ProposalEvidenceError(ValueError):
    """One closed shared proposal-evidence contract failure."""


@dataclass(frozen=True, slots=True)
class ExactProposalArtifactReceipt:
    """Immutable local artifact coordinate whose bytes must be re-read."""

    logical_ref: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ProposalEvidenceArtifact:
    """Canonical self-fingerprinted bytes at one exact logical reference."""

    logical_ref: str
    fingerprint: str
    content: bytes


@dataclass(frozen=True, slots=True, init=False, eq=False, weakref_slot=True)
class VerifiedSemanticCapability:
    """Reader-verified exact model or embedding capability evidence."""

    capability: Literal["MODEL", "EMBEDDING"]
    profile_fingerprint: str
    profile_receipt_ref: str
    profile_receipt_fingerprint: str
    evidence_ref: str
    evidence_fingerprint: str
    status: Literal["PROVIDER_DISABLED_PREPARATION_ONLY"]


_VerifiedRegistration = tuple[ReferenceType[VerifiedSemanticCapability], tuple[str, ...]]
_VERIFIED_CAPABILITIES: dict[int, _VerifiedRegistration] = {}


@dataclass(frozen=True, slots=True)
class PreparedBatchArtifact:
    """Strictly parsed, provider-disabled prepared-batch evidence."""

    material_family: Literal["CASES", "LEGISLATION"]
    scope_id: str
    batch_id: str
    observation_cutoff: str
    acquisition_manifest_fingerprint: str
    journal_head_fingerprint: str
    evidence_set_fingerprint: str
    evidence_refs: tuple[str, ...]
    semantic_profile_fingerprint: str
    capability_evidence_ref: str
    fingerprint: str
    receipt: ExactProposalArtifactReceipt


def provider_disabled_profile_receipt_ref(capability: str, profile_fingerprint: str) -> str:
    """Return the exact immutable logical path for one profile receipt."""
    kind = _capability(capability)
    if not _valid_fingerprint(profile_fingerprint):
        _fail("SEMANTIC_PROFILE_RECEIPT_INVALID")
    return (
        f"proposal-readiness/profile-receipts/{kind.lower()}/"
        f"{profile_fingerprint.removeprefix('sha256:')}.json"
    )


def build_provider_disabled_profile_receipt(
    capability: str,
    profile_fingerprint: str,
) -> ProposalEvidenceArtifact:
    """Reject the obsolete hash-only minting path; applications own issuance."""
    del capability, profile_fingerprint
    return _fail("SEMANTIC_PROFILE_AUTHORITY_REQUIRED")


def build_provider_disabled_capability_evidence(
    capability: str,
    profile_receipt: ProposalEvidenceArtifact,
    observation_cutoff: str,
) -> ProposalEvidenceArtifact:
    """Reject the obsolete shared minting path; applications own issuance."""
    del capability, profile_receipt, observation_cutoff
    return _fail("SEMANTIC_PROFILE_AUTHORITY_REQUIRED")


def verify_provider_disabled_semantic_capability(  # noqa: PLR0913, PLR0917 - exact documents.
    capability: str,
    profile_receipt_ref: str,
    profile_receipt_content: bytes,
    evidence_ref: str,
    evidence_content: bytes,
    expected_observation_cutoff: str,
) -> VerifiedSemanticCapability:
    """Verify both exact documents and issue a process-local capability snapshot."""
    try:
        kind = _capability(capability)
        profile_fingerprint, profile_receipt_fingerprint = _parse_profile_receipt(
            profile_receipt_ref, profile_receipt_content, kind
        )
        evidence_fingerprint = _parse_capability_evidence(
            evidence_ref,
            evidence_content,
            kind,
            expected_observation_cutoff,
            profile_receipt_ref,
            profile_receipt_fingerprint,
            profile_fingerprint,
        )
        value = object.__new__(VerifiedSemanticCapability)
        for name, item in (
            ("capability", kind),
            ("profile_fingerprint", profile_fingerprint),
            ("profile_receipt_ref", profile_receipt_ref),
            ("profile_receipt_fingerprint", profile_receipt_fingerprint),
            ("evidence_ref", evidence_ref),
            ("evidence_fingerprint", evidence_fingerprint),
            ("status", _DISABLED_STATUS),
        ):
            object.__setattr__(value, name, item)
        snapshot = _semantic_snapshot(value)
        value_id = id(value)

        def cleanup(
            dead: ReferenceType[VerifiedSemanticCapability], value_id: int = value_id
        ) -> None:
            current = _VERIFIED_CAPABILITIES.get(value_id)
            if current is not None and current[0] is dead:
                del _VERIFIED_CAPABILITIES[value_id]

        _VERIFIED_CAPABILITIES[value_id] = (ref(value, cleanup), snapshot)
    except (ContractViolation, KeyError, TypeError, ValueError) as error:
        if isinstance(error, ProposalEvidenceError):
            raise
        code = "SEMANTIC_CAPABILITY_EVIDENCE_INVALID"
        raise ProposalEvidenceError(code) from error
    return value


def validate_verified_semantic_capability(value: object) -> VerifiedSemanticCapability:
    """Reject reconstructed or mutated capability values before reporting use."""
    if type(value) is not VerifiedSemanticCapability:
        _fail("SEMANTIC_CAPABILITY_PROVENANCE_INVALID")
    try:
        registration = _VERIFIED_CAPABILITIES.get(id(value))
        if (
            registration is None
            or registration[0]() is not value
            or registration[1] != _semantic_snapshot(value)
        ):
            _fail("SEMANTIC_CAPABILITY_PROVENANCE_INVALID")
    except (AttributeError, TypeError, ValueError) as error:
        if isinstance(error, ProposalEvidenceError):
            raise
        code = "SEMANTIC_CAPABILITY_PROVENANCE_INVALID"
        raise ProposalEvidenceError(code) from error
    return value


def prepared_batch_logical_ref(
    material_family: str,
    scope_id: str,
    batch_id: str,
    evidence_set_fingerprint: str,
    semantic_profile_fingerprint: str,
) -> str:
    """Return the only logical path for one exact prepared batch."""
    if (
        material_family not in _SCOPES
        or scope_id not in _SCOPES[material_family]
        or type(batch_id) is not str
        or _BATCH_ID.fullmatch(batch_id) is None
        or any(
            type(value) is not str or _FINGERPRINT.fullmatch(value) is None
            for value in (evidence_set_fingerprint, semantic_profile_fingerprint)
        )
    ):
        _fail("PREPARED_BATCH_PATH_INVALID")
    return "/".join(
        (
            "prepared-batches",
            material_family.lower(),
            scope_id.lower(),
            batch_id,
            evidence_set_fingerprint.removeprefix("sha256:"),
            f"{semantic_profile_fingerprint.removeprefix('sha256:')}.json",
        )
    )


def parse_prepared_batch_artifact(  # noqa: C901, PLR0912 - closed artifact boundary.
    receipt: ExactProposalArtifactReceipt,
    content: bytes,
) -> PreparedBatchArtifact:
    """Read and revalidate every proposal-relevant prepared-batch fact."""
    try:
        if (
            type(receipt) is not ExactProposalArtifactReceipt
            or not _valid_ref(receipt.logical_ref)
            or not _valid_fingerprint(receipt.fingerprint)
            or type(content) is not bytes
            or not content
            or receipt.fingerprint != _bytes_fingerprint(content)
        ):
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        document = parse_json_bytes(content, max_bytes=1_000_000)
        if type(document) is not dict or frozenset(document) != _FIELDS:
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        if canonicalize(document) != content or document["schema_id"] != (
            "asklegal.hk-v1-prepared-verified-batch/v1"
        ):
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        embedded_fingerprint = _fingerprint(document["fingerprint"])
        unsigned = {name: item for name, item in document.items() if name != "fingerprint"}
        if embedded_fingerprint != _bytes_fingerprint(canonicalize(unsigned)):
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        family = _family(document["material_family"])
        scope_id = _text(document["scope_id"])
        if scope_id not in _SCOPES[family]:
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        batch_id = _text(document["batch_id"])
        if _BATCH_ID.fullmatch(batch_id) is None:
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        cutoff = _text(document["observation_cutoff"])
        if _UTC.fullmatch(cutoff) is None:
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        manifest_fingerprint = _fingerprint(document["acquisition_manifest_fingerprint"])
        journal_head = _fingerprint(document["journal_head_fingerprint"])
        profile_fingerprint = _fingerprint(document["semantic_profile_fingerprint"])
        capability_ref = _text(document["capability_evidence_ref"])
        if not _valid_ref(capability_ref):
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        evidence_set_fingerprint, facts = _prepared_evidence(document["evidence_items"])
        if _fingerprint(document["evidence_set_fingerprint"]) != evidence_set_fingerprint:
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        _prepared_requests(document["model_requests"], facts, profile_fingerprint)
        if document["provider_invocation_count"] != 0 or document["release_state"] != (
            "WITHHELD_PENDING_TWO_FAMILY_RECONCILIATION"
        ):
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        expected_ref = prepared_batch_logical_ref(
            family,
            scope_id,
            batch_id,
            evidence_set_fingerprint,
            profile_fingerprint,
        )
        if receipt.logical_ref != expected_ref:
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        return PreparedBatchArtifact(
            material_family=family,
            scope_id=scope_id,
            batch_id=batch_id,
            observation_cutoff=cutoff,
            acquisition_manifest_fingerprint=manifest_fingerprint,
            journal_head_fingerprint=journal_head,
            evidence_set_fingerprint=evidence_set_fingerprint,
            evidence_refs=tuple(item[0] for item in facts),
            semantic_profile_fingerprint=profile_fingerprint,
            capability_evidence_ref=capability_ref,
            fingerprint=embedded_fingerprint,
            receipt=ExactProposalArtifactReceipt(receipt.logical_ref, receipt.fingerprint),
        )
    except (ContractViolation, KeyError, TypeError, ValueError) as error:
        if isinstance(error, ProposalEvidenceError):
            raise
        code = "PREPARED_BATCH_ARTIFACT_INVALID"
        raise ProposalEvidenceError(code) from error


def _prepared_evidence(
    value: JsonValue,
) -> tuple[str, tuple[tuple[str, str, str], ...]]:
    if type(value) is not list or not value:
        _fail("PREPARED_BATCH_ARTIFACT_INVALID")
    facts: list[tuple[str, str, str]] = []
    fingerprint_facts: list[dict[str, JsonValue]] = []
    for item in value:
        if type(item) is not dict or frozenset(item) != _EVIDENCE_FIELDS:
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        evidence_ref = _text(item["evidence_ref"])
        evidence_fingerprint = _fingerprint(item["fingerprint"])
        language = _text(item["language"])
        subject_id = _text(item["subject_id"])
        _fingerprint(item["text_fingerprint"])
        if not _valid_ref(evidence_ref) or language not in {"en", "zh-Hant"}:
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        facts.append((evidence_ref, evidence_fingerprint, subject_id))
        fingerprint_facts.append(
            {"evidence_ref": evidence_ref, "fingerprint": evidence_fingerprint}
        )
    references = tuple(item[0] for item in facts)
    if len(set(references)) != len(references):
        _fail("PREPARED_BATCH_ARTIFACT_INVALID")
    fingerprint = _bytes_fingerprint(canonicalize(checked_json_value(fingerprint_facts)))
    return fingerprint, tuple(facts)


def _prepared_requests(
    value: JsonValue,
    evidence_facts: tuple[tuple[str, str, str], ...],
    profile_fingerprint: str,
) -> None:
    if type(value) is not list or len(value) != len(evidence_facts):
        _fail("PREPARED_BATCH_ARTIFACT_INVALID")
    for item, (evidence_ref, evidence_fingerprint, subject_id) in zip(
        value, evidence_facts, strict=True
    ):
        if type(item) is not dict or frozenset(item) != _REQUEST_FIELDS:
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")
        facts: dict[str, JsonValue] = {
            "evidence_fingerprint": evidence_fingerprint,
            "evidence_ref": evidence_ref,
            "semantic_profile_fingerprint": profile_fingerprint,
            "subject_id": subject_id,
        }
        if any(item[name] != fact for name, fact in facts.items()) or item["request_id"] != (
            f"request-{sha256(canonicalize(facts)).hexdigest()}"
        ):
            _fail("PREPARED_BATCH_ARTIFACT_INVALID")


def _family(value: JsonValue) -> Literal["CASES", "LEGISLATION"]:
    text = _text(value)
    if text == "CASES":
        return "CASES"
    if text == "LEGISLATION":
        return "LEGISLATION"
    return _fail("PREPARED_BATCH_ARTIFACT_INVALID")


def _text(value: JsonValue) -> str:
    if type(value) is not str or not value or value != value.strip():
        _fail("PREPARED_BATCH_ARTIFACT_INVALID")
    return value


def _fingerprint(value: JsonValue) -> str:
    result = _text(value)
    if _FINGERPRINT.fullmatch(result) is None:
        _fail("PREPARED_BATCH_ARTIFACT_INVALID")
    return result


def _valid_ref(value: object) -> bool:
    return type(value) is str and _REFERENCE.fullmatch(value) is not None and "//" not in value


def _valid_fingerprint(value: object) -> bool:
    return type(value) is str and _FINGERPRINT.fullmatch(value) is not None


def _capability(value: object) -> Literal["MODEL", "EMBEDDING"]:
    if value == "MODEL" and type(value) is str:
        return "MODEL"
    if value == "EMBEDDING" and type(value) is str:
        return "EMBEDDING"
    return _fail("SEMANTIC_CAPABILITY_EVIDENCE_INVALID")


def _self_fingerprinted_document(
    content: bytes,
    fields: frozenset[str],
    schema_id: str,
    code: str,
) -> tuple[dict[str, JsonValue], str]:
    if type(content) is not bytes or not content:
        _fail(code)
    document = parse_json_bytes(content, max_bytes=131_072)
    if (
        type(document) is not dict
        or frozenset(document) != fields
        or document["schema_id"] != schema_id
        or canonicalize(document) != content
    ):
        _fail(code)
    fingerprint = _fingerprint(document["fingerprint"])
    unsigned = {name: item for name, item in document.items() if name != "fingerprint"}
    if fingerprint != _bytes_fingerprint(canonicalize(unsigned)):
        _fail(code)
    return document, fingerprint


def _parse_profile_receipt(
    logical_ref: str,
    content: bytes,
    expected_capability: Literal["MODEL", "EMBEDDING"],
) -> tuple[str, str]:
    document, fingerprint = _self_fingerprinted_document(
        content,
        _PROFILE_FIELDS,
        "asklegal.hk-v1-provider-disabled-profile-receipt/v1",
        "SEMANTIC_PROFILE_RECEIPT_INVALID",
    )
    profile_fingerprint = _fingerprint(document["profile_fingerprint"])
    if (
        document["capability"] != expected_capability
        or document["issuer_application"] != _CAPABILITY_IDENTITIES[expected_capability][0]
        or document["status"] != _DISABLED_STATUS
        or logical_ref
        != provider_disabled_profile_receipt_ref(expected_capability, profile_fingerprint)
    ):
        _fail("SEMANTIC_PROFILE_RECEIPT_INVALID")
    return profile_fingerprint, fingerprint


def _parse_capability_evidence(  # noqa: PLR0913, PLR0917 - exact cross-document binding.
    logical_ref: str,
    content: bytes,
    expected_capability: Literal["MODEL", "EMBEDDING"],
    expected_cutoff: str,
    profile_receipt_ref: str,
    profile_receipt_fingerprint: str,
    profile_fingerprint: str,
) -> str:
    document, fingerprint = _self_fingerprinted_document(
        content,
        _CAPABILITY_FIELDS,
        "asklegal.hk-v1-provider-disabled-capability-evidence/v1",
        "SEMANTIC_CAPABILITY_EVIDENCE_INVALID",
    )
    expected_application, expected_role = _CAPABILITY_IDENTITIES[expected_capability]
    expected_ref = (
        f"proposal-readiness/capability-evidence/{expected_capability.lower()}/"
        f"{fingerprint.removeprefix('sha256:')}.json"
    )
    if (
        document["capability"] != expected_capability
        or document["application"] != expected_application
        or document["role"] != expected_role
        or document["observation_cutoff"] != expected_cutoff
        or type(expected_cutoff) is not str
        or _UTC.fullmatch(expected_cutoff) is None
        or document["profile_receipt_ref"] != profile_receipt_ref
        or document["profile_receipt_fingerprint"] != profile_receipt_fingerprint
        or document["profile_fingerprint"] != profile_fingerprint
        or document["status"] != _DISABLED_STATUS
        or logical_ref != expected_ref
    ):
        _fail("SEMANTIC_CAPABILITY_EVIDENCE_INVALID")
    return fingerprint


def _semantic_snapshot(value: VerifiedSemanticCapability) -> tuple[str, ...]:
    return (
        value.capability,
        value.profile_fingerprint,
        value.profile_receipt_ref,
        value.profile_receipt_fingerprint,
        value.evidence_ref,
        value.evidence_fingerprint,
        value.status,
    )


def _bytes_fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"


def _fail(code: str) -> Never:
    raise ProposalEvidenceError(code)
