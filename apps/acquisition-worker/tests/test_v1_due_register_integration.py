"""Integration proof that due-cycle projection consumes checked-in registers exactly."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_acquisition_worker import hk_v1_due_cycle as acquisition_due_cycle
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_evidence_vault import (
    ExactObjectReference,
    VaultName,
    s3_version_reference,
    validate_logical_key,
)
from asklegal_reporting import (
    DueCycleKind,
    DueImmutableReference,
    HongKongV1DueCycleError,
    HongKongV1DueCycleInstruction,
    derive_hk_v1_due_cycle_plan,
    hk_v1_due_cycle_manifest_key,
    hk_v1_due_source_payload_key,
    hk_v1_due_source_result_manifest_key,
    hk_v1_due_source_terminal_key,
    load_hk_v1_coverage_matrix,
    parse_hk_v1_due_register_bundle,
)

_REGISTER_ROOT = (
    Path(__file__).resolve().parents[3]
    / "packages/source-connectors/src/asklegal_source_connectors"
)
_EXPECTED = {
    "hk_legislation_source_register.json": (
        "sha256:be2dc02b4ef087ac2357ad96dc05be5a36127e2a7f395bffe5b7a98f6408de67",
        14,
    ),
    "hk_cases_source_register.json": (
        "sha256:a697a7f7b9b1327169d368ebdef722ee71d6dae447057c8da2a502b5bcdbe13e",
        7,
    ),
    "hk_regulatory_source_register.json": (
        "sha256:9af7fb460f3556d82b93620ba171cf7391480ad288268afce24ac03e8b7bbbb6",
        5,
    ),
}
_CURRENT_REGISTER_NAMES = (
    "hk_legislation_source_register.json",
    "hk_cases_source_register.json",
)


@pytest.mark.parametrize(("name", "expected"), _EXPECTED.items())
def test_due_register_projection_accepts_raw_and_canonical_checked_in_contract(
    name: str,
    expected: tuple[str, int],
) -> None:
    """Both byte representations retain the official register identity."""
    raw = (_REGISTER_ROOT / name).read_bytes()
    canonical = canonicalize(checked_json_value(json.loads(raw)))

    for content in (raw, canonical):
        bundle = parse_hk_v1_due_register_bundle(content)
        assert (bundle.register_fingerprint, len(bundle.sources)) == expected


def test_due_register_projection_rejects_reordered_official_source_array() -> None:
    """Source order is a contract fact, not a normalization choice."""
    raw = (_REGISTER_ROOT / "hk_cases_source_register.json").read_bytes()
    document = json.loads(raw)
    document["sources"] = list(reversed(document["sources"]))
    unsigned = dict(document)
    del unsigned["fingerprint"]
    document["fingerprint"] = (
        f"sha256:{sha256(canonicalize(checked_json_value(unsigned))).hexdigest()}"
    )

    with pytest.raises(HongKongV1DueCycleError, match="REGISTER_BUNDLE_INVALID"):
        parse_hk_v1_due_register_bundle(canonicalize(checked_json_value(document)))


def test_actual_registers_derive_unadmitted_daily_requirements() -> None:
    """Self-authored configured projections cannot turn HK-V1-003 into COMPLETE."""
    matrix = load_hk_v1_coverage_matrix()
    bundles = tuple(
        parse_hk_v1_due_register_bundle((_REGISTER_ROOT / name).read_bytes())
        for name in _CURRENT_REGISTER_NAMES
    )
    plan = derive_hk_v1_due_cycle_plan(
        HongKongV1DueCycleInstruction(
            "hk-v1-daily-20260826",
            DueCycleKind.DAILY_CURRENT_LAW,
            "2026-08-26T00:00:00Z",
            "2026-08-26T00:00:00Z",
            matrix.revision,
            matrix.fingerprint,
        ),
        matrix,
        bundles,
    )

    assert len(plan.requirements) == 4
    assert {requirement.material_family for requirement in plan.requirements} <= {
        "CASES",
        "LEGISLATION",
    }
    assert all(
        not requirement.source_id.startswith("HK-REG-HKEX-") for requirement in plan.requirements
    )
    assert all(requirement.technical_state == "NOT_ADMITTED" for requirement in plan.requirements)
    assert all(requirement.rights_state == "NOT_ADMITTED" for requirement in plan.requirements)


def test_acquisition_current_due_registers_exclude_hkex() -> None:
    """The acquisition composition loads only the two current family registers."""
    bundles = acquisition_due_cycle._fixed_register_bundles()  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

    assert tuple(bundle.register_id for bundle in bundles) == (
        "hsr_000000000000000000000000000000000000000000000001",
        "hcr_000000000000000000000000000000000000000000000001",
    )
    assert all(
        not source.source_id.startswith("HK-REG-HKEX-")
        for bundle in bundles
        for source in bundle.sources
    )


@pytest.mark.parametrize("vault", [VaultName.PRIMARY, VaultName.RECOVERY])
def test_due_immutable_reference_losslessly_projects_real_vault_receipt_fields(
    vault: VaultName,
) -> None:
    """Acquisition can carry a real read-back receipt without reporting importing vault code."""
    key = "hk-v1/due-cycles/" + "a" * 64 + "/" + "b" * 64 + "/terminal.json"
    receipt = ExactObjectReference(
        vault,
        key,
        "v" + "c" * 64,
        "sha256:" + "d" * 64,
        0,
    )
    due_reference = DueImmutableReference(
        receipt.vault.value,
        receipt.logical_key,
        receipt.version_id,
        receipt.fingerprint,
        receipt.byte_length,
    )
    rebuilt = ExactObjectReference(
        VaultName(due_reference.vault),
        due_reference.logical_key,
        due_reference.version_id,
        due_reference.fingerprint,
        due_reference.byte_length,
    )
    assert rebuilt == receipt
    assert validate_logical_key(due_reference.logical_key) == due_reference.logical_key


def test_due_immutable_reference_accepts_only_a_real_canonical_s3_version() -> None:
    """The pure projection admits the same serialized S3 version as the vault model."""
    reference = DueImmutableReference(
        "PRIMARY",
        "hk-v1/due-cycles/" + "a" * 64 + "/" + "b" * 64 + "/attempt.json",
        s3_version_reference("provider-version-123"),
        "sha256:" + "d" * 64,
        1,
    )
    assert reference.version_id == s3_version_reference("provider-version-123")
    with pytest.raises(HongKongV1DueCycleError, match="DUE_REFERENCE_INVALID"):
        DueImmutableReference(
            "PRIMARY",
            reference.logical_key,
            "s3v___",
            reference.fingerprint,
            reference.byte_length,
        )


@pytest.mark.parametrize(
    "key",
    [
        hk_v1_due_source_payload_key("Cycle-A_1", "Source-A_1"),
        hk_v1_due_source_result_manifest_key("Cycle-A_1", "Source-A_1"),
        hk_v1_due_source_terminal_key("Cycle-A_1", "Source-A_1"),
        hk_v1_due_cycle_manifest_key("Cycle-A_1"),
    ],
)
def test_all_reporting_owned_due_keys_are_accepted_by_the_real_vault_grammar(key: str) -> None:
    """Every fixed reporting key is directly usable as an immutable vault key."""
    assert validate_logical_key(key) == key
