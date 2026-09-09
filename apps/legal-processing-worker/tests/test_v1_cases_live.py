# ruff: noqa: EM101, TRY003
"""Focused fail-before-call tests for live Case acceptance composition."""

from pathlib import Path

import pytest
from asklegal_evidence_vault import ExactObjectReference
from asklegal_legal_processing_worker.v1_cases_acceptance import CasesAcceptanceError
from asklegal_legal_processing_worker.v1_cases_live import (
    prepare_hk_v1_cases_acceptance_component,
)
from asklegal_processing import ExactTokenCounter, SemanticProfileSet


class _NoCallRunner:
    calls = 0

    def invoke_exact_json(self, *args: object, **kwargs: object) -> bytes:
        del args, kwargs
        self.calls += 1
        raise AssertionError("provider call was not expected")


class _UnusedVault:
    """Structurally valid vault double whose methods must remain unreachable."""

    def resolve_current(self, logical_key: str) -> ExactObjectReference | None:
        del logical_key
        raise AssertionError("vault lookup was not expected")

    def read_exact(self, reference: ExactObjectReference) -> bytes:
        del reference
        raise AssertionError("vault read was not expected")


def test_missing_case_policy_is_not_ready_before_provider_call(tmp_path: Path) -> None:
    """The wrapper never fabricates workflow/profile/serving authority."""
    runner = _NoCallRunner()
    vault = _UnusedVault()
    profiles = object.__new__(SemanticProfileSet)
    counter = object.__new__(ExactTokenCounter)

    with pytest.raises(CasesAcceptanceError, match="CASES_PROCESSING_POLICY_NOT_READY"):
        prepare_hk_v1_cases_acceptance_component(
            "op_case",
            b"{}",
            {},
            vault,
            profiles,
            counter,
            runner,
            (tmp_path / "missing-policy.json").resolve(),
            state_root=(tmp_path / "state").resolve(),
            output_root=(tmp_path / "outputs").resolve(),
        )

    assert runner.calls == 0
