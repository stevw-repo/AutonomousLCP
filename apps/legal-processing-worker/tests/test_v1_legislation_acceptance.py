"""Fixture-backed live Hong Kong legislation acceptance composition."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_evidence_vault import ExactObjectReference, VaultName
from asklegal_legal_processing_worker.v1_legislation_acceptance import (
    LegislationAcceptanceError,
    prepare_hk_v1_legislation_acceptance_component,
)


class _Vault:
    def __init__(self, objects: dict[str, tuple[ExactObjectReference, bytes]]) -> None:
        self.objects = objects

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        expected, content = self.objects[reference.logical_key]
        assert reference == expected
        return content


def _canonical(value: object) -> bytes:
    return canonicalize(checked_json_value(value))


def _object(value: object) -> dict[str, JsonValue]:
    parsed = checked_json_value(value)
    assert isinstance(parsed, dict)
    return parsed


def _ref(key: str, content: bytes) -> ExactObjectReference:
    digest = sha256(content).hexdigest()
    return ExactObjectReference(
        VaultName.PRIMARY, key, f"v{digest}", f"sha256:{digest}", len(content)
    )


def _descriptor(reference: ExactObjectReference) -> dict[str, JsonValue]:
    return {
        "logical_key": reference.logical_key,
        "version_id": reference.version_id,
        "content_fingerprint": reference.fingerprint,
        "body_length": reference.byte_length,
    }


def _manifest(cutoff: str, verified_ref: str) -> bytes:
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.legislation-acquisition-manifest",
        "schema_version": "1.0.0",
        "cycle_id": "cyc_20260908_legislation",
        "observation_cutoff": cutoff,
        "scope_dispositions": [
            {
                "scope_id": scope,
                "required_item_count": 1,
                "verified_item_count": 1,
                "retryable_item_count": 0,
                "rejected_item_count": 0,
                "result": "COMPLETE",
            }
            for scope in (
                "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
                "HK-LEG-ORDINANCES",
                "HK-LEG-SUBSIDIARY",
            )
        ],
        "verified_item_refs": [verified_ref],
        "review_issue_refs": [],
        "journal_head_fingerprint": "sha256:" + "1" * 64,
        "source_register_fingerprint": "sha256:" + "2" * 64,
        "source_baseline_fingerprint": "sha256:" + "3" * 64,
        "work_plan_fingerprint": "sha256:" + "4" * 64,
        "result": "COMPLETE",
    }
    return _canonical({**body, "fingerprint": "sha256:" + sha256(_canonical(body)).hexdigest()})


def _fixture() -> tuple[bytes, dict[str, JsonValue], _Vault]:
    cutoff = "2026-09-08T00:00:00+00:00"
    objects: dict[str, tuple[ExactObjectReference, bytes]] = {}

    def retain(key: str, body: bytes) -> dict[str, JsonValue]:
        reference = _ref(key, body)
        objects[key] = reference, body
        return _descriptor(reference)

    xsd = (
        b'<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">'
        b'<xs:element name="legislation"/></xs:schema>'
    )
    common_xsd = retain("legislation/hkel/schema.xsd", xsd)
    items: list[dict[str, JsonValue]] = []
    for index, scope in enumerate(
        (
            "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
            "HK-LEG-ORDINANCES",
            "HK-LEG-SUBSIDIARY",
        ),
        start=1,
    ):
        source_key = f"cap-{index}"
        en = (
            f'<legislation language="en" source-key="{source_key}">'
            f"<title>Instrument {index}</title>"
            f'<citation>Cap. {index}</citation><provision id="s1" locator="section 1" '
            f'heading="Application"><paragraph id="p1">This provision applies.</paragraph>'
            "</provision></legislation>"
        ).encode()
        zh = (
            f'<legislation language="zh-Hant" source-key="{source_key}"><title>法例 {index}</title>'
            f'<citation>第{index}章</citation><provision id="s1" locator="第1條" '
            f'heading="適用範圍"><paragraph id="p1">本條文適用。</paragraph>'
            "</provision></legislation>"
        ).encode()
        pdf = b"%PDF-1.7\nfixture gazette evidence\n%%EOF"
        pdf_ref = retain(f"legislation/gld/{source_key}.pdf", pdf)
        event = _canonical(
            {
                "schema_id": "asklegal.hk-v1-gld-event-evidence/v1",
                "schema_version": "1.0.0",
                "source_key": source_key,
                "gazette_id": f"gazette-{index}",
                "publication_at": "2026-09-01T00:00:00Z",
                "commencement_at": "2026-09-02T00:00:00Z",
                "source_pdf_fingerprint": pdf_ref["content_fingerprint"],
            }
        )
        items.append(
            {
                "scope_id": scope,
                "inventory_item_id": f"inventory-{index}",
                "source_key": source_key,
                "en_xml": retain(f"legislation/hkel/{source_key}.en.xml", en),
                "zh_hant_xml": retain(f"legislation/hkel/{source_key}.zh.xml", zh),
                "xsd": common_xsd,
                "gld_pdf": pdf_ref,
                "gld_event": retain(f"legislation/gld/{source_key}.event.json", event),
            }
        )
    bundle = _canonical(
        {
            "schema_id": "asklegal.hk-v1-legislation-source-bundle/v1",
            "schema_version": "1.0.0",
            "operation_id": "op_acceptance_fixture",
            "observation_cutoff": cutoff,
            "items": items,
        }
    )
    bundle_descriptor = retain("legislation/acceptance/source-bundle.json", bundle)
    verified_objects = [_descriptor(reference) for reference, _body in objects.values()]
    inputs = _object(
        {
            "operation_id": "op_acceptance_fixture",
            "command_fingerprint": "sha256:" + "9" * 64,
            "observation_cutoff": cutoff,
            "families": [
                {
                    "source_family": "LEGISLATION",
                    "result": "COMPLETE",
                    "verified_objects": verified_objects,
                }
            ],
        }
    )
    return _manifest(cutoff, str(bundle_descriptor["content_fingerprint"])), inputs, _Vault(objects)


def test_full_fixture_path_is_restart_safe_and_retains_three_real_scope_inputs(
    tmp_path: Path,
) -> None:
    """A complete retained source fixture reaches all three release scopes and replays."""
    manifest, inputs, vault = _fixture()
    first = prepare_hk_v1_legislation_acceptance_component(
        operation_id="op_acceptance_fixture",
        manifest=manifest,
        verified_inputs=inputs,
        primary_vault=vault,
        state_root=tmp_path / "state",
        output_root=tmp_path / "processed",
    )
    second = prepare_hk_v1_legislation_acceptance_component(
        operation_id="op_acceptance_fixture",
        manifest=manifest,
        verified_inputs=inputs,
        primary_vault=vault,
        state_root=tmp_path / "state",
        output_root=tmp_path / "processed",
    )
    assert first == second
    assert first["result"] == "COMPLETE"
    output = tmp_path / "processed/op_acceptance_fixture/legislation-release-input.json"
    assert output.read_bytes() == canonicalize(
        parse_json_bytes(output.read_bytes(), max_bytes=16_777_216)
    )
    retained = parse_json_bytes(output.read_bytes(), max_bytes=16_777_216)
    assert isinstance(retained, dict)
    scopes = retained["legislation_scopes"]
    assert isinstance(scopes, list)
    rows = [_object(row) for row in scopes]
    assert [row["scope_id"] for row in rows] == [
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    ]
    for row in rows:
        identities = _object(row["allocated_identities"])
        assert identities["allocations"]
    assert (tmp_path / "state/legislation-identities.json").is_file()


def test_missing_gld_evidence_is_not_ready_without_state_or_output(tmp_path: Path) -> None:
    """A missing exact Gazette object fails before identity or output mutation."""
    manifest, inputs, vault = _fixture()
    del vault.objects["legislation/gld/cap-2.event.json"]
    with pytest.raises(LegislationAcceptanceError, match="LEGISLATION_GLD_EVIDENCE_NOT_READY"):
        prepare_hk_v1_legislation_acceptance_component(
            operation_id="op_acceptance_fixture",
            manifest=manifest,
            verified_inputs=inputs,
            primary_vault=vault,
            state_root=tmp_path / "state",
            output_root=tmp_path / "processed",
        )
    assert not (tmp_path / "state").exists()
    assert not (tmp_path / "processed").exists()
