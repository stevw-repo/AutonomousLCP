"""Measure and verify the local Ubuntu/amd64 Docker proof for five V1 images.

This is deliberately a local build/runtime proof, not an Image Admission Record.
It performs read-only Docker inspection and never pulls, runs, tags, or pushes an
image. The retained document binds exact host facts, current source-bound build
results, the pinned base configuration/layers, and each local image configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
from pathlib import Path
from typing import cast

from tools.v1_poc_build_images import workspace_source_fingerprint

APPLICATION_IMAGE_INPUTS_PATH = Path("infrastructure/poc/application_image_inputs.json")
APPLICATION_BUILD_RESULTS_PATH = Path("var/hk-v1/host/application-build-results.json")
HOST_FACTS_PATH = Path("var/hk-v1/host/post-image-build-root.json")
LOCAL_OCI_PROOF_PATH = Path("var/hk-v1/host/application-image-oci-proof.json")

_SCHEMA_ID = "asklegal.v1-poc-application-image-local-oci-proof/v1"
_SCHEMA_VERSION = "1.0.0"
_BUILD_SCHEMA_ID = "asklegal.hk-v1-application-build-results/v1"
_BUILD_SCHEMA_VERSION = "1.0.0"
_DOCKER_VERSION = "29.7.2"
_SG = "/usr/bin/sg"
_MAX_DOCUMENT_BYTES = 1_000_000
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_SHA512 = re.compile(r"^[0-9a-f]{128}$")
_ENTRYPOINT = ["/opt/asklegal/bin/asklegal-service", "--serve"]
_OCI_IMAGE_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
_EXPECTED_IMAGE_COUNT = 5
_BUILD_RESULTS_INVALID = "LOCAL_OCI_PROOF_BUILD_RESULTS_INVALID"
_HOST_FACTS_INVALID = "LOCAL_OCI_PROOF_HOST_FACTS_INVALID"
_IMAGE_INPUTS_INVALID = "LOCAL_OCI_PROOF_IMAGE_INPUTS_INVALID"
_FINGERPRINT_INVALID = "LOCAL_OCI_PROOF_FINGERPRINT_INVALID"
_DOCUMENT_INVALID = "LOCAL_OCI_PROOF_DOCUMENT_INVALID"
_BASE_IMAGE_INVALID = "LOCAL_OCI_PROOF_BASE_IMAGE_INVALID"
_IMAGES_INVALID = "LOCAL_OCI_PROOF_IMAGES_INVALID"
_CANONICAL_BYTES_INVALID = "LOCAL_OCI_PROOF_CANONICAL_BYTES_INVALID"
_DOCKER_INSPECTION_FAILED = "LOCAL_OCI_PROOF_DOCKER_INSPECTION_FAILED"
_ACKNOWLEDGEMENT_REQUIRED = "LOCAL_OCI_PROOF_READ_ONLY_ACKNOWLEDGEMENT_REQUIRED"
_CHECKS = [
    "AUTHENTICATED_HOST_FACTS_UBUNTU_24_04_X86_64",
    "DOCKER_29_7_2_LINUX_AMD64",
    "CURRENT_SOURCE_BOUND_BUILD_RESULTS",
    "PINNED_BASE_OCI_DESCRIPTOR_AND_LAYER_PREFIX",
    "EXACT_FIVE_LOCAL_IMAGE_CONFIGURATION_DIGESTS",
    "EXACT_NON_ROOT_NUMERIC_RUNTIME_IDENTITIES",
    "EXACT_RUNTIME_ENTRYPOINTS",
]
_PROOF_KEYS = {
    "admitted",
    "application_build_results_sha256",
    "application_image_inputs_fingerprint",
    "base_image",
    "checks",
    "docker_runtime",
    "fingerprint",
    "host_facts_sha256",
    "host_kernel_release",
    "host_os",
    "images",
    "proof_kind",
    "proof_state",
    "schema_id",
    "schema_version",
    "target_platform",
}
_BASE_KEYS = {
    "artifact_ref",
    "configuration_id",
    "descriptor",
    "platform",
    "repo_digests",
    "rootfs_diff_ids",
}
_DESCRIPTOR_KEYS = {"digest", "media_type", "size"}
_RUNTIME_KEYS = {"architecture", "operating_system", "os", "server_version"}
_HOST_OS_KEYS = {"architecture", "id", "version_id"}
_IMAGE_KEYS = {
    "image_id",
    "installed_tree_sha512",
    "platform",
    "rootfs_diff_ids",
    "runtime_entrypoint",
    "runtime_user",
    "service_id",
    "tag",
}


class LocalOCIProofError(RuntimeError):
    """One exact, value-free local OCI proof failure."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )


def _fingerprint(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _bytes_fingerprint(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        message = f"LOCAL_OCI_PROOF_{label}_INVALID"
        raise LocalOCIProofError(message)
    candidate = cast("dict[object, object]", value)
    if not all(type(key) is str for key in candidate):
        message = f"LOCAL_OCI_PROOF_{label}_INVALID"
        raise LocalOCIProofError(message)
    return cast("dict[str, object]", candidate)


def _objects(value: object, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list):
        message = f"LOCAL_OCI_PROOF_{label}_INVALID"
        raise LocalOCIProofError(message)
    return [_object(item, label) for item in cast("list[object]", value)]


def _strings(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        message = f"LOCAL_OCI_PROOF_{label}_INVALID"
        raise LocalOCIProofError(message)
    items = cast("list[object]", value)
    if not all(type(item) is str and item for item in items):
        message = f"LOCAL_OCI_PROOF_{label}_INVALID"
        raise LocalOCIProofError(message)
    return cast("list[str]", items)


def _load(path: Path, label: str) -> tuple[dict[str, object], bytes]:
    raw = path.read_bytes()
    if len(raw) > _MAX_DOCUMENT_BYTES:
        message = f"LOCAL_OCI_PROOF_{label}_INVALID"
        raise LocalOCIProofError(message)
    try:
        value: object = json.loads(raw)
    except json.JSONDecodeError as error:
        message = f"LOCAL_OCI_PROOF_{label}_INVALID"
        raise LocalOCIProofError(message) from error
    return _object(value, label), raw


def _application_inputs_fingerprint(root: Path, policy: dict[str, object]) -> str:
    return _fingerprint(
        {
            "application_image_inputs": policy,
            "workspace_source_fingerprint": workspace_source_fingerprint(root),
        }
    )


def _validated_build_results(
    root: Path, policy: dict[str, object], path: Path
) -> tuple[dict[str, dict[str, object]], str, str]:
    document, raw = _load(path, "BUILD_RESULTS")
    if raw != _canonical(document) + b"\n" or set(document) != {
        "application_image_inputs_fingerprint",
        "fingerprint",
        "images",
        "schema_id",
        "schema_version",
    }:
        raise LocalOCIProofError(_BUILD_RESULTS_INVALID)
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    current_inputs = _application_inputs_fingerprint(root, policy)
    if (
        document.get("schema_id") != _BUILD_SCHEMA_ID
        or document.get("schema_version") != _BUILD_SCHEMA_VERSION
        or document.get("application_image_inputs_fingerprint") != current_inputs
        or supplied != _fingerprint(unsigned)
    ):
        raise LocalOCIProofError(_BUILD_RESULTS_INVALID)
    declared_paths = {
        str(item.get("artifact_id")): item.get("application_path")
        for item in _objects(policy.get("images"), "IMAGE_INPUTS")
    }
    images: dict[str, dict[str, object]] = {}
    for item in _objects(document.get("images"), "BUILD_RESULTS"):
        if set(item) != {
            "application_path",
            "image_id",
            "installed_tree_sha512",
            "service_id",
            "tag",
        }:
            raise LocalOCIProofError(_BUILD_RESULTS_INVALID)
        service = item.get("service_id")
        if (
            type(service) is not str
            or service in images
            or item.get("application_path") != declared_paths.get(service)
            or _SHA256.fullmatch(str(item.get("image_id"))) is None
            or _SHA512.fullmatch(str(item.get("installed_tree_sha512"))) is None
            or type(item.get("tag")) is not str
        ):
            raise LocalOCIProofError(_BUILD_RESULTS_INVALID)
        images[service] = item
    expected = set(declared_paths)
    if set(images) != expected or len(images) != _EXPECTED_IMAGE_COUNT:
        raise LocalOCIProofError(_BUILD_RESULTS_INVALID)
    if (
        len({item["image_id"] for item in images.values()}) != _EXPECTED_IMAGE_COUNT
        or len({item["tag"] for item in images.values()}) != _EXPECTED_IMAGE_COUNT
    ):
        raise LocalOCIProofError(_BUILD_RESULTS_INVALID)
    return images, _bytes_fingerprint(raw), current_inputs


def _validated_host_facts(path: Path) -> tuple[dict[str, object], str]:
    document, raw = _load(path, "HOST_FACTS")
    legacy = _object(document.get("legacy_facts"), "HOST_FACTS")
    host_os = _object(legacy.get("os"), "HOST_FACTS")
    kernel = _object(legacy.get("kernel"), "HOST_FACTS")
    if (
        raw != _canonical(document) + b"\n"
        or document.get("source") != "READ_ONLY_HK_V1_HOST_FACTS_ENVELOPE"
        or document.get("complete") is not True
        or document.get("missing_fact_classes") != []
        or document.get("failures") != []
        or legacy.get("source") != "READ_ONLY_HOST_FACTS"
        or host_os != {"id": "ubuntu", "version_id": "24.04"}
        or legacy.get("architecture") != "x86_64"
        or type(kernel.get("release")) is not str
        or not kernel["release"]
    ):
        raise LocalOCIProofError(_HOST_FACTS_INVALID)
    return {
        "host_os": {**host_os, "architecture": "x86_64"},
        "host_kernel_release": kernel["release"],
    }, _bytes_fingerprint(raw)


def _validated_policy(path: Path) -> dict[str, object]:
    policy, _ = _load(path, "IMAGE_INPUTS")
    base = _object(policy.get("base_image"), "IMAGE_INPUTS")
    artifact_ref = base.get("artifact_ref")
    if (
        policy.get("target_platform") != "linux/amd64"
        or base.get("selection_state") != "DIGEST_PINNED"
        or type(artifact_ref) is not str
        or artifact_ref.count("@") != 1
        or _SHA256.fullmatch(artifact_ref.rsplit("@", maxsplit=1)[-1]) is None
    ):
        raise LocalOCIProofError(_IMAGE_INPUTS_INVALID)
    return policy


def _verify_self_fingerprint(document: dict[str, object]) -> None:
    unsigned = dict(document)
    supplied = unsigned.pop("fingerprint", None)
    if supplied != _fingerprint(unsigned):
        raise LocalOCIProofError(_FINGERPRINT_INVALID)


def validate_local_oci_proof(
    root: Path,
    proof: dict[str, object],
    *,
    image_inputs_path: Path,
    build_results_path: Path,
    host_facts_path: Path,
) -> None:
    """Validate one retained measurement against current exact local inputs."""
    policy = _validated_policy(image_inputs_path)
    build_images, build_sha256, current_inputs = _validated_build_results(
        root, policy, build_results_path
    )
    host, host_sha256 = _validated_host_facts(host_facts_path)
    if set(proof) != _PROOF_KEYS:
        raise LocalOCIProofError(_DOCUMENT_INVALID)
    _verify_self_fingerprint(proof)
    docker_runtime = _object(proof.get("docker_runtime"), "DOCUMENT")
    proof_host_os = _object(proof.get("host_os"), "DOCUMENT")
    base = _object(proof.get("base_image"), "DOCUMENT")
    if (
        proof.get("schema_id") != _SCHEMA_ID
        or proof.get("schema_version") != _SCHEMA_VERSION
        or proof.get("proof_kind") != "LOCAL_DOCKER_IMAGE_CONFIGURATION_AND_LAYER_PROOF"
        or proof.get("proof_state") != "PASSED"
        or proof.get("admitted") is not False
        or proof.get("target_platform") != "linux/amd64"
        or proof.get("checks") != _CHECKS
        or proof.get("application_build_results_sha256") != build_sha256
        or proof.get("application_image_inputs_fingerprint") != current_inputs
        or proof.get("host_facts_sha256") != host_sha256
        or proof_host_os != host["host_os"]
        or proof.get("host_kernel_release") != host["host_kernel_release"]
        or set(docker_runtime) != _RUNTIME_KEYS
        or docker_runtime.get("architecture") != "x86_64"
        or docker_runtime.get("os") != "linux"
        or docker_runtime.get("server_version") != _DOCKER_VERSION
        or not str(docker_runtime.get("operating_system", "")).startswith("Ubuntu 24.04")
        or set(base) != _BASE_KEYS
    ):
        raise LocalOCIProofError(_DOCUMENT_INVALID)
    base_policy = _object(policy["base_image"], "IMAGE_INPUTS")
    base_ref = base_policy["artifact_ref"]
    base_layers = _strings(base.get("rootfs_diff_ids"), "BASE_IMAGE")
    descriptor = _object(base.get("descriptor"), "BASE_IMAGE")
    repo_digests = _strings(base.get("repo_digests"), "BASE_IMAGE")
    reference_digest = str(base_ref).rsplit("@", maxsplit=1)[-1]
    reference_repository = str(base_ref).split("@", maxsplit=1)[0]
    local_repository = reference_repository.removeprefix("docker.io/library/")
    descriptor_size = descriptor.get("size")
    if (
        base.get("artifact_ref") != base_ref
        or _SHA256.fullmatch(str(base.get("configuration_id"))) is None
        or set(descriptor) != _DESCRIPTOR_KEYS
        or descriptor.get("digest") != reference_digest
        or descriptor.get("media_type") != _OCI_IMAGE_MANIFEST
        or type(descriptor_size) is not int
        or descriptor_size <= 0
        or repo_digests != [f"{local_repository}@{reference_digest}"]
        or base.get("platform") != "linux/amd64"
        or not base_layers
        or any(_SHA256.fullmatch(layer) is None for layer in base_layers)
    ):
        raise LocalOCIProofError(_BASE_IMAGE_INVALID)
    policy_images = {
        str(item.get("artifact_id")): item
        for item in _objects(policy.get("images"), "IMAGE_INPUTS")
    }
    proof_images = _objects(proof.get("images"), "IMAGES")
    if [item.get("service_id") for item in proof_images] != sorted(build_images):
        raise LocalOCIProofError(_IMAGES_INVALID)
    for image in proof_images:
        if set(image) != _IMAGE_KEYS:
            raise LocalOCIProofError(_IMAGES_INVALID)
        service = str(image.get("service_id"))
        built = build_images.get(service)
        declared = policy_images.get(service)
        layers = _strings(image.get("rootfs_diff_ids"), "IMAGES")
        uid = declared.get("runtime_uid") if declared is not None else None
        if (
            built is None
            or declared is None
            or image.get("image_id") != built.get("image_id")
            or image.get("installed_tree_sha512") != built.get("installed_tree_sha512")
            or image.get("tag") != built.get("tag")
            or image.get("platform") != "linux/amd64"
            or type(uid) is not int
            or image.get("runtime_user") != f"{uid}:{uid}"
            or image.get("runtime_entrypoint") != _ENTRYPOINT
            or layers[: len(base_layers)] != base_layers
            or any(_SHA256.fullmatch(layer) is None for layer in layers)
        ):
            raise LocalOCIProofError(_IMAGES_INVALID)


def check_local_oci_proof(root: Path, proof_path: Path) -> None:
    """Read and validate the exact retained local proof."""
    proof, raw = _load(proof_path, "DOCUMENT")
    if raw != _canonical(proof) + b"\n":
        raise LocalOCIProofError(_CANONICAL_BYTES_INVALID)
    validate_local_oci_proof(
        root,
        proof,
        image_inputs_path=root / APPLICATION_IMAGE_INPUTS_PATH,
        build_results_path=root / APPLICATION_BUILD_RESULTS_PATH,
        host_facts_path=root / HOST_FACTS_PATH,
    )


def _docker_json(arguments: tuple[str, ...]) -> object:
    command = shlex.join(("docker", *arguments))
    result = subprocess.run(  # noqa: S603
        [_SG, "docker", "-c", command],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise LocalOCIProofError(_DOCKER_INSPECTION_FAILED)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise LocalOCIProofError(_DOCKER_INSPECTION_FAILED) from error


def build_local_oci_proof(
    root: Path,
    *,
    image_inputs_path: Path,
    build_results_path: Path,
    host_facts_path: Path,
) -> dict[str, object]:
    """Read Docker state and build one value-free local proof document."""
    policy = _validated_policy(image_inputs_path)
    build_images, build_sha256, current_inputs = _validated_build_results(
        root, policy, build_results_path
    )
    host, host_sha256 = _validated_host_facts(host_facts_path)
    base_policy = _object(policy["base_image"], "IMAGE_INPUTS")
    base_ref = str(base_policy["artifact_ref"])
    refs = [base_ref, *(str(build_images[key]["tag"]) for key in sorted(build_images))]
    inspected = _objects(_docker_json(("image", "inspect", *refs)), "DOCKER_INSPECT")
    if len(inspected) != len(refs):
        raise LocalOCIProofError(_DOCKER_INSPECTION_FAILED)
    docker = _object(_docker_json(("info", "--format", "{{json .}}")), "DOCKER_INFO")
    base_inspect = inspected[0]

    def measured_image(item: dict[str, object], service: str) -> dict[str, object]:
        config = _object(item.get("Config"), "DOCKER_INSPECT")
        rootfs = _object(item.get("RootFS"), "DOCKER_INSPECT")
        layers = _strings(rootfs.get("Layers"), "DOCKER_INSPECT")
        built = build_images[service]
        return {
            "image_id": item.get("Id"),
            "installed_tree_sha512": built["installed_tree_sha512"],
            "platform": f"{item.get('Os')}/{item.get('Architecture')}",
            "rootfs_diff_ids": layers,
            "runtime_entrypoint": config.get("Entrypoint"),
            "runtime_user": config.get("User"),
            "service_id": service,
            "tag": built["tag"],
        }

    base_rootfs = _object(base_inspect.get("RootFS"), "DOCKER_INSPECT")
    base_descriptor = _object(base_inspect.get("Descriptor"), "DOCKER_INSPECT")
    unsigned: dict[str, object] = {
        "admitted": False,
        "application_build_results_sha256": build_sha256,
        "application_image_inputs_fingerprint": current_inputs,
        "base_image": {
            "artifact_ref": base_ref,
            "configuration_id": base_inspect.get("Id"),
            "descriptor": {
                "digest": base_descriptor.get("digest"),
                "media_type": base_descriptor.get("mediaType"),
                "size": base_descriptor.get("size"),
            },
            "platform": f"{base_inspect.get('Os')}/{base_inspect.get('Architecture')}",
            "repo_digests": base_inspect.get("RepoDigests"),
            "rootfs_diff_ids": _strings(base_rootfs.get("Layers"), "DOCKER_INSPECT"),
        },
        "checks": _CHECKS,
        "docker_runtime": {
            "architecture": docker.get("Architecture"),
            "operating_system": docker.get("OperatingSystem"),
            "os": docker.get("OSType"),
            "server_version": docker.get("ServerVersion"),
        },
        "host_facts_sha256": host_sha256,
        "host_kernel_release": host["host_kernel_release"],
        "host_os": host["host_os"],
        "images": [
            measured_image(item, service)
            for item, service in zip(inspected[1:], sorted(build_images), strict=True)
        ],
        "proof_kind": "LOCAL_DOCKER_IMAGE_CONFIGURATION_AND_LAYER_PROOF",
        "proof_state": "PASSED",
        "schema_id": _SCHEMA_ID,
        "schema_version": _SCHEMA_VERSION,
        "target_platform": "linux/amd64",
    }
    proof = {**unsigned, "fingerprint": _fingerprint(unsigned)}
    validate_local_oci_proof(
        root,
        proof,
        image_inputs_path=image_inputs_path,
        build_results_path=build_results_path,
        host_facts_path=host_facts_path,
    )
    return proof


def _write_private(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        os.fchmod(handle.fileno(), 0o600)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> None:
    """Measure the exact local Docker state after explicit read-only acknowledgement."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acknowledge-read-only-docker-inspection", action="store_true")
    parser.add_argument("--image-inputs", type=Path, default=APPLICATION_IMAGE_INPUTS_PATH)
    parser.add_argument("--build-results", type=Path, default=APPLICATION_BUILD_RESULTS_PATH)
    parser.add_argument("--host-facts", type=Path, default=HOST_FACTS_PATH)
    parser.add_argument("--output", type=Path, default=LOCAL_OCI_PROOF_PATH)
    arguments = parser.parse_args()
    if not arguments.acknowledge_read_only_docker_inspection:
        raise SystemExit(_ACKNOWLEDGEMENT_REQUIRED)
    root = Path(__file__).resolve().parents[1]
    try:
        proof = build_local_oci_proof(
            root,
            image_inputs_path=root / arguments.image_inputs,
            build_results_path=root / arguments.build_results,
            host_facts_path=root / arguments.host_facts,
        )
        output = root / arguments.output
        _write_private(output, _canonical(proof) + b"\n")
        check_local_oci_proof(root, output)
    except (LocalOCIProofError, OSError, ValueError) as error:
        print(f"NOT_READY {error}")  # noqa: T201
        raise SystemExit(2) from None
    print(f"PASS {proof['fingerprint']} {arguments.output}")  # noqa: T201


if __name__ == "__main__":
    main()
