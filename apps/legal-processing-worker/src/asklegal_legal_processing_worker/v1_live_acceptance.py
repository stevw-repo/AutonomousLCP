# ruff: noqa: D107, EM101, PLR0913, PLR0917, TC002, TRY301
"""Compose both family-owned Legal acceptance components from retained inputs."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Protocol

from asklegal_contracts import parse_json_bytes
from asklegal_contracts.json_types import JsonValue
from asklegal_evidence_vault import ExactObjectReference

from .v1_acceptance import AcceptanceLegalError
from .v1_cases_acceptance import CasesAcceptanceError
from .v1_cases_live import (
    CaseTokenCounter,
    ExactJsonSemanticRunner,
    SemanticProfiles,
    prepare_hk_v1_cases_acceptance_component,
)
from .v1_legislation_acceptance import (
    LegislationAcceptanceError,
    prepare_hk_v1_legislation_acceptance_component,
)
from .v1_package_facts import prepare_hk_v1_package_fact_components


class _PrimaryVault(Protocol):
    def resolve_current(self, logical_key: str) -> ExactObjectReference | None: ...

    def read_exact(self, reference: ExactObjectReference) -> bytes: ...


class LiveAcceptanceComponentPreparer:
    """Run/replay Case semantics and deterministic Legislation mapping in one activity."""

    def __init__(
        self,
        primary_vault: _PrimaryVault,
        profiles: SemanticProfiles,
        counter: CaseTokenCounter,
        runner: ExactJsonSemanticRunner,
        case_policy_path: Path,
        state_root: Path,
        output_root: Path,
        package_facts_root: Path,
    ) -> None:
        self._vault = primary_vault
        self._profiles = profiles
        self._counter = counter
        self._runner = runner
        self._case_policy_path = case_policy_path
        self._state_root = state_root
        self._output_root = output_root
        self._package_facts_root = package_facts_root

    def prepare_exact(self, payload: Mapping[str, JsonValue], operation_root: Path) -> None:
        """Create-or-match Cases then Legislation components from one checkpoint."""
        try:
            request = payload.get("request")
            if type(request) is not dict:
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PAYLOAD_INVALID")
            operation_value = request.get("operation_id")
            if type(operation_value) is not str:
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACCEPTANCE_PAYLOAD_INVALID")
            operation_id = operation_value
            verified = parse_json_bytes(
                (operation_root / "verified-acquisition-inputs.json").read_bytes(),
                max_bytes=16_777_216,
            )
            if type(verified) is not dict:
                raise AcceptanceLegalError("LEGAL_PROCESSING_ACQUISITION_EVIDENCE_INVALID")
            cases_manifest = (operation_root / "manifests" / "cases.json").read_bytes()
            legislation_manifest = (operation_root / "manifests" / "legislation.json").read_bytes()
            prepare_hk_v1_cases_acceptance_component(
                operation_id,
                cases_manifest,
                verified,
                self._vault,
                self._profiles,
                self._counter,
                self._runner,
                self._case_policy_path,
                state_root=self._state_root,
                output_root=self._output_root,
            )
            prepare_hk_v1_legislation_acceptance_component(
                operation_id,
                legislation_manifest,
                verified,
                self._vault,
                state_root=self._state_root,
                output_root=self._output_root,
            )
            prepare_hk_v1_package_fact_components(
                operation_id,
                request,
                operation_root,
                self._package_facts_root,
                self._state_root,
            )
        except AcceptanceLegalError:
            raise
        except (CasesAcceptanceError, LegislationAcceptanceError) as error:
            raise AcceptanceLegalError(str(error)) from error
        except (OSError, TypeError, ValueError) as error:
            raise AcceptanceLegalError(
                "LEGAL_PROCESSING_ACCEPTANCE_COMPONENT_INPUT_NOT_READY"
            ) from error
