"""Fail-closed V1 POC application-image input and runtime-readiness contract."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

APPLICATION_IMAGE_POLICY_PATH = Path("infrastructure/poc/application_image_inputs.json")
ARTIFACT_POLICY_PATH = Path("infrastructure/poc/artifact_admission.json")
PACKAGE_POLICY_PATH = Path("tools/package_spike_manifest.json")
TOPOLOGY_PATH = Path("infrastructure/poc/topology.json")
_MAX_DOCUMENT_BYTES = 1_000_000
_SOURCE_DATE_EPOCH = 315_532_800
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SECRET_VALUE = re.compile(r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)")
_DOCUMENT_KEYS = frozenset(
    {
        "authority",
        "base_image",
        "images",
        "input_locks",
        "python_version",
        "required_blockers",
        "schema_version",
        "security_profile",
        "source_date_epoch",
        "status",
        "target_platform",
    }
)
_IMAGE_KEYS = frozenset(
    {
        "admitted",
        "application_path",
        "artifact_id",
        "artifact_ref",
        "check_command",
        "console_script",
        "distribution",
        "module",
        "oci_build_definition_state",
        "runtime_command",
        "runtime_entrypoint_state",
        "third_party_wheelhouse_state",
        "topology_identity",
        "topology_listener_ports",
        "workspace_distribution_closure",
    }
)
_INPUT_PATHS = (
    ".python-version",
    "pyproject.toml",
    "tools/package_spike_manifest.json",
    "uv.lock",
)
_BLOCKERS = (
    "BASE_IMAGE_DIGEST",
    "THIRD_PARTY_WHEELHOUSE",
    "OCI_BUILD_DEFINITION",
    "RUNTIME_CONFIGURATION_ADAPTER",
    "UBUNTU_24_04_X86_64_OCI_PROOF",
)
_APPLICATIONS = frozenset(
    {
        "acquisition-worker",
        "control-plane",
        "legal-processing-worker",
        "promotion-worker",
        "review-api",
    }
)


class ApplicationImageCode(StrEnum):
    """Stable application-image contract failure codes."""

    ADMISSION = "ADMISSION"
    AUTHORITY = "AUTHORITY"
    BLOCKER = "BLOCKER"
    COVERAGE = "COVERAGE"
    INPUT = "INPUT"
    INVENTORY = "INVENTORY"
    PACKAGE = "PACKAGE"
    RUNTIME = "RUNTIME"
    SECRET = "SECRET"
    TOPOLOGY = "TOPOLOGY"


@dataclass(frozen=True, slots=True)
class ApplicationImageFinding:
    """One exact build-input or runtime-readiness mismatch."""

    code: ApplicationImageCode
    detail: str


@dataclass(frozen=True, slots=True)
class ApplicationImageReport:
    """One valid but deliberately blocked application-image summary."""

    images: int
    workspace_distributions: int
    blockers: tuple[str, ...]
    admitted: int


def _read_object(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES:
        message = f"application image document too large: {path}"
        raise ValueError(message)
    value = json.loads(raw)
    if not isinstance(value, dict):
        message = f"application image document root: {path}"
        raise TypeError(message)
    return value


def _objects(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        message = "application image object list"
        raise TypeError(message)
    return tuple(item for item in value if isinstance(item, dict))


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(type(item) is str and item for item in value):
        message = "application image string list"
        raise TypeError(message)
    return tuple(item for item in value if isinstance(item, str))


def _has_secret(value: object) -> bool:
    if isinstance(value, dict):
        forbidden = {"api_key", "password", "private_key", "secret", "token"}
        return any(key.lower() in forbidden or _has_secret(child) for key, child in value.items())
    if isinstance(value, list):
        return any(_has_secret(child) for child in value)
    return isinstance(value, str) and _SECRET_VALUE.search(value) is not None


def _by_id(items: tuple[dict[str, object], ...], field: str) -> dict[str, dict[str, object]]:
    return {value: item for item in items if type(value := item.get(field)) is str}


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _validate_document(policy: dict[str, object], root: Path) -> list[ApplicationImageFinding]:
    findings: list[ApplicationImageFinding] = []
    if (
        frozenset(policy) != _DOCUMENT_KEYS
        or policy.get("schema_version") != 1
        or policy.get("status") != "DESIGN_ONLY_DISABLED"
        or policy.get("target_platform") != "linux/amd64"
        or policy.get("python_version") != "3.14.7"
        or policy.get("source_date_epoch") != _SOURCE_DATE_EPOCH
    ):
        findings.append(ApplicationImageFinding(ApplicationImageCode.INVENTORY, "document"))
    if _has_secret(policy):
        findings.append(ApplicationImageFinding(ApplicationImageCode.SECRET, "policy"))
    if policy.get("authority") != {
        "image_build_authorized": False,
        "registry_pull_authorized": False,
        "registry_push_authorized": False,
        "service_enablement_authorized": False,
    }:
        findings.append(ApplicationImageFinding(ApplicationImageCode.AUTHORITY, "policy"))
    if policy.get("base_image") != {
        "selection_state": "PYTHON_3_14_7_LINUX_AMD64_DIGEST_REQUIRED",
        "artifact_ref": None,
    }:
        findings.append(ApplicationImageFinding(ApplicationImageCode.BLOCKER, "base image"))
    if tuple(policy.get("required_blockers", ())) != _BLOCKERS:
        findings.append(ApplicationImageFinding(ApplicationImageCode.BLOCKER, "inventory"))
    if policy.get("security_profile") != {
        "non_root_required": True,
        "read_only_root_filesystem_required": True,
        "no_new_privileges_required": True,
        "drop_all_linux_capabilities_required": True,
        "secret_environment_forbidden": True,
        "secret_arguments_forbidden": True,
        "network_during_build_forbidden": True,
    }:
        findings.append(ApplicationImageFinding(ApplicationImageCode.RUNTIME, "security profile"))
    locks = policy.get("input_locks")
    if not isinstance(locks, dict) or tuple(locks) != _INPUT_PATHS:
        findings.append(ApplicationImageFinding(ApplicationImageCode.INPUT, "lock inventory"))
    else:
        for relative in _INPUT_PATHS:
            declared = locks.get(relative)
            if (
                not isinstance(declared, str)
                or _SHA256.fullmatch(declared) is None
                or declared != _sha256(root / relative)
            ):
                findings.append(ApplicationImageFinding(ApplicationImageCode.INPUT, relative))
    return findings


def _validate_image(
    image: dict[str, object],
    package_member: dict[str, object] | None,
    artifact: dict[str, object] | None,
    service: dict[str, object] | None,
    root: Path,
) -> tuple[ApplicationImageFinding, ...]:
    artifact_id = image.get("artifact_id")
    label = artifact_id if isinstance(artifact_id, str) else "unknown"
    findings: list[ApplicationImageFinding] = []
    if frozenset(image) != _IMAGE_KEYS:
        findings.append(ApplicationImageFinding(ApplicationImageCode.INVENTORY, f"{label} schema"))
    if (
        image.get("runtime_command") is not None
        or image.get("runtime_entrypoint_state") != "ADAPTER_REQUIRED"
        or image.get("third_party_wheelhouse_state") != "REQUIRED"
        or image.get("oci_build_definition_state") != "REQUIRED"
    ):
        findings.append(ApplicationImageFinding(ApplicationImageCode.RUNTIME, label))
    if image.get("admitted") is not False or image.get("artifact_ref") is not None:
        findings.append(ApplicationImageFinding(ApplicationImageCode.ADMISSION, label))
    console_script = image.get("console_script")
    if image.get("check_command") != [console_script, "--check"]:
        findings.append(ApplicationImageFinding(ApplicationImageCode.RUNTIME, f"{label} check"))
    if package_member is None or (
        image.get("application_path") != package_member.get("path")
        or image.get("distribution") != package_member.get("distribution")
        or image.get("module") != package_member.get("module")
        or image.get("workspace_distribution_closure")
        != package_member.get("allowed_workspace_distributions")
    ):
        findings.append(ApplicationImageFinding(ApplicationImageCode.PACKAGE, label))
    else:
        pyproject = tomllib.loads(
            (root / str(image["application_path"]) / "pyproject.toml").read_text(encoding="utf-8")
        )
        scripts = pyproject.get("project", {}).get("scripts", {})
        if not isinstance(scripts, dict) or console_script not in scripts:
            findings.append(
                ApplicationImageFinding(ApplicationImageCode.PACKAGE, f"{label} script")
            )
    if artifact != {
        "artifact_id": label,
        "kind": "REPOSITORY_IMAGE",
        "consumers": [label],
        "selection_state": "REPRODUCIBLE_BUILD_REQUIRED",
        "artifact_ref": None,
        "admitted": False,
        "credential_interface_gate": False,
    }:
        findings.append(ApplicationImageFinding(ApplicationImageCode.COVERAGE, f"{label} artifact"))
    listeners = service.get("listeners") if service is not None else None
    listener_ports = (
        [item.get("port") for item in listeners if isinstance(item, dict)]
        if isinstance(listeners, list)
        else None
    )
    if service is None or (
        service.get("kind") != "REPOSITORY_IMAGE"
        or service.get("identity") != image.get("topology_identity")
        or listener_ports != image.get("topology_listener_ports")
        or service.get("enabled") is not False
    ):
        findings.append(ApplicationImageFinding(ApplicationImageCode.TOPOLOGY, label))
    return tuple(findings)


def validate_application_image_policy(
    policy: dict[str, object],
    package_policy: dict[str, object],
    artifact_policy: dict[str, object],
    topology: dict[str, object],
    root: Path,
) -> tuple[ApplicationImageFinding, ...]:
    """Return all drift; empty proves only a disabled build-input contract."""
    findings = _validate_document(policy, root)
    images = _objects(policy.get("images"))
    image_ids = tuple(image.get("artifact_id") for image in images)
    if len(image_ids) != len(set(image_ids)) or frozenset(image_ids) != _APPLICATIONS:
        findings.append(ApplicationImageFinding(ApplicationImageCode.COVERAGE, "image ids"))
    members = _by_id(_objects(package_policy.get("members")), "distribution")
    artifacts = _by_id(_objects(artifact_policy.get("artifacts")), "artifact_id")
    services = _by_id(_objects(topology.get("services")), "service_id")
    for image in images:
        distribution = image.get("distribution")
        artifact_id = image.get("artifact_id")
        findings.extend(
            _validate_image(
                image,
                members.get(distribution) if isinstance(distribution, str) else None,
                artifacts.get(artifact_id) if isinstance(artifact_id, str) else None,
                services.get(artifact_id) if isinstance(artifact_id, str) else None,
                root,
            )
        )
    return tuple(findings)


def check_application_image_policy(root: Path) -> ApplicationImageReport:
    """Validate the frozen application-image inputs and explicit blockers."""
    policy = _read_object(root / APPLICATION_IMAGE_POLICY_PATH)
    findings = validate_application_image_policy(
        policy,
        _read_object(root / PACKAGE_POLICY_PATH),
        _read_object(root / ARTIFACT_POLICY_PATH),
        _read_object(root / TOPOLOGY_PATH),
        root,
    )
    if findings:
        detail = ", ".join(f"{item.code.value}:{item.detail}" for item in findings)
        raise ValueError(detail)
    images = _objects(policy["images"])
    closures = {
        item for image in images for item in _strings(image["workspace_distribution_closure"])
    }
    return ApplicationImageReport(
        images=len(images),
        workspace_distributions=len(closures),
        blockers=_BLOCKERS,
        admitted=sum(image.get("admitted") is True for image in images),
    )


def main() -> None:
    """Run the disabled application-image contract gate."""
    root = Path(__file__).resolve().parents[1]
    report = check_application_image_policy(root)
    print(  # noqa: T201
        "PASS V1 POC application-image inputs; NOT_READY: "
        f"{report.images} images, {len(report.blockers)} blockers, admitted={report.admitted}"
    )


if __name__ == "__main__":
    main()
