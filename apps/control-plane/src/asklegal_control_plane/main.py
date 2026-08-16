"""Control-plane process entry point."""

import argparse

import uvicorn

from asklegal_control_plane.api import create_app, local_dependencies


def main() -> None:
    """Validate configuration or run the ASGI server."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    dependencies = local_dependencies()
    if args.check:
        if not dependencies.register.check():
            raise SystemExit(1)
        return
    uvicorn.run(create_app(dependencies), host="127.0.0.1", port=8001)


if __name__ == "__main__":
    main()
