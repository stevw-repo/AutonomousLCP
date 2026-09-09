"""Repository wrapper for the installed GLD operator entrypoint."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from asklegal_acquisition_worker.gld_operator import main as _operator_main


def main(arguments: Sequence[str] | None = None) -> int:
    """Delegate without duplicating authority or execution logic."""
    return _operator_main(arguments)


if __name__ == "__main__":
    sys.exit(main())
