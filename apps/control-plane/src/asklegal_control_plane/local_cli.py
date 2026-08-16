"""Stable command shim for the repository-owned M7 conformance tooling."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    """Run the non-deployed local conformance module with this exact interpreter."""
    root = Path(__file__).resolve().parents[4]
    result = subprocess.run(
        [sys.executable, "-m", "tools.local_conformance", *sys.argv[1:]],
        cwd=root,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
