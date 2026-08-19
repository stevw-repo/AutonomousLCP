"""Keep the documented system-Python entrypoints parseable by the host interpreter.

The repository pins Python 3.14.7 for its applications, but `tools/dev_test.py`
and every `tools/v1_poc_*.py` static gate are documented as runnable with the
Ubuntu host's own `python3`, which is 3.12. `ruff format` canonicalises to the
declared `target-version = "py314"`, so a construct such as PEP 758's
unparenthesised `except A, B:` is written into the tree automatically and only
fails when the older interpreter tries to import it. Commit b38c184 shipped
exactly that and broke every static gate. This guard fails at test time instead.
"""

import ast
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SYSTEM_PYTHON_FEATURE_VERSION = (3, 12)
_ENTRYPOINTS = sorted(
    [
        *(REPOSITORY_ROOT / "tools").glob("v1_poc_*.py"),
        REPOSITORY_ROOT / "tools/dev_test.py",
        REPOSITORY_ROOT / "tools/python_boundary_check.py",
    ]
)


def test_the_entrypoint_inventory_is_not_silently_empty() -> None:
    """A glob that stops matching would turn this guard into a no-op."""
    assert len(_ENTRYPOINTS) >= 10


@pytest.mark.parametrize("path", _ENTRYPOINTS, ids=lambda path: path.name)
def test_entrypoint_parses_under_the_host_interpreter(path: Path) -> None:
    """Reject syntax newer than the Ubuntu host's own python3 can import."""
    ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
        feature_version=SYSTEM_PYTHON_FEATURE_VERSION,
    )
