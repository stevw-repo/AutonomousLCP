"""Offline scheduler boundary tests for HKeL evidence capture."""

# ruff: noqa: SLF001
# pyright: reportPrivateUsage=false

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import asklegal_acquisition_worker.v1_pipeline as pipeline
import pytest
from asklegal_acquisition_worker.v1_infrastructure import V1AcquisitionInfrastructure
from asklegal_application_runtime import CredentialMaterial
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_durable_task import ActivityContext
from asklegal_evidence_vault import ExactObjectReference, VaultName
from asklegal_source_connectors import (
    HkelEvidenceArtifact,
    HkelEvidencePlan,
    HkelEvidenceRole,
    HttpMethod,
    OfficialEndpointContract,
    OfficialTransportFailure,
    OfficialTransportResponse,
    load_hk_legislation_source_register,
)

_CUTOFF = "2026-08-25T00:00:00Z"
_INVENTORY_ENDPOINTS = {
    "sep_000000000000000000000000000000000000000000000002",
    "sep_000000000000000000000000000000000000000000000003",
}
_DIRECT_ARTIFACTS = {
    "sep_00000000000000000000000000000000000000000000000a",
    "sep_00000000000000000000000000000000000000000000000e",
    "sep_000000000000000000000000000000000000000000000035",
    "sep_000000000000000000000000000000000000000000000036",
    "sep_000000000000000000000000000000000000000000000037",
    "sep_000000000000000000000000000000000000000000000038",
}


def _new_string_list() -> list[str]:
    return []


class _Vault:
    def __init__(self, *, read_back_verified: bool = True) -> None:
        self.read_back_verified = read_back_verified
        self.vault_name = VaultName.PRIMARY
        self.writes: dict[str, bytes] = {}
        self.references: dict[str, ExactObjectReference] = {}
        self.failure_prefix: str | None = None

    def conditional_create(
        self,
        logical_key: str,
        content: bytes,
        _retention: object,
    ) -> SimpleNamespace:
        if self.failure_prefix is not None and logical_key.startswith(self.failure_prefix):
            message = "test vault write failure"
            raise RuntimeError(message)
        existing = self.writes.get(logical_key)
        if existing is not None:
            assert existing == content
        else:
            self.writes[logical_key] = content
            fingerprint = f"sha256:{sha256(content).hexdigest()}"
            self.references[logical_key] = ExactObjectReference(
                VaultName.PRIMARY,
                logical_key,
                f"v{sha256((logical_key + fingerprint).encode()).hexdigest()}",
                fingerprint,
                len(content),
            )
        return SimpleNamespace(
            created=existing is None,
            read_back_verified=self.read_back_verified,
            reference=self.references[logical_key],
        )

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        stored = self.references.get(reference.logical_key)
        if stored != reference:
            message = "test vault exact object is unavailable"
            raise RuntimeError(message)
        return self.writes[reference.logical_key]


@dataclass(slots=True)
class _Transport:
    failure_endpoint: str | None = None
    changed_endpoint: str | None = None
    unsafe_endpoint: str | None = None
    archive_member_mismatch: bool = False
    inventory_version: str = "2026-08-25"
    calls: list[str] = field(default_factory=_new_string_list, init=False)

    def request(
        self,
        *,
        endpoint: OfficialEndpointContract,
        method: HttpMethod,
        timeout_seconds: int,
    ) -> OfficialTransportResponse:
        assert method is HttpMethod.GET
        assert timeout_seconds in {30, 45, 60}
        self.calls.append(endpoint.endpoint_id)
        if endpoint.endpoint_id == self.failure_endpoint:
            message = "bounded"
            raise OfficialTransportFailure(message)
        body = _inventory_body(endpoint.endpoint_id, version=self.inventory_version)
        if body is None:
            body = _zip_artifact(endpoint.endpoint_id, mismatch=self.archive_member_mismatch)
        if endpoint.endpoint_id == self.unsafe_endpoint:
            body = b"<!DOCTYPE x [<!ENTITY e SYSTEM 'file:///etc/passwd'>]><x>&e;</x>"
        return OfficialTransportResponse(
            status_code=(404 if endpoint.endpoint_id == self.changed_endpoint else 200),
            final_url=endpoint.url,
            media_type=_media_type(endpoint.endpoint_id),
            character_encoding="utf-8",
            body=body,
            declared_length=len(body),
            truncated=False,
        )


def _inventory_body(endpoint_id: str, *, version: str) -> bytes | None:
    language = {
        "sep_000000000000000000000000000000000000000000000002": "en",
        "sep_000000000000000000000000000000000000000000000003": "zh-Hant",
    }.get(endpoint_id)
    if language is None:
        return None
    data_endpoint = {
        "en": "sep_00000000000000000000000000000000000000000000000a",
        "zh-Hant": "sep_00000000000000000000000000000000000000000000000e",
    }[language]
    profile = "asklegal.synthetic.hkel.current-inventory.v1"
    return (
        f'<hkel-inventory profile="{profile}" language="{language}">'
        f'<item id="hk-cap-001" version="{version}" status="CURRENT" '
        'editorial-disposition="NOT_PUBLISHED">'
        f'<resource id="hk-cap-001-{language}" endpoint-id="{data_endpoint}" '
        'endpoint-version="1.0.0" '
        f'locator="cap-001!{language}" archive-member="hk-cap-001/{language}.xml" '
        'copy-endpoint-id="sep_000000000000000000000000000000000000000000000017" '
        'copy-endpoint-version="1.0.0" '
        f'copy-locator="cap-001!{language}" '
        f'sha256="sha256:{sha256(b"<artifact/>").hexdigest()}"/></item></hkel-inventory>'
    ).encode()


def _zip_artifact(endpoint_id: str, *, mismatch: bool) -> bytes:
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        language = {
            "sep_00000000000000000000000000000000000000000000000a": "en",
            "sep_00000000000000000000000000000000000000000000000e": "zh-Hant",
        }.get(endpoint_id)
        if language is None:
            member_name = f"fixture/{endpoint_id}.xml"
            content = b"<artifact/>"
        else:
            content = b"<mismatch/>" if mismatch else b"<artifact/>"
            member_name = f"hk-cap-001/{language}.xml"
        member = ZipInfo(member_name, date_time=(2026, 8, 25, 0, 0, 0))
        member.compress_type = ZIP_DEFLATED
        archive.writestr(member, content)
    return stream.getvalue()


def test_hkel_zip_fixture_is_independent_of_wall_clock() -> None:
    """A retry fixture must not manufacture source change from ZIP member timestamps."""
    first = _zip_artifact("sep_00000000000000000000000000000000000000000000000a", mismatch=False)
    second = _zip_artifact("sep_00000000000000000000000000000000000000000000000a", mismatch=False)

    assert second == first
    with ZipFile(BytesIO(first)) as archive:
        assert archive.infolist()[0].date_time == (2026, 8, 25, 0, 0, 0)


def _media_type(endpoint_id: str) -> str:
    if endpoint_id in _INVENTORY_ENDPOINTS or endpoint_id.endswith("000035"):
        return "application/xml"
    if endpoint_id.endswith(("000036", "000037", "000038")):
        return "application/pdf"
    return "application/zip"


def _activities(
    transport: _Transport,
    *,
    read_back_verified: bool = True,
    vault: _Vault | None = None,
) -> tuple[pipeline.AcquisitionActivities, _Vault]:
    vault = vault or _Vault(read_back_verified=read_back_verified)
    infrastructure = V1AcquisitionInfrastructure.__new__(V1AcquisitionInfrastructure)
    object.__setattr__(
        infrastructure,
        "source_egress_proxy_credential",
        CredentialMaterial(b"http://proxy.invalid:3128"),
    )
    object.__setattr__(infrastructure, "primary_vault", vault)
    object.__setattr__(infrastructure, "due_cycle_state_root", Path("/dev/null"))
    activities = pipeline.AcquisitionActivities(infrastructure)
    object.__setattr__(
        activities,
        "_connector",
        __import__("asklegal_source_connectors").OfficialHttpConnector(
            load_hk_legislation_source_register(), transport
        ),
    )
    return activities, vault


def _caller_artifact_payload() -> dict[str, object]:
    """One deliberately untrusted caller artifact assertion."""
    return {
        "instrument_id": "hk-cap-001",
        "observation_cutoff": _CUTOFF,
        "artifacts": [{"endpoint_id": "sep_00000000000000000000000000000000000000000000000a"}],
    }


def _planned_payload(activities: pipeline.AcquisitionActivities) -> dict[str, object]:
    planned = _result(
        activities.plan_hkel_evidence(
            ActivityContext("hkel-plan", 1),
            {"instrument_id": "hk-cap-001", "observation_cutoff": _CUTOFF},
        )
    )
    return {
        "instrument_id": planned["instrument_id"],
        "observation_cutoff": planned["observation_cutoff"],
        "expected_plan_fingerprint": planned["expected_plan_fingerprint"],
        "expected_inventory_fingerprint": planned["expected_inventory_fingerprint"],
    }


def _result(value: object) -> dict[str, JsonValue]:
    checked = checked_json_value(value)
    assert isinstance(checked, dict)
    return checked


def test_hkel_activity_validates_inventory_before_artifacts_and_writes_manifest_last() -> None:
    """The inventory runs first; every member then reaches the terminal manifest."""
    transport = _Transport()
    activities, vault = _activities(transport)

    result = _result(
        activities.capture_hkel_evidence(ActivityContext("hkel", 1), _planned_payload(activities))
    )

    assert set(transport.calls[:2]) == _INVENTORY_ENDPOINTS
    assert set(transport.calls[2:4]) == _INVENTORY_ENDPOINTS
    assert set(transport.calls[4:]) == _DIRECT_ARTIFACTS
    assert result["code"] == "PARTIAL_CAPTURE"
    assert result["release_blocking"] is True
    members = result["members"]
    assert isinstance(members, list)
    assert len(members) == 10
    editorial = [
        member
        for member in members
        if isinstance(member, dict) and member["role"] == "EDITORIAL_RECORD"
    ]
    assert len(editorial) == 1
    assert set(editorial[0]) == pipeline._HKEL_TERMINAL_MEMBER_FIELDS
    assert editorial[0]["artifact_id"] == "hk-cap-001:editorial-record"
    assert editorial[0]["code"] == "NOT_PUBLISHED"
    assert editorial[0]["evidence"] is None
    assert editorial[0]["failure_code"] is None
    assert editorial[0]["isolated_response"] is None
    assert editorial[0]["role"] == "EDITORIAL_RECORD"
    assert editorial[0]["source_disposition"] == "NOT_PUBLISHED"
    assert "sep_000000000000000000000000000000000000000000000033" not in transport.calls
    terminal = result["terminal_manifest"]
    assert isinstance(terminal, dict)
    terminal_key = terminal["logical_key"]
    assert isinstance(terminal_key, str)
    assert list(vault.writes)[-1] == terminal_key
    manifest = parse_json_bytes(
        vault.writes[terminal_key], max_bytes=len(vault.writes[terminal_key])
    )
    assert isinstance(manifest, dict)
    assert manifest["complete"] is False
    assert manifest["plan_fingerprint"] == result["plan_fingerprint"]


@pytest.mark.parametrize("failure", ["failure_endpoint", "changed_endpoint", "unsafe_endpoint"])
def test_hkel_artifact_failures_are_accounted_before_terminal_manifest(failure: str) -> None:
    """Unavailable, drifted, and hostile artifact responses cannot look complete."""
    transport = _Transport()
    setattr(
        transport,
        failure,
        "sep_00000000000000000000000000000000000000000000000a",
    )
    activities, vault = _activities(transport)

    result = _result(
        activities.capture_hkel_evidence(ActivityContext("hkel", 1), _planned_payload(activities))
    )

    assert result["code"] == "PARTIAL_CAPTURE"
    assert result["terminal_manifest"] is not None
    assert any(key.startswith("poc/report/hkel-evidence-attempt/") for key in vault.writes)


def test_hkel_archive_member_hash_mismatch_is_visible_and_never_retained_as_evidence() -> None:
    """A captured ZIP must prove the exact declared archive member bytes."""
    transport = _Transport(archive_member_mismatch=True)
    activities, _vault = _activities(transport)

    result = _result(
        activities.capture_hkel_evidence(ActivityContext("hkel", 1), _planned_payload(activities))
    )

    members = result["members"]
    assert isinstance(members, list)
    member_dicts = [member for member in members if isinstance(member, dict)]
    assert any(
        member["failure_code"] == "HKEL_ARCHIVE_MEMBER_DECLARATION_MISMATCH"
        for member in member_dicts
    )


def test_hkel_capture_rejects_inventory_drift_before_addressed_artifact_transport() -> None:
    """A retry cannot silently replace its frozen plan with a later inventory."""
    transport = _Transport()
    activities, _vault = _activities(transport)
    payload = _planned_payload(activities)
    transport.inventory_version = "2026-08-26"

    with pytest.raises(pipeline.AcquisitionPipelineError, match="frozen plan drifted"):
        activities.capture_hkel_evidence(ActivityContext("hkel", 1), payload)

    assert set(transport.calls) == _INVENTORY_ENDPOINTS


def test_hkel_terminal_manifest_write_failure_never_returns_capture_success() -> None:
    """Manifest-last accounting failure remains visible after member dispositions exist."""
    transport = _Transport()
    activities, vault = _activities(transport)
    payload = _planned_payload(activities)
    vault.failure_prefix = "poc/report/hkel-evidence-attempt/"

    with pytest.raises(RuntimeError, match="test vault write failure"):
        activities.capture_hkel_evidence(ActivityContext("hkel", 1), payload)

    assert not any(key.startswith("poc/report/hkel-evidence-attempt/") for key in vault.writes)


def test_retained_hkel_plan_bytes_self_reproduce_every_plan_fingerprint_input() -> None:
    """A retained plan carries every primitive needed to reproduce its displayed digest."""
    transport = _Transport()
    activities, vault = _activities(transport)
    planned = _result(
        activities.plan_hkel_evidence(
            ActivityContext("hkel-plan", 1),
            {"instrument_id": "hk-cap-001", "observation_cutoff": _CUTOFF},
        )
    )
    plan_manifest = planned["plan_manifest"]
    assert isinstance(plan_manifest, dict)
    logical_key = plan_manifest["logical_key"]
    assert isinstance(logical_key, str)
    retained = parse_json_bytes(vault.writes[logical_key], max_bytes=len(vault.writes[logical_key]))
    assert isinstance(retained, dict)
    members = retained["members"]
    assert isinstance(members, list)
    assert retained["instrument_id"] == "hk-cap-001"
    assert retained["source_register_id"] == "hsr_000000000000000000000000000000000000000000000001"
    assert all(
        isinstance(member, dict) and member["instrument_id"] == "hk-cap-001" for member in members
    )
    fingerprint_inputs = {
        key: retained[key]
        for key in (
            "authentic_source_admitted",
            "instrument_id",
            "inventory_fingerprint",
            "members",
            "missing_member_ids",
            "observation_cutoff",
            "projection_fingerprint",
            "source_register_fingerprint",
            "source_register_id",
        )
    }
    reproduced = (
        f"sha256:{sha256(canonicalize(checked_json_value(fingerprint_inputs))).hexdigest()}"
    )
    assert reproduced == retained["plan_fingerprint"] == planned["expected_plan_fingerprint"]


def test_changed_hkel_plan_rejects_prior_attempt_outcomes_without_artifact_fetch() -> None:
    """Issuance for one frozen plan cannot authorize its same-member successor."""
    transport = _Transport()
    activities, vault = _activities(transport)
    inventory_one = activities._capture_current_hkel_inventory()
    plan_one = pipeline.build_hkel_evidence_plan_from_projection(
        pipeline.project_hkel_current_inventory(inventory_one, register=activities._register),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt_one = activities._begin_hkel_terminal_attempt(plan_one)
    outcomes = _vault_backed_complete_hkel_outcomes(plan_one, vault, activities, attempt_one)
    transport.inventory_version = "2026-08-26"
    inventory_two = activities._capture_current_hkel_inventory()
    plan_two = pipeline.build_hkel_evidence_plan_from_projection(
        pipeline.project_hkel_current_inventory(inventory_two, register=activities._register),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    transport.calls.clear()

    with pytest.raises(pipeline.AcquisitionPipelineError, match="attempt"):
        activities._retain_hkel_evidence_manifest(plan_two, outcomes, attempt_one)

    assert transport.calls == []
    assert not any(key.startswith("poc/report/hkel-evidence-attempt/") for key in vault.writes)


def test_hkel_attempt_issuance_is_consumed_after_successful_terminal_manifest() -> None:
    """Successful terminal accounting leaves no process-lifetime reference authority."""
    transport = _Transport()
    activities, vault = _activities(transport)
    inventory = activities._capture_current_hkel_inventory()
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        pipeline.project_hkel_current_inventory(inventory, register=activities._register),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt = activities._begin_hkel_terminal_attempt(plan)
    outcomes = _vault_backed_complete_hkel_outcomes(plan, vault, activities, attempt)

    activities._retain_hkel_evidence_manifest(plan, outcomes, attempt)

    assert activities._hkel_terminal_reference_issuance == {}


def test_hkel_attempt_issuance_is_consumed_when_manifest_write_fails() -> None:
    """A manifest-last error cannot retain authorization for a later stale attempt."""
    transport = _Transport()
    activities, vault = _activities(transport)
    inventory = activities._capture_current_hkel_inventory()
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        pipeline.project_hkel_current_inventory(inventory, register=activities._register),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt = activities._begin_hkel_terminal_attempt(plan)
    outcomes = _vault_backed_complete_hkel_outcomes(plan, vault, activities, attempt)
    vault.failure_prefix = "poc/report/hkel-evidence-attempt/"

    with pytest.raises(RuntimeError, match="test vault write failure"):
        activities._retain_hkel_evidence_manifest(plan, outcomes, attempt)

    assert activities._hkel_terminal_reference_issuance == {}


def test_hkel_same_plan_retry_and_cross_instance_adopt_immutable_manifest() -> None:
    """Fresh attempts may adopt one unchanged immutable plan without sharing issuance state."""
    transport_one = _Transport()
    first, vault = _activities(transport_one)
    payload = _planned_payload(first)
    initial = _result(first.capture_hkel_evidence(ActivityContext("hkel", 1), payload))
    retried = _result(first.capture_hkel_evidence(ActivityContext("hkel", 2), payload))
    second, _same_vault = _activities(_Transport(), vault=vault)
    adopted = _result(second.capture_hkel_evidence(ActivityContext("hkel", 1), payload))

    first_manifest = initial["terminal_manifest"]
    retry_manifest = retried["terminal_manifest"]
    adopted_manifest = adopted["terminal_manifest"]
    assert isinstance(first_manifest, dict)
    assert isinstance(retry_manifest, dict)
    assert isinstance(adopted_manifest, dict)
    assert retry_manifest["created"] is False
    assert adopted_manifest["created"] is False
    assert retry_manifest["fingerprint"] == first_manifest["fingerprint"]
    assert adopted_manifest["fingerprint"] == first_manifest["fingerprint"]
    assert first._hkel_terminal_reference_issuance == {}
    assert second._hkel_terminal_reference_issuance == {}


@pytest.mark.parametrize("code", ["NOT_APPLICABLE", "ARBITRARY_TERMINAL_CODE"])
def test_hkel_terminal_manifest_rejects_unproducible_terminal_codes(code: str) -> None:
    """Only source-derived absence and actual OfficialFetchCode values can be retained."""
    transport = _Transport()
    activities, vault = _activities(transport)
    inventory = activities._capture_current_hkel_inventory()
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        pipeline.project_hkel_current_inventory(inventory, register=activities._register),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt = activities._begin_hkel_terminal_attempt(plan)
    outcomes = _vault_backed_complete_hkel_outcomes(plan, vault, activities, attempt)
    captured = next(outcome for outcome in outcomes if outcome["evidence"] is not None)
    captured["code"] = code
    captured["evidence"] = None
    captured["failure_code"] = None

    with pytest.raises(pipeline.AcquisitionPipelineError, match="terminal"):
        activities._retain_hkel_evidence_manifest(plan, outcomes, attempt)

    assert not any(key.startswith("poc/report/hkel-evidence-attempt/") for key in vault.writes)


@pytest.mark.parametrize(
    ("code", "failure_code"),
    [
        ("SOURCE_UNAVAILABLE", "ARBITRARY_FAILURE"),
        ("SOURCE_CONTRACT_CHANGED", "BOUNDED_TRANSPORT_FAILURE"),
        ("UNSAFE_RESPONSE", "MEDIA_TYPE_DRIFT"),
    ],
)
def test_hkel_terminal_manifest_rejects_codes_with_wrong_producer_failure_shape(
    code: str,
    failure_code: str,
) -> None:
    """Terminal failures retain only the exact code/failure combinations their producer emits."""
    transport = _Transport()
    activities, vault = _activities(transport)
    inventory = activities._capture_current_hkel_inventory()
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        pipeline.project_hkel_current_inventory(inventory, register=activities._register),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt = activities._begin_hkel_terminal_attempt(plan)
    outcomes = _vault_backed_complete_hkel_outcomes(plan, vault, activities, attempt)
    captured = next(outcome for outcome in outcomes if outcome["evidence"] is not None)
    captured["code"] = code
    captured["evidence"] = None
    captured["failure_code"] = failure_code

    with pytest.raises(pipeline.AcquisitionPipelineError, match="failure"):
        activities._retain_hkel_evidence_manifest(plan, outcomes, attempt)

    assert activities._hkel_terminal_reference_issuance == {}
    assert not any(key.startswith("poc/report/hkel-evidence-attempt/") for key in vault.writes)


def test_hkel_terminal_manifest_rejects_removed_issued_failure_isolation() -> None:
    """A changed-result isolation cannot be omitted at terminal accounting."""
    transport = _Transport(changed_endpoint="sep_00000000000000000000000000000000000000000000000a")
    activities, _vault = _activities(transport)
    inventory = activities._capture_current_hkel_inventory()
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        pipeline.project_hkel_current_inventory(inventory, register=activities._register),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt = activities._begin_hkel_terminal_attempt(plan)
    outcomes = [
        activities._capture_hkel_evidence_member(member, attempt) for member in plan.members
    ]
    changed = next(outcome for outcome in outcomes if outcome["code"] == "SOURCE_CONTRACT_CHANGED")
    assert changed["isolated_response"] is not None
    changed["isolated_response"] = None

    with pytest.raises(pipeline.AcquisitionPipelineError, match="issued"):
        activities._retain_hkel_evidence_manifest(plan, outcomes, attempt)


def test_hkel_terminal_manifest_rejects_altered_allowed_failure_code() -> None:
    """A caller cannot exchange one allowed producer failure for another within an attempt."""
    transport = _Transport(changed_endpoint="sep_00000000000000000000000000000000000000000000000a")
    activities, _vault = _activities(transport)
    inventory = activities._capture_current_hkel_inventory()
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        pipeline.project_hkel_current_inventory(inventory, register=activities._register),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt = activities._begin_hkel_terminal_attempt(plan)
    outcomes = [
        activities._capture_hkel_evidence_member(member, attempt) for member in plan.members
    ]
    changed = next(outcome for outcome in outcomes if outcome["code"] == "SOURCE_CONTRACT_CHANGED")
    assert changed["failure_code"] == "STATUS_OR_REDIRECT_DRIFT"
    changed["failure_code"] = "MEDIA_TYPE_DRIFT"

    with pytest.raises(pipeline.AcquisitionPipelineError, match="issued"):
        activities._retain_hkel_evidence_manifest(plan, outcomes, attempt)


@pytest.mark.parametrize(
    "field",
    [
        "endpoint_id",
        "endpoint_version",
        "source_id",
        "language",
        "locator",
        "resource_id",
        "version_signal",
        "status_signal",
        "declared_sha256",
        "archive_member",
        "inventory_member_fingerprint",
    ],
)
def test_hkel_terminal_manifest_rejects_post_issuance_provenance_mutation(
    field: str,
) -> None:
    """Every worker-issued provenance primitive remains exact through terminal retention."""
    activities, vault = _activities(_Transport())
    inventory = activities._capture_current_hkel_inventory()
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        pipeline.project_hkel_current_inventory(inventory, register=activities._register),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt = activities._begin_hkel_terminal_attempt(plan)
    outcomes = [
        activities._capture_hkel_evidence_member(member, attempt) for member in plan.members
    ]
    captured = next(outcome for outcome in outcomes if outcome["evidence"] is not None)
    captured[field] = "FORGED-POST-ISSUANCE"

    with pytest.raises(pipeline.AcquisitionPipelineError, match="HKeL"):
        activities._retain_hkel_evidence_manifest(plan, outcomes, attempt)

    assert activities._hkel_terminal_reference_issuance == {}
    assert not any(key.startswith("poc/report/hkel-evidence-attempt/") for key in vault.writes)


@pytest.mark.parametrize(
    "field",
    [
        "archive_member",
        "artifact_id",
        "code",
        "declared_sha256",
        "endpoint_id",
        "endpoint_version",
        "evidence",
        "failure_code",
        "instrument_id",
        "inventory_member_fingerprint",
        "isolated_response",
        "language",
        "locator",
        "resource_id",
        "role",
        "source_disposition",
        "source_id",
        "status_signal",
        "version_signal",
    ],
)
def test_hkel_terminal_manifest_rejects_missing_or_unknown_worker_outcome_fields(
    field: str,
) -> None:
    """Every required terminal-member field is retained through terminal validation."""
    activities, vault = _activities(_Transport())
    inventory = activities._capture_current_hkel_inventory()
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        pipeline.project_hkel_current_inventory(inventory, register=activities._register),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt = activities._begin_hkel_terminal_attempt(plan)
    outcomes = [
        activities._capture_hkel_evidence_member(member, attempt) for member in plan.members
    ]
    captured = next(outcome for outcome in outcomes if outcome["evidence"] is not None)
    del captured[field]

    with pytest.raises(pipeline.AcquisitionPipelineError, match="HKeL"):
        activities._retain_hkel_evidence_manifest(plan, outcomes, attempt)

    assert activities._hkel_terminal_reference_issuance == {}
    assert not any(key.startswith("poc/report/hkel-evidence-attempt/") for key in vault.writes)


def test_hkel_terminal_manifest_rejects_unknown_secret_bearing_worker_outcome_field() -> None:
    """An unissued outcome field cannot enter the immutable terminal manifest."""
    activities, vault = _activities(_Transport())
    inventory = activities._capture_current_hkel_inventory()
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        pipeline.project_hkel_current_inventory(inventory, register=activities._register),
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt = activities._begin_hkel_terminal_attempt(plan)
    outcomes = [
        activities._capture_hkel_evidence_member(member, attempt) for member in plan.members
    ]
    captured = next(outcome for outcome in outcomes if outcome["evidence"] is not None)
    captured["secret_bearing_field"] = "TOP-SECRET-UNISSUED"

    with pytest.raises(pipeline.AcquisitionPipelineError, match="HKeL"):
        activities._retain_hkel_evidence_manifest(plan, outcomes, attempt)

    assert activities._hkel_terminal_reference_issuance == {}
    assert not any(key.startswith("poc/report/hkel-evidence-attempt/") for key in vault.writes)


def test_caller_artifact_contract_stops_before_any_transport() -> None:
    """Caller-selected artifacts are rejected before inventory or item transport."""
    transport = _Transport()
    activities, _vault = _activities(transport)

    with pytest.raises(pipeline.AcquisitionPipelineError):
        activities.capture_hkel_evidence(
            ActivityContext("hkel", 1),
            _caller_artifact_payload(),
        )

    assert transport.calls == []


def test_unverified_immutable_write_cannot_report_hkel_capture_success() -> None:
    """A false vault receipt stops before a terminal success can be returned."""
    transport = _Transport()
    activities, _vault = _activities(transport, read_back_verified=False)

    with pytest.raises(pipeline.AcquisitionPipelineError, match="read-back"):
        _planned_payload(activities)


def test_hkel_capture_instruction_rejects_unknown_fields_before_transport() -> None:
    """The schedulable activity must accept only a frozen plan description."""
    invalid: dict[str, JsonValue] = {
        "instrument_id": "hk-cap-001",
        "observation_cutoff": "2026-08-25T00:00:00Z",
        "artifacts": [],
        "url": "https://outside.invalid/",
    }

    with pytest.raises(pipeline.AcquisitionPipelineError):
        pipeline.HkelEvidenceInstruction.from_json(invalid)


def test_hkel_capture_instruction_rejects_caller_artifact_authority() -> None:
    """Only a prior source-byte-derived plan may choose artifact membership."""
    with pytest.raises(pipeline.AcquisitionPipelineError, match="caller artifact"):
        pipeline.HkelEvidenceInstruction.from_json(_caller_artifact_payload())


def test_hkel_terminal_manifest_rejects_missing_or_unplanned_outcomes() -> None:
    """A caller cannot write a complete terminal manifest for an empty outcome set."""
    transport = _Transport()
    activities, _vault = _activities(transport)
    inventory = activities._capture_current_hkel_inventory()
    projection = pipeline.project_hkel_current_inventory(inventory, register=activities._register)
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        projection,
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt = activities._begin_hkel_terminal_attempt(plan)

    with pytest.raises(pipeline.AcquisitionPipelineError, match="outcomes"):
        activities._retain_hkel_evidence_manifest(plan, [], attempt)


def test_hkel_completeness_treats_source_proved_not_published_as_accounted() -> None:
    """A source-proved no-publication fact is successful accounting, not a failed fetch."""
    transport = _Transport()
    activities, vault = _activities(transport)
    inventory = activities._capture_current_hkel_inventory()
    projection = pipeline.project_hkel_current_inventory(inventory, register=activities._register)
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        projection,
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt = activities._begin_hkel_terminal_attempt(plan)
    outcomes: list[dict[str, object]] = [
        pipeline._hkel_terminal_member_projection(
            member,
            code=(
                "NOT_PUBLISHED" if member.role is HkelEvidenceRole.EDITORIAL_RECORD else "CAPTURED"
            ),
            evidence=(
                None
                if member.role is HkelEvidenceRole.EDITORIAL_RECORD
                else _retained_hkel_reference(vault, member, member.artifact_id.encode())
            ),
            failure_code=None,
            isolated_response=None,
        )
        for member in plan.members
    ]
    for member, outcome in zip(plan.members, outcomes, strict=True):
        evidence = outcome["evidence"]
        if evidence is not None:
            activities._issue_hkel_terminal_reference(member, evidence, "evidence", attempt)
        activities._issue_hkel_terminal_outcome(member, outcome, attempt)

    assert activities._hkel_evidence_is_complete(plan, outcomes, attempt) is True
    activities._consume_hkel_terminal_attempt(attempt)


def test_hkel_complete_manifest_rejects_real_vault_reference_not_issued_for_member() -> None:
    """An existing object cannot be relabelled as a capture outcome by its caller."""
    transport = _Transport()
    activities, vault = _activities(transport)
    inventory = activities._capture_current_hkel_inventory()
    projection = pipeline.project_hkel_current_inventory(inventory, register=activities._register)
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        projection,
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    outcomes = _vault_backed_complete_hkel_outcomes(plan, vault)
    attempt = activities._begin_hkel_terminal_attempt(plan)

    with pytest.raises(pipeline.AcquisitionPipelineError, match="issued"):
        activities._retain_hkel_evidence_manifest(plan, outcomes, attempt)


def _retained_hkel_reference(
    vault: _Vault,
    member: HkelEvidenceArtifact,
    content: bytes,
) -> dict[str, object]:
    """Issue one real fake-vault receipt for an exact planned captured member."""
    fingerprint = f"sha256:{sha256(content).hexdigest()}"
    receipt = vault.conditional_create(
        f"poc/source/inventory/{member.endpoint_id}/{fingerprint.removeprefix('sha256:')}",
        content,
        object(),
    )
    return {
        "byte_length": receipt.reference.byte_length,
        "created": receipt.created,
        "fingerprint": receipt.reference.fingerprint,
        "logical_key": receipt.reference.logical_key,
        "read_back_verified": receipt.read_back_verified,
        "vault": receipt.reference.vault.value,
        "version_id": receipt.reference.version_id,
    }


def _vault_backed_complete_hkel_outcomes(
    plan: HkelEvidencePlan,
    vault: _Vault,
    activities: pipeline.AcquisitionActivities | None = None,
    attempt: pipeline._HkelAttemptIssuance | None = None,
) -> list[dict[str, object]]:
    """Make one complete accounting set whose captured references really exist."""
    if activities is not None and attempt is None:
        message = "issued test outcomes require one explicit attempt"
        raise AssertionError(message)
    outcomes: list[dict[str, object]] = []
    for member in plan.members:
        if member.role is HkelEvidenceRole.EDITORIAL_RECORD:
            outcomes.append(
                pipeline._hkel_terminal_member_projection(
                    member,
                    code="NOT_PUBLISHED",
                    evidence=None,
                    failure_code=None,
                    isolated_response=None,
                )
            )
            continue
        content = f"retained {member.artifact_id}".encode()
        evidence = _retained_hkel_reference(vault, member, content)
        if activities is not None and attempt is not None:
            activities._issue_hkel_terminal_reference(member, evidence, "evidence", attempt)
        outcomes.append(
            pipeline._hkel_terminal_member_projection(
                member,
                code="CAPTURED",
                evidence=evidence,
                failure_code=None,
                isolated_response=None,
            )
        )
    if activities is not None and attempt is not None:
        for member, outcome in zip(plan.members, outcomes, strict=True):
            activities._issue_hkel_terminal_outcome(member, outcome, attempt)
    return outcomes


def _mutate_hkel_evidence_reference(
    mutation: str,
    plan: HkelEvidencePlan,
    vault: _Vault,
    outcomes: list[dict[str, object]],
) -> None:
    """Apply one hostile alteration to otherwise exact retained-member accounting."""
    captured = [outcome for outcome in outcomes if outcome["evidence"] is not None]
    assert len(captured) >= 2
    first = captured[0]
    second = captured[1]
    evidence = checked_json_value(first["evidence"])
    assert isinstance(evidence, dict)
    first["evidence"] = evidence
    direct: dict[str, tuple[str, JsonValue]] = {
        "malformed_digest": ("fingerprint", "sha256:not-a-digest"),
        "zero_length": ("byte_length", 0),
        "wrong_length": ("byte_length", 1),
        "wrong_key": ("logical_key", "poc/source/inventory/forged/" + "a" * 64),
        "wrong_version": ("version_id", "v" + "f" * 64),
        "wrong_hash": ("fingerprint", "sha256:" + "c" * 64),
        "forged_read_back": ("read_back_verified", False),
    }
    if mutation in direct:
        field, value = direct[mutation]
        evidence[field] = value
    elif mutation == "nonexistent_object":
        evidence["logical_key"] = f"poc/source/inventory/{plan.members[0].endpoint_id}/" + "b" * 64
    elif mutation == "wrong_bytes":
        logical_key = evidence["logical_key"]
        assert isinstance(logical_key, str)
        vault.writes[logical_key] = b"tampered"
    elif mutation == "swapped_reference":
        second_evidence = checked_json_value(second["evidence"])
        assert isinstance(second_evidence, dict)
        first["evidence"] = dict(second_evidence)
    elif mutation == "duplicate_reference":
        second["evidence"] = dict(evidence)
    elif mutation == "isolation_as_evidence":
        first["isolated_response"] = dict(evidence)
    else:  # pragma: no cover - parametrization is closed below.
        raise AssertionError(mutation)


@pytest.mark.parametrize(
    "mutation",
    [
        "malformed_digest",
        "zero_length",
        "wrong_length",
        "wrong_key",
        "wrong_version",
        "nonexistent_object",
        "wrong_hash",
        "wrong_bytes",
        "forged_read_back",
        "swapped_reference",
        "duplicate_reference",
        "isolation_as_evidence",
    ],
)
def test_hkel_complete_manifest_rejects_forged_or_misbinding_evidence_references(
    mutation: str,
) -> None:
    """Completion is based on exact readable immutable bytes, never receipt-shaped input."""
    transport = _Transport()
    activities, vault = _activities(transport)
    inventory = activities._capture_current_hkel_inventory()
    projection = pipeline.project_hkel_current_inventory(inventory, register=activities._register)
    plan = pipeline.build_hkel_evidence_plan_from_projection(
        projection,
        instrument_id="hk-cap-001",
        cutoff=_CUTOFF,
        register=activities._register,
    )
    attempt = activities._begin_hkel_terminal_attempt(plan)
    outcomes = _vault_backed_complete_hkel_outcomes(plan, vault, activities, attempt)
    _mutate_hkel_evidence_reference(mutation, plan, vault, outcomes)

    with pytest.raises(pipeline.AcquisitionPipelineError, match="HKeL"):
        activities._retain_hkel_evidence_manifest(plan, outcomes, attempt)

    assert not any(key.startswith("poc/report/hkel-evidence-attempt/") for key in vault.writes)
