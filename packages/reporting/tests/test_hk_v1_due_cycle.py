"""Hostile pure-contract coverage for Hong Kong V1 due cycles.

Production success is intentionally unavailable until Slice B supplies an
adapter-issued result binding.  These tests preserve all pure planning,
terminal, accounting, parser, mutation, and provenance failure coverage.
"""

# ruff: noqa: SLF001

# pyright: reportPrivateUsage=false
# Process-local test simulations exercise issuance boundaries unavailable to
# production callers until Slice B owns a retained-result adapter.

from __future__ import annotations

import gc
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import asklegal_reporting.hk_v1_coverage as coverage
import asklegal_reporting.hk_v1_due_cycle as due_cycle
import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_reporting import (
    DueChangeStatus,
    DueCycleKind,
    DueImmutableReference,
    DueRegisterBundle,
    DueSourceRegister,
    DueTerminalOutcome,
    DueTerminalReportReference,
    HongKongV1DueCycleError,
    HongKongV1DueCycleInstruction,
    HongKongV1DueRequirement,
    HongKongV1DueTerminal,
    IssuedDueResultBinding,
    build_hk_v1_due_cycle_report,
    build_hk_v1_due_result_manifest,
    build_hk_v1_due_terminal,
    build_hk_v1_due_terminal_from_result_binding,
    derive_hk_v1_due_cycle_plan,
    hk_v1_due_cycle_manifest_key,
    hk_v1_due_source_payload_key,
    hk_v1_due_source_result_manifest_key,
    hk_v1_due_source_terminal_key,
    load_hk_v1_coverage_matrix,
    parse_hk_v1_due_cycle_report,
    parse_hk_v1_due_register_bundle,
    parse_hk_v1_due_terminal,
)

_ROOT = Path(__file__).resolve().parents[3]
_REGISTER_ROOT = _ROOT / "packages/source-connectors/src/asklegal_source_connectors"
_REGISTER_NAMES = (
    "hk_cases_source_register.json",
    "hk_legislation_source_register.json",
)
_EXPECTED_COUNTS = {
    DueCycleKind.DAILY_CURRENT_LAW: 4,
    DueCycleKind.WEEKLY_RELEASE: 6,
    DueCycleKind.MONTHLY_CROSS_CHECK: 1,
    DueCycleKind.FULL_PERIODIC: 7,
}
_NPC_SOURCE_IDS = frozenset(
    {
        "HK-LEG-NPC-NATIONAL-LAWS-DATABASE",
        "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS",
    }
)
_MATRIX_PATH = Path(coverage.__file__).with_name("hk_v1_coverage_matrix.json")


def _count_preserving_npc_swap_matrix(tmp_path: Path) -> coverage.HongKongV1CoverageMatrix:
    """Load a validly resealed Matrix that swaps Basic Law for one dormant NPC role."""
    document = parse_json_bytes(_MATRIX_PATH.read_bytes(), max_bytes=1_000_000)
    assert isinstance(document, dict)
    rows = document["rows"]
    assert isinstance(rows, list)
    changed: set[str] = set()
    for row in rows:
        assert isinstance(row, dict)
        source_id = row["source_id"]
        if source_id == "HK-LEG-BASIC-LAW-PORTAL":
            row["cadence"] = "EXCLUDED_FROM_V1"
            changed.add("HK-LEG-BASIC-LAW-PORTAL")
        elif source_id == "HK-LEG-NPC-NATIONAL-LAWS-DATABASE":
            row["cadence"] = "MONTHLY_AND_EVENT_TRIGGERED"
            changed.add("HK-LEG-NPC-NATIONAL-LAWS-DATABASE")
    assert changed == {
        "HK-LEG-BASIC-LAW-PORTAL",
        "HK-LEG-NPC-NATIONAL-LAWS-DATABASE",
    }
    unsigned = dict(document)
    del unsigned["fingerprint"]
    document["fingerprint"] = f"sha256:{sha256(canonicalize(unsigned)).hexdigest()}"
    path = tmp_path / "count-preserving-npc-swap.json"
    path.write_bytes(canonicalize(document))
    return load_hk_v1_coverage_matrix(path)


def _bundles() -> tuple[due_cycle.DueRegisterBundle, ...]:
    return tuple(
        parse_hk_v1_due_register_bundle((_REGISTER_ROOT / name).read_bytes())
        for name in _REGISTER_NAMES
    )


def _plan(kind: DueCycleKind = DueCycleKind.DAILY_CURRENT_LAW) -> due_cycle.HongKongV1DueCyclePlan:
    matrix = load_hk_v1_coverage_matrix()
    return derive_hk_v1_due_cycle_plan(
        HongKongV1DueCycleInstruction(
            f"hk-v1-{kind.value.lower()}-20260826",
            kind,
            "2026-08-26T00:00:00Z",
            "2026-08-26T00:00:00Z",
            matrix.revision,
            matrix.fingerprint,
        ),
        matrix,
        _bundles(),
    )


def _incomplete_terminal(
    plan: due_cycle.HongKongV1DueCyclePlan,
    requirement: HongKongV1DueRequirement | None = None,
) -> HongKongV1DueTerminal:
    requirement = plan.requirements[0] if requirement is None else requirement
    blockers = next(
        source.blockers
        for register in plan.registers
        for source in register.sources
        if source.source_id == requirement.source_id
    )
    return HongKongV1DueTerminal(
        plan.instruction.cycle_id,
        plan.plan_fingerprint,
        plan.instruction.matrix_fingerprint,
        requirement,
        plan.instruction.observation_cutoff,
        requirement.result_schema,
        "sha256:" + "1" * 64,
        None,
        None,
        DueTerminalOutcome.INCOMPLETE_OBSERVATION,
        DueChangeStatus.NOT_PROVED,
        ("UNADMITTED",),
        0,
        0,
        0,
        0,
        0,
        blockers,
    )


def _reference(
    logical_key: str,
    fingerprint: str = "sha256:" + "a" * 64,
    byte_length: int = 1,
    vault: str = "PRIMARY",
) -> DueImmutableReference:
    return DueImmutableReference(vault, logical_key, "v" + "a" * 64, fingerprint, byte_length)


def _binding(plan: due_cycle.HongKongV1DueCyclePlan) -> IssuedDueResultBinding:
    terminal = _incomplete_terminal(plan)
    return IssuedDueResultBinding(
        plan.instruction.cycle_id,
        plan.plan_fingerprint,
        plan.instruction.matrix_fingerprint,
        terminal.requirement,
        plan.instruction.observation_cutoff,
        terminal.requirement.result_schema,
        "1.0.0",
        _reference(
            hk_v1_due_source_payload_key(plan.instruction.cycle_id, terminal.requirement.source_id)
        ),
        None,
        terminal.outcome,
        terminal.change_status,
        terminal.failure_codes,
        terminal.expected_count,
        terminal.retained_count,
        terminal.not_published_count,
        terminal.gap_count,
        terminal.failed_count,
        terminal.registered_blockers,
    )


def _issued_incomplete_pair(
    plan: due_cycle.HongKongV1DueCyclePlan,
    terminal: HongKongV1DueTerminal | None = None,
) -> tuple[DueTerminalReportReference, HongKongV1DueTerminal]:
    issued = due_cycle._issue_terminal(_incomplete_terminal(plan) if terminal is None else terminal)
    content, fingerprint = build_hk_v1_due_terminal(issued)
    reference = DueTerminalReportReference(
        issued.requirement.source_id,
        _reference(
            hk_v1_due_source_terminal_key(plan.instruction.cycle_id, issued.requirement.source_id),
            fingerprint,
            len(content),
        ),
    )
    return reference, issued


@pytest.mark.parametrize(("kind", "count"), _EXPECTED_COUNTS.items())
def test_exact_due_set_counts(kind: DueCycleKind, count: int) -> None:
    """The two-family Matrix derives exactly 4/6/1/7 active source roles."""
    assert len(_plan(kind).requirements) == count


@pytest.mark.parametrize(
    ("kind", "source_id"),
    [
        (DueCycleKind.DAILY_CURRENT_LAW, "HK-CASE-HKLII-DISCOVERY"),
        (DueCycleKind.DAILY_CURRENT_LAW, "HK-LEG-GLD-EGAZETTE"),
        (DueCycleKind.WEEKLY_RELEASE, "HK-LEG-HKEL-EDITORIAL-RECORDS"),
        (DueCycleKind.MONTHLY_CROSS_CHECK, "HK-LEG-BASIC-LAW-PORTAL"),
        (DueCycleKind.FULL_PERIODIC, "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS"),
    ],
)
def test_exact_due_set_membership(kind: DueCycleKind, source_id: str) -> None:
    """Representative roles from every frozen cadence remain visible."""
    assert source_id in {item.source_id for item in _plan(kind).requirements}


def test_monthly_is_basic_law_only_and_no_periodic_plan_contains_npc_roles() -> None:
    """Dormant NPC vocabulary never enters an autonomous V1 schedule."""
    monthly = {item.source_id for item in _plan(DueCycleKind.MONTHLY_CROSS_CHECK).requirements}
    assert monthly == {"HK-LEG-BASIC-LAW-PORTAL"}
    for kind in DueCycleKind:
        assert _NPC_SOURCE_IDS.isdisjoint(item.source_id for item in _plan(kind).requirements)


def test_no_current_due_plan_contains_hkex_or_regulatory_work() -> None:
    """Preserved HKEX vocabulary must never become current V1 scheduled work."""
    for kind in DueCycleKind:
        requirements = _plan(kind).requirements
        assert all(item.material_family in {"CASES", "LEGISLATION"} for item in requirements)
        assert all(not item.source_id.startswith("HK-REG-HKEX-") for item in requirements)


def test_plan_derivation_rejects_resealed_count_preserving_npc_cadence_swap(
    tmp_path: Path,
) -> None:
    """Exact counts cannot authorize a different monthly/full-periodic source universe."""
    matrix = _count_preserving_npc_swap_matrix(tmp_path)
    instruction = HongKongV1DueCycleInstruction(
        "hk-v1-count-preserving-policy-swap-20260827",
        DueCycleKind.MONTHLY_CROSS_CHECK,
        "2026-08-27T00:00:00Z",
        "2026-08-27T00:00:00Z",
        matrix.revision,
        matrix.fingerprint,
    )

    with pytest.raises(HongKongV1DueCycleError, match="MATRIX_POLICY_INVALID"):
        derive_hk_v1_due_cycle_plan(instruction, matrix, _bundles())


@pytest.mark.parametrize(
    "scheduled_at",
    ["bad", "2026-08-26T00:00:00+00:00", "2026-08-26T00:00Z"],
)
def test_instruction_rejects_noncanonical_time(scheduled_at: str) -> None:
    """Instruction parsing stays exact UTC-only."""
    matrix = load_hk_v1_coverage_matrix()
    with pytest.raises(HongKongV1DueCycleError, match="CYCLE_INSTRUCTION_INVALID"):
        HongKongV1DueCycleInstruction(
            "hk-v1-invalid-20260826",
            DueCycleKind.DAILY_CURRENT_LAW,
            scheduled_at,
            "2026-08-26T00:00:00Z",
            matrix.revision,
            matrix.fingerprint,
        )


def test_instruction_round_trip_is_exact() -> None:
    """Instruction bytes preserve all controlling values."""
    plan = _plan()
    assert plan.instruction.scheduled_at == "2026-08-26T00:00:00Z"
    assert plan.instruction.observation_cutoff == "2026-08-26T00:00:00Z"


def test_invented_projection_schema_is_not_register_authority() -> None:
    """The deleted six-field projection cannot mint a new production register."""
    unsigned: dict[str, JsonValue] = {
        "schema_id": "asklegal.hk-v1-due-register",
        "schema_version": "1.0.0",
        "register_id": "hsr_000000000000000000000000000000000000000000000001",
        "register_version": "2026-08-21.1",
        "sources": [],
    }
    fingerprint = sha256(canonicalize(checked_json_value(unsigned))).hexdigest()
    content = canonicalize(checked_json_value(unsigned | {"fingerprint": f"sha256:{fingerprint}"}))
    with pytest.raises(HongKongV1DueCycleError, match="REGISTER_BUNDLE_INVALID"):
        parse_hk_v1_due_register_bundle(content)


@pytest.mark.parametrize("name", _REGISTER_NAMES)
def test_actual_register_raw_and_canonical_bytes_issue_same_bundle(name: str) -> None:
    """Whitespace/key formatting is not authority, the full canonical document is."""
    raw = (_REGISTER_ROOT / name).read_bytes()
    canonical = canonicalize(checked_json_value(json.loads(raw)))
    left = parse_hk_v1_due_register_bundle(raw)
    right = parse_hk_v1_due_register_bundle(canonical)
    assert left == right


def test_register_array_reorder_is_rejected_even_when_resealed() -> None:
    """Official source order is a schema fact."""
    document = json.loads((_REGISTER_ROOT / _REGISTER_NAMES[0]).read_bytes())
    document["sources"] = list(reversed(document["sources"]))
    unsigned = dict(document)
    del unsigned["fingerprint"]
    document["fingerprint"] = (
        f"sha256:{sha256(canonicalize(checked_json_value(unsigned))).hexdigest()}"
    )
    with pytest.raises(HongKongV1DueCycleError, match="REGISTER_BUNDLE_INVALID"):
        parse_hk_v1_due_register_bundle(canonicalize(checked_json_value(document)))


@pytest.mark.parametrize(
    ("name", "fingerprint"),
    [
        (
            "hk_legislation_source_register.json",
            "sha256:be2dc02b4ef087ac2357ad96dc05be5a36127e2a7f395bffe5b7a98f6408de67",
        ),
        (
            "hk_cases_source_register.json",
            "sha256:a697a7f7b9b1327169d368ebdef722ee71d6dae447057c8da2a502b5bcdbe13e",
        ),
        (
            "hk_regulatory_source_register.json",
            "sha256:9af7fb460f3556d82b93620ba171cf7391480ad288268afce24ac03e8b7bbbb6",
        ),
    ],
)
def test_actual_register_keeps_official_declared_fingerprint(name: str, fingerprint: str) -> None:
    """Projection retains the register's authority digest, never a derived substitute."""
    assert (
        parse_hk_v1_due_register_bundle((_REGISTER_ROOT / name).read_bytes()).register_fingerprint
        == fingerprint
    )


@pytest.mark.parametrize("kind", list(DueCycleKind))
def test_fresh_plan_rederivation_is_deterministic(kind: DueCycleKind) -> None:
    """Restart-equivalent rederivation preserves the exact frozen plan fingerprint."""
    assert _plan(kind).plan_fingerprint == _plan(kind).plan_fingerprint


@pytest.mark.parametrize("field", ["operational_state", "endpoint_ids", "blockers"])
def test_issued_register_mutation_is_rejected(field: str) -> None:
    """Nested issued source changes invalidate loader provenance."""
    bundle = _bundles()[0]
    source = bundle.sources[0]
    original = getattr(source, field)
    changed = (
        "PARTIALLY_CONFIGURED"
        if field == "operational_state"
        else (("endpoint",) if field == "endpoint_ids" else ("X",))
    )
    object.__setattr__(source, field, changed)
    try:
        matrix = load_hk_v1_coverage_matrix()
        instruction = HongKongV1DueCycleInstruction(
            "hk-v1-mutated-register-20260826",
            DueCycleKind.DAILY_CURRENT_LAW,
            "2026-08-26T00:00:00Z",
            "2026-08-26T00:00:00Z",
            matrix.revision,
            matrix.fingerprint,
        )
        with pytest.raises(HongKongV1DueCycleError, match="REGISTER_BUNDLE"):
            derive_hk_v1_due_cycle_plan(
                instruction,
                matrix,
                (bundle, *_bundles()[1:]),
            )
    finally:
        object.__setattr__(source, field, original)


@pytest.mark.parametrize("field", ["technical_state", "rights_state"])
def test_current_matrix_admission_blocks_complete(field: str) -> None:
    """No self-authored configured register can bypass Matrix admission."""
    plan = _plan()
    requirement = plan.requirements[0]
    assert getattr(requirement, field) == "NOT_ADMITTED"
    with pytest.raises(HongKongV1DueCycleError, match="DUE_TERMINAL_INVALID"):
        HongKongV1DueTerminal(
            plan.instruction.cycle_id,
            plan.plan_fingerprint,
            plan.instruction.matrix_fingerprint,
            requirement,
            plan.instruction.observation_cutoff,
            requirement.result_schema,
            "sha256:" + "2" * 64,
            None,
            "sha256:" + "3" * 64,
            DueTerminalOutcome.COMPLETE,
            DueChangeStatus.NO_CHANGE,
            (),
            0,
            0,
            0,
            0,
            0,
            (),
        )


def test_matrix_admission_rejection_reaches_cycle_binding_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A simulated configured register proves cycle admission blocks COMPLETE."""
    plan = _plan()
    requirement = plan.requirements[0]
    manifest = _reference(
        hk_v1_due_source_result_manifest_key(plan.instruction.cycle_id, requirement.source_id)
    )
    terminal = due_cycle._issue_terminal(
        HongKongV1DueTerminal(
            plan.instruction.cycle_id,
            plan.plan_fingerprint,
            plan.instruction.matrix_fingerprint,
            requirement,
            plan.instruction.observation_cutoff,
            requirement.result_schema,
            "sha256:" + "2" * 64,
            manifest,
            "sha256:" + "3" * 64,
            DueTerminalOutcome.COMPLETE,
            DueChangeStatus.NO_CHANGE,
            (),
            0,
            0,
            0,
            0,
            0,
            (),
        )
    )
    content, fingerprint = build_hk_v1_due_terminal(terminal)
    reference = DueTerminalReportReference(
        requirement.source_id,
        _reference(
            hk_v1_due_source_terminal_key(plan.instruction.cycle_id, requirement.source_id),
            fingerprint,
            len(content),
        ),
    )
    configured = DueSourceRegister(
        requirement.source_id,
        requirement.source_version,
        ("configured-endpoint",),
        "CONFIGURED",
        (),
    )

    def configured_sources(
        _registers: tuple[DueRegisterBundle, ...],
    ) -> dict[str, tuple[DueRegisterBundle, DueSourceRegister]]:
        return {requirement.source_id: (plan.registers[0], configured)}

    monkeypatch.setattr(
        due_cycle,
        "_register_sources",
        configured_sources,
    )
    with pytest.raises(HongKongV1DueCycleError, match="DUE_CYCLE_INVALID"):
        due_cycle._assert_terminal_binding(
            plan, reference, terminal, {requirement.source_id: requirement}
        )


def test_plan_copy_and_same_object_mutation_are_rejected() -> None:
    """Issued plan snapshots defeat copied/resealed policy objects."""
    plan = _plan()
    with pytest.raises(HongKongV1DueCycleError, match="CYCLE_PLAN_PROVENANCE_INVALID"):
        build_hk_v1_due_cycle_report(replace(plan), ())
    requirement = next(item for item in plan.requirements if item.outage_impact != "NONBLOCKING")
    original = requirement.outage_impact
    object.__setattr__(requirement, "outage_impact", "NONBLOCKING")
    try:
        with pytest.raises(HongKongV1DueCycleError, match="CYCLE_PLAN_PROVENANCE_INVALID"):
            build_hk_v1_due_cycle_report(plan, ())
    finally:
        object.__setattr__(requirement, "outage_impact", original)


@pytest.mark.parametrize(
    ("outcome", "change", "failure_codes", "counts"),
    [
        (DueTerminalOutcome.COMPLETE, DueChangeStatus.NOT_PROVED, (), (0, 0, 0, 0, 0)),
        (DueTerminalOutcome.GAP, DueChangeStatus.NO_CHANGE, (), (1, 0, 0, 1, 0)),
        (DueTerminalOutcome.FAILED, DueChangeStatus.NOT_PROVED, (), (1, 0, 0, 0, 1)),
        (
            DueTerminalOutcome.INCOMPLETE_OBSERVATION,
            DueChangeStatus.NOT_PROVED,
            (),
            (0, 0, 0, 0, 0),
        ),
        (DueTerminalOutcome.FAILED, DueChangeStatus.NOT_PROVED, ("X",), (1, 1, 0, 0, 1)),
    ],
)
def test_terminal_outcome_count_truth_table_rejects_mixed_or_hidden_counts(
    outcome: DueTerminalOutcome,
    change: DueChangeStatus,
    failure_codes: tuple[str, ...],
    counts: tuple[int, int, int, int, int],
) -> None:
    """Every terminal outcome has a closed count and failure relation."""
    plan = _plan()
    requirement = plan.requirements[0]
    with pytest.raises(HongKongV1DueCycleError, match="DUE_TERMINAL_INVALID"):
        HongKongV1DueTerminal(
            plan.instruction.cycle_id,
            plan.plan_fingerprint,
            plan.instruction.matrix_fingerprint,
            requirement,
            plan.instruction.observation_cutoff,
            requirement.result_schema,
            "sha256:" + "1" * 64,
            None,
            None,
            outcome,
            change,
            failure_codes,
            *counts,
            (),
        )


def test_unissued_terminal_cannot_enter_cycle_and_terminal_bytes_round_trip() -> None:
    """Canonical terminal parsing is separate from production result authority."""
    plan = _plan()
    terminal = _incomplete_terminal(plan)
    terminal_bytes, fingerprint = build_hk_v1_due_terminal(terminal)
    assert parse_hk_v1_due_terminal(terminal_bytes) == terminal
    reference = DueTerminalReportReference(
        terminal.requirement.source_id,
        DueImmutableReference(
            "PRIMARY", "wrong-key", "v" + "a" * 64, fingerprint, len(terminal_bytes)
        ),
    )
    with pytest.raises(HongKongV1DueCycleError, match="DUE_TERMINAL_PROVENANCE_INVALID"):
        build_hk_v1_due_cycle_report(plan, ((reference, terminal),))


@pytest.mark.parametrize(
    ("vault", "key", "length"),
    [("remote", "key", 1), ("PRIMARY", "", 1), ("PRIMARY", "key", -1)],
)
def test_immutable_reference_rejects_invalid_control_values(
    vault: str, key: str, length: int
) -> None:
    """Terminal references remain local, nonempty, and length-bound."""
    with pytest.raises(HongKongV1DueCycleError, match="DUE_REFERENCE_INVALID"):
        DueImmutableReference(vault, key, "v" + "1" * 64, "sha256:" + "1" * 64, length)


@pytest.mark.parametrize("mutation", ["schema", "cutoff", "unknown"])
def test_terminal_parser_rejects_malformed_or_resealed_bytes(mutation: str) -> None:
    """Terminal parser requires exact closed canonical content."""
    terminal_bytes, _ = build_hk_v1_due_terminal(_incomplete_terminal(_plan()))
    document = json.loads(terminal_bytes)
    if mutation == "schema":
        document["schema_id"] = "wrong"
    elif mutation == "cycle":
        document["cycle_id"] = "other-cycle"
    elif mutation == "cutoff":
        document["observation_cutoff"] = "bad"
    else:
        document["unknown"] = "forbidden"
    with pytest.raises(HongKongV1DueCycleError, match="DUE_TERMINAL_INVALID"):
        parse_hk_v1_due_terminal(canonicalize(checked_json_value(document)))


def test_direct_result_binding_and_test_only_binding_cannot_produce_terminal() -> None:
    """Reporting cannot bless a caller payload, JSON, digest, or test double."""
    plan = _plan()
    requirement = plan.requirements[0]
    binding = IssuedDueResultBinding(
        plan.instruction.cycle_id,
        plan.plan_fingerprint,
        plan.instruction.matrix_fingerprint,
        requirement,
        plan.instruction.observation_cutoff,
        requirement.result_schema,
        "1.0.0",
        DueImmutableReference(
            "PRIMARY",
            hk_v1_due_source_payload_key(plan.instruction.cycle_id, requirement.source_id),
            "v" + "4" * 64,
            "sha256:" + "4" * 64,
            1,
        ),
        None,
        DueTerminalOutcome.INCOMPLETE_OBSERVATION,
        DueChangeStatus.NOT_PROVED,
        ("UNADMITTED",),
        0,
        0,
        0,
        0,
        0,
        _incomplete_terminal(plan).registered_blockers,
    )
    attempt = DueImmutableReference("PRIMARY", "attempt", "v" + "5" * 64, "sha256:" + "5" * 64, 1)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_PROVENANCE_INVALID"):
        build_hk_v1_due_terminal_from_result_binding(binding, attempt)
    due_cycle.issue_test_only_due_result_binding(binding)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_PROVENANCE_INVALID"):
        build_hk_v1_due_terminal_from_result_binding(binding, attempt)


@pytest.mark.parametrize("artifact", [(), ((object(),),), ((object(), b"", b"", object()),)])
def test_cycle_parser_rejects_malformed_artifact_shapes(
    artifact: tuple[tuple[object, ...], ...],
) -> None:
    """Cycle parser fails closed before accepting any caller-supplied artifact."""
    with pytest.raises(HongKongV1DueCycleError, match="DUE_CYCLE_INVALID"):
        parse_hk_v1_due_cycle_report(b"{}", _plan(), artifact)


def test_issued_registries_release_dead_entries() -> None:
    """Weak registries do not grow forever across deterministic rederivations."""
    gc.collect()
    registry = getattr(due_cycle, "_" + "ISSUED_PLANS")
    baseline = len(registry)
    plans = [_plan() for _ in range(12)]
    assert len(registry) >= baseline + 12
    del plans
    gc.collect()
    assert len(registry) == baseline


@pytest.mark.parametrize(
    ("name", "source_ids"),
    [
        (
            "hk_legislation_source_register.json",
            (
                "HK-LEG-HKEL-CURRENT-INVENTORY",
                "HK-LEG-HKEL-CURRENT-DATA",
                "HK-LEG-HKEL-VERIFIED-COPIES",
                "HK-LEG-HKEL-ASSISTED-COPIES",
                "HK-LEG-HKEL-PAST-INVENTORY",
                "HK-LEG-HKEL-PAST-DATA",
                "HK-LEG-HKEL-EDITORIAL-RECORDS",
                "HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS",
                "HK-LEG-GLD-EGAZETTE",
                "HK-LEG-OFFICIAL-GAZETTE-ARCHIVE",
                "HK-LEG-HKEL-GAZETTE-BACKCAPTURE",
                "HK-LEG-BASIC-LAW-PORTAL",
                "HK-LEG-NPC-NATIONAL-LAWS-DATABASE",
                "HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS",
            ),
        ),
        (
            "hk_cases_source_register.json",
            (
                "HK-CASE-COURT-REGISTRY",
                "HK-CASE-HKLII-DISCOVERY",
                "HK-CASE-JUDICIARY-JUDGMENT",
                "HK-CASE-JUDICIARY-LIBRARY",
                "HK-CASE-JUDICIARY-LRS-INVENTORY",
                "HK-CASE-JUDICIARY-TRANSLATION",
                "HK-CASE-PRIVY-COUNCIL",
            ),
        ),
        (
            "hk_regulatory_source_register.json",
            (
                "HK-REG-HKEX-CONSOLIDATED-RULEBOOKS",
                "HK-REG-HKEX-FEES-RULES",
                "HK-REG-HKEX-REGULATORY-FORMS",
                "HK-REG-HKEX-RULE-UPDATES",
                "HK-REG-HKEX-RULEBOOK-CATALOGUE",
            ),
        ),
    ],
)
def test_frozen_register_full_source_identity(name: str, source_ids: tuple[str, ...]) -> None:
    """Every checked-in source role and its official order remain bound."""
    bundle = parse_hk_v1_due_register_bundle((_REGISTER_ROOT / name).read_bytes())
    assert tuple(source.source_id for source in bundle.sources) == source_ids


@pytest.mark.parametrize("name", _REGISTER_NAMES)
def test_frozen_register_id_version_fingerprint_and_source_versions_are_exact(name: str) -> None:
    """The due projection keeps every official register and source-version tuple intact."""
    document = json.loads((_REGISTER_ROOT / name).read_bytes())
    bundle = parse_hk_v1_due_register_bundle(canonicalize(checked_json_value(document)))
    expected = tuple((source["source_id"], source["version"]) for source in document["sources"])
    assert (bundle.register_id, bundle.register_version, bundle.register_fingerprint) == (
        document["register_id"],
        document["register_version"],
        document["fingerprint"],
    )
    assert tuple((source.source_id, source.source_version) for source in bundle.sources) == expected


@pytest.mark.parametrize("mutation", ["malformed", "unknown", "fingerprint", "ownership"])
def test_register_parser_closed_negative_matrix(mutation: str) -> None:
    """Register parsing rejects malformed, unknown, tampered, and wrong-family facts."""
    raw = (_REGISTER_ROOT / "hk_cases_source_register.json").read_bytes()
    if mutation == "malformed":
        content = b"{"
    else:
        document = json.loads(raw)
        if mutation == "unknown":
            document["unknown"] = True
        elif mutation == "fingerprint":
            document["fingerprint"] = "sha256:" + "0" * 64
        else:
            document["sources"][0]["source_id"] = "HK-LEG-GLD-EGAZETTE"
        content = canonicalize(checked_json_value(document))
    with pytest.raises(HongKongV1DueCycleError, match="REGISTER_BUNDLE_INVALID"):
        parse_hk_v1_due_register_bundle(content)


def test_copied_bundle_and_exact_restoration_provenance() -> None:
    """Direct copies fail while an exact restored issued bundle derives again."""
    bundles = _bundles()
    matrix = load_hk_v1_coverage_matrix()
    instruction = HongKongV1DueCycleInstruction(
        "hk-v1-copy-register-20260826",
        DueCycleKind.DAILY_CURRENT_LAW,
        "2026-08-26T00:00:00Z",
        "2026-08-26T00:00:00Z",
        matrix.revision,
        matrix.fingerprint,
    )
    with pytest.raises(HongKongV1DueCycleError, match="REGISTER_BUNDLE_PROVENANCE_INVALID"):
        derive_hk_v1_due_cycle_plan(instruction, matrix, (copy(bundles[0]), *bundles[1:]))
    source = bundles[0].sources[0]
    original = source.blockers
    object.__setattr__(source, "blockers", ("X",))
    with pytest.raises(HongKongV1DueCycleError, match="REGISTER_BUNDLE"):
        derive_hk_v1_due_cycle_plan(instruction, matrix, bundles)
    object.__setattr__(source, "blockers", original)
    assert derive_hk_v1_due_cycle_plan(instruction, matrix, bundles).requirements


@pytest.mark.parametrize("variant", ["copy", "replace", "new", "mutated", "test_only"])
def test_result_binding_negative_provenance_matrix(variant: str) -> None:
    """No direct, copied, rebuilt, mutated, or test-issued binding is production authority."""
    plan = _plan()
    requirement = plan.requirements[0]
    binding = IssuedDueResultBinding(
        plan.instruction.cycle_id,
        plan.plan_fingerprint,
        plan.instruction.matrix_fingerprint,
        requirement,
        plan.instruction.observation_cutoff,
        requirement.result_schema,
        "1.0.0",
        DueImmutableReference(
            "PRIMARY",
            hk_v1_due_source_payload_key(plan.instruction.cycle_id, requirement.source_id),
            "v" + "4" * 64,
            "sha256:" + "4" * 64,
            1,
        ),
        None,
        DueTerminalOutcome.INCOMPLETE_OBSERVATION,
        DueChangeStatus.NOT_PROVED,
        ("UNADMITTED",),
        0,
        0,
        0,
        0,
        0,
        _incomplete_terminal(plan).registered_blockers,
    )
    candidate = copy(binding) if variant == "copy" else replace(binding)
    if variant == "new":
        candidate = object.__new__(IssuedDueResultBinding)
    if variant == "mutated":
        object.__setattr__(candidate, "cycle_id", "other-cycle")
    if variant == "test_only":
        due_cycle.issue_test_only_due_result_binding(candidate)
    attempt = DueImmutableReference("PRIMARY", "attempt", "v" + "5" * 64, "sha256:" + "5" * 64, 1)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_PROVENANCE_INVALID"):
        build_hk_v1_due_terminal_from_result_binding(candidate, attempt)


@pytest.mark.parametrize("blockers", [(), ("FABRICATED",), ("EXTRA", "UNADMITTED")])
def test_terminal_requires_exact_registered_blockers(blockers: tuple[str, ...]) -> None:
    """Omitted, fabricated, and extra register blockers remain fail-visible."""
    plan = _plan()
    terminal = replace(_incomplete_terminal(plan), registered_blockers=blockers)
    reference, issued = _issued_incomplete_pair(plan, terminal)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_CYCLE_INVALID"):
        build_hk_v1_due_cycle_report(plan, ((reference, issued),))


def test_reversed_issued_terminal_input_has_identical_canonical_cycle_bytes() -> None:
    """Report ordering is canonical even when independently retained terminals arrive reversed."""
    plan = _plan()
    first = _issued_incomplete_pair(plan)
    second = _issued_incomplete_pair(plan, _incomplete_terminal(plan, plan.requirements[1]))
    forward = build_hk_v1_due_cycle_report(plan, (first, second))
    reverse = build_hk_v1_due_cycle_report(plan, (second, first))
    assert forward.canonical_bytes == reverse.canonical_bytes


def test_direct_bundle_and_subset_plan_cannot_claim_issued_provenance() -> None:
    """A constructor-shaped bundle or one-role plan is never an issued authority."""
    plan = _plan()
    first = _bundles()[0]
    direct = DueRegisterBundle(
        first.register_id, first.register_version, first.register_fingerprint, first.sources
    )
    matrix = load_hk_v1_coverage_matrix()
    with pytest.raises(HongKongV1DueCycleError, match="REGISTER_BUNDLE_PROVENANCE_INVALID"):
        derive_hk_v1_due_cycle_plan(plan.instruction, matrix, (direct, *_bundles()[1:]))
    with pytest.raises(HongKongV1DueCycleError, match="CYCLE_PLAN_INPUT_INVALID"):
        replace(plan, requirements=(plan.requirements[0],))


def test_two_register_plan_validation_rejects_regulatory_substitution() -> None:
    """A coherent two-register plan must contain the exact current family registers."""
    plan = _plan()
    legislation = next(bundle for bundle in plan.registers if bundle.register_id.startswith("hsr_"))
    regulatory = parse_hk_v1_due_register_bundle(
        (_REGISTER_ROOT / "hk_regulatory_source_register.json").read_bytes()
    )
    substituted_registers = tuple(
        sorted((legislation, regulatory), key=lambda bundle: bundle.register_id)
    )
    requirements = tuple(
        requirement
        for requirement in plan.requirements
        if requirement.register_id == legislation.register_id
    )
    requirements_fingerprint = due_cycle._fingerprint(
        [due_cycle._requirement_body(requirement) for requirement in requirements]
    )
    plan_fingerprint = due_cycle._plan_fingerprint(
        plan.instruction,
        substituted_registers,
        requirements_fingerprint,
        plan.predecessor_fingerprint,
    )

    with pytest.raises(HongKongV1DueCycleError, match="REGISTER_BUNDLE_INVALID"):
        due_cycle.HongKongV1DueCyclePlan(
            plan.instruction,
            substituted_registers,
            plan.predecessor_fingerprint,
            requirements,
            requirements_fingerprint,
            plan_fingerprint,
        )


def test_issued_terminal_copy_mutation_restoration_and_detached_attempt_are_closed() -> None:
    """Terminal issuance binds identity, snapshot, and the exact derived attempt key."""
    plan = _plan()
    reference, terminal = _issued_incomplete_pair(plan)
    assert build_hk_v1_due_cycle_report(plan, ((reference, terminal),)).missing_source_ids
    with pytest.raises(HongKongV1DueCycleError, match="DUE_TERMINAL_PROVENANCE_INVALID"):
        build_hk_v1_due_cycle_report(plan, ((reference, copy(terminal)),))
    original = terminal.result_fingerprint
    object.__setattr__(terminal, "result_fingerprint", "sha256:" + "b" * 64)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_TERMINAL_PROVENANCE_INVALID"):
        build_hk_v1_due_cycle_report(plan, ((reference, terminal),))
    object.__setattr__(terminal, "result_fingerprint", original)
    assert build_hk_v1_due_cycle_report(plan, ((reference, terminal),)).missing_source_ids
    detached = replace(terminal, attempt_manifest=_reference("detached-attempt"))
    detached = due_cycle._issue_terminal(detached)
    detached_content, detached_fingerprint = build_hk_v1_due_terminal(detached)
    detached_reference = DueTerminalReportReference(
        detached.requirement.source_id,
        _reference(
            hk_v1_due_source_terminal_key(
                plan.instruction.cycle_id, detached.requirement.source_id
            ),
            detached_fingerprint,
            len(detached_content),
        ),
    )
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_PROVENANCE_INVALID"):
        parse_hk_v1_due_cycle_report(
            build_hk_v1_due_cycle_report(plan, ((detached_reference, detached),)).canonical_bytes,
            plan,
            ((detached_reference, detached_content, b"{}", object()),),
        )


@pytest.mark.parametrize("target", ["plan", "terminal", "reference"])
def test_cycle_report_retains_only_snapshots_after_final_body_race(
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    """A caller object changed after the final body cannot alter a returned report."""
    plan = _plan()
    reference, terminal = _issued_incomplete_pair(plan)
    expected = build_hk_v1_due_cycle_report(plan, ((reference, terminal),))
    actual = due_cycle._cycle_body
    mutated = False

    def mutate_after_final_body(
        safe_plan: due_cycle.HongKongV1DueCyclePlan,
        references: tuple[DueTerminalReportReference, ...],
        terminals: tuple[HongKongV1DueTerminal, ...],
    ) -> dict[str, object]:
        nonlocal mutated
        body = actual(safe_plan, references, terminals)
        if not mutated:
            mutated = True
            if target == "plan":
                object.__setattr__(plan, "predecessor_fingerprint", "sha256:" + "b" * 64)
            elif target == "terminal":
                object.__setattr__(terminal, "outcome", DueTerminalOutcome.COMPLETE)
            else:
                object.__setattr__(reference, "source_id", "FORGED")
        return body

    monkeypatch.setattr(due_cycle, "_cycle_body", mutate_after_final_body)
    report = build_hk_v1_due_cycle_report(plan, ((reference, terminal),))
    assert report.canonical_bytes == expected.canonical_bytes
    assert report.complete_source_ids == expected.complete_source_ids
    assert report.missing_source_ids == expected.missing_source_ids
    assert report.duplicate_source_ids == expected.duplicate_source_ids
    assert report.gap_source_ids == expected.gap_source_ids
    assert report.failed_source_ids == expected.failed_source_ids
    assert report.release_blocking is expected.release_blocking
    assert report.disposition == expected.disposition
    assert report.terminal_report_references == expected.terminal_report_references
    assert report.plan is not plan
    assert report.terminals[0] is not terminal
    assert report.terminal_report_references[0] is not reference
    report.__post_init__()


def test_report_constructor_rebuilds_private_snapshots_before_storing_them() -> None:
    """Direct reconstruction cannot retain the prior report's mutable object identities."""
    report = _issued_report_with_missing_sources()
    rebuilt = replace(report)
    assert rebuilt.canonical_bytes == report.canonical_bytes
    assert rebuilt.plan is not report.plan
    assert rebuilt.terminals[0] is not report.terminals[0]
    assert rebuilt.terminal_report_references[0] is not report.terminal_report_references[0]
    object.__setattr__(report.terminals[0], "outcome", DueTerminalOutcome.COMPLETE)
    rebuilt.__post_init__()


@pytest.mark.parametrize(
    "field",
    ["result_schema_version", "expected_count", "result_schema", "failure_codes"],
)
def test_result_binding_rebuild_rejects_mutation_then_restores(field: str) -> None:
    """Every binding field is rebuilt before serialization or later issuance."""
    binding = _binding(_plan())
    original = getattr(binding, field)
    changed: object = {
        "result_schema_version": "9.9.9",
        "expected_count": 1,
        "result_schema": "wrong-family-schema",
        "failure_codes": (),
    }[field]
    object.__setattr__(binding, field, changed)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_INVALID"):
        build_hk_v1_due_result_manifest(binding)
    object.__setattr__(binding, field, original)
    content, fingerprint = build_hk_v1_due_result_manifest(binding)
    assert fingerprint == "sha256:" + sha256(content).hexdigest()


@pytest.mark.parametrize(
    "field",
    ["logical_key", "fingerprint", "byte_length", "vault", "version_id"],
)
def test_immutable_reference_rebuild_rejects_nested_mutation(field: str) -> None:
    """Reference controls are revalidated independently of dataclass equality."""
    reference = _reference("hk-v1/due-cycles/a/terminal.json")
    original = getattr(reference, field)
    changed: object = {
        "logical_key": "HK-UPPER",
        "fingerprint": "sha256:" + "B" * 64,
        "byte_length": -1,
        "vault": "OTHER",
        "version_id": "v1",
    }[field]
    object.__setattr__(reference, field, changed)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_REFERENCE_INVALID"):
        DueTerminalReportReference("HK-CASE-HKLII-DISCOVERY", reference)
    object.__setattr__(reference, field, original)
    assert DueTerminalReportReference("HK-CASE-HKLII-DISCOVERY", reference).reference == reference


def test_binding_manifest_is_public_canonical_but_not_an_issuer() -> None:
    """Slice B may persist exact bytes without gaining a reporting-side issuer."""
    plan = _plan()
    binding = _binding(plan)
    content, fingerprint = build_hk_v1_due_result_manifest(binding)
    attempt = _reference(
        hk_v1_due_source_result_manifest_key(
            plan.instruction.cycle_id, binding.requirement.source_id
        ),
        fingerprint,
        len(content),
    )
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_PROVENANCE_INVALID"):
        build_hk_v1_due_terminal_from_result_binding(binding, attempt)


@pytest.mark.parametrize(
    ("builder", "filename", "identity_scope"),
    [
        (hk_v1_due_source_payload_key, "payload.json", "source"),
        (hk_v1_due_source_result_manifest_key, "attempt.json", "source"),
        (hk_v1_due_source_terminal_key, "terminal.json", "source"),
        (hk_v1_due_cycle_manifest_key, "manifest.json", "cycle"),
    ],
)
def test_public_due_key_builders_are_reversible_digest_bound_and_case_exact(
    builder: Callable[..., str],
    filename: str,
    identity_scope: str,
) -> None:
    """Paths retain exact identities, not merely a collision-prone digest."""
    cycle = "Cycle-A_1"
    source = "Source-A_1"
    if identity_scope == "source":
        key = builder(cycle, source)
        due_cycle._validate_due_key(key, filename, cycle, source)
        assert key != builder(cycle.lower(), source)
        assert key != builder(cycle, source.lower())
    else:
        key = builder(cycle)
        due_cycle._validate_due_key(key, filename, cycle, None)
        assert key != builder(cycle.lower())
    assert all(len(part) <= 120 and re.fullmatch(r"[a-z0-9._-]+", part) for part in key.split("/"))


def test_due_key_long_identity_chunking_tamper_and_simulated_hash_collision_are_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hex reconstruction makes a digest collision and any path substitution visible."""
    cycle = "C" + "a" * 159
    source = "S" + "b" * 159
    key = hk_v1_due_source_payload_key(cycle, source)
    assert all(len(part) <= 120 for part in key.split("/"))
    due_cycle._validate_due_key(key, "payload.json", cycle, source)
    tampered = key.replace("hex-43", "hex-44", 1)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_REFERENCE_INVALID"):
        due_cycle._validate_due_key(tampered, "payload.json", cycle, source)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_REFERENCE_INVALID"):
        due_cycle._validate_due_key(key, "payload.json", cycle, source.lower())

    def colliding_digest(_value: str) -> str:
        return "0" * 64

    monkeypatch.setattr(due_cycle, "_key_digest", colliding_digest)
    first = hk_v1_due_source_payload_key("Cycle-A_1", "Source-A_1")
    second = hk_v1_due_source_payload_key("Cycle-A_1", "Source-B_1")
    assert first != second
    with pytest.raises(HongKongV1DueCycleError, match="DUE_REFERENCE_INVALID"):
        due_cycle._validate_due_key(first, "payload.json", "Cycle-A_1", "Source-B_1")


def test_binding_requires_exact_public_payload_key() -> None:
    """A correct digest/version cannot substitute a wrong cycle/source payload object."""
    binding = _binding(_plan())
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_INVALID"):
        replace(binding, payload_reference=_reference("payload"))


def test_slice_b_owned_positive_issuance_and_restart_replay_remain_unavailable() -> None:
    """Slice A deliberately contains no marker-free positive production issuer or restart replay."""
    plan = _plan()
    binding = _binding(plan)
    content, fingerprint = build_hk_v1_due_result_manifest(binding)
    attempt = _reference(
        hk_v1_due_source_result_manifest_key(
            plan.instruction.cycle_id, binding.requirement.source_id
        ),
        fingerprint,
        len(content),
    )
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_PROVENANCE_INVALID"):
        build_hk_v1_due_terminal_from_result_binding(binding, attempt)


def _production_binding_simulation(
    binding: IssuedDueResultBinding | None = None,
) -> tuple[IssuedDueResultBinding, DueImmutableReference]:
    """Create the private test-only production registry state needed by converter tests."""
    binding = _binding(_plan()) if binding is None else binding
    content, fingerprint = build_hk_v1_due_result_manifest(binding)
    binding_id = id(binding)

    def cleanup(dead: due_cycle.ReferenceType[IssuedDueResultBinding]) -> None:
        current = due_cycle._ISSUED_RESULT_BINDINGS.get(binding_id)
        if current is not None and current[0] is dead:
            del due_cycle._ISSUED_RESULT_BINDINGS[binding_id]

    due_cycle._ISSUED_RESULT_BINDINGS[binding_id] = (
        due_cycle.ref(binding, cleanup),
        content,
        False,
    )
    return binding, _reference(
        hk_v1_due_source_result_manifest_key(binding.cycle_id, binding.requirement.source_id),
        fingerprint,
        len(content),
    )


class _MissingConverterFields:
    """A converter-boundary object with no reference fields."""


@pytest.mark.parametrize("attempt", [object(), _MissingConverterFields()])
def test_converter_normalizes_plain_or_missing_attempt_before_any_terminal_issuance(
    attempt: object,
) -> None:
    """Wrong outer attempt objects cannot leak or mint a terminal."""
    binding, _valid_attempt = _production_binding_simulation()
    before = dict(due_cycle._ISSUED_TERMINALS)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_TERMINAL_INVALID"):
        build_hk_v1_due_terminal_from_result_binding(binding, attempt)
    assert before == due_cycle._ISSUED_TERMINALS


@pytest.mark.parametrize(
    "field", ["vault", "logical_key", "version_id", "fingerprint", "byte_length"]
)
def test_converter_rebuilds_mutated_or_deleted_exact_attempt_before_use(field: str) -> None:
    """Every attempt-reference field is replayed before comparison or serialization."""
    binding, attempt = _production_binding_simulation()
    before = dict(due_cycle._ISSUED_TERMINALS)
    object.__delattr__(attempt, field)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_TERMINAL_INVALID"):
        build_hk_v1_due_terminal_from_result_binding(binding, attempt)
    assert before == due_cycle._ISSUED_TERMINALS


@pytest.mark.parametrize("field", ["payload_reference", "evidence_reference"])
def test_registered_binding_nested_reference_mutation_is_closed_before_terminal_issuance(
    field: str,
) -> None:
    """Registered snapshots do not permit hostile nested reference access on conversion."""
    binding = _binding(_plan())
    if field == "evidence_reference":
        binding = replace(binding, evidence_reference=_reference("evidence"))
    binding, attempt = _production_binding_simulation(binding)
    before = dict(due_cycle._ISSUED_TERMINALS)
    object.__setattr__(binding, field, _MissingNestedFields())
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_PROVENANCE_INVALID"):
        build_hk_v1_due_terminal_from_result_binding(binding, attempt)
    assert before == due_cycle._ISSUED_TERMINALS


def test_registered_binding_copy_mutation_and_restoration_are_not_converter_authority() -> None:
    """Only the exact registered binding survives the converter's reconstruction checks."""
    binding, attempt = _production_binding_simulation()
    copied = copy(binding)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_PROVENANCE_INVALID"):
        build_hk_v1_due_terminal_from_result_binding(copied, attempt)
    original = binding.payload_reference
    object.__setattr__(binding, "payload_reference", _MissingNestedFields())
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_PROVENANCE_INVALID"):
        build_hk_v1_due_terminal_from_result_binding(binding, attempt)
    object.__setattr__(binding, "payload_reference", original)
    terminal = build_hk_v1_due_terminal_from_result_binding(binding, attempt)
    assert terminal.requirement == binding.requirement


def test_converter_issues_only_rebuilt_binding_snapshot_after_post_snapshot_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mutation after snapshot creation cannot alter the issued terminal facts."""
    binding, attempt = _production_binding_simulation()
    original_payload = binding.payload_reference
    original_requirement = binding.requirement
    original_snapshot = due_cycle._binding_snapshot

    def mutate_after_snapshot(value: IssuedDueResultBinding) -> bytes:
        content = original_snapshot(value)
        object.__setattr__(
            binding,
            "payload_reference",
            _reference("changed-payload", "sha256:" + "b" * 64),
        )
        object.__setattr__(binding, "evidence_reference", _reference("changed-evidence"))
        object.__setattr__(
            binding,
            "requirement",
            replace(original_requirement, source_version="9.9.9"),
        )
        object.__setattr__(binding, "result_schema", "forged-schema")
        object.__setattr__(binding, "expected_count", 1)
        return content

    monkeypatch.setattr(due_cycle, "_binding_snapshot", mutate_after_snapshot)
    terminal = build_hk_v1_due_terminal_from_result_binding(binding, attempt)
    assert terminal.result_fingerprint == original_payload.fingerprint
    assert terminal.requirement == original_requirement
    assert terminal.expected_count == 0
    assert terminal.result_schema == original_requirement.result_schema


def test_public_result_manifest_uses_rebuilt_snapshot_after_rebuild_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Public result serialization must not read the original after reconstruction."""
    binding = _binding(_plan())
    original_payload = binding.payload_reference
    actual = due_cycle._rebuild_result_binding
    calls = 0

    def mutate_after_rebuild(value: object, code: str) -> IssuedDueResultBinding:
        nonlocal calls
        calls += 1
        rebuilt = actual(value, code)
        object.__setattr__(
            binding,
            "payload_reference",
            _reference("changed-payload", "sha256:" + "b" * 64),
        )
        return rebuilt

    monkeypatch.setattr(due_cycle, "_rebuild_result_binding", mutate_after_rebuild)
    content, _fingerprint = build_hk_v1_due_result_manifest(binding)
    document = json.loads(content)
    assert calls == 1
    assert document["payload_reference"]["fingerprint"] == original_payload.fingerprint


def test_process_local_issued_artifact_round_trip_reaches_nonempty_parser_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A private test simulation reaches parser artifact and byte comparison checks."""
    plan = _plan()
    binding = _binding(plan)
    result_manifest, result_fingerprint = build_hk_v1_due_result_manifest(binding)
    due_cycle._ISSUED_RESULT_BINDINGS[id(binding)] = (
        due_cycle.ref(binding),
        result_manifest,
        False,
    )
    attempt = _reference(
        hk_v1_due_source_result_manifest_key(
            plan.instruction.cycle_id, binding.requirement.source_id
        ),
        result_fingerprint,
        len(result_manifest),
    )
    terminal = build_hk_v1_due_terminal_from_result_binding(binding, attempt)
    content, fingerprint = build_hk_v1_due_terminal(terminal)
    reference = DueTerminalReportReference(
        terminal.requirement.source_id,
        _reference(
            hk_v1_due_source_terminal_key(
                plan.instruction.cycle_id, terminal.requirement.source_id
            ),
            fingerprint,
            len(content),
        ),
    )
    report = build_hk_v1_due_cycle_report(plan, ((reference, terminal),))
    calls = 0
    actual = due_cycle._terminal_artifact_bindings

    def observed(artifacts: tuple[tuple[object, ...], ...]) -> tuple[tuple[object, object], ...]:
        nonlocal calls
        calls += 1
        return actual(artifacts)

    monkeypatch.setattr(due_cycle, "_terminal_artifact_bindings", observed)
    artifacts = ((reference, content, result_manifest, binding),)
    assert parse_hk_v1_due_cycle_report(report.canonical_bytes, plan, artifacts) == report
    assert calls == 1
    document = json.loads(report.canonical_bytes)
    document["release_blocking"] = not document["release_blocking"]
    with pytest.raises(HongKongV1DueCycleError, match="DUE_CYCLE_INVALID"):
        parse_hk_v1_due_cycle_report(canonicalize(checked_json_value(document)), plan, artifacts)
    assert calls == 2
    for field, value in {
        "matrix": {"fingerprint": "sha256:" + "0" * 64},
        "registers": [],
        "requirements": [],
        "complete_source_ids": ["forged"],
        "missing_source_ids": [],
        "duplicate_source_ids": ["forged"],
        "gap_source_ids": ["forged"],
        "failed_source_ids": ["forged"],
        "accounting_complete": True,
        "disposition": "COMPLETE",
    }.items():
        changed = json.loads(report.canonical_bytes)
        changed[field] = value
        with pytest.raises(HongKongV1DueCycleError, match="DUE_CYCLE_INVALID"):
            parse_hk_v1_due_cycle_report(canonicalize(checked_json_value(changed)), plan, artifacts)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_CYCLE_INVALID"):
        parse_hk_v1_due_cycle_report(report.canonical_bytes, plan, ((),))
    assert calls == 13
    detached_reference = DueTerminalReportReference(
        reference.source_id,
        _reference(reference.reference.logical_key, "sha256:" + "0" * 64, len(content)),
    )
    with pytest.raises(HongKongV1DueCycleError, match="DUE_CYCLE_INVALID"):
        parse_hk_v1_due_cycle_report(
            report.canonical_bytes,
            plan,
            ((detached_reference, content, result_manifest, binding),),
        )
    assert calls == 14
    registration = due_cycle._ISSUED_RESULT_BINDINGS.get(id(binding))
    if registration is not None and registration[0]() is binding:
        del due_cycle._ISSUED_RESULT_BINDINGS[id(binding)]


def test_all_issued_registries_release_dead_entries() -> None:
    """Bundle, plan, binding, and terminal weak registries use identity-safe cleanup."""
    registries = (
        due_cycle._ISSUED_REGISTERS,
        due_cycle._ISSUED_PLANS,
        due_cycle._ISSUED_RESULT_BINDINGS,
        due_cycle._ISSUED_TERMINALS,
    )
    gc.collect()
    baseline = tuple(len(registry) for registry in registries)
    bundles = _bundles()
    plan = _plan()
    binding = _binding(plan)
    due_cycle.issue_test_only_due_result_binding(binding)
    terminal = due_cycle._issue_terminal(_incomplete_terminal(plan))
    assert all(
        len(registry) >= before for registry, before in zip(registries, baseline, strict=True)
    )
    del terminal, binding, plan, bundles
    gc.collect()
    assert tuple(len(registry) for registry in registries) == baseline


def test_cycle_snapshot_registries_release_dead_entries() -> None:
    """Cycle-private plan and terminal snapshots do not retain reports or inputs."""
    registries = (due_cycle._CYCLE_PLAN_SNAPSHOTS, due_cycle._CYCLE_TERMINAL_SNAPSHOTS)
    gc.collect()
    baseline = tuple(len(registry) for registry in registries)
    plan = _plan()
    reference, terminal = _issued_incomplete_pair(plan)
    report = build_hk_v1_due_cycle_report(plan, ((reference, terminal),))
    assert all(
        len(registry) >= before for registry, before in zip(registries, baseline, strict=True)
    )
    del report, terminal, reference, plan
    gc.collect()
    assert tuple(len(registry) for registry in registries) == baseline


def test_concurrent_plan_derivation_is_deterministic_and_registry_safe() -> None:
    """Parallel fresh derivations keep their exact issued snapshots independent."""
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(_plan) for _ in range(32)]
        plans = [future.result() for future in futures]
    assert len({plan.plan_fingerprint for plan in plans}) == 1
    assert all(plan.requirements for plan in plans)


class _EqualityHashLiar(str):
    """A hostile primitive that would defeat ordinary equality and set checks."""

    __slots__ = ()

    def __eq__(self, other: object) -> bool:
        return True

    def __ne__(self, other: object) -> bool:
        return False

    def __hash__(self) -> int:
        return hash("COMPLETE")


def _issued_report_with_missing_sources() -> due_cycle.HongKongV1DueCycleReport:
    plan = _plan()
    reference, terminal = _issued_incomplete_pair(plan)
    return build_hk_v1_due_cycle_report(plan, ((reference, terminal),))


@pytest.mark.parametrize(
    "field",
    [
        "complete_source_ids",
        "missing_source_ids",
        "duplicate_source_ids",
        "gap_source_ids",
        "failed_source_ids",
    ],
)
def test_cached_source_id_fields_reject_exact_tuple_and_string_equality_liars(field: str) -> None:
    """Every cached source field validates tuple/string primitives before equality."""
    report = _issued_report_with_missing_sources()
    original = getattr(report, field)
    forged = tuple(_EqualityHashLiar("FORGED") for _ in range(max(1, len(original))))
    object.__setattr__(report, field, forged)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_CYCLE_INVALID"):
        report.__post_init__()


def test_equal_length_cached_source_tuple_liars_cannot_pass_revalidation() -> None:
    """The reviewer-reproduced equal-length missing tuple bypass is permanently closed."""
    report = _issued_report_with_missing_sources()
    forged = tuple(_EqualityHashLiar("FORGED") for _ in report.missing_source_ids)
    assert len(forged) == len(report.missing_source_ids)
    object.__setattr__(report, "missing_source_ids", forged)
    with pytest.raises(HongKongV1DueCycleError, match="DUE_CYCLE_INVALID"):
        report.__post_init__()


def test_disposition_equality_hash_and_inequality_liar_cannot_pass_closed_check() -> None:
    """Closed disposition checks require an exact built-in string before membership."""
    report = _issued_report_with_missing_sources()
    object.__setattr__(report, "disposition", _EqualityHashLiar("FORGED"))
    with pytest.raises(HongKongV1DueCycleError, match="DUE_CYCLE_INVALID"):
        report.__post_init__()


@pytest.mark.parametrize("field", ["technical_state", "rights_state", "policy_conflict"])
def test_requirement_closed_literals_reject_equality_hash_liars_before_membership(
    field: str,
) -> None:
    """Admission and conflict fields require exact built-in strings before closed checks."""
    requirement = _plan().requirements[0]
    with pytest.raises(HongKongV1DueCycleError, match="DUE_REQUIREMENT_INVALID"):
        replace(requirement, **{field: _EqualityHashLiar("FORGED")})


def test_terminal_and_binding_schema_version_liars_reject_before_serialization() -> None:
    """Neither public serializer can preserve a forged schema-version subclass."""
    terminal = _incomplete_terminal(_plan())
    with pytest.raises(HongKongV1DueCycleError, match="DUE_TERMINAL_INVALID"):
        replace(terminal, result_schema_version=_EqualityHashLiar("FORGED"))
    binding = _binding(_plan())
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_INVALID"):
        replace(binding, result_schema_version=_EqualityHashLiar("FORGED"))


class _UnhashableString(str):
    """A string-shaped value that must fail before set/sort normalisation."""

    __slots__ = ()

    def __hash__(self) -> int:
        return hash([])


class _MissingNestedFields:
    """A hostile replacement that has none of a nested contract's fields."""


@pytest.mark.parametrize(
    ("field", "forged"),
    [
        ("cycle_id", "x"),
        ("cycle_kind", "FORGED"),
        ("scheduled_at", "bad"),
        ("observation_cutoff", "bad"),
        ("matrix_revision", _EqualityHashLiar("FORGED")),
        ("matrix_fingerprint", _EqualityHashLiar("FORGED")),
    ],
)
def test_plan_derivation_rebuilds_every_same_object_instruction_field(
    field: str, forged: object
) -> None:
    """No mutated instruction field can enter the issued-plan registry."""
    matrix = load_hk_v1_coverage_matrix()
    instruction = HongKongV1DueCycleInstruction(
        "hk-v1-instruction-replay-20260826",
        DueCycleKind.DAILY_CURRENT_LAW,
        "2026-08-26T00:00:00Z",
        "2026-08-26T00:00:00Z",
        matrix.revision,
        matrix.fingerprint,
    )
    object.__setattr__(instruction, field, forged)
    with pytest.raises(HongKongV1DueCycleError):
        derive_hk_v1_due_cycle_plan(instruction, matrix, _bundles())


@pytest.mark.parametrize(
    ("field", "forged"),
    [
        ("material_family", "FORGED"),
        ("source_id", "FORGED"),
        ("source_version", "FORGED"),
        ("cadence", "FORGED"),
        ("outage_impact", "FORGED"),
        ("register_id", "FORGED"),
        ("register_version", "FORGED"),
        ("register_fingerprint", "sha256:" + "0" * 64),
        ("matrix_policy_fingerprint", "FORGED"),
        ("policy_conflict", "FORGED"),
        ("result_schema", "FORGED"),
        ("technical_state", "FORGED"),
        ("rights_state", "FORGED"),
    ],
)
def test_resealed_direct_plan_rejects_every_mutated_nested_requirement_field(
    field: str, forged: object
) -> None:
    """Recomputing fingerprints cannot make a forged nested requirement valid."""
    plan = _plan()
    requirement = plan.requirements[0]
    object.__setattr__(requirement, field, forged)
    object.__setattr__(
        plan,
        "requirements_fingerprint",
        due_cycle._fingerprint([_unsafe_requirement_body(item) for item in plan.requirements]),
    )
    object.__setattr__(
        plan,
        "plan_fingerprint",
        due_cycle._plan_fingerprint(
            plan.instruction,
            plan.registers,
            plan.requirements_fingerprint,
            plan.predecessor_fingerprint,
        ),
    )
    with pytest.raises(HongKongV1DueCycleError, match="CYCLE_PLAN_INPUT_INVALID"):
        plan.__post_init__()


def _unsafe_requirement_body(requirement: HongKongV1DueRequirement) -> dict[str, object]:
    """Test-only reseal projection that intentionally does not validate hostile input."""
    return {
        field: getattr(requirement, field)
        for field in (
            "material_family",
            "source_id",
            "source_version",
            "cadence",
            "outage_impact",
            "register_id",
            "register_version",
            "register_fingerprint",
            "matrix_policy_fingerprint",
            "policy_conflict",
            "result_schema",
            "technical_state",
            "rights_state",
        )
    }


@pytest.mark.parametrize(
    "field",
    [
        "cycle_id",
        "cycle_kind",
        "scheduled_at",
        "observation_cutoff",
        "matrix_revision",
        "matrix_fingerprint",
    ],
)
def test_plan_derivation_rejects_equality_liar_in_every_instruction_field(field: str) -> None:
    """Exact replay precedes all instruction comparisons, sort, and fingerprint work."""
    matrix = load_hk_v1_coverage_matrix()
    instruction = HongKongV1DueCycleInstruction(
        "hk-v1-instruction-liar-20260826",
        DueCycleKind.DAILY_CURRENT_LAW,
        "2026-08-26T00:00:00Z",
        "2026-08-26T00:00:00Z",
        matrix.revision,
        matrix.fingerprint,
    )
    object.__setattr__(instruction, field, _EqualityHashLiar("FORGED"))
    with pytest.raises(HongKongV1DueCycleError, match="CYCLE_PLAN_INPUT_INVALID"):
        derive_hk_v1_due_cycle_plan(instruction, matrix, _bundles())


@pytest.mark.parametrize(
    "field",
    [
        "material_family",
        "source_id",
        "source_version",
        "cadence",
        "outage_impact",
        "register_id",
        "register_version",
        "register_fingerprint",
        "matrix_policy_fingerprint",
        "policy_conflict",
        "result_schema",
        "technical_state",
        "rights_state",
    ],
)
def test_direct_plan_rejects_equality_liar_in_every_nested_requirement_field(field: str) -> None:
    """A same-object requirement mutation cannot reach plan serialization or issuance."""
    plan = _plan()
    object.__setattr__(plan.requirements[0], field, _EqualityHashLiar("FORGED"))
    with pytest.raises(HongKongV1DueCycleError, match="CYCLE_PLAN_INPUT_INVALID"):
        plan.__post_init__()


def test_public_result_manifest_normalizes_hostile_nested_requirement() -> None:
    """Result serialization never leaks a raw nested-object exception."""
    binding = _binding(_plan())
    object.__setattr__(binding, "requirement", _MissingNestedFields())
    with pytest.raises(HongKongV1DueCycleError, match="DUE_RESULT_BINDING_INVALID"):
        build_hk_v1_due_result_manifest(binding)


@pytest.mark.parametrize("field", ["endpoint_ids", "blockers"])
def test_source_register_unhashable_tuple_items_fail_closed(field: str) -> None:
    """Register tuples validate exact leaves before deduplication or sorting."""
    source = _bundles()[0].sources[0]
    values = (_UnhashableString("FORGED"),)
    with pytest.raises(HongKongV1DueCycleError, match="REGISTER_BUNDLE_INVALID"):
        replace(source, **{field: values})


@pytest.mark.parametrize("field", ["failure_codes", "registered_blockers"])
def test_terminal_unhashable_tuple_items_fail_closed(field: str) -> None:
    """Terminal tuples validate exact leaves before deduplication or sorting."""
    terminal = _incomplete_terminal(_plan())
    with pytest.raises(HongKongV1DueCycleError, match="DUE_TERMINAL_INVALID"):
        replace(terminal, **{field: (_UnhashableString("FORGED"),)})


def test_public_terminal_serializer_normalizes_hostile_nested_requirement() -> None:
    """A mutated exact terminal never leaks AttributeError from nested access."""
    terminal = _incomplete_terminal(_plan())
    object.__setattr__(terminal, "requirement", _MissingNestedFields())
    with pytest.raises(HongKongV1DueCycleError, match="DUE_TERMINAL_INVALID"):
        build_hk_v1_due_terminal(terminal)


def test_public_cycle_builder_normalizes_hostile_nested_plan_and_reference() -> None:
    """Plan and reference reconstruction happens before nested access or sort keys."""
    plan = _plan()
    reference, terminal = _issued_incomplete_pair(plan)
    object.__setattr__(plan, "instruction", _MissingNestedFields())
    with pytest.raises(HongKongV1DueCycleError, match="CYCLE_PLAN_PROVENANCE_INVALID"):
        build_hk_v1_due_cycle_report(plan, ((reference, terminal),))

    plan = _plan()
    reference, terminal = _issued_incomplete_pair(plan)
    object.__setattr__(reference, "reference", _MissingNestedFields())
    with pytest.raises(HongKongV1DueCycleError, match="DUE_CYCLE_INVALID"):
        build_hk_v1_due_cycle_report(plan, ((reference, terminal),))
