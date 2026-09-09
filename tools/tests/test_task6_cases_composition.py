"""Boundary-allowed Task 6 acquisition-to-legal admission composition proof."""

from __future__ import annotations

import runpy
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_acquisition_worker import retained_evidence_import
from asklegal_acquisition_worker.acquisition_journal import (
    AcquisitionCycleResult,
    JournalTransition,
    WorkItemIdentity,
)
from asklegal_acquisition_worker.hk_cases_acquisition import (
    CasesAcquisitionManifest,
    CasesCycleMode,
    CasesJudgmentBundleStore,
    CasesWorkKind,
)
from asklegal_acquisition_worker.resumable_acquisition import CaptureOutcome, CycleBudget
from asklegal_acquisition_worker.retained_evidence_import import (
    RetainedImportedObjectReference,
    RetainedImportReceipt,
)
from asklegal_acquisition_worker.v1_pipeline import (
    AcquisitionActivities,
    AcquisitionPipelineError,
    CasesProductionCycleInputs,
)
from asklegal_contracts import parse_json_bytes
from asklegal_durable_task import ActivityContext
from asklegal_legal_desks.hk_case_judgment import accept_complete_cases_acquisition_manifest
from asklegal_source_connectors.hk_judiciary import registered_judiciary_current_list_route

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_AUTHENTIC_HELPERS: dict[str, object] = runpy.run_path(
    str(_REPOSITORY_ROOT / "packages/source-connectors/tests/test_hk_judiciary_authentic.py")
)


class _RetainedEvidenceReader:
    def __init__(self, values: dict[str, bytes]) -> None:
        self._values = values
        self.references: list[RetainedImportedObjectReference] = []

    def read(self, reference: RetainedImportedObjectReference) -> bytes:
        self.references.append(reference)
        return self._values[reference.object_ref]


class _ExplodingRetainedEvidenceReader:
    def __init__(self) -> None:
        self.calls = 0

    def read(self, reference: RetainedImportedObjectReference) -> bytes:
        del reference
        self.calls += 1
        message = "cutoff validation must precede retained reconstruction"
        raise AssertionError(message)


class _Clock:
    @staticmethod
    def monotonic_ns() -> int:
        return 0

    @staticmethod
    def now() -> datetime:
        return datetime(2026, 9, 6, tzinfo=UTC)


class _Verifier:
    @staticmethod
    def verify(
        item: WorkItemIdentity,
        object_ref: str,
        content_fingerprint: str,
        body_length: int,
    ) -> bool:
        del item, object_ref, content_fingerprint, body_length
        return True


class _VerifiedReader:
    def __init__(self, values: dict[str, bytes]) -> None:
        self._values = values

    def read_exact(self, object_ref: str, content_fingerprint: str, body_length: int) -> bytes:
        body = self._values[object_ref]
        assert content_fingerprint == f"sha256:{sha256(body).hexdigest()}"
        assert body_length == len(body)
        return body


class _BundleStore(CasesJudgmentBundleStore):
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    def conditional_create(self, object_ref: str, body: bytes) -> None:
        prior = self.values.setdefault(object_ref, body)
        assert prior == body

    def read(self, object_ref: str) -> bytes:
        return self.values[object_ref]


class _Page364Transport:
    def __init__(self, bodies: dict[str, bytes], page_364: bytes) -> None:
        self.bodies = bodies
        self.page_364 = page_364
        self.listing_locators: list[str] = []

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        self.listing_locators.append(item.locator)
        if not ("year=2011" in item.locator and "page=364" in item.locator):
            return CaptureOutcome(
                work_item_id=item.work_item_id,
                transition=JournalTransition.RETRYABLE_FAILURE,
                status_code=None,
                media_type=None,
                final_url=None,
                body_length=0,
                body_fingerprint=None,
                object_ref=None,
                failure_code="SOURCE_UNAVAILABLE",
                retry_not_before="2026-09-07T00:00:00+00:00",
                read_back_verified=False,
                redirect_chain=(),
            )
        body = self.page_364
        object_ref = f"test/cases/{item.work_item_id}"
        self.bodies[object_ref] = body
        return CaptureOutcome(
            work_item_id=item.work_item_id,
            transition=JournalTransition.CAPTURED_VERIFIED,
            status_code=200,
            media_type=item.media_type,
            final_url=item.locator,
            body_length=len(body),
            body_fingerprint=f"sha256:{sha256(body).hexdigest()}",
            object_ref=object_ref,
            failure_code=None,
            retry_not_before=None,
            read_back_verified=True,
            redirect_chain=(),
        )


class _IncrementalTransport:
    def __init__(self, bodies: dict[str, bytes], observations: dict[str, bytes]) -> None:
        self.bodies = bodies
        self.observations = observations
        self.stages: list[str] = []

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        self.stages.append(item.stage)
        body = self.observations.get(item.stage, f"verified judgment {item.work_item_id}".encode())
        object_ref = f"test/incremental/{item.work_item_id}"
        self.bodies[object_ref] = body
        if item.stage == CasesWorkKind.CURRENT_LIST_OBSERVATION.value:
            _entry, final_url = registered_judiciary_current_list_route()
            redirect_chain = (final_url,)
        else:
            final_url = item.locator
            redirect_chain = ()
        return CaptureOutcome(
            work_item_id=item.work_item_id,
            transition=JournalTransition.CAPTURED_VERIFIED,
            status_code=200,
            media_type=item.media_type,
            final_url=final_url,
            body_length=len(body),
            body_fingerprint=f"sha256:{sha256(body).hexdigest()}",
            object_ref=object_ref,
            failure_code=None,
            retry_not_before=None,
            read_back_verified=True,
            redirect_chain=redirect_chain,
        )


class _CasesInputPort:
    def __init__(self, inputs: CasesProductionCycleInputs) -> None:
        self.inputs = inputs

    def load(self, cycle_id: str, work_graph_ref: str) -> CasesProductionCycleInputs:
        if not cycle_id or not work_graph_ref:
            raise ValueError
        return self.inputs


class _ExplodingTransport:
    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        del item
        message = "cutoff validation must precede transport"
        raise AssertionError(message)


def _helper_bytes(name: str) -> bytes:
    helper = _AUTHENTIC_HELPERS[name]
    if not callable(helper):
        raise TypeError
    value = helper()
    if type(value) is not bytes:
        raise TypeError
    return value


def _year_locator(year: int, page: int) -> str:
    return (
        "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?"
        "selSchct=FA&selSchct=CA&selSchct=HC&selSchct=CT&selSchct=DC&selSchct=FC&"
        "selSchct=LD&selSchct=OT&selDatabase2=JU&isadvsearch=1&selall2=1&"
        f"selallct=1&stem=1&txtselectopt3=5&day1=&month=&txtSearch3=%2F%2F{year}&"
        f"year={year}&page={page}"
    )


def _factory_issued(receipt: RetainedImportReceipt) -> RetainedImportReceipt:
    """Use the production issuance registry without exporting a test-only constructor."""
    issuer: object = vars(retained_evidence_import).get("_issue_receipt")
    if not callable(issuer):
        raise TypeError
    issued = issuer(receipt)
    if type(issued) is not RetainedImportReceipt:
        raise TypeError
    return issued


def _complete_synthetic_w_prefix() -> tuple[RetainedImportReceipt, dict[str, bytes]]:
    """Issue the full deterministic retained sequence ending at 2011/page363."""
    coordinates = (
        *((year, 1) for year in range(1997, 2011)),
        *((2011, page) for page in range(1, 364)),
    )
    bodies: dict[str, bytes] = {}
    references: list[RetainedImportedObjectReference] = []
    for year, page in coordinates:
        body = f"<html><body>synthetic retained {year} page {page}</body></html>".encode()
        object_ref = f"retained/judiciary/{year}/{page}"
        bodies[object_ref] = body
        references.append(
            RetainedImportedObjectReference(
                endpoint_id=f"judiciary-year-{year}-page-{page}",
                work_item_id=f"wi-retained-{year}-{page}",
                media_type="text/html",
                final_url=_year_locator(year, page),
                body_length=len(body),
                content_fingerprint=f"sha256:{sha256(body).hexdigest()}",
                object_ref=object_ref,
                authority_manifest_fingerprint="sha256:" + "b" * 64,
                execution_authorization_fingerprint="sha256:" + "c" * 64,
            )
        )
    return (
        _factory_issued(
            RetainedImportReceipt(
                source_family="CASES",
                source_report_fingerprint="sha256:" + "a" * 64,
                imported_item_count=len(references),
                reused_object_bytes=sum(len(body) for body in bodies.values()),
                journal_head_fingerprint="sha256:" + "e" * 64,
                archive_members=None,
                archive_pairs=None,
                publication_specifications=None,
                semantic_proof_fingerprint="sha256:" + "f" * 64,
                last_listing=(1997, 1),
                cycle_id="cyc_import_complete_w",
                source_attempt_id="judiciary-retained-complete-w",
                imported_object_references=tuple(references),
            )
        ),
        bodies,
    )


def test_production_activity_rejects_impossible_cutoff_before_any_graph_work(
    tmp_path: Path,
) -> None:
    """A regex-shaped impossible cutoff cannot reach retained reads or transport."""
    reference = RetainedImportedObjectReference(
        endpoint_id="judiciary-year-2011-page-363",
        work_item_id="wi-retained",
        media_type="text/html",
        final_url="https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?page=363",
        body_length=1,
        content_fingerprint="sha256:" + "d" * 64,
        object_ref="retained/judiciary/363",
        authority_manifest_fingerprint="sha256:" + "b" * 64,
        execution_authorization_fingerprint="sha256:" + "c" * 64,
    )
    receipt = _factory_issued(
        RetainedImportReceipt(
            source_family="CASES",
            source_report_fingerprint="sha256:" + "a" * 64,
            imported_item_count=1,
            reused_object_bytes=1,
            journal_head_fingerprint="sha256:" + "e" * 64,
            archive_members=None,
            archive_pairs=None,
            publication_specifications=None,
            semantic_proof_fingerprint="sha256:" + "f" * 64,
            last_listing=(2011, 363),
            cycle_id="cyc_import",
            source_attempt_id="judiciary-retained",
            imported_object_references=(reference,),
        )
    )
    reader = _ExplodingRetainedEvidenceReader()
    inputs = CasesProductionCycleInputs(
        retained_receipt=receipt,
        retained_evidence_reader=reader,
        verified_capture_reader=_VerifiedReader({}),
        advanced_search_form_body=_helper_bytes("_current_advanced_search_form"),
        advanced_search_entry_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            "?isadvsearch=1&stem=1&selall2=1&selallct=1"
        ),
        form_contract_version="1.0.13",
        observation_cutoff="2011-02-30T00:00:00Z",
        cycle_mode=CasesCycleMode.FULL_RECONCILIATION,
        discrepancy_refs=(),
        judgment_bundle_store=_BundleStore(),
        transport=_ExplodingTransport(),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )
    activities = object.__new__(AcquisitionActivities)
    object.__setattr__(activities, "_cases_production_inputs", _CasesInputPort(inputs))
    object.__setattr__(activities, "_cycle_state_root", tmp_path / "invalid-cutoff")

    with pytest.raises(AcquisitionPipelineError, match="Cases production inputs are invalid"):
        activities.run_resumable_acquisition(
            ActivityContext("test", 1),
            {
                "schema_id": "asklegal.cases-resumable-acquisition-instruction",
                "schema_version": "1.0.0",
                "source_family": "CASES",
                "cycle_id": "cyc_20260906_production_cases",
                "work_graph_ref": "worker-local/cases/full",
            },
        )
    assert reader.calls == 0


def test_production_activity_reconstructs_factory_receipt_and_starts_page364(
    tmp_path: Path,
) -> None:
    """The production activity must use its factory receipt and exact W successor."""
    receipt, bodies = _complete_synthetic_w_prefix()
    page_364 = b"<html><body>new publisher page 364</body></html>"
    transport = _Page364Transport(bodies, page_364)
    retained_reader = _RetainedEvidenceReader(bodies)
    bundle_store = _BundleStore()
    inputs = CasesProductionCycleInputs(
        retained_receipt=receipt,
        retained_evidence_reader=retained_reader,
        verified_capture_reader=_VerifiedReader(bodies),
        advanced_search_form_body=_helper_bytes("_current_advanced_search_form"),
        advanced_search_entry_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            "?isadvsearch=1&stem=1&selall2=1&selallct=1"
        ),
        form_contract_version="1.0.13",
        observation_cutoff="2011-12-31T00:00:00Z",
        cycle_mode=CasesCycleMode.FULL_RECONCILIATION,
        discrepancy_refs=("差異/測試",),
        judgment_bundle_store=bundle_store,
        transport=transport,
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(101, 1_000_000_000, 3_600, 2_000),
    )
    activities = object.__new__(AcquisitionActivities)
    object.__setattr__(activities, "_cases_production_inputs", _CasesInputPort(inputs))
    object.__setattr__(activities, "_cycle_state_root", tmp_path / "activity")

    raw = activities.run_resumable_acquisition(
        ActivityContext("test", 1),
        {
            "schema_id": "asklegal.cases-resumable-acquisition-instruction",
            "schema_version": "1.0.0",
            "source_family": "CASES",
            "cycle_id": "cyc_20260906_production_cases",
            "work_graph_ref": "worker-local/cases/full",
        },
    )

    if type(raw) is not bytes:
        raise TypeError
    manifest = CasesAcquisitionManifest.from_json(parse_json_bytes(raw, max_bytes=len(raw)))
    expected_retained_endpoints = (
        *(f"judiciary-year-{year}-page-1" for year in range(1997, 2011)),
        *(f"judiciary-year-2011-page-{page}" for page in range(1, 364)),
    )
    assert tuple(item.endpoint_id for item in retained_reader.references) == (
        expected_retained_endpoints
    )
    assert transport.listing_locators[0] == (
        "https://legalref.judiciary.hk/lrs/common/index.jsp?target=newjudgments&lan=en"
    )
    assert _year_locator(2011, 364) in transport.listing_locators
    assert manifest.result is AcquisitionCycleResult.BUDGET_EXHAUSTED
    assert manifest.judgment_bundle_refs == ()
    with pytest.raises(ValueError, match="ACQUISITION_MANIFEST_INVALID"):
        accept_complete_cases_acquisition_manifest(raw)


def test_production_activity_executes_incremental_current_list_and_rss(
    tmp_path: Path,
) -> None:
    """The real activity must execute both registered incremental discovery routes."""
    retained_body = b"<html><body>retained publisher page 363</body></html>"
    reference = RetainedImportedObjectReference(
        endpoint_id="judiciary-year-2011-page-363",
        work_item_id="wi-retained-incremental",
        media_type="text/html",
        final_url=_year_locator(2011, 363),
        body_length=len(retained_body),
        content_fingerprint=f"sha256:{sha256(retained_body).hexdigest()}",
        object_ref="retained/judiciary/incremental/363",
        authority_manifest_fingerprint="sha256:" + "b" * 64,
        execution_authorization_fingerprint="sha256:" + "c" * 64,
    )
    receipt = _factory_issued(
        RetainedImportReceipt(
            source_family="CASES",
            source_report_fingerprint="sha256:" + "a" * 64,
            imported_item_count=1,
            reused_object_bytes=len(retained_body),
            journal_head_fingerprint="sha256:" + "e" * 64,
            archive_members=None,
            archive_pairs=None,
            publication_specifications=None,
            semantic_proof_fingerprint="sha256:" + "f" * 64,
            last_listing=(2011, 363),
            cycle_id="cyc_import_incremental",
            source_attempt_id="judiciary-retained",
            imported_object_references=(reference,),
        )
    )
    current = (
        b'<html><body><table id="newjudgments"><tr><td>05/09/2011</td><td>'
        b'<a href="https://legalref.judiciary.hk/lrs/common/search/'
        b'search_result_detail_body.jsp?ID=&amp;DIS=901&amp;QS=%2B&amp;TP=JU">Case</a>'
        b"</td></tr></table></body></html>"
    )
    rss = (
        b'<rss version="2.0"><channel><item><link>https://legalref.judiciary.hk/'
        b"lrs/common/search/search_result_detail_body.jsp?ID=&amp;DIS=902&amp;QS=%2B&amp;TP=JU"
        b"</link><guid>902</guid><pubDate>Mon, 05 Sep 2011 00:00:00 +0800</pubDate>"
        b"</item></channel></rss>"
    )
    bodies = {reference.object_ref: retained_body}
    transport = _IncrementalTransport(
        bodies,
        {
            CasesWorkKind.CURRENT_LIST_OBSERVATION.value: current,
            CasesWorkKind.RSS_OBSERVATION.value: rss,
        },
    )
    bundle_store = _BundleStore()
    inputs = CasesProductionCycleInputs(
        retained_receipt=receipt,
        retained_evidence_reader=_RetainedEvidenceReader(bodies),
        verified_capture_reader=_VerifiedReader(bodies),
        advanced_search_form_body=_helper_bytes("_current_advanced_search_form"),
        advanced_search_entry_url=(
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            "?isadvsearch=1&stem=1&selall2=1&selallct=1"
        ),
        form_contract_version="1.0.13",
        observation_cutoff="2011-09-06T00:00:00Z",
        cycle_mode=CasesCycleMode.INCREMENTAL_DISCOVERY,
        discrepancy_refs=(),
        judgment_bundle_store=bundle_store,
        transport=transport,
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )
    activities = object.__new__(AcquisitionActivities)
    object.__setattr__(activities, "_cases_production_inputs", _CasesInputPort(inputs))
    object.__setattr__(activities, "_cycle_state_root", tmp_path / "incremental")

    raw = activities.run_resumable_acquisition(
        ActivityContext("test", 1),
        {
            "schema_id": "asklegal.cases-resumable-acquisition-instruction",
            "schema_version": "1.0.0",
            "source_family": "CASES",
            "cycle_id": "cyc_20260906_incremental_cases",
            "work_graph_ref": "worker-local/cases/incremental",
        },
    )

    if type(raw) is not bytes:
        raise TypeError
    manifest = CasesAcquisitionManifest.from_json(parse_json_bytes(raw, max_bytes=len(raw)))
    assert CasesWorkKind.CURRENT_LIST_OBSERVATION.value in transport.stages
    assert CasesWorkKind.RSS_OBSERVATION.value in transport.stages
    assert transport.stages.count(CasesWorkKind.JUDGMENT_ARTIFACT.value) == 2
    assert manifest.result is AcquisitionCycleResult.INCOMPLETE_TERMINAL
    assert len(manifest.judgment_bundle_refs) == 2
    with pytest.raises(ValueError, match="ACQUISITION_MANIFEST_INVALID"):
        accept_complete_cases_acquisition_manifest(raw)
