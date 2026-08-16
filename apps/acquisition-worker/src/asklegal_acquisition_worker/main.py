"""Acquisition worker process entry point."""

import argparse

from asklegal_acquisition_worker.runtime import create_runtime


def main() -> None:
    """Validate the no-ingress worker configuration and local adapters."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    runtime = create_runtime()
    if args.check:
        if not runtime.ready():
            raise SystemExit(1)
        return
    runtime.run_once(lambda _lease: None)


if __name__ == "__main__":
    main()
