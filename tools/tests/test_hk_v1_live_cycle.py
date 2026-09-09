"""Pure Task 9 schedule-slot, replay, and overlap contract tests."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import asklegal_control_plane.v1_schedule as schedule_module
import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_durable_task import OrchestrationStatus
from asklegal_reporting import (
    DueCycleKind,
    HongKongV1CoverageMatrix,
    load_hk_v1_coverage_matrix,
)

from tools.hk_v1_live_cycle import (
    AcceptanceCycleError,
    AcceptanceCycleKind,
    AcceptanceCycleRequest,
    InMemoryLiveScheduleStore,
    LiveScheduleError,
    LiveScheduleStore,
    LocalLiveScheduleStore,
    ScheduleEnqueueResult,
    ScheduleKind,
    ScheduleState,
    dispatch_acceptance_cycle,
    enqueue_schedule,
    main,
    mark_schedule_terminal,
    preflight_acceptance_cycle,
    read_acceptance_cycle_result,
    release_terminal_schedules,
    retain_acceptance_cycle,
    retain_acceptance_cycle_result,
    schedule_definitions,
    schedule_request,
)

_OBSERVATION = "2026-09-08T02:15:00+08:00"
_NEXT_OBSERVATION = "2026-09-09T02:15:00+08:00"
_RECONCILIATION = "2026-09-13T03:15:00+08:00"
_POST_RECONCILIATION_OBSERVATION = "2026-09-14T02:15:00+08:00"


def _family_evidence(cases_fingerprint: str, legislation_fingerprint: str) -> dict[str, JsonValue]:
    children: list[JsonValue] = []
    for family, fingerprint, marker in (
        ("CASES", cases_fingerprint, "c"),
        ("LEGISLATION", legislation_fingerprint, "d"),
    ):
        cycle_id = f"cyc_{marker * 48}"
        children.append(
            {
                "source_family": family,
                "cycle_id": cycle_id,
                "journal_ref": f"acquisition-journals/{cycle_id}",
                "manifest_fingerprint": fingerprint,
                "journal_head_fingerprint": "sha256:" + marker * 64,
                "result": "COMPLETE",
                "manifest_reference": {
                    "vault": "PRIMARY",
                    "logical_key": f"retained/{family.casefold()}.json",
                    "version_id": "v" + marker * 64,
                    "fingerprint": "sha256:" + marker * 64,
                    "byte_length": 1,
                },
            }
        )
    return {
        "schema_id": "asklegal.hk-v1.acceptance-family-acquisition-evidence",
        "schema_version": "1.0.0",
        "root_cycle_id": "manual-cycle",
        "root_plan_fingerprint": "sha256:" + "e" * 64,
        "evidence_reference": {
            "vault": "PRIMARY",
            "logical_key": "retained/family-evidence.json",
            "version_id": "v" + "e" * 64,
            "fingerprint": "sha256:" + "e" * 64,
            "byte_length": 1,
        },
        "children": children,
    }


def _successful_due_state() -> SimpleNamespace:
    return SimpleNamespace(
        runtime_status=OrchestrationStatus.COMPLETED,
        serialized_output=json.dumps(
            {
                "acceptance": {
                    "schema_id": "asklegal.hk-v1.acceptance-cycle-result",
                    "schema_version": "1.0.0",
                    "kind": "UPDATE",
                    "operation_id": "cyc_" + "1" * 64,
                    "command_fingerprint": "sha256:" + "2" * 64,
                    "observation_cutoff": "2026-09-07T18:15:00Z",
                    "families": ["CASES", "LEGISLATION"],
                    "scope_ids": [
                        "HK-CASE-BINDING-POST-1997",
                        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
                        "HK-LEG-ORDINANCES",
                        "HK-LEG-SUBSIDIARY",
                    ],
                    "result": "NO_CHANGE",
                    "blocker_codes": [],
                    "proposal_reference": None,
                }
            }
        ),
    )


def _cutoff_selection() -> bytes:
    t1_cases = "sha256:" + "1" * 64
    t1_legislation = "sha256:" + "2" * 64
    t2_cases = "sha256:" + "3" * 64
    t2_legislation = "sha256:" + "2" * 64
    body: dict[str, JsonValue] = {
        "families": ["CASES", "LEGISLATION"],
        "schema_id": "asklegal.hk-v1.acceptance-cutoff-selection",
        "schema_version": "1.0.0",
        "scope_ids": [
            "HK-CASE-BINDING-POST-1997",
            "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
            "HK-LEG-ORDINANCES",
            "HK-LEG-SUBSIDIARY",
        ],
        "t1": {
            "authentic_changed_families": [],
            "cases_manifest_fingerprint": t1_cases,
            "legislation_manifest_fingerprint": t1_legislation,
            "observation_cutoff": "2026-09-07T00:00:00Z",
            "family_acquisition_evidence": _family_evidence(t1_cases, t1_legislation),
        },
        "t2": {
            "authentic_changed_families": ["CASES"],
            "cases_manifest_fingerprint": t2_cases,
            "legislation_manifest_fingerprint": t2_legislation,
            "observation_cutoff": "2026-09-08T00:00:00Z",
            "family_acquisition_evidence": _family_evidence(t2_cases, t2_legislation),
        },
    }
    body["fingerprint"] = "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()
    return canonicalize(checked_json_value(body))


def _acceptance_result(request: AcceptanceCycleRequest) -> dict[str, JsonValue]:
    operation_id = request.operation_id
    return {
        "schema_id": "asklegal.hk-v1.acceptance-cycle-result",
        "schema_version": "1.0.0",
        "kind": request.kind.value,
        "operation_id": operation_id,
        "command_fingerprint": request.command_fingerprint,
        "observation_cutoff": request.observation_cutoff,
        "families": ["CASES", "LEGISLATION"],
        "scope_ids": [
            "HK-CASE-BINDING-POST-1997",
            "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
            "HK-LEG-ORDINANCES",
            "HK-LEG-SUBSIDIARY",
        ],
        "result": "PROPOSAL_READY",
        "blocker_codes": [],
        "proposal_reference": {
            "vault": "PRIMARY",
            "logical_key": f"proposals/{operation_id}.json",
            "version_id": "v" + "a" * 64,
            "fingerprint": "sha256:" + "b" * 64,
            "byte_length": 1,
        },
    }


def _enqueue(
    store: LiveScheduleStore,
    kind: ScheduleKind,
    scheduled_at: str,
) -> ScheduleEnqueueResult:
    return enqueue_schedule(
        store,
        kind,
        scheduled_at,
        matrix=load_hk_v1_coverage_matrix(),
    )


def test_schedule_catalogue_is_exact_two_family_v1() -> None:
    """The live catalogue contains five activities and only two source families."""
    definitions = schedule_definitions()

    assert tuple(item.kind for item in definitions) == (
        ScheduleKind.OBSERVATION,
        ScheduleKind.RECONCILIATION,
        ScheduleKind.AUDIT_ARCHIVE,
        ScheduleKind.RECOVERY_VERIFY,
        ScheduleKind.TELEMETRY_RETENTION,
    )
    assert tuple(item.on_calendar for item in definitions) == (
        "*-*-* 02:15:00 Asia/Hong_Kong",
        "Sun *-*-* 03:15:00 Asia/Hong_Kong",
        "*-*-* 04:30:00 Asia/Hong_Kong",
        "Mon *-*-* 05:15:00 Asia/Hong_Kong",
        "*-*-* 06:00:00 Asia/Hong_Kong",
    )
    source_definitions = tuple(item for item in definitions if item.due_cycle_kind is not None)
    assert tuple(item.due_cycle_kind for item in source_definitions) == (
        DueCycleKind.DAILY_CURRENT_LAW,
        DueCycleKind.FULL_PERIODIC,
    )
    assert all(item.source_families == ("CASES", "LEGISLATION") for item in source_definitions)


def test_acceptance_baseline_preflight_binds_frozen_cutoff_and_matrix_without_dispatch() -> None:
    """Task 10 preflight is a complete no-effect request for the exact T1 lineage."""
    request = preflight_acceptance_cycle(
        AcceptanceCycleKind.BASELINE,
        _cutoff_selection(),
        cutoff_key="t1",
        matrix=load_hk_v1_coverage_matrix(),
    )

    assert request.kind is AcceptanceCycleKind.BASELINE
    assert request.cutoff_key == "t1"
    assert request.observation_cutoff == "2026-09-07T00:00:00Z"
    assert request.changed_families == ()
    assert request.command_id.startswith("cmd_")
    assert request.operation_id.startswith("cyc_")
    assert request.command_fingerprint.startswith("sha256:")
    assert request.families == ("CASES", "LEGISLATION")
    assert len(request.scope_ids) == 4
    assert request.document()["family_acquisition_evidence"] == request.family_acquisition_evidence


def test_acceptance_update_dispatch_uses_one_stable_control_instance() -> None:
    """The enqueue boundary uses the frozen T2 identity and exact replay-safe instance ID."""
    request = preflight_acceptance_cycle(
        AcceptanceCycleKind.UPDATE,
        _cutoff_selection(),
        cutoff_key="t2",
        matrix=load_hk_v1_coverage_matrix(),
    )

    class _Client:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object, str, str]] = []

        def get_orchestration_state(self, instance_id: str) -> object | None:
            assert instance_id == request.operation_id
            return None

        def schedule_new_orchestration(
            self,
            orchestrator: str,
            *,
            input: object,  # noqa: A002 - exact scheduler keyword.
            instance_id: str,
            version: str,
        ) -> str:
            self.calls.append((orchestrator, input, instance_id, version))
            return instance_id

    client = _Client()
    assert dispatch_acceptance_cycle(client, request) == "SCHEDULED"
    assert client.calls == [
        (
            "run_hk_v1_acceptance_cycle",
            request.document(),
            request.operation_id,
            "1.0.0",
        )
    ]


@pytest.mark.parametrize(
    ("kind", "cutoff_key"),
    [
        (AcceptanceCycleKind.BASELINE, "t2"),
        (AcceptanceCycleKind.UPDATE, "t1"),
    ],
)
def test_acceptance_cycle_rejects_wrong_cutoff_role_before_dispatch(
    kind: AcceptanceCycleKind,
    cutoff_key: str,
) -> None:
    """T1 cannot be relabelled as update and T2 cannot be relabelled as baseline."""
    with pytest.raises(AcceptanceCycleError, match="ACCEPTANCE_CUTOFF_ROLE_INVALID"):
        preflight_acceptance_cycle(
            kind,
            _cutoff_selection(),
            cutoff_key=cutoff_key,
            matrix=load_hk_v1_coverage_matrix(),
        )


def test_acceptance_cycle_rejects_noncanonical_or_hkex_selection() -> None:
    """A caller cannot widen accepted two-family scope or rewrite canonical bytes."""
    selection = json.loads(_cutoff_selection())
    selection["families"].append("REGULATORY")
    selection["scope_ids"].append("HK-REG-HKEX-MAIN")
    widened = json.dumps(selection, sort_keys=True).encode()
    for content in (b" " + _cutoff_selection(), widened):
        with pytest.raises(AcceptanceCycleError, match="ACCEPTANCE_CUTOFF_INVALID"):
            preflight_acceptance_cycle(
                AcceptanceCycleKind.UPDATE,
                content,
                cutoff_key="t2",
                matrix=load_hk_v1_coverage_matrix(),
            )


def test_acceptance_cli_defaults_to_preflight_and_does_not_enqueue(
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """The operator command is no-effect unless `--mode enqueue` is explicit."""
    selection = tmp_path / "cutoffs.json"
    selection.write_bytes(_cutoff_selection() + b"\n")
    matrix = (
        Path(__file__).parents[2]
        / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )

    assert (
        main(
            [
                "--kind",
                "BASELINE",
                "--cutoff-file",
                str(selection),
                "--cutoff-key",
                "t1",
                "--matrix",
                str(matrix),
            ]
        )
        == 0
    )
    output = json.loads(capfd.readouterr().out)
    assert output["enqueued"] is False
    assert output["resolution"] == "PREFLIGHT_READY"
    assert output["kind"] == "BASELINE"


def test_acceptance_request_is_retained_before_dispatch_and_replays_after_restart(
    tmp_path: Path,
) -> None:
    """A lost memory-only scheduler instance cannot erase the frozen T2 command."""
    request = preflight_acceptance_cycle(
        AcceptanceCycleKind.UPDATE,
        _cutoff_selection(),
        cutoff_key="t2",
        matrix=load_hk_v1_coverage_matrix(),
    )

    assert retain_acceptance_cycle(tmp_path, request) == "RETAINED"
    assert retain_acceptance_cycle(tmp_path, request) == "EXACT_REPLAY"
    state_path = tmp_path / "hk-v1-acceptance-cycles" / f"{request.operation_id}.json"
    assert json.loads(state_path.read_bytes()) == request.document()
    assert state_path.read_bytes().endswith(b"\n")


def test_completed_acceptance_result_is_rebound_retained_and_replayed(tmp_path: Path) -> None:
    """Gate G can consume the exact owner result after a scheduler restart."""
    request = preflight_acceptance_cycle(
        AcceptanceCycleKind.BASELINE,
        _cutoff_selection(),
        cutoff_key="t1",
        matrix=load_hk_v1_coverage_matrix(),
    )
    result = _acceptance_result(request)

    class _Client:
        def get_orchestration_state(self, instance_id: str) -> object:
            assert instance_id == request.operation_id
            return SimpleNamespace(
                instance_id=instance_id,
                name="run_hk_v1_acceptance_cycle",
                runtime_status=OrchestrationStatus.COMPLETED,
                serialized_output=canonicalize(checked_json_value(result)).decode("utf-8"),
            )

        def schedule_new_orchestration(self, *_args: object, **_kwargs: object) -> str:
            pytest.fail("result readback attempted to schedule work")

    content = read_acceptance_cycle_result(_Client(), request)
    output = tmp_path / "results" / "baseline.json"
    assert retain_acceptance_cycle_result(output, content) == "RETAINED"
    assert retain_acceptance_cycle_result(output, content) == "EXACT_REPLAY"
    assert output.read_bytes() == canonicalize(checked_json_value(result))
    assert output.stat().st_mode & 0o777 == 0o600


def test_acceptance_result_cli_exports_without_dispatch(
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
) -> None:
    """Result mode performs one read-only scheduler lookup and atomic publication."""
    selection = tmp_path / "cutoffs.json"
    selection.write_bytes(_cutoff_selection() + b"\n")
    matrix = (
        Path(__file__).parents[2]
        / "packages/reporting/src/asklegal_reporting/hk_v1_coverage_matrix.json"
    )
    request = preflight_acceptance_cycle(
        AcceptanceCycleKind.BASELINE,
        _cutoff_selection(),
        cutoff_key="t1",
        matrix=load_hk_v1_coverage_matrix(),
    )
    result = _acceptance_result(request)

    class _Client:
        def get_orchestration_state(self, instance_id: str) -> object:
            return SimpleNamespace(
                instance_id=instance_id,
                name="run_hk_v1_acceptance_cycle",
                runtime_status=OrchestrationStatus.COMPLETED,
                serialized_output=canonicalize(checked_json_value(result)).decode("utf-8"),
            )

        def schedule_new_orchestration(self, *_args: object, **_kwargs: object) -> str:
            pytest.fail("result export attempted to schedule work")

    output = tmp_path / "results" / "baseline.json"
    arguments = [
        "--kind",
        "BASELINE",
        "--cutoff-file",
        str(selection),
        "--cutoff-key",
        "t1",
        "--matrix",
        str(matrix),
        "--mode",
        "result",
        "--output",
        str(output),
    ]
    client = _Client()
    assert main(arguments, scheduler_client=client) == 0
    assert json.loads(capfd.readouterr().out)["resolution"] == "RESULT_RETAINED"
    assert output.read_bytes() == canonicalize(checked_json_value(result))
    assert main(arguments, scheduler_client=client) == 0
    assert json.loads(capfd.readouterr().out)["resolution"] == "RESULT_EXACT_REPLAY"


def test_acceptance_result_drift_is_rejected_before_output(tmp_path: Path) -> None:
    """A terminal result cannot be rebound to a different exact request."""
    request = preflight_acceptance_cycle(
        AcceptanceCycleKind.UPDATE,
        _cutoff_selection(),
        cutoff_key="t2",
        matrix=load_hk_v1_coverage_matrix(),
    )
    result = _acceptance_result(request)
    result["command_fingerprint"] = "sha256:" + "f" * 64

    class _Client:
        def get_orchestration_state(self, instance_id: str) -> object:
            assert instance_id == request.operation_id
            return SimpleNamespace(
                instance_id=request.operation_id,
                name="run_hk_v1_acceptance_cycle",
                runtime_status=OrchestrationStatus.COMPLETED,
                serialized_output=canonicalize(checked_json_value(result)).decode("utf-8"),
            )

        def schedule_new_orchestration(self, *_args: object, **_kwargs: object) -> str:
            pytest.fail("result readback attempted to schedule work")

    with pytest.raises(AcceptanceCycleError, match="ACCEPTANCE_RESULT_READBACK_INVALID"):
        read_acceptance_cycle_result(_Client(), request)
    assert not (tmp_path / "result.json").exists()


def test_acceptance_identity_binds_exact_family_evidence() -> None:
    """A changed retained evidence reference cannot replay under the old stable ID."""
    original = json.loads(_cutoff_selection())
    changed = json.loads(_cutoff_selection())
    changed["t2"]["family_acquisition_evidence"]["evidence_reference"]["version_id"] = (
        "v" + "f" * 64
    )
    unsigned = dict(changed)
    unsigned.pop("fingerprint")
    changed["fingerprint"] = "sha256:" + sha256(canonicalize(unsigned)).hexdigest()

    first = preflight_acceptance_cycle(
        AcceptanceCycleKind.UPDATE,
        canonicalize(original),
        cutoff_key="t2",
        matrix=load_hk_v1_coverage_matrix(),
    )
    second = preflight_acceptance_cycle(
        AcceptanceCycleKind.UPDATE,
        canonicalize(changed),
        cutoff_key="t2",
        matrix=load_hk_v1_coverage_matrix(),
    )

    assert first.operation_id != second.operation_id
    assert first.command_fingerprint != second.command_fingerprint


def test_retained_acceptance_request_rejects_same_identity_with_drift(tmp_path: Path) -> None:
    """A caller cannot overwrite a previously retained request after a crash."""
    request = preflight_acceptance_cycle(
        AcceptanceCycleKind.BASELINE,
        _cutoff_selection(),
        cutoff_key="t1",
        matrix=load_hk_v1_coverage_matrix(),
    )
    retain_acceptance_cycle(tmp_path, request)
    state_path = tmp_path / "hk-v1-acceptance-cycles" / f"{request.operation_id}.json"
    state_path.write_bytes(b"{}\n")

    with pytest.raises(AcceptanceCycleError, match="ACCEPTANCE_STATE_CONFLICT"):
        retain_acceptance_cycle(tmp_path, request)


def test_same_hong_kong_schedule_slot_has_stable_command_cycle_and_journal() -> None:
    """Duplicate timer delivery replays the exact durable source-cycle identity."""
    store = InMemoryLiveScheduleStore()

    first = _enqueue(store, ScheduleKind.OBSERVATION, _OBSERVATION)
    second = _enqueue(store, ScheduleKind.OBSERVATION, _OBSERVATION)

    assert first.resolution == "RESULT_RECORDED"
    assert first.state is ScheduleState.STARTED
    assert second.resolution == "EXACT_REPLAY"
    assert second.state is ScheduleState.STARTED
    assert second.command_id == first.command_id
    assert second.cycle_id == first.cycle_id
    assert second.journal_ref == first.journal_ref
    assert second.instruction == first.instruction
    assert first.cycle_id is not None
    assert first.cycle_id.startswith("cyc_")
    assert first.journal_ref == f"acquisition-journals/{first.cycle_id}"


def test_same_slot_with_different_coverage_matrix_lineage_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A retained slot cannot silently replay under a changed Coverage Matrix."""
    store = InMemoryLiveScheduleStore()
    matrix = load_hk_v1_coverage_matrix()
    changed = replace(
        matrix,
        revision=matrix.revision + ".drift",
        fingerprint="sha256:" + "9" * 64,
    )

    def approve_test_matrix(_matrix: HongKongV1CoverageMatrix) -> bool:
        return True

    monkeypatch.setattr(
        schedule_module,
        "is_hk_v1_coverage_matrix_policy_approved",
        approve_test_matrix,
    )

    first_request = schedule_request(ScheduleKind.OBSERVATION, _OBSERVATION, matrix=matrix)
    changed_request = schedule_request(ScheduleKind.OBSERVATION, _OBSERVATION, matrix=changed)
    assert changed_request.command_id == first_request.command_id
    assert changed_request.command_fingerprint != first_request.command_fingerprint

    _enqueue(store, ScheduleKind.OBSERVATION, _OBSERVATION)
    with pytest.raises(LiveScheduleError, match="SCHEDULE_COMMAND_CONFLICT"):
        enqueue_schedule(
            store,
            ScheduleKind.OBSERVATION,
            _OBSERVATION,
            matrix=changed,
        )


def test_interrupted_process_resumes_exact_cycle_and_journal() -> None:
    """A replacement coordinator uses retained state instead of a competing baseline."""
    retained_store = InMemoryLiveScheduleStore()
    before_interrupt = _enqueue(retained_store, ScheduleKind.OBSERVATION, _OBSERVATION)

    after_restart = _enqueue(retained_store, ScheduleKind.OBSERVATION, _OBSERVATION)

    assert after_restart.resolution == "EXACT_REPLAY"
    assert after_restart.cycle_id == before_interrupt.cycle_id
    assert after_restart.journal_ref == before_interrupt.journal_ref
    assert retained_store.command_count == 1


def test_file_retained_restart_resumes_exact_cycle_and_journal(tmp_path: Path) -> None:
    """A genuinely reopened local adapter preserves the exact active acquisition."""
    state_path = tmp_path / "control" / "hk-v1-live-schedules.json"
    before_interrupt = _enqueue(
        LocalLiveScheduleStore(state_path), ScheduleKind.OBSERVATION, _OBSERVATION
    )

    after_restart = _enqueue(
        LocalLiveScheduleStore(state_path), ScheduleKind.OBSERVATION, _OBSERVATION
    )

    assert after_restart.resolution == "EXACT_REPLAY"
    assert after_restart.cycle_id == before_interrupt.cycle_id
    assert after_restart.journal_ref == before_interrupt.journal_ref
    assert state_path.read_bytes().endswith(b"\n")


def test_overlapping_source_slot_coalesces_onto_active_cycle() -> None:
    """A new due source slot cannot start a second acquisition baseline."""
    store = InMemoryLiveScheduleStore()
    active = _enqueue(store, ScheduleKind.OBSERVATION, _OBSERVATION)

    overlap = _enqueue(store, ScheduleKind.RECONCILIATION, _RECONCILIATION)
    overlap_replay = _enqueue(store, ScheduleKind.RECONCILIATION, _RECONCILIATION)

    assert overlap.resolution == "RESULT_RECORDED"
    assert overlap.state is ScheduleState.COALESCED_IN_PROGRESS
    assert overlap.command_id != active.command_id
    assert overlap.cycle_id == active.cycle_id
    assert overlap.journal_ref == active.journal_ref
    assert overlap.instruction == active.instruction
    assert overlap.root_schedule_kind is ScheduleKind.OBSERVATION
    assert overlap.root_scheduled_at == _OBSERVATION
    assert overlap_replay.resolution == "EXACT_REPLAY"
    assert overlap_replay.state is ScheduleState.COALESCED_IN_PROGRESS
    assert overlap_replay.cycle_id == active.cycle_id
    assert store.active_count == 1


def test_terminal_source_cycle_releases_next_schedule_slot() -> None:
    """Only a terminal exact root permits the next source schedule to start."""
    store = InMemoryLiveScheduleStore()
    first = _enqueue(store, ScheduleKind.OBSERVATION, _OBSERVATION)
    assert first.cycle_id is not None

    mark_schedule_terminal(store, first.cycle_id)
    second = _enqueue(store, ScheduleKind.OBSERVATION, _NEXT_OBSERVATION)

    assert second.state is ScheduleState.STARTED
    assert second.cycle_id != first.cycle_id
    assert second.journal_ref != first.journal_ref


def test_terminal_root_promotes_oldest_coalesced_source_slot() -> None:
    """A weekly reconciliation queued behind observation is not silently lost."""
    store = InMemoryLiveScheduleStore()
    observation = _enqueue(store, ScheduleKind.OBSERVATION, _OBSERVATION)
    queued = _enqueue(store, ScheduleKind.RECONCILIATION, _RECONCILIATION)
    assert observation.cycle_id is not None
    assert queued.state is ScheduleState.COALESCED_IN_PROGRESS

    mark_schedule_terminal(store, observation.cycle_id)
    promoted = _enqueue(store, ScheduleKind.RECONCILIATION, _RECONCILIATION)

    assert promoted.resolution == "EXACT_REPLAY"
    assert promoted.state is ScheduleState.STARTED
    assert promoted.operation_id != observation.operation_id
    assert promoted.operation_id == promoted.cycle_id
    assert promoted.root_schedule_kind is ScheduleKind.RECONCILIATION
    assert promoted.root_scheduled_at == _RECONCILIATION
    assert promoted.journal_ref == f"acquisition-journals/{promoted.cycle_id}"
    assert store.active_count == 1


def test_file_retained_waiting_slots_advance_in_order_across_restarts(tmp_path: Path) -> None:
    """Queued source slots survive process replacement and each becomes the exact root."""
    state_path = tmp_path / "control" / "hk-v1-live-schedules.json"
    first_store = LocalLiveScheduleStore(state_path)
    observation = _enqueue(first_store, ScheduleKind.OBSERVATION, _OBSERVATION)
    reconciliation = _enqueue(first_store, ScheduleKind.RECONCILIATION, _RECONCILIATION)
    next_observation = _enqueue(
        first_store, ScheduleKind.OBSERVATION, _POST_RECONCILIATION_OBSERVATION
    )
    assert reconciliation.state is ScheduleState.COALESCED_IN_PROGRESS
    assert next_observation.state is ScheduleState.COALESCED_IN_PROGRESS

    second_store = LocalLiveScheduleStore(state_path)
    mark_schedule_terminal(second_store, observation.operation_id)
    promoted_reconciliation = _enqueue(
        LocalLiveScheduleStore(state_path), ScheduleKind.RECONCILIATION, _RECONCILIATION
    )
    still_waiting = _enqueue(
        LocalLiveScheduleStore(state_path),
        ScheduleKind.OBSERVATION,
        _POST_RECONCILIATION_OBSERVATION,
    )

    assert promoted_reconciliation.state is ScheduleState.STARTED
    assert promoted_reconciliation.root_schedule_kind is ScheduleKind.RECONCILIATION
    assert still_waiting.state is ScheduleState.COALESCED_IN_PROGRESS
    assert still_waiting.operation_id == promoted_reconciliation.operation_id

    mark_schedule_terminal(LocalLiveScheduleStore(state_path), promoted_reconciliation.operation_id)
    promoted_observation = _enqueue(
        LocalLiveScheduleStore(state_path),
        ScheduleKind.OBSERVATION,
        _POST_RECONCILIATION_OBSERVATION,
    )

    assert promoted_observation.state is ScheduleState.STARTED
    assert promoted_observation.root_schedule_kind is ScheduleKind.OBSERVATION
    assert promoted_observation.operation_id == promoted_observation.cycle_id


def test_scheduler_terminal_reconciliation_releases_exact_active_root() -> None:
    """A later slot can start only after exact Durable Task terminal evidence."""
    store = InMemoryLiveScheduleStore()
    first = _enqueue(store, ScheduleKind.OBSERVATION, _OBSERVATION)

    class _Client:
        def get_orchestration_state(self, instance_id: str) -> object:
            assert instance_id == first.operation_id
            return _successful_due_state()

        def schedule_new_orchestration(
            self,
            orchestrator: str,
            *,
            input: object,  # noqa: A002 - exact scheduler protocol keyword.
            instance_id: str,
            version: str,
        ) -> str:
            del orchestrator, input, version
            return instance_id

    release_terminal_schedules(store, _Client())
    second = _enqueue(store, ScheduleKind.OBSERVATION, _NEXT_OBSERVATION)

    assert second.state is ScheduleState.STARTED
    assert second.operation_id != first.operation_id


@pytest.mark.parametrize(
    "status",
    [OrchestrationStatus.FAILED, OrchestrationStatus.TERMINATED],
)
def test_failed_or_terminated_source_root_remains_active_for_exact_recovery(
    status: OrchestrationStatus,
) -> None:
    """Unexpected scheduler termination cannot advance to a competing source lineage."""
    store = InMemoryLiveScheduleStore()
    first = _enqueue(store, ScheduleKind.OBSERVATION, _OBSERVATION)

    class _Client:
        def get_orchestration_state(self, instance_id: str) -> object:
            assert instance_id == first.operation_id
            return SimpleNamespace(runtime_status=status)

        def schedule_new_orchestration(
            self,
            orchestrator: str,
            *,
            input: object,  # noqa: A002 - exact scheduler protocol keyword.
            instance_id: str,
            version: str,
        ) -> str:
            del orchestrator, input, version
            return instance_id

    retries = release_terminal_schedules(store, _Client())
    overlap = _enqueue(store, ScheduleKind.RECONCILIATION, _RECONCILIATION)

    assert len(retries) == 1
    assert retries[0].resolution == "RESULT_RETRY"
    assert overlap.state is ScheduleState.COALESCED_IN_PROGRESS
    assert overlap.operation_id == retries[0].operation_id
    assert overlap.operation_id != first.operation_id
    assert overlap.cycle_id == first.cycle_id
    assert store.active_count == 1


@pytest.mark.parametrize(
    ("kind", "scheduled_at"),
    [
        (ScheduleKind.OBSERVATION, "2026-09-08T02:15:01+08:00"),
        (ScheduleKind.OBSERVATION, "2026-09-08T02:15:00Z"),
        (ScheduleKind.RECONCILIATION, "2026-09-08T03:15:00+08:00"),
        (ScheduleKind.RECOVERY_VERIFY, "2026-09-08T05:15:00+08:00"),
        (ScheduleKind.TELEMETRY_RETENTION, "2026-09-08T06:00:00.000000+08:00"),
    ],
)
def test_noncanonical_or_wrong_schedule_slot_fails_closed(
    kind: ScheduleKind, scheduled_at: str
) -> None:
    """Caller wall-clock values cannot mint arbitrary scheduled identities."""
    with pytest.raises(LiveScheduleError, match="SCHEDULE_SLOT_INVALID"):
        _enqueue(InMemoryLiveScheduleStore(), kind, scheduled_at)


def test_non_source_operations_do_not_mint_acquisition_instructions() -> None:
    """Maintenance timers remain distinct from the two source-cycle instructions."""
    store = InMemoryLiveScheduleStore()

    audit = _enqueue(store, ScheduleKind.AUDIT_ARCHIVE, "2026-09-08T04:30:00+08:00")
    recovery = _enqueue(store, ScheduleKind.RECOVERY_VERIFY, "2026-09-14T05:15:00+08:00")
    telemetry = _enqueue(store, ScheduleKind.TELEMETRY_RETENTION, "2026-09-08T06:00:00+08:00")

    assert all(item.cycle_id is None for item in (audit, recovery, telemetry))
    assert all(item.journal_ref is None for item in (audit, recovery, telemetry))
    assert all(item.instruction is None for item in (audit, recovery, telemetry))
    assert store.active_count == 3


def test_concurrent_duplicate_delivery_has_one_recorded_winner() -> None:
    """The atomic store resolves concurrent delivery to one durable command."""
    store = InMemoryLiveScheduleStore()

    def submit(_index: int) -> ScheduleEnqueueResult:
        return _enqueue(store, ScheduleKind.OBSERVATION, _OBSERVATION)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(
            pool.map(
                submit,
                range(2),
            )
        )

    assert sorted(item.resolution for item in results) == ["EXACT_REPLAY", "RESULT_RECORDED"]
    assert len({item.command_id for item in results}) == 1
    assert len({item.cycle_id for item in results}) == 1
    assert store.command_count == 1
    assert store.active_count == 1
