"""Fail-closed tests for the disabled V1 POC infrastructure topology."""

from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from tools.v1_poc_topology import (
    ApplicationContainerBlocker,
    ApplicationContainerContractError,
    CandidateApplicationImagePin,
    ContainerAccountingState,
    ContainerOwnership,
    ObservedPipelineContainer,
    TopologyCode,
    TopologyReport,
    V1ApplicationContainerTopology,
    build_v1_application_container_topology,
    check_topology,
    evaluate_v1_application_containers,
    load_topology,
    validate_topology,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_EXACT_APPLICATIONS = (
    (
        "acquisition-worker",
        "asklegal-acquisition-worker",
        "asklegal-acquisition-worker.service",
        "1",
    ),
    ("control-plane", "asklegal-control-plane", "asklegal-control-plane.service", "2"),
    (
        "legal-processing-worker",
        "asklegal-legal-processing-worker",
        "asklegal-legal-processing-worker.service",
        "3",
    ),
    ("promotion-worker", "asklegal-promotion-worker", "asklegal-promotion-worker.service", "4"),
    ("review-api", "asklegal-review-api", "asklegal-review-api.service", "5"),
)
_INVALID_REGISTRY_AUTHORITIES = (
    "registry.invalid:0",
    "registry.invalid:65536",
    "registry.invalid:99999",
    "registry.invalid:+1",
    "registry.invalid:-1",
    "registry.invalid:01",
    "registry.invalid:00001",
    "registry.invalid:",
    "registry.invalid:abc",
    "registry.invalid:1:2",
    "[::1]:443",
)


def _candidate_reference(application_id: str, digit: str) -> str:
    return f"registry.invalid/release/{application_id}@sha256:{digit * 64}"


def _candidate_pins() -> list[CandidateApplicationImagePin]:
    return [
        CandidateApplicationImagePin(
            application_id=application_id,
            candidate_image_reference=_candidate_reference(application_id, digit),
        )
        for application_id, _, _, digit in reversed(_EXACT_APPLICATIONS)
    ]


def _desired_topology() -> V1ApplicationContainerTopology:
    return build_v1_application_container_topology(_candidate_pins())


def _observed_exact() -> list[ObservedPipelineContainer]:
    return [
        ObservedPipelineContainer(
            container_name=container_name,
            image_reference=_candidate_reference(application_id, digit),
            systemd_unit=unit_name,
            ownership=ContainerOwnership.SYSTEMD,
        )
        for application_id, container_name, unit_name, digit in reversed(_EXACT_APPLICATIONS)
    ]


def _document() -> dict[str, object]:
    return load_topology(REPOSITORY_ROOT / "infrastructure/poc/topology.json")


def _service(document: dict[str, object], service_id: str) -> dict[str, object]:
    for raw_service in _object_list(document["services"]):
        service = _object_map(raw_service)
        if service.get("service_id") == service_id:
            return service
    raise AssertionError(service_id)


def _object_map(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    candidate = cast("dict[object, object]", value)
    assert all(type(key) is str for key in candidate)
    return cast("dict[str, object]", candidate)


def _object_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast("list[object]", value)


def _codes(document: dict[str, object]) -> set[TopologyCode]:
    return {finding.code for finding in validate_topology(document)}


def test_repository_topology_passes_with_exact_summary() -> None:
    """Keep the checked-in topology synchronized with its closed admission policy."""
    assert check_topology(REPOSITORY_ROOT) == TopologyReport(
        services=16,
        networks=10,
        credentials=26,
        pinned_artifacts=11,
        pins_required=5,
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("enable", TopologyCode.ARTIFACT),
        ("latest", TopologyCode.ARTIFACT),
        ("public", TopologyCode.SURFACE),
        ("secret", TopologyCode.SECRET),
        ("network", TopologyCode.NETWORK),
        ("vault", TopologyCode.VAULT),
        ("scheduler", TopologyCode.SCHEDULER),
        ("pinecone", TopologyCode.AUTHORITY),
        ("unknown", TopologyCode.INVENTORY),
    ],
)
def test_authority_and_isolation_regressions_fail_closed(
    mutation: str, expected_code: TopologyCode
) -> None:
    """Reject representative regressions before generating any runtime files."""
    document = deepcopy(_document())
    if mutation == "enable":
        _service(document, "control-plane")["enabled"] = True
    elif mutation == "latest":
        service = _service(document, "control-plane")
        service["artifact_state"] = "PINNED"
        service["artifact_ref"] = "asklegal/control-plane:latest"
    elif mutation == "public":
        listeners = _object_list(_service(document, "review-api")["listeners"])
        _object_map(listeners[0])["scope"] = "PUBLIC"
    elif mutation == "secret":
        document["api_key"] = "do-not-store-secret-values"
    elif mutation == "network":
        networks = _object_list(document["networks"])
        members = _object_list(_object_map(networks[0])["members"])
        members.pop()
    elif mutation == "vault":
        vaults = _object_list(document["vaults"])
        first_vault = _object_map(vaults[0])
        _object_map(vaults[1])["root"] = first_vault["root"]
    elif mutation == "scheduler":
        schedulers = _object_list(document["scheduler_instances"])
        _object_map(schedulers[0])["loss_result"] = "RESUMED"
    elif mutation == "pinecone":
        pinecone = _object_map(document["pinecone"])
        pinecone["real_write_authorized"] = True
    else:
        document["unexpected"] = "field"
    assert expected_code in _codes(document)


def test_candidate_topology_derives_exact_sorted_names_and_units() -> None:
    """A caller cannot choose container or unit ownership for the five applications."""
    topology = _desired_topology()

    assert tuple(
        (
            item.application_id,
            item.image_repository,
            item.container_name,
            item.systemd_unit,
            item.candidate_image_reference,
        )
        for item in topology.applications
    ) == (
        (
            "acquisition-worker",
            "registry.invalid/release/acquisition-worker",
            "asklegal-acquisition-worker",
            "asklegal-acquisition-worker.service",
            "registry.invalid/release/acquisition-worker@sha256:" + ("1" * 64),
        ),
        (
            "control-plane",
            "registry.invalid/release/control-plane",
            "asklegal-control-plane",
            "asklegal-control-plane.service",
            "registry.invalid/release/control-plane@sha256:" + ("2" * 64),
        ),
        (
            "legal-processing-worker",
            "registry.invalid/release/legal-processing-worker",
            "asklegal-legal-processing-worker",
            "asklegal-legal-processing-worker.service",
            "registry.invalid/release/legal-processing-worker@sha256:" + ("3" * 64),
        ),
        (
            "promotion-worker",
            "registry.invalid/release/promotion-worker",
            "asklegal-promotion-worker",
            "asklegal-promotion-worker.service",
            "registry.invalid/release/promotion-worker@sha256:" + ("4" * 64),
        ),
        (
            "review-api",
            "registry.invalid/release/review-api",
            "asklegal-review-api",
            "asklegal-review-api.service",
            "registry.invalid/release/review-api@sha256:" + ("5" * 64),
        ),
    )
    assert b'"state":"CANDIDATE_STRUCTURAL_ONLY"' in topology.to_json_bytes()
    assert b"admitted" not in topology.to_json_bytes()


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "unknown"])
def test_candidate_topology_requires_the_exact_five_application_ids(mutation: str) -> None:
    """Missing, extra, duplicate, or unknown application pins cannot form desired state."""
    pins = _candidate_pins()
    if mutation == "missing":
        pins.pop()
    elif mutation == "extra":
        pins.append(
            CandidateApplicationImagePin(
                application_id="extra-worker",
                candidate_image_reference=_candidate_reference("extra-worker", "6"),
            )
        )
    elif mutation == "duplicate":
        pins.append(pins[0])
    else:
        pins[-1] = CandidateApplicationImagePin(
            application_id="unknown-worker",
            candidate_image_reference=_candidate_reference("unknown-worker", "6"),
        )

    with pytest.raises(ApplicationContainerContractError) as raised:
        build_v1_application_container_topology(pins)

    assert str(raised.value) == "CANDIDATE_PIN_INVENTORY_INVALID"


@pytest.mark.parametrize(
    "reference",
    [
        "asklegal/control-plane:latest",
        "asklegal/control-plane:v1@sha256:" + ("0" * 64),
        "sha256:" + ("0" * 64),
        " asklegal/control-plane@sha256:" + ("0" * 64),
        "asklegal/control-plane@sha256:" + ("0" * 63),
        "asklegal/control-plane@sha256:" + ("A" * 64),
        "@sha256:" + ("0" * 64),
        "ASKLEGAL/control-plane@sha256:" + ("0" * 64),
        "asklegal//control-plane@sha256:" + ("0" * 64),
    ],
)
def test_candidate_topology_rejects_malformed_or_mutable_image_references(
    reference: str,
) -> None:
    """A tag or non-canonical OCI reference cannot masquerade as an immutable pin."""
    pins = _candidate_pins()
    control_index = next(
        index for index, item in enumerate(pins) if item.application_id == "control-plane"
    )
    pins[control_index] = CandidateApplicationImagePin(
        application_id="control-plane",
        candidate_image_reference=reference,
    )

    with pytest.raises(ApplicationContainerContractError) as raised:
        build_v1_application_container_topology(pins)

    assert str(raised.value) == "CANDIDATE_IMAGE_REFERENCE_INVALID"
    assert reference not in str(raised.value)


@pytest.mark.parametrize("registry_authority", ["registry.invalid:1", "registry.invalid:65535"])
def test_candidate_topology_accepts_only_canonical_boundary_registry_ports(
    registry_authority: str,
) -> None:
    """Ports 1 and 65535 remain valid immutable candidate registry authorities."""
    pins = _candidate_pins()
    control_index = next(
        index for index, item in enumerate(pins) if item.application_id == "control-plane"
    )
    reference = f"{registry_authority}/release/control-plane@sha256:{'2' * 64}"
    pins[control_index] = CandidateApplicationImagePin(
        application_id="control-plane",
        candidate_image_reference=reference,
    )

    topology = build_v1_application_container_topology(pins)

    control = next(item for item in topology.applications if item.application_id == "control-plane")
    assert control.candidate_image_reference == reference
    assert control.image_repository == f"{registry_authority}/release/control-plane"


@pytest.mark.parametrize("registry_authority", _INVALID_REGISTRY_AUTHORITIES)
def test_candidate_topology_rejects_out_of_range_or_ambiguous_registry_ports(
    registry_authority: str,
) -> None:
    """Invalid ports and colon-ambiguous authorities cannot become desired image pins."""
    pins = _candidate_pins()
    control_index = next(
        index for index, item in enumerate(pins) if item.application_id == "control-plane"
    )
    reference = f"{registry_authority}/release/control-plane@sha256:{'2' * 64}"
    pins[control_index] = CandidateApplicationImagePin(
        application_id="control-plane",
        candidate_image_reference=reference,
    )

    with pytest.raises(ApplicationContainerContractError) as raised:
        build_v1_application_container_topology(pins)

    assert str(raised.value) == "CANDIDATE_IMAGE_REFERENCE_INVALID"


@pytest.mark.parametrize("registry_authority", ["registry.invalid:1", "registry.invalid:65535"])
def test_observed_inventory_accepts_canonical_boundary_registry_ports_as_image_facts(
    registry_authority: str,
) -> None:
    """The observed boundary uses the same valid port grammar as desired candidates."""
    observed = _observed_exact()
    control_index = next(
        index
        for index, item in enumerate(observed)
        if item.container_name == "asklegal-control-plane"
    )
    observed[control_index] = replace(
        observed[control_index],
        image_reference=f"{registry_authority}/release/control-plane@sha256:{'2' * 64}",
    )

    report = evaluate_v1_application_containers(
        _desired_topology(), observed, inventory_complete=True
    )

    assert report.drifted_application_containers == ("asklegal-control-plane",)
    assert report.blocker_codes == (ApplicationContainerBlocker.APPLICATION_IMAGE_DRIFT,)


@pytest.mark.parametrize("registry_authority", _INVALID_REGISTRY_AUTHORITIES)
def test_observed_inventory_rejects_out_of_range_or_ambiguous_registry_ports(
    registry_authority: str,
) -> None:
    """Malformed observed authorities fail before image drift can be classified."""
    observed = _observed_exact()
    control_index = next(
        index
        for index, item in enumerate(observed)
        if item.container_name == "asklegal-control-plane"
    )
    observed[control_index] = replace(
        observed[control_index],
        image_reference=f"{registry_authority}/release/control-plane@sha256:{'2' * 64}",
    )

    with pytest.raises(ApplicationContainerContractError) as raised:
        evaluate_v1_application_containers(_desired_topology(), observed, inventory_complete=True)

    assert str(raised.value) == "OBSERVED_CONTAINER_INPUT_INVALID"


def test_candidate_repository_must_end_with_its_canonical_application_id() -> None:
    """A valid digest for another repository cannot be rebound to an application."""
    pins = _candidate_pins()
    control_index = next(
        index for index, item in enumerate(pins) if item.application_id == "control-plane"
    )
    pins[control_index] = CandidateApplicationImagePin(
        application_id="control-plane",
        candidate_image_reference=_candidate_reference("review-api", "2"),
    )

    with pytest.raises(ApplicationContainerContractError) as raised:
        build_v1_application_container_topology(pins)

    assert str(raised.value) == "CANDIDATE_IMAGE_REPOSITORY_MISMATCH"


def test_caller_name_and_unit_substitutions_are_rejected_without_callback_access() -> None:
    """Lookalike inputs cannot inject caller-chosen container or systemd names."""
    callback_called = False

    class SubstitutedPin:
        application_id = "control-plane"
        candidate_image_reference = _candidate_reference("control-plane", "2")
        container_name = "attacker-container"
        systemd_unit = "attacker.service"

        def __getattribute__(self, name: str) -> object:
            nonlocal callback_called
            callback_called = True
            return object.__getattribute__(self, name)

    pins = cast("list[CandidateApplicationImagePin]", [SubstitutedPin()])
    with pytest.raises(ApplicationContainerContractError) as raised:
        build_v1_application_container_topology(pins)

    assert str(raised.value) == "CANDIDATE_PIN_INPUT_INVALID"
    assert callback_called is False


def test_complete_exact_inventory_is_clean_but_grants_no_authority() -> None:
    """Five exact supervised matches prove only this synthetic reconciliation dimension."""
    report = evaluate_v1_application_containers(
        _desired_topology(),
        _observed_exact(),
        inventory_complete=True,
    )

    assert report.clean is True
    assert report.mutation_authorized is False
    assert report.blocker_codes == ()
    assert report.matched_application_containers == (
        "asklegal-acquisition-worker",
        "asklegal-control-plane",
        "asklegal-legal-processing-worker",
        "asklegal-promotion-worker",
        "asklegal-review-api",
    )
    assert report.missing_application_containers == ()
    assert report.drifted_application_containers == ()
    assert report.duplicate_pipeline_containers == ()
    assert report.ownership_unknown_containers == ()
    assert report.unsupervised_application_containers == ()
    assert report.orphan_pipeline_containers == ()
    assert len(report.observed_accounting) == 5
    assert {item.state for item in report.observed_accounting} == {ContainerAccountingState.MATCHED}
    assert b"admitted" not in report.to_json_bytes()


def test_incomplete_inventory_cannot_report_clean_with_five_exact_matches() -> None:
    """An explicit incomplete inventory blocks even when every expected name is present."""
    report = evaluate_v1_application_containers(
        _desired_topology(),
        _observed_exact(),
        inventory_complete=False,
    )

    assert report.clean is False
    assert report.blocker_codes == (ApplicationContainerBlocker.CONTAINER_INVENTORY_INCOMPLETE,)


def test_acq_batch_and_cp_test_are_exact_names_only_orphans() -> None:
    """Known and future pipeline extras block without granting stop or removal authority."""
    observed = _observed_exact()
    observed.extend(
        [
            ObservedPipelineContainer(
                container_name="cp-test",
                image_reference="registry.invalid/legacy/cp-test@sha256:" + ("7" * 64),
                systemd_unit=None,
                ownership=ContainerOwnership.UNSUPERVISED,
            ),
            ObservedPipelineContainer(
                container_name="acq-batch",
                image_reference="registry.invalid/legacy/acq-batch@sha256:" + ("6" * 64),
                systemd_unit=None,
                ownership=ContainerOwnership.UNSUPERVISED,
            ),
        ]
    )

    report = evaluate_v1_application_containers(
        _desired_topology(), observed, inventory_complete=True
    )

    assert report.clean is False
    assert report.mutation_authorized is False
    assert report.orphan_pipeline_containers == ("acq-batch", "cp-test")
    assert report.blocker_codes == (ApplicationContainerBlocker.ORPHAN_PIPELINE_CONTAINERS,)
    assert tuple(
        item.container_name
        for item in report.observed_accounting
        if item.state is ContainerAccountingState.ORPHAN
    ) == ("acq-batch", "cp-test")


@pytest.mark.parametrize(
    ("mutation", "expected_blocker", "expected_state"),
    [
        (
            "image",
            ApplicationContainerBlocker.APPLICATION_IMAGE_DRIFT,
            ContainerAccountingState.DRIFTED,
        ),
        (
            "unit",
            ApplicationContainerBlocker.APPLICATION_SYSTEMD_UNIT_DRIFT,
            ContainerAccountingState.DRIFTED,
        ),
        (
            "unsupervised",
            ApplicationContainerBlocker.UNSUPERVISED_APPLICATION_CONTAINERS,
            ContainerAccountingState.UNSUPERVISED,
        ),
    ],
)
def test_expected_container_image_unit_and_supervision_drift_remain_distinct(
    mutation: str,
    expected_blocker: ApplicationContainerBlocker,
    expected_state: ContainerAccountingState,
) -> None:
    """Digest drift, wrong unit ownership, and no supervisor cannot collapse together."""
    observed = _observed_exact()
    control_index = next(
        index
        for index, item in enumerate(observed)
        if item.container_name == "asklegal-control-plane"
    )
    control = observed[control_index]
    if mutation == "image":
        observed[control_index] = replace(
            control,
            image_reference=_candidate_reference("control-plane", "9"),
        )
    elif mutation == "unit":
        observed[control_index] = replace(control, systemd_unit="asklegal-review-api.service")
    else:
        observed[control_index] = replace(
            control,
            systemd_unit=None,
            ownership=ContainerOwnership.UNSUPERVISED,
        )

    report = evaluate_v1_application_containers(
        _desired_topology(), observed, inventory_complete=True
    )

    assert report.clean is False
    assert expected_blocker in report.blocker_codes
    control_accounting = next(
        item
        for item in report.observed_accounting
        if item.container_name == "asklegal-control-plane"
    )
    assert control_accounting.state is expected_state


def test_missing_application_and_duplicate_observations_are_distinct_and_exhaustive() -> None:
    """An absent name and repeated inventory rows receive separate exact accounting."""
    observed = _observed_exact()
    review_index = next(
        index for index, item in enumerate(observed) if item.container_name == "asklegal-review-api"
    )
    observed.pop(review_index)
    observed.append(observed[0])

    report = evaluate_v1_application_containers(
        _desired_topology(), observed, inventory_complete=True
    )

    assert report.clean is False
    assert report.missing_application_containers == ("asklegal-review-api",)
    assert report.duplicate_pipeline_containers == ("asklegal-promotion-worker",)
    assert ApplicationContainerBlocker.MISSING_APPLICATION_CONTAINERS in report.blocker_codes
    assert ApplicationContainerBlocker.DUPLICATE_PIPELINE_CONTAINERS in report.blocker_codes
    assert len(report.observed_accounting) == len(observed)
    assert (
        sum(item.state is ContainerAccountingState.DUPLICATE for item in report.observed_accounting)
        == 2
    )


def test_unknown_ownership_always_makes_the_inventory_incomplete() -> None:
    """A caller cannot assert completeness while one expected container has unknown ownership."""
    observed = _observed_exact()
    review_index = next(
        index for index, item in enumerate(observed) if item.container_name == "asklegal-review-api"
    )
    observed[review_index] = replace(
        observed[review_index],
        systemd_unit=None,
        ownership=ContainerOwnership.UNKNOWN,
    )

    report = evaluate_v1_application_containers(
        _desired_topology(), observed, inventory_complete=True
    )

    assert report.clean is False
    assert report.ownership_unknown_containers == ("asklegal-review-api",)
    assert report.blocker_codes == (
        ApplicationContainerBlocker.CONTAINER_INVENTORY_INCOMPLETE,
        ApplicationContainerBlocker.CONTAINER_OWNERSHIP_UNKNOWN,
    )
    accounting = next(
        item for item in report.observed_accounting if item.container_name == "asklegal-review-api"
    )
    assert accounting.state is ContainerAccountingState.OWNERSHIP_UNKNOWN


def test_duplicate_unknown_row_cannot_mask_ownership_or_inventory_incompleteness() -> None:
    """Duplicate accounting stays exclusive while UNKNOWN facts independently block."""
    observed = _observed_exact()
    review = next(item for item in observed if item.container_name == "asklegal-review-api")
    observed.append(
        replace(
            review,
            systemd_unit=None,
            ownership=ContainerOwnership.UNKNOWN,
        )
    )

    report = evaluate_v1_application_containers(
        _desired_topology(), observed, inventory_complete=True
    )

    assert report.inventory_complete is False
    assert report.duplicate_pipeline_containers == ("asklegal-review-api",)
    assert report.ownership_unknown_containers == ("asklegal-review-api",)
    assert report.blocker_codes == (
        ApplicationContainerBlocker.CONTAINER_INVENTORY_INCOMPLETE,
        ApplicationContainerBlocker.DUPLICATE_PIPELINE_CONTAINERS,
        ApplicationContainerBlocker.CONTAINER_OWNERSHIP_UNKNOWN,
    )
    assert len(report.observed_accounting) == len(observed)
    review_accounting = tuple(
        item for item in report.observed_accounting if item.container_name == "asklegal-review-api"
    )
    assert len(review_accounting) == 2
    assert all(item.state is ContainerAccountingState.DUPLICATE for item in review_accounting)


def test_input_reordering_callbacks_and_post_return_mutation_cannot_change_bytes() -> None:
    """Scalar snapshots isolate issued bytes from later caller-controlled mutation."""
    pins = _candidate_pins()
    first_pin = pins[0]

    def callback_pins() -> Iterator[CandidateApplicationImagePin]:
        yield first_pin
        object.__setattr__(
            first_pin,
            "candidate_image_reference",
            _candidate_reference(first_pin.application_id, "f"),
        )
        yield from pins[1:]

    topology = build_v1_application_container_topology(callback_pins())
    topology_bytes = topology.to_json_bytes()
    assert topology_bytes == _desired_topology().to_json_bytes()

    observed = _observed_exact()
    first_observed = observed[0]

    def callback_observations() -> Iterator[ObservedPipelineContainer]:
        yield first_observed
        object.__setattr__(first_observed, "systemd_unit", "attacker.service")
        yield from observed[1:]

    report = evaluate_v1_application_containers(
        topology,
        callback_observations(),
        inventory_complete=True,
    )
    report_bytes = report.to_json_bytes()
    object.__setattr__(first_observed, "container_name", "changed-after-return")
    observed.reverse()

    assert report.clean is True
    assert report.to_json_bytes() == report_bytes


def test_ordinary_callback_failures_are_closed_and_baseexception_remains_visible() -> None:
    """Iterator diagnostics are sanitized while process-control exceptions propagate."""
    secret_detail = "private callback diagnostic"

    def ordinary_failure() -> Iterator[CandidateApplicationImagePin]:
        raise RuntimeError(secret_detail)
        yield from ()

    with pytest.raises(ApplicationContainerContractError) as raised:
        build_v1_application_container_topology(ordinary_failure())
    assert str(raised.value) == "CANDIDATE_PIN_INPUT_INVALID"
    assert secret_detail not in str(raised.value)
    assert raised.value.__context__ is None

    class ProcessControl(BaseException):
        pass

    process_control = ProcessControl()

    def interrupted() -> Iterator[ObservedPipelineContainer]:
        raise process_control
        yield from ()

    with pytest.raises(ProcessControl) as interrupted_result:
        evaluate_v1_application_containers(
            _desired_topology(), interrupted(), inventory_complete=True
        )
    assert interrupted_result.value is process_control
