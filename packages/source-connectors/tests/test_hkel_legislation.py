"""Offline contracts for complete per-instrument HKeL evidence planning."""

# ruff: noqa: SLF001
# pyright: reportPrivateUsage=false

from __future__ import annotations

import copy
import gc
import weakref
from dataclasses import replace
from hashlib import sha256

import pytest
from asklegal_evidence_vault import HostileClassification
from asklegal_source_connectors import hkel_legislation
from asklegal_source_connectors.hkel_legislation import (
    HkelArchiveReuseKey,
    HkelEvidencePlan,
    HkelEvidenceRole,
    HkelInventoryProfile,
    build_hkel_evidence_plan_from_projection,
    project_hkel_current_inventory,
    select_hkel_archives_to_reparse,
)
from asklegal_source_connectors.official import load_hk_legislation_source_register
from asklegal_source_connectors.official_http import (
    OfficialFetchCode,
    OfficialFetchResult,
    OfficialTransportResponse,
)
from asklegal_source_connectors.official_inventory import (
    OfficialInventoryCode,
    OfficialInventoryResult,
)

_CUTOFF = "2026-08-25T00:00:00Z"


def _source_inventory(*, editorial_disposition: str = "NOT_PUBLISHED") -> OfficialInventoryResult:
    """Build a completed current-inventory result, not a parallel authority."""
    inventory_bodies = {
        "sep_000000000000000000000000000000000000000000000002": (
            b'<hkel-inventory profile="asklegal.synthetic.hkel.current-inventory.v1" '
            b'language="en"><item id="hk-cap-001" version="2026-08-25" '
            b'status="CURRENT" editorial-disposition="NOT_PUBLISHED"><resource '
            b'id="hk-cap-001-en" endpoint-id="'
            b'sep_00000000000000000000000000000000000000000000000a" '
            b'endpoint-version="1.0.0" locator="cap-001!en" '
            b'archive-member="hk-cap-001/en.xml" '
            b'copy-endpoint-id="sep_000000000000000000000000000000000000000000000017" '
            b'copy-endpoint-version="1.0.0" copy-locator="cap-001!en" '
            b'sha256="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"/>'
            b"</item></hkel-inventory>"
        ),
        "sep_000000000000000000000000000000000000000000000003": (
            b'<hkel-inventory profile="asklegal.synthetic.hkel.current-inventory.v1" '
            b'language="zh-Hant"><item id="hk-cap-001" version="2026-08-25" '
            b'status="CURRENT" editorial-disposition="NOT_PUBLISHED"><resource '
            b'id="hk-cap-001-zh-hant" endpoint-id="'
            b'sep_00000000000000000000000000000000000000000000000e" '
            b'endpoint-version="1.0.0" locator="cap-001!zh-Hant" '
            b'archive-member="hk-cap-001/zh-Hant.xml" '
            b'copy-endpoint-id="sep_000000000000000000000000000000000000000000000017" '
            b'copy-endpoint-version="1.0.0" copy-locator="cap-001!zh-Hant" '
            b'sha256="sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"/>'
            b"</item></hkel-inventory>"
        ),
    }
    if editorial_disposition != "NOT_PUBLISHED":
        inventory_bodies = {
            endpoint_id: body.replace(
                b'editorial-disposition="NOT_PUBLISHED"',
                f'editorial-disposition="{editorial_disposition}"'.encode(),
            )
            for endpoint_id, body in inventory_bodies.items()
        }
    results = tuple(
        OfficialFetchResult(
            OfficialFetchCode.CAPTURED,
            "HK-LEG-HKEL-CURRENT-INVENTORY",
            endpoint_id,
            "1.0.0",
            f"sha256:{sha256(inventory_bodies[endpoint_id]).hexdigest()}",
            inventory_bodies[endpoint_id],
            "application/xml",
            HostileClassification(True, ()),
            None,
            OfficialTransportResponse(
                200,
                url,
                "application/xml",
                "utf-8",
                inventory_bodies[endpoint_id],
                len(inventory_bodies[endpoint_id]),
                False,
            ),
        )
        for endpoint_id, _unused_digest, url in (
            (
                "sep_000000000000000000000000000000000000000000000002",
                "a",
                "https://resource.data.one.gov.hk/doj/data/hkel_list_c_all_en.xml",
            ),
            (
                "sep_000000000000000000000000000000000000000000000003",
                "b",
                "https://resource.data.one.gov.hk/doj/data/hkel_list_c_all_zh-Hant.xml",
            ),
        )
    )
    digest = sha256()
    for result in results:
        assert result.fingerprint is not None
        for value in (result.endpoint_id, result.endpoint_version, result.fingerprint):
            digest.update(value.encode("utf-8"))
            digest.update(b"\x00")
    return OfficialInventoryResult(
        OfficialInventoryCode.COMPLETE_CAPTURED,
        "HK-LEG-HKEL-CURRENT-INVENTORY",
        results,
        f"sha256:{digest.hexdigest()}",
        None,
    )


def test_candidate_projection_derives_exact_membership_from_both_captured_bodies() -> None:
    """A synthetic profile proves membership from bytes, not caller artifact labels."""
    projection = project_hkel_current_inventory(_source_inventory())

    assert projection.profile is HkelInventoryProfile.SYNTHETIC_CANDIDATE_V1
    assert projection.authentic_source_admitted is False
    item = projection.item("hk-cap-001")
    assert {
        (resource.language, resource.endpoint_id, resource.archive_member)
        for resource in item.resources
    } == {
        ("en", "sep_00000000000000000000000000000000000000000000000a", "hk-cap-001/en.xml"),
        (
            "zh-Hant",
            "sep_00000000000000000000000000000000000000000000000e",
            "hk-cap-001/zh-Hant.xml",
        ),
    }
    assert {resource.inventory_member_fingerprint for resource in item.resources} == {
        result.fingerprint for result in _source_inventory().member_results
    }


def test_projection_rejects_inventory_body_that_does_not_match_its_captured_fingerprint() -> None:
    """The result wrapper cannot assert provenance for bytes it did not capture."""
    source = _source_inventory()
    forged_body = b"<hkel-inventory/>"
    transport = source.member_results[0].transport_response
    assert transport is not None
    forged_member = replace(
        source.member_results[0],
        body=forged_body,
        transport_response=replace(transport, body=forged_body, declared_length=len(forged_body)),
    )
    forged = replace(source, member_results=(forged_member, source.member_results[1]))

    with pytest.raises(ValueError, match="captured inventory body fingerprint"):
        project_hkel_current_inventory(forged)


def test_projection_plan_uses_only_source_byte_derived_xml_and_copy_members() -> None:
    """A caller cannot select a different chapter ZIP or copy locator for an item."""
    plan = build_hkel_evidence_plan_from_projection(
        project_hkel_current_inventory(_source_inventory()),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
    )

    xml_members = {
        (
            member.role,
            member.language,
            member.endpoint_id,
            member.locator,
            member.archive_member,
        )
        for member in plan.members
        if member.role in {HkelEvidenceRole.ENGLISH_XML, HkelEvidenceRole.TRADITIONAL_CHINESE_XML}
    }
    assert xml_members == {
        (
            HkelEvidenceRole.ENGLISH_XML,
            "en",
            "sep_00000000000000000000000000000000000000000000000a",
            None,
            "hk-cap-001/en.xml",
        ),
        (
            HkelEvidenceRole.TRADITIONAL_CHINESE_XML,
            "zh-Hant",
            "sep_00000000000000000000000000000000000000000000000e",
            None,
            "hk-cap-001/zh-Hant.xml",
        ),
    }
    assert plan.authentic_source_admitted is False
    assert plan.release_blocking is False
    assert {
        (member.role, member.language, member.endpoint_id, member.locator)
        for member in plan.members
        if member.role is HkelEvidenceRole.OFFICIAL_COPY
    } == {
        (
            HkelEvidenceRole.OFFICIAL_COPY,
            "en",
            "sep_000000000000000000000000000000000000000000000017",
            "cap-001!en",
        ),
        (
            HkelEvidenceRole.OFFICIAL_COPY,
            "zh-Hant",
            "sep_000000000000000000000000000000000000000000000017",
            "cap-001!zh-Hant",
        ),
    }


def test_source_proved_published_editorial_record_remains_an_explicit_blocker() -> None:
    """NOT_PUBLISHED is conditional: a published record needs its own procedure."""
    plan = build_hkel_evidence_plan_from_projection(
        project_hkel_current_inventory(_source_inventory(editorial_disposition="PUBLISHED")),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
    )

    assert plan.release_blocking is True
    assert plan.missing_member_ids == ("EDITORIAL_RECORD:PROCEDURE_NOT_ADMITTED",)


def test_source_proved_not_published_editorial_record_is_an_explicit_member() -> None:
    """A non-published record is a source fact, not an omitted required role."""
    plan = build_hkel_evidence_plan_from_projection(
        project_hkel_current_inventory(_source_inventory()),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
    )

    editorial = [
        member for member in plan.members if member.role is HkelEvidenceRole.EDITORIAL_RECORD
    ]
    assert len(editorial) == 1
    assert editorial[0].source_disposition == "NOT_PUBLISHED"
    assert plan.missing_member_ids == ()


def test_replaced_projection_cannot_be_used_to_build_an_evidence_plan() -> None:
    """Replacing a public frozen projection must lose its factory provenance."""
    projection = project_hkel_current_inventory(_source_inventory())

    with pytest.raises(ValueError, match="factory-issued"):
        build_hkel_evidence_plan_from_projection(
            replace(projection, items=projection.items),
            instrument_id="hk-cap-001",
            cutoff=_CUTOFF,
        )


def test_replaced_plan_loses_its_factory_provenance() -> None:
    """A replacement cannot be passed on as the original frozen issued plan."""
    plan = build_hkel_evidence_plan_from_projection(
        project_hkel_current_inventory(_source_inventory()),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
    )

    with pytest.raises(ValueError, match="factory-issued"):
        replace(plan).assert_factory_issued()


def test_plan_constructor_rejects_an_empty_nonblocking_member_set() -> None:
    """A public constructor cannot manufacture an empty successful plan."""
    with pytest.raises(ValueError, match="six semantic roles"):
        HkelEvidencePlan(
            instrument_id="hk-cap-001",
            observation_cutoff=_CUTOFF,
            source_register_id="HK-LEG-SOURCES",
            source_register_fingerprint="sha256:" + "a" * 64,
            inventory_fingerprint="sha256:" + "b" * 64,
            projection_fingerprint="sha256:" + "c" * 64,
            members=(),
            missing_member_ids=(),
            release_blocking=False,
            plan_fingerprint="sha256:" + "d" * 64,
        )


def test_copied_projection_cannot_reseal_changed_source_membership() -> None:
    """Copying and resealing public fields cannot reuse issuance provenance."""
    projection = project_hkel_current_inventory(_source_inventory())
    copied = copy.copy(projection)
    resource = replace(
        projection.items[0].resources[0],
        archive_member="hk-cap-001/forged-en.xml",
    )
    item = replace(
        projection.items[0],
        resources=(resource, projection.items[0].resources[1]),
    )
    object.__setattr__(copied, "items", (item,))
    object.__setattr__(
        copied,
        "projection_fingerprint",
        hkel_legislation._projection_fingerprint(copied),
    )

    with pytest.raises(ValueError, match="factory-issued"):
        build_hkel_evidence_plan_from_projection(
            copied,
            instrument_id="hk-cap-001",
            cutoff=_CUTOFF,
        )


def test_copied_plan_cannot_reseal_changed_copy_locator() -> None:
    """A copied plan cannot turn an unrelated official-copy locator into evidence."""
    plan = build_hkel_evidence_plan_from_projection(
        project_hkel_current_inventory(_source_inventory()),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
    )
    copied = copy.copy(plan)
    changed_members = tuple(
        replace(member, locator="cap-001!forged")
        if member.role is HkelEvidenceRole.OFFICIAL_COPY and member.language == "en"
        else member
        for member in plan.members
    )
    object.__setattr__(copied, "members", changed_members)
    object.__setattr__(
        copied,
        "plan_fingerprint",
        hkel_legislation._plan_fingerprint(copied),
    )
    if hasattr(copied, "_issued_snapshot"):
        object.__setattr__(
            copied,
            "_issued_snapshot",
            hkel_legislation._plan_fingerprint(copied),
        )

    with pytest.raises(ValueError, match="factory-issued"):
        copied.assert_factory_issued()


def test_plan_rejects_displayed_fingerprint_drift_after_factory_issuance() -> None:
    """A current snapshot is not enough when its displayed fingerprint was changed."""
    plan = build_hkel_evidence_plan_from_projection(
        project_hkel_current_inventory(_source_inventory()),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
    )
    object.__setattr__(plan, "plan_fingerprint", "sha256:" + "f" * 64)

    with pytest.raises(ValueError, match="factory-issued"):
        plan.assert_factory_issued()


def test_plan_rejects_object_setattr_derived_release_state_drift() -> None:
    """A public-object mutation cannot flip the member-derived release result."""
    plan = build_hkel_evidence_plan_from_projection(
        project_hkel_current_inventory(_source_inventory()),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
    )
    object.__setattr__(plan, "release_blocking", True)

    with pytest.raises(ValueError, match="factory-issued"):
        plan.assert_factory_issued()


def test_projection_rejects_nested_resource_item_identity_mutation() -> None:
    """Nested resource identity must remain part of the issued projection snapshot."""
    projection = project_hkel_current_inventory(_source_inventory())
    object.__setattr__(projection.items[0].resources[0], "item_id", "hk-cap-999")

    with pytest.raises(ValueError, match="factory-issued"):
        projection.assert_factory_issued()


def test_plan_rejects_nested_member_instrument_identity_mutation() -> None:
    """Nested artifact identity must remain part of the issued plan snapshot."""
    plan = build_hkel_evidence_plan_from_projection(
        project_hkel_current_inventory(_source_inventory()),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
    )
    object.__setattr__(plan.members[0], "instrument_id", "hk-cap-999")

    with pytest.raises(ValueError, match="factory-issued"):
        plan.assert_factory_issued()


def test_issuance_registry_cleans_dead_identity_before_reuse_pressure() -> None:
    """Dead issued identities leave no record that a later object could inherit."""
    projection = project_hkel_current_inventory(_source_inventory())
    projection_id = id(projection)
    issued_reference = weakref.ref(projection)

    assert "_issuance_token" not in projection.__dataclass_fields__
    assert projection_id in hkel_legislation._PROJECTION_ISSUANCE
    del projection
    gc.collect()

    assert issued_reference() is None
    assert projection_id not in hkel_legislation._PROJECTION_ISSUANCE
    for _ in range(64):
        fresh = project_hkel_current_inventory(_source_inventory())
        fresh.assert_factory_issued()


def test_builder_rejects_replaced_register_with_stale_original_fingerprint() -> None:
    """A register object cannot retain its fingerprint after endpoint facts changed."""
    register = load_hk_legislation_source_register()
    changed_endpoint = replace(
        register.endpoints[0],
        url="https://evil.example.invalid/changed",
    )
    forged = replace(register, endpoints=(changed_endpoint, *register.endpoints[1:]))

    with pytest.raises(ValueError, match="checked-in source register"):
        project_hkel_current_inventory(_source_inventory(), register=forged)


def test_archive_reuse_key_binds_archive_and_publication_profile() -> None:
    """Only the exact archive/spec tuple may reuse a prior safe parse."""
    first = HkelArchiveReuseKey.issue(
        "sep_00000000000000000000000000000000000000000000000a",
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
    )
    same = HkelArchiveReuseKey.issue(
        first.archive_endpoint_id,
        first.archive_fingerprint,
        first.publication_profile_fingerprint,
    )
    changed_archive = HkelArchiveReuseKey.issue(
        first.archive_endpoint_id,
        "sha256:" + "c" * 64,
        first.publication_profile_fingerprint,
    )
    changed_profile = HkelArchiveReuseKey.issue(
        first.archive_endpoint_id,
        first.archive_fingerprint,
        "sha256:" + "d" * 64,
    )

    assert first == same
    assert select_hkel_archives_to_reparse((same,), (first,)) == ()
    assert select_hkel_archives_to_reparse((changed_archive,), (first,)) == (changed_archive,)
    assert select_hkel_archives_to_reparse((changed_profile,), (first,)) == (changed_profile,)


def test_archive_reuse_selection_rejects_duplicate_endpoint_identity() -> None:
    """Two current keys cannot compete for one archive endpoint."""
    first = HkelArchiveReuseKey.issue(
        "sep_00000000000000000000000000000000000000000000000a",
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
    )
    changed = HkelArchiveReuseKey.issue(
        first.archive_endpoint_id,
        "sha256:" + "c" * 64,
        first.publication_profile_fingerprint,
    )
    with pytest.raises(ValueError, match="HKEL_ARCHIVE_REUSE_KEYS_INVALID"):
        select_hkel_archives_to_reparse((first, changed), ())
