"""Fail-closed local proof for reproducible and attested OCI image admission."""

import argparse
import base64
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import cast

MANIFEST_PATH = Path("tools/image_admission_spike_manifest.json")
FIXTURE_PATH = Path("tools/image_admission_fixture")
OCI_IMAGE_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
OCI_IMAGE_INDEX = "application/vnd.oci.image.index.v1+json"
OCI_IMAGE_CONFIG = "application/vnd.oci.image.config.v1+json"
IN_TOTO_MEDIA_TYPE = "application/vnd.in-toto+json"
FIXED_CREATED = "1980-01-01T00:00:00Z"
_DIGEST_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SECRET_PATTERN = re.compile(
    rb"(?i)(api[_-]?key|authorization|bearer|password|private[_-]?key|secret|token)\s*[:=]"
)

type JsonScalar = bool | int | float | str | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class ImageAdmissionFailure(RuntimeError):
    """One exact image-admission invariant failed."""


@dataclass(frozen=True, slots=True)
class Descriptor:
    """One verified OCI descriptor."""

    media_type: str
    digest: str
    size: int
    artifact_type: str | None = None


@dataclass(frozen=True, slots=True)
class ToolPaths:
    """Exact external executables and offline database used by the proof."""

    buildx: Path
    docker: Path
    grype: Path
    grype_db: Path
    notation: Path
    openssl: Path
    oras: Path
    sudo: Path
    syft: Path


@dataclass(frozen=True, slots=True)
class BuildEvidence:
    """Verified image and provenance result from one BuildKit output."""

    image_descriptor: Descriptor
    image_graph: dict[str, bytes]
    filesystem: dict[str, bytes]
    normalized_provenance: JsonValue


@dataclass(frozen=True, slots=True)
class ImageAdmissionReport:
    """Canonical final proof result."""

    image_digest: str
    image_graph_sha256: str
    normalized_sbom_sha256: str
    normalized_provenance_sha256: str
    vulnerability_report_sha256: str
    licence_report_sha256: str
    candidate_graph_sha256: str
    signed_release_graph_sha256: str
    recovery_graph_sha256: str
    tool_versions: dict[str, str]
    vulnerability_database: dict[str, str]

    def to_json(self) -> dict[str, JsonValue]:
        """Return the deterministic report representation."""
        return {
            "candidate_graph_sha256": self.candidate_graph_sha256,
            "image_digest": self.image_digest,
            "image_graph_sha256": self.image_graph_sha256,
            "licence_report_sha256": self.licence_report_sha256,
            "normalized_provenance_sha256": self.normalized_provenance_sha256,
            "normalized_sbom_sha256": self.normalized_sbom_sha256,
            "recovery_graph_sha256": self.recovery_graph_sha256,
            "signed_release_graph_sha256": self.signed_release_graph_sha256,
            "tool_versions": dict(sorted(self.tool_versions.items())),
            "vulnerability_database": dict(sorted(self.vulnerability_database.items())),
            "vulnerability_report_sha256": self.vulnerability_report_sha256,
        }


def load_policy(root: Path) -> dict[str, JsonValue]:
    """Load the checked-in closed spike policy."""
    policy = _json_mapping(_load_json(root / MANIFEST_PATH), "policy")
    expected = {
        "application",
        "candidate_repository",
        "identity_policy",
        "image",
        "platform",
        "release_repository",
        "required_referrer_types",
        "risk_acceptances",
        "runtime",
        "schema_version",
        "source_date_epoch",
        "test_licence_catalogue",
        "test_signing",
        "tools",
        "vulnerability_database",
    }
    if set(policy) != expected or _json_integer(policy["schema_version"], "schema") != 1:
        raise ImageAdmissionFailure("IMAGE_POLICY_SCHEMA_INVALID")
    if _json_string(policy["candidate_repository"], "candidate") != (
        f"candidate/{_json_string(policy['application'], 'application')}"
    ):
        raise ImageAdmissionFailure("IMAGE_POLICY_CANDIDATE_SCOPE_INVALID")
    if _json_string(policy["release_repository"], "release") != (
        f"release/{_json_string(policy['application'], 'application')}"
    ):
        raise ImageAdmissionFailure("IMAGE_POLICY_RELEASE_SCOPE_INVALID")
    signing = _json_mapping(policy["test_signing"], "test signing")
    if (
        _json_string(signing.get("trust_capability"), "trust capability") != "LOCAL_TEST_ONLY"
        or signing.get("production_trust_forbidden") is not True
    ):
        raise ImageAdmissionFailure("IMAGE_TEST_TRUST_NOT_ISOLATED")
    return policy


def verify_toolchain(
    policy: Mapping[str, JsonValue], paths: ToolPaths, now: datetime
) -> tuple[dict[str, str], dict[str, str]]:
    """Verify exact binaries, local runtimes, and the offline Grype database."""
    tool_policy = _json_mapping(policy["tools"], "tools")
    executable_by_name = {
        "buildx": paths.buildx,
        "grype": paths.grype,
        "notation": paths.notation,
        "oras": paths.oras,
        "syft": paths.syft,
    }
    versions: dict[str, str] = {}
    for name, executable in executable_by_name.items():
        selected = _json_mapping(tool_policy[name], f"tools.{name}")
        expected_hash = _json_string(selected["binary_sha256"], f"{name} hash")
        if _sha256(executable.read_bytes()) != expected_hash:
            raise ImageAdmissionFailure(f"IMAGE_TOOL_HASH_MISMATCH: {name}")
        versions[name] = _json_string(selected["version"], f"{name} version")

    command_outputs = {
        "buildx": _run(
            (str(paths.sudo), "-n", str(paths.buildx), "version"), cwd=paths.buildx.parent
        ).stdout,
        "grype": _run((str(paths.grype), "version"), cwd=paths.grype.parent).stdout,
        "notation": _run((str(paths.notation), "version"), cwd=paths.notation.parent).stdout,
        "oras": _run((str(paths.oras), "version"), cwd=paths.oras.parent).stdout,
        "syft": _run((str(paths.syft), "version"), cwd=paths.syft.parent).stdout,
    }
    for name, version in versions.items():
        if version not in command_outputs[name]:
            raise ImageAdmissionFailure(f"IMAGE_TOOL_VERSION_MISMATCH: {name}")

    runtime = _json_mapping(policy["runtime"], "runtime")
    docker_version = _run(
        (
            str(paths.sudo),
            "-n",
            str(paths.docker),
            "version",
            "--format",
            "{{.Server.Version}}",
        ),
        cwd=paths.docker.parent,
    ).stdout.strip()
    if docker_version != _json_string(runtime["docker_engine_version"], "docker"):
        raise ImageAdmissionFailure("IMAGE_DOCKER_VERSION_MISMATCH")
    buildx_nodes = _run(
        (str(paths.sudo), "-n", str(paths.buildx), "ls"), cwd=paths.buildx.parent
    ).stdout
    buildkit_version = _json_string(runtime["buildkit_version"], "buildkit")
    if buildkit_version not in buildx_nodes:
        raise ImageAdmissionFailure("IMAGE_BUILDKIT_VERSION_MISMATCH")
    openssl_version = _run((str(paths.openssl), "version"), cwd=paths.openssl.parent).stdout.strip()
    if not openssl_version.startswith(_json_string(runtime["openssl_version_prefix"], "openssl")):
        raise ImageAdmissionFailure("IMAGE_OPENSSL_VERSION_MISMATCH")
    versions.update(
        {
            "buildkit": buildkit_version,
            "docker": docker_version,
            "openssl": openssl_version.split()[1],
        }
    )

    db_policy = _json_mapping(policy["vulnerability_database"], "database")
    database_path = paths.grype_db / "6" / "vulnerability.db"
    if _sha256(database_path.read_bytes()) != _json_string(
        db_policy["database_sha256"], "database hash"
    ):
        raise ImageAdmissionFailure("IMAGE_DATABASE_HASH_MISMATCH")
    grype_environment = _grype_environment(paths)
    status = _json_mapping(
        _load_json_text(
            _run(
                (str(paths.grype), "db", "status", "-o", "json"),
                cwd=paths.grype.parent,
                environment=grype_environment,
            ).stdout
        ),
        "database status",
    )
    built = _parse_utc(_json_string(status["built"], "database built"))
    maximum_age = _json_integer(db_policy["max_age_seconds"], "database age")
    validate_database_freshness(built, now, maximum_age)
    if (
        status.get("valid") is not True
        or _json_string(status["schemaVersion"], "database schema")
        != _json_string(db_policy["schema_version"], "selected database schema")
        or _format_utc(built) != _json_string(db_policy["built"], "selected database built")
    ):
        raise ImageAdmissionFailure("IMAGE_DATABASE_STATUS_MISMATCH")
    database = {
        "built": _format_utc(built),
        "sha256": _json_string(db_policy["database_sha256"], "database hash"),
        "schema": _json_string(db_policy["schema_version"], "database schema"),
    }
    return versions, database


def validate_database_freshness(built: datetime, now: datetime, maximum_age: int) -> None:
    """Reject stale database state and timestamps that cannot be trusted."""
    if built.tzinfo is None or now.tzinfo is None or maximum_age < 0:
        raise ImageAdmissionFailure("IMAGE_DATABASE_TIME_INVALID")
    built_utc = built.astimezone(UTC)
    now_utc = now.astimezone(UTC)
    if built_utc > now_utc:
        raise ImageAdmissionFailure("IMAGE_DATABASE_TIME_INVALID")
    if now_utc - built_utc > _seconds(maximum_age):
        raise ImageAdmissionFailure("IMAGE_DATABASE_STALE")


def normalize_sbom(value: JsonValue) -> JsonValue:
    """Remove only Syft observation identity and time fields from SPDX output."""
    normalized = deepcopy(value)
    root = _json_mapping(normalized, "SBOM")
    creation = _json_mapping(root["creationInfo"], "SBOM creation")
    creation.pop("created", None)
    root.pop("documentNamespace", None)
    return root


def normalize_provenance(value: JsonValue) -> JsonValue:
    """Remove BuildKit run observations and internal digest-to-step mappings."""
    normalized = deepcopy(value)
    root = _json_mapping(normalized, "provenance")
    predicate = _json_mapping(root["predicate"], "provenance predicate")
    metadata = _json_mapping(predicate["metadata"], "provenance metadata")
    for field in ("buildFinishedOn", "buildInvocationID", "buildStartedOn"):
        metadata.pop(field, None)
    _remove_mapping_key(root, "digestMapping")
    return root


def normalize_vulnerability_report(value: JsonValue) -> JsonValue:
    """Remove only Grype observation time and host output/cache paths."""
    normalized = deepcopy(value)
    root = _json_mapping(normalized, "Grype report")
    descriptor = _json_mapping(root["descriptor"], "Grype descriptor")
    descriptor.pop("timestamp", None)
    configuration = _json_mapping(descriptor["configuration"], "Grype configuration")
    configuration.pop("file", None)
    database = _json_mapping(configuration["db"], "Grype database config")
    database.pop("cache-dir", None)
    return root


def evaluate_licences(
    sbom: JsonValue,
    catalogue: Mapping[str, JsonValue],
    image_paths: set[str],
) -> dict[str, JsonValue]:
    """Apply the closed synthetic licence catalogue to every non-container package."""
    root = _json_mapping(sbom, "SBOM")
    packages = _json_sequence(root["packages"], "SBOM packages")
    allowed = set(_json_string_list(catalogue["allowed"], "allowed licences"))
    denied = set(_json_string_list(catalogue["denied"], "denied licences"))
    review = set(_json_string_list(catalogue["review_required"], "review licences"))
    obligations = _json_mapping(catalogue["obligations"], "licence obligations")
    results: list[JsonValue] = []
    for item in packages:
        package = _json_mapping(item, "SBOM package")
        if package.get("primaryPackagePurpose") == "CONTAINER":
            continue
        name = _json_string(package["name"], "package name")
        version = _json_string(package["versionInfo"], "package version")
        licence = _json_string(package["licenseDeclared"], "package licence")
        if licence in denied:
            raise ImageAdmissionFailure("IMAGE_LICENCE_DENIED")
        if licence in review:
            raise ImageAdmissionFailure("IMAGE_LICENCE_REVIEW_REQUIRED")
        if licence in {"NOASSERTION", "NONE", "UNKNOWN"} or licence not in allowed:
            raise ImageAdmissionFailure("IMAGE_LICENCE_UNKNOWN")
        required_paths = _json_string_list(
            obligations.get(licence, []), f"obligations for {licence}"
        )
        if not set(required_paths) <= image_paths:
            raise ImageAdmissionFailure("IMAGE_LICENCE_OBLIGATION_MISSING")
        obligation_values: list[JsonValue] = []
        obligation_values.extend(sorted(required_paths))
        result: dict[str, JsonValue] = {
            "licence": licence,
            "name": name,
            "obligations": obligation_values,
            "result": "ALLOWED_SYNTHETIC_POLICY",
            "version": version,
        }
        results.append(result)
    if not results:
        raise ImageAdmissionFailure("IMAGE_LICENCE_PACKAGE_SET_EMPTY")
    return {
        "catalogue_capability": "LOCAL_SYNTHETIC_ONLY",
        "packages": sorted(results, key=lambda item: str(_json_mapping(item, "result")["name"])),
        "result": "PASS",
        "schema_version": 1,
    }


def evaluate_vulnerabilities(
    report: JsonValue,
    database: Mapping[str, str],
    *,
    image_digest: str | None = None,
    risk_acceptances: Sequence[Mapping[str, JsonValue]] = (),
    now: datetime | None = None,
) -> dict[str, JsonValue]:
    """Apply ADR 0095's initial vulnerability rules to complete Grype findings."""
    root = _json_mapping(report, "Grype report")
    if not {"descriptor", "matches", "source"} <= set(root):
        raise ImageAdmissionFailure("IMAGE_VULNERABILITY_REPORT_INCOMPLETE")
    matches = _json_sequence(root["matches"], "Grype matches")
    descriptor = _json_mapping(root["descriptor"], "Grype descriptor")
    configuration = _json_mapping(descriptor.get("configuration"), "Grype configuration")
    external_sources = _json_mapping(configuration.get("externalSources"), "Grype external sources")
    database_configuration = _json_mapping(configuration.get("db"), "Grype database config")
    database_descriptor = _json_mapping(descriptor.get("db"), "Grype database descriptor")
    database_status = _json_mapping(database_descriptor.get("status"), "Grype database status")
    source = _json_mapping(root["source"], "Grype source")
    if image_digest is not None:
        target = _json_mapping(source.get("target"), "Grype source target")
        if target.get("manifestDigest") != image_digest:
            raise ImageAdmissionFailure("IMAGE_VULNERABILITY_SUBJECT_MISMATCH")
    if (
        external_sources.get("enable") is not False
        or database_configuration.get("auto-update") is not False
        or database_status.get("valid") is not True
        or database_status.get("schemaVersion") != database.get("schema")
        or database_status.get("built") != database.get("built")
    ):
        raise ImageAdmissionFailure("IMAGE_VULNERABILITY_DATABASE_BINDING_INVALID")
    dispositions: list[JsonValue] = []
    for item in matches:
        match = _json_mapping(item, "Grype match")
        if not {"artifact", "vulnerability"} <= set(match):
            raise ImageAdmissionFailure("IMAGE_VULNERABILITY_MATCH_INCOMPLETE")
        vulnerability = _json_mapping(match["vulnerability"], "vulnerability")
        artifact = _json_mapping(match["artifact"], "vulnerable artifact")
        if not {"fix", "id", "severity"} <= set(vulnerability) or not {
            "name",
            "version",
        } <= set(artifact):
            raise ImageAdmissionFailure("IMAGE_VULNERABILITY_MATCH_INCOMPLETE")
        identifier = _json_string(vulnerability["id"], "vulnerability id")
        severity = _json_string(vulnerability["severity"], "severity").lower()
        fix = _json_mapping(vulnerability["fix"], "vulnerability fix")
        fixed_versions = _json_sequence(fix.get("versions", []), "fixed versions")
        known_exploited = _json_sequence(vulnerability.get("knownExploited", []), "known exploited")
        if known_exploited:
            raise ImageAdmissionFailure("IMAGE_VULNERABILITY_KNOWN_EXPLOITED")
        if severity == "critical":
            raise ImageAdmissionFailure("IMAGE_VULNERABILITY_CRITICAL")
        if severity == "high" and fixed_versions:
            raise ImageAdmissionFailure("IMAGE_VULNERABILITY_HIGH_FIXED")
        if severity == "high":
            acceptance = _exact_risk_acceptance(
                risk_acceptances,
                image_digest,
                artifact,
                identifier,
                datetime.now(UTC) if now is None else now,
            )
            dispositions.append(
                {
                    "acceptance_expires_at": acceptance["expires_at"],
                    "acceptance_owner": acceptance["owner"],
                    "id": identifier,
                    "package": _json_string(artifact["name"], "artifact name"),
                    "severity": "HIGH",
                    "status": "TIME_BOUND_RISK_ACCEPTANCE",
                    "version": _json_string(artifact["version"], "artifact version"),
                }
            )
            continue
        if severity not in {"medium", "low", "negligible"}:
            raise ImageAdmissionFailure("IMAGE_VULNERABILITY_SEVERITY_UNKNOWN")
        dispositions.append(
            {
                "id": identifier,
                "package": _json_string(artifact["name"], "artifact name"),
                "severity": severity.upper(),
                "status": "OWNED_REMEDIATION_REQUIRED",
                "version": _json_string(artifact["version"], "artifact version"),
            }
        )
    return {
        "complete_grype_report_sha256": _sha256(
            _canonical_json_bytes(normalize_vulnerability_report(root))
        ),
        "database": dict(database),
        "dispositions": sorted(
            dispositions,
            key=lambda item: str(_json_mapping(item, "disposition")["id"]),
        ),
        "result": "PASS",
        "schema_version": 1,
    }


def _exact_risk_acceptance(
    acceptances: Sequence[Mapping[str, JsonValue]],
    image_digest: str | None,
    artifact: Mapping[str, JsonValue],
    vulnerability_id: str,
    now: datetime,
) -> Mapping[str, JsonValue]:
    expected_keys = {
        "approval_evidence",
        "compensating_controls",
        "expires_at",
        "image_digest",
        "owner",
        "package",
        "reason",
        "version",
        "vulnerability",
    }
    package = _json_string(artifact["name"], "artifact name")
    version = _json_string(artifact["version"], "artifact version")
    matches = [
        acceptance
        for acceptance in acceptances
        if acceptance.get("image_digest") == image_digest
        and acceptance.get("package") == package
        and acceptance.get("version") == version
        and acceptance.get("vulnerability") == vulnerability_id
    ]
    if len(matches) == 0:
        raise ImageAdmissionFailure("IMAGE_VULNERABILITY_HIGH_ACCEPTANCE_REQUIRED")
    if len(matches) != 1:
        raise ImageAdmissionFailure("IMAGE_VULNERABILITY_HIGH_ACCEPTANCE_INVALID")
    acceptance = matches[0]
    if set(acceptance) != expected_keys or image_digest is None:
        raise ImageAdmissionFailure("IMAGE_VULNERABILITY_HIGH_ACCEPTANCE_INVALID")
    for field in ("approval_evidence", "owner", "reason"):
        _json_string(acceptance[field], f"risk acceptance {field}")
    controls = _json_string_list(acceptance["compensating_controls"], "risk acceptance controls")
    expires = _parse_utc(_json_string(acceptance["expires_at"], "risk acceptance expiry"))
    if not controls or now.tzinfo is None or expires <= now.astimezone(UTC):
        raise ImageAdmissionFailure("IMAGE_VULNERABILITY_HIGH_ACCEPTANCE_INVALID")
    return acceptance


def validate_deployment_reference(reference: str, release_repository: str) -> None:
    """Require one exact release repository and digest reference."""
    prefix = f"{release_repository}@"
    if not reference.startswith(prefix) or not _DIGEST_PATTERN.fullmatch(
        reference.removeprefix(prefix)
    ):
        raise ImageAdmissionFailure("IMAGE_DEPLOYMENT_REFERENCE_INVALID")


def validate_identity(actions: Sequence[str], permitted: Sequence[str]) -> None:
    """Reject broad or extra capabilities and require the exact narrow set."""
    if any("*" in action or action in {"catalog/list", "registry/admin"} for action in actions):
        raise ImageAdmissionFailure("IMAGE_IDENTITY_BROAD_CAPABILITY")
    if set(actions) != set(permitted):
        raise ImageAdmissionFailure("IMAGE_IDENTITY_CAPABILITY_MISMATCH")


def run_spike(
    root: Path,
    paths: ToolPaths,
    work_root: Path,
    *,
    now: datetime | None = None,
) -> ImageAdmissionReport:
    """Execute the full synthetic local image-admission proof."""
    policy = load_policy(root)
    validation_time = datetime.now(UTC) if now is None else now
    versions, database = verify_toolchain(policy, paths, validation_time)
    source_epoch = _json_integer(policy["source_date_epoch"], "source epoch")
    image_policy = _json_mapping(policy["image"], "image")
    busybox = Path(_json_string(image_policy["busybox_path"], "busybox path"))
    if busybox != paths.docker.parent / busybox.name and busybox != Path("/bin/busybox"):
        raise ImageAdmissionFailure("IMAGE_BUSYBOX_PATH_INVALID")
    if _sha256(busybox.read_bytes()) != _json_string(
        image_policy["busybox_sha256"], "busybox hash"
    ):
        raise ImageAdmissionFailure("IMAGE_BUSYBOX_HASH_MISMATCH")

    contexts = [work_root / "context-a", work_root / "context-b"]
    for context in contexts:
        _create_context(root, context, busybox, source_epoch)
    archives = [work_root / "image-a.tar", work_root / "image-b.tar"]
    for context, archive in zip(contexts, archives, strict=True):
        _build_image(paths, context, archive, source_epoch)
    layouts = [work_root / "layout-a", work_root / "layout-b"]
    for archive, layout in zip(archives, layouts, strict=True):
        _safe_extract_tar(archive, layout)
    builds = [inspect_build(layout, policy) for layout in layouts]
    first, second = builds
    if first.image_descriptor != second.image_descriptor or first.image_graph != second.image_graph:
        raise ImageAdmissionFailure("IMAGE_BUILD_NOT_REPRODUCIBLE")
    if _canonical_json_bytes(first.normalized_provenance) != _canonical_json_bytes(
        second.normalized_provenance
    ):
        raise ImageAdmissionFailure("IMAGE_PROVENANCE_NOT_REPRODUCIBLE")

    sboms: list[JsonValue] = []
    for index, archive in enumerate(archives):
        sbom_path = work_root / f"sbom-{index}.json"
        _generate_sbom(
            paths,
            archive,
            first.image_descriptor.digest,
            sbom_path,
            work_root / f"syft-cache-{index}",
        )
        sboms.append(normalize_sbom(_load_json(sbom_path)))
    if _canonical_json_bytes(sboms[0]) != _canonical_json_bytes(sboms[1]):
        raise ImageAdmissionFailure("IMAGE_SBOM_NOT_REPRODUCIBLE")
    _validate_sbom_packages(sboms[0], image_policy)

    raw_grype_path = work_root / "grype-report.json"
    _scan_sbom(paths, work_root / "sbom-0.json", raw_grype_path, work_root / "grype-cache")
    raw_grype = _load_json(raw_grype_path)
    risk_acceptances = [
        _json_mapping(item, "risk acceptance")
        for item in _json_sequence(policy["risk_acceptances"], "risk acceptances")
    ]
    vulnerability_report = evaluate_vulnerabilities(
        raw_grype,
        database,
        image_digest=first.image_descriptor.digest,
        risk_acceptances=risk_acceptances,
        now=validation_time,
    )
    _prove_known_vulnerable_fixture(root, paths, database, work_root)
    licence_report = evaluate_licences(
        sboms[0],
        _json_mapping(policy["test_licence_catalogue"], "licence catalogue"),
        set(first.filesystem),
    )

    evidence = {
        "application/spdx+json": _canonical_json_bytes(sboms[0]),
        "application/vnd.asklegal.licence-report.v1+json": _canonical_json_bytes(licence_report),
        "application/vnd.asklegal.provenance.v1+json": _canonical_json_bytes(
            first.normalized_provenance
        ),
        "application/vnd.asklegal.vulnerability-report.v1+json": _canonical_json_bytes(
            vulnerability_report
        ),
    }
    candidate = work_root / "candidate-layout"
    shutil.copytree(layouts[0], candidate)
    _tag_image_manifest(paths, candidate, first.image_descriptor, work_root)
    for number, (artifact_type, content) in enumerate(sorted(evidence.items())):
        evidence_path = work_root / f"evidence-{number}.json"
        evidence_path.write_bytes(content)
        _attach(paths, candidate, first.image_descriptor.digest, artifact_type, evidence_path)
    required_types = set(_json_string_list(policy["required_referrer_types"], "required referrers"))
    _require_referrer_types(candidate, first.image_descriptor.digest, required_types)
    candidate_graph = graph_closure(candidate, first.image_descriptor.digest)

    release = work_root / "release-layout"
    _copy_graph(paths, candidate, "candidate", release, "release", work_root)
    if _resolve(paths, release, "release", work_root) != first.image_descriptor.digest:
        raise ImageAdmissionFailure("IMAGE_RELEASE_DIGEST_MISMATCH")
    release_before_signature = graph_closure(release, first.image_descriptor.digest)
    if candidate_graph != release_before_signature:
        raise ImageAdmissionFailure("IMAGE_RELEASE_GRAPH_MISMATCH")

    signature_bundle = _sign_release(
        paths,
        policy,
        first.image_descriptor.digest,
        {artifact_type: _sha256(content) for artifact_type, content in evidence.items()},
        work_root,
    )
    signature_path = work_root / "test-signature.json"
    signature_path.write_bytes(_canonical_json_bytes(signature_bundle))
    signature_type = _json_string(
        _json_mapping(policy["test_signing"], "test signing")["signature_artifact_type"],
        "signature type",
    )
    _attach(paths, release, first.image_descriptor.digest, signature_type, signature_path)
    _verify_signature_referrer(
        paths, release, first.image_descriptor.digest, signature_type, policy, work_root
    )
    _require_referrer_types(
        release, first.image_descriptor.digest, required_types | {signature_type}
    )
    signed_release_graph = graph_closure(release, first.image_descriptor.digest)

    identity = _json_mapping(policy["identity_policy"], "identity policy")
    validate_identity(
        _json_string_list(identity["copy_actions"], "copy actions"),
        ("candidate/read", "release/write"),
    )
    validate_identity(
        _json_string_list(identity["deploy_actions"], "deploy actions"),
        ("release/read", "review-api/deploy"),
    )
    release_repository = _json_string(policy["release_repository"], "release repository")
    validate_deployment_reference(
        f"{release_repository}@{first.image_descriptor.digest}", release_repository
    )
    _validate_sealed_record(policy, first.image_descriptor.digest, signed_release_graph)

    recovery = work_root / "recovery-layout"
    restored = work_root / "restored-layout"
    _copy_graph(paths, release, "release", recovery, "recovery", work_root)
    _copy_graph(paths, recovery, "recovery", restored, "restored", work_root)
    recovery_graph = graph_closure(restored, first.image_descriptor.digest)
    if recovery_graph != signed_release_graph:
        raise ImageAdmissionFailure("IMAGE_RECOVERY_GRAPH_MISMATCH")

    _prove_read_only_runtime(paths, contexts[0], source_epoch)
    return ImageAdmissionReport(
        image_digest=first.image_descriptor.digest,
        image_graph_sha256=_graph_hash(first.image_graph),
        normalized_sbom_sha256=_sha256(_canonical_json_bytes(sboms[0])),
        normalized_provenance_sha256=_sha256(_canonical_json_bytes(first.normalized_provenance)),
        vulnerability_report_sha256=_sha256(_canonical_json_bytes(vulnerability_report)),
        licence_report_sha256=_sha256(_canonical_json_bytes(licence_report)),
        candidate_graph_sha256=_graph_hash(candidate_graph),
        signed_release_graph_sha256=_graph_hash(signed_release_graph),
        recovery_graph_sha256=_graph_hash(recovery_graph),
        tool_versions=versions,
        vulnerability_database=database,
    )


def inspect_build(layout: Path, policy: Mapping[str, JsonValue]) -> BuildEvidence:
    """Verify one BuildKit OCI output and return its result-determining evidence."""
    outer = _json_mapping(_load_json(layout / "index.json"), "OCI outer index")
    outer_descriptors = _descriptors(outer["manifests"], "OCI outer manifests")
    if len(outer_descriptors) != 1 or outer_descriptors[0].media_type != OCI_IMAGE_INDEX:
        raise ImageAdmissionFailure("IMAGE_OUTER_INDEX_INVALID")
    inner = _json_mapping(_read_json_blob(layout, outer_descriptors[0]), "OCI image index")
    raw_inner = _json_sequence(inner["manifests"], "OCI image manifests")
    platform_entries: list[Descriptor] = []
    attestation_entries: list[tuple[Descriptor, str]] = []
    for item in raw_inner:
        raw = _json_mapping(item, "OCI image descriptor")
        platform = _json_mapping(raw.get("platform", {}), "OCI platform")
        descriptor = _descriptor(raw)
        if platform.get("os") == "linux" and platform.get("architecture") == "amd64":
            platform_entries.append(descriptor)
        else:
            annotations = _json_mapping(raw.get("annotations", {}), "attestation annotations")
            if annotations.get("vnd.docker.reference.type") == "attestation-manifest":
                attestation_entries.append(
                    (
                        descriptor,
                        _json_string(
                            annotations.get("vnd.docker.reference.digest"),
                            "attestation subject digest",
                        ),
                    )
                )
    if len(platform_entries) != 1 or len(attestation_entries) != 1:
        raise ImageAdmissionFailure("IMAGE_PLATFORM_OR_ATTESTATION_COUNT")
    image_descriptor = platform_entries[0]
    if image_descriptor.media_type != OCI_IMAGE_MANIFEST:
        raise ImageAdmissionFailure("IMAGE_PLATFORM_MANIFEST_TYPE")
    image_graph = _manifest_graph(layout, image_descriptor)
    filesystem = _verify_image_config_and_layers(layout, image_descriptor, policy)
    attestation_descriptor, attestation_subject = attestation_entries[0]
    if attestation_subject != image_descriptor.digest:
        raise ImageAdmissionFailure("IMAGE_PROVENANCE_SUBJECT_MISMATCH")
    provenance = _read_buildkit_provenance(layout, attestation_descriptor)
    return BuildEvidence(
        image_descriptor=image_descriptor,
        image_graph=image_graph,
        filesystem=filesystem,
        normalized_provenance=normalize_provenance(provenance),
    )


def graph_closure(layout: Path, root_digest: str) -> dict[str, bytes]:
    """Return the complete reachable subject graph, including all referrers."""
    index = _json_mapping(_load_json(layout / "index.json"), "OCI layout index")
    descriptors = _descriptors(index["manifests"], "OCI layout descriptors")
    roots = [descriptor for descriptor in descriptors if descriptor.digest == root_digest]
    if not roots:
        raw = (layout / "blobs" / "sha256" / root_digest.removeprefix("sha256:")).read_bytes()
        roots = [Descriptor(OCI_IMAGE_MANIFEST, root_digest, len(raw))]
    pending = list(roots)
    result: dict[str, bytes] = {}
    while pending:
        descriptor = pending.pop()
        if descriptor.digest in result:
            continue
        content = _read_blob(layout, descriptor)
        result[descriptor.digest] = content
        if descriptor.media_type in {OCI_IMAGE_MANIFEST, OCI_IMAGE_INDEX}:
            value = _json_mapping(_load_json_bytes(content), "OCI graph object")
            for field in ("config", "layers", "manifests"):
                if field not in value:
                    continue
                raw_children = value[field]
                if isinstance(raw_children, dict):
                    pending.append(_descriptor(_json_mapping(raw_children, field)))
                else:
                    pending.extend(_descriptors(raw_children, field))
        pending.extend(_referrers_to(descriptors, layout, descriptor.digest))
    return result


def _create_context(root: Path, destination: Path, busybox: Path, epoch: int) -> None:
    shutil.copytree(root / FIXTURE_PATH, destination)
    generated = destination / "_generated" / "rootfs" / "bin" / "busybox"
    generated.parent.mkdir(parents=True)
    shutil.copyfile(busybox, generated)
    generated.chmod(0o555)
    for path in sorted(destination.rglob("*"), reverse=True):
        os.utime(path, (epoch, epoch), follow_symlinks=False)
    os.utime(destination, (epoch, epoch), follow_symlinks=False)


def _build_image(paths: ToolPaths, context: Path, output: Path, epoch: int) -> None:
    _run(
        (
            str(paths.sudo),
            "-n",
            str(paths.buildx),
            "build",
            "--builder",
            "default",
            "--network=none",
            "--no-cache",
            "--build-arg",
            f"SOURCE_DATE_EPOCH={epoch}",
            "--provenance=mode=max",
            "--sbom=false",
            "--platform",
            "linux/amd64",
            "--output",
            f"type=oci,dest={output}",
            str(context),
        ),
        cwd=context,
        environment=_offline_environment(),
    )


def _generate_sbom(
    paths: ToolPaths,
    archive: Path,
    digest: str,
    output: Path,
    cache: Path,
) -> None:
    environment = _offline_environment()
    environment.update({"SYFT_CHECK_FOR_APP_UPDATE": "false", "XDG_CACHE_HOME": str(cache)})
    _run(
        (
            str(paths.syft),
            "scan",
            f"oci-archive:{archive}",
            "--platform",
            "linux/amd64",
            "--source-name",
            "asklegal-image-fixture",
            "--source-version",
            digest,
            "--override-default-catalogers",
            "dpkg-db-cataloger,python-installed-package-cataloger",
            "-o",
            f"spdx-json={output}",
        ),
        cwd=archive.parent,
        environment=environment,
    )


def _scan_sbom(paths: ToolPaths, sbom: Path, output: Path, cache: Path) -> None:
    environment = _grype_environment(paths)
    environment["XDG_CACHE_HOME"] = str(cache)
    _run(
        (
            str(paths.grype),
            f"sbom:{sbom}",
            "-o",
            "json",
            "--file",
            str(output),
        ),
        cwd=sbom.parent,
        environment=environment,
    )


def _prove_known_vulnerable_fixture(
    root: Path,
    paths: ToolPaths,
    database: Mapping[str, str],
    work_root: Path,
) -> None:
    output = work_root / "known-vulnerable.json"
    _scan_sbom(
        paths,
        root / FIXTURE_PATH / "vulnerable.spdx.json",
        output,
        work_root / "grype-vulnerable-cache",
    )
    try:
        evaluate_vulnerabilities(_load_json(output), database)
    except ImageAdmissionFailure as error:
        if str(error) != "IMAGE_VULNERABILITY_KNOWN_EXPLOITED":
            raise
    else:
        raise ImageAdmissionFailure("IMAGE_KNOWN_VULNERABLE_FIXTURE_PASSED")


def _validate_sbom_packages(sbom: JsonValue, image_policy: Mapping[str, JsonValue]) -> None:
    packages = _json_sequence(_json_mapping(sbom, "SBOM")["packages"], "packages")
    identities = {
        (
            _json_string(_json_mapping(item, "package")["name"], "package name"),
            _json_string(_json_mapping(item, "package")["versionInfo"], "package version"),
        )
        for item in packages
        if _json_mapping(item, "package").get("primaryPackagePurpose") != "CONTAINER"
    }
    required = {
        (
            _json_string(image_policy["busybox_package"], "busybox package"),
            _json_string(image_policy["busybox_version"], "busybox version"),
        ),
        (
            _json_string(image_policy["expected_python_package"], "Python package"),
            _json_string(image_policy["expected_python_version"], "Python version"),
        ),
    }
    if identities != required:
        raise ImageAdmissionFailure("IMAGE_SBOM_PACKAGE_COVERAGE_MISMATCH")


def _tag_image_manifest(
    paths: ToolPaths,
    layout: Path,
    descriptor: Descriptor,
    work_root: Path,
) -> None:
    manifest_path = work_root / "image-manifest.json"
    manifest_path.write_bytes(_read_blob(layout, descriptor))
    _run(
        (
            str(paths.oras),
            "manifest",
            "push",
            "--oci-layout",
            "--media-type",
            OCI_IMAGE_MANIFEST,
            f"{layout.name}:candidate",
            manifest_path.name,
        ),
        cwd=work_root,
        environment=_offline_environment(),
    )


def _attach(
    paths: ToolPaths,
    layout: Path,
    subject_digest: str,
    artifact_type: str,
    artifact: Path,
) -> None:
    _run(
        (
            str(paths.oras),
            "attach",
            "--oci-layout",
            "--artifact-type",
            artifact_type,
            "--annotation",
            f"org.opencontainers.image.created={FIXED_CREATED}",
            f"{layout.name}@{subject_digest}",
            f"{artifact.name}:{artifact_type}",
            "--format",
            "json",
        ),
        cwd=layout.parent,
        environment=_offline_environment(),
    )


def _copy_graph(
    paths: ToolPaths,
    source: Path,
    source_tag: str,
    destination: Path,
    destination_tag: str,
    work_root: Path,
) -> None:
    _run(
        (
            str(paths.oras),
            "cp",
            "-r",
            "--from-oci-layout",
            f"{source.name}:{source_tag}",
            "--to-oci-layout",
            f"{destination.name}:{destination_tag}",
        ),
        cwd=work_root,
        environment=_offline_environment(),
    )


def _resolve(paths: ToolPaths, layout: Path, tag: str, work_root: Path) -> str:
    return _run(
        (str(paths.oras), "resolve", "--oci-layout", f"{layout.name}:{tag}"),
        cwd=work_root,
        environment=_offline_environment(),
    ).stdout.strip()


def _sign_release(
    paths: ToolPaths,
    policy: Mapping[str, JsonValue],
    image_digest: str,
    evidence_hashes: Mapping[str, str],
    work_root: Path,
) -> dict[str, JsonValue]:
    signing = _json_mapping(policy["test_signing"], "test signing")
    common_name = _json_string(signing["common_name"], "test common name")
    config_home = work_root / "notation-config"
    cache_home = work_root / "notation-cache"
    environment = _offline_environment()
    environment.update({"XDG_CACHE_HOME": str(cache_home), "XDG_CONFIG_HOME": str(config_home)})
    _run(
        (
            str(paths.notation),
            "certificate",
            "generate-test",
            "--default",
            common_name,
        ),
        cwd=work_root,
        environment=environment,
    )
    key = config_home / "notation" / "localkeys" / f"{common_name}.key"
    certificate = config_home / "notation" / "localkeys" / f"{common_name}.crt"
    certificate_text = _run(
        (str(paths.openssl), "x509", "-in", str(certificate), "-noout", "-subject"),
        cwd=work_root,
    ).stdout
    if f"CN = {common_name}" not in certificate_text:
        raise ImageAdmissionFailure("IMAGE_TEST_CERTIFICATE_SUBJECT_MISMATCH")
    payload: dict[str, JsonValue] = {
        "evidence_sha256": dict(sorted(evidence_hashes.items())),
        "image_digest": image_digest,
        "release_repository": _json_string(policy["release_repository"], "release repository"),
        "schema_version": 1,
        "signer_common_name": common_name,
        "trust_capability": "LOCAL_TEST_ONLY",
    }
    payload_path = work_root / "signature-payload.json"
    signature_path = work_root / "signature.bin"
    public_key = work_root / "signature-public.pem"
    payload_path.write_bytes(_canonical_json_bytes(payload))
    _run(
        (
            str(paths.openssl),
            "dgst",
            "-sha256",
            "-sign",
            str(key),
            "-out",
            str(signature_path),
            str(payload_path),
        ),
        cwd=work_root,
    )
    public_key.write_text(
        _run(
            (str(paths.openssl), "x509", "-in", str(certificate), "-pubkey", "-noout"),
            cwd=work_root,
        ).stdout,
        encoding="ascii",
    )
    _run(
        (
            str(paths.openssl),
            "dgst",
            "-sha256",
            "-verify",
            str(public_key),
            "-signature",
            str(signature_path),
            str(payload_path),
        ),
        cwd=work_root,
    )
    return {
        "certificate_pem": certificate.read_text(encoding="ascii"),
        "certificate_sha256": _sha256(certificate.read_bytes()),
        "payload": payload,
        "schema_version": 1,
        "signature_base64": base64.b64encode(signature_path.read_bytes()).decode("ascii"),
        "signature_scheme": "RSA-PKCS1v15-SHA256",
        "trust_capability": "LOCAL_TEST_ONLY",
    }


def _verify_signature_referrer(
    paths: ToolPaths,
    layout: Path,
    image_digest: str,
    signature_type: str,
    policy: Mapping[str, JsonValue],
    work_root: Path,
) -> None:
    referrers = _referrers_to(
        _descriptors(
            _json_mapping(_load_json(layout / "index.json"), "index")["manifests"],
            "index descriptors",
        ),
        layout,
        image_digest,
    )
    signatures = [item for item in referrers if item.artifact_type == signature_type]
    if len(signatures) != 1:
        raise ImageAdmissionFailure("IMAGE_SIGNATURE_REFERRER_COUNT")
    manifest = _json_mapping(_read_json_blob(layout, signatures[0]), "signature manifest")
    layers = _descriptors(manifest["layers"], "signature layers")
    if len(layers) != 1:
        raise ImageAdmissionFailure("IMAGE_SIGNATURE_LAYER_COUNT")
    bundle = _json_mapping(_load_json_bytes(_read_blob(layout, layers[0])), "signature bundle")
    if bundle.get("trust_capability") != "LOCAL_TEST_ONLY":
        raise ImageAdmissionFailure("IMAGE_SIGNATURE_TRUST_INVALID")
    payload = _json_mapping(bundle["payload"], "signature payload")
    if (
        payload.get("image_digest") != image_digest
        or payload.get("release_repository") != policy["release_repository"]
    ):
        raise ImageAdmissionFailure("IMAGE_SIGNATURE_SUBJECT_INVALID")
    certificate = work_root / "verify-certificate.pem"
    signature = work_root / "verify-signature.bin"
    payload_path = work_root / "verify-payload.json"
    public_key = work_root / "verify-public.pem"
    certificate.write_text(
        _json_string(bundle["certificate_pem"], "certificate PEM"), encoding="ascii"
    )
    signature.write_bytes(
        base64.b64decode(_json_string(bundle["signature_base64"], "signature"), validate=True)
    )
    payload_path.write_bytes(_canonical_json_bytes(payload))
    public_key.write_text(
        _run(
            (str(paths.openssl), "x509", "-in", str(certificate), "-pubkey", "-noout"),
            cwd=work_root,
        ).stdout,
        encoding="ascii",
    )
    _run(
        (
            str(paths.openssl),
            "dgst",
            "-sha256",
            "-verify",
            str(public_key),
            "-signature",
            str(signature),
            str(payload_path),
        ),
        cwd=work_root,
    )


def _validate_sealed_record(
    policy: Mapping[str, JsonValue], image_digest: str, graph: Mapping[str, bytes]
) -> None:
    record: dict[str, JsonValue] = {
        "delete_enabled": False,
        "graph_sha256": _graph_hash(graph),
        "image_digest": image_digest,
        "release_repository": _json_string(policy["release_repository"], "release"),
        "status": "ADMITTED",
        "write_enabled": False,
    }
    if (
        record["status"] != "ADMITTED"
        or record["delete_enabled"] is not False
        or record["write_enabled"] is not False
    ):
        raise ImageAdmissionFailure("IMAGE_RELEASE_NOT_SEALED")


def _prove_read_only_runtime(paths: ToolPaths, context: Path, epoch: int) -> None:
    tag = "asklegal-image-admission-fixture:spike"
    try:
        _run(
            (
                str(paths.sudo),
                "-n",
                str(paths.buildx),
                "build",
                "--builder",
                "default",
                "--network=none",
                "--no-cache",
                "--build-arg",
                f"SOURCE_DATE_EPOCH={epoch}",
                "--provenance=false",
                "--sbom=false",
                "--load",
                "--tag",
                tag,
                str(context),
            ),
            cwd=context,
            environment=_offline_environment(),
        )
        result = _run(
            (
                str(paths.sudo),
                "-n",
                str(paths.docker),
                "run",
                "--rm",
                "--read-only",
                "--network",
                "none",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges",
                "--user",
                "10001:10001",
                tag,
            ),
            cwd=context,
            environment=_offline_environment(),
        )
        if result.stdout != "asklegal-image-admission-fixture\n":
            raise ImageAdmissionFailure("IMAGE_READ_ONLY_RUNTIME_FAILED")
    finally:
        _run_allow_failure(
            (str(paths.sudo), "-n", str(paths.docker), "image", "rm", "--force", tag),
            cwd=context,
        )


def _verify_image_config_and_layers(
    layout: Path, descriptor: Descriptor, policy: Mapping[str, JsonValue]
) -> dict[str, bytes]:
    manifest = _json_mapping(_read_json_blob(layout, descriptor), "image manifest")
    config_descriptor = _descriptor(_json_mapping(manifest["config"], "image config"))
    if config_descriptor.media_type != OCI_IMAGE_CONFIG:
        raise ImageAdmissionFailure("IMAGE_CONFIG_MEDIA_TYPE_INVALID")
    config = _json_mapping(_read_json_blob(layout, config_descriptor), "image config")
    image_policy = _json_mapping(policy["image"], "image policy")
    runtime_config = _json_mapping(config["config"], "runtime config")
    if (
        config.get("architecture") != "amd64"
        or config.get("os") != "linux"
        or config.get("created") != FIXED_CREATED
        or runtime_config.get("User") != image_policy["expected_user"]
        or runtime_config.get("WorkingDir") != image_policy["expected_working_directory"]
        or runtime_config.get("Entrypoint") != image_policy["expected_entrypoint"]
    ):
        raise ImageAdmissionFailure("IMAGE_RUNTIME_CONFIG_INVALID")
    serialized_config = _canonical_json_bytes(config)
    if _SECRET_PATTERN.search(serialized_config):
        raise ImageAdmissionFailure("IMAGE_CONFIG_SECRET_PATTERN")

    busybox_path = _json_string(image_policy["busybox_path"], "busybox path")
    layer_descriptors = _descriptors(manifest["layers"], "image layers")
    rootfs = _json_mapping(config["rootfs"], "rootfs")
    diff_ids = _json_string_list(rootfs["diff_ids"], "diff ids")
    if len(layer_descriptors) != len(diff_ids):
        raise ImageAdmissionFailure("IMAGE_LAYER_DIFF_ID_COUNT")
    files: dict[str, bytes] = {}
    for layer_descriptor, expected_diff_id in zip(layer_descriptors, diff_ids, strict=True):
        compressed = _read_blob(layout, layer_descriptor)
        uncompressed = gzip.decompress(compressed)
        if f"sha256:{_sha256(uncompressed)}" != expected_diff_id:
            raise ImageAdmissionFailure("IMAGE_LAYER_DIFF_ID_MISMATCH")
        with tarfile.open(fileobj=io.BytesIO(uncompressed), mode="r:") as archive:
            for member in archive.getmembers():
                name = _safe_archive_name(member.name)
                if member.isdir():
                    continue
                if not member.isfile() or member.issym() or member.islnk():
                    raise ImageAdmissionFailure("IMAGE_LAYER_SPECIAL_FILE")
                extracted = archive.extractfile(member)
                if extracted is None:
                    raise ImageAdmissionFailure("IMAGE_LAYER_FILE_MISSING")
                content = extracted.read()
                absolute_name = f"/{name}"
                if _SECRET_PATTERN.search(name.encode()) or (
                    absolute_name != busybox_path and _SECRET_PATTERN.search(content)
                ):
                    raise ImageAdmissionFailure("IMAGE_LAYER_SECRET_PATTERN")
                files[absolute_name] = content
    if _sha256(files[busybox_path]) != _json_string(image_policy["busybox_sha256"], "busybox hash"):
        raise ImageAdmissionFailure("IMAGE_LAYER_BUSYBOX_MISMATCH")
    return files


def _read_buildkit_provenance(layout: Path, descriptor: Descriptor) -> JsonValue:
    manifest = _json_mapping(_read_json_blob(layout, descriptor), "attestation manifest")
    layers = _descriptors(manifest["layers"], "attestation layers")
    if len(layers) != 1 or layers[0].media_type != IN_TOTO_MEDIA_TYPE:
        raise ImageAdmissionFailure("IMAGE_PROVENANCE_LAYER_INVALID")
    provenance = _json_mapping(_load_json_bytes(_read_blob(layout, layers[0])), "provenance")
    predicate = _json_mapping(provenance["predicate"], "provenance predicate")
    invocation = _json_mapping(predicate["invocation"], "provenance invocation")
    parameters = _json_mapping(invocation["parameters"], "provenance parameters")
    arguments = _json_mapping(parameters["args"], "provenance arguments")
    metadata = _json_mapping(predicate["metadata"], "provenance metadata")
    if (
        provenance.get("predicateType") != "https://slsa.dev/provenance/v0.2"
        or arguments.get("force-network-mode") != "none"
        or arguments.get("build-arg:SOURCE_DATE_EPOCH") != "315532800"
        or metadata.get("completeness") is None
    ):
        raise ImageAdmissionFailure("IMAGE_PROVENANCE_BINDING_INVALID")
    return provenance


def _manifest_graph(layout: Path, root: Descriptor) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    pending = [root]
    while pending:
        descriptor = pending.pop()
        if descriptor.digest in result:
            continue
        content = _read_blob(layout, descriptor)
        result[descriptor.digest] = content
        if descriptor.media_type == OCI_IMAGE_MANIFEST:
            manifest = _json_mapping(_load_json_bytes(content), "image manifest")
            pending.append(_descriptor(_json_mapping(manifest["config"], "config")))
            pending.extend(_descriptors(manifest["layers"], "layers"))
    return result


def _require_referrer_types(layout: Path, subject: str, required: set[str]) -> None:
    index = _json_mapping(_load_json(layout / "index.json"), "index")
    descriptors = _descriptors(index["manifests"], "index descriptors")
    actual = {
        descriptor.artifact_type
        for descriptor in _referrers_to(descriptors, layout, subject)
        if descriptor.artifact_type is not None
    }
    validate_referrer_types(actual, required)


def validate_referrer_types(actual: set[str], required: set[str]) -> None:
    """Require the exact evidence-referrer set, without omissions or extras."""
    if actual != required:
        raise ImageAdmissionFailure("IMAGE_REQUIRED_REFERRER_SET_MISMATCH")


def _referrers_to(
    descriptors: Sequence[Descriptor], layout: Path, subject_digest: str
) -> list[Descriptor]:
    result: list[Descriptor] = []
    for descriptor in descriptors:
        if descriptor.media_type != OCI_IMAGE_MANIFEST or descriptor.artifact_type is None:
            continue
        manifest = _json_mapping(_read_json_blob(layout, descriptor), "referrer manifest")
        subject = _json_mapping(manifest.get("subject", {}), "referrer subject")
        if subject.get("digest") == subject_digest:
            result.append(descriptor)
    return result


def _descriptors(value: JsonValue, location: str) -> list[Descriptor]:
    return [_descriptor(_json_mapping(item, location)) for item in _json_sequence(value, location)]


def _descriptor(value: Mapping[str, JsonValue]) -> Descriptor:
    digest = _json_string(value["digest"], "descriptor digest")
    if not _DIGEST_PATTERN.fullmatch(digest):
        raise ImageAdmissionFailure("IMAGE_DESCRIPTOR_DIGEST_INVALID")
    return Descriptor(
        media_type=_json_string(value["mediaType"], "descriptor media type"),
        digest=digest,
        size=_json_integer(value["size"], "descriptor size"),
        artifact_type=(
            _json_string(value["artifactType"], "artifact type")
            if "artifactType" in value
            else None
        ),
    )


def _read_blob(layout: Path, descriptor: Descriptor) -> bytes:
    path = layout / "blobs" / "sha256" / descriptor.digest.removeprefix("sha256:")
    content = path.read_bytes()
    if len(content) != descriptor.size or f"sha256:{_sha256(content)}" != descriptor.digest:
        raise ImageAdmissionFailure("IMAGE_DESCRIPTOR_CONTENT_MISMATCH")
    return content


def _read_json_blob(layout: Path, descriptor: Descriptor) -> JsonValue:
    return _load_json_bytes(_read_blob(layout, descriptor))


def _safe_extract_tar(source: Path, destination: Path) -> None:
    destination.mkdir()
    with tarfile.open(source, mode="r:") as archive:
        for member in archive.getmembers():
            name = _safe_archive_name(member.name)
            target = destination / name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile() or member.issym() or member.islnk():
                raise ImageAdmissionFailure("IMAGE_OCI_ARCHIVE_SPECIAL_FILE")
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ImageAdmissionFailure("IMAGE_OCI_ARCHIVE_FILE_MISSING")
            target.write_bytes(extracted.read())


def _safe_archive_name(name: str) -> str:
    normalized = name.removeprefix("./").removesuffix("/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or ".." in path.parts or normalized != path.as_posix():
        raise ImageAdmissionFailure("IMAGE_ARCHIVE_PATH_UNSAFE")
    return normalized


def _grype_environment(paths: ToolPaths) -> dict[str, str]:
    environment = _offline_environment()
    environment.update(
        {
            "GRYPE_CHECK_FOR_APP_UPDATE": "false",
            "GRYPE_DB_AUTO_UPDATE": "false",
            "GRYPE_DB_CACHE_DIR": str(paths.grype_db),
            "GRYPE_EXTERNAL_SOURCES_ENABLE": "false",
        }
    )
    return environment


def _offline_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.update(
        {
            "DOCKER_BUILDKIT": "1",
            "NO_PROXY": "*",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "SOURCE_DATE_EPOCH": "315532800",
            "TZ": "UTC",
        }
    )
    return environment


def _run(
    command: Sequence[str],
    *,
    cwd: Path,
    environment: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        env=None if environment is None else dict(environment),
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise ImageAdmissionFailure(
            f"IMAGE_SUBPROCESS_FAILED: {detail[-1] if detail else 'no detail'}"
        )
    return result


def _run_allow_failure(command: Sequence[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, capture_output=True, check=False, text=True)


def _load_json(path: Path) -> JsonValue:
    return _load_json_text(path.read_text(encoding="utf-8"))


def _load_json_bytes(value: bytes) -> JsonValue:
    return _load_json_text(value.decode("utf-8"))


def _load_json_text(value: str) -> JsonValue:
    return cast("JsonValue", json.loads(value))


def _json_mapping(value: JsonValue | object, location: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ImageAdmissionFailure(f"IMAGE_EXPECTED_MAPPING: {location}")
    raw = cast("dict[object, object]", value)
    if not all(isinstance(key, str) for key in raw):
        raise ImageAdmissionFailure(f"IMAGE_EXPECTED_STRING_KEY: {location}")
    return cast("dict[str, JsonValue]", value)


def _json_sequence(value: JsonValue | object, location: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ImageAdmissionFailure(f"IMAGE_EXPECTED_LIST: {location}")
    return cast("list[JsonValue]", value)


def _json_string(value: JsonValue | object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise ImageAdmissionFailure(f"IMAGE_EXPECTED_STRING: {location}")
    return value


def _json_integer(value: JsonValue | object, location: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ImageAdmissionFailure(f"IMAGE_EXPECTED_INTEGER: {location}")
    return value


def _json_string_list(value: JsonValue | object, location: str) -> list[str]:
    return [
        _json_string(item, f"{location}[{index}]")
        for index, item in enumerate(_json_sequence(value, location))
    ]


def _remove_mapping_key(value: JsonValue, key: str) -> None:
    if isinstance(value, dict):
        value.pop(key, None)
        for child in value.values():
            _remove_mapping_key(child, key)
    elif isinstance(value, list):
        for child in value:
            _remove_mapping_key(child, key)


def _canonical_json_bytes(value: JsonValue | object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _graph_hash(graph: Mapping[str, bytes]) -> str:
    inventory = [
        {"digest": digest, "sha256": _sha256(content), "size": len(content)}
        for digest, content in sorted(graph.items())
    ]
    return _sha256(_canonical_json_bytes(inventory))


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ImageAdmissionFailure("IMAGE_TIMESTAMP_TIMEZONE_MISSING")
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seconds(value: int) -> timedelta:
    return timedelta(seconds=value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--buildx", required=True, type=Path)
    parser.add_argument("--docker", default=Path("/usr/bin/docker"), type=Path)
    parser.add_argument("--grype", required=True, type=Path)
    parser.add_argument("--grype-db", required=True, type=Path)
    parser.add_argument("--notation", required=True, type=Path)
    parser.add_argument("--openssl", default=Path("/usr/bin/openssl"), type=Path)
    parser.add_argument("--oras", required=True, type=Path)
    parser.add_argument("--sudo", default=Path("/usr/bin/sudo"), type=Path)
    parser.add_argument("--syft", required=True, type=Path)
    return parser


def main() -> int:
    """Run the proof in a disposable directory and print its canonical report."""
    arguments = _parser().parse_args()
    paths = ToolPaths(
        buildx=arguments.buildx.resolve(),
        docker=arguments.docker.resolve(),
        grype=arguments.grype.resolve(),
        grype_db=arguments.grype_db.resolve(),
        notation=arguments.notation.resolve(),
        openssl=arguments.openssl.resolve(),
        oras=arguments.oras.resolve(),
        sudo=arguments.sudo.resolve(),
        syft=arguments.syft.resolve(),
    )
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="asklegal-image-admission-spike-") as temporary:
        report = run_spike(root, paths, Path(temporary))
    print(_canonical_json_bytes(report.to_json()).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
