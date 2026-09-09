"""Deterministic legislation-family work graph and manifest tests."""
# pyright: reportPrivateUsage=false

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest
from asklegal_acquisition_worker import v1_pipeline
from asklegal_acquisition_worker.acquisition_journal import (
    AcquisitionCycleResult,
    CheckpointItem,
    ImportedCaptureVerifiedPayload,
    JournalTransition,
    LocalAcquisitionJournal,
    WorkItemIdentity,
)
from asklegal_acquisition_worker.gld_session import GldSessionError
from asklegal_acquisition_worker.hk_legislation_acquisition import (
    LEGISLATION_SCOPE_IDS,
    HkelArchiveProvenanceKind,
    HkelImportedBaseline,
    LegislationAcceptedSourceState,
    LegislationAcquisitionManifest,
    LegislationVerifiedItem,
    LegislationWorkGraph,
    LegislationWorkKind,
    LegislationWorkNode,
    LegislationWorkSeed,
    bind_imported_hkel_baseline,
    build_legislation_acquisition_manifest,
    build_legislation_work_graph,
    changed_legislation_inputs,
    hkel_baseline_to_json,
    legislation_runner_dependencies,
    load_accepted_legislation_source_state,
    registered_legislation_work_seeds,
    restore_hkel_baseline,
    run_legislation_acquisition_cycle,
    run_legislation_resumable_graph,
)
from asklegal_acquisition_worker.resumable_acquisition import (
    AcquisitionCycleReport,
    CaptureOutcome,
    CycleBudget,
)
from asklegal_acquisition_worker.retained_evidence_import import (
    RetainedImportReceipt,
    RetainedReportReference,
    import_retained_report,
)
from asklegal_acquisition_worker.v1_infrastructure import V1AcquisitionInfrastructure
from asklegal_acquisition_worker.v1_pipeline import (
    AcquisitionActivities,
    AcquisitionPipelineError,
    LegislationProductionCycleInputs,
)
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_durable_task import ActivityContext
from asklegal_management_register_ports import (
    AcquisitionObservationRecord,
    InMemoryAcquisitionRegister,
)
from asklegal_reporting import parse_hk_v1_legislation_acquisition_manifest
from asklegal_source_connectors import (
    GldGazetteClass,
    GldGazetteEntry,
    GldGazetteIssueKind,
    GldGazetteWindow,
    GldSessionGrant,
    GldSessionRequest,
    HkelArchiveReuseKey,
    admit_hkel_current_archive,
    enumerate_gld_gazette_window,
)

_CYCLE_A = "cyc_20260904_legislation_a"
_CYCLE_B = "cyc_20260904_legislation_b"
_CYCLE_C = "cyc_20260904_legislation_c"
_CUTOFF = "2026-09-04T00:00:00+00:00"
_HEAD = "sha256:" + "a" * 64
_REGISTER_FINGERPRINT = "sha256:be2dc02b4ef087ac2357ad96dc05be5a36127e2a7f395bffe5b7a98f6408de67"


class _ActivityClock:
    def __init__(self) -> None:
        self._now = datetime(2026, 9, 4, tzinfo=UTC)
        self._monotonic = 0

    def monotonic_ns(self) -> int:
        return self._monotonic

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        self._monotonic += round(seconds * 1_000_000_000)


class _ActivityVerifier:
    @staticmethod
    def verify(
        item: WorkItemIdentity,
        object_ref: str,
        content_fingerprint: str,
        body_length: int,
    ) -> bool:
        del item, object_ref, content_fingerprint, body_length
        return True


def _test_retained_verifier(_vault: object) -> _ActivityVerifier:
    return _ActivityVerifier()


class _OfflineLegislationTransport:
    def __init__(self, discovery_id: str) -> None:
        self.discovery_id = discovery_id
        self.calls: list[str] = []
        self.discovery_attempts = 0

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        self.calls.append(item.work_item_id)
        if item.work_item_id == self.discovery_id:
            self.discovery_attempts += 1
            if self.discovery_attempts == 1:
                code = "GLD_CHALLENGE_UNRESOLVED"
                raise GldSessionError(code)
        digest = "sha256:" + sha256(item.work_item_id.encode()).hexdigest()
        return CaptureOutcome(
            work_item_id=item.work_item_id,
            transition=JournalTransition.CAPTURED_VERIFIED,
            status_code=200,
            media_type=item.media_type,
            final_url=item.locator,
            body_length=1,
            body_fingerprint=digest,
            object_ref=f"offline/{item.work_item_id}",
            failure_code=None,
            retry_not_before=None,
            read_back_verified=True,
            redirect_chain=(),
        )


class _CycleTransport:
    """Deterministic offline source boundary keyed by actual registered graph nodes."""

    def __init__(
        self,
        graph: LegislationWorkGraph,
        changed_keys: frozenset[str],
        *,
        retry_gld_once: bool,
        base_fingerprints: dict[str, str] | None = None,
        retry_keys: frozenset[str] = frozenset(),
    ) -> None:
        self._nodes = {node.scheduled.identity.work_item_id: node for node in graph.nodes}
        self._changed_keys = changed_keys
        self._retry_gld_once = retry_gld_once
        self._base_fingerprints = base_fingerprints or {}
        self._retry_keys = retry_keys
        self._retried = False
        self.verified: dict[str, tuple[str, str]] = {}

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        node = self._nodes[item.work_item_id]
        if node.stable_key in self._retry_keys:
            code = "GLD_CHALLENGE_UNRESOLVED"
            raise GldSessionError(code)
        if (
            self._retry_gld_once
            and not self._retried
            and node.kind is LegislationWorkKind.GLD_ISSUE_DISCOVERY
        ):
            self._retried = True
            code = "GLD_CHALLENGE_UNRESOLVED"
            raise GldSessionError(code)
        marker = "b" if node.stable_key in self._changed_keys else "a"
        fingerprint = (
            "sha256:" + marker * 64
            if node.stable_key in self._changed_keys
            else self._base_fingerprints.get(node.stable_key, "sha256:" + marker * 64)
        )
        object_ref = f"offline/{node.stable_key}/{fingerprint.removeprefix('sha256:')}"
        self.verified[node.stable_key] = (object_ref, fingerprint)
        return CaptureOutcome(
            work_item_id=item.work_item_id,
            transition=JournalTransition.CAPTURED_VERIFIED,
            status_code=200,
            media_type=item.media_type,
            final_url=item.locator,
            body_length=1,
            body_fingerprint=fingerprint,
            object_ref=object_ref,
            failure_code=None,
            retry_not_before=None,
            read_back_verified=True,
            redirect_chain=(),
        )


def _run_cycle(  # noqa: PLR0913 - compact deterministic runner fixture.
    state_root: Path,
    graph: LegislationWorkGraph,
    changed_keys: frozenset[str] = frozenset(),
    *,
    retry_gld_once: bool = False,
    base_fingerprints: dict[str, str] | None = None,
    retry_keys: frozenset[str] = frozenset(),
) -> tuple[AcquisitionCycleReport, tuple[LegislationVerifiedItem, ...]]:
    clock = _ActivityClock()
    transport = _CycleTransport(
        graph,
        changed_keys,
        retry_gld_once=retry_gld_once,
        base_fingerprints=base_fingerprints,
        retry_keys=retry_keys,
    )
    report = run_legislation_resumable_graph(
        state_root=state_root,
        graph=graph,
        transport=transport,
        retained_verifier=_ActivityVerifier(),
        clock=clock,
        sleeper=clock.sleep,
        budget=CycleBudget(100, 100_000_000_000, 60, 1_000),
    )
    return report, tuple(
        LegislationVerifiedItem.issue(stable_key, *transport.verified[stable_key])
        for stable_key in sorted(transport.verified)
    )


class _AdmitChangedHkelArchives:
    """Injected full-member/XML admission outcome for already retained archive bytes."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def admit_archive(
        self,
        *,
        source_role: str,
        endpoint_id: str,
        object_ref: str,
        content_fingerprint: str,
    ) -> bool:
        assert source_role == "HK_LEG_HKEL_CURRENT_DATA"
        self.calls.append((endpoint_id, object_ref, content_fingerprint))
        return True


class _AdmittedGraphOutcomePort:
    """Local admitted outcomes standing in for unavailable external source sessions."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def capture(self, node: LegislationWorkNode) -> CaptureOutcome:
        identity = node.scheduled.identity
        self.calls.append(node.stable_key)
        fingerprint = "sha256:" + sha256(node.stable_key.encode()).hexdigest()
        return CaptureOutcome(
            work_item_id=identity.work_item_id,
            transition=JournalTransition.CAPTURED_VERIFIED,
            status_code=200,
            media_type=identity.media_type,
            final_url=identity.locator,
            body_length=1,
            body_fingerprint=fingerprint,
            object_ref=f"offline/{node.stable_key}/{fingerprint.removeprefix('sha256:')}",
            failure_code=None,
            retry_not_before=None,
            read_back_verified=True,
            redirect_chain=(),
        )


def _admission_document() -> bytes:
    archive_fingerprints = (
        "7d12582cd93cba2bee8cf89c18dc56941cc626d3b5a5bf380bf711db13be602c",
        "2375d1215006a98549942c30581cf7a01749e9018aa44e017891df5ba049601c",
        "6714d98b5ed219b20706a40c55d71a332eb4757db21e99ca13096f856fdb88eb",
        "51a4d2f38e2d025df4ae2e96292caf8e6fe7b93b7eba7514bf8b8a9d81271b26",
        "796e5272b25dcc1f92c40dd3c0a778432f7b173550c1c3dca49050c57f308bb0",
        "014f9dfa8893a69949f1e4c1493b7fd9cd9904ff27e3b68b92251be6e6009fa9",
        "c1a9b59d15949c45752cb529d0e0e9215ededc88a049447478cc4db413d1379b",
        "85ed0a7ec778f2ce89e7b99393b96839a8ca96b1a6ec4f257529059ccab8d85d",
        "8cf813e8ce7f5039424ec6dc4043635ae0a807d48a9a0bdab6987f640c27e615",
        "8b87db9f64d39d0928902be3362f072a79e06b586f5b2b1fdef606cea6c6957b",
        "66a216c5d013c9d3cb0745b3eead87aab2a20f6754f4011f0b9436a33d56c94b",
        "da12d0791a9a9573b91a86cebe6c9d25a51406ac0a470ed0ec0df1f77a32a603",
    )
    reuse_keys: list[JsonValue] = []
    for index, archive_fingerprint in enumerate(archive_fingerprints, start=10):
        key_body: dict[str, JsonValue] = {
            "archive_endpoint_id": f"sep_{index:048x}",
            "archive_fingerprint": f"sha256:{archive_fingerprint}",
            "publication_profile_fingerprint": (
                "sha256:747c168d4bd8a3836f4c95b541a3d203d120d579102bcbfffc254e30a9585737"
            ),
        }
        reuse_keys.append(
            {
                **key_body,
                "fingerprint": "sha256:" + sha256(canonicalize(key_body)).hexdigest(),
            }
        )
    body: dict[str, JsonValue] = {
        "schema_id": "asklegal.hkel-authentic-admission",
        "schema_version": "1.0.0",
        "attempt_id": "hkel-live-baseline-basic-law20-20260828b",
        "observation_cutoff": "2026-08-28T22:20:23+08:00",
        "report_fingerprint": (
            "sha256:5f6b8625fd7c0ff4093d96b7a2f72e4ededc9b8af54b6c1add02b95e81549b50"
        ),
        "source_observation_fingerprint": (
            "sha256:c5c6fd784c7b96f11c77b99e52090bd9b7afd45a27d1df1faacfac98ca822309"
        ),
        "structure_profile_fingerprint": (
            "sha256:bf44b850d30b0521b1a915f1399915e2aab169dcae5204c8ab5587d6c5a7891f"
        ),
        "archive_member_count": 12_858,
        "bilingual_pair_count": 3_157,
        "publication_specification_count": 7,
        "archive_reuse_keys": reuse_keys,
        "review_issue_refs": [
            "hkel-structure/HKEL_ARCHIVE_ROOT_LANGUAGE_CONFLICT/3",
            "hkel-structure/HKEL_BILINGUAL_ROOT_KIND_CONFLICT/1",
        ],
    }
    return canonicalize(
        {
            **body,
            "fingerprint": "sha256:" + sha256(canonicalize(body)).hexdigest(),
        }
    )


def _hkel_archive(
    members: tuple[tuple[str, bytes], ...], *, compression: int = ZIP_DEFLATED
) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=compression) as archive:
        for name, body in members:
            archive.writestr(name, body)
    return buffer.getvalue()


def _archive_observation_document(
    reuse_keys: tuple[HkelArchiveReuseKey, ...] | None = None,
) -> bytes:
    if reuse_keys is None:
        admission = parse_json_bytes(_admission_document(), max_bytes=1_048_576)
        assert type(admission) is dict
        raw = admission["archive_reuse_keys"]
    else:
        raw = [
            {
                "archive_endpoint_id": item.archive_endpoint_id,
                "archive_fingerprint": item.archive_fingerprint,
                "publication_profile_fingerprint": item.publication_profile_fingerprint,
                "fingerprint": item.fingerprint,
            }
            for item in reuse_keys
        ]
    body = checked_json_value(
        {
            "schema_id": "asklegal.hkel-archive-observation",
            "schema_version": "1.0.0",
            "archive_reuse_keys": raw,
        }
    )
    assert type(body) is dict
    return canonicalize({**body, "fingerprint": "sha256:" + sha256(canonicalize(body)).hexdigest()})


def _valid_hkel_xml(language: str = "en") -> bytes:
    root_language = "en" if language == "en" else f"{language}-HK"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<lawDoc xmlns="http://www.xml.gov.hk/schemas/hklm/1.0" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        f'xml:lang="{root_language}" '
        'xsi:schemaLocation="http://www.xml.gov.hk/schemas/hklm/1.0 '
        'https://www.elegislation.gov.hk/schemas/hklm.xsd"><heading>valid</heading></lawDoc>'
    ).encode()


def _reseal_admission(mutator: Callable[[dict[str, JsonValue]], None]) -> bytes:
    """Return a coherently self-hashed but evidence-foreign admission document."""
    document = parse_json_bytes(_admission_document(), max_bytes=1_048_576)
    assert type(document) is dict
    mutator(document)
    body = {key: value for key, value in document.items() if key != "fingerprint"}
    document["fingerprint"] = "sha256:" + sha256(canonicalize(body)).hexdigest()
    return canonicalize(document)


def _arbitrary_seeds() -> tuple[LegislationWorkSeed, ...]:
    return tuple(
        LegislationWorkSeed(
            stable_key=f"source-{index:02d}",
            kind=kind,
            source_role=f"HK_LEGISLATION_{kind.value}",
            locator=(
                f"https://egazette.gld.gov.hk/issued/{index}"
                if kind
                in {
                    LegislationWorkKind.GLD_ISSUE_DISCOVERY,
                    LegislationWorkKind.GLD_EVENT_ARTIFACT,
                }
                else f"https://www.elegislation.gov.hk/source/{index}"
            ),
            media_type="application/octet-stream",
            max_bytes=4096,
            scope_ids=(LEGISLATION_SCOPE_IDS[index % len(LEGISLATION_SCOPE_IDS)],),
            dependency_keys=(() if index == 0 else (f"source-{index - 1:02d}",)),
        )
        for index, kind in enumerate(LegislationWorkKind)
    )


def _gld_window(observation_cutoff: str = _CUTOFF) -> GldGazetteWindow:
    entry = GldGazetteEntry(
        stable_identity="gld-gazette-2026-0001",
        gazette_class=GldGazetteClass.LEGAL_SUPPLEMENT_1,
        issue_kind=GldGazetteIssueKind.ORDINARY,
        publication_date="2026-09-04",
        artifact_endpoint_id="sep_00000000000000000000000000000000000000000000003d",
        artifact_endpoint_version="1.0.0",
        source_profile_version="1.1.0",
        register_version="2026-08-28.3",
        register_fingerprint=_REGISTER_FINGERPRINT,
        artifact_locator="issued/2026/0001",
    )
    body = {
        "source_id": "HK-LEG-GLD-EGAZETTE",
        "endpoint_id": "sep_00000000000000000000000000000000000000000000003b",
        "endpoint_version": "1.0.0",
        "source_profile_version": "1.1.0",
        "register_version": "2026-08-28.3",
        "register_fingerprint": _REGISTER_FINGERPRINT,
        "start_date": "2026-09-04",
        "end_date": "2026-09-04",
        "language": "BILINGUAL",
        "observation_cutoff": observation_cutoff,
        "entries": [
            {
                "stable_identity": entry.stable_identity,
                "gazette_class": entry.gazette_class.value,
                "issue_kind": entry.issue_kind.value,
                "publication_date": entry.publication_date,
                "artifact_endpoint_id": entry.artifact_endpoint_id,
                "artifact_endpoint_version": entry.artifact_endpoint_version,
                "source_profile_version": entry.source_profile_version,
                "register_version": entry.register_version,
                "register_fingerprint": entry.register_fingerprint,
                "artifact_locator": entry.artifact_locator,
            }
        ],
    }
    raw = GldGazetteWindow(
        source_id="HK-LEG-GLD-EGAZETTE",
        endpoint_id="sep_00000000000000000000000000000000000000000000003b",
        endpoint_version="1.0.0",
        source_profile_version="1.1.0",
        register_version="2026-08-28.3",
        register_fingerprint=_REGISTER_FINGERPRINT,
        start_date="2026-09-04",
        end_date="2026-09-04",
        language="BILINGUAL",
        observation_cutoff=observation_cutoff,
        entries=(entry,),
        listing_fingerprint=(
            "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()
        ),
    )
    request = GldSessionRequest(
        raw.source_id,
        raw.endpoint_id,
        raw.endpoint_version,
        raw.source_profile_version,
        raw.register_version,
        raw.register_fingerprint,
        raw.start_date,
        raw.end_date,
        raw.language,
        raw.observation_cutoff,
    )
    grant = GldSessionGrant(
        "gld-session-task5",
        "2026-09-03T23:59:00+00:00",
        "2026-09-04T00:01:00+00:00",
        "egazette.gld.gov.hk",
        "sha256:" + "e" * 64,
    )

    class Exchange:
        @staticmethod
        def enumerate_window(
            supplied_grant: GldSessionGrant,
            supplied_request: GldSessionRequest,
        ) -> GldGazetteWindow:
            assert supplied_grant is grant
            assert supplied_request is request
            return raw

        @staticmethod
        def fetch_artifact(
            _grant: GldSessionGrant,
            _entry: GldGazetteEntry,
        ) -> object:
            raise AssertionError

    return enumerate_gld_gazette_window(Exchange(), grant, request)


def _seeds(window: GldGazetteWindow | None = None) -> tuple[LegislationWorkSeed, ...]:
    return registered_legislation_work_seeds(window or _gld_window())


@pytest.fixture(scope="module")
def authentic_import(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[RetainedImportReceipt, AcquisitionCycleReport]:
    """Run the real Task 4 HKeL import and expose its exact journal projection."""
    repository_root = Path(__file__).resolve().parents[3]
    report_path = (
        repository_root
        / "var/hk-v1/source-admission/hkel-attempt-b/attempts"
        / "hkel-live-baseline-basic-law20-20260828b/report.json"
    )
    reference = RetainedReportReference(
        report_path=report_path,
        expected_report_fingerprint=(
            "sha256:5f6b8625fd7c0ff4093d96b7a2f72e4ededc9b8af54b6c1add02b95e81549b50"
        ),
        expected_authority_manifest_fingerprint=(
            "sha256:ef67b8dd0a6f00d23ca4ec1e8ac157d3fdd6423bf88dbd4f6b4346c0df296c66"
        ),
        expected_execution_authorization_fingerprint=(
            "sha256:4d43ac6c66e938777942d4d09e22de05542d065a39b34f6c2c2a4c48ced9ad88"
        ),
        product_family="LEGISLATION",
        cycle_id="cyc_20260903_import_hkel",
        expected_source_result="COMPLETE",
        expected_imported_item_count=56,
    )
    state_root = tmp_path_factory.mktemp("task5-hkel-import")
    receipt = import_retained_report(state_root, reference)
    with LocalAcquisitionJournal(state_root, reference.cycle_id) as journal:
        checkpoint = journal.load_checkpoint()
    report = _valid_report(
        AcquisitionCycleReport(
            reference.cycle_id,
            AcquisitionCycleResult.COMPLETE,
            checkpoint.items,
            0,
            0,
            receipt.journal_head_fingerprint,
            "",
        )
    )
    return receipt, report


@pytest.fixture(scope="module")
def authentic_baseline(
    authentic_import: tuple[RetainedImportReceipt, AcquisitionCycleReport],
) -> HkelImportedBaseline:
    """Bind the authentic Task 4 import and full-body admission into Task 5."""
    receipt, report = authentic_import
    return bind_imported_hkel_baseline(receipt, report, _admission_document())


def _report(
    graph: LegislationWorkGraph, transitions: dict[str, JournalTransition]
) -> AcquisitionCycleReport:
    items = tuple(
        CheckpointItem(
            node.scheduled.identity.work_item_id,
            index,
            transitions.get(node.stable_key, JournalTransition.CAPTURED_VERIFIED),
            (
                0
                if transitions.get(node.stable_key) is JournalTransition.IMPORTED_CAPTURE_VERIFIED
                else 1
            ),
            (
                f"retained/{node.stable_key}"
                if transitions.get(node.stable_key, JournalTransition.CAPTURED_VERIFIED)
                in {
                    JournalTransition.CAPTURED_VERIFIED,
                    JournalTransition.IMPORTED_CAPTURE_VERIFIED,
                }
                else None
            ),
            (
                "2026-09-04T01:00:00+00:00"
                if transitions.get(node.stable_key) is JournalTransition.RETRYABLE_FAILURE
                else None
            ),
        )
        for index, node in enumerate(graph.nodes, start=1)
    )
    result = (
        AcquisitionCycleResult.INCOMPLETE_RETRYABLE
        if JournalTransition.RETRYABLE_FAILURE in transitions.values()
        else AcquisitionCycleResult.COMPLETE
    )
    provisional = AcquisitionCycleReport(graph.cycle_id, result, items, 0, 0, _HEAD, "")
    body = provisional.to_json()
    del body["fingerprint"]
    return replace(
        provisional,
        fingerprint="sha256:" + sha256(canonicalize(body)).hexdigest(),
    )


def _valid_report(report: AcquisitionCycleReport) -> AcquisitionCycleReport:
    provisional = replace(report, fingerprint="")
    body = provisional.to_json()
    del body["fingerprint"]
    return replace(
        provisional,
        fingerprint="sha256:" + sha256(canonicalize(body)).hexdigest(),
    )


def _reseal_graph(graph: LegislationWorkGraph) -> LegislationWorkGraph:
    window = graph.gld_window
    body = {
        "cycle_id": graph.cycle_id,
        "observation_cutoff": graph.observation_cutoff,
        "gld_window": {
            "source_id": window.source_id,
            "endpoint_id": window.endpoint_id,
            "endpoint_version": window.endpoint_version,
            "source_profile_version": window.source_profile_version,
            "register_version": window.register_version,
            "register_fingerprint": window.register_fingerprint,
            "start_date": window.start_date,
            "end_date": window.end_date,
            "language": window.language,
            "observation_cutoff": window.observation_cutoff,
            "entries": [
                {
                    "stable_identity": entry.stable_identity,
                    "gazette_class": entry.gazette_class.value,
                    "issue_kind": entry.issue_kind.value,
                    "publication_date": entry.publication_date,
                    "artifact_endpoint_id": entry.artifact_endpoint_id,
                    "artifact_endpoint_version": entry.artifact_endpoint_version,
                    "source_profile_version": entry.source_profile_version,
                    "register_version": entry.register_version,
                    "register_fingerprint": entry.register_fingerprint,
                    "artifact_locator": entry.artifact_locator,
                }
                for entry in window.entries
            ],
            "listing_fingerprint": window.listing_fingerprint,
        },
        "nodes": [
            {
                "stable_key": node.stable_key,
                "kind": node.kind.value,
                "scope_ids": list(node.scope_ids),
                "dependency_keys": list(node.dependency_keys),
                "work_item": node.scheduled.identity.to_json(),
                "priority": list(node.scheduled.priority),
                "host": node.scheduled.host,
                "source_id": node.source_id,
                "endpoint_id": node.endpoint_id,
                "source_register_fingerprint": node.source_register_fingerprint,
                "source_input_fingerprint": node.source_input_fingerprint,
            }
            for node in graph.nodes
        ],
    }
    return replace(
        graph,
        fingerprint="sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest(),
    )


def _reseal_manifest(
    result: LegislationAcquisitionManifest,
) -> LegislationAcquisitionManifest:
    body = {
        "schema_id": "asklegal.legislation-acquisition-manifest",
        "schema_version": "1.0.0",
        "cycle_id": result.cycle_id,
        "observation_cutoff": result.observation_cutoff,
        "scope_dispositions": [item.to_json() for item in result.scope_dispositions],
        "verified_item_refs": list(result.verified_item_refs),
        "review_issue_refs": list(result.review_issue_refs),
        "journal_head_fingerprint": result.journal_head_fingerprint,
        "source_register_fingerprint": result.source_register_fingerprint,
        "source_baseline_fingerprint": result.source_baseline_fingerprint,
        "work_plan_fingerprint": result.work_plan_fingerprint,
        "result": result.result.value,
    }
    return replace(
        result,
        fingerprint="sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest(),
    )


def _verified(
    graph: LegislationWorkGraph, *, changed: frozenset[str] = frozenset()
) -> tuple[LegislationVerifiedItem, ...]:
    return tuple(
        LegislationVerifiedItem.issue(
            stable_key=node.stable_key,
            object_ref=f"retained/{node.stable_key}",
            content_fingerprint="sha256:" + ("b" if node.stable_key in changed else "a") * 64,
        )
        for node in graph.nodes
    )


def _accepted_state(
    manifest: LegislationAcquisitionManifest,
) -> LegislationAcceptedSourceState:
    store = InMemoryAcquisitionRegister()
    record = AcquisitionObservationRecord(
        observation_id=f"observation-{manifest.cycle_id}",
        input_fingerprint=manifest.fingerprint,
        source_id="HK-LEG-HKEL-CURRENT-INVENTORY",
        endpoint_id="sep_000000000000000000000000000000000000000000000001",
        observation_cutoff=manifest.observation_cutoff,
        watcher_result="POSSIBLE_CHANGE",
        scraper_result="SNAPSHOT_PRESERVED",
        disposition="SNAPSHOT_PRESERVED",
        consequence="LEGAL_PROCESSING_ELIGIBLE",
        evidence_package_id=f"evidence-{manifest.cycle_id}",
        primary_manifest_version=f"primary-{manifest.fingerprint}",
        recovery_manifest_version=f"recovery-{manifest.fingerprint}",
        manifest_fingerprint=manifest.fingerprint,
        source_snapshot_id=f"snapshot-{manifest.cycle_id}",
        issue_id="",
    )
    stored = store.record_observation(record)
    assert stored == record
    return load_accepted_legislation_source_state(manifest, store, record.observation_id)


def test_work_graph_contains_every_required_source_class_and_is_order_stable() -> None:
    """Input order cannot alter graph identity or omit a required source class."""
    first = build_legislation_work_graph(_CYCLE_A, _CUTOFF, tuple(reversed(_seeds())))
    second = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())

    assert first == second
    assert {node.kind for node in first.nodes} == set(LegislationWorkKind)
    assert {scope for node in first.nodes for scope in node.scope_ids} == set(LEGISLATION_SCOPE_IDS)
    assert tuple(node.stable_key for node in first.nodes) == tuple(
        sorted(node.stable_key for node in first.nodes)
    )
    assert first.fingerprint.startswith("sha256:")


def test_arbitrary_https_seed_set_has_no_registered_graph_authority() -> None:
    """Syntactically valid foreign roles and URLs cannot enter a family graph."""
    with pytest.raises(ValueError, match="LEGISLATION_WORK_SEED_NOT_REGISTERED"):
        build_legislation_work_graph(_CYCLE_A, _CUTOFF, _arbitrary_seeds())


def test_fabricated_count_only_retained_profile_cannot_authorize_baseline() -> None:
    """Self-consistent counts and journal rows are not an authentic Task 4 receipt."""
    receipt = RetainedImportReceipt(
        "HKEL",
        "sha256:" + "1" * 64,
        56,
        2_892_060_128,
        _HEAD,
        12_858,
        3_157,
        7,
        "sha256:" + "9" * 64,
        None,
    )
    report = _valid_report(
        AcquisitionCycleReport(
            "cyc_20260903_import_hkel",
            AcquisitionCycleResult.COMPLETE,
            tuple(
                CheckpointItem(
                    f"awi_{index:064x}",
                    index,
                    JournalTransition.IMPORTED_CAPTURE_VERIFIED,
                    0,
                    f"objects/{index:064x}.bin",
                    None,
                )
                for index in range(1, 57)
            ),
            0,
            0,
            _HEAD,
            "",
        )
    )

    with pytest.raises(ValueError, match="HKEL_IMPORTED_BASELINE_INVALID"):
        bind_imported_hkel_baseline(receipt, report, _admission_document())


def test_authentic_task4_import_binds_exact_lineage_and_reused_bytes(
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """The positive baseline is the real imported bytes/journal lineage, not counts."""
    assert len(authentic_baseline.imported_work_item_ids) == 56
    assert authentic_baseline.archive_member_count == 12_858
    assert authentic_baseline.bilingual_pair_count == 3_157
    assert authentic_baseline.publication_specification_count == 7
    assert authentic_baseline.import_cycle_id == "cyc_20260903_import_hkel"
    assert authentic_baseline.source_attempt_id == "hkel-live-baseline-basic-law20-20260828b"
    assert authentic_baseline.receipt_fingerprint.startswith("sha256:")
    assert authentic_baseline.work_item_lineage_fingerprint.startswith("sha256:")
    assert len(authentic_baseline.archive_object_references) == 12
    assert tuple(
        (item.endpoint_id, item.content_fingerprint)
        for item in authentic_baseline.archive_object_references
    ) == tuple(
        (item.archive_endpoint_id, item.archive_fingerprint)
        for item in authentic_baseline.archive_reuse_keys
    )


def test_unchanged_imported_archives_seed_cycle_without_transport(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """Verified Task 4 archive refs resume as imports and cause no source request."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    archive_keys = {
        node.stable_key
        for node in graph.nodes
        if node.kind is LegislationWorkKind.HKEL_CURRENT_ARCHIVE
    }
    transport = _CycleTransport(graph, frozenset(), retry_gld_once=False)
    clock = _ActivityClock()

    cycle = run_legislation_acquisition_cycle(
        state_root=tmp_path / "seed-imported-archives",
        graph=graph,
        transport=transport,
        retained_verifier=_ActivityVerifier(),
        clock=clock,
        sleeper=clock.sleep,
        budget=CycleBudget(100, 100_000_000_000, 60, 1_000),
        baseline=authentic_baseline,
        archive_admission=_AdmitChangedHkelArchives(),
        review_issue_refs=(),
    )

    assert archive_keys.isdisjoint(transport.verified)
    assert {
        item.transition
        for item in cycle.report.item_dispositions
        if item.work_item_id
        in {
            node.scheduled.identity.work_item_id
            for node in graph.nodes
            if node.kind is LegislationWorkKind.HKEL_CURRENT_ARCHIVE
        }
    } == {JournalTransition.IMPORTED_CAPTURE_VERIFIED}


def test_publication_specification_change_readmits_affected_archives(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """A specification change invalidates retained archive parsing before manifesting."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    changed_spec = next(
        node.stable_key
        for node in graph.nodes
        if node.kind is LegislationWorkKind.HKEL_PUBLICATION_SPECIFICATION
    )
    archive_fingerprints = {
        node.stable_key: next(
            item.archive_fingerprint
            for item in authentic_baseline.archive_reuse_keys
            if item.archive_endpoint_id == node.endpoint_id
        )
        for node in graph.nodes
        if node.kind is LegislationWorkKind.HKEL_CURRENT_ARCHIVE
    }
    transport = _CycleTransport(
        graph,
        frozenset({changed_spec}),
        retry_gld_once=False,
        base_fingerprints=archive_fingerprints,
    )
    admission = _AdmitChangedHkelArchives()
    clock = _ActivityClock()

    run_legislation_acquisition_cycle(
        state_root=tmp_path / "spec-change-readmission",
        graph=graph,
        transport=transport,
        retained_verifier=_ActivityVerifier(),
        clock=clock,
        sleeper=clock.sleep,
        budget=CycleBudget(100, 100_000_000_000, 60, 1_000),
        baseline=authentic_baseline,
        archive_admission=admission,
        review_issue_refs=(),
        observed_archive_reuse_keys=tuple(
            HkelArchiveReuseKey.issue(
                item.archive_endpoint_id,
                item.archive_fingerprint,
                "sha256:" + "c" * 64,
            )
            for item in authentic_baseline.archive_reuse_keys
        ),
    )

    assert tuple(sorted(call[0] for call in admission.calls)) == tuple(
        item.archive_endpoint_id for item in authentic_baseline.archive_reuse_keys
    )


def test_changed_archive_records_current_cycle_provenance_not_task4_claims(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """A fresh capture cannot inherit Task 4 attempt or authority provenance."""
    graph = build_legislation_work_graph(_CYCLE_B, _CUTOFF, _seeds())
    changed = next(
        node for node in graph.nodes if node.kind is LegislationWorkKind.HKEL_CURRENT_ARCHIVE
    )
    observed = tuple(
        HkelArchiveReuseKey.issue(
            item.archive_endpoint_id,
            "sha256:" + "b" * 64
            if item.archive_endpoint_id == changed.endpoint_id
            else item.archive_fingerprint,
            item.publication_profile_fingerprint,
        )
        for item in authentic_baseline.archive_reuse_keys
    )
    clock = _ActivityClock()
    cycle = run_legislation_acquisition_cycle(
        state_root=tmp_path / "current-provenance",
        graph=graph,
        transport=_CycleTransport(graph, frozenset({changed.stable_key}), retry_gld_once=False),
        retained_verifier=_ActivityVerifier(),
        clock=clock,
        sleeper=clock.sleep,
        budget=CycleBudget(100, 100_000_000_000, 60, 1_000),
        baseline=authentic_baseline,
        archive_admission=_AdmitChangedHkelArchives(),
        review_issue_refs=(),
        observed_archive_reuse_keys=observed,
    )
    current = next(
        item
        for item in cycle.baseline.archive_object_references
        if item.endpoint_id == changed.endpoint_id
    )
    prior = next(
        item
        for item in authentic_baseline.archive_object_references
        if item.endpoint_id == changed.endpoint_id
    )

    assert current.provenance_kind is HkelArchiveProvenanceKind.CURRENT_CYCLE_CAPTURE
    assert current.source_cycle_id == _CYCLE_B
    assert current.source_attempt_id == f"runner-{_CYCLE_B}"
    assert current.source_report_fingerprint == cycle.report.fingerprint
    assert current.authority_manifest_fingerprint == graph.fingerprint
    assert current.execution_authorization_fingerprint == cycle.report.fingerprint
    assert current.source_journal_head_fingerprint == cycle.report.journal_head_fingerprint
    assert (
        current.source_attempt_id,
        current.source_report_fingerprint,
        current.authority_manifest_fingerprint,
        current.execution_authorization_fingerprint,
    ) != (
        prior.source_attempt_id,
        prior.source_report_fingerprint,
        prior.authority_manifest_fingerprint,
        prior.execution_authorization_fingerprint,
    )


def test_restored_baseline_rejects_current_label_with_copied_task4_provenance(
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """Resealing cannot relabel an old Task 4 reference as a current capture."""
    document = hkel_baseline_to_json(authentic_baseline)
    references = document["archive_object_references"]
    assert type(references) is list
    first = references[0]
    assert type(first) is dict
    first["provenance_kind"] = "CURRENT_CYCLE_CAPTURE"
    body = {
        key: value
        for key, value in document.items()
        if key not in {"schema_id", "schema_version", "fingerprint"}
    }
    document["fingerprint"] = "sha256:" + sha256(canonicalize(checked_json_value(body))).hexdigest()

    with pytest.raises(ValueError, match="HKEL_IMPORTED_BASELINE_INVALID"):
        restore_hkel_baseline(document, authentic_baseline)


def test_authentic_receipt_rejects_a_resealed_foreign_checkpoint_projection(
    authentic_import: tuple[RetainedImportReceipt, AcquisitionCycleReport],
) -> None:
    """Authentic IDs/head cannot bless a caller-replaced imported journal projection."""
    receipt, report = authentic_import
    first, second, *remaining = report.item_dispositions
    forged = _valid_report(
        replace(
            report,
            item_dispositions=(
                replace(first, object_ref=second.object_ref),
                second,
                *remaining,
            ),
            fingerprint="",
        )
    )

    with pytest.raises(ValueError, match="HKEL_IMPORTED_BASELINE_INVALID"):
        bind_imported_hkel_baseline(receipt, forged, _admission_document())


def test_authentic_receipt_rejects_resealed_foreign_archive_hashes_and_review_omissions(
    authentic_import: tuple[RetainedImportReceipt, AcquisitionCycleReport],
) -> None:
    """A self-hash cannot replace evidence-derived archive or review facts."""
    receipt, report = authentic_import

    def replace_archive(document: dict[str, JsonValue]) -> None:
        raw_keys = document["archive_reuse_keys"]
        assert type(raw_keys) is list
        assert type(raw_keys[0]) is dict
        key = raw_keys[0]
        key["archive_fingerprint"] = "sha256:" + "f" * 64
        key_body = {name: value for name, value in key.items() if name != "fingerprint"}
        key["fingerprint"] = "sha256:" + sha256(canonicalize(key_body)).hexdigest()

    def omit_review(document: dict[str, JsonValue]) -> None:
        raw_reviews = document["review_issue_refs"]
        assert type(raw_reviews) is list
        document["review_issue_refs"] = raw_reviews[:-1]

    for forged in (_reseal_admission(replace_archive), _reseal_admission(omit_review)):
        with pytest.raises(ValueError, match="HKEL_IMPORTED_BASELINE_INVALID"):
            bind_imported_hkel_baseline(receipt, report, forged)


def test_work_graph_rejects_a_missing_class_and_unknown_dependency() -> None:
    """Incomplete membership and dangling dependencies fail before scheduling."""
    with pytest.raises(ValueError, match="LEGISLATION_WORK_GRAPH_INCOMPLETE"):
        build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds()[:-1])

    bad = replace(_seeds()[-1], dependency_keys=("not-present",))
    with pytest.raises(ValueError, match="LEGISLATION_WORK_DEPENDENCY_INVALID"):
        build_legislation_work_graph(_CYCLE_A, _CUTOFF, (*_seeds()[:-1], bad))


def test_graph_revalidation_requires_all_seven_publication_specifications() -> None:
    """One surviving spec node cannot conceal omission of another required spec."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    omitted = next(
        node
        for node in graph.nodes
        if node.kind is LegislationWorkKind.HKEL_PUBLICATION_SPECIFICATION
    )
    remaining = tuple(node for node in graph.nodes if node is not omitted)
    reindexed = tuple(
        replace(
            node,
            scheduled=replace(
                node.scheduled,
                priority=(tuple(LegislationWorkKind).index(node.kind), index, node.stable_key),
            ),
        )
        for index, node in enumerate(remaining)
    )
    forged = _reseal_graph(replace(graph, nodes=reindexed))

    with pytest.raises(ValueError, match="LEGISLATION_WORK_GRAPH_INVALID"):
        legislation_runner_dependencies(forged)


def test_graph_revalidation_reproduces_gld_projection_and_dependency() -> None:
    """A new outer hash cannot rewrite or detach an admitted GLD artifact row."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    artifact = next(
        node for node in graph.nodes if node.kind is LegislationWorkKind.GLD_EVENT_ARTIFACT
    )
    without_discovery = _reseal_graph(
        replace(
            graph,
            nodes=tuple(
                replace(node, dependency_keys=()) if node is artifact else node
                for node in graph.nodes
            ),
        )
    )
    with pytest.raises(ValueError, match="LEGISLATION_WORK_GRAPH_INVALID"):
        legislation_runner_dependencies(without_discovery)

    identity = artifact.scheduled.identity
    foreign_locator = identity.locator.rsplit("/", maxsplit=1)[0] + "/foreign-artifact.pdf"
    foreign_identity = WorkItemIdentity.issue(
        source_family=identity.source_family,
        source_role=identity.source_role,
        cycle_id=identity.cycle_id,
        observation_cutoff=identity.observation_cutoff,
        procedure_version=identity.procedure_version,
        locator=foreign_locator,
        stage=identity.stage,
        parent_id=identity.parent_id,
        media_type=identity.media_type,
        max_bytes=identity.max_bytes,
    )
    foreign_node = replace(
        artifact,
        scheduled=replace(artifact.scheduled, identity=foreign_identity),
        source_input_fingerprint="sha256:" + "f" * 64,
    )
    foreign = _reseal_graph(
        replace(
            graph,
            nodes=tuple(foreign_node if node is artifact else node for node in graph.nodes),
        )
    )
    with pytest.raises(ValueError, match="LEGISLATION_WORK_GRAPH_INVALID"):
        legislation_runner_dependencies(foreign)


@pytest.mark.parametrize(
    "kind",
    [LegislationWorkKind.HKEL_CURRENT_ARCHIVE, LegislationWorkKind.ANNEX_III],
)
def test_graph_revalidation_reproduces_every_factory_dependency(
    kind: LegislationWorkKind,
) -> None:
    """Resealing cannot erase archive/inventory or constitutional prerequisites."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    target = next(node for node in graph.nodes if node.kind is kind)
    assert target.dependency_keys
    forged = _reseal_graph(
        replace(
            graph,
            nodes=tuple(
                replace(node, dependency_keys=()) if node is target else node
                for node in graph.nodes
            ),
        )
    )

    with pytest.raises(ValueError, match="LEGISLATION_WORK_GRAPH_INVALID"):
        legislation_runner_dependencies(forged)


def test_registered_graph_rejects_copied_self_hashed_gld_window() -> None:
    """Only the live listing returned by the admitted exchange can authorize seeds."""
    issued = _gld_window()
    copied = replace(issued)

    with pytest.raises(ValueError, match="LEGISLATION_GLD_WINDOW_NOT_ISSUED"):
        registered_legislation_work_seeds(copied)


def test_graph_revalidation_rejects_resealed_nested_identity_and_cycle() -> None:
    """A new outer hash cannot detach node identity or create a dependency cycle."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    node = graph.nodes[0]
    identity = node.scheduled.identity
    foreign = WorkItemIdentity.issue(
        source_family="CASES",
        source_role=identity.source_role,
        cycle_id=identity.cycle_id,
        observation_cutoff=identity.observation_cutoff,
        procedure_version=identity.procedure_version,
        locator=identity.locator,
        stage=identity.stage,
        parent_id=identity.parent_id,
        media_type=identity.media_type,
        max_bytes=identity.max_bytes,
    )
    replaced_node = replace(node, scheduled=replace(node.scheduled, identity=foreign))
    replaced_graph = _reseal_graph(replace(graph, nodes=(replaced_node, *graph.nodes[1:])))
    with pytest.raises(ValueError, match="LEGISLATION_WORK_GRAPH_INVALID"):
        legislation_runner_dependencies(replaced_graph)

    left, right, *remaining = graph.nodes
    cyclic = _reseal_graph(
        replace(
            graph,
            nodes=tuple(
                sorted(
                    (
                        replace(left, dependency_keys=(right.stable_key,)),
                        replace(right, dependency_keys=(left.stable_key,)),
                        *remaining,
                    ),
                    key=lambda item: item.stable_key,
                )
            ),
        )
    )
    with pytest.raises(ValueError, match="LEGISLATION_WORK_GRAPH_INVALID"):
        legislation_runner_dependencies(cyclic)


@pytest.mark.parametrize(
    ("field", "foreign_value"),
    [
        ("source_family", "CASES"),
        ("source_role", "HK_LEG_FOREIGN_ROLE"),
        ("cycle_id", "cyc_foreign_legislation"),
        ("observation_cutoff", "2026-09-03T00:00:00+00:00"),
        ("stage", "FOREIGN_STAGE"),
        ("parent_id", "foreign-parent"),
    ],
)
def test_graph_revalidation_binds_each_nested_identity_fact_to_its_node(
    field: str,
    foreign_value: str,
) -> None:
    """A coherently reissued identity cannot replace any enclosing graph fact."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    node = graph.nodes[0]
    identity = node.scheduled.identity
    foreign = WorkItemIdentity.issue(
        source_family=(foreign_value if field == "source_family" else identity.source_family),
        source_role=(foreign_value if field == "source_role" else identity.source_role),
        cycle_id=(foreign_value if field == "cycle_id" else identity.cycle_id),
        observation_cutoff=(
            foreign_value if field == "observation_cutoff" else identity.observation_cutoff
        ),
        procedure_version=identity.procedure_version,
        locator=identity.locator,
        stage=(foreign_value if field == "stage" else identity.stage),
        parent_id=(foreign_value if field == "parent_id" else identity.parent_id),
        media_type=identity.media_type,
        max_bytes=identity.max_bytes,
    )
    replaced_node = replace(node, scheduled=replace(node.scheduled, identity=foreign))
    replaced_graph = _reseal_graph(replace(graph, nodes=(replaced_node, *graph.nodes[1:])))

    with pytest.raises(ValueError, match="LEGISLATION_WORK_GRAPH_INVALID"):
        legislation_runner_dependencies(replaced_graph)


@pytest.mark.parametrize("schedule_field", ["priority", "not_before"])
def test_graph_revalidation_binds_priority_and_initial_eligibility(
    schedule_field: str,
) -> None:
    """A re-sealed node cannot rewrite runner order or initial eligibility."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    node = graph.nodes[0]
    scheduled = (
        replace(node.scheduled, priority=(99, 99, node.stable_key))
        if schedule_field == "priority"
        else replace(node.scheduled, not_before_monotonic_ns=1)
    )
    replaced_node = replace(node, scheduled=scheduled)
    replaced_graph = _reseal_graph(replace(graph, nodes=(replaced_node, *graph.nodes[1:])))

    with pytest.raises(ValueError, match="LEGISLATION_WORK_GRAPH_INVALID"):
        legislation_runner_dependencies(replaced_graph)


def test_registered_legislation_activity_runs_gld_projection_and_dependencies(
    tmp_path: Path,
) -> None:
    """The V1 activity core uses the shared runner and classifies GLD session retry."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    discovery = next(
        node for node in graph.nodes if node.kind is LegislationWorkKind.GLD_ISSUE_DISCOVERY
    )
    artifact = next(
        node for node in graph.nodes if node.kind is LegislationWorkKind.GLD_EVENT_ARTIFACT
    )
    clock = _ActivityClock()
    transport = _OfflineLegislationTransport(discovery.scheduled.identity.work_item_id)

    report = run_legislation_resumable_graph(
        state_root=tmp_path / "state",
        graph=graph,
        transport=transport,
        retained_verifier=_ActivityVerifier(),
        clock=clock,
        sleeper=clock.sleep,
        budget=CycleBudget(100, 100_000_000_000, 60, 1_000),
    )

    assert report.result is AcquisitionCycleResult.COMPLETE
    assert transport.discovery_attempts == 2
    assert transport.calls.index(artifact.scheduled.identity.work_item_id) > max(
        index
        for index, work_id in enumerate(transport.calls)
        if work_id == discovery.scheduled.identity.work_item_id
    )


def test_registered_activity_can_complete_every_role_from_admitted_local_outcomes(
    tmp_path: Path,
) -> None:
    """The service transport can consume injected admitted outcomes for all graph roles."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    admitted = _AdmittedGraphOutcomePort()
    activities = object.__new__(AcquisitionActivities)
    object.__setattr__(activities, "_legislation_admitted_outcomes", admitted)
    clock = _ActivityClock()

    report = run_legislation_resumable_graph(
        state_root=tmp_path / "registered-admitted",
        graph=graph,
        transport=v1_pipeline.V1LegislationTransport(activities, graph),
        retained_verifier=_ActivityVerifier(),
        clock=clock,
        sleeper=clock.sleep,
        budget=CycleBudget(100, 100_000_000_000, 60, 1_000),
    )

    assert report.result is AcquisitionCycleResult.COMPLETE
    assert tuple(sorted(admitted.calls)) == tuple(node.stable_key for node in graph.nodes)


def test_generic_activity_rejects_serialized_legislation_graph_before_any_effect(
    tmp_path: Path,
) -> None:
    """Serialized GLD fields cannot bypass the in-process issued-window boundary."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())

    class ExplodingAdmittedOutcomes:
        @staticmethod
        def capture(node: LegislationWorkNode) -> CaptureOutcome:
            del node
            message = "serialized legislation graph reached transport"
            raise AssertionError(message)

    class ExplodingVault:
        def __getattr__(self, name: str) -> object:
            message = f"serialized legislation graph reached verifier/vault: {name}"
            raise AssertionError(message)

    state_root = tmp_path / "generic-legislation-rejected"
    activities = object.__new__(AcquisitionActivities)
    object.__setattr__(activities, "_cycle_state_root", state_root)
    object.__setattr__(activities, "_vault", ExplodingVault())
    object.__setattr__(activities, "_legislation_admitted_outcomes", ExplodingAdmittedOutcomes())
    payload = {
        "source_family": "LEGISLATION",
        "graph": graph.to_json(),
        "budget": {
            "maximum_starts": 100,
            "maximum_retained_bytes": 1_000,
            "maximum_elapsed_seconds": 100,
            "maximum_redirects": 10,
        },
    }

    with pytest.raises(AcquisitionPipelineError, match="resumable acquisition payload is invalid"):
        activities.run_resumable_acquisition(ActivityContext("test", 1), payload)
    assert not state_root.exists()


@pytest.mark.parametrize(
    "archive_body",
    [
        _hkel_archive((("readme.txt", b"not legislation xml"),)),
        _hkel_archive(
            (
                (
                    "cap_1_en_c/cap_1_20260904000000_en_c.xml",
                    b'<lawDoc xmlns="urn:not-hkel"/>',
                ),
            )
        ),
        _hkel_archive(
            (
                ("cap_1_en_c/cap_1_20260904000000_en_c.xml", _valid_hkel_xml()),
                ("cap_1_en_c/payload.bin", b"arbitrary binary"),
            )
        ),
        _hkel_archive(
            (
                (
                    "cap_1_en_c/cap_1_20260904000000_en_c.xml",
                    b'<?xml version="1.0" encoding="UTF-8"?>'
                    + b" " * 5_001
                    + b"<!DOCTYPE lawDoc>"
                    + _valid_hkel_xml().split(b"?>", 1)[1],
                ),
            ),
            compression=ZIP_STORED,
        ),
    ],
    ids=("text-only", "foreign-namespace", "xml-plus-junk", "late-doctype"),
)
def test_primary_vault_archive_admission_rejects_non_authentic_hkel_shapes(
    archive_body: bytes,
) -> None:
    """A safe generic ZIP is not an authentic HKeL current-data archive."""
    fingerprint = f"sha256:{sha256(archive_body).hexdigest()}"

    class Vault:
        @staticmethod
        def resolve_current(object_ref: str) -> object:
            assert object_ref == "captured/current-archive"
            return object()

        @staticmethod
        def read_exact(_reference: object) -> bytes:
            return archive_body

    admission = v1_pipeline.PrimaryVaultHkelArchiveAdmission(Vault())

    assert (
        admission.admit_archive(
            source_role="HK_LEG_HKEL_CURRENT_DATA",
            endpoint_id="sep_00000000000000000000000000000000000000000000000a",
            object_ref="captured/current-archive",
            content_fingerprint=fingerprint,
        )
        is False
    )


def test_primary_vault_archive_admission_reads_and_parses_valid_hkel_xml() -> None:
    """A registered archive containing exact HKLM XML crosses the concrete port."""
    archive_body = _hkel_archive((("cap_1_en_c/cap_1_20260904000000_en_c.xml", _valid_hkel_xml()),))
    fingerprint = f"sha256:{sha256(archive_body).hexdigest()}"

    class Vault:
        @staticmethod
        def resolve_current(_object_ref: str) -> object:
            return object()

        @staticmethod
        def read_exact(_reference: object) -> bytes:
            return archive_body

    admission = v1_pipeline.PrimaryVaultHkelArchiveAdmission(Vault())

    assert admission.admit_archive(
        source_role="HK_LEG_HKEL_CURRENT_DATA",
        endpoint_id="sep_00000000000000000000000000000000000000000000000a",
        object_ref="captured/current-archive",
        content_fingerprint=fingerprint,
    )


def test_hkel_archive_admission_accepts_publisher_backslash_member_spelling() -> None:
    """Publisher backslash members normalize only to their exact canonical member name."""
    archive_body = _hkel_archive(
        ((r"cap_100_en_c\cap_100_19970630000000_en_c.xml", _valid_hkel_xml()),)
    )

    admitted = admit_hkel_current_archive(
        endpoint_id="sep_00000000000000000000000000000000000000000000000a",
        source_role="HK_LEG_HKEL_CURRENT_DATA",
        content_fingerprint=f"sha256:{sha256(archive_body).hexdigest()}",
        body=archive_body,
    )

    assert admitted.member_count == 1


def test_registered_activity_emits_canonical_manifest_from_live_task4_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    authentic_import: tuple[RetainedImportReceipt, AcquisitionCycleReport],
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """The service entry binds baseline, graph, runner, and manifest without JSON reissuance."""
    receipt, report = authentic_import
    admitted = _AdmittedGraphOutcomePort()
    archive_admission = _AdmitChangedHkelArchives()

    class Inputs:
        @staticmethod
        def load(cycle_id: str, observation_cutoff: str) -> LegislationProductionCycleInputs:
            assert cycle_id == _CYCLE_A
            assert observation_cutoff == _CUTOFF
            return LegislationProductionCycleInputs(
                _gld_window(),
                receipt,
                report,
                _admission_document(),
                authentic_baseline.archive_reuse_keys,
                archive_admission,
                (),
            )

    class Credential:
        @staticmethod
        def reveal() -> bytes:
            return b"http://127.0.0.1:8080"

    infrastructure = SimpleNamespace(
        source_egress_proxy_credential=Credential(),
        primary_vault=object(),
        due_cycle_state_root=(tmp_path / "activity-manifest").resolve(),
    )
    activities = v1_pipeline.build_activities(
        cast("V1AcquisitionInfrastructure", infrastructure),
        {},
        legislation_admitted_outcomes=admitted,
        legislation_production_inputs=Inputs(),
    )
    monkeypatch.setattr(
        v1_pipeline,
        "_PrimaryVaultRetainedVerifier",
        _test_retained_verifier,
    )
    payload = {
        "source_family": "LEGISLATION",
        "cycle_id": _CYCLE_A,
        "observation_cutoff": _CUTOFF,
        "budget": {
            "maximum_starts": 100,
            "maximum_retained_bytes": 100_000_000_000,
            "maximum_elapsed_seconds": 60,
            "maximum_redirects": 1_000,
        },
    }

    result = activities.run_legislation_acquisition(ActivityContext("test", 1), payload)

    assert type(result) is bytes
    assert canonicalize(parse_json_bytes(result, max_bytes=len(result))) == result
    document = parse_json_bytes(result, max_bytes=len(result))
    assert type(document) is dict
    assert document["result"] == "COMPLETE"
    assert archive_admission.calls == []


def test_normal_activity_build_requires_complete_local_legislation_configuration(
    tmp_path: Path,
) -> None:
    """A missing retained/admission/window path must prevent unusable registration."""

    class Credential:
        @staticmethod
        def reveal() -> bytes:
            return b"http://127.0.0.1:8080"

    infrastructure = SimpleNamespace(
        source_egress_proxy_credential=Credential(),
        primary_vault=object(),
        due_cycle_state_root=tmp_path / "cycles",
    )

    with pytest.raises(
        AcquisitionPipelineError, match="legislation production configuration invalid"
    ):
        v1_pipeline.build_activities(cast("V1AcquisitionInfrastructure", infrastructure), {})


def test_normal_activity_build_supplies_concrete_local_legislation_ports(tmp_path: Path) -> None:
    """Normal composition must never register a production activity backed by None."""

    class Credential:
        @staticmethod
        def reveal() -> bytes:
            return b"http://127.0.0.1:8080"

    source_root = Path(__file__).resolve().parents[3] / "var/hk-v1/source-admission"
    admission_path = tmp_path / "hkel-admission.json"
    admission_path.write_bytes(_admission_document())
    window_path = tmp_path / "gld-window.json"
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    window_path.write_bytes(canonicalize(graph.to_json()["gld_window"]))
    observation_path = tmp_path / "hkel-observation.json"
    observation_path.write_bytes(_archive_observation_document())
    cases_form_path = tmp_path / "judiciary-current-form.html"
    cases_form_path.write_bytes(b"<html><form id='advanced-search'></form></html>")
    cases_form_fingerprint_path = tmp_path / "judiciary-current-form.sha256"
    cases_form_fingerprint_path.write_text(
        f"sha256:{sha256(cases_form_path.read_bytes()).hexdigest()}\n"
    )
    infrastructure = SimpleNamespace(
        source_egress_proxy_credential=Credential(),
        primary_vault=object(),
        due_cycle_state_root=tmp_path / "cycles",
    )

    activities = v1_pipeline.build_activities(
        cast("V1AcquisitionInfrastructure", infrastructure),
        {
            "ASKLEGAL_HK_V1_SOURCE_ADMISSION_ROOT": str(source_root),
            "ASKLEGAL_HK_V1_HKEL_ADMISSION_RECEIPT": str(admission_path),
            "ASKLEGAL_HK_V1_GLD_WINDOW_SNAPSHOT": str(window_path),
            "ASKLEGAL_HK_V1_HKEL_ARCHIVE_OBSERVATION": str(observation_path),
            "ASKLEGAL_HK_V1_LEGISLATION_STATE_ROOT": str(tmp_path / "legislation-state"),
            "ASKLEGAL_HK_V1_JUDICIARY_ADVANCED_SEARCH_FORM": str(cases_form_path),
            "ASKLEGAL_HK_V1_JUDICIARY_ADVANCED_SEARCH_FORM_FINGERPRINT": str(
                cases_form_fingerprint_path
            ),
        },
    )

    assert activities.production_legislation_configured is True
    assert activities.production_cases_configured is True


def test_local_inputs_accept_live_issued_gld_windows_at_later_cutoffs(tmp_path: Path) -> None:
    """A provider-issued current window removes the frozen-cutoff restart ceiling."""

    class Credential:
        @staticmethod
        def reveal() -> bytes:
            return b"http://127.0.0.1:8080"

    class Provider:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def load_window(self, cycle_id: str, observation_cutoff: str) -> GldGazetteWindow:
            self.calls.append((cycle_id, observation_cutoff))
            return _gld_window(observation_cutoff)

    source_root = Path(__file__).resolve().parents[3] / "var/hk-v1/source-admission"
    admission_path = tmp_path / "hkel-admission.json"
    admission_path.write_bytes(_admission_document())
    observation_path = tmp_path / "hkel-observation.json"
    observation_path.write_bytes(_archive_observation_document())
    provider = Provider()
    inputs = v1_pipeline.LocalLegislationProductionInputs(
        cast(
            "V1AcquisitionInfrastructure",
            SimpleNamespace(
                source_egress_proxy_credential=Credential(),
                primary_vault=object(),
                due_cycle_state_root=tmp_path / "cycles",
            ),
        ),
        {
            "ASKLEGAL_HK_V1_SOURCE_ADMISSION_ROOT": str(source_root),
            "ASKLEGAL_HK_V1_HKEL_ADMISSION_RECEIPT": str(admission_path),
            "ASKLEGAL_HK_V1_HKEL_ARCHIVE_OBSERVATION": str(observation_path),
            "ASKLEGAL_HK_V1_LEGISLATION_STATE_ROOT": str(tmp_path / "state"),
        },
        gld_window_provider=provider,
    )
    later_cutoff = "2026-09-08T00:00:00+00:00"

    loaded = inputs.load(_CYCLE_A, later_cutoff)

    assert provider.calls == [(_CYCLE_A, later_cutoff)]
    assert loaded.gld_window.observation_cutoff == later_cutoff


def test_local_production_inputs_restore_advanced_baseline_and_predecessor(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """A service restart reloads the exact advanced baseline and accepted predecessor."""

    class Credential:
        @staticmethod
        def reveal() -> bytes:
            return b"http://127.0.0.1:8080"

    source_root = Path(__file__).resolve().parents[3] / "var/hk-v1/source-admission"
    admission_path = tmp_path / "hkel-admission.json"
    admission_path.write_bytes(_admission_document())
    window_path = tmp_path / "gld-window.json"
    window_graph = build_legislation_work_graph(_CYCLE_B, _CUTOFF, _seeds())
    window_path.write_bytes(canonicalize(window_graph.to_json()["gld_window"]))
    changed_endpoint = authentic_baseline.archive_reuse_keys[0].archive_endpoint_id
    observed = tuple(
        HkelArchiveReuseKey.issue(
            item.archive_endpoint_id,
            "sha256:" + "b" * 64
            if item.archive_endpoint_id == changed_endpoint
            else item.archive_fingerprint,
            item.publication_profile_fingerprint,
        )
        for item in authentic_baseline.archive_reuse_keys
    )
    observation_path = tmp_path / "hkel-observation.json"
    observation_path.write_bytes(_archive_observation_document(observed))
    environment = {
        "ASKLEGAL_HK_V1_SOURCE_ADMISSION_ROOT": str(source_root),
        "ASKLEGAL_HK_V1_HKEL_ADMISSION_RECEIPT": str(admission_path),
        "ASKLEGAL_HK_V1_GLD_WINDOW_SNAPSHOT": str(window_path),
        "ASKLEGAL_HK_V1_HKEL_ARCHIVE_OBSERVATION": str(observation_path),
        "ASKLEGAL_HK_V1_LEGISLATION_STATE_ROOT": str(tmp_path / "state"),
    }
    infrastructure = SimpleNamespace(
        source_egress_proxy_credential=Credential(),
        primary_vault=object(),
        due_cycle_state_root=tmp_path / "cycles",
    )
    graph = build_legislation_work_graph(_CYCLE_B, _CUTOFF, _seeds())
    changed = next(node for node in graph.nodes if node.endpoint_id == changed_endpoint)
    clock = _ActivityClock()
    cycle = run_legislation_acquisition_cycle(
        state_root=tmp_path / "cycles",
        graph=graph,
        transport=_CycleTransport(graph, frozenset({changed.stable_key}), retry_gld_once=False),
        retained_verifier=_ActivityVerifier(),
        clock=clock,
        sleeper=clock.sleep,
        budget=CycleBudget(100, 100_000_000_000, 60, 1_000),
        baseline=authentic_baseline,
        archive_admission=_AdmitChangedHkelArchives(),
        review_issue_refs=(),
        observed_archive_reuse_keys=observed,
    )
    first = v1_pipeline.LocalLegislationProductionInputs(
        cast("V1AcquisitionInfrastructure", infrastructure), environment
    )
    first.record_completed_cycle(cycle)

    restarted = v1_pipeline.LocalLegislationProductionInputs(
        cast("V1AcquisitionInfrastructure", infrastructure), environment
    )
    restored = restarted.load(_CYCLE_C, _CUTOFF)

    assert restored.baseline == cycle.baseline
    assert restored.previous is not None
    assert restored.previous.manifest == cycle.manifest
    assert restored.observed_archive_reuse_keys == observed

    state_path = tmp_path / "state/accepted-legislation-cycle.json"
    corrupted = state_path.read_bytes().replace(
        b'"schema_version":"1.0.0"',
        b'"schema_version":"9.0.0"',
        1,
    )
    state_path.write_bytes(corrupted)
    corrupt = v1_pipeline.LocalLegislationProductionInputs(
        cast("V1AcquisitionInfrastructure", infrastructure), environment
    )
    with pytest.raises(
        AcquisitionPipelineError, match="legislation production configuration invalid"
    ):
        corrupt.load(_CYCLE_C, _CUTOFF)


def test_restart_c_imports_each_archive_provenance_from_its_single_origin(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """Restart C cannot combine Task-4 and B-capture provenance in one journal payload."""
    graph_b = build_legislation_work_graph(_CYCLE_B, _CUTOFF, _seeds())
    changed_endpoint = authentic_baseline.archive_reuse_keys[0].archive_endpoint_id
    observed = tuple(
        HkelArchiveReuseKey.issue(
            item.archive_endpoint_id,
            "sha256:" + "b" * 64
            if item.archive_endpoint_id == changed_endpoint
            else item.archive_fingerprint,
            item.publication_profile_fingerprint,
        )
        for item in authentic_baseline.archive_reuse_keys
    )
    clock = _ActivityClock()
    changed_stable_key = next(
        node.stable_key for node in graph_b.nodes if node.endpoint_id == changed_endpoint
    )
    cycle_b = run_legislation_acquisition_cycle(
        state_root=tmp_path / "b",
        graph=graph_b,
        transport=_CycleTransport(graph_b, frozenset({changed_stable_key}), retry_gld_once=False),
        retained_verifier=_ActivityVerifier(),
        clock=clock,
        sleeper=clock.sleep,
        budget=CycleBudget(100, 100_000_000_000, 60, 1_000),
        baseline=authentic_baseline,
        archive_admission=_AdmitChangedHkelArchives(),
        review_issue_refs=(),
        observed_archive_reuse_keys=observed,
    )
    graph_c = build_legislation_work_graph(_CYCLE_C, _CUTOFF, _seeds())
    restart_root = tmp_path / "c"
    run_legislation_resumable_graph(
        state_root=restart_root,
        graph=graph_c,
        transport=_CycleTransport(graph_c, frozenset(), retry_gld_once=False),
        retained_verifier=_ActivityVerifier(),
        clock=clock,
        sleeper=clock.sleep,
        budget=CycleBudget(100, 100_000_000_000, 60, 1_000),
        baseline=cycle_b.baseline,
        observed_archive_reuse_keys=observed,
    )
    reference = next(
        item
        for item in cycle_b.baseline.archive_object_references
        if item.endpoint_id == changed_endpoint
    )
    work_item_id = next(
        node.scheduled.identity.work_item_id
        for node in graph_c.nodes
        if node.endpoint_id == changed_endpoint
    )
    with LocalAcquisitionJournal(restart_root, _CYCLE_C) as journal:
        payload = next(
            entry.payload
            for entry in journal.replay()
            if entry.work_item.work_item_id == work_item_id
            and entry.transition is JournalTransition.IMPORTED_CAPTURE_VERIFIED
        )

    assert type(payload) is ImportedCaptureVerifiedPayload
    assert (
        payload.source_attempt_id,
        payload.source_report_fingerprint,
        payload.authority_manifest_fingerprint,
        payload.execution_authorization_fingerprint,
    ) == (
        reference.source_attempt_id,
        reference.source_report_fingerprint,
        reference.authority_manifest_fingerprint,
        reference.execution_authorization_fingerprint,
    )


def test_retryable_gld_item_preserves_completed_hkel_progress(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """GLD retry exhaustion remains visible without erasing successful HKeL refs."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    retry_key = next(
        node.stable_key
        for node in graph.nodes
        if node.kind is LegislationWorkKind.GLD_EVENT_ARTIFACT
    )
    report, verified = _run_cycle(
        tmp_path / "retryable-gld",
        graph,
        retry_keys=frozenset({retry_key}),
    )

    manifest = build_legislation_acquisition_manifest(
        graph, report, verified, (), authentic_baseline
    )

    assert manifest.result is AcquisitionCycleResult.RETRY_EXHAUSTED
    assert len(manifest.verified_item_refs) == len(graph.nodes) - 1
    assert any(scope.rejected_item_count == 1 for scope in manifest.scope_dispositions)


def test_complete_legislation_manifest_round_trips_through_reporting_projection(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """The reporting parser must accept bytes from the authoritative producer."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    report, verified = _run_cycle(tmp_path / "reporting-round-trip", graph)
    manifest = build_legislation_acquisition_manifest(
        graph, report, verified, (), authentic_baseline
    )

    projected = parse_hk_v1_legislation_acquisition_manifest(canonicalize(manifest.to_json()))

    assert projected.manifest_fingerprint == manifest.fingerprint
    assert projected.journal_head_fingerprint == manifest.journal_head_fingerprint
    assert projected.scope_ids == LEGISLATION_SCOPE_IDS


def test_manifest_rejects_forged_extra_verified_binding(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """A ref without a successful graph node cannot enter the release manifest."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    report, verified = _run_cycle(tmp_path / "extra-binding", graph)
    with pytest.raises(ValueError, match="LEGISLATION_VERIFIED_INPUT_MISMATCH"):
        build_legislation_acquisition_manifest(
            graph,
            report,
            (
                *verified,
                LegislationVerifiedItem.issue("forged", "retained/forged", "sha256:" + "f" * 64),
            ),
            (),
            authentic_baseline,
        )


def test_manifest_rejects_forged_graph_and_cycle_report_fingerprints(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """Graph and shared-runner report integrity are rechecked at the boundary."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    report, verified = _run_cycle(tmp_path / "forged-integrity", graph)

    with pytest.raises(ValueError, match="LEGISLATION_WORK_GRAPH_INVALID"):
        build_legislation_acquisition_manifest(
            replace(graph, fingerprint=_HEAD),
            report,
            verified,
            (),
            authentic_baseline,
        )
    with pytest.raises(ValueError, match="LEGISLATION_REPORT_INVALID"):
        build_legislation_acquisition_manifest(
            graph,
            replace(report, fingerprint=_HEAD),
            verified,
            (),
            authentic_baseline,
        )


def test_manifest_rejects_a_caller_self_hashed_cycle_report(
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """Canonical report JSON is not proof that the shared runner produced it."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())

    with pytest.raises(ValueError, match="LEGISLATION_REPORT_NOT_RUNNER_ISSUED"):
        build_legislation_acquisition_manifest(
            graph,
            _report(graph, {}),
            _verified(graph),
            (),
            authentic_baseline,
        )


def test_manifest_binds_verified_content_fingerprint_to_journal_capture_payload(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """An object reference cannot be paired with a caller-selected content hash."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    report, verified = _run_cycle(tmp_path / "content-binding", graph)
    first, *remaining = verified
    forged = (
        replace(first, content_fingerprint="sha256:" + "f" * 64),
        *remaining,
    )

    with pytest.raises(ValueError, match="LEGISLATION_VERIFIED_INPUT_MISMATCH"):
        build_legislation_acquisition_manifest(
            graph,
            report,
            forged,
            (),
            authentic_baseline,
        )


def test_change_detection_rejects_a_forged_previous_manifest(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """NO_CHANGE cannot be derived from a previous manifest with invalid integrity."""
    graph = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    report, verified = _run_cycle(tmp_path / "forged-previous", graph)
    manifest = build_legislation_acquisition_manifest(
        graph,
        report,
        verified,
        (),
        authentic_baseline,
    )

    with pytest.raises(ValueError, match="LEGISLATION_MANIFEST_INVALID"):
        changed_legislation_inputs(verified, replace(manifest, fingerprint=_HEAD))


def test_incomplete_predecessor_cannot_authorize_no_change(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """Only a prior successful source state can prove equality-based NO_CHANGE."""
    graph_a = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    report_a, verified_a = _run_cycle(tmp_path / "incomplete-prior-a", graph_a)
    complete = build_legislation_acquisition_manifest(
        graph_a, report_a, verified_a, (), authentic_baseline
    )
    incomplete = _reseal_manifest(
        replace(
            complete,
            scope_dispositions=tuple(
                replace(item, result=AcquisitionCycleResult.INCOMPLETE_RETRYABLE)
                for item in complete.scope_dispositions
            ),
            result=AcquisitionCycleResult.INCOMPLETE_RETRYABLE,
        )
    )
    graph_b = build_legislation_work_graph(_CYCLE_B, _CUTOFF, _seeds())
    report_b, verified_b = _run_cycle(tmp_path / "incomplete-prior-b", graph_b)

    with pytest.raises(ValueError, match="LEGISLATION_ACCEPTED_SOURCE_STATE_REQUIRED"):
        build_legislation_acquisition_manifest(
            graph_b,
            report_b,
            verified_b,
            (),
            authentic_baseline,
            previous=incomplete,
        )


def test_complete_label_with_incomplete_scope_accounting_cannot_authorize_no_change(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """A COMPLETE label cannot override zero verified and retryable scope facts."""
    graph_a = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    report_a, verified_a = _run_cycle(tmp_path / "semantic-prior-a", graph_a)
    complete = build_legislation_acquisition_manifest(
        graph_a,
        report_a,
        verified_a,
        (),
        authentic_baseline,
    )
    forged = _reseal_manifest(
        replace(
            complete,
            scope_dispositions=tuple(
                replace(
                    item,
                    verified_item_count=0,
                    retryable_item_count=item.required_item_count,
                )
                for item in complete.scope_dispositions
            ),
        )
    )
    graph_b = build_legislation_work_graph(_CYCLE_B, _CUTOFF, _seeds())
    report_b, verified_b = _run_cycle(tmp_path / "semantic-prior-b", graph_b)

    with pytest.raises(ValueError, match="LEGISLATION_ACCEPTED_SOURCE_STATE_REQUIRED"):
        build_legislation_acquisition_manifest(
            graph_b,
            report_b,
            verified_b,
            (),
            authentic_baseline,
            previous=forged,
        )


def test_semantically_complete_but_unaccepted_predecessor_cannot_authorize_no_change(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """Source equality requires exact accepted-state provenance, not prior bytes alone."""
    graph_a = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    report_a, verified_a = _run_cycle(tmp_path / "unaccepted-prior-a", graph_a)
    unaccepted = build_legislation_acquisition_manifest(
        graph_a,
        report_a,
        verified_a,
        (),
        authentic_baseline,
    )
    graph_b = build_legislation_work_graph(_CYCLE_B, _CUTOFF, _seeds())
    report_b, verified_b = _run_cycle(tmp_path / "unaccepted-prior-b", graph_b)

    with pytest.raises(ValueError, match="LEGISLATION_ACCEPTED_SOURCE_STATE_REQUIRED"):
        build_legislation_acquisition_manifest(
            graph_b,
            report_b,
            verified_b,
            (),
            authentic_baseline,
            previous=unaccepted,
        )


def test_register_accepted_complete_source_state_can_authorize_no_change(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """The register's exact preserved snapshot is the predecessor authority."""
    graph_a = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    report_a, verified_a = _run_cycle(tmp_path / "accepted-prior-a", graph_a)
    complete = build_legislation_acquisition_manifest(
        graph_a,
        report_a,
        verified_a,
        (),
        authentic_baseline,
    )
    accepted = _accepted_state(complete)
    graph_b = build_legislation_work_graph(_CYCLE_B, _CUTOFF, _seeds())
    report_b, verified_b = _run_cycle(tmp_path / "accepted-prior-b", graph_b)

    no_change = build_legislation_acquisition_manifest(
        graph_b,
        report_b,
        verified_b,
        (),
        authentic_baseline,
        previous=accepted,
    )

    assert no_change.result is AcquisitionCycleResult.NO_CHANGE


def test_accepted_source_state_rejects_frozen_manifest_substitution(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """A live register-issued object cannot be mutated into another predecessor."""
    graph_a = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    report_a, verified_a = _run_cycle(tmp_path / "accepted-substitution-a", graph_a)
    complete = build_legislation_acquisition_manifest(
        graph_a, report_a, verified_a, (), authentic_baseline
    )
    accepted = _accepted_state(complete)
    substituted = replace(complete, cycle_id=_CYCLE_B)
    substituted = _reseal_manifest(substituted)
    object.__setattr__(accepted, "manifest", substituted)
    graph_b = build_legislation_work_graph(_CYCLE_B, _CUTOFF, _seeds())
    report_b, verified_b = _run_cycle(tmp_path / "accepted-substitution-b", graph_b)

    with pytest.raises(ValueError, match="LEGISLATION_ACCEPTED_SOURCE_STATE_INVALID"):
        build_legislation_acquisition_manifest(
            graph_b,
            report_b,
            verified_b,
            (),
            authentic_baseline,
            previous=accepted,
        )


def test_later_cutoff_preserves_stable_work_plan_when_source_content_is_unchanged(
    tmp_path: Path,
    authentic_baseline: HkelImportedBaseline,
) -> None:
    """Observation timing may change without redefining the logical source work plan."""
    later_cutoff = "2026-09-05T00:00:00+00:00"
    graph_a = build_legislation_work_graph(_CYCLE_A, _CUTOFF, _seeds())
    graph_b = build_legislation_work_graph(
        _CYCLE_B,
        later_cutoff,
        _seeds(_gld_window(later_cutoff)),
    )
    assert tuple(node.stable_key for node in graph_b.nodes) == tuple(
        node.stable_key for node in graph_a.nodes
    )
    report_a, verified_a = _run_cycle(tmp_path / "stable-plan-a", graph_a)
    report_b, verified_b = _run_cycle(tmp_path / "stable-plan-b", graph_b)
    manifest_a = build_legislation_acquisition_manifest(
        graph_a,
        report_a,
        verified_a,
        (),
        authentic_baseline,
    )
    manifest_b = build_legislation_acquisition_manifest(
        graph_b,
        report_b,
        verified_b,
        (),
        authentic_baseline,
    )

    assert manifest_b.work_plan_fingerprint == manifest_a.work_plan_fingerprint
