"""Fail-closed V1 POC application-image input and runtime-readiness contract."""

from __future__ import annotations

import hashlib
import json
import re
import tomllib
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

APPLICATION_IMAGE_POLICY_PATH = Path("infrastructure/poc/application_image_inputs.json")
ARTIFACT_POLICY_PATH = Path("infrastructure/poc/artifact_admission.json")
PACKAGE_POLICY_PATH = Path("tools/package_spike_manifest.json")
TOPOLOGY_PATH = Path("infrastructure/poc/topology.json")
LOCAL_OCI_PROOF_PATH = Path("var/hk-v1/host/application-image-oci-proof.json")
_MAX_DOCUMENT_BYTES = 1_000_000
_SOURCE_DATE_EPOCH = 315_532_800
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SECRET_VALUE = re.compile(r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)")
_DOCUMENT_KEYS = frozenset(
    {
        "authority",
        "base_image",
        "build_definition",
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
        "installed_tree_sha256",
        "runtime_command",
        "runtime_entrypoint_state",
        "runtime_uid",
        "third_party_wheelhouse_state",
        "topology_identity",
        "topology_listener_ports",
        "workspace_distribution_closure",
    }
)
_INPUT_PATHS = (
    ".python-version",
    "infrastructure/poc/libexec/asklegal-vault-application-rotation-network",
    "infrastructure/poc/patchright_runtime_inputs.json",
    "infrastructure/poc/patchright_runtime_system_packages.json",
    "pyproject.toml",
    "tools/package_spike_manifest.json",
    "uv.lock",
)
_BASE_IMAGE_REF = (
    "docker.io/library/python@sha256:"
    "d6e0850f13fda0e2305d4c3c1c2f7930fe1042d34ddd958e49bba6ef685d0bb2"
)
_POLICY_BLOCKERS = ("UBUNTU_24_04_X86_64_OCI_PROOF",)
_PATCHRIGHT_CLOSURE_BLOCKER = "ACQUISITION_PATCHRIGHT_DEBIAN_SYSTEM_PACKAGE_CLOSURE_REQUIRED"
_BUILD_DEFINITION = {
    "dockerfile": "infrastructure/poc/images/Dockerfile",
    "build_tool": "tools/v1_poc_build_images.py",
    "network_during_build": "DISABLED",
    "reproducibility_measure": "INSTALLED_TREE_CONTENT_DIGEST",
    "reproducibility_state": "TWO_BUILDS_CONTENT_IDENTICAL",
    "image_id_stability": "NOT_CLAIMED",
    "image_id_reason": (
        "Docker embeds a creation timestamp in the image config, so image ids differ "
        "between builds while the installed tree is byte-identical. Content is the "
        "honest measure; image id is not claimed to be reproducible."
    ),
}
_TREE_DIGEST_LENGTH = 128
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
    value: object = json.loads(raw)
    document = _string_object(value)
    if document is None:
        message = f"application image document root: {path}"
        raise TypeError(message)
    return document


def _objects(value: object) -> tuple[dict[str, object], ...]:
    items = _object_list(value)
    if items is None:
        message = "application image object list"
        raise TypeError(message)
    result: list[dict[str, object]] = []
    for item in items:
        document = _string_object(item)
        if document is None:
            message = "application image object list"
            raise TypeError(message)
        result.append(document)
    return tuple(result)


def _strings(value: object) -> tuple[str, ...]:
    items = _object_list(value)
    if items is None:
        message = "application image string list"
        raise TypeError(message)
    result: list[str] = []
    for item in items:
        if type(item) is not str or not item:
            message = "application image string list"
            raise TypeError(message)
        result.append(item)
    return tuple(result)


def _string_object(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    candidate = cast("dict[object, object]", value)
    if not all(type(key) is str for key in candidate):
        return None
    return cast("dict[str, object]", candidate)


def _object_list(value: object) -> list[object] | None:
    if not isinstance(value, list):
        return None
    return cast("list[object]", value)


def _strings_or_empty(value: object) -> tuple[str, ...]:
    try:
        return _strings(value)
    except TypeError:
        return ()


def _has_secret(value: object) -> bool:
    document = _string_object(value)
    items = _object_list(value)
    if document is not None:
        forbidden = {"api_key", "password", "private_key", "secret", "token"}
        return any(
            key.lower() in forbidden or _has_secret(child) for key, child in document.items()
        )
    if items is not None:
        return any(_has_secret(child) for child in items)
    return isinstance(value, str) and _SECRET_VALUE.search(value) is not None


def _by_id(items: tuple[dict[str, object], ...], field: str) -> dict[str, dict[str, object]]:
    return {value: item for item in items if type(value := item.get(field)) is str}


def _sha256(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _validate_build_blockers(policy: dict[str, object]) -> tuple[ApplicationImageFinding, ...]:
    """Require the exact offline build definition and the remaining blocker inventory."""
    findings: list[ApplicationImageFinding] = []
    if policy.get("build_definition") != _BUILD_DEFINITION:
        findings.append(ApplicationImageFinding(ApplicationImageCode.BLOCKER, "build definition"))
    if _strings_or_empty(policy.get("required_blockers")) != _POLICY_BLOCKERS:
        findings.append(ApplicationImageFinding(ApplicationImageCode.BLOCKER, "inventory"))
    return tuple(findings)


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
        "selection_state": "DIGEST_PINNED",
        "artifact_ref": _BASE_IMAGE_REF,
        "distribution": "Debian GNU/Linux 13 (trixie)",
        "interpreter": "CPython 3.14.7",
        "libc": "glibc 2.41",
    }:
        findings.append(ApplicationImageFinding(ApplicationImageCode.BLOCKER, "base image"))
    findings.extend(_validate_build_blockers(policy))
    if policy.get("security_profile") != {
        "non_root_required": True,
        "read_only_root_filesystem_required": True,
        "no_new_privileges_required": True,
        "drop_all_linux_capabilities_required": True,
        "secret_environment_forbidden": False,
        "secret_arguments_forbidden": True,
        "network_during_build_forbidden": True,
    }:
        findings.append(ApplicationImageFinding(ApplicationImageCode.RUNTIME, "security profile"))
    locks = _string_object(policy.get("input_locks"))
    if locks is None or tuple(locks) != _INPUT_PATHS:
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


def _listener_ports(service: dict[str, object] | None) -> list[object] | None:
    listeners = service.get("listeners") if service is not None else None
    try:
        listener_items = _objects(listeners)
    except TypeError:
        return None
    return [item.get("port") for item in listener_items]


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
        image.get("runtime_command") != [image.get("console_script"), "--serve"]
        or image.get("runtime_entrypoint_state") != "IMPLEMENTED"
        or image.get("third_party_wheelhouse_state") != "LOCKED"
        or image.get("oci_build_definition_state") != "IMPLEMENTED"
        or type(image.get("runtime_uid")) is not int
        or not isinstance(image.get("installed_tree_sha256"), str)
        or len(str(image.get("installed_tree_sha256"))) != _TREE_DIGEST_LENGTH
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
    listener_ports = _listener_ports(service)
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
    image_ids = tuple(
        image_id for image in images if isinstance((image_id := image.get("artifact_id")), str)
    )
    if (
        len(image_ids) != len(images)
        or len(image_ids) != len(set(image_ids))
        or frozenset(image_ids) != _APPLICATIONS
    ):
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


def check_application_image_policy(
    root: Path,
    oci_proof_path: Path | None = LOCAL_OCI_PROOF_PATH,
) -> ApplicationImageReport:
    """Validate frozen image inputs and discharge only a measured local OCI proof."""
    from tools.v1_poc_patchright_runtime import (  # noqa: PLC0415
        PatchrightRuntimeError,
        verify_build_inputs,
    )

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
    blockers: list[str] = list(_POLICY_BLOCKERS)
    if oci_proof_path is not None and (root / oci_proof_path).is_file():
        from tools.v1_poc_application_image_oci_proof import (  # noqa: PLC0415
            check_local_oci_proof,
        )

        check_local_oci_proof(root, root / oci_proof_path)
        blockers.remove("UBUNTU_24_04_X86_64_OCI_PROOF")
    try:
        verify_build_inputs(root)
    except PatchrightRuntimeError:
        blockers.append(_PATCHRIGHT_CLOSURE_BLOCKER)
    return ApplicationImageReport(
        images=len(images),
        workspace_distributions=len(closures),
        blockers=tuple(blockers),
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
