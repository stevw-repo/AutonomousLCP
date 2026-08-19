"""Review API process entry point."""

import argparse

import uvicorn

from asklegal_review_api.api import create_app, local_dependencies
from asklegal_review_api.v1_service import run as run_v1_service


def main() -> None:
    """Validate configuration or run the ASGI server."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    if args.serve:
        raise SystemExit(run_v1_service())
    dependencies = local_dependencies()
    if args.check:
        if not dependencies.register.check() or not dependencies.projections.check():
            raise SystemExit(1)
        return
    uvicorn.run(create_app(dependencies), host="127.0.0.1", port=8002)


if __name__ == "__main__":
    main()
