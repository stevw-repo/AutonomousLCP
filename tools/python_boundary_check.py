"""Fail-closed static policy for Python type and import boundaries."""

import ast
import re
import tokenize
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class BoundaryCode(StrEnum):
    """Stable finding codes emitted by the boundary checker."""

    ANY = "PYBOUND001"
    UNPARAMETERIZED_COLLECTION = "PYBOUND002"
    CAST = "PYBOUND003"
    IGNORED_ERROR = "PYBOUND004"
    INFRASTRUCTURE_IMPORT = "PYBOUND005"
    FRAMEWORK_IMPORT = "PYBOUND006"
    INVALID_POLICY = "PYBOUND007"
    INVALID_PYTHON = "PYBOUND008"


@dataclass(frozen=True, order=True)
class ExceptionKey:
    """Exact source position and finding kind for one reviewed exception."""

    path: str
    line: int
    code: BoundaryCode


@dataclass(frozen=True)
class ApprovedException:
    """A narrow reviewed exception with a durable explanation."""

    key: ExceptionKey
    reason: str


@dataclass(frozen=True, order=True)
class Finding:
    """One deterministic boundary-policy failure."""

    path: str
    line: int
    code: BoundaryCode
    detail: str


_SCHEMA_PATH = "packages/contracts/src/asklegal_contracts/schemas.py"
_JSON_TYPES_PATH = "packages/contracts/src/asklegal_contracts/json_types.py"
_STRICT_JSON_PATH = "packages/contracts/src/asklegal_contracts/strict_json.py"
_MSSQL_DRIVER_PATH = (
    "packages/management-register-adapter/src/asklegal_management_register/driver.py"
)
_CONTROL_SERVICE_PATH = "apps/control-plane/src/asklegal_control_plane/v1_service.py"
_CONTROL_MAIN_PATH = "apps/control-plane/src/asklegal_control_plane/main.py"
_CONTROL_SCHEDULE_PATH = "apps/control-plane/src/asklegal_control_plane/v1_schedule.py"
_CONTROL_DUE_SERVICE_TEST_PATH = "apps/control-plane/tests/test_v1_due_cycle_service.py"
_CONTROL_ACCEPTANCE_TEST_PATH = "apps/control-plane/tests/test_v1_acceptance_cycle.py"
_CONTROL_SCHEDULE_TEST_PATH = "apps/control-plane/tests/test_v1_schedules.py"
_REVIEW_SERVICE_PATH = "apps/review-api/src/asklegal_review_api/v1_service.py"
_PROBES_PATH = "packages/application-runtime/src/asklegal_application_runtime/probes.py"
_SERVICE_HOST_PATH = "packages/application-runtime/src/asklegal_application_runtime/service.py"
_HK_JUDICIARY_AUTHENTIC_PATH = (
    "packages/source-connectors/src/asklegal_source_connectors/hk_judiciary_authentic.py"
)
_HK_LEGISLATION_RETAINED_PATH = (
    "packages/legal-desks/src/asklegal_legal_desks/hk_legislation_retained.py"
)
_HK_LEGISLATION_RETAINED_STRUCTURE_PATH = (
    "packages/legal-desks/src/asklegal_legal_desks/hk_legislation_retained_structure.py"
)
_ACQUISITION_JOURNAL_PATH = (
    "apps/acquisition-worker/src/asklegal_acquisition_worker/acquisition_journal.py"
)
_RESUMABLE_ACQUISITION_PATH = (
    "apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py"
)
_RETAINED_EVIDENCE_IMPORT_PATH = (
    "apps/acquisition-worker/src/asklegal_acquisition_worker/retained_evidence_import.py"
)
_HK_LEGISLATION_ACQUISITION_PATH = (
    "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_legislation_acquisition.py"
)
_HK_LEGISLATION_ACQUISITION_TEST_PATH = (
    "apps/acquisition-worker/tests/test_hk_legislation_acquisition.py"
)
_ACQUISITION_PIPELINE_PATH = (
    "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py"
)
_ACQUISITION_PROGRESS_PATH = (
    "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_progress.py"
)
_RETAINED_EVIDENCE_IMPORT_TEST_PATH = (
    "apps/acquisition-worker/tests/test_retained_evidence_import.py"
)
_ACQUISITION_SERVICE_PATH = "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_service.py"
_ACQUISITION_JOURNAL_TEST_PATH = "apps/acquisition-worker/tests/test_acquisition_journal.py"
_RESUMABLE_ACQUISITION_TEST_PATH = "apps/acquisition-worker/tests/test_resumable_acquisition.py"
_ACQUISITION_DUE_SERVICE_TEST_PATH = (
    "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py"
)
_DUE_CYCLE_ORCHESTRATOR_TEST_PATH = (
    "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py"
)
_SCHEDULED_FAMILY_COMPOSITION_TEST_PATH = (
    "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py"
)
_CONTROL_MAINTENANCE_PATH = "apps/control-plane/src/asklegal_control_plane/v1_maintenance.py"
_CONTROL_LOCAL_MAINTENANCE_TEST_PATH = "apps/control-plane/tests/test_v1_local_maintenance.py"
_HKEL_ARCHIVE_ADMISSION_PATH = (
    "packages/source-connectors/src/asklegal_source_connectors/hkel_archive_admission.py"
)

APPROVED_EXCEPTIONS: tuple[ApprovedException, ...] = (
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/acquisition_journal.py",
            230,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the canonical work-item ID must bind all ten settled request facts in one explicit "
            "keyword-only public constructor"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/acquisition_journal.py",
            940,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "one closed decoder branch per journal transition keeps unknown payload shapes "
            "fail-closed and directly reviewable"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/acquisition_journal.py",
            1820,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the single journal lifecycle owner keeps sequence, attempt, retry, and terminal "
            "transition invariants together for direct review"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/acquisition_journal.py",
            2238,
            BoundaryCode.IGNORED_ERROR,
        ),
        "fd-relative entry enumeration is required so replay never follows replaceable path text",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/acquisition_journal.py",
            2337,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the retained-journal reader enumerates entries through its pinned directory "
            "descriptor so replaced path text cannot redirect verification"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            184,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the discover closed owner boundary keeps this exact reviewed suppression local "
            "(noqa: PLR0913)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            221,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the discover closed owner boundary keeps this exact reviewed suppression local "
            "(noqa: C901, PLR0913)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            264,
            BoundaryCode.CAST,
        ),
        (
            "the discover closed runtime-validation boundary narrows 'tuple[object, ...]' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            289,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _run_discovery_child closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: PLR0913, PLR0917)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            319,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _run_discovery_child hostile adapter boundary intentionally normalizes every "
            "external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            350,
            BoundaryCode.CAST,
        ),
        (
            "the _bounded_cdp_stream closed runtime-validation boundary narrows 'dict[str, "
            "object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            370,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _capture_paused_navigation closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: C901)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            381,
            BoundaryCode.CAST,
        ),
        (
            "the _capture_paused_navigation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            392,
            BoundaryCode.CAST,
        ),
        (
            "the _capture_paused_navigation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            403,
            BoundaryCode.CAST,
        ),
        (
            "the _capture_paused_navigation closed runtime-validation boundary narrows "
            "'list[object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            406,
            BoundaryCode.CAST,
        ),
        (
            "the _capture_paused_navigation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            430,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _discover_direct closed owner boundary keeps this exact reviewed suppression "
            "local (noqa: C901, PLR0913, PLR0915)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            489,
            BoundaryCode.CAST,
        ),
        (
            "the _discover_direct closed runtime-validation boundary narrows '_CdpSession' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            724,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _challenge_contract closed owner boundary keeps this exact reviewed "
            "suppression local (type: ignore[arg-type])"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            731,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _preflight closed owner boundary keeps this exact reviewed suppression local "
            "(noqa: PLR0913)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            753,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the preflight_gld_operator closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: C901, PLR0911, PLR0912)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            945,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the preflight_gld_operator composition boundary accesses one repository-owned "
            "private seam at this exact reviewed integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            947,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the preflight_gld_operator closed owner boundary keeps this exact reviewed "
            "suppression local (pyright: ignore[reportPrivateUsage])"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            976,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _verify_primary_object hostile adapter boundary intentionally normalizes every "
            "external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            989,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the __init__ closed owner boundary keeps this exact reviewed suppression local "
            "(noqa: PLR0913)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            1018,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the capture_observation closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: C901, PLR0912, PLR0915)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            1208,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _verify_discovery_basis hostile adapter boundary intentionally normalizes "
            "every external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            1345,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _retain_discovery closed owner boundary keeps this exact reviewed suppression "
            "local (noqa: PLR0913, PLR0917)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            1422,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _load_retained_discovery hostile adapter boundary intentionally normalizes "
            "every external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            1477,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _retain_observation closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: PLR0913, PLR0917)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            1546,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _load_retained_observation hostile adapter boundary intentionally normalizes "
            "every external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/gld_operator.py",
            1662,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the main hostile adapter boundary intentionally normalizes every external failure "
            "to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_cases_acquisition.py",
            450,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the frozen acquisition-manifest projection deliberately names each independent "
            "evidence boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_cases_acquisition.py",
            682,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the immutable Case bundle gate keeps capture, occurrence, relationship, canonical "
            "fingerprint, conditional-create, and exact read-back checks together"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_cases_acquisition.py",
            1345,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _listing_node closed owner boundary keeps this exact reviewed suppression "
            "local (noqa: PLR0913 - exact work identity components are independently bound.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_cases_acquisition.py",
            1389,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the provisional listing helper keeps every exact occurrence and relationship "
            "identity input visible at its deterministic graph-expansion boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_cases_acquisition.py",
            1506,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the exact verified-listing expansion retains source parser, successor, physical "
            "capture deduplication, and relationship graph branches together"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_cases_acquisition.py",
            1584,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the expand_cases_graph_from_verified_listings closed owner boundary keeps this "
            "exact reviewed suppression local (noqa: C901, PLR0912, PLR0915 - closed partition "
            "expansion.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_cases_acquisition.py",
            1733,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the expand_cases_graph_from_verified_observations closed owner boundary keeps this "
            "exact reviewed suppression local (noqa: C901, PLR0912, PLR0915 - closed "
            "expansion.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_cases_acquisition.py",
            1914,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _artifact_node closed owner boundary keeps this exact reviewed suppression "
            "local (noqa: PLR0913 - each immutable work identity fact is independently bound.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_legislation_acquisition.py",
            985,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the durable baseline parser keeps closed JSON shape, authentic Task 4 anchoring, "
            "current-capture provenance, and resealed-substitution rejection together"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_legislation_acquisition.py",
            1166,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the registered seed issuer binds the complete source, endpoint, register, cutoff, "
            "and input provenance tuple at its sole private factory boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_legislation_acquisition.py",
            1211,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "one closed projection maps every required legislation role and GLD artifact from "
            "the exact source register into the deterministic family work graph"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_legislation_acquisition.py",
            1585,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "one graph revalidation pass binds every nested identity, source, endpoint, scope, "
            "dependency, priority, cycle, and canonical fingerprint fact"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_legislation_acquisition.py",
            1881,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the legislation adapter explicitly composes each independent shared-runner port so "
            "the registered activity has no second scheduling path"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_legislation_acquisition.py",
            2115,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the production Legislation cycle composes the runner, retained verifier, archive "
            "admission, authentic baseline, predecessor, and manifest without implicit ports"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_legislation_acquisition.py",
            2510,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the complete manifest factory consumes graph, report, verified evidence, reviews, "
            "authentic baseline, and predecessor as independently validated facts"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            66,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the one acquisition-owned registrar call is deliberately module-private; the "
            "reporting contract and repository-wide AST test enforce it as the sole issuer"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            546,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the predecessor store is an untrusted local application port, so every ordinary "
            "implementation exception must become one closed due-cycle state failure"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1089,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the shared retained-source reconstruction carries the six exact manifest bindings "
            "that cannot be collapsed without weakening replay verification"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1131,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _binding_from_retained_source_payload closed owner boundary keeps this exact "
            "reviewed suppression local (noqa: PLR0913, PLR0917)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1298,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _replay_terminal_artifact closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: C901)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1539,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the family-evidence activity treats its serialized payload as hostile input and "
            "converts every decoder failure to one closed result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1585,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the source activity keeps adapter dispatch, immutable evidence write-readback, "
            "admission downgrade, restart, and terminal issuance in one auditable boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1598,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the public constructor checks a deliberately object-typed local port at runtime so "
            "unusable stores cannot reach a due-cycle activity"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1604,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _verify_family_journal closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: C901, PLR0912, PLR0915)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1623,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _verify_family_journal hostile adapter boundary intentionally normalizes every "
            "external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1699,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _verify_family_journal hostile adapter boundary intentionally normalizes every "
            "external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1718,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _current_family_capture closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: C901, PLR0912, PLR0913, PLR0917)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1976,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the orchestrator treats each Durable activity result as hostile input before "
            "accepting its retained evidence identity"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1998,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the __init__ adapter performs one closed-name dynamic protocol lookup at this "
            "exact reviewed compatibility boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            1999,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the __init__ adapter performs one closed-name dynamic protocol lookup at this "
            "exact reviewed compatibility boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            2017,
            BoundaryCode.CAST,
        ),
        (
            "the exact runtime list check is narrowed to object leaves before every "
            "scheduler-history text value is rebuilt"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            2046,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _capture_hk_v1_due_source closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: C901, PLR0915)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            2384,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _assemble_hk_v1_due_cycle hostile adapter boundary intentionally normalizes "
            "every external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            2451,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the hostile Durable assembly acknowledgement parser normalizes every ordinary "
            "result error before any scheduler-safe outcome is returned"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            2488,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _orchestrator_family_evidence_result hostile adapter boundary intentionally "
            "normalizes every external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            2503,
            BoundaryCode.CAST,
        ),
        (
            "the _orchestrator_exact_object closed runtime-validation boundary narrows "
            "'dict[str, JsonValue]' at this exact reviewed site after the surrounding shape "
            "checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            2515,
            BoundaryCode.CAST,
        ),
        (
            "the _orchestrator_exact_text_list closed runtime-validation boundary narrows "
            "'list[object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            2695,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _orchestrator_plan hostile adapter boundary intentionally normalizes every "
            "external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            2763,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _orchestrator_capture_result hostile adapter boundary intentionally normalizes "
            "every external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            2772,
            BoundaryCode.CAST,
        ),
        (
            "the _orchestrator_source_ids closed runtime-validation boundary narrows "
            "'list[object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/hk_v1_due_cycle.py",
            2929,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _orchestrator_assembly_result hostile adapter boundary intentionally "
            "normalizes every external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py",
            423,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the shared runner exposes each independently injected concurrency, pacing, budget, "
            "retry, interruption, and clock control at one explicit composition boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py",
            511,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "one coordinator owns the closed queue, journal, retry, drain, and stop transition "
            "branches so transport workers cannot mutate durable state"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py",
            687,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "an unobserved worker-future fault remains an exact pre-transport interruption "
            "without inventing either a physical marker or a transport outcome"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py",
            738,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "a malformed completed transport result is contained before the coordinator "
            "interprets or journals any claimed outcome facts"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py",
            905,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "a hostile retained-object verifier must become an evidence-integrity stop rather "
            "than escape replay or expose adapter details"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py",
            1062,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "clock, sleeper, and host-gate faults are typed before transport so the coordinator "
            "can close admission without a false physical-start marker"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py",
            1066,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the worker returns an untyped transport exception with its actual physical-start "
            "fact so the sole coordinator can classify and journal both truthfully"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py",
            1070,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the outcome interpreter keeps every exact journal fact and stop branch together "
            "for direct review before the coordinator appends a terminal transition"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py",
            1117,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "a hostile current-capture verifier must become an evidence-integrity stop rather "
            "than allow unverified retention or expose adapter details"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/resumable_acquisition.py",
            1383,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the shared runner validates exact dependency membership, uniqueness, self-edges, "
            "dangling edges, and cycles in one closed prerequisite-map pass"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/retained_evidence_import.py",
            744,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the offline importer validates two closed historical report envelopes without "
            "weakening either source-specific shape"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/retained_evidence_import.py",
            845,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the physical-ledger verifier keeps structural, object, ordering, and final-URL "
            "checks in one fail-closed pass"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/retained_evidence_import.py",
            1152,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the HKeL retained verifier derives archive membership and bilingual closure in one "
            "bounded ZIP graph pass"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/retained_evidence_import.py",
            1265,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the Judiciary retained verifier walks the exact pinned predecessor chain and "
            "physical provenance before import"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/retained_evidence_import.py",
            1495,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "one closed offline import transaction validates the selected report, every object, "
            "every projection, and the exact journal prefix before publishing any transition"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/source_admission_adapter.py",
            258,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the capture closed owner boundary keeps this exact reviewed suppression local "
            "(noqa: C901, PLR0912, PLR0915 - closed verification is linear.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/source_admission_adapter.py",
            271,
            BoundaryCode.CAST,
        ),
        "the exact runtime mapping check precedes each captured-endpoint terminal check",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/source_admission_adapter.py",
            303,
            BoundaryCode.CAST,
        ),
        "the exact runtime string check precedes fingerprint grammar validation",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/source_admission_adapter.py",
            305,
            BoundaryCode.CAST,
        ),
        "the exact runtime string check precedes membership fingerprint validation",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/source_admission_adapter.py",
            329,
            BoundaryCode.CAST,
        ),
        "the exact runtime endpoint list check precedes immutable object graph verification",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/source_admission_adapter.py",
            332,
            BoundaryCode.CAST,
        ),
        "the exact runtime endpoint mapping check precedes object-key and digest verification",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/source_admission_adapter.py",
            406,
            BoundaryCode.CAST,
        ),
        (
            "the _verify_current_hkex_shape closed runtime-validation boundary narrows 'str' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/source_admission_adapter.py",
            409,
            BoundaryCode.CAST,
        ),
        (
            "the _verify_current_hkex_shape closed runtime-validation boundary narrows 'str' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/source_admission_adapter.py",
            421,
            BoundaryCode.CAST,
        ),
        (
            "the _verify_objects closed runtime-validation boundary narrows 'list[object]' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/source_admission_adapter.py",
            424,
            BoundaryCode.CAST,
        ),
        (
            "the _verify_objects closed runtime-validation boundary narrows 'dict[str, object]' "
            "at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_infrastructure.py",
            81,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the hostile non-secret state-root environment boundary normalizes every ordinary "
            "lookup or path parse failure to one safe not-ready configuration error"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py",
            1523,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the shared-runner vault verifier normalizes any hostile adapter read failure to a "
            "closed false result before an imported or captured object is trusted"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py",
            1670,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the exact retained-byte reader normalizes every hostile vault adapter failure "
            "before returning any purported evidence"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py",
            1702,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the retained capture adapter converts every vault read failure to an explicit "
            "closed read-back error"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py",
            1715,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the Task 9 capture boundary keeps its closed unchanged, changed, malformed, and "
            "vault-failure outcomes together for direct review"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py",
            1730,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "a malformed registered source graph is rejected at the capture boundary before any "
            "evidence or success claim is emitted"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py",
            1769,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "every vault failure during source capture becomes a terminal fail-visible outcome "
            "rather than an unverified success"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py",
            1800,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the capture hostile adapter boundary intentionally normalizes every external "
            "failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py",
            1992,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the changed-archive admission boundary closes every hostile retained-vault read "
            "failure before any archive member or XML body is trusted"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py",
            4259,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the production Cases activity owns one cycle-mode branch and the shared runner, "
            "expansion, verified bundle, and manifest projection sequence"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_pipeline.py",
            4634,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the build_activities closed owner boundary keeps this exact reviewed suppression "
            "local (noqa: PLR0913)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_progress.py",
            102,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the exact-file reader returns verified bytes before its shared descriptor cleanup "
            "block so all exits close the pinned handle"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_progress.py",
            207,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the local progress loader names the exact two-family retained inputs and lineage "
            "facts required for one fail-closed snapshot"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_service.py",
            66,
            BoundaryCode.IGNORED_ERROR,
        ),
        "a hostile critical logging adapter cannot replace a closed lifecycle result",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_service.py",
            74,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the service-owned pinned predecessor root must close on every lifecycle branch and "
            "maps ordinary local release failures to one safe failed service result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_service.py",
            82,
            BoundaryCode.IGNORED_ERROR,
        ),
        "a hostile lifecycle logging adapter cannot prevent the worker cleanup path",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_service.py",
            153,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "each configured worker-local family adapter is an independent startup authority "
            "whose ordinary construction failure must produce not-ready"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_service.py",
            168,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the injected local predecessor store is a hostile filesystem boundary, so startup "
            "normalizes every ordinary construction error to safe not-ready state"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_service.py",
            184,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the service-host call is a lifecycle boundary; an ordinary host failure must still "
            "release the pinned predecessor root and return the closed failed status"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/src/asklegal_acquisition_worker/v1_service.py",
            202,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _run hostile adapter boundary intentionally normalizes every external failure "
            "to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_acquisition_journal.py",
            101,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the journal profile test helper exposes each immutable safety fact so lifecycle "
            "cases can vary one exact bound control"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_gld_operator.py",
            53,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the discover closed test boundary keeps this exact reviewed suppression local "
            "(noqa: PLR0913)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_gld_operator.py",
            303,
            BoundaryCode.CAST,
        ),
        (
            "the __call__ fixture/replay boundary narrows 'LocalGldSessionTransport' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_gld_operator.py",
            482,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_discovery_reads_chromium_stream_only_to_exact_body_cap_plus_sentinel test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_gld_operator.py",
            677,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_observation_production_listing_transport_forbids_redirects test boundary "
            "accesses one repository-owned private seam at this exact reviewed integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_hk_legislation_acquisition.py",
            212,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the deterministic runner fixture exposes independent retry, content, and admitted "
            "source controls needed by the production-composition regression"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_hk_legislation_acquisition.py",
            1520,
            BoundaryCode.CAST,
        ),
        (
            "the registered-manifest test narrows its minimal effect-free acquisition "
            "infrastructure double only at the normal activity build boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_hk_legislation_acquisition.py",
            1571,
            BoundaryCode.CAST,
        ),
        (
            "the missing-configuration test narrows its minimal effect-free acquisition "
            "infrastructure double only at the normal activity build boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_hk_legislation_acquisition.py",
            1603,
            BoundaryCode.CAST,
        ),
        (
            "the configured-port test narrows its minimal effect-free acquisition "
            "infrastructure double only at the normal activity build boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_hk_legislation_acquisition.py",
            1644,
            BoundaryCode.CAST,
        ),
        (
            "the durable-input test narrows its minimal local infrastructure double at the "
            "normal production-input construction boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_hk_legislation_acquisition.py",
            1727,
            BoundaryCode.CAST,
        ),
        "the corrupt-state half reopens the same reviewed local infrastructure boundary",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_hk_legislation_acquisition.py",
            1732,
            BoundaryCode.CAST,
        ),
        (
            "the test_local_production_inputs_restore_advanced_baseline_and_predecessor "
            "fixture/replay boundary narrows 'V1AcquisitionInfrastructure' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_hk_legislation_acquisition.py",
            1749,
            BoundaryCode.CAST,
        ),
        (
            "the test_local_production_inputs_restore_advanced_baseline_and_predecessor "
            "fixture/replay boundary narrows 'V1AcquisitionInfrastructure' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_resumable_acquisition.py",
            178,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the immutable-profile test helper exposes each independently varied safety control "
            "so resume drift and budget cases remain explicit"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_resumable_acquisition.py",
            205,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test runner helper exposes every independently varied safety control so each "
            "concurrency, pacing, budget, resume, and stop regression remains explicit"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_retained_evidence_import.py",
            571,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the hostile replacement test deliberately exercises the private same-descriptor "
            "retained-object verifier that closes the import TOCTOU boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            200,
            BoundaryCode.CAST,
        ),
        (
            "one typed test-only infrastructure view crosses into the concrete service "
            "composition contract at the isolated monkeypatch boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            216,
            BoundaryCode.CAST,
        ),
        (
            "the state-store test double crosses into the concrete predecessor-store type only "
            "at the isolated service factory boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            429,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the pre-worker store regression reaches the private logger only to prove a hostile "
            "critical adapter cannot replace not-ready"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            439,
            BoundaryCode.CAST,
        ),
        (
            "the test_service_composes_retained_source_admission_before_worker_start "
            "fixture/replay boundary narrows 'MethodType' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            440,
            BoundaryCode.CAST,
        ),
        (
            "the test_service_composes_retained_source_admission_before_worker_start "
            "fixture/replay boundary narrows 'HongKongV1DueCycleActivities' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            441,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the pre-worker logger matrix invokes the private process coroutine to observe its "
            "exact closed not-ready result and store cleanup"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            461,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the cancellation regression observes the private process coroutine because the "
            "public synchronous wrapper cannot preserve an active task cancellation signal"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            500,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the boolean lifecycle expectation is test-only fixture data for the observable "
            "started/not-started ownership state and is not a public production parameter"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            510,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the host double deliberately normalizes every ordinary injected startup failure to "
            "the same closed failed outcome as the real shared service host"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            515,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "one parameterized lifecycle matrix intentionally holds every service failure point "
            "together so its exact state-release and worker-stop comparison stays readable"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            518,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_hostile_lifecycle_logger_cannot_replace_a_not_ready_result test boundary "
            "accesses one repository-owned private seam at this exact reviewed integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            549,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the observe_cancellation test boundary accesses one repository-owned private seam "
            "at this exact reviewed integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            559,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_service_preserves_cancellation_when_due_state_store_close_also_fails test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            576,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_service_lifecycle_failures_close_state_once_and_stop_only_started_workers "
            "closed test boundary keeps this exact reviewed suppression local (noqa: C901, "
            "PLR0913, PLR0917 - one explicit lifecycle matrix.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            581,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_service_lifecycle_failures_close_state_once_and_stop_only_started_workers "
            "test uses one literal boolean solely to express the exact lifecycle expectation "
            "under review"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            606,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the host hostile adapter boundary intentionally normalizes every external failure "
            "to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            781,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the post-start host double normalizes an arbitrary diagnostic projection fault to "
            "the shared closed failed service result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            828,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the logger regression invokes the private process coroutine to observe its closed "
            "success and exact cleanup result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            872,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the stop regression reaches the private logger solely to prove cancellation "
            "survives a hostile critical logging adapter"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            886,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the cancellation regression deliberately invokes the private serve builder to "
            "observe started-worker cancellation and stop ownership"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            921,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_post_start_lifecycle_logger_fault_does_not_block_worker_or_store_cleanup "
            "test boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            924,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_post_start_lifecycle_logger_fault_does_not_block_worker_or_store_cleanup "
            "test boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            952,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the cancel_started_serve test boundary accesses one repository-owned private seam "
            "at this exact reviewed integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            955,
            BoundaryCode.CAST,
        ),
        (
            "the cancel_started_serve fixture/replay boundary narrows "
            "'LocalDueCyclePredecessorStore' at this exact reviewed site after the surrounding "
            "shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_acquisition_due_cycle_service.py",
            969,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_serve_preserves_cancellation_when_started_worker_stop_fails test boundary "
            "accesses one repository-owned private seam at this exact reviewed integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_authentic_due_cycle_binding.py",
            107,
            BoundaryCode.CAST,
        ),
        (
            "the direct activity test narrows the documented serialized plan result only to "
            "build the next public activity request"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_authentic_due_cycle_binding.py",
            127,
            BoundaryCode.CAST,
        ),
        (
            "the direct activity test narrows the plan source identifier array solely to issue "
            "every public capture activity required for final assembly"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_authentic_due_cycle_binding.py",
            181,
            BoundaryCode.CAST,
        ),
        (
            "the failure-terminal test narrows the documented serialized plan result solely to "
            "issue the public capture activity"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_authentic_due_cycle_binding.py",
            331,
            BoundaryCode.CAST,
        ),
        "the schema-2 test constructs a deliberately empty exact attachment list",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_authentic_due_cycle_binding.py",
            332,
            BoundaryCode.CAST,
        ),
        "the schema-2 test constructs a deliberately empty exact association list",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_authentic_due_cycle_binding.py",
            333,
            BoundaryCode.CAST,
        ),
        "the schema-2 test constructs a deliberately empty exact attachment list",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_authentic_due_cycle_binding.py",
            393,
            BoundaryCode.CAST,
        ),
        "the generated procedure rows bind exact string source identifiers before adapter use",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_acquisition.py",
            2497,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the repository-wide gateway AST audit deliberately enumerates every forbidden "
            "lookup form in one test, exceeding the generic branch-complexity threshold"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_acquisition.py",
            2673,
            BoundaryCode.CAST,
        ),
        (
            "the hostile predecessor-store double deliberately returns malformed values through "
            "its typed port so the activity boundary must reject them at runtime"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_acquisition.py",
            2681,
            BoundaryCode.CAST,
        ),
        (
            "the hostile predecessor-store double deliberately returns malformed values through "
            "its typed port so the activity boundary must reject them at runtime"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            42,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the replay double must expose Durable Task's public input keyword exactly, "
            "including the deliberate built-in-name shadowing"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            50,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the replay double must expose Durable Task's sub-orchestrator input keyword "
            "exactly, including its deliberate built-in-name shadowing"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            161,
            BoundaryCode.CAST,
        ),
        (
            "one test-only adapter narrows the minimal recording replay driver to the SDK "
            "context solely at the orchestrator call boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            216,
            BoundaryCode.CAST,
        ),
        (
            "the two-family replay helper narrows its recording double to the SDK context only "
            "at the orchestrator call boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            221,
            BoundaryCode.CAST,
        ),
        (
            "the replay helper narrows a yielded Durable task only after the test double "
            "records its exact mapping shape"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            223,
            BoundaryCode.CAST,
        ),
        (
            "the replay helper crosses an object-typed payload into the recursive JSON checker "
            "before feeding it back to the generator"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            228,
            BoundaryCode.CAST,
        ),
        (
            "the replay helper narrows the recorded family payload at the exact synthetic "
            "activity-receipt construction boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            234,
            BoundaryCode.CAST,
        ),
        (
            "the normal replay completion value is narrowed only after StopIteration proves the "
            "generator returned its final mapping"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            240,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the replay proxy must forward any BaseException into generator.throw to preserve "
            "the exact Durable generator protocol under test"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            244,
            BoundaryCode.CAST,
        ),
        (
            "the exceptional replay completion value is narrowed only after StopIteration "
            "proves the generator returned its final mapping"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            397,
            BoundaryCode.CAST,
        ),
        (
            "the shared-cycle orchestration regression narrows the minimal recording replay "
            "driver to the SDK context solely at the orchestrator call boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            421,
            BoundaryCode.CAST,
        ),
        (
            "the Legislation branch regression narrows the same minimal recording replay driver "
            "to the SDK context solely at the orchestrator call boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_cycle_orchestrator.py",
            458,
            BoundaryCode.CAST,
        ),
        (
            "the mixed-family rejection regression narrows the same minimal recording replay "
            "driver solely to prove the fail-before-schedule boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_due_register_integration.py",
            120,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the V1 scope regression deliberately inspects the one private fixed-register "
            "composition boundary to prove that only the two admitted families are loaded"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            52,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the composition replay double mirrors Durable Task's exact sub-orchestrator input "
            "keyword for faithful child-history assertions"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            60,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the composition replay double mirrors Durable Task's exact activity input keyword "
            "for faithful scheduler-history assertions"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            233,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the retained-family regression calls the private result parser solely to obtain "
            "the exact admitted family result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            242,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the missing-family-port regression invokes the private process owner only to prove "
            "not-ready precedes worker creation"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            243,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _complete_journal test boundary accesses one repository-owned private seam at "
            "this exact reviewed integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            253,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _complete_journal test boundary accesses one repository-owned private seam at "
            "this exact reviewed integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            320,
            BoundaryCode.CAST,
        ),
        (
            "the _retain_complete_family_evidence fixture/replay boundary narrows 'dict[str, "
            "object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            351,
            BoundaryCode.CAST,
        ),
        (
            "the _retain_complete_family_evidence fixture/replay boundary narrows 'str' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            359,
            BoundaryCode.CAST,
        ),
        (
            "the _retain_complete_family_evidence fixture/replay boundary narrows 'str' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            367,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _retain_complete_family_evidence test boundary accesses one repository-owned "
            "private seam at this exact reviewed integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            394,
            BoundaryCode.CAST,
        ),
        (
            "the _complete_family_payload fixture/replay boundary narrows 'dict[str, object]' "
            "at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            403,
            BoundaryCode.CAST,
        ),
        (
            "the _complete_family_payload fixture/replay boundary narrows 'str' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            410,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _complete_family_payload test boundary accesses one repository-owned private "
            "seam at this exact reviewed integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            427,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the "
            "test_schedule_dispatches_both_real_family_boundaries_with_replay_stable_identities "
            "test boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            428,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the "
            "test_schedule_dispatches_both_real_family_boundaries_with_replay_stable_identities "
            "test boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            434,
            BoundaryCode.CAST,
        ),
        (
            "the drive fixture/replay boundary narrows 'OrchestrationContext' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            437,
            BoundaryCode.CAST,
        ),
        (
            "the drive fixture/replay boundary narrows 'dict[str, object]' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            442,
            BoundaryCode.CAST,
        ),
        (
            "the drive fixture/replay boundary narrows 'str' at this exact reviewed site after "
            "the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            444,
            BoundaryCode.CAST,
        ),
        (
            "the drive fixture/replay boundary narrows 'dict[str, object]' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            447,
            BoundaryCode.CAST,
        ),
        (
            "the drive fixture/replay boundary narrows 'str' at this exact reviewed site after "
            "the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            448,
            BoundaryCode.CAST,
        ),
        (
            "the drive fixture/replay boundary narrows 'str' at this exact reviewed site after "
            "the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            462,
            BoundaryCode.CAST,
        ),
        (
            "the "
            "test_schedule_dispatches_both_real_family_boundaries_with_replay_stable_identities "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            466,
            BoundaryCode.CAST,
        ),
        (
            "the "
            "test_schedule_dispatches_both_real_family_boundaries_with_replay_stable_identities "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            470,
            BoundaryCode.CAST,
        ),
        (
            "the "
            "test_schedule_dispatches_both_real_family_boundaries_with_replay_stable_identities "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            471,
            BoundaryCode.CAST,
        ),
        (
            "the "
            "test_schedule_dispatches_both_real_family_boundaries_with_replay_stable_identities "
            "fixture/replay boundary narrows 'list[object]' at this exact reviewed site after "
            "the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            472,
            BoundaryCode.CAST,
        ),
        (
            "the "
            "test_schedule_dispatches_both_real_family_boundaries_with_replay_stable_identities "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            474,
            BoundaryCode.CAST,
        ),
        (
            "the "
            "test_schedule_dispatches_both_real_family_boundaries_with_replay_stable_identities "
            "fixture/replay boundary narrows 'str' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            487,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_family_results_are_strictly_validated_and_retained_with_readback test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            493,
            BoundaryCode.CAST,
        ),
        (
            "the test_family_results_are_strictly_validated_and_retained_with_readback "
            "fixture/replay boundary narrows 'str' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            497,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_family_results_are_strictly_validated_and_retained_with_readback test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            505,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_family_results_are_strictly_validated_and_retained_with_readback test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            516,
            BoundaryCode.CAST,
        ),
        (
            "the test_family_results_are_strictly_validated_and_retained_with_readback "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            534,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_family_results_are_strictly_validated_and_retained_with_readback test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            539,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_family_results_are_strictly_validated_and_retained_with_readback test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            548,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_family_results_are_strictly_validated_and_retained_with_readback test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            633,
            BoundaryCode.CAST,
        ),
        (
            "the test_complete_family_manifest_with_journal_head_drift_is_rejected "
            "fixture/replay boundary narrows 'str' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            671,
            BoundaryCode.CAST,
        ),
        (
            "the test_complete_family_manifest_with_missing_terminal_object_is_rejected "
            "fixture/replay boundary narrows 'str' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            708,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_current_family_evidence_owns_all_roles_and_binds_every_scheduled_terminal "
            "test boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            722,
            BoundaryCode.CAST,
        ),
        (
            "the test_current_family_evidence_owns_all_roles_and_binds_every_scheduled_terminal "
            "fixture/replay boundary narrows 'list[str]' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            756,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_current_family_evidence_owns_all_roles_and_binds_every_scheduled_terminal "
            "test boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            840,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the "
            "test_second_cutoff_uses_its_own_family_manifests_without_frozen_report_fallback "
            "test boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/acquisition-worker/tests/test_v1_scheduled_family_composition.py",
            932,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_missing_cases_production_port_is_not_ready_before_worker_creation test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/main.py",
            54,
            BoundaryCode.CAST,
        ),
        (
            "the Durable Task SDK client satisfies the narrow scheduling protocol but exposes "
            "no nominal protocol declaration"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/main.py",
            111,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the schedule command process boundary converts every adapter failure to one safe "
            "fail-visible exit code"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_maintenance.py",
            350,
            BoundaryCode.CAST,
        ),
        (
            "the archive-maintenance result details are narrowed only after exact builtin "
            "mapping validation of the local task result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_maintenance.py",
            387,
            BoundaryCode.CAST,
        ),
        (
            "the maintenance request timestamp is narrowed after the closed request validator "
            "has proved the exact field is text"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_maintenance.py",
            459,
            BoundaryCode.CAST,
        ),
        (
            "the perform_hk_v1_telemetry_retention closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_maintenance.py",
            482,
            BoundaryCode.CAST,
        ),
        (
            "the perform_hk_v1_telemetry_retention closed runtime-validation boundary narrows "
            "'dict[str, JsonValue]' at this exact reviewed site after the surrounding shape "
            "checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_pipeline.py",
            288,
            BoundaryCode.IGNORED_ERROR,
        ),
        "exact copying precedes shared parsing and ordinary parser faults stay closed",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_pipeline.py",
            316,
            BoundaryCode.IGNORED_ERROR,
        ),
        "hostile instruction copying faults close before shared parser inspection",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_pipeline.py",
            325,
            BoundaryCode.CAST,
        ),
        "the exact runtime dict guard narrows only the detached six-field instruction boundary",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_pipeline.py",
            335,
            BoundaryCode.IGNORED_ERROR,
        ),
        "scheduler configuration access is an adapter boundary with a closed route error",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_pipeline.py",
            359,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _due_scheduler_route hostile adapter boundary intentionally normalizes every "
            "external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_pipeline.py",
            424,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the acquisition acknowledgement boundary normalizes every ordinary hostile result failure",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_pipeline.py",
            521,
            BoundaryCode.IGNORED_ERROR,
        ),
        "Matrix reconciliation must normalize ordinary corrupted-state failures to one safe result",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_pipeline.py",
            596,
            BoundaryCode.CAST,
        ),
        "the exact runtime list guard narrows only the recursive detached result copier",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_pipeline.py",
            604,
            BoundaryCode.CAST,
        ),
        "the exact runtime dict guard narrows only the recursive detached result copier",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_pipeline.py",
            877,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _due_orchestrator_result hostile adapter boundary intentionally normalizes "
            "every external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_schedule.py",
            245,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the narrow scheduler protocol must retain the external Durable Task client's exact "
            "input keyword"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_schedule.py",
            907,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the dispatch_schedule hostile adapter boundary intentionally normalizes every "
            "external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_schedule.py",
            1609,
            BoundaryCode.CAST,
        ),
        (
            "the _families closed runtime-validation boundary narrows 'list[object]' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_schedule.py",
            1612,
            BoundaryCode.CAST,
        ),
        (
            "the _families closed runtime-validation boundary narrows 'list[str]' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_schedule.py",
            1618,
            BoundaryCode.CAST,
        ),
        (
            "the _invocation_ids closed runtime-validation boundary narrows 'list[object]' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_service.py",
            55,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the container listener is scoped to the private Control network",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_service.py",
            143,
            BoundaryCode.IGNORED_ERROR,
        ),
        "a worker adapter stop fault is normalized only after all shutdown cleanup runs",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_service.py",
            162,
            BoundaryCode.IGNORED_ERROR,
        ),
        "a hostile lifecycle info logger cannot prevent service cleanup",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/src/asklegal_control_plane/v1_service.py",
            170,
            BoundaryCode.IGNORED_ERROR,
        ),
        "a hostile lifecycle critical logger cannot replace shutdown outcome",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            349,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the call_activity signature mirrors the pinned external SDK keyword exactly at "
            "this reviewed adapter boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            356,
            BoundaryCode.CAST,
        ),
        "the acquisition-drift test mutates exact JSON family rows after closed shape validation",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            362,
            BoundaryCode.CAST,
        ),
        (
            "the _object_list fixture/replay boundary narrows 'list[object]' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            417,
            BoundaryCode.CAST,
        ),
        (
            "the test_changed_cycle_requires_complete_four_scope_legal_result fixture/replay "
            "boundary narrows 'dict[str, JsonValue]' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            431,
            BoundaryCode.CAST,
        ),
        (
            "the test_manual_request_cannot_drop_or_drift_family_evidence fixture/replay "
            "boundary narrows 'dict[str, JsonValue]' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            434,
            BoundaryCode.CAST,
        ),
        (
            "the test_manual_request_cannot_drop_or_drift_family_evidence fixture/replay "
            "boundary narrows 'list[JsonValue]' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            435,
            BoundaryCode.CAST,
        ),
        (
            "the test_manual_request_cannot_drop_or_drift_family_evidence fixture/replay "
            "boundary narrows 'dict[str, JsonValue]' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            449,
            BoundaryCode.CAST,
        ),
        (
            "the test_complete_zero_record_scope_requires_explicit_justification_reference "
            "fixture/replay boundary narrows 'list[dict[str, JsonValue]]' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            476,
            BoundaryCode.CAST,
        ),
        (
            "the test_zero_record_references_follow_the_exact_family_contracts fixture/replay "
            "boundary narrows 'list[dict[str, JsonValue]]' at this exact reviewed site after "
            "the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            527,
            BoundaryCode.CAST,
        ),
        (
            "the test_manifest_fingerprint_or_incomplete_family_fails_before_legal_activity "
            "fixture/replay boundary narrows 'list[dict[str, JsonValue]]' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            815,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the schedule_new_orchestration signature mirrors the pinned external SDK keyword "
            "exactly at this reviewed adapter boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            826,
            BoundaryCode.CAST,
        ),
        (
            "the wait_for_orchestration_completion fixture/replay boundary narrows 'dict[str, "
            "JsonValue]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            827,
            BoundaryCode.CAST,
        ),
        (
            "the wait_for_orchestration_completion fixture/replay boundary narrows 'dict[str, "
            "object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            868,
            BoundaryCode.CAST,
        ),
        (
            "the test_ordinary_due_change_routes_exact_wrapper_and_preserves_legal_blocker "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            869,
            BoundaryCode.CAST,
        ),
        (
            "the test_ordinary_due_change_routes_exact_wrapper_and_preserves_legal_blocker "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            873,
            BoundaryCode.CAST,
        ),
        (
            "the test_ordinary_due_change_routes_exact_wrapper_and_preserves_legal_blocker "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            876,
            BoundaryCode.CAST,
        ),
        (
            "the test_ordinary_due_change_routes_exact_wrapper_and_preserves_legal_blocker "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            877,
            BoundaryCode.CAST,
        ),
        (
            "the test_ordinary_due_change_routes_exact_wrapper_and_preserves_legal_blocker "
            "fixture/replay boundary narrows 'list[object]' at this exact reviewed site after "
            "the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            879,
            BoundaryCode.CAST,
        ),
        (
            "the test_ordinary_due_change_routes_exact_wrapper_and_preserves_legal_blocker "
            "fixture/replay boundary narrows 'list[object]' at this exact reviewed site after "
            "the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            881,
            BoundaryCode.CAST,
        ),
        (
            "the test_ordinary_due_change_routes_exact_wrapper_and_preserves_legal_blocker "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            883,
            BoundaryCode.CAST,
        ),
        (
            "the test_ordinary_due_change_routes_exact_wrapper_and_preserves_legal_blocker "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            885,
            BoundaryCode.CAST,
        ),
        (
            "the test_ordinary_due_change_routes_exact_wrapper_and_preserves_legal_blocker "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            887,
            BoundaryCode.CAST,
        ),
        (
            "the test_ordinary_due_change_routes_exact_wrapper_and_preserves_legal_blocker "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_acceptance_cycle.py",
            891,
            BoundaryCode.CAST,
        ),
        (
            "the test_ordinary_due_change_routes_exact_wrapper_and_preserves_legal_blocker "
            "fixture/replay boundary narrows 'str' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            79,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the Durable Task SDK reserves input and the recording client mirrors it exactly",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            139,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the Durable Task SDK reserves the input keyword and the replay double mirrors it exactly",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            228,
            BoundaryCode.CAST,
        ),
        "the resealed-policy guard test supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            299,
            BoundaryCode.CAST,
        ),
        "the isolated activity test supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            337,
            BoundaryCode.CAST,
        ),
        "the wrong-route regression supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            366,
            BoundaryCode.CAST,
        ),
        "the wrong-route regression supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            386,
            BoundaryCode.CAST,
        ),
        "the instance-ack regression supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            406,
            BoundaryCode.CAST,
        ),
        "the hostile scheduler double is narrowed only at its isolated monkeypatch boundary",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            424,
            BoundaryCode.CAST,
        ),
        "the route exception regression supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            443,
            BoundaryCode.CAST,
        ),
        "the detachment regression supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            447,
            BoundaryCode.CAST,
        ),
        "the deterministic test narrows its recording context to the SDK protocol",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            458,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the hostile-reference regression invokes the private result reconstruction boundary",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            459,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the hostile-reference regression deliberately invokes the private Matrix snapshot helper",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            462,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the hostile-reference regression invokes the private detached instruction parser",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            469,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the hostile-result regression invokes the private result reconstruction boundary",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            470,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_due_control_normalizes_hostile_nested_mapping_before_traversal test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            473,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_due_control_normalizes_hostile_nested_mapping_before_traversal test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            485,
            BoundaryCode.CAST,
        ),
        "the generator completion is narrowed after the test observes its exact dict shape",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            507,
            BoundaryCode.CAST,
        ),
        "the parameterized hostile input is narrowed only to construct its exact malformed fixture",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            513,
            BoundaryCode.CAST,
        ),
        "the parameterized hostile input is narrowed only to construct its exact malformed fixture",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            537,
            BoundaryCode.CAST,
        ),
        "the hostile result is narrowed only to construct its exact malformed fixture",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            549,
            BoundaryCode.CAST,
        ),
        "the hostile result is narrowed only to construct its exact malformed fixture",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            552,
            BoundaryCode.CAST,
        ),
        "the hostile result is narrowed only to construct its exact malformed fixture",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            564,
            BoundaryCode.CAST,
        ),
        "the installed SDK private dispatcher is narrowed to the compact dispatch proof protocols",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            566,
            BoundaryCode.CAST,
        ),
        "the installed SDK private dispatcher is narrowed to the compact dispatch proof protocols",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            568,
            BoundaryCode.CAST,
        ),
        "the SDK dispatch test supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            570,
            BoundaryCode.CAST,
        ),
        "the hostile result is narrowed only to construct its exact malformed fixture",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            572,
            BoundaryCode.CAST,
        ),
        "the false-complete regression supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            579,
            BoundaryCode.CAST,
        ),
        "the Matrix mutation regression supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            590,
            BoundaryCode.CAST,
        ),
        (
            "the test_due_control_orchestrator_strictly_rebuilds_all_returned_shapes "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            592,
            BoundaryCode.CAST,
        ),
        (
            "the test_due_control_orchestrator_strictly_rebuilds_all_returned_shapes "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            594,
            BoundaryCode.CAST,
        ),
        (
            "the test_due_control_orchestrator_strictly_rebuilds_all_returned_shapes "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            596,
            BoundaryCode.CAST,
        ),
        (
            "the test_due_control_orchestrator_strictly_rebuilds_all_returned_shapes "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            599,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_due_control_orchestrator_strictly_rebuilds_all_returned_shapes test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            601,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_due_control_orchestrator_strictly_rebuilds_all_returned_shapes test "
            "boundary accesses one repository-owned private seam at this exact reviewed "
            "integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            629,
            BoundaryCode.CAST,
        ),
        "the duplicate-key regression supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            630,
            BoundaryCode.CAST,
        ),
        "the accounting regression supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            633,
            BoundaryCode.CAST,
        ),
        (
            "the test_installed_durable_activity_executor_reaches_the_closed_due_parser "
            "fixture/replay boundary narrows 'V1ControlInfrastructure' at this exact reviewed "
            "site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            657,
            BoundaryCode.CAST,
        ),
        "the reference regression supplies an infrastructure-free control composition double",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            670,
            BoundaryCode.CAST,
        ),
        (
            "the test_due_control_revalidates_an_issued_matrix_before_dispatch fixture/replay "
            "boundary narrows 'V1ControlInfrastructure' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            693,
            BoundaryCode.CAST,
        ),
        (
            "the family-acquisition evidence-reference regression supplies an "
            "infrastructure-free control composition double"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            721,
            BoundaryCode.CAST,
        ),
        (
            "the test_due_control_rejects_hostile_category_or_derived_result_field "
            "fixture/replay boundary narrows 'V1ControlInfrastructure' at this exact reviewed "
            "site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            742,
            BoundaryCode.CAST,
        ),
        (
            "the test_due_control_rejects_wrong_manifest_reference fixture/replay boundary "
            "narrows 'V1ControlInfrastructure' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_control.py",
            767,
            BoundaryCode.CAST,
        ),
        (
            "the test_due_control_rejects_wrong_family_acquisition_evidence_reference "
            "fixture/replay boundary narrows 'V1ControlInfrastructure' at this exact reviewed "
            "site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_service.py",
            120,
            BoundaryCode.CAST,
        ),
        "service composition test has no infrastructure use",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_service.py",
            158,
            BoundaryCode.IGNORED_ERROR,
        ),
        "service lifecycle test intentionally invokes its private async owner",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_service.py",
            197,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the missing-cutoff-root test intentionally invokes the private async service owner",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_service.py",
            229,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the pre-readiness configuration test invokes the private process coroutine directly",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_service.py",
            262,
            BoundaryCode.IGNORED_ERROR,
        ),
        "revision-guard test intentionally invokes the private async owner",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_service.py",
            287,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the resealed-policy guard test intentionally invokes the private async owner",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_service.py",
            304,
            BoundaryCode.IGNORED_ERROR,
        ),
        "start-failure test intentionally invokes its private async owner",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_service.py",
            325,
            BoundaryCode.IGNORED_ERROR,
        ),
        "task-creation failure test intentionally invokes its private async owner",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_service.py",
            342,
            BoundaryCode.IGNORED_ERROR,
        ),
        "stop failure test intentionally invokes its private async owner",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_due_cycle_service.py",
            356,
            BoundaryCode.IGNORED_ERROR,
        ),
        "cancellation test intentionally invokes the private async lifecycle owner",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_local_maintenance.py",
            139,
            BoundaryCode.CAST,
        ),
        (
            "the retained result reference is narrowed solely to load the exact object emitted "
            "by the maintenance boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_local_maintenance.py",
            141,
            BoundaryCode.CAST,
        ),
        (
            "the test_audit_archive_is_exact_read_back_verified_and_restart_safe fixture/replay "
            "boundary narrows 'str' at this exact reviewed site after the surrounding shape "
            "checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_local_maintenance.py",
            264,
            BoundaryCode.CAST,
        ),
        (
            "the test_retained_result_binds_request_and_current_matrix_lineage fixture/replay "
            "boundary narrows 'str' at this exact reviewed site after the surrounding shape "
            "checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_local_maintenance.py",
            269,
            BoundaryCode.CAST,
        ),
        (
            "the test_retained_result_binds_request_and_current_matrix_lineage fixture/replay "
            "boundary narrows 'dict[str, object]' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_schedules.py",
            43,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the deterministic scheduler double preserves the external client's exact input keyword",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_schedules.py",
            63,
            BoundaryCode.CAST,
        ),
        "the schedule test helper narrows a JSON object only after an exact builtin type assertion",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/control-plane/tests/test_v1_schedules.py",
            68,
            BoundaryCode.CAST,
        ),
        "the schedule test helper narrows a JSON array only after an exact builtin list assertion",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_legislation_acceptance.py",
            345,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _xml_root parser uses the bounded standard-library XML reader only after its "
            "explicit declaration, DTD, entity, and include guards"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_legislation_acceptance.py",
            346,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _xml_root parser uses the bounded standard-library XML reader only after its "
            "explicit declaration, DTD, entity, and include guards"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_legislation_acceptance.py",
            373,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _tree closed owner boundary keeps this exact reviewed suppression local (noqa: "
            "PLR0913, PLR0917)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_legislation_acceptance.py",
            490,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _unit closed owner boundary keeps this exact reviewed suppression local (noqa: "
            "PLR0913, PLR0917)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_legislation_acceptance.py",
            504,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _node closed owner boundary keeps this exact reviewed suppression local (noqa: "
            "PLR0913, PLR0917)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/src/asklegal_legal_processing_worker/v1_legislation_acceptance.py",
            727,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the prepare_hk_v1_legislation_acceptance_component closed owner boundary keeps "
            "this exact reviewed suppression local (noqa: PLR0913, PLR0915)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/tests/test_live_semantic_evaluation.py",
            52,
            BoundaryCode.CAST,
        ),
        (
            "the _profiles fixture/replay boundary narrows 'dict[str, object]' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/tests/test_live_semantic_evaluation.py",
            53,
            BoundaryCode.CAST,
        ),
        (
            "the _profiles fixture/replay boundary narrows 'list[object]' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/tests/test_live_semantic_evaluation.py",
            55,
            BoundaryCode.CAST,
        ),
        (
            "the _profiles fixture/replay boundary narrows 'dict[str, object]' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/tests/test_live_semantic_evaluation.py",
            57,
            BoundaryCode.CAST,
        ),
        (
            "the _profiles fixture/replay boundary narrows 'dict[str, object]' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/tests/test_live_semantic_evaluation.py",
            90,
            BoundaryCode.CAST,
        ),
        (
            "the invoke fixture/replay boundary narrows 'object' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/tests/test_live_semantic_evaluation.py",
            90,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the invoke closed test boundary keeps this exact reviewed suppression local "
            "(pyright: ignore[reportArgumentType])"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/tests/test_live_semantic_evaluation.py",
            174,
            BoundaryCode.CAST,
        ),
        (
            "the test_semantic_receipt_cannot_turn_failed_decision_into_passed fixture/replay "
            "boundary narrows 'dict[str, object]' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/tests/test_live_semantic_evaluation.py",
            175,
            BoundaryCode.CAST,
        ),
        (
            "the test_semantic_receipt_cannot_turn_failed_decision_into_passed fixture/replay "
            "boundary narrows 'dict[str, object]' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/tests/test_live_semantic_evaluation.py",
            176,
            BoundaryCode.CAST,
        ),
        (
            "the test_semantic_receipt_cannot_turn_failed_decision_into_passed fixture/replay "
            "boundary narrows 'dict[str, object]' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/legal-processing-worker/tests/test_v1_model_profiles.py",
            149,
            BoundaryCode.CAST,
        ),
        (
            "the negative composition test deliberately supplies a duck counter to prove "
            "exact-type refusal"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/local_approval.py",
            147,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "one fail-closed local ledger reconstruction keeps all retained-state consistency "
            "checks visible"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/local_intents.py",
            101,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the retain_v1_effect_intents closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: PLR0913 - exact authority lineage.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/real_effects.py",
            120,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "issuing write authority explicitly binds Approval, retained intents, serving "
            "profile, manifest, exact token counter, and execution lineage"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/real_effects.py",
            780,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the compose_v1_real_effects closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: PLR0913 - two credentials, two transports, authority.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/service.py",
            101,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the replay fingerprint helper names every exact immutable Task 8 execution input",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/service.py",
            292,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the promotion sequence keeps every pre-effect validation and state transition visible",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_execution.py",
            145,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the compose_approved_promotion_activity closed owner boundary keeps this exact "
            "reviewed suppression local (noqa: PLR0913 - exact injected boundaries.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_infrastructure.py",
            271,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the preflight_v1_promotion closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: C901, PLR0912 - closed retained-input trust boundary.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_infrastructure.py",
            476,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the compose_admitted_provider_effects closed owner boundary keeps this exact "
            "reviewed suppression local (noqa: PLR0913 - exact composition inputs.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_infrastructure.py",
            499,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the compose_approved_provider_effects closed owner boundary keeps this exact "
            "reviewed suppression local (noqa: PLR0913, PLR0917 - exact authority inputs.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            109,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the schedule_new_orchestration signature mirrors the pinned external SDK keyword "
            "exactly at this reviewed adapter boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            345,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'int' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            348,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'str' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            349,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'str' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            371,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'int' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            372,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'str' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            373,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'str' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            374,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'str' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            375,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'str' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            376,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'str | None' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            377,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'str | None' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            378,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'str | None' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            379,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'str | None' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            380,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'str | None' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            381,
            BoundaryCode.CAST,
        ),
        (
            "the _read_retry_state closed runtime-validation boundary narrows 'str | None' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            433,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _retry_state closed owner boundary keeps this exact reviewed suppression local "
            "(noqa: PLR0913)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            512,
            BoundaryCode.CAST,
        ),
        (
            "the _recovery_authority closed runtime-validation boundary narrows 'str' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            513,
            BoundaryCode.CAST,
        ),
        (
            "the _recovery_authority closed runtime-validation boundary narrows 'str' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            662,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the dispatch_pending_promotions closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: C901,PLR0912,PLR0913,PLR0915)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            887,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the dispatch_pending_promotions hostile adapter boundary intentionally normalizes "
            "every external failure to its closed non-secret result"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            897,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _build_serve closed owner boundary keeps this exact reviewed suppression local "
            "(noqa: PLR0913 - all retained recovery roots are load-bearing.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/src/asklegal_promotion_worker/v1_service.py",
            973,
            BoundaryCode.CAST,
        ),
        (
            "the resolve closed runtime-validation boundary narrows 'dict[str, object]' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_live_retrieval_evaluation.py",
            156,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _receipt closed test boundary keeps this exact reviewed suppression local "
            "(pyright: ignore[reportArgumentType])"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_live_retrieval_evaluation.py",
            174,
            BoundaryCode.CAST,
        ),
        (
            "the test_retrieval_receipt_rejects_expected_record_removed_from_results "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_live_retrieval_evaluation.py",
            175,
            BoundaryCode.CAST,
        ),
        (
            "the test_retrieval_receipt_rejects_expected_record_removed_from_results "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_promotion_evidence.py",
            104,
            BoundaryCode.CAST,
        ),
        (
            "the test_rollback_owner_evidence_requires_exact_t2_to_t1_retained_cas "
            "fixture/replay boundary narrows 'V1PromotionPreflight' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_promotion_evidence.py",
            138,
            BoundaryCode.CAST,
        ),
        (
            "the test_rollback_owner_evidence_requires_exact_t2_to_t1_retained_cas "
            "fixture/replay boundary narrows 'dict[str, JsonValue]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_approval_to_promotion.py",
            96,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the readiness fixture names every immutable fact shown to the local human reviewer",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            56,
            BoundaryCode.CAST,
        ),
        "the focused loader test obtains one typed callable from the repository-owned test module",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            62,
            BoundaryCode.CAST,
        ),
        (
            "the focused loader test obtains one typed callable from the repository-owned "
            "fixture script"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            457,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the schedule_new_orchestration signature mirrors the pinned external SDK keyword "
            "exactly at this reviewed adapter boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            462,
            BoundaryCode.CAST,
        ),
        (
            "the schedule_new_orchestration fixture/replay boundary narrows 'dict[str, str]' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            475,
            BoundaryCode.CAST,
        ),
        (
            "the restart_orchestration fixture/replay boundary narrows '_WakeupState' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            532,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _cross_process_dispatch closed test boundary keeps this exact reviewed "
            "suppression local (noqa: PLR0913,PLR0917)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            583,
            BoundaryCode.CAST,
        ),
        (
            "the _write_retry_intents fixture/replay boundary narrows 'PromotionManifest' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            600,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _write_recovery_authority test boundary accesses one repository-owned private "
            "seam at this exact reviewed integration site"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            673,
            BoundaryCode.CAST,
        ),
        (
            "the test_failed_promotion_restarts_under_the_same_approval_lineage fixture/replay "
            "boundary narrows 'dict[str, object]' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            702,
            BoundaryCode.CAST,
        ),
        (
            "the test_failed_promotion_past_intent_deadline_never_restarts fixture/replay "
            "boundary narrows 'dict[str, object]' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            719,
            BoundaryCode.CAST,
        ),
        (
            "the test_failed_promotion_rejects_non_reconciling_intent_retry_class "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            720,
            BoundaryCode.CAST,
        ),
        (
            "the test_failed_promotion_rejects_non_reconciling_intent_retry_class "
            "fixture/replay boundary narrows 'list[dict[str, object]]' at this exact reviewed "
            "site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            821,
            BoundaryCode.CAST,
        ),
        (
            "the test_unchanged_terminal_promotion_state_is_not_restarted_in_a_busy_loop "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            828,
            BoundaryCode.CAST,
        ),
        (
            "the test_unchanged_terminal_promotion_state_is_not_restarted_in_a_busy_loop "
            "fixture/replay boundary narrows '_WakeupState' at this exact reviewed site after "
            "the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            838,
            BoundaryCode.CAST,
        ),
        (
            "the test_unchanged_terminal_promotion_state_is_not_restarted_in_a_busy_loop "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            901,
            BoundaryCode.CAST,
        ),
        (
            "the restart_orchestration fixture/replay boundary narrows '_WakeupState' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            934,
            BoundaryCode.CAST,
        ),
        (
            "the test_terminated_lost_ack_consumes_authority_after_generation_readback "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            971,
            BoundaryCode.CAST,
        ),
        (
            "the test_last_updated_change_does_not_masquerade_as_a_new_scheduler_generation "
            "fixture/replay boundary narrows '_WakeupState' at this exact reviewed site after "
            "the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            981,
            BoundaryCode.CAST,
        ),
        (
            "the test_last_updated_change_does_not_masquerade_as_a_new_scheduler_generation "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            1057,
            BoundaryCode.CAST,
        ),
        (
            "the test_initial_schedule_stops_when_current_deadline_is_closed fixture/replay "
            "boundary narrows 'dict[str, object]' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            1106,
            BoundaryCode.CAST,
        ),
        (
            "the test_dispatch_rechecks_deadline_after_scheduler_read_before_action "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            1157,
            BoundaryCode.CAST,
        ),
        (
            "the test_terminated_authority_expiry_is_rechecked_at_restart_boundary "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            1175,
            BoundaryCode.CAST,
        ),
        (
            "the restart_orchestration fixture/replay boundary narrows '_WakeupState' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            1200,
            BoundaryCode.CAST,
        ),
        (
            "the test_lost_restart_ack_reconciles_changed_terminal_generation_once "
            "fixture/replay boundary narrows 'dict[str, object]' at this exact reviewed site "
            "after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            1217,
            BoundaryCode.CAST,
        ),
        (
            "the test_activity_rechecks_current_deadline_before_service_effects fixture/replay "
            "boundary narrows 'PromotionManifest' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            1224,
            BoundaryCode.CAST,
        ),
        (
            "the test_activity_rechecks_current_deadline_before_service_effects fixture/replay "
            "boundary narrows 'V1PromotionPreflight' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            1234,
            BoundaryCode.CAST,
        ),
        (
            "the test_activity_rechecks_current_deadline_before_service_effects fixture/replay "
            "boundary narrows 'PromotionService' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            1240,
            BoundaryCode.CAST,
        ),
        (
            "the test_activity_rechecks_current_deadline_before_service_effects fixture/replay "
            "boundary narrows 'ActivityContext' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            1248,
            BoundaryCode.CAST,
        ),
        (
            "the test_executable_review_package_recovers_exact_typed_manifest fixture/replay "
            "boundary narrows 'PromotionManifest' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/promotion-worker/tests/test_v1_live_service_composition.py",
            1249,
            BoundaryCode.CAST,
        ),
        (
            "the test_executable_review_package_recovers_exact_typed_manifest fixture/replay "
            "boundary narrows '_FixtureResult' at this exact reviewed site after the "
            "surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/api.py",
            533,
            BoundaryCode.CAST,
        ),
        (
            "the _read_local_review_authority closed runtime-validation boundary narrows "
            "'list[JsonValue]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/api.py",
            537,
            BoundaryCode.CAST,
        ),
        (
            "the _read_local_review_authority closed runtime-validation boundary narrows "
            "'list[str]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/api.py",
            1118,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _load_state closed owner boundary keeps this exact reviewed suppression local "
            "(noqa: PLR0912 - exact ledger checks stay explicit.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/api.py",
            1208,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the create_app closed owner boundary keeps this exact reviewed suppression local "
            "(noqa: PLR0915 - routes are one explicit closed API surface.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/governance.py",
            263,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the atomic Review command keeps all authorization and decision checks visibly together",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/registered_proposals.py",
            106,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the immutable Review projection explicitly names every human-visible approval fact",
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/registered_proposals.py",
            853,
            BoundaryCode.CAST,
        ),
        (
            "the _load_evidence_audit closed runtime-validation boundary narrows "
            "'list[JsonValue]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/registered_proposals.py",
            902,
            BoundaryCode.CAST,
        ),
        (
            "the read_evidence closed runtime-validation boundary narrows 'list[JsonValue]' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/registered_proposals.py",
            907,
            BoundaryCode.CAST,
        ),
        (
            "the read_evidence closed runtime-validation boundary narrows 'dict[str, "
            "JsonValue]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/registered_proposals.py",
            917,
            BoundaryCode.CAST,
        ),
        (
            "the read_evidence closed runtime-validation boundary narrows 'list[JsonValue]' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/registered_proposals.py",
            928,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the Task 7 proposal reader keeps every two-family completeness and capability "
            "invariant together for exact retained-byte validation"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/registered_proposals.py",
            1155,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the review-evidence root explicitly binds the complete immutable artifact set and "
            "approval context without a promotion-manifest hash cycle"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/registered_proposals.py",
            1354,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the hk_v1_local_review_evidence_fingerprint closed owner boundary keeps this exact "
            "reviewed suppression local (noqa: PLR0913 - exact root fact set.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "apps/review-api/src/asklegal_review_api/v1_service.py",
            29,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the container listener must bind every interface of its own private network; it is "
            "reachable only from that network and only over the internal authority's TLS, and "
            "the host nftables table that would narrow it further is not applied"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/application-runtime/src/asklegal_application_runtime/probes.py",
            144,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "this is the readiness normalization boundary: every adapter exception must become "
            "one safe failure so no provider or credential detail can reach the gate"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/application-runtime/src/asklegal_application_runtime/service.py",
            64,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "an unexpected serve failure must become one closed process exit code rather than a "
            "traceback that could carry connection or credential detail into the journal"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/contracts/src/asklegal_contracts/json_types.py",
            28,
            BoundaryCode.CAST,
        ),
        "runtime list recognition is narrowed to object elements before recursive validation",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/contracts/src/asklegal_contracts/json_types.py",
            33,
            BoundaryCode.CAST,
        ),
        "runtime mapping recognition is narrowed before every key and value is validated",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/contracts/src/asklegal_contracts/schemas.py",
            51,
            BoundaryCode.CAST,
        ),
        "referencing's recursive Schema alias is narrower than the validated JSON mapping",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/contracts/src/asklegal_contracts/schemas.py",
            86,
            BoundaryCode.CAST,
        ),
        "jsonschema's dependency-owned iterator type is narrowed to the tested adapter protocol",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/contracts/src/asklegal_contracts/schemas.py",
            88,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the exact jsonschema member diagnostic is contained beside the typed adapter and tests",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/contracts/src/asklegal_contracts/strict_json.py",
            48,
            BoundaryCode.CAST,
        ),
        "stdlib json.loads returns Any and is immediately passed to the recursive runtime checker",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/legal-desks/src/asklegal_legal_desks/hk_case_proposition.py",
            832,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _output_request closed owner boundary keeps this exact reviewed suppression "
            "local (type: ignore[assignment])"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/legal-desks/src/asklegal_legal_desks/hk_legislation_retained.py",
            621,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the Plan 3 contract requires stdlib ElementTree after exact UTF-8 decoding and "
            "explicit DTD, entity, NUL, encoding, and XInclude rejection"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/legal-desks/src/asklegal_legal_desks/hk_legislation_retained_structure.py",
            812,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the Plan 3 retained profiler requires bounded stdlib iterparse with streaming "
            "UTF-8, declaration, entity, NUL, size, and fail-closed XInclude detection"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/legal-desks/src/asklegal_legal_desks/hk_legislation_retained_structure.py",
            1031,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the bound retained XSD profile uses stdlib iterparse after exact read-back and "
            "UTF-8, declaration, entity, NUL, size, and fail-closed XInclude detection"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/management-register-adapter/src/asklegal_management_register/driver.py",
            86,
            BoundaryCode.IGNORED_ERROR,
        ),
        "mssql-python 1.12 leaves execute parameters unknown behind this typed wrapper",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/management-register-adapter/src/asklegal_management_register/driver.py",
            88,
            BoundaryCode.IGNORED_ERROR,
        ),
        "mssql-python 1.12 leaves parameterless execute unknown behind this typed wrapper",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            103,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the run_live_semantic_evaluation closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: PLR0913 - exact evaluation lineage.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            195,
            BoundaryCode.CAST,
        ),
        (
            "the _decision closed runtime-validation boundary narrows 'dict[str, object]' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            210,
            BoundaryCode.CAST,
        ),
        (
            "the _decision closed runtime-validation boundary narrows 'dict[str, object]' at "
            "this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            218,
            BoundaryCode.CAST,
        ),
        (
            "the _decision closed runtime-validation boundary narrows 'list[object]' at this "
            "exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            219,
            BoundaryCode.CAST,
        ),
        (
            "the _decision closed runtime-validation boundary narrows 'list[str]' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            229,
            BoundaryCode.CAST,
        ),
        (
            "the _decision closed runtime-validation boundary narrows 'str' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            250,
            BoundaryCode.CAST,
        ),
        (
            "the _decision closed runtime-validation boundary narrows 'str' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            251,
            BoundaryCode.CAST,
        ),
        (
            "the _decision closed runtime-validation boundary narrows 'str' at this exact "
            "reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            257,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the parse_live_semantic_evaluation closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: C901 - closed receipt grammar.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            267,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            296,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            307,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'list[object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            310,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            331,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'list[object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            334,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            336,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            338,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            341,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'list[str]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            347,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            355,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            365,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            369,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            370,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            371,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            372,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            373,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            374,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/processing/src/asklegal_processing/live_evaluation.py",
            376,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_semantic_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            157,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the run_live_retrieval_evaluation closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: PLR0913 - exact evaluation lineage.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            304,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the parse_live_retrieval_evaluation closed owner boundary keeps this exact "
            "reviewed suppression local (noqa: C901, PLR0912, PLR0915 - closed receipt "
            "grammar.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            314,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            353,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            365,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'list[object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            368,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            386,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'list[JsonValue]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            400,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'list[object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            403,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            414,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            435,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            442,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'int' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            444,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'int' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            446,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'int' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            465,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'list[object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            468,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            488,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'list[object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            492,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'int' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            493,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'int' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            495,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            497,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            508,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[object, object]' at this exact reviewed site after the surrounding shape "
            "checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            509,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[object, object]' at this exact reviewed site after the surrounding shape "
            "checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            510,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[object, object]' at this exact reviewed site after the surrounding shape "
            "checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            511,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[object, object]' at this exact reviewed site after the surrounding shape "
            "checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            512,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[object, object]' at this exact reviewed site after the surrounding shape "
            "checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            513,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[object, object]' at this exact reviewed site after the surrounding shape "
            "checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            515,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            517,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            528,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'list[object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            531,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            542,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            546,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            548,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'list[str]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            551,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            553,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            566,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'list[dict[str, object]]' at this exact reviewed site after the surrounding shape "
            "checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            580,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            584,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            589,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'dict[str, object]' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            591,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            594,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            598,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            599,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            600,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            601,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            602,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            603,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            604,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            605,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/live_retrieval.py",
            607,
            BoundaryCode.CAST,
        ),
        (
            "the parse_live_retrieval_evaluation closed runtime-validation boundary narrows "
            "'str' at this exact reviewed site after the surrounding shape checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/promotion/src/asklegal_promotion/remote.py",
            490,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the __init__ closed owner boundary keeps this exact reviewed suppression local "
            "(noqa: PLR0913 - exact profile, gate, accounting, and transport bindings.)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/reporting/src/asklegal_reporting/hk_v1_due_cycle.py",
            1346,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the sole cross-application registrar deliberately remains private, so Pyright "
            "cannot observe its one acquisition-owned call and needs this reviewed marker"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/reporting/src/asklegal_reporting/hk_v1_due_cycle.py",
            2599,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the strict Legislation manifest projection keeps every producer invariant in one "
            "closed cross-application parser"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/reporting/src/asklegal_reporting/hk_v1_proposal_evidence.py",
            179,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "semantic verification binds two exact stored documents, their logical references, "
            "capability kind, and cutoff in one issuer-receipt boundary"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/reporting/src/asklegal_reporting/hk_v1_proposal_evidence.py",
            283,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "prepared-batch parsing keeps canonical shape, content identity, path, and disabled "
            "state checks together before issuing a verified projection"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/reporting/src/asklegal_reporting/hk_v1_proposal_evidence.py",
            499,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "capability evidence validation binds the exact profile receipt identities and "
            "provider-disabled issuer fields in one closed cross-document check"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/src/asklegal_source_connectors/hk_judiciary_authentic.py",
            493,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the versioned Judiciary form builder keeps its closed field-shape, locator, and "
            "legacy replay grammar together for direct contract review"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/src/asklegal_source_connectors/hk_judiciary_authentic.py",
            1070,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the bounded RSS parser uses stdlib ElementTree only after exact UTF-8 decoding and "
            "explicit DOCTYPE and entity rejection"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/src/asklegal_source_connectors/hk_judiciary_authentic.py",
            1351,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the versioned Judiciary result parser keeps its closed structural, count, row, "
            "locator, and legacy replay validation together for direct contract review"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/src/asklegal_source_connectors/hk_judiciary_authentic.py",
            1920,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the versioned Judiciary partition reconciliation keeps raw-count, overlap, stable "
            "identity-map, and legacy replay invariants together for direct review"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/src/asklegal_source_connectors/hkel_archive_admission.py",
            215,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the source-neutral archive verifier uses bounded stdlib iterparse only after "
            "streaming declaration, member, expansion, namespace, and profile checks"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/src/asklegal_source_connectors/hkex_dom.py",
            965,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the pure association constructor mirrors the complete immutable report row",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/src/asklegal_source_connectors/hkex_dom.py",
            1055,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the pure occurrence constructor mirrors the complete immutable report row",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/src/asklegal_source_connectors/hkex_fees.py",
            38,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the pure Fees parser exposes the complete frozen root and section contract",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/src/asklegal_source_connectors/hkex_forms.py",
            47,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the pure Forms parser exposes the complete frozen root and section contract",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/src/asklegal_source_connectors/hkex_updates.py",
            133,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the positional Updates parser exposes the complete frozen two-page contract",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/src/asklegal_source_connectors/official_http.py",
            785,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the _read_response_before_deadline closed owner boundary keeps this exact reviewed "
            "suppression local (noqa: PLR0913, PLR0917)"
        ),
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/tests/test_hkex_fees.py",
            45,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the parameterized Fees proof carries the exact six immutable fixture facts",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/tests/test_hkex_forms.py",
            40,
            BoundaryCode.CAST,
        ),
        "the fixture manifest is runtime-checked before mapping access",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/tests/test_hkex_forms.py",
            42,
            BoundaryCode.CAST,
        ),
        "the fixture list and each typed fixture row are narrowed after runtime checks",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/tests/test_hkex_forms.py",
            75,
            BoundaryCode.IGNORED_ERROR,
        ),
        "the parameterized Forms proof carries the exact six immutable fixture facts",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/tests/test_hkex_updates.py",
            45,
            BoundaryCode.CAST,
        ),
        "the retained structure manifest is runtime-checked before mapping access",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/tests/test_hkex_updates.py",
            47,
            BoundaryCode.CAST,
        ),
        "the retained board list is narrowed only after its runtime list check",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/tests/test_hkex_updates.py",
            48,
            BoundaryCode.CAST,
        ),
        "each retained board fact is narrowed to the exact test mapping shape",
    ),
    ApprovedException(
        ExceptionKey(
            "packages/source-connectors/tests/test_official_http_connector.py",
            271,
            BoundaryCode.IGNORED_ERROR,
        ),
        (
            "the test_proxied_transport_decreases_one_deadline_through_response_read closed "
            "test boundary keeps this exact reviewed suppression local (noqa: C901)"
        ),
    ),
)

_SOURCE_PATTERNS: tuple[str, ...] = (
    "packages/*/src/**/*.py",
    "packages/*/tests/**/*.py",
    "apps/*/src/**/*.py",
    "apps/*/tests/**/*.py",
)
_TYPING_MODULES = frozenset({"typing", "typing_extensions"})
_COLLECTION_NAMES = frozenset(
    {
        "AsyncGenerator",
        "AsyncIterable",
        "AsyncIterator",
        "Awaitable",
        "Callable",
        "Collection",
        "Container",
        "Coroutine",
        "DefaultDict",
        "Deque",
        "Dict",
        "Generator",
        "Hashable",
        "Iterable",
        "Iterator",
        "List",
        "Mapping",
        "MutableMapping",
        "MutableSequence",
        "MutableSet",
        "Sequence",
        "Set",
        "Tuple",
        "Type",
        "dict",
        "frozenset",
        "list",
        "set",
        "tuple",
        "type",
    }
)
_INFRASTRUCTURE_ROOTS = frozenset(
    {
        "azure",
        "durabletask",
        "mssql_python",
        "pinecone",
        "pyodbc",
        "sqlalchemy",
    }
)
_FRAMEWORK_ROOTS = frozenset({"django", "fastapi", "flask", "starlette", "uvicorn"})
_DOMAIN_EXTRA_ROOTS = frozenset({"jsonschema", "pydantic", "referencing", "rfc8785"})
_IGNORE_PATTERN = re.compile(r"#\s*(?:type:\s*ignore\b|pyright:\s*ignore\b|noqa\b)")
_PACKAGE_PATH_PARTS = 3
_MINIMUM_EXCEPTION_REASON_LENGTH = 24


class _BoundaryVisitor(ast.NodeVisitor):
    """Inspect one parsed module using its import aliases and package role."""

    def __init__(
        self,
        *,
        relative_path: str,
        approved: frozenset[ExceptionKey],
        protected_package: bool,
        domain_package: bool,
        framework_free_package: bool,
    ) -> None:
        self.relative_path = relative_path
        self.approved = approved
        self.protected_package = protected_package
        self.domain_package = domain_package
        self.framework_free_package = framework_free_package
        self.findings: list[Finding] = []
        self.used_exceptions: set[ExceptionKey] = set()
        self._typing_aliases: set[str] = set()
        self._cast_aliases: set[str] = set()
        self._collection_aliases: set[str] = set()

    def _record(self, node: ast.AST, code: BoundaryCode, detail: str) -> None:
        line = getattr(node, "lineno", 1)
        key = ExceptionKey(self.relative_path, line, code)
        if key in self.approved:
            self.used_exceptions.add(key)
            return
        self.findings.append(Finding(self.relative_path, line, code, detail))

    def _check_import_root(self, node: ast.AST, module: str) -> None:
        root = module.partition(".")[0]
        segments = frozenset(module.split("."))
        if self.protected_package and (
            root in _INFRASTRUCTURE_ROOTS or "infrastructure" in segments or "adapters" in segments
        ):
            self._record(
                node,
                BoundaryCode.INFRASTRUCTURE_IMPORT,
                f"protected package imports infrastructure module {module!r}",
            )
        if self.domain_package and root in _DOMAIN_EXTRA_ROOTS:
            self._record(
                node,
                BoundaryCode.FRAMEWORK_IMPORT,
                f"domain package imports boundary library {module!r}",
            )
        if self.framework_free_package and root in _FRAMEWORK_ROOTS:
            self._record(
                node,
                BoundaryCode.FRAMEWORK_IMPORT,
                f"domain package imports application framework {module!r}",
            )

    def visit_Import(self, node: ast.Import) -> None:
        """Record module aliases and enforce protected import roots."""
        for alias in node.names:
            self._check_import_root(node, alias.name)
            if alias.name in _TYPING_MODULES:
                self._typing_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record imported type helpers and enforce protected import roots."""
        module = node.module or ""
        if node.level == 0 and module:
            self._check_import_root(node, module)
        if module in _TYPING_MODULES:
            for alias in node.names:
                local_name = alias.asname or alias.name
                if alias.name == "Any":
                    self._record(node, BoundaryCode.ANY, "typing.Any import is not approved")
                elif alias.name == "cast":
                    self._cast_aliases.add(local_name)
                elif alias.name in _COLLECTION_NAMES:
                    self._collection_aliases.add(local_name)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Reject qualified typing.Any uses."""
        if (
            isinstance(node.value, ast.Name)
            and node.value.id in self._typing_aliases
            and node.attr == "Any"
        ):
            self._record(node, BoundaryCode.ANY, "typing.Any is not approved")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Require every static cast to occupy one exact reviewed position."""
        direct_cast = isinstance(node.func, ast.Name) and node.func.id in self._cast_aliases
        qualified_cast = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self._typing_aliases
            and node.func.attr == "cast"
        )
        if direct_cast or qualified_cast:
            self._record(node, BoundaryCode.CAST, "static cast is not explicitly approved")
        self.generic_visit(node)

    def _check_annotation(self, annotation: ast.expr) -> None:
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            try:
                parsed = ast.parse(annotation.value, mode="eval")
            except SyntaxError:
                return
            ast.increment_lineno(parsed, annotation.lineno - 1)
            self._check_annotation(parsed.body)
            return
        if isinstance(annotation, ast.Subscript):
            self._check_annotation(annotation.slice)
            return
        if isinstance(annotation, ast.Name):
            if annotation.id in _COLLECTION_NAMES or annotation.id in self._collection_aliases:
                self._record(
                    annotation,
                    BoundaryCode.UNPARAMETERIZED_COLLECTION,
                    f"collection annotation {annotation.id!r} has no type arguments",
                )
            return
        if isinstance(annotation, ast.Attribute):
            if (
                isinstance(annotation.value, ast.Name)
                and annotation.value.id in self._typing_aliases
                and annotation.attr in _COLLECTION_NAMES
            ):
                self._record(
                    annotation,
                    BoundaryCode.UNPARAMETERIZED_COLLECTION,
                    f"collection annotation {annotation.attr!r} has no type arguments",
                )
            return
        for child in ast.iter_child_nodes(annotation):
            if isinstance(child, ast.expr):
                self._check_annotation(child)

    def _check_arguments(self, arguments: ast.arguments) -> None:
        all_arguments = (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
        )
        for argument in all_arguments:
            if argument.annotation is not None:
                self._check_annotation(argument.annotation)
        if arguments.vararg is not None and arguments.vararg.annotation is not None:
            self._check_annotation(arguments.vararg.annotation)
        if arguments.kwarg is not None and arguments.kwarg.annotation is not None:
            self._check_annotation(arguments.kwarg.annotation)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check every synchronous function annotation."""
        self._check_arguments(node.args)
        if node.returns is not None:
            self._check_annotation(node.returns)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Check every asynchronous function annotation."""
        self._check_arguments(node.args)
        if node.returns is not None:
            self._check_annotation(node.returns)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Check annotated variables and attributes."""
        self._check_annotation(node.annotation)
        self.generic_visit(node)

    def visit_TypeAlias(self, node: ast.TypeAlias) -> None:
        """Check Python 3.12+ type alias declarations."""
        self._check_annotation(node.value)
        self.generic_visit(node)


def _package_roles(relative_path: str) -> tuple[bool, bool, bool]:
    parts = Path(relative_path).parts
    if (
        len(parts) < _PACKAGE_PATH_PARTS
        or parts[0] not in {"apps", "packages"}
        or parts[2] != "src"
    ):
        return False, False, False
    package_name = parts[1]
    is_adapter = "adapter" in package_name or "infrastructure" in package_name
    protected_package = not is_adapter
    domain_package = package_name.startswith("domain")
    framework_free_package = package_name == "contracts" or domain_package
    return protected_package, domain_package, framework_free_package


def _comment_findings(
    *,
    source: str,
    relative_path: str,
    approved: frozenset[ExceptionKey],
) -> tuple[list[Finding], set[ExceptionKey]]:
    findings: list[Finding] = []
    used: set[ExceptionKey] = set()
    for token in tokenize.generate_tokens(iter(source.splitlines(keepends=True)).__next__):
        if token.type != tokenize.COMMENT or _IGNORE_PATTERN.search(token.string) is None:
            continue
        key = ExceptionKey(relative_path, token.start[0], BoundaryCode.IGNORED_ERROR)
        if key in approved:
            used.add(key)
        else:
            findings.append(
                Finding(
                    relative_path,
                    token.start[0],
                    BoundaryCode.IGNORED_ERROR,
                    "type or lint error suppression is not explicitly approved",
                )
            )
    return findings, used


def check_files(
    root: Path,
    paths: tuple[Path, ...],
    approved_exceptions: tuple[ApprovedException, ...] = (),
    *,
    require_all_exceptions: bool = False,
) -> tuple[Finding, ...]:
    """Check exact Python paths and optionally reject unused exception entries."""
    approved_by_key = {exception.key: exception for exception in approved_exceptions}
    findings: list[Finding] = []
    used_exceptions: set[ExceptionKey] = set()
    if len(approved_by_key) != len(approved_exceptions):
        findings.append(
            Finding("<policy>", 1, BoundaryCode.INVALID_POLICY, "duplicate exception key")
        )
    findings.extend(
        Finding(
            exception.key.path,
            exception.key.line,
            BoundaryCode.INVALID_POLICY,
            "approved exception requires a specific durable reason",
        )
        for exception in approved_exceptions
        if len(exception.reason.strip()) < _MINIMUM_EXCEPTION_REASON_LENGTH
    )

    approved_keys = frozenset(approved_by_key)
    for path in sorted(paths):
        relative_path = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=relative_path)
        except SyntaxError as error:
            findings.append(
                Finding(
                    relative_path,
                    error.lineno or 1,
                    BoundaryCode.INVALID_PYTHON,
                    "file cannot be parsed by the pinned Python grammar",
                )
            )
            continue
        protected_package, domain_package, framework_free_package = _package_roles(relative_path)
        visitor = _BoundaryVisitor(
            relative_path=relative_path,
            approved=approved_keys,
            protected_package=protected_package,
            domain_package=domain_package,
            framework_free_package=framework_free_package,
        )
        visitor.visit(tree)
        findings.extend(visitor.findings)
        used_exceptions.update(visitor.used_exceptions)
        comment_results, comment_exceptions = _comment_findings(
            source=source,
            relative_path=relative_path,
            approved=approved_keys,
        )
        findings.extend(comment_results)
        used_exceptions.update(comment_exceptions)

    if require_all_exceptions:
        findings.extend(
            Finding(
                key.path,
                key.line,
                BoundaryCode.INVALID_POLICY,
                f"approved {key.code} exception is stale or no longer used",
            )
            for key in sorted(approved_keys - used_exceptions)
        )
    return tuple(sorted(findings))


def discover_python_files(root: Path) -> tuple[Path, ...]:
    """Discover current and future package/application Python without a manual list."""
    paths: set[Path] = set()
    for pattern in _SOURCE_PATTERNS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    return tuple(sorted(paths))


def check_repository(root: Path) -> tuple[Finding, ...]:
    """Apply the complete checked-in policy to one repository root."""
    return check_files(
        root,
        discover_python_files(root),
        APPROVED_EXCEPTIONS,
        require_all_exceptions=True,
    )


def main() -> int:
    """Run the repository check and return a shell-friendly result."""
    repository_root = Path(__file__).resolve().parents[1]
    findings = check_repository(repository_root)
    if findings:
        for finding in findings:
            print(f"{finding.path}:{finding.line}: {finding.code} {finding.detail}")
        return 1
    checked_count = len(discover_python_files(repository_root))
    print(
        "PASS Python type boundaries: "
        f"{checked_count} files, {len(APPROVED_EXCEPTIONS)} exact reviewed exceptions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
