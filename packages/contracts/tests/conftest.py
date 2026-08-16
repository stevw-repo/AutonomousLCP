"""Shared paths and fixtures for the local contract proof."""

from pathlib import Path

import pytest
from asklegal_contracts import SchemaRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_ROOT = REPOSITORY_ROOT / "contracts"


@pytest.fixture(scope="session")
def schema_registry() -> SchemaRegistry:
    """Build the complete closed schema registry once per test process."""
    return SchemaRegistry.from_contracts_root(CONTRACTS_ROOT)
