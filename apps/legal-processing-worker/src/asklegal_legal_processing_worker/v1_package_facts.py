# ruff: noqa: EM101
"""Owning loader for exact proposal-time package and traceability facts."""

from __future__ import annotations

import os
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path, PurePosixPath

from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_management_register import LocalLegalIdentityRegister
from asklegal_management_register_ports import LegalIdentityKind, LegalIdentityRequest

from .v1_acceptance import (
    AcceptanceLegalError,
    preview_generated_family_releases,
)

_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)


def prepare_hk_v1_package_fact_components(
    operation_id: str,
    request: Mapping[str, JsonValue],
    operation_root: Path,
    configuration_root: Path,
    state_root: Path,
) -> None:
    """Load, cross-bind, and persist package facts without inventing readiness."""
    if not configuration_root.is_absolute() or configuration_root.is_symlink():
        raise AcceptanceLegalError("LEGAL_PROCESSING_PACKAGE_FACTS_NOT_READY")
    required = {
        "package": "hk-v1-review-package.json",
        "readiness": "hk-v1-review-readiness.json",
        "task7": "hk-v1-two-family-proposal.json",
        "coverage": "coverage-status/coverage.json",
        "promotion": "promotion-manifest/promotion-manifest.json",
        "cost": "cost-and-capacity/admission.json",
        "report": "review-report/report.json",
        "lookup": "record-traceability/lookup.json",
    }
    documents = {name: _read(configuration_root / path) for name, path in required.items()}
    cutoff = _text(request.get("observation_cutoff"))
    package = documents["package"]
    readiness = documents["readiness"]
    promotion = documents["promotion"]
    coverage = documents["coverage"]
    task7 = documents["task7"]
    if (
        any(document.get("observation_cutoff") != cutoff for document in (package, coverage, task7))
        or promotion.get("observation_cutoff", promotion.get("valid_from")) != cutoff
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_PACKAGE_FACTS_DRIFT")
    refs = {
        "model_evaluation": _text(readiness.get("model_evaluation_ref")),
        "retrieval_evaluation": _text(readiness.get("retrieval_evaluation_ref")),
        "native_backup": _text(readiness.get("native_backup_ref")),
        "recovery_backup": _text(readiness.get("recovery_backup_ref")),
    }
    fingerprints = {
        f"{name}_fingerprint": _fingerprint(_read_bytes(configuration_root, relative))
        for name, relative in refs.items()
    }
    if (
        package.get("base_serving_state_id") != readiness.get("rollback_state_id")
        or package.get("base_serving_state_id") != promotion.get("base_serving_state_id")
        or promotion.get("rollback_serving_state_id") != package.get("base_serving_state_id")
        or promotion.get("target_namespace", readiness.get("target_namespace"))
        != readiness.get("target_namespace")
        or promotion.get("target_name", readiness.get("target_name"))
        != readiness.get("target_name")
        or readiness.get("embedding_profile_fingerprint")
        != promotion.get("embedding_profile_fingerprint")
    ):
        raise AcceptanceLegalError("LEGAL_PROCESSING_PACKAGE_FACTS_DRIFT")
    releases = preview_generated_family_releases(operation_root)
    release_ids = {
        releases.case_release.scope_id: releases.case_release.release_id,
        **{
            item.legislation_scope_code: item.release.release_id
            for item in releases.legislation_release_set.scope_results
        },
    }
    if frozenset(release_ids) != frozenset(_SCOPES):
        raise AcceptanceLegalError("LEGAL_PROCESSING_PACKAGE_FACTS_DRIFT")
    lookup = documents["lookup"]
    register = LocalLegalIdentityRegister(state_root / "package-identities.json")
    lookup_id = register.issue_identity(
        LegalIdentityRequest(LegalIdentityKind.TRACEABILITY_LOOKUP, f"package:{operation_id}")
    ).identity_id
    shards = [
        {
            "release_scope_id": scope,
            "corpus_release_id": release_ids[scope],
            "lookup_shard_id": register.issue_identity(
                LegalIdentityRequest(
                    LegalIdentityKind.TRACEABILITY_SHARD,
                    f"package:{operation_id}:{scope}:{release_ids[scope]}",
                )
            ).identity_id,
        }
        for scope in _SCOPES
    ]
    register.commit()
    common = {
        "schema_version": "1.0.0",
        "operation_id": operation_id,
        "command_fingerprint": request.get("command_fingerprint"),
        "observation_cutoff": cutoff,
    }
    traceability = {
        **common,
        "schema_id": "asklegal.hk-v1-package-traceability-input/v1",
        "package_lookup_input": {
            "lookup_revision_id": lookup_id,
            "manifest_schema_fingerprint": lookup.get("manifest_schema_fingerprint"),
            "entry_schema_fingerprint": lookup.get("entry_schema_fingerprint"),
        },
        "package_lookup_shards": shards,
    }
    policy = {
        **common,
        "schema_id": "asklegal.hk-v1-package-policy-facts/v1",
        "title": package.get("title"),
        "base_serving_state_fingerprint": package.get("base_serving_state_fingerprint"),
        "task7_proposal": task7,
        "coverage_status": coverage,
        "promotion_manifest": promotion,
        "readiness": {
            key: readiness.get(key)
            for key in (
                "limitations",
                "model_evaluation_ref",
                "retrieval_evaluation_ref",
                "model_profile_fingerprint",
                "embedding_profile_fingerprint",
                "serving_profile_fingerprint",
                "target_namespace",
                "backup_profile_fingerprint",
                "target_name",
                "native_backup_ref",
                "recovery_backup_ref",
                "rollback_state_id",
            )
        }
        | fingerprints,
        "estimated_cost_microunits": documents["cost"].get("estimated_cost_microunits"),
        "review_statement": documents["report"].get("statement"),
    }
    _atomic(operation_root / "package-traceability-input.json", traceability)
    _atomic(operation_root / "package-policy-facts.json", policy)


def _read(path: Path) -> dict[str, JsonValue]:
    content = _read_bytes(path.parent, path.name)
    value = parse_json_bytes(content, max_bytes=16_777_216)
    if type(value) is not dict or canonicalize(value) != content:
        raise AcceptanceLegalError("LEGAL_PROCESSING_PACKAGE_FACTS_INVALID")
    return value


def _read_bytes(root: Path, relative: str) -> bytes:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts:
        raise AcceptanceLegalError("LEGAL_PROCESSING_PACKAGE_FACTS_INVALID")
    path = root.joinpath(*pure.parts)
    if path.is_symlink() or not path.is_file():
        raise AcceptanceLegalError("LEGAL_PROCESSING_PACKAGE_FACTS_NOT_READY")
    return path.read_bytes()


def _atomic(path: Path, body: Mapping[str, object]) -> None:
    checked = checked_json_value(body)
    if type(checked) is not dict:
        raise AcceptanceLegalError("LEGAL_PROCESSING_PACKAGE_FACTS_INVALID")
    content = canonicalize(
        checked_json_value({**checked, "fingerprint": _fingerprint(canonicalize(checked))})
    )
    if path.exists():
        if path.read_bytes() != content:
            raise AcceptanceLegalError("LEGAL_PROCESSING_PACKAGE_FACTS_DRIFT")
        return
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    if path.read_bytes() != content:
        raise AcceptanceLegalError("LEGAL_PROCESSING_PACKAGE_FACTS_READBACK_FAILED")


def _text(value: object) -> str:
    if type(value) is not str or not value:
        raise AcceptanceLegalError("LEGAL_PROCESSING_PACKAGE_FACTS_INVALID")
    return value


def _fingerprint(content: bytes) -> str:
    return f"sha256:{sha256(content).hexdigest()}"
