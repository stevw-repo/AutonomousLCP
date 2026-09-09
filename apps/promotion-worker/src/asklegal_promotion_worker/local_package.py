"""Typed Promotion Manifest recovery from one exact executable Review package."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Never, Protocol

from asklegal_contracts import (
    ProposalMemberBindings,
    canonicalize,
    parse_json_bytes,
    validate_v1_proposal_members,
)
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_corpus import (
    CoverageScopeStatus,
    CoverageState,
    CoverageStatusManifest,
    CoverageWarning,
    DesiredStateInventory,
    FlattenedRecord,
    ServingRecord,
    freeze_coverage_status,
    serving_payload_fingerprint,
    source_coverage_cycle_binding_from_json,
)
from asklegal_promotion import (
    PromotionManifest,
    PromotionPlan,
    ServingCapabilityProfile,
    freeze_v1_promotion_manifest,
    promotion_approval_snapshot_from_bytes,
)

_PACKAGE = "hk-v1-review-package.json"
_ERROR = "LOCAL_PROMOTION_PACKAGE_INVALID"
_PAIR_SIZE = 2
_EXPECTED_ROLES = {
    "CHANGE_INVENTORY",
    "CORPUS_RELEASES",
    "COST_AND_CAPACITY",
    "COVERAGE_STATUS",
    "DESIRED_STATE_INVENTORIES",
    "PROMOTION_MANIFEST",
    "RECORD_TRACEABILITY",
    "RECOVERY_READINESS",
    "REVIEW_REPORT",
    "SERVING_STATE_DEFINITION",
    "VALIDATION",
}
_PACKAGE_KEYS = {
    "artifacts",
    "base_serving_state_fingerprint",
    "base_serving_state_id",
    "candidate_serving_state_fingerprint",
    "candidate_serving_state_id",
    "observation_cutoff",
    "package_fingerprint",
    "promotion_manifest_fingerprint",
    "promotion_manifest_id",
    "proposal_id",
    "schema_id",
    "title",
    "valid_from",
    "valid_until",
    "validity_predicates",
}


class LocalPromotionPackageError(RuntimeError):
    """Exact executable Review package is absent, lossy, or drifted."""


class _ApprovalSnapshot(Protocol):
    @property
    def expected_base_serving_state_id(self) -> str: ...

    @property
    def candidate_serving_state_id(self) -> str: ...

    @property
    def valid_from(self) -> str: ...

    @property
    def valid_until(self) -> str: ...

    @property
    def validity_predicates(self) -> tuple[tuple[str, str, str], ...]: ...


def _fail() -> Never:
    raise LocalPromotionPackageError(_ERROR)


def _document(content: bytes) -> dict[str, JsonValue]:
    value = parse_json_bytes(content, max_bytes=1_000_000)
    if not isinstance(value, dict) or canonicalize(value) != content:
        _fail()
    return value


def _text(value: dict[str, JsonValue], field: str) -> str:
    item = value.get(field)
    if type(item) is not str or not item or item.strip() != item:
        _fail()
    return item


def _strings(value: JsonValue | None) -> tuple[str, ...]:
    if not isinstance(value, list) or any(type(item) is not str or not item for item in value):
        _fail()
    return tuple(item for item in value if type(item) is str)


def _member_path(root: Path, value: str) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        _fail()
    path = root.joinpath(*relative.parts)
    if path.is_symlink() or not path.is_file():
        _fail()
    return path


def _members(root: Path, package: dict[str, JsonValue]) -> dict[str, bytes]:
    raw = package.get("artifacts")
    if not isinstance(raw, list):
        _fail()
    result: dict[str, bytes] = {}
    seen_paths: set[Path] = set()
    for item in raw:
        if not isinstance(item, dict) or set(item) != {
            "byte_length",
            "fingerprint",
            "media_type",
            "path",
            "role",
        }:
            _fail()
        role = _text(item, "role")
        path = _member_path(root, _text(item, "path"))
        content = path.read_bytes()
        if (
            item.get("media_type") != "application/json"
            or item.get("byte_length") != len(content)
            or item.get("fingerprint") != f"sha256:{sha256(content).hexdigest()}"
            or role in result
            or path in seen_paths
        ):
            _fail()
        result[role] = content
        seen_paths.add(path)
    if set(result) != _EXPECTED_ROLES:
        _fail()
    return result


def _validate_package(package: dict[str, JsonValue]) -> None:
    if set(package) != _PACKAGE_KEYS or package.get("schema_id") != (
        "asklegal.hk-v1-local-review-package/v1"
    ):
        _fail()


def _validate_package_bindings(
    package: dict[str, JsonValue],
    snapshot: _ApprovalSnapshot,
    manifest_id: str,
    manifest_fingerprint: str,
) -> None:
    predicates = [
        {"contract_id": item[0], "fingerprint": item[2], "version": item[1]}
        for item in snapshot.validity_predicates
    ]
    if (
        package.get("promotion_manifest_id") != manifest_id
        or package.get("promotion_manifest_fingerprint") != manifest_fingerprint
        or package.get("base_serving_state_id") != snapshot.expected_base_serving_state_id
        or package.get("candidate_serving_state_id") != snapshot.candidate_serving_state_id
        or package.get("valid_from") != snapshot.valid_from
        or package.get("valid_until") != snapshot.valid_until
        or package.get("validity_predicates") != predicates
    ):
        _fail()
    fingerprint = _text(package, "package_fingerprint")
    unsigned = dict(package)
    unsigned.pop("package_fingerprint")
    if fingerprint != f"sha256:{sha256(canonicalize(unsigned)).hexdigest()}":
        _fail()


def _desired(value: dict[str, JsonValue]) -> DesiredStateInventory:
    required = {
        "inventory_fingerprint",
        "inventory_id",
        "observation_cutoff",
        "records",
        "records_fingerprint",
        "scope_releases",
        "target_key",
    }
    if set(value) != required:
        _fail()
    raw_records = value.get("records")
    raw_scopes = value.get("scope_releases")
    if not isinstance(raw_records, list) or not isinstance(raw_scopes, list):
        _fail()
    records: list[FlattenedRecord] = []
    for item in raw_records:
        if not isinstance(item, dict) or set(item) != {
            "artifact_ref",
            "authority_note",
            "country",
            "evidence_refs",
            "jurisdiction",
            "material_type",
            "record_id",
            "release_id",
            "scope_id",
            "serving_payload_fingerprint",
            "source",
            "text",
        }:
            _fail()
        record = ServingRecord(
            _text(item, "record_id"),
            _text(item, "text"),
            _text(item, "country"),
            _text(item, "jurisdiction"),
            _text(item, "material_type"),
            _text(item, "source"),
            _text(item, "authority_note"),
            _text(item, "artifact_ref"),
            _strings(item.get("evidence_refs")),
        )
        fingerprint = _text(item, "serving_payload_fingerprint")
        if serving_payload_fingerprint(record) != fingerprint:
            _fail()
        records.append(
            FlattenedRecord(
                record.record_id,
                fingerprint,
                _text(item, "scope_id"),
                _text(item, "release_id"),
                record,
            )
        )
    scopes: list[tuple[str, str]] = []
    for item in raw_scopes:
        if not isinstance(item, list) or len(item) != _PAIR_SIZE:
            _fail()
        first, second = item
        if type(first) is not str or type(second) is not str:
            _fail()
        scopes.append((first, second))
    record_projection = [
        {
            "content_fingerprint": item.content_fingerprint,
            "record_id": item.record_id,
            "release_id": item.release_id,
            "scope_id": item.scope_id,
        }
        for item in records
    ]
    records_fingerprint = (
        f"sha256:{sha256(canonicalize(checked_json_value(record_projection))).hexdigest()}"
    )
    target_key = _text(value, "target_key")
    cutoff = _text(value, "observation_cutoff")
    inventory_body = {
        "observation_cutoff": cutoff,
        "records_fingerprint": records_fingerprint,
        "scope_releases": [list(item) for item in scopes],
        "target_key": target_key,
    }
    inventory_fingerprint = (
        f"sha256:{sha256(canonicalize(checked_json_value(inventory_body))).hexdigest()}"
    )
    inventory_material = chr(31).join((target_key, cutoff, inventory_fingerprint)).encode()
    inventory_id = f"dsi_{sha256(inventory_material).hexdigest()[:48]}"
    if (
        records_fingerprint != value.get("records_fingerprint")
        or inventory_fingerprint != value.get("inventory_fingerprint")
        or inventory_id != value.get("inventory_id")
    ):
        _fail()
    return DesiredStateInventory(
        inventory_id,
        target_key,
        cutoff,
        tuple(scopes),
        tuple(records),
        records_fingerprint,
        inventory_fingerprint,
    )


def _coverage(value: dict[str, JsonValue]) -> CoverageStatusManifest:
    raw_scopes = value.get("scopes")
    if not isinstance(raw_scopes, list):
        _fail()
    statuses: list[CoverageScopeStatus] = []
    for item in raw_scopes:
        if not isinstance(item, dict):
            _fail()
        statuses.append(
            CoverageScopeStatus(
                _text(item, "scope_id"),
                CoverageState(_text(item, "status")),
                _text(item, "last_verified_at"),
                _strings(item.get("gap_refs")),
                _strings(item.get("quarantine_refs")),
                _strings(item.get("source_failure_refs")),
                CoverageWarning(_text(item, "warning")),
            )
        )
    source = value.get("source_cycle")
    return freeze_coverage_status(
        _text(value, "serving_state_id"),
        _text(value, "observation_cutoff"),
        tuple(item.scope_id for item in statuses),
        statuses,
        source_cycle=(None if source is None else source_coverage_cycle_binding_from_json(source)),
    )


def load_v1_promotion_manifest_from_review_package(
    root: Path,
    profile: ServingCapabilityProfile,
    *,
    expected_manifest_id: str,
    expected_manifest_fingerprint: str,
) -> PromotionManifest:
    """Recover and re-freeze executable typed authority only from reviewed members."""
    try:
        package_path = _member_path(root, _PACKAGE)
        package_content = package_path.read_bytes()
        package = _document(package_content)
        _validate_package(package)
        members = _members(root, package)
        manifest_bytes = members["PROMOTION_MANIFEST"]
        snapshot = promotion_approval_snapshot_from_bytes(
            manifest_bytes,
            expected_manifest_id=expected_manifest_id,
            expected_fingerprint=expected_manifest_fingerprint,
        )
        _validate_package_bindings(
            package,
            snapshot,
            expected_manifest_id,
            expected_manifest_fingerprint,
        )
        desired = _desired(_document(members["DESIRED_STATE_INVENTORIES"]))
        coverage = _coverage(_document(members["COVERAGE_STATUS"]))
        manifest_document = _document(manifest_bytes)
        predicates = snapshot.validity_predicates
        bindings = ProposalMemberBindings(
            _text(package, "observation_cutoff"),
            expected_manifest_id,
            expected_manifest_fingerprint,
            snapshot.expected_base_serving_state_id,
            snapshot.candidate_serving_state_id,
            _text(package, "candidate_serving_state_fingerprint"),
        )
        traceability = _document(members["RECORD_TRACEABILITY"])
        raw_shards = traceability.get("shards")
        if not isinstance(raw_shards, list):
            _fail()
        shards: dict[str, bytes] = {}
        for item in raw_shards:
            if not isinstance(item, dict):
                _fail()
            shard_path = _text(item, "path")
            shards[shard_path] = _member_path(
                root / "record-traceability",
                shard_path,
            ).read_bytes()
        validate_v1_proposal_members(members, bindings, shards)
        if (
            desired.observation_cutoff != bindings.observation_cutoff
            or coverage.canonical_bytes != members["COVERAGE_STATUS"]
            or profile.embedding.profile_fingerprint
            != _text(manifest_document, "embedding_profile_fingerprint")
        ):
            _fail()
        raw_batch_size = manifest_document.get("batch_size")
        if type(raw_batch_size) is not int:
            _fail()
        manifest = freeze_v1_promotion_manifest(
            PromotionPlan(
                _text(manifest_document, "environment"),
                _text(manifest_document, "jurisdiction"),
                _text(manifest_document, "freeze_date"),
                snapshot.valid_from,
                snapshot.valid_until,
                snapshot.expected_base_serving_state_id,
                snapshot.candidate_serving_state_id,
                bindings.candidate_serving_state_fingerprint,
                _text(manifest_document, "rollback_serving_state_id"),
                desired,
                coverage,
                profile.embedding,
                predicates,
                raw_batch_size,
                _text(manifest_document, "project_id"),
                snapshot.action_contract_version,
                snapshot.actions,
                _strings(manifest_document.get("exact_retirement_target_ids")),
            )
        )
        if (
            manifest.manifest_id != expected_manifest_id
            or manifest.fingerprint != expected_manifest_fingerprint
        ):
            _fail()
    except LocalPromotionPackageError:
        raise
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise LocalPromotionPackageError(_ERROR) from error
    else:
        return manifest
