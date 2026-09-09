"""Source-neutral HKEX evidence-bundle hostile tests."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import replace

import pytest
from asklegal_evidence_vault import VaultName
from asklegal_legal_desks.hk_regulatory_authentic import (
    ExactObjectReference,
    HKEXSourceCycleManifest,
    HKEXSourceNeutralEvidenceBundle,
    HKEXSourceNeutralEvidenceError,
    HKEXSourceNeutralEvidenceMember,
    canonical_manifest_fingerprint,
    load_hkex_source_neutral_bundle,
)
from asklegal_legal_desks.hk_regulatory_inventory import HKEX_REGULATORY_SOURCE_IDS


class _Reader:
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        return self.values[reference.logical_key]


def _manifest() -> tuple[HKEXSourceCycleManifest, _Reader]:
    members: list[HKEXSourceNeutralEvidenceMember] = []
    values: dict[str, bytes] = {}
    for role in HKEX_REGULATORY_SOURCE_IDS:
        for board in ("GEM", "MAIN"):
            for language in ("EN", "ZH"):
                member_id = f"{role}-{board}-{language}"
                raw = member_id.encode()
                key = f"hkex/{member_id.lower()}"
                values[key] = raw
                ref = ExactObjectReference(
                    VaultName.PRIMARY,
                    key,
                    "v" + hashlib.sha256(key.encode()).hexdigest(),
                    "sha256:" + hashlib.sha256(raw).hexdigest(),
                    len(raw),
                )
                members.append(
                    HKEXSourceNeutralEvidenceMember(
                        member_id, role, board, language, "application/pdf", ref
                    )
                )
    exact = tuple(members)
    cutoff = "2026-08-26"
    return HKEXSourceCycleManifest(
        cutoff, exact, canonical_manifest_fingerprint(cutoff, exact)
    ), _Reader(values)


def _reseal(
    manifest: HKEXSourceCycleManifest, members: tuple[HKEXSourceNeutralEvidenceMember, ...]
) -> HKEXSourceCycleManifest:
    return HKEXSourceCycleManifest(
        manifest.observation_cutoff,
        members,
        canonical_manifest_fingerprint(manifest.observation_cutoff, members),
    )


def test_exact_five_roles_both_boards_english_required_chinese_optional() -> None:
    manifest, reader = _manifest()
    bundle = load_hkex_source_neutral_bundle(manifest, reader)
    assert len(bundle.members_for_board("MAIN")) == 10
    missing = tuple(
        member
        for member in manifest.members
        if not (
            member.role == HKEX_REGULATORY_SOURCE_IDS[0]
            and member.board == "GEM"
            and member.language == "EN"
        )
    )
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="ENGLISH_MISSING"):
        load_hkex_source_neutral_bundle(_reseal(manifest, missing), reader)
    absent = tuple(
        member
        for member in manifest.members
        if not (member.role == HKEX_REGULATORY_SOURCE_IDS[0] and member.board == "GEM")
    )
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="ROLE_BOARD_MISSING"):
        load_hkex_source_neutral_bundle(_reseal(manifest, absent), reader)


def test_multiple_members_per_role_are_read_and_board_isolation_is_exact() -> None:
    manifest, reader = _manifest()
    original = manifest.members[0]
    member_id = f"{original.role}-{original.board}-EN-SUPPORT"
    raw = member_id.encode()
    key = f"hkex/{member_id.lower()}"
    reader.values[key] = raw
    support = HKEXSourceNeutralEvidenceMember(
        member_id,
        original.role,
        original.board,
        "EN",
        "application/xml",
        ExactObjectReference(
            VaultName.RECOVERY,
            key,
            "v" + hashlib.sha256(key.encode()).hexdigest(),
            "sha256:" + hashlib.sha256(raw).hexdigest(),
            len(raw),
        ),
    )
    bundle = load_hkex_source_neutral_bundle(
        _reseal(manifest, (*manifest.members, support)), reader
    )
    assert len(bundle.members_for_board(original.board)) == 11
    assert len(bundle.members_for_board("MAIN")) == 10


def test_invalid_later_member_prevents_all_reads_and_references_are_exact() -> None:
    manifest, reader = _manifest()
    calls = 0

    class CountingReader(_Reader):
        def read_exact(self, reference: ExactObjectReference) -> bytes:
            nonlocal calls
            calls += 1
            return super().read_exact(reference)

    object.__setattr__(manifest, "members", (*manifest.members[:-1], object()))
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="MEMBER_INVALID"):
        load_hkex_source_neutral_bundle(manifest, CountingReader(reader.values))
    assert calls == 0

    exact, _ = _manifest()
    with pytest.raises(ValueError, match="unsafe segment"):
        replace(exact.members[-1].reference, logical_key="hkex/./alias")


def test_duplicate_reference_content_bad_bytes_and_reader_error_close() -> None:
    manifest, reader = _manifest()
    duplicate = (*manifest.members, replace(manifest.members[0], member_id="DUPLICATE"))
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="REFERENCE_DUPLICATE"):
        load_hkex_source_neutral_bundle(_reseal(manifest, duplicate), reader)

    manifest, reader = _manifest()
    first, second = manifest.members[:2]
    shared = reader.values[first.reference.logical_key]
    reader.values[second.reference.logical_key] = shared
    content_duplicate = replace(
        second,
        reference=replace(
            second.reference,
            fingerprint=first.reference.fingerprint,
            byte_length=first.reference.byte_length,
        ),
    )
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="CONTENT_DUPLICATE"):
        load_hkex_source_neutral_bundle(
            _reseal(manifest, (first, content_duplicate, *manifest.members[2:])), reader
        )

    manifest, reader = _manifest()
    reader.values[manifest.members[0].reference.logical_key] = b"mutated"
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="BYTES_INVALID"):
        load_hkex_source_neutral_bundle(manifest, reader)
    manifest, reader = _manifest()
    reader.values.pop(manifest.members[0].reference.logical_key)
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="READ_FAILED"):
        load_hkex_source_neutral_bundle(manifest, reader)


@pytest.mark.parametrize(
    ("field", "value"),
    [("fingerprint", "sha256:" + "0" * 64), ("byte_length", 999)],
)
def test_reference_fingerprint_and_length_are_verified(field: str, value: str | int) -> None:
    manifest, reader = _manifest()
    changed_ref = replace(manifest.members[0].reference, **{field: value})
    changed = replace(manifest.members[0], reference=changed_ref)
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="BYTES_INVALID"):
        load_hkex_source_neutral_bundle(_reseal(manifest, (changed, *manifest.members[1:])), reader)


def test_reader_ordinary_errors_and_non_exact_bytes_close_but_baseexception_survives() -> None:
    manifest, _ = _manifest()

    class ErrorReader:
        def read_exact(self, reference: ExactObjectReference) -> bytes:
            raise RuntimeError(reference.logical_key)

    class BytesSubclass(bytes):
        pass

    class SubclassReader:
        def read_exact(self, reference: ExactObjectReference) -> bytes:
            return BytesSubclass(reference.logical_key.encode())

    class FatalReader:
        def read_exact(self, reference: ExactObjectReference) -> bytes:
            raise KeyboardInterrupt(reference.logical_key)

    with pytest.raises(HKEXSourceNeutralEvidenceError, match="READ_FAILED"):
        load_hkex_source_neutral_bundle(manifest, ErrorReader())
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="READ_FAILED"):
        load_hkex_source_neutral_bundle(manifest, SubclassReader())
    with pytest.raises(KeyboardInterrupt):
        load_hkex_source_neutral_bundle(manifest, FatalReader())


def test_manifest_date_fingerprint_exact_types_and_equality_liar_reject() -> None:
    manifest, reader = _manifest()
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="CUTOFF_INVALID"):
        load_hkex_source_neutral_bundle(replace(manifest, observation_cutoff="2026-02-31"), reader)
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="MANIFEST_FINGERPRINT_INVALID"):
        load_hkex_source_neutral_bundle(replace(manifest, fingerprint="sha256:" + "0" * 64), reader)

    class EqualityLiar(str):
        __slots__ = ()
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            return True

    with pytest.raises(HKEXSourceNeutralEvidenceError, match="MEMBER_INVALID"):
        replace(manifest.members[0], role=EqualityLiar(manifest.members[0].role))
    with pytest.raises(TypeError, match="vault must be an exact VaultName"):
        replace(manifest.members[0].reference, vault=EqualityLiar("PRIMARY"))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("role", "UNKNOWN_ROLE"),
        ("board", "UNKNOWN_BOARD"),
        ("language", "FR"),
        ("media_type", "text/html"),
    ],
)
def test_unknown_member_metadata_rejects_before_reader(field: str, value: str) -> None:
    """Closed member vocabularies reject at value construction."""
    manifest, _ = _manifest()
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="MEMBER_INVALID"):
        replace(manifest.members[-1], **{field: value})


def test_reader_and_caller_mutation_cannot_reseal_snapshot() -> None:
    """Reader receives a disposable ref and caller mutation cannot alter output."""
    manifest, reader = _manifest()
    original_role = manifest.members[0].role

    class MutatingReader(_Reader):
        def read_exact(self, reference: ExactObjectReference) -> bytes:
            original_key = reference.logical_key
            object.__setattr__(reference, "fingerprint", "sha256:" + "0" * 64)
            object.__setattr__(manifest, "observation_cutoff", "tomorrow")
            object.__setattr__(manifest.members[0], "role", "UNKNOWN_ROLE")
            object.__setattr__(manifest.members[0].reference, "logical_key", "hkex/mutated")
            return self.values[original_key]

    bundle = load_hkex_source_neutral_bundle(manifest, MutatingReader(reader.values))
    assert bundle.observation_cutoff == "2026-08-26"
    assert bundle.bundle_fingerprint == canonical_manifest_fingerprint(
        bundle.observation_cutoff, bundle.members
    )
    assert bundle.members[0].role == original_role
    assert bundle.members[0].reference.logical_key != "hkex/mutated"


def test_reader_cannot_reseal_disposable_reference_for_different_bytes() -> None:
    """Post-validation reader mutation cannot redefine fingerprint or length authority."""
    manifest, _ = _manifest()
    malicious = b"reader-resealed-content"

    class ResealingReader:
        def read_exact(self, reference: ExactObjectReference) -> bytes:
            object.__setattr__(
                reference, "fingerprint", "sha256:" + hashlib.sha256(malicious).hexdigest()
            )
            object.__setattr__(reference, "byte_length", len(malicious))
            return malicious

    with pytest.raises(HKEXSourceNeutralEvidenceError, match="BYTES_INVALID"):
        load_hkex_source_neutral_bundle(manifest, ResealingReader())


def test_output_revalidates_cutoff_members_references_and_board_exact_type() -> None:
    """Direct/replaced output construction cannot reseal incoherent values."""
    manifest, reader = _manifest()
    bundle = load_hkex_source_neutral_bundle(manifest, reader)

    with pytest.raises(TypeError):
        type.__call__(
            HKEXSourceNeutralEvidenceBundle,
            "tomorrow",
            bundle.members,
            canonical_manifest_fingerprint("tomorrow", bundle.members),
        )

    member = bundle.members[0]
    object.__setattr__(member, "board", "UNKNOWN_BOARD")
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="MANIFEST_INVALID"):
        bundle.members_for_board("MAIN")

    manifest, reader = _manifest()
    ref = manifest.members[0].reference
    object.__setattr__(ref, "logical_key", "hkex/./alias")
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="MEMBER_INVALID"):
        replace(manifest.members[0], reference=ref)

    class EqualityLiar(str):
        __slots__ = ()
        __hash__ = str.__hash__

        def __eq__(self, other: object) -> bool:
            return True

    manifest, reader = _manifest()
    bundle = load_hkex_source_neutral_bundle(manifest, reader)
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="BOARD_INVALID"):
        bundle.members_for_board(EqualityLiar("MAIN"))


def test_validated_bundle_construction_and_replace_are_proof_owned() -> None:
    """Public data-only construction cannot claim that reader verification occurred."""
    manifest, reader = _manifest()
    with pytest.raises(TypeError):
        HKEXSourceNeutralEvidenceBundle()
    with pytest.raises(TypeError):
        type.__call__(
            HKEXSourceNeutralEvidenceBundle,
            manifest.observation_cutoff,
            manifest.members,
            canonical_manifest_fingerprint(manifest.observation_cutoff, manifest.members),
        )

    bundle = load_hkex_source_neutral_bundle(manifest, reader)
    with pytest.raises(TypeError):
        replace(bundle)

    forged = object.__new__(HKEXSourceNeutralEvidenceBundle)
    object.__setattr__(forged, "observation_cutoff", manifest.observation_cutoff)
    object.__setattr__(forged, "members", manifest.members)
    object.__setattr__(
        forged,
        "bundle_fingerprint",
        canonical_manifest_fingerprint(manifest.observation_cutoff, manifest.members),
    )
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="MANIFEST_INVALID"):
        forged.members_for_board("MAIN")


def test_copied_private_proof_identity_is_not_issued() -> None:
    """Proof field equality cannot substitute for one post-read issued identity."""
    manifest, reader = _manifest()
    bundle = load_hkex_source_neutral_bundle(manifest, reader)
    issued = object.__getattribute__(bundle, "_proof")
    copied = copy.copy(issued)
    deep_copied = copy.deepcopy(issued)

    for proof in (copied, deep_copied):
        forged = object.__new__(HKEXSourceNeutralEvidenceBundle)
        object.__setattr__(forged, "observation_cutoff", bundle.observation_cutoff)
        object.__setattr__(forged, "members", bundle.members)
        object.__setattr__(forged, "bundle_fingerprint", bundle.bundle_fingerprint)
        object.__setattr__(forged, "_proof", proof)
        with pytest.raises(HKEXSourceNeutralEvidenceError, match="MANIFEST_INVALID"):
            forged.members_for_board("MAIN")

    copied_bundle = copy.copy(bundle)
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="MANIFEST_INVALID"):
        copied_bundle.members_for_board("MAIN")


def _install_unread_successor(bundle: HKEXSourceNeutralEvidenceBundle) -> str:
    original = bundle.members[0]
    raw = b"unread-successor"
    key = "hkex/unread-successor"
    successor = replace(
        original,
        reference=ExactObjectReference(
            VaultName.PRIMARY,
            key,
            "v" + hashlib.sha256(key.encode()).hexdigest(),
            "sha256:" + hashlib.sha256(raw).hexdigest(),
            len(raw),
        ),
    )
    object.__setattr__(bundle, "members", (successor, *bundle.members[1:]))
    fingerprint = canonical_manifest_fingerprint(bundle.observation_cutoff, bundle.members)
    object.__setattr__(bundle, "bundle_fingerprint", fingerprint)
    return fingerprint


def test_replacement_proof_cannot_authorize_unread_successor_reference() -> None:
    """An equal-shaped new proof is not authority for a post-read successor."""
    manifest, reader = _manifest()
    bundle = load_hkex_source_neutral_bundle(manifest, reader)
    fingerprint = _install_unread_successor(bundle)
    replacement_proof = copy.copy(object.__getattribute__(bundle, "_proof"))
    object.__setattr__(replacement_proof, "fingerprint", fingerprint)
    object.__setattr__(bundle, "_proof", replacement_proof)
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="MANIFEST_INVALID"):
        bundle.members_for_board("MAIN")


def test_mutated_issued_proof_cannot_authorize_unread_successor_reference() -> None:
    """The registry retains original authority independently of a mutable proof."""
    manifest, reader = _manifest()
    bundle = load_hkex_source_neutral_bundle(manifest, reader)
    fingerprint = _install_unread_successor(bundle)
    proof = object.__getattribute__(bundle, "_proof")
    object.__setattr__(proof, "fingerprint", fingerprint)
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="MANIFEST_INVALID"):
        bundle.members_for_board("MAIN")


def test_board_projection_rejects_resealed_global_member_id_duplicate() -> None:
    """Output coherence uses the loader's global member-id uniqueness rule."""
    manifest, reader = _manifest()
    bundle = load_hkex_source_neutral_bundle(manifest, reader)
    object.__setattr__(bundle.members[-1], "member_id", bundle.members[0].member_id)
    object.__setattr__(
        bundle,
        "bundle_fingerprint",
        canonical_manifest_fingerprint(bundle.observation_cutoff, bundle.members),
    )
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="MEMBER_DUPLICATE"):
        bundle.members_for_board("MAIN")


def test_board_projection_rejects_post_return_member_mutation() -> None:
    """A nested mutation cannot alter a projection under a stale fingerprint."""
    manifest, reader = _manifest()
    bundle = load_hkex_source_neutral_bundle(manifest, reader)
    object.__setattr__(bundle.members[0], "board", "MAIN")
    with pytest.raises(HKEXSourceNeutralEvidenceError, match="MANIFEST_INVALID"):
        bundle.members_for_board("MAIN")
