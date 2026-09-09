"""Acquisition worker process entry point."""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

from asklegal_acquisition_worker.runtime import create_runtime
from asklegal_acquisition_worker.v1_progress import (
    HKV1ProgressError,
    canonical_hk_v1_progress,
    load_hk_v1_progress,
)
from asklegal_acquisition_worker.v1_service import run as run_v1_service


def _progress_as_of(value: str | None) -> datetime:
    if value is None:
        return datetime.now(tz=UTC).replace(microsecond=0)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as error:
        message = "as-of must be canonical UTC seconds"
        raise argparse.ArgumentTypeError(message) from error
    return parsed


def main() -> None:
    """Validate the no-ingress worker configuration and local adapters."""
    parser = argparse.ArgumentParser()
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true")
    action.add_argument("--serve", action="store_true")
    action.add_argument("--show-hk-v1-progress", action="store_true")
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--cases-cycle-id")
    parser.add_argument("--legislation-cycle-id")
    parser.add_argument("--cases-result", type=Path)
    parser.add_argument("--legislation-result", type=Path)
    parser.add_argument("--as-of")
    args = parser.parse_args()
    if args.show_hk_v1_progress:
        if (
            args.state_root is None
            or args.cases_cycle_id is None
            or args.legislation_cycle_id is None
        ):
            parser.error(
                "--show-hk-v1-progress requires --state-root, "
                "--cases-cycle-id, and --legislation-cycle-id"
            )
        try:
            snapshot = load_hk_v1_progress(
                state_root=args.state_root,
                cases_cycle_id=args.cases_cycle_id,
                legislation_cycle_id=args.legislation_cycle_id,
                cases_result_path=args.cases_result,
                legislation_result_path=args.legislation_result,
                as_of=_progress_as_of(args.as_of),
            )
            sys.stdout.write(canonical_hk_v1_progress(snapshot).decode("utf-8"))
        except HKV1ProgressError, argparse.ArgumentTypeError:
            sys.stderr.write("HK_V1_PROGRESS_UNAVAILABLE\n")
            raise SystemExit(2) from None
        return
    if args.serve:
        raise SystemExit(run_v1_service())
    runtime = create_runtime()
    if args.check:
        if not runtime.ready():
            raise SystemExit(1)
        return
    runtime.run_once(lambda _lease: None)


if __name__ == "__main__":
    main()
