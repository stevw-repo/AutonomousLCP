"""Fail-closed validation for the disabled V1 POC Ubuntu topology."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterable

TOPOLOGY_PATH = Path("infrastructure/poc/topology.json")
_DIGEST_REF = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
_SECRET_VALUE = re.compile(r"(?:^sk-[A-Za-z0-9]|BEGIN [A-Z ]*PRIVATE KEY|://[^/\s:]+:[^/@\s]+@)")
_EXPECTED_SERVICES = frozenset(
    {
        "acquisition-worker",
        "control-plane",
        "dts-general",
        "dts-promotion",
        "egress-model",
        "egress-promotion",
        "egress-source",
        "grafana",
        "legal-processing-worker",
        "otel-collector",
        "prometheus",
        "promotion-worker",
        "review-api",
        "sql-server",
        "vault-primary",
        "vault-recovery",
    }
)
_EXPECTED_DATABASES = ("AskLegalPocIntegration", "AskLegalPocOperational")
_EXPECTED_TOP_LEVEL_KEYS = frozenset(
    {
        "authoritative_audit",
        "databases",
        "host",
        "networks",
        "pinecone",
        "recovery_class",
        "scheduler_instances",
        "schema_version",
        "services",
        "status",
        "vaults",
    }
)
_EXPECTED_SERVICE_KEYS = frozenset(
    {
        "artifact_ref",
        "artifact_state",
        "credential_names",
        "enabled",
        "identity",
        "kind",
        "listeners",
        "networks",
        "outbound_profile",
        "service_id",
        "write_paths",
    }
)
_EXPECTED_LISTENER_KEYS = frozenset({"port", "scope"})
_EXPECTED_NETWORK_KEYS = frozenset({"internal", "members", "network_id"})
_EXPECTED_EGRESS_NETWORKS = frozenset(
    {"asklegal-egress-model", "asklegal-egress-promotion", "asklegal-egress-source"}
)
_EXPECTED_VAULT_KEYS = frozenset(
    {
        "bucket",
        "manifest_last_required",
        "object_lock_required",
        "root",
        "service_id",
        "sidecar",
        "versioning_required",
        "versions",
    }
)
_EXPECTED_SCHEDULER_KEYS = frozenset({"loss_result", "persistence", "service_id", "task_hubs"})
_PAIR_COUNT = 2
_MAX_PORT = 65_535
_MAX_TOPOLOGY_BYTES = 1_000_000
_TOPOLOGY_TOO_LARGE = "topology too large"
_TOPOLOGY_ROOT_TYPE = "topology root"
_APPLICATION_IDS = (
    "acquisition-worker",
    "control-plane",
    "legal-processing-worker",
    "promotion-worker",
    "review-api",
)
_REPOSITORY_SEGMENT = r"[a-z0-9]+(?:[._-][a-z0-9]+)*"
_CANDIDATE_IMAGE_REF = re.compile(
    rf"^(?P<repository>{_REPOSITORY_SEGMENT}(?::(?P<port>[1-9][0-9]{{0,4}}))?"
    rf"(?:/{_REPOSITORY_SEGMENT})+)@sha256:[0-9a-f]{{64}}$"
)
_CONTAINER_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9_.-]{0,126}[a-z0-9])?$")
_SYSTEMD_UNIT = re.compile(r"^[a-z0-9](?:[a-z0-9@_.-]{0,124}[a-z0-9])?\.service$")
_MAX_IMAGE_REFERENCE_LENGTH = 512


class _ContractErrorCode(StrEnum):
    CANDIDATE_IMAGE_REFERENCE_INVALID = "CANDIDATE_IMAGE_REFERENCE_INVALID"
    CANDIDATE_IMAGE_REPOSITORY_MISMATCH = "CANDIDATE_IMAGE_REPOSITORY_MISMATCH"
    CANDIDATE_PIN_INPUT_INVALID = "CANDIDATE_PIN_INPUT_INVALID"
    CANDIDATE_PIN_INVENTORY_INVALID = "CANDIDATE_PIN_INVENTORY_INVALID"
    DESIRED_APPLICATION_TOPOLOGY_INVALID = "DESIRED_APPLICATION_TOPOLOGY_INVALID"
    INVENTORY_COMPLETENESS_INVALID = "INVENTORY_COMPLETENESS_INVALID"
    OBSERVED_CONTAINER_INPUT_INVALID = "OBSERVED_CONTAINER_INPUT_INVALID"


class ApplicationContainerContractError(ValueError):
    """One closed, input-free candidate-topology contract failure."""

    code: str

    def __init__(self, code: _ContractErrorCode) -> None:
        """Create one error from a closed internal code only."""
        self.code = code.value
        super().__init__(self.code)


class ContainerOwnership(StrEnum):
    """Closed ownership observation for one known pipeline container."""

    SYSTEMD = "SYSTEMD"
    UNKNOWN = "UNKNOWN"
    UNSUPERVISED = "UNSUPERVISED"


class ContainerAccountingState(StrEnum):
    """Exactly one reconciliation class for each observed pipeline container."""

    DUPLICATE = "DUPLICATE"
    DRIFTED = "DRIFTED"
    MATCHED = "MATCHED"
    ORPHAN = "ORPHAN"
    OWNERSHIP_UNKNOWN = "OWNERSHIP_UNKNOWN"
    UNSUPERVISED = "UNSUPERVISED"


class ContainerDriftCode(StrEnum):
    """Closed material drift within one otherwise canonical application name."""

    IMAGE = "IMAGE"
    SYSTEMD_UNIT = "SYSTEMD_UNIT"


class ApplicationContainerBlocker(StrEnum):
    """Closed blockers for only the application-container reconciliation dimension."""

    CONTAINER_INVENTORY_INCOMPLETE = "CONTAINER_INVENTORY_INCOMPLETE"
    MISSING_APPLICATION_CONTAINERS = "MISSING_APPLICATION_CONTAINERS"
    DUPLICATE_PIPELINE_CONTAINERS = "DUPLICATE_PIPELINE_CONTAINERS"
    CONTAINER_OWNERSHIP_UNKNOWN = "CONTAINER_OWNERSHIP_UNKNOWN"
    UNSUPERVISED_APPLICATION_CONTAINERS = "UNSUPERVISED_APPLICATION_CONTAINERS"
    APPLICATION_IMAGE_DRIFT = "APPLICATION_IMAGE_DRIFT"
    APPLICATION_SYSTEMD_UNIT_DRIFT = "APPLICATION_SYSTEMD_UNIT_DRIFT"
    ORPHAN_PIPELINE_CONTAINERS = "ORPHAN_PIPELINE_CONTAINERS"


@dataclass(frozen=True, slots=True)
class CandidateApplicationImagePin:
    """Caller-owned structural image candidate; never image-admission evidence."""

    application_id: str
    candidate_image_reference: str


@dataclass(frozen=True, slots=True)
class DesiredApplicationContainer:
    """One derived immutable candidate application-container declaration."""

    application_id: str
    image_repository: str
    candidate_image_reference: str
    container_name: str
    systemd_unit: str


@dataclass(frozen=True, slots=True)
class V1ApplicationContainerTopology:
    """Detached exact five-application candidate topology, without admission."""

    applications: tuple[DesiredApplicationContainer, ...]

    def to_json_bytes(self) -> bytes:
        """Return canonical detached bytes for comparison and later evidence binding."""
        payload = {
            "applications": [
                {
                    "application_id": item.application_id,
                    "candidate_image_reference": item.candidate_image_reference,
                    "container_name": item.container_name,
                    "image_repository": item.image_repository,
                    "systemd_unit": item.systemd_unit,
                }
                for item in self.applications
            ],
            "schema_version": 1,
            "state": "CANDIDATE_STRUCTURAL_ONLY",
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class ObservedPipelineContainer:
    """Narrow caller-owned projection of one container already classified as pipeline."""

    container_name: str
    image_reference: str
    systemd_unit: str | None
    ownership: ContainerOwnership


@dataclass(frozen=True, slots=True)
class PipelineContainerAccounting:
    """Exactly one closed classification for one observed inventory row."""

    container_name: str
    state: ContainerAccountingState
    drift_codes: tuple[ContainerDriftCode, ...]


@dataclass(frozen=True, slots=True)
class ApplicationContainerReconciliation:
    """Pure dimensional comparison; not host admission or mutation authority."""

    inventory_complete: bool
    observed_accounting: tuple[PipelineContainerAccounting, ...]
    matched_application_containers: tuple[str, ...]
    missing_application_containers: tuple[str, ...]
    drifted_application_containers: tuple[str, ...]
    duplicate_pipeline_containers: tuple[str, ...]
    ownership_unknown_containers: tuple[str, ...]
    unsupervised_application_containers: tuple[str, ...]
    orphan_pipeline_containers: tuple[str, ...]
    blocker_codes: tuple[ApplicationContainerBlocker, ...]
    clean: bool
    mutation_authorized: bool

    def to_json_bytes(self) -> bytes:
        """Return deterministic names-and-closed-codes reconciliation bytes."""
        payload = {
            "blocker_codes": [code.value for code in self.blocker_codes],
            "clean": self.clean,
            "drifted_application_containers": list(self.drifted_application_containers),
            "duplicate_pipeline_containers": list(self.duplicate_pipeline_containers),
            "inventory_complete": self.inventory_complete,
            "matched_application_containers": list(self.matched_application_containers),
            "missing_application_containers": list(self.missing_application_containers),
            "mutation_authorized": self.mutation_authorized,
            "observed_accounting": [
                {
                    "container_name": item.container_name,
                    "drift_codes": [code.value for code in item.drift_codes],
                    "state": item.state.value,
                }
                for item in self.observed_accounting
            ],
            "orphan_pipeline_containers": list(self.orphan_pipeline_containers),
            "ownership_unknown_containers": list(self.ownership_unknown_containers),
            "schema_version": 1,
            "unsupervised_application_containers": list(self.unsupervised_application_containers),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class _CandidatePinSnapshot:
    application_id: str
    candidate_image_reference: str


@dataclass(frozen=True, slots=True)
class _DesiredContainerSnapshot:
    application_id: str
    image_repository: str
    candidate_image_reference: str
    container_name: str
    systemd_unit: str


@dataclass(frozen=True, slots=True)
class _ObservedContainerSnapshot:
    container_name: str
    image_reference: str
    systemd_unit: str | None
    ownership: ContainerOwnership


def _candidate_repository(reference: str) -> str | None:
    if len(reference) > _MAX_IMAGE_REFERENCE_LENGTH:
        return None
    match = _CANDIDATE_IMAGE_REF.fullmatch(reference)
    if match is None:
        return None
    port = match.group("port")
    if port is not None and int(port) > _MAX_PORT:
        return None
    return match.group("repository")


def _snapshot_candidate_pins(
    pins: Iterable[CandidateApplicationImagePin],
) -> tuple[_CandidatePinSnapshot, ...]:
    try:
        return _raw_candidate_pin_snapshots(pins)
    except Exception:  # noqa: BLE001, S110 - discard every ordinary hostile failure
        pass
    raise ApplicationContainerContractError(_ContractErrorCode.CANDIDATE_PIN_INPUT_INVALID)


def _raw_candidate_pin_snapshots(
    pins: Iterable[CandidateApplicationImagePin],
) -> tuple[_CandidatePinSnapshot, ...]:
    snapshots: list[_CandidatePinSnapshot] = []
    for pin in pins:
        if type(pin) is not CandidateApplicationImagePin:
            raise TypeError
        application_id = object.__getattribute__(pin, "application_id")
        reference = object.__getattribute__(pin, "candidate_image_reference")
        if type(application_id) is not str or type(reference) is not str:
            raise TypeError
        snapshots.append(_CandidatePinSnapshot(application_id, reference))
    return tuple(snapshots)


def build_v1_application_container_topology(
    pins: Iterable[CandidateApplicationImagePin],
) -> V1ApplicationContainerTopology:
    """Freeze exact candidate pins into derived five-application desired state."""
    snapshots = _snapshot_candidate_pins(pins)
    application_ids = tuple(item.application_id for item in snapshots)
    if (
        len(application_ids) != len(_APPLICATION_IDS)
        or len(application_ids) != len(set(application_ids))
        or frozenset(application_ids) != frozenset(_APPLICATION_IDS)
    ):
        raise ApplicationContainerContractError(_ContractErrorCode.CANDIDATE_PIN_INVENTORY_INVALID)
    applications: list[DesiredApplicationContainer] = []
    for pin in snapshots:
        repository = _candidate_repository(pin.candidate_image_reference)
        if repository is None:
            raise ApplicationContainerContractError(
                _ContractErrorCode.CANDIDATE_IMAGE_REFERENCE_INVALID
            )
        if repository.rsplit("/", 1)[-1] != pin.application_id:
            raise ApplicationContainerContractError(
                _ContractErrorCode.CANDIDATE_IMAGE_REPOSITORY_MISMATCH
            )
        container_name = f"asklegal-{pin.application_id}"
        applications.append(
            DesiredApplicationContainer(
                application_id=pin.application_id,
                image_repository=repository,
                candidate_image_reference=pin.candidate_image_reference,
                container_name=container_name,
                systemd_unit=f"{container_name}.service",
            )
        )
    return V1ApplicationContainerTopology(
        applications=tuple(sorted(applications, key=lambda item: item.application_id))
    )


def _snapshot_desired_topology(
    topology: V1ApplicationContainerTopology,
) -> tuple[_DesiredContainerSnapshot, ...]:
    try:
        result = _raw_desired_container_snapshots(topology)
    except Exception:  # noqa: BLE001 - normalize every ordinary forged-object failure
        result = ()
    if not result:
        raise ApplicationContainerContractError(
            _ContractErrorCode.DESIRED_APPLICATION_TOPOLOGY_INVALID
        )
    if tuple(item.application_id for item in result) != _APPLICATION_IDS:
        raise ApplicationContainerContractError(
            _ContractErrorCode.DESIRED_APPLICATION_TOPOLOGY_INVALID
        )
    for item in result:
        repository = _candidate_repository(item.candidate_image_reference)
        container_name = f"asklegal-{item.application_id}"
        if (
            repository is None
            or repository != item.image_repository
            or repository.rsplit("/", 1)[-1] != item.application_id
            or item.container_name != container_name
            or item.systemd_unit != f"{container_name}.service"
        ):
            raise ApplicationContainerContractError(
                _ContractErrorCode.DESIRED_APPLICATION_TOPOLOGY_INVALID
            )
    return result


def _raw_desired_container_snapshots(
    topology: V1ApplicationContainerTopology,
) -> tuple[_DesiredContainerSnapshot, ...]:
    snapshots: list[_DesiredContainerSnapshot] = []
    if type(topology) is not V1ApplicationContainerTopology:
        raise TypeError
    raw_applications = object.__getattribute__(topology, "applications")
    if type(raw_applications) is not tuple:
        raise TypeError
    applications = cast("tuple[object, ...]", raw_applications)
    for item in applications:
        if type(item) is not DesiredApplicationContainer:
            raise TypeError
        values = (
            object.__getattribute__(item, "application_id"),
            object.__getattribute__(item, "image_repository"),
            object.__getattribute__(item, "candidate_image_reference"),
            object.__getattribute__(item, "container_name"),
            object.__getattribute__(item, "systemd_unit"),
        )
        if not all(type(value) is str for value in values):
            raise TypeError
        snapshots.append(_DesiredContainerSnapshot(*values))
    return tuple(snapshots)


def _snapshot_observed_containers(
    observed: Iterable[ObservedPipelineContainer],
) -> tuple[_ObservedContainerSnapshot, ...]:
    try:
        return _raw_observed_container_snapshots(observed)
    except Exception:  # noqa: BLE001, S110 - discard every ordinary hostile failure
        pass
    raise ApplicationContainerContractError(_ContractErrorCode.OBSERVED_CONTAINER_INPUT_INVALID)


def _raw_observed_container_snapshots(
    observed: Iterable[ObservedPipelineContainer],
) -> tuple[_ObservedContainerSnapshot, ...]:
    snapshots: list[_ObservedContainerSnapshot] = []
    for item in observed:
        if type(item) is not ObservedPipelineContainer:
            raise TypeError
        container_name = object.__getattribute__(item, "container_name")
        image_reference = object.__getattribute__(item, "image_reference")
        systemd_unit = object.__getattribute__(item, "systemd_unit")
        ownership = object.__getattribute__(item, "ownership")
        if (
            type(container_name) is not str
            or type(image_reference) is not str
            or (systemd_unit is not None and type(systemd_unit) is not str)
            or type(ownership) is not ContainerOwnership
        ):
            raise TypeError
        snapshots.append(
            _ObservedContainerSnapshot(
                container_name,
                image_reference,
                systemd_unit,
                ownership,
            )
        )
    return tuple(snapshots)


def _validate_observed_containers(
    observed: tuple[_ObservedContainerSnapshot, ...],
) -> None:
    for item in observed:
        unit_is_valid = item.systemd_unit is None or _SYSTEMD_UNIT.fullmatch(item.systemd_unit)
        ownership_is_coherent = (item.ownership is ContainerOwnership.SYSTEMD) == (
            item.systemd_unit is not None
        )
        if (
            _CONTAINER_NAME.fullmatch(item.container_name) is None
            or _candidate_repository(item.image_reference) is None
            or not unit_is_valid
            or not ownership_is_coherent
        ):
            raise ApplicationContainerContractError(
                _ContractErrorCode.OBSERVED_CONTAINER_INPUT_INVALID
            )


def _account_observed_containers(
    desired: tuple[_DesiredContainerSnapshot, ...],
    observed: tuple[_ObservedContainerSnapshot, ...],
) -> tuple[PipelineContainerAccounting, ...]:
    desired_by_name = {item.container_name: item for item in desired}
    name_counts: dict[str, int] = {}
    for item in observed:
        name_counts[item.container_name] = name_counts.get(item.container_name, 0) + 1
    accounting: list[PipelineContainerAccounting] = []
    for item in sorted(
        observed,
        key=lambda value: (
            value.container_name,
            value.image_reference,
            value.systemd_unit or "",
            value.ownership.value,
        ),
    ):
        state: ContainerAccountingState
        drift_codes: tuple[ContainerDriftCode, ...] = ()
        expected = desired_by_name.get(item.container_name)
        if name_counts[item.container_name] > 1:
            state = ContainerAccountingState.DUPLICATE
        elif item.ownership is ContainerOwnership.UNKNOWN:
            state = ContainerAccountingState.OWNERSHIP_UNKNOWN
        elif expected is None:
            state = ContainerAccountingState.ORPHAN
        elif item.ownership is ContainerOwnership.UNSUPERVISED:
            state = ContainerAccountingState.UNSUPERVISED
        else:
            drift: list[ContainerDriftCode] = []
            if item.image_reference != expected.candidate_image_reference:
                drift.append(ContainerDriftCode.IMAGE)
            if item.systemd_unit != expected.systemd_unit:
                drift.append(ContainerDriftCode.SYSTEMD_UNIT)
            drift_codes = tuple(drift)
            state = (
                ContainerAccountingState.DRIFTED
                if drift_codes
                else ContainerAccountingState.MATCHED
            )
        accounting.append(
            PipelineContainerAccounting(
                container_name=item.container_name,
                state=state,
                drift_codes=drift_codes,
            )
        )
    return tuple(accounting)


def _names_for_state(
    accounting: tuple[PipelineContainerAccounting, ...],
    state: ContainerAccountingState,
) -> tuple[str, ...]:
    return tuple(sorted({item.container_name for item in accounting if item.state is state}))


def evaluate_v1_application_containers(
    desired: V1ApplicationContainerTopology,
    observed: Iterable[ObservedPipelineContainer],
    *,
    inventory_complete: bool,
) -> ApplicationContainerReconciliation:
    """Compare a detached narrow inventory without inspecting or changing a host."""
    if type(inventory_complete) is not bool:
        raise ApplicationContainerContractError(_ContractErrorCode.INVENTORY_COMPLETENESS_INVALID)
    desired_snapshot = _snapshot_desired_topology(desired)
    observed_snapshot = _snapshot_observed_containers(observed)
    _validate_observed_containers(observed_snapshot)
    accounting = _account_observed_containers(desired_snapshot, observed_snapshot)
    matched = _names_for_state(accounting, ContainerAccountingState.MATCHED)
    drifted = _names_for_state(accounting, ContainerAccountingState.DRIFTED)
    duplicates = _names_for_state(accounting, ContainerAccountingState.DUPLICATE)
    ownership_unknown = tuple(
        sorted(
            {
                item.container_name
                for item in observed_snapshot
                if item.ownership is ContainerOwnership.UNKNOWN
            }
        )
    )
    unsupervised = _names_for_state(accounting, ContainerAccountingState.UNSUPERVISED)
    orphans = _names_for_state(accounting, ContainerAccountingState.ORPHAN)
    observed_names = {item.container_name for item in observed_snapshot}
    missing = tuple(
        sorted(
            item.container_name
            for item in desired_snapshot
            if item.container_name not in observed_names
        )
    )
    drift_codes = {code for item in accounting for code in item.drift_codes}
    blockers: list[ApplicationContainerBlocker] = []
    effective_complete = inventory_complete and not ownership_unknown
    if not effective_complete:
        blockers.append(ApplicationContainerBlocker.CONTAINER_INVENTORY_INCOMPLETE)
    if missing:
        blockers.append(ApplicationContainerBlocker.MISSING_APPLICATION_CONTAINERS)
    if duplicates:
        blockers.append(ApplicationContainerBlocker.DUPLICATE_PIPELINE_CONTAINERS)
    if ownership_unknown:
        blockers.append(ApplicationContainerBlocker.CONTAINER_OWNERSHIP_UNKNOWN)
    if unsupervised:
        blockers.append(ApplicationContainerBlocker.UNSUPERVISED_APPLICATION_CONTAINERS)
    if ContainerDriftCode.IMAGE in drift_codes:
        blockers.append(ApplicationContainerBlocker.APPLICATION_IMAGE_DRIFT)
    if ContainerDriftCode.SYSTEMD_UNIT in drift_codes:
        blockers.append(ApplicationContainerBlocker.APPLICATION_SYSTEMD_UNIT_DRIFT)
    if orphans:
        blockers.append(ApplicationContainerBlocker.ORPHAN_PIPELINE_CONTAINERS)
    blocker_codes = tuple(blockers)
    return ApplicationContainerReconciliation(
        inventory_complete=effective_complete,
        observed_accounting=accounting,
        matched_application_containers=matched,
        missing_application_containers=missing,
        drifted_application_containers=drifted,
        duplicate_pipeline_containers=duplicates,
        ownership_unknown_containers=ownership_unknown,
        unsupervised_application_containers=unsupervised,
        orphan_pipeline_containers=orphans,
        blocker_codes=blocker_codes,
        clean=(
            not blocker_codes
            and len(matched) == len(_APPLICATION_IDS)
            and len(accounting) == len(_APPLICATION_IDS)
        ),
        mutation_authorized=False,
    )


class TopologyCode(StrEnum):
    """Closed topology validation findings."""

    ARTIFACT = "ARTIFACT"
    AUTHORITY = "AUTHORITY"
    CREDENTIAL = "CREDENTIAL"
    DUPLICATE = "DUPLICATE"
    HOST = "HOST"
    INVENTORY = "INVENTORY"
    NETWORK = "NETWORK"
    RECOVERY = "RECOVERY"
    SCHEDULER = "SCHEDULER"
    SECRET = "SECRET"
    SURFACE = "SURFACE"
    VAULT = "VAULT"


@dataclass(frozen=True, slots=True)
class TopologyFinding:
    """One stable fail-closed topology finding."""

    code: TopologyCode
    detail: str


@dataclass(frozen=True, slots=True)
class TopologyReport:
    """One successful closed topology summary."""

    services: int
    networks: int
    credentials: int
    pinned_artifacts: int
    pins_required: int


def _objects(value: object, label: str) -> tuple[dict[str, object], ...]:
    items = _object_list(value)
    if items is None:
        raise ValueError(label)
    result: list[dict[str, object]] = []
    for item in items:
        document = _string_object(item)
        if document is None:
            raise ValueError(label)
        result.append(document)
    return tuple(result)


def _strings(value: object, label: str) -> tuple[str, ...]:
    items = _object_list(value)
    if items is None:
        raise ValueError(label)
    result: list[str] = []
    for item in items:
        if type(item) is not str or not item:
            raise ValueError(label)
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


def _text(value: object, label: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(label)
    return value


def _duplicates(values: Iterable[str]) -> bool:
    sequence = tuple(values)
    return len(sequence) != len(set(sequence))


def _secret_findings(value: object, path: str = "$") -> tuple[TopologyFinding, ...]:
    findings: list[TopologyFinding] = []
    document = _string_object(value)
    items = _object_list(value)
    if document is not None:
        forbidden_keys = {"password", "secret", "token", "api_key", "private_key"}
        for key, child in document.items():
            if key.lower() in forbidden_keys:
                findings.append(TopologyFinding(TopologyCode.SECRET, f"{path}.{key}"))
            findings.extend(_secret_findings(child, f"{path}.{key}"))
    elif items is not None:
        for index, child in enumerate(items):
            findings.extend(_secret_findings(child, f"{path}[{index}]"))
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        findings.append(TopologyFinding(TopologyCode.SECRET, path))
    return tuple(findings)


def _validate_host(document: dict[str, object]) -> tuple[TopologyFinding, ...]:
    host = _string_object(document.get("host"))
    if host is None:
        return (TopologyFinding(TopologyCode.HOST, "host"),)
    expected = {
        "os": "Ubuntu 24.04",
        "architecture": "x86_64",
        "minimum_ram_gib": 60,
        "physical_disk_count": 3,
        "minimum_ext4_capacity_tb": 3,
        "mac_runtime_dependency": False,
    }
    return () if host == expected else (TopologyFinding(TopologyCode.HOST, "exact host"),)


def _validate_artifact(service: dict[str, object], service_id: str) -> tuple[TopologyFinding, ...]:
    findings: list[TopologyFinding] = []
    state = service.get("artifact_state")
    artifact = service.get("artifact_ref")
    if service.get("enabled") is not False:
        findings.append(TopologyFinding(TopologyCode.ARTIFACT, f"{service_id} enabled"))
    if state == "PINNED":
        if not isinstance(artifact, str) or not _DIGEST_REF.fullmatch(artifact):
            findings.append(TopologyFinding(TopologyCode.ARTIFACT, service_id))
    elif state == "PIN_REQUIRED":
        if artifact is not None:
            findings.append(TopologyFinding(TopologyCode.ARTIFACT, service_id))
    else:
        findings.append(TopologyFinding(TopologyCode.ARTIFACT, service_id))
    if isinstance(artifact, str) and "latest" in artifact.lower():
        findings.append(TopologyFinding(TopologyCode.ARTIFACT, f"{service_id} latest"))
    return tuple(findings)


def _validate_service(service: dict[str, object]) -> tuple[TopologyFinding, ...]:
    findings: list[TopologyFinding] = []
    service_id = _text(service.get("service_id"), "service_id")
    if frozenset(service) != _EXPECTED_SERVICE_KEYS:
        findings.append(TopologyFinding(TopologyCode.INVENTORY, f"{service_id} schema"))
    findings.extend(_validate_artifact(service, service_id))
    for listener in _objects(service.get("listeners"), "listeners"):
        if frozenset(listener) != _EXPECTED_LISTENER_KEYS:
            findings.append(TopologyFinding(TopologyCode.SURFACE, f"{service_id} listener"))
        if listener.get("scope") not in {"CONTAINER_ONLY", "PRIVATE_HOST"}:
            findings.append(TopologyFinding(TopologyCode.SURFACE, service_id))
        port = listener.get("port")
        if type(port) is not int or not 1 <= port <= _MAX_PORT:
            findings.append(TopologyFinding(TopologyCode.SURFACE, f"{service_id} port"))
    credential_names = _strings(service.get("credential_names"), "credential_names")
    if _duplicates(credential_names):
        findings.append(TopologyFinding(TopologyCode.CREDENTIAL, service_id))
    return tuple(findings)


def _validate_services(
    services: tuple[dict[str, object], ...],
) -> tuple[TopologyFinding, ...]:
    findings: list[TopologyFinding] = []
    service_ids = tuple(_text(service.get("service_id"), "service_id") for service in services)
    identities = tuple(_text(service.get("identity"), "identity") for service in services)
    if _duplicates(service_ids) or _duplicates(identities):
        findings.append(TopologyFinding(TopologyCode.DUPLICATE, "service identity"))
    if frozenset(service_ids) != _EXPECTED_SERVICES:
        findings.append(TopologyFinding(TopologyCode.INVENTORY, "service inventory"))
    for service in services:
        findings.extend(_validate_service(service))
    return tuple(findings)


def _validate_networks(
    services: tuple[dict[str, object], ...],
    networks: tuple[dict[str, object], ...],
) -> tuple[TopologyFinding, ...]:
    findings: list[TopologyFinding] = []
    service_networks = {
        _text(service.get("service_id"), "service_id"): set(
            _strings(service.get("networks"), "networks")
        )
        for service in services
    }
    network_ids = tuple(_text(network.get("network_id"), "network_id") for network in networks)
    if _duplicates(network_ids):
        findings.append(TopologyFinding(TopologyCode.DUPLICATE, "network"))
    declared_networks = set(network_ids)
    if set().union(*service_networks.values()) != declared_networks:
        findings.append(TopologyFinding(TopologyCode.NETWORK, "network inventory"))
    for network in networks:
        network_id = _text(network.get("network_id"), "network_id")
        expected_internal = network_id not in _EXPECTED_EGRESS_NETWORKS
        if (
            frozenset(network) != _EXPECTED_NETWORK_KEYS
            or network.get("internal") is not expected_internal
        ):
            findings.append(TopologyFinding(TopologyCode.NETWORK, f"{network_id} schema"))
        members = set(_strings(network.get("members"), "members"))
        if not members <= _EXPECTED_SERVICES:
            findings.append(TopologyFinding(TopologyCode.NETWORK, f"{network_id} member"))
        for service_id in _EXPECTED_SERVICES:
            declared = network_id in service_networks.get(service_id, set())
            if declared != (service_id in members):
                findings.append(TopologyFinding(TopologyCode.NETWORK, f"{network_id}/{service_id}"))
    return tuple(findings)


def _validate_vaults(document: dict[str, object]) -> tuple[TopologyFinding, ...]:
    vaults = _objects(document.get("vaults"), "vaults")
    if len(vaults) != _PAIR_COUNT:
        return (TopologyFinding(TopologyCode.VAULT, "count"),)
    compared = ("service_id", "bucket", "root", "versions", "sidecar")
    findings: list[TopologyFinding] = []
    expected_service_ids = {"vault-primary", "vault-recovery"}
    if {_text(vault.get("service_id"), "service_id") for vault in vaults} != expected_service_ids:
        findings.append(TopologyFinding(TopologyCode.VAULT, "service inventory"))
    findings.extend(
        TopologyFinding(TopologyCode.VAULT, field)
        for field in compared
        if len({_text(vault.get(field), field) for vault in vaults}) != _PAIR_COUNT
    )
    for vault in vaults:
        if frozenset(vault) != _EXPECTED_VAULT_KEYS:
            findings.append(TopologyFinding(TopologyCode.VAULT, "schema"))
        if any(
            vault.get(field) is not True
            for field in ("object_lock_required", "versioning_required", "manifest_last_required")
        ):
            findings.append(TopologyFinding(TopologyCode.VAULT, "required behavior"))
    return tuple(findings)


def _validate_schedulers(document: dict[str, object]) -> tuple[TopologyFinding, ...]:
    schedulers = _objects(document.get("scheduler_instances"), "scheduler_instances")
    if len(schedulers) != _PAIR_COUNT:
        return (TopologyFinding(TopologyCode.SCHEDULER, "count"),)
    hubs: list[str] = []
    if {_text(item.get("service_id"), "service_id") for item in schedulers} != {
        "dts-general",
        "dts-promotion",
    }:
        return (TopologyFinding(TopologyCode.SCHEDULER, "service inventory"),)
    for scheduler in schedulers:
        if frozenset(scheduler) != _EXPECTED_SCHEDULER_KEYS:
            return (TopologyFinding(TopologyCode.SCHEDULER, "schema"),)
        hubs.extend(_strings(scheduler.get("task_hubs"), "task_hubs"))
        if (
            scheduler.get("persistence") != "MEMORY_ONLY"
            or scheduler.get("loss_result") != "REPLACEMENT_FROM_SAFE_CHECKPOINT"
        ):
            return (TopologyFinding(TopologyCode.SCHEDULER, "loss semantics"),)
    if _duplicates(hubs) or set(hubs) != {
        "acquisition",
        "control",
        "legal-processing",
        "promotion",
    }:
        return (TopologyFinding(TopologyCode.SCHEDULER, "task hubs"),)
    return ()


def validate_topology(document: dict[str, object]) -> tuple[TopologyFinding, ...]:
    """Return every stable topology finding; an empty tuple is admission."""
    findings = list(_secret_findings(document))
    if frozenset(document) != _EXPECTED_TOP_LEVEL_KEYS:
        findings.append(TopologyFinding(TopologyCode.INVENTORY, "document schema"))
    if document.get("schema_version") != 1 or document.get("status") != "DESIGN_ONLY_DISABLED":
        findings.append(TopologyFinding(TopologyCode.INVENTORY, "header"))
    findings.extend(_validate_host(document))
    if document.get("recovery_class") != "LOGICALLY_SEPARATE_POC_RECOVERY":
        findings.append(TopologyFinding(TopologyCode.RECOVERY, "recovery class"))
    try:
        databases = _strings(document.get("databases"), "databases")
    except ValueError:
        databases = ()
    if databases != _EXPECTED_DATABASES:
        findings.append(TopologyFinding(TopologyCode.AUTHORITY, "databases"))
    services = _objects(document.get("services"), "services")
    networks = _objects(document.get("networks"), "networks")
    findings.extend(_validate_services(services))
    findings.extend(_validate_networks(services, networks))
    findings.extend(_validate_vaults(document))
    findings.extend(_validate_schedulers(document))
    audit: set[str]
    try:
        audit = set(_strings(document.get("authoritative_audit"), "authoritative_audit"))
    except ValueError:
        audit = set()
    if audit != {
        "RECOVERY_VAULT_IMMUTABLE_ARCHIVE",
        "SQL_SERVER_LEDGER",
    }:
        findings.append(TopologyFinding(TopologyCode.AUTHORITY, "audit"))
    pinecone = _string_object(document.get("pinecone"))
    if pinecone != {
        "project_isolation": "DEDICATED_POC_PROJECT",
        "mutation_owner": "promotion-worker",
        "replacement_indexes_only": True,
        "real_write_authorized": False,
        "plan": "UNSELECTED_PENDING_MEASUREMENT",
    }:
        findings.append(TopologyFinding(TopologyCode.AUTHORITY, "pinecone"))
    return tuple(findings)


def load_topology(path: Path) -> dict[str, object]:
    """Load one bounded JSON topology object."""
    raw = path.read_bytes()
    if len(raw) > _MAX_TOPOLOGY_BYTES:
        raise ValueError(_TOPOLOGY_TOO_LARGE)
    value: object = json.loads(raw)
    document = _string_object(value)
    if document is None:
        raise TypeError(_TOPOLOGY_ROOT_TYPE)
    return document


def check_topology(root: Path) -> TopologyReport:
    """Validate the repository topology and return its exact summary."""
    document = load_topology(root / TOPOLOGY_PATH)
    findings = validate_topology(document)
    if findings:
        detail = ", ".join(f"{finding.code.value}:{finding.detail}" for finding in findings)
        raise ValueError(detail)
    services = _objects(document["services"], "services")
    credentials = {
        credential
        for service in services
        for credential in _strings(service.get("credential_names"), "credential_names")
    }
    return TopologyReport(
        services=len(services),
        networks=len(_objects(document["networks"], "networks")),
        credentials=len(credentials),
        pinned_artifacts=sum(service.get("artifact_state") == "PINNED" for service in services),
        pins_required=sum(service.get("artifact_state") == "PIN_REQUIRED" for service in services),
    )


def main() -> None:
    """Run the repository topology gate."""
    root = Path(__file__).resolve().parents[1]
    report = check_topology(root)
    print(
        "PASS V1 POC topology: "
        f"{report.services} services, {report.networks} networks, "
        f"{report.credentials} credential references, {report.pinned_artifacts} pinned, "
        f"{report.pins_required} pins required"
    )


if __name__ == "__main__":
    main()
