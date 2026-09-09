"""Source-neutral, injected-reader HKEX evidence validation; no source access."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Protocol
from weakref import ReferenceType, ref

from asklegal_evidence_vault import ExactObjectReference, VaultName

from .hk_regulatory_inventory import HKEX_REGULATORY_SOURCE_IDS

_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_IDENTIFIER = re.compile(r"[A-Z0-9][A-Z0-9_-]{2,199}\Z")
_BOARDS = ("GEM", "MAIN")
_LANGUAGES = ("EN", "ZH")
_MEDIA_TYPES = ("application/pdf", "application/xml", "text/xml")
_BOARD_INVALID = "BOARD_INVALID"
_MANIFEST_INVALID = "MANIFEST_INVALID"
_CUTOFF_INVALID = "CUTOFF_INVALID"
_MANIFEST_FP_INVALID = "MANIFEST_FINGERPRINT_INVALID"
_MEMBER_INVALID = "MEMBER_INVALID"
_MEMBER_DUPLICATE = "MEMBER_DUPLICATE"
_ROLE_BOARD_MISSING = "ROLE_BOARD_MISSING"
_ENGLISH_MISSING = "ENGLISH_MISSING"
_REFERENCE_DUPLICATE = "REFERENCE_DUPLICATE"
_READ_FAILED = "READ_FAILED"
_BYTES_INVALID = "BYTES_INVALID"
_CONTENT_DUPLICATE = "CONTENT_DUPLICATE"
_BUNDLE_FACTORY_ONLY = "validated HKEX bundles are factory-owned"


class HKEXSourceNeutralEvidenceError(ValueError):
    """Closed source-neutral evidence rejection."""


def _error(code: str) -> HKEXSourceNeutralEvidenceError:
    return HKEXSourceNeutralEvidenceError(code)


@dataclass(frozen=True, slots=True)
class HKEXSourceNeutralEvidenceMember:
    """One manifest-declared artifact member."""

    member_id: str
    role: str
    board: str
    language: str
    media_type: str
    reference: ExactObjectReference

    def __post_init__(self) -> None:
        """Reject incoherent direct or replaced members."""
        if not _valid_member(self):
            raise _error(_MEMBER_INVALID)


@dataclass(frozen=True, slots=True)
class HKEXSourceCycleManifest:
    """Frozen source-cycle member authority."""

    observation_cutoff: str
    members: tuple[HKEXSourceNeutralEvidenceMember, ...]
    fingerprint: str


class HKEXEvidenceReader(Protocol):
    """Reads one exact immutable object."""

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        """Return exact referenced bytes."""
        ...


@dataclass(frozen=True, slots=True, weakref_slot=True)
class _ValidatedBundleProof:
    """Internal proof bound to one reader-verified bundle fingerprint."""

    fingerprint: str


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True)
class HKEXSourceNeutralEvidenceBundle:
    """Validated source-neutral bytes with no authenticity conclusion."""

    observation_cutoff: str
    members: tuple[HKEXSourceNeutralEvidenceMember, ...]
    bundle_fingerprint: str
    _proof: _ValidatedBundleProof

    def __init__(self) -> None:
        """Reject public construction; only the verified factory may create output."""
        raise TypeError(_BUNDLE_FACTORY_ONLY)

    def __post_init__(self) -> None:
        """Reject direct or replaced incoherent outputs."""
        try:
            cutoff = self.observation_cutoff
            members = self.members
            fingerprint = self.bundle_fingerprint
            proof = self._proof
        except AttributeError as error:
            raise _error(_MANIFEST_INVALID) from error
        if (
            not _valid_cutoff(cutoff)
            or type(members) is not tuple
            or any(not _valid_member(member) for member in members)
            or type(fingerprint) is not str
            or _SHA.fullmatch(fingerprint) is None
        ):
            raise _error(_MANIFEST_INVALID)
        canonical_bytes = _canonical_manifest_bytes(cutoff, members)
        if fingerprint != "sha256:" + hashlib.sha256(canonical_bytes).hexdigest():
            raise _error(_MANIFEST_INVALID)
        _validate_members(members)
        if not _valid_bundle_proof(self, proof, fingerprint, canonical_bytes):
            raise _error(_MANIFEST_INVALID)

    def members_for_board(self, board: str) -> tuple[HKEXSourceNeutralEvidenceMember, ...]:
        """Return one isolated board view."""
        if type(board) is not str or board not in _BOARDS:
            raise _error(_BOARD_INVALID)
        self.__post_init__()
        return tuple(member for member in self.members if member.board == board)


def _projection(member: HKEXSourceNeutralEvidenceMember) -> dict[str, object]:
    ref = member.reference
    return {
        "member_id": member.member_id,
        "role": member.role,
        "board": member.board,
        "language": member.language,
        "media_type": member.media_type,
        "reference": {
            "vault": ref.vault,
            "logical_key": ref.logical_key,
            "version_id": ref.version_id,
            "fingerprint": ref.fingerprint,
            "byte_length": ref.byte_length,
        },
    }


def _canonical_manifest_bytes(
    cutoff: str, members: tuple[HKEXSourceNeutralEvidenceMember, ...]
) -> bytes:
    return json.dumps(
        {"observation_cutoff": cutoff, "members": [_projection(member) for member in members]},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def canonical_manifest_fingerprint(
    cutoff: str, members: tuple[HKEXSourceNeutralEvidenceMember, ...]
) -> str:
    """Fingerprint exact primitive manifest authority."""
    raw = _canonical_manifest_bytes(cutoff, members)
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _valid_cutoff(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _copy_reference(reference: object) -> ExactObjectReference:
    if type(reference) is not ExactObjectReference:
        raise _error(_MEMBER_INVALID)
    try:
        vault = reference.vault
        logical_key = reference.logical_key
        version_id = reference.version_id
        fingerprint = reference.fingerprint
        byte_length = reference.byte_length
        copied = ExactObjectReference(vault, logical_key, version_id, fingerprint, byte_length)
    except Exception as error:
        raise _error(_MEMBER_INVALID) from error
    if type(vault) is not VaultName or type(byte_length) is not int or byte_length <= 0:
        raise _error(_MEMBER_INVALID)
    return copied


def _valid_reference(reference: object) -> bool:
    try:
        _copy_reference(reference)
    except HKEXSourceNeutralEvidenceError:
        return False
    return True


def _valid_member(member: object) -> bool:
    if type(member) is not HKEXSourceNeutralEvidenceMember:
        return False
    try:
        values = (member.member_id, member.role, member.board, member.language, member.media_type)
        reference = member.reference
    except AttributeError, RuntimeError, TypeError, ValueError:
        return False
    return (
        all(type(value) is str and bool(value) for value in values)
        and _IDENTIFIER.fullmatch(values[0]) is not None
        and values[1] in HKEX_REGULATORY_SOURCE_IDS
        and values[2] in _BOARDS
        and values[3] in _LANGUAGES
        and values[4] in _MEDIA_TYPES
        and _valid_reference(reference)
    )


def _copy_member(member: object) -> HKEXSourceNeutralEvidenceMember:
    if type(member) is not HKEXSourceNeutralEvidenceMember:
        raise _error(_MEMBER_INVALID)
    try:
        member_id = member.member_id
        role = member.role
        board = member.board
        language = member.language
        media_type = member.media_type
        reference = member.reference
    except Exception as error:
        raise _error(_MEMBER_INVALID) from error
    copied_reference = _copy_reference(reference)
    try:
        return HKEXSourceNeutralEvidenceMember(
            member_id, role, board, language, media_type, copied_reference
        )
    except Exception as error:
        raise _error(_MEMBER_INVALID) from error


def _snapshot(
    manifest: HKEXSourceCycleManifest,
) -> tuple[str, tuple[HKEXSourceNeutralEvidenceMember, ...]]:
    if type(manifest) is not HKEXSourceCycleManifest:
        raise _error(_MANIFEST_INVALID)
    try:
        cutoff = manifest.observation_cutoff
        declared_members = manifest.members
        declared_fingerprint = manifest.fingerprint
    except Exception as error:
        raise _error(_MANIFEST_INVALID) from error
    if type(declared_members) is not tuple or type(declared_fingerprint) is not str:
        raise _error(_MANIFEST_INVALID)
    if not _valid_cutoff(cutoff):
        raise _error(_CUTOFF_INVALID)
    result = tuple(_copy_member(member) for member in declared_members)
    if declared_fingerprint != canonical_manifest_fingerprint(cutoff, result):
        raise _error(_MANIFEST_FP_INVALID)
    member_ids: set[str] = set()
    for member in result:
        if member.member_id in member_ids:
            raise _error(_MEMBER_INVALID)
        member_ids.add(member.member_id)
    return cutoff, result


def _validate_members(members: tuple[HKEXSourceNeutralEvidenceMember, ...]) -> None:
    member_ids = [member.member_id for member in members]
    if len(set(member_ids)) != len(member_ids):
        raise _error(_MEMBER_DUPLICATE)
    identities = {(member.role, member.board, member.member_id) for member in members}
    if len(identities) != len(members):
        raise _error(_MEMBER_DUPLICATE)
    for role in HKEX_REGULATORY_SOURCE_IDS:
        for board in _BOARDS:
            applicable = [
                member for member in members if member.role == role and member.board == board
            ]
            if not applicable:
                raise _error(_ROLE_BOARD_MISSING)
            if not any(member.language == "EN" for member in applicable):
                raise _error(_ENGLISH_MISSING)
    references = [
        (m.reference.vault, m.reference.logical_key, m.reference.version_id) for m in members
    ]
    if len(set(references)) != len(references):
        raise _error(_REFERENCE_DUPLICATE)


def _read_members(
    members: tuple[HKEXSourceNeutralEvidenceMember, ...], reader: HKEXEvidenceReader
) -> None:
    contents: set[str] = set()
    for member in members:
        authority_ref = member.reference
        reader_ref = ExactObjectReference(
            authority_ref.vault,
            authority_ref.logical_key,
            authority_ref.version_id,
            authority_ref.fingerprint,
            authority_ref.byte_length,
        )
        try:
            raw = reader.read_exact(reader_ref)
        except Exception as error:
            raise _error(_READ_FAILED) from error
        if type(raw) is not bytes:
            raise _error(_READ_FAILED)
        copied = bytes(memoryview(raw))
        digest = "sha256:" + hashlib.sha256(copied).hexdigest()
        if (
            not copied
            or len(copied) != authority_ref.byte_length
            or digest != authority_ref.fingerprint
        ):
            raise _error(_BYTES_INVALID)
        if digest in contents:
            raise _error(_CONTENT_DUPLICATE)
        contents.add(digest)


def _loader_authority() -> tuple[
    Callable[[HKEXSourceCycleManifest, HKEXEvidenceReader], HKEXSourceNeutralEvidenceBundle],
    Callable[[object, object, str, bytes], bool],
]:
    issued: dict[
        int,
        tuple[
            ReferenceType[HKEXSourceNeutralEvidenceBundle],
            ReferenceType[_ValidatedBundleProof],
            str,
            bytes,
        ],
    ] = {}

    def proof_is_valid(
        bundle: object, proof: object, fingerprint: str, canonical_bytes: bytes
    ) -> bool:
        if type(proof) is not _ValidatedBundleProof:
            return False
        authority = issued.get(id(bundle))
        if authority is None:
            return False
        bundle_reference, proof_reference, original_fingerprint, original_bytes = authority
        return (
            bundle_reference() is bundle
            and proof_reference() is proof
            and type(proof.fingerprint) is str
            and proof.fingerprint == original_fingerprint
            and fingerprint == original_fingerprint
            and canonical_bytes == original_bytes
        )

    def load(
        manifest: HKEXSourceCycleManifest, reader: HKEXEvidenceReader
    ) -> HKEXSourceNeutralEvidenceBundle:
        cutoff, members = _snapshot(manifest)
        _validate_members(members)
        _read_members(members, reader)
        canonical_bytes = _canonical_manifest_bytes(cutoff, members)
        fingerprint = "sha256:" + hashlib.sha256(canonical_bytes).hexdigest()
        proof = _ValidatedBundleProof(fingerprint)
        bundle = object.__new__(HKEXSourceNeutralEvidenceBundle)
        object.__setattr__(bundle, "observation_cutoff", cutoff)
        object.__setattr__(bundle, "members", members)
        object.__setattr__(bundle, "bundle_fingerprint", fingerprint)
        object.__setattr__(bundle, "_proof", proof)
        identity = id(bundle)

        def forget(
            reference: ReferenceType[HKEXSourceNeutralEvidenceBundle], identity: int = identity
        ) -> None:
            authority = issued.get(identity)
            if authority is not None and authority[0] is reference:
                issued.pop(identity, None)

        issued[identity] = (ref(bundle, forget), ref(proof), fingerprint, canonical_bytes)
        bundle.__post_init__()
        return bundle

    return load, proof_is_valid


load_hkex_source_neutral_bundle, _valid_bundle_proof = _loader_authority()
del _loader_authority
