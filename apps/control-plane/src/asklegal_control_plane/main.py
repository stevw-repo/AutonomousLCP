"""Control-plane process entry point."""

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import uvicorn
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import checked_json_value
from asklegal_durable_task import V1SchedulerSettings
from asklegal_reporting import load_hk_v1_coverage_matrix

from asklegal_control_plane.api import create_app, local_dependencies
from asklegal_control_plane.v1_schedule import (
    LiveScheduleError,
    LiveSchedulerClient,
    LocalLiveScheduleStore,
    ScheduleKind,
    applicable_schedule_slot,
    dispatch_schedule,
    enqueue_schedule,
    release_terminal_schedules,
    validate_systemd_invocation_id,
)
from asklegal_control_plane.v1_service import run as run_v1_service

_SCHEDULE_STATE_FILE = "hk-v1-live-schedules.json"
_DEFAULT_CONTROL_STATE_ROOT = "/var/lib/asklegal/control"


def _schedule_now() -> datetime:
    """Return adapter time; schedule identity is still resolved to a calendar slot."""
    return datetime.now(UTC)


def _enqueue_live_schedule(
    kind: ScheduleKind,
    scheduled_at: str | None,
    invocation_id: object,
) -> bytes:
    """Retain one schedule command before ensuring its durable instance exists."""
    delivery_invocation_id = validate_systemd_invocation_id(invocation_id)
    root = Path(os.environ.get("ASKLEGAL_CONTROL_STATE_ROOT", _DEFAULT_CONTROL_STATE_ROOT))
    if not root.is_absolute() or root.is_symlink():
        message = "SCHEDULE_STATE_PATH_INVALID"
        raise LiveScheduleError(message)
    slot = scheduled_at or applicable_schedule_slot(kind, _schedule_now())
    store = LocalLiveScheduleStore(root / _SCHEDULE_STATE_FILE)
    settings = V1SchedulerSettings.for_application("CONTROL_PLANE")
    client = settings.create_client(default_version="1.0.0")
    typed_client = cast("LiveSchedulerClient", client)
    promoted = release_terminal_schedules(store, typed_client)
    for waiting in promoted:
        dispatch_schedule(typed_client, waiting)
    result = enqueue_schedule(
        store,
        kind,
        slot,
        matrix=load_hk_v1_coverage_matrix(),
        invocation_id=delivery_invocation_id,
    )
    dispatch = dispatch_schedule(typed_client, result)
    document = checked_json_value(
        {
            "activity_complete": False,
            "command_id": result.command_id,
            "cycle_id": result.cycle_id,
            "dispatch": dispatch,
            "delivery_invocation_id": delivery_invocation_id,
            "delivery_invocation_ids": list(result.delivery_invocation_ids),
            "journal_ref": result.journal_ref,
            "operation_id": result.operation_id,
            "attempt_number": result.attempt_number,
            "resolution": result.resolution,
            "schedule_kind": result.schedule_kind.value,
            "scheduled_at": result.scheduled_at,
            "state": result.state.value,
        }
    )
    return canonicalize(document) + b"\n"


def main() -> None:
    """Validate configuration or run the ASGI server."""
    parser = argparse.ArgumentParser()
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--serve", action="store_true")
    actions.add_argument("--enqueue-schedule", choices=tuple(item.value for item in ScheduleKind))
    parser.add_argument("--scheduled-at")
    parser.add_argument("--invocation-id")
    args = parser.parse_args()
    if args.scheduled_at is not None and args.enqueue_schedule is None:
        parser.error("--scheduled-at requires --enqueue-schedule")
    if args.invocation_id is not None and args.enqueue_schedule is None:
        parser.error("--invocation-id requires --enqueue-schedule")
    if args.enqueue_schedule is not None and args.invocation_id is None:
        parser.error("--enqueue-schedule requires --invocation-id")
    if args.serve:
        raise SystemExit(run_v1_service())
    if args.enqueue_schedule is not None:
        try:
            output = _enqueue_live_schedule(
                ScheduleKind(args.enqueue_schedule),
                args.scheduled_at,
                args.invocation_id,
            )
        except Exception:  # noqa: BLE001 - process boundary emits only one safe failure code.
            sys.stderr.write("SCHEDULE_COMMAND_FAILED\n")
            raise SystemExit(2) from None
        sys.stdout.buffer.write(output)
        return
    dependencies = local_dependencies()
    if args.check:
        if not dependencies.register.check():
            raise SystemExit(1)
        return
    uvicorn.run(create_app(dependencies), host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
