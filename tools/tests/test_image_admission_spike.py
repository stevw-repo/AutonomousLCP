"""Fail-closed tests for the local synthetic image-admission proof."""

import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from tools.image_admission_spike import (
    FIXTURE_PATH,
    MANIFEST_PATH,
    ImageAdmissionFailure,
    JsonValue,
    ToolPaths,
    evaluate_licences,
    evaluate_vulnerabilities,
    load_policy,
    normalize_provenance,
    normalize_sbom,
    normalize_vulnerability_report,
    run_spike,
    validate_database_freshness,
    validate_deployment_reference,
    validate_identity,
    validate_referrer_types,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATABASE = {
    "built": "2026-08-15T06:13:48Z",
    "schema": "v6.1.9",
    "sha256": "0" * 64,
}


def _licence_sbom(licence: str) -> JsonValue:
    return {
        "packages": [
            {
                "licenseDeclared": licence,
                "name": "example",
                "versionInfo": "1.0.0",
            }
        ]
    }


def _licence_catalogue() -> dict[str, JsonValue]:
    return {
        "allowed": ["Apache-2.0"],
        "denied": ["AGPL-3.0-only"],
        "obligations": {"Apache-2.0": ["/licenses/Apache-2.0.txt"]},
        "review_required": ["LicenseRef-Review-Required"],
    }


def _vulnerability_report(
    *, severity: str = "Medium", fixed: bool = False, known_exploited: bool = False
) -> JsonValue:
    vulnerability: dict[str, JsonValue] = {
        "fix": {"versions": ["2.0"] if fixed else []},
        "id": "CVE-2099-0001",
        "knownExploited": ["2026-08-01"] if known_exploited else [],
        "severity": severity,
    }
    return {
        "descriptor": {
            "configuration": {
                "db": {"auto-update": False},
                "externalSources": {"enable": False},
            },
            "db": {
                "status": {
                    "built": DATABASE["built"],
                    "schemaVersion": DATABASE["schema"],
                    "valid": True,
                }
            },
        },
        "matches": [
            {
                "artifact": {"name": "example", "version": "1.0"},
                "vulnerability": vulnerability,
            }
        ],
        "source": {
            "target": {"manifestDigest": f"sha256:{'b' * 64}"},
            "type": "sbom",
        },
    }


def test_policy_is_repository_scoped_and_test_trust_cannot_become_production_trust() -> None:
    """Pin the candidate/release repository split and isolated trust capability."""
    policy = load_policy(REPOSITORY_ROOT)
    assert REPOSITORY_ROOT / MANIFEST_PATH
    assert policy["candidate_repository"] == "candidate/review-api"
    assert policy["release_repository"] == "release/review-api"
    signing = policy["test_signing"]
    assert isinstance(signing, dict)
    assert signing == {
        "common_name": "AskLegal-Image-Admission-Test-Root",
        "production_trust_forbidden": True,
        "signature_artifact_type": "application/vnd.asklegal.test-signature.v1+json",
        "trust_capability": "LOCAL_TEST_ONLY",
    }


def test_synthetic_busybox_package_evidence_is_tracked_with_the_fixture() -> None:
    """Keep the package database needed for complete ordinary SBOM discovery."""
    status = (REPOSITORY_ROOT / FIXTURE_PATH / "rootfs/var/lib/dpkg/status").read_text(
        encoding="utf-8"
    )
    assert "Package: busybox-static\n" in status
    assert "Status: install ok installed\n" in status
    assert "Version: 1:1.36.1-6ubuntu3.1\n" in status


def test_runtime_policy_binds_the_named_builder_image_and_database_source() -> None:
    """Prevent version-only builder checks or an unrecoverable database snapshot."""
    policy = load_policy(REPOSITORY_ROOT)
    runtime = policy["runtime"]
    assert isinstance(runtime, dict)
    assert runtime["buildkit_builder_name"] == "asklegal-image-admission-v0262"
    assert runtime["buildkit_image_ref"] == (
        "moby/buildkit@sha256:de10faf919fc71ba4eb1dd7bd6449566d012b0c9436b1c61bfee21d621b009aa"
    )
    database = policy["vulnerability_database"]
    assert isinstance(database, dict)
    assert str(database["source_archive_url"]).startswith("https://grype.anchore.io/")
    assert database["source_archive_sha256"] == (
        "dca26dd65bd0c4ba626af404a2e60d983d9302863eabdd8a7e7d42008fb4da3c"
    )


def test_normalizers_remove_only_declared_observation_fields() -> None:
    """Keep meaningful SBOM and provenance mutations result-determining."""
    first_sbom: JsonValue = {
        "creationInfo": {"created": "first", "creators": ["Tool: syft"]},
        "documentNamespace": "first-run",
        "packages": [{"name": "example"}],
    }
    second_sbom = deepcopy(first_sbom)
    assert isinstance(second_sbom, dict)
    second_sbom["creationInfo"] = {"created": "second", "creators": ["Tool: syft"]}
    second_sbom["documentNamespace"] = "second-run"
    assert normalize_sbom(first_sbom) == normalize_sbom(second_sbom)
    second_sbom["packages"] = [{"name": "changed"}]
    assert normalize_sbom(first_sbom) != normalize_sbom(second_sbom)

    first_provenance: JsonValue = {
        "predicate": {
            "metadata": {
                "buildFinishedOn": "first",
                "buildInvocationID": "first",
                "buildStartedOn": "first",
                "completeness": {"parameters": True},
            },
            "materials": [{"digestMapping": {"run": "step"}, "uri": "local://fixture"}],
        }
    }
    second_provenance = deepcopy(first_provenance)
    assert isinstance(second_provenance, dict)
    predicate = second_provenance["predicate"]
    assert isinstance(predicate, dict)
    metadata = predicate["metadata"]
    assert isinstance(metadata, dict)
    metadata["buildInvocationID"] = "second"
    assert normalize_provenance(first_provenance) == normalize_provenance(second_provenance)
    predicate["materials"] = [{"uri": "local://changed"}]
    assert normalize_provenance(first_provenance) != normalize_provenance(second_provenance)

    first_scan = _vulnerability_report()
    assert isinstance(first_scan, dict)
    first_descriptor = first_scan["descriptor"]
    assert isinstance(first_descriptor, dict)
    first_descriptor["timestamp"] = "first"
    first_configuration = first_descriptor["configuration"]
    assert isinstance(first_configuration, dict)
    first_configuration["file"] = "/synthetic/run-a/report.json"
    first_database = first_configuration["db"]
    assert isinstance(first_database, dict)
    first_database["cache-dir"] = "/synthetic/run-a/database"
    second_scan = deepcopy(first_scan)
    assert isinstance(second_scan, dict)
    second_descriptor = second_scan["descriptor"]
    assert isinstance(second_descriptor, dict)
    second_descriptor["timestamp"] = "second"
    second_configuration = second_descriptor["configuration"]
    assert isinstance(second_configuration, dict)
    second_configuration["file"] = "/synthetic/run-b/report.json"
    second_database = second_configuration["db"]
    assert isinstance(second_database, dict)
    second_database["cache-dir"] = "/synthetic/run-b/database"
    assert normalize_vulnerability_report(first_scan) == normalize_vulnerability_report(second_scan)
    second_scan["matches"] = []
    assert normalize_vulnerability_report(first_scan) != normalize_vulnerability_report(second_scan)


def test_licence_policy_requires_known_allowed_licence_and_obligation_files() -> None:
    """Accept the synthetic allowed licence only with its required image content."""
    report = evaluate_licences(
        _licence_sbom("Apache-2.0"),
        _licence_catalogue(),
        {"/licenses/Apache-2.0.txt"},
    )
    assert report["result"] == "PASS"
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_LICENCE_OBLIGATION_MISSING"):
        evaluate_licences(_licence_sbom("Apache-2.0"), _licence_catalogue(), set())


@pytest.mark.parametrize(
    ("licence", "failure"),
    [
        ("AGPL-3.0-only", "IMAGE_LICENCE_DENIED"),
        ("LicenseRef-Review-Required", "IMAGE_LICENCE_REVIEW_REQUIRED"),
        ("NOASSERTION", "IMAGE_LICENCE_UNKNOWN"),
    ],
)
def test_licence_policy_blocks_denied_review_and_unknown_values(licence: str, failure: str) -> None:
    """Exercise every fail-closed licence disposition."""
    with pytest.raises(ImageAdmissionFailure, match=failure):
        evaluate_licences(_licence_sbom(licence), _licence_catalogue(), set())


def test_medium_vulnerability_is_owned_and_complete_database_is_bound() -> None:
    """Permit only a supported non-blocking severity and retain remediation ownership."""
    report = evaluate_vulnerabilities(_vulnerability_report(), DATABASE)
    assert report["result"] == "PASS"
    dispositions = report["dispositions"]
    assert isinstance(dispositions, list)
    assert dispositions[0] == {
        "id": "CVE-2099-0001",
        "package": "example",
        "severity": "MEDIUM",
        "status": "OWNED_REMEDIATION_REQUIRED",
        "version": "1.0",
    }


@pytest.mark.parametrize(
    ("severity", "flags", "failure"),
    [
        ("Medium", (False, True), "IMAGE_VULNERABILITY_KNOWN_EXPLOITED"),
        ("Critical", (False, False), "IMAGE_VULNERABILITY_CRITICAL"),
        ("High", (True, False), "IMAGE_VULNERABILITY_HIGH_FIXED"),
        ("High", (False, False), "IMAGE_VULNERABILITY_HIGH_ACCEPTANCE_REQUIRED"),
        ("Unknown", (False, False), "IMAGE_VULNERABILITY_SEVERITY_UNKNOWN"),
    ],
)
def test_vulnerability_policy_blocks_every_initial_stop_condition(
    severity: str, flags: tuple[bool, bool], failure: str
) -> None:
    """Exercise KEV, Critical, High, and unknown-severity rejection."""
    fixed, known_exploited = flags
    with pytest.raises(ImageAdmissionFailure, match=failure):
        evaluate_vulnerabilities(
            _vulnerability_report(
                severity=severity,
                fixed=fixed,
                known_exploited=known_exploited,
            ),
            DATABASE,
        )


def test_vulnerability_report_must_be_complete_and_database_bound() -> None:
    """Reject absent results and scanner state that is not the selected database."""
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_VULNERABILITY_REPORT_INCOMPLETE"):
        evaluate_vulnerabilities({"matches": []}, DATABASE)
    report = _vulnerability_report()
    assert isinstance(report, dict)
    descriptor = report["descriptor"]
    assert isinstance(descriptor, dict)
    database = descriptor["db"]
    assert isinstance(database, dict)
    status = database["status"]
    assert isinstance(status, dict)
    status["valid"] = False
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_VULNERABILITY_DATABASE_BINDING_INVALID"):
        evaluate_vulnerabilities(report, DATABASE)


def test_unfixed_high_requires_one_exact_unexpired_acceptance() -> None:
    """Accept only a digest/package/version/CVE-bound owned exception."""
    digest = f"sha256:{'b' * 64}"
    now = datetime(2026, 8, 16, tzinfo=UTC)
    acceptance: dict[str, JsonValue] = {
        "approval_evidence": "security-review-001",
        "compensating_controls": ["network isolation"],
        "expires_at": "2026-08-17T00:00:00Z",
        "image_digest": digest,
        "owner": "security-owner",
        "package": "example",
        "reason": "No fixed release exists",
        "version": "1.0",
        "vulnerability": "CVE-2099-0001",
    }
    result = evaluate_vulnerabilities(
        _vulnerability_report(severity="High"),
        DATABASE,
        image_digest=digest,
        risk_acceptances=(acceptance,),
        now=now,
    )
    dispositions = result["dispositions"]
    assert isinstance(dispositions, list)
    disposition = dispositions[0]
    assert isinstance(disposition, dict)
    assert disposition["status"] == "TIME_BOUND_RISK_ACCEPTANCE"

    expired = deepcopy(acceptance)
    expired["expires_at"] = "2026-08-16T00:00:00Z"
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_VULNERABILITY_HIGH_ACCEPTANCE_INVALID"):
        evaluate_vulnerabilities(
            _vulnerability_report(severity="High"),
            DATABASE,
            image_digest=digest,
            risk_acceptances=(expired,),
            now=now,
        )
    wrong_digest = deepcopy(acceptance)
    wrong_digest["image_digest"] = f"sha256:{'c' * 64}"
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_VULNERABILITY_HIGH_ACCEPTANCE_REQUIRED"):
        evaluate_vulnerabilities(
            _vulnerability_report(severity="High"),
            DATABASE,
            image_digest=digest,
            risk_acceptances=(wrong_digest,),
            now=now,
        )


def test_database_freshness_rejects_stale_future_and_naive_time() -> None:
    """Make freshness fail closed under staleness and clock ambiguity."""
    built = datetime(2026, 8, 15, tzinfo=UTC)
    validate_database_freshness(built, built + timedelta(hours=23), 86_400)
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_DATABASE_STALE"):
        validate_database_freshness(built, built + timedelta(hours=25), 86_400)
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_DATABASE_TIME_INVALID"):
        validate_database_freshness(built, built - timedelta(seconds=1), 86_400)
    naive = datetime(2026, 8, 15, tzinfo=UTC).replace(tzinfo=None)
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_DATABASE_TIME_INVALID"):
        validate_database_freshness(built, naive, 86_400)


def test_deployments_require_exact_release_repository_digest() -> None:
    """Reject mutable tags, candidate repositories, and the wrong release repository."""
    digest = f"sha256:{'a' * 64}"
    validate_deployment_reference(f"release/review-api@{digest}", "release/review-api")
    for reference in (
        "release/review-api:latest",
        f"candidate/review-api@{digest}",
        f"release/other-api@{digest}",
    ):
        with pytest.raises(ImageAdmissionFailure, match="IMAGE_DEPLOYMENT_REFERENCE_INVALID"):
            validate_deployment_reference(reference, "release/review-api")


def test_identity_policy_requires_exact_narrow_capabilities() -> None:
    """Reject wildcards, broad registry access, omissions, and extras."""
    permitted = ("candidate/read", "release/write")
    validate_identity(permitted, permitted)
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_IDENTITY_BROAD_CAPABILITY"):
        validate_identity(("repository/*",), permitted)
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_IDENTITY_BROAD_CAPABILITY"):
        validate_identity(("registry/admin",), permitted)
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_IDENTITY_CAPABILITY_MISMATCH"):
        validate_identity(("candidate/read",), permitted)
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_IDENTITY_CAPABILITY_MISMATCH"):
        validate_identity((*permitted, "release/delete"), permitted)


def test_required_referrer_types_reject_missing_and_extra_evidence() -> None:
    """Require equality rather than treating the policy as a minimum subset."""
    required = {"application/spdx+json", "application/vnd.asklegal.provenance.v1+json"}
    validate_referrer_types(required, required)
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_REQUIRED_REFERRER_SET_MISMATCH"):
        validate_referrer_types({"application/spdx+json"}, required)
    with pytest.raises(ImageAdmissionFailure, match="IMAGE_REQUIRED_REFERRER_SET_MISMATCH"):
        validate_referrer_types(required | {"application/unknown"}, required)


@pytest.mark.image_admission
@pytest.mark.skipif(
    os.environ.get("ASKLEGAL_IMAGE_ADMISSION_SPIKE") != "1",
    reason="set ASKLEGAL_IMAGE_ADMISSION_SPIKE=1 with exact tool paths to run the proof",
)
def test_complete_local_image_admission_spike(tmp_path: Path) -> None:
    """Run both builds, scanner policies, graph copy, signing, recovery, and runtime proof."""
    names = ("BUILDX", "GRYPE", "GRYPE_DB", "NOTATION", "ORAS", "SYFT")
    values = {name: os.environ.get(f"ASKLEGAL_{name}") for name in names}
    missing = [name for name, value in values.items() if value is None]
    if missing:
        pytest.fail(f"missing image-admission tool paths: {', '.join(missing)}")
    paths = ToolPaths(
        buildx=Path(str(values["BUILDX"])),
        docker=Path(os.environ.get("ASKLEGAL_DOCKER", "/usr/bin/docker")),
        grype=Path(str(values["GRYPE"])),
        grype_db=Path(str(values["GRYPE_DB"])),
        notation=Path(str(values["NOTATION"])),
        openssl=Path("/usr/bin/openssl"),
        oras=Path(str(values["ORAS"])),
        sudo=Path(os.environ.get("ASKLEGAL_PRIVILEGE_RUNNER", "/usr/bin/sudo")),
        syft=Path(str(values["SYFT"])),
    )
    report = run_spike(REPOSITORY_ROOT, paths, tmp_path)
    assert report.recovery_graph_sha256 == report.signed_release_graph_sha256
    assert report.image_digest.startswith("sha256:")
