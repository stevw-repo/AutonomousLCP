"""Fail-closed tests for the measured local application-image OCI proof."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest

import tools.v1_poc_application_image_oci_proof as local_oci
from tools.v1_poc_application_image_oci_proof import (
    LocalOCIProofError,
    build_local_oci_proof,
    validate_local_oci_proof,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
        "ascii"
    )


def _fingerprint(value: object) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    candidate = cast("dict[object, object]", value)
    assert all(type(key) is str for key in candidate)
    return cast("dict[str, object]", candidate)


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    policy: dict[str, object] = {
        "target_platform": "linux/amd64",
        "base_image": {
            "selection_state": "DIGEST_PINNED",
            "artifact_ref": "docker.io/library/python@sha256:" + "a" * 64,
        },
        "images": [
            {
                "application_path": f"apps/app-{index}",
                "artifact_id": f"app-{index}",
                "runtime_uid": 3000 + index,
            }
            for index in range(5)
        ],
    }
    policy_path = tmp_path / "image-inputs.json"
    policy_path.write_bytes(_canonical(policy) + b"\n")
    input_fingerprint = _fingerprint(
        {
            "application_image_inputs": policy,
            "workspace_source_fingerprint": "sha256:" + "b" * 64,
        }
    )
    build_unsigned: dict[str, object] = {
        "application_image_inputs_fingerprint": input_fingerprint,
        "images": [
            {
                "application_path": f"apps/app-{index}",
                "image_id": "sha256:" + str(index + 1) * 64,
                "installed_tree_sha512": str(index + 1) * 128,
                "service_id": f"app-{index}",
                "tag": f"asklegal/app-{index}:v1",
            }
            for index in range(5)
        ],
        "schema_id": "asklegal.hk-v1-application-build-results/v1",
        "schema_version": "1.0.0",
    }
    build = {
        **build_unsigned,
        "fingerprint": _fingerprint(build_unsigned),
    }
    build_path = tmp_path / "build-results.json"
    build_path.write_bytes(_canonical(build) + b"\n")
    host: dict[str, object] = {
        "complete": True,
        "failures": [],
        "legacy_facts": {
            "architecture": "x86_64",
            "kernel": {"release": "7.0.0-test"},
            "os": {"id": "ubuntu", "version_id": "24.04"},
            "source": "READ_ONLY_HOST_FACTS",
        },
        "missing_fact_classes": [],
        "source": "READ_ONLY_HK_V1_HOST_FACTS_ENVELOPE",
    }
    host_path = tmp_path / "host-facts.json"
    host_path.write_bytes(_canonical(host) + b"\n")
    return policy_path, build_path, host_path


def _docker_observations() -> tuple[dict[str, object], list[dict[str, object]]]:
    base_layers = ["sha256:" + "c" * 64]
    docker: dict[str, object] = {
        "Architecture": "x86_64",
        "OperatingSystem": "Ubuntu 24.04.4 LTS",
        "OSType": "linux",
        "ServerVersion": "29.7.2",
    }
    images: list[dict[str, object]] = [
        {
            "Architecture": "amd64",
            "Config": {"Entrypoint": None, "User": ""},
            "Descriptor": {
                "digest": "sha256:" + "a" * 64,
                "mediaType": "application/vnd.oci.image.manifest.v1+json",
                "size": 1745,
            },
            "Id": "sha256:" + "d" * 64,
            "Os": "linux",
            "RepoDigests": ["python@sha256:" + "a" * 64],
            "RootFS": {"Layers": base_layers},
        }
    ]

    def application_image(index: int) -> dict[str, object]:
        return {
            "Architecture": "amd64",
            "Config": {
                "Entrypoint": ["/opt/asklegal/bin/asklegal-service", "--serve"],
                "User": f"{3000 + index}:{3000 + index}",
            },
            "Id": "sha256:" + str(index + 1) * 64,
            "Os": "linux",
            "RootFS": {"Layers": [*base_layers, "sha256:" + str(index + 2) * 64]},
        }

    images.extend(application_image(index) for index in range(5))
    return docker, images


def test_measured_current_local_images_discharge_only_the_oci_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bind host, build, base ancestry, image identities, users, and entrypoints."""
    policy, build, host = _write_inputs(tmp_path)
    docker, images = _docker_observations()
    replies: list[object] = [images, docker]

    def source_fingerprint(_root: Path) -> str:
        return "sha256:" + "b" * 64

    def docker_json(_arguments: tuple[str, ...]) -> object:
        return replies.pop(0)

    monkeypatch.setattr(local_oci, "workspace_source_fingerprint", source_fingerprint)
    monkeypatch.setattr(local_oci, "_docker_json", docker_json)

    proof = build_local_oci_proof(
        REPOSITORY_ROOT,
        image_inputs_path=policy,
        build_results_path=build,
        host_facts_path=host,
    )

    assert proof["proof_state"] == "PASSED"
    assert proof["admitted"] is False
    validate_local_oci_proof(
        REPOSITORY_ROOT,
        proof,
        image_inputs_path=policy,
        build_results_path=build,
        host_facts_path=host,
    )


@pytest.mark.parametrize("mutation", ["image", "base", "descriptor", "host", "admission"])
def test_proof_drift_never_closes_the_blocker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    """Reject stale identity, false ancestry, host drift, and admission overclaim."""
    policy, build, host = _write_inputs(tmp_path)
    docker, images = _docker_observations()
    replies: list[object] = [images, docker]

    def source_fingerprint(_root: Path) -> str:
        return "sha256:" + "b" * 64

    def docker_json(_arguments: tuple[str, ...]) -> object:
        return replies.pop(0)

    monkeypatch.setattr(local_oci, "workspace_source_fingerprint", source_fingerprint)
    monkeypatch.setattr(local_oci, "_docker_json", docker_json)
    proof = build_local_oci_proof(
        REPOSITORY_ROOT,
        image_inputs_path=policy,
        build_results_path=build,
        host_facts_path=host,
    )
    changed = deepcopy(proof)
    changed_images = cast("list[object]", changed["images"])
    first_image = _mapping(changed_images[0])
    if mutation == "image":
        first_image["image_id"] = "sha256:" + "f" * 64
    elif mutation == "base":
        first_image["rootfs_diff_ids"] = ["sha256:" + "f" * 64]
    elif mutation == "descriptor":
        _mapping(_mapping(changed["base_image"])["descriptor"])["digest"] = "sha256:" + "f" * 64
    elif mutation == "host":
        _mapping(changed["host_os"])["version_id"] = "24.10"
    else:
        changed["admitted"] = True
    unsigned = dict(changed)
    unsigned.pop("fingerprint")
    changed["fingerprint"] = _fingerprint(unsigned)

    with pytest.raises(LocalOCIProofError):
        validate_local_oci_proof(
            REPOSITORY_ROOT,
            changed,
            image_inputs_path=policy,
            build_results_path=build,
            host_facts_path=host,
        )
