"""Independent JSON-contract oracle for the M2 lifecycle kernel."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from asklegal_contracts import parse_json_bytes
from asklegal_domain import (
    COVERAGE_GAP_MACHINE,
    PIPELINE_RUN_MACHINE,
    QUARANTINE_MACHINE,
    SOURCE_CONTRACT_REVIEW_MACHINE,
    WORK_ITEM_MACHINE,
    StateMachine,
)

if TYPE_CHECKING:
    from asklegal_contracts.json_types import JsonValue

_CONTRACTS_ROOT = Path(__file__).resolve().parents[2] / "contracts"


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _array(value: JsonValue) -> list[JsonValue]:
    assert isinstance(value, list)
    return value


def _text(value: JsonValue) -> str:
    assert isinstance(value, str)
    return value


def _load_contract(relative_path: str) -> dict[str, JsonValue]:
    raw = (_CONTRACTS_ROOT / relative_path).read_bytes()
    return _object(parse_json_bytes(raw, max_bytes=max(len(raw), 1)))


def _assert_machine_matches_contract[StateT: StrEnum](
    machine: StateMachine[StateT],
    relative_path: str,
) -> None:
    contract = _load_contract(relative_path)
    assert machine.machine_id == _text(contract["machine_id"])
    assert machine.machine_version == _text(contract["machine_version"])
    assert machine.entity_type == _text(contract["entity_type"])

    contract_states = frozenset(
        machine.state_type(_text(value)) for value in _array(contract["states"])
    )
    contract_initial_states = tuple(
        machine.state_type(_text(value)) for value in _array(contract["initial_states"])
    )
    contract_terminal_states = frozenset(
        machine.state_type(_text(value)) for value in _array(contract["terminal_states"])
    )
    contract_transitions = frozenset(
        (
            machine.state_type(_text(_object(value)["from"])),
            machine.state_type(_text(_object(value)["to"])),
        )
        for value in _array(contract["allowed_transitions"])
    )

    assert contract_states == frozenset(machine.state_type)
    assert contract_initial_states == (machine.initial_state,)
    assert contract_terminal_states == machine.terminal_states
    assert contract_transitions == machine.transitions


def test_python_machines_exactly_match_the_five_normative_json_contracts() -> None:
    """Require exact Python agreement with every structural contract field."""
    _assert_machine_matches_contract(PIPELINE_RUN_MACHINE, "transitions/pipeline-run.json")
    _assert_machine_matches_contract(WORK_ITEM_MACHINE, "transitions/work-item.json")
    _assert_machine_matches_contract(
        SOURCE_CONTRACT_REVIEW_MACHINE,
        "transitions/source-contract-review.json",
    )
    _assert_machine_matches_contract(COVERAGE_GAP_MACHINE, "transitions/coverage-gap.json")
    _assert_machine_matches_contract(QUARANTINE_MACHINE, "transitions/quarantine.json")
