"""Task-6 Cases baseline acquisition planning tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_acquisition_worker.acquisition_journal import (
    AcquisitionCycleResult,
    AcquisitionFailureCode,
    CheckpointItem,
    JournalTransition,
    WorkItemIdentity,
)
from asklegal_acquisition_worker.hk_cases_acquisition import (
    CasesAcceptedPredecessorState,
    CasesCycleMode,
    CasesJudgmentBundleStore,
    CasesWorkGraph,
    CasesWorkKind,
    RetainedJudiciaryPrefix,
    YearShardDisposition,
    build_cases_acquisition_manifest,
    build_cases_baseline_plan,
    build_cases_observation_graph,
    build_cases_work_graph,
    expand_cases_graph_from_verified_listings,
    expand_cases_graph_from_verified_observations,
    persist_verified_cases_judgment_bundles,
    project_cases_manifest_from_runner,
    retained_judiciary_prefix_from_receipt,
    run_cases_resumable_graph,
)
from asklegal_acquisition_worker.resumable_acquisition import (
    CaptureOutcome,
    CycleBudget,
    runner_verified_capture_bindings,
)
from asklegal_acquisition_worker.retained_evidence_import import (
    RetainedImportedObjectReference,
    RetainedImportReceipt,
)
from asklegal_contracts import canonicalize
from asklegal_reporting import parse_hk_v1_cases_acquisition_manifest
from asklegal_source_connectors.hk_judiciary import registered_judiciary_current_list_route
from asklegal_source_connectors.hk_judiciary_authentic import parse_judiciary_year_result_page


class _RetainedEvidenceReader:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.references: list[RetainedImportedObjectReference] = []

    def read(self, reference: RetainedImportedObjectReference) -> bytes:
        self.references.append(reference)
        return self.body


class _Clock:
    def __init__(self) -> None:
        self._monotonic = 0

    def monotonic_ns(self) -> int:
        return self._monotonic

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


class _Transport:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        self.calls.append(item.work_item_id)
        body = f"case:{item.work_item_id}".encode()
        return CaptureOutcome(
            work_item_id=item.work_item_id,
            transition=JournalTransition.CAPTURED_VERIFIED,
            status_code=200,
            media_type="text/html",
            final_url=item.locator,
            body_length=len(body),
            body_fingerprint=f"sha256:{sha256(body).hexdigest()}",
            object_ref=f"test/cases/{item.work_item_id}",
            failure_code=None,
            retry_not_before=None,
            read_back_verified=True,
            redirect_chain=(),
        )


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


class _ObservationTransport:
    def __init__(self, bodies: dict[str, bytes]) -> None:
        self.retained: dict[str, bytes] = {}
        self._bodies = bodies

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        body = self._bodies.get(item.stage, f"judgment:{item.work_item_id}".encode())
        object_ref = f"test/observations/{item.work_item_id}"
        self.retained[object_ref] = body
        if item.stage == CasesWorkKind.CURRENT_LIST_OBSERVATION.value:
            _entry_url, final_url = registered_judiciary_current_list_route()
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


class _OneRetryTransport(_Transport):
    def __init__(self, retry_id: str) -> None:
        super().__init__()
        self._retry_id = retry_id

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        if item.work_item_id == self._retry_id:
            self.calls.append(item.work_item_id)
            return CaptureOutcome(
                work_item_id=item.work_item_id,
                transition=JournalTransition.RETRYABLE_FAILURE,
                status_code=None,
                media_type=None,
                final_url=None,
                body_length=0,
                body_fingerprint=None,
                object_ref=None,
                failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE.value,
                retry_not_before="2026-09-07T00:00:00+00:00",
                read_back_verified=False,
                redirect_chain=(),
            )
        return super().capture(item)


class _ImmediateRetryTransport(_Transport):
    def __init__(self, retry_id: str) -> None:
        super().__init__()
        self._retry_id = retry_id

    def capture(self, item: WorkItemIdentity) -> CaptureOutcome:
        if item.work_item_id == self._retry_id:
            self.calls.append(item.work_item_id)
            return CaptureOutcome(
                work_item_id=item.work_item_id,
                transition=JournalTransition.RETRYABLE_FAILURE,
                status_code=None,
                media_type=None,
                final_url=None,
                body_length=0,
                body_fingerprint=None,
                object_ref=None,
                failure_code=AcquisitionFailureCode.SOURCE_UNAVAILABLE.value,
                retry_not_before="2026-09-06T00:00:00+00:00",
                read_back_verified=False,
                redirect_chain=(),
            )
        return super().capture(item)


def test_incremental_graph_uses_registered_current_list_and_rss_procedures() -> None:
    """Opaque observation refs would fail to create executable durable source work."""
    graph = build_cases_observation_graph(
        cycle_id="cyc_incremental",
        observation_cutoff="2026-09-06T00:00:00Z",
    )

    assert graph.mode is CasesCycleMode.INCREMENTAL_DISCOVERY
    assert {(node.kind, node.endpoint_id, node.endpoint_version) for node in graph.nodes} == {
        (
            CasesWorkKind.CURRENT_LIST_OBSERVATION,
            "sep_000000000000000000000000000000000000000000000202",
            "1.0.0",
        ),
        (
            CasesWorkKind.RSS_OBSERVATION,
            "sep_000000000000000000000000000000000000000000000203",
            "1.0.0",
        ),
    }


def test_incremental_current_list_and_rss_create_durable_work_but_never_no_change(
    tmp_path: Path,
) -> None:
    """Both discovery signals may add descendants but cannot prove complete silence."""
    current = (
        b'<html><body><table id="newjudgments"><tr><td>05/09/2026</td><td>'
        b'<a href="https://legalref.judiciary.hk/lrs/common/search/'
        b'search_result_detail_body.jsp?ID=&amp;DIS=901&amp;QS=%2B&amp;TP=JU">Case</a>'
        b"</td></tr></table></body></html>"
    )
    rss = (
        b'<rss version="2.0"><channel><item><link>https://legalref.judiciary.hk/'
        b"lrs/common/search/search_result_detail_body.jsp?ID=&amp;DIS=902&amp;QS=%2B&amp;TP=JU"
        b"</link><guid>902</guid><pubDate>Sat, 05 Sep 2026 00:00:00 +0800</pubDate>"
        b"</item></channel></rss>"
    )
    graph = build_cases_observation_graph(
        cycle_id="cyc_incremental_observations",
        observation_cutoff="2026-09-06T00:00:00Z",
    )
    prefix = _prefix_for_1997(b"unused")
    transport = _ObservationTransport(
        {
            CasesWorkKind.CURRENT_LIST_OBSERVATION.value: current,
            CasesWorkKind.RSS_OBSERVATION.value: rss,
        }
    )
    state_root = tmp_path / "incremental"
    first = run_cases_resumable_graph(
        state_root=state_root,
        graph=graph,
        retained_prefix=prefix,
        transport=transport,
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )
    graph = expand_cases_graph_from_verified_observations(
        graph=graph,
        report=first,
        reader=_VerifiedReader(transport.retained),
    )
    second = run_cases_resumable_graph(
        state_root=state_root,
        graph=graph,
        retained_prefix=prefix,
        transport=transport,
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )
    refs = persist_verified_cases_judgment_bundles(
        state_root=state_root, graph=graph, report=second, store=_BundleStore()
    )
    manifest = project_cases_manifest_from_runner(
        graph=graph,
        report=second,
        discrepancy_refs=(),
        judgment_bundle_refs=refs,
    )

    assert len(graph.occurrences) == 2
    assert len(refs) == 2
    assert manifest.result is AcquisitionCycleResult.INCOMPLETE_TERMINAL


def test_incremental_grammar_drift_adds_no_descendants(tmp_path: Path) -> None:
    """One malformed registered observation invalidates the whole expansion atomically."""
    graph = build_cases_observation_graph(
        cycle_id="cyc_incremental_drift",
        observation_cutoff="2026-09-06T00:00:00Z",
    )
    transport = _ObservationTransport(
        {
            CasesWorkKind.CURRENT_LIST_OBSERVATION.value: (
                b'<html><body><table id="changed"></table></body></html>'
            ),
            CasesWorkKind.RSS_OBSERVATION.value: b'<rss version="2.0"><channel/></rss>',
        }
    )
    report = run_cases_resumable_graph(
        state_root=tmp_path / "drift",
        graph=graph,
        retained_prefix=_prefix_for_1997(b"unused"),
        transport=transport,
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(10, 100_000_000, 60, 20),
    )

    with pytest.raises(ValueError, match="CASES_INCREMENTAL_CONTRACT_CHANGED"):
        expand_cases_graph_from_verified_observations(
            graph=graph,
            report=report,
            reader=_VerifiedReader(transport.retained),
        )

    assert len(graph.nodes) == 2
    assert graph.occurrences == ()


def test_current_list_same_host_route_drift_adds_no_descendants(tmp_path: Path) -> None:
    """A same-host response cannot replace the registered entry-to-session route."""
    current = (
        b'<html><body><table id="newjudgments"><tr><td>05/09/2026</td><td>'
        b'<a href="https://legalref.judiciary.hk/lrs/common/search/'
        b'search_result_detail_body.jsp?ID=&amp;DIS=903&amp;QS=%2B&amp;TP=JU">Case</a>'
        b"</td></tr></table></body></html>"
    )
    graph = build_cases_observation_graph(
        cycle_id="cyc_incremental_route_drift",
        observation_cutoff="2026-09-06T00:00:00Z",
    )
    transport = _ObservationTransport(
        {
            CasesWorkKind.CURRENT_LIST_OBSERVATION.value: current,
            CasesWorkKind.RSS_OBSERVATION.value: b'<rss version="2.0"><channel/></rss>',
        }
    )
    original_capture = transport.capture
    drifted = "https://legalref.judiciary.hk/lrs/common/ju/unregistered.jsp"

    def capture(item: WorkItemIdentity) -> CaptureOutcome:
        outcome = original_capture(item)
        if item.stage != CasesWorkKind.CURRENT_LIST_OBSERVATION.value:
            return outcome
        return replace(outcome, final_url=drifted, redirect_chain=(drifted,))

    transport.capture = capture
    report = run_cases_resumable_graph(
        state_root=tmp_path / "route-drift",
        graph=graph,
        retained_prefix=_prefix_for_1997(b"unused"),
        transport=transport,
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(10, 100_000_000, 60, 20),
    )
    binding = next(
        item
        for item in runner_verified_capture_bindings(report)
        if item.work_item_id == graph.nodes[0].scheduled.identity.work_item_id
    )

    assert binding.final_url == drifted
    assert binding.redirect_chain == (drifted,)
    with pytest.raises(ValueError, match="CASES_INCREMENTAL_CONTRACT_CHANGED"):
        expand_cases_graph_from_verified_observations(
            graph=graph,
            report=report,
            reader=_VerifiedReader(transport.retained),
        )
    assert len(graph.nodes) == 2
    assert graph.occurrences == ()


def test_incremental_cycle_budget_is_cumulative_across_graph_expansion(tmp_path: Path) -> None:
    """A second activity loop cannot reuse starts already spent on observation capture."""
    transport = _ObservationTransport(
        {
            CasesWorkKind.CURRENT_LIST_OBSERVATION.value: (
                b'<html><body><table id="newjudgments"><tr><td>05/09/2026</td><td>'
                b'<a href="https://legalref.judiciary.hk/lrs/common/search/'
                b'search_result_detail_body.jsp?ID=&amp;DIS=911&amp;QS=%2B&amp;TP=JU">Case</a>'
                b"</td></tr></table></body></html>"
            ),
            CasesWorkKind.RSS_OBSERVATION.value: (
                b'<rss version="2.0"><channel><item><link>https://legalref.judiciary.hk/'
                b"lrs/common/search/search_result_detail_body.jsp?ID=&amp;DIS=912&amp;QS=%2B&amp;TP=JU"
                b"</link><guid>912</guid><pubDate>Sat, 05 Sep 2026 00:00:00 +0800</pubDate>"
                b"</item></channel></rss>"
            ),
        }
    )
    graph = build_cases_observation_graph(
        cycle_id="cyc_incremental_budget",
        observation_cutoff="2026-09-06T00:00:00Z",
    )
    state_root = tmp_path / "budget"
    prefix = _prefix_for_1997(b"unused")

    def sleeper(_seconds: float) -> None:
        return

    budget = CycleBudget(3, 100_000_000, 60, 100)
    first = run_cases_resumable_graph(
        graph=graph,
        state_root=state_root,
        retained_prefix=prefix,
        transport=transport,
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=sleeper,
        budget=budget,
    )
    graph = expand_cases_graph_from_verified_observations(
        graph=graph, report=first, reader=_VerifiedReader(transport.retained)
    )
    second = run_cases_resumable_graph(
        graph=graph,
        state_root=state_root,
        retained_prefix=prefix,
        transport=transport,
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=sleeper,
        budget=budget,
    )
    judgment_dispositions = [
        item
        for node in graph.nodes
        if node.kind is CasesWorkKind.JUDGMENT_ARTIFACT
        for item in second.item_dispositions
        if item.work_item_id == node.scheduled.identity.work_item_id
    ]

    assert second.request_starts == 3
    assert second.result is AcquisitionCycleResult.BUDGET_EXHAUSTED
    assert (
        sum(
            item.transition is JournalTransition.CAPTURED_VERIFIED for item in judgment_dispositions
        )
        == 1
    )


def _complete_one_page_body(year: int, *, dis_offset: int) -> bytes:
    body = (
        Path(__file__).parents[3]
        / "packages/source-connectors/tests/fixtures"
        / "judiciary_result_page_1997_attempt_f_sanitized.html"
    ).read_bytes()
    parsed = parse_judiciary_year_result_page(body, year=1997, page=1, contract_version="1.0.13")
    for dis_id in parsed.dis_ids:
        body = body.replace(str(dis_id).encode(), str(dis_id + dis_offset).encode())
    body = body.replace(b"/1997", f"/{year}".encode())
    body = body.replace(
        b'<span id="searchresult-total">1627</span>',
        b'<span id="searchresult-total">10</span>',
    ).replace(
        b'<span id="searchresult-totalpages">163</span>',
        b'<span id="searchresult-totalpages">1</span>',
    )
    return b"\n".join(line for line in body.splitlines() if b"to page 2" not in line)


def test_retryable_artifact_in_one_year_does_not_block_other_year_capture(
    tmp_path: Path,
) -> None:
    """Artifact dependencies are local; one failed 1997 judgment cannot stall 1998."""
    body_1997 = _complete_one_page_body(1997, dis_offset=0)
    body_1998 = _complete_one_page_body(1998, dis_offset=100_000)
    prefix = RetainedJudiciaryPrefix(
        source_attempt_id="judiciary-baseline",
        source_report_fingerprint="sha256:" + "a" * 64,
        authority_manifest_fingerprint="sha256:" + "b" * 64,
        execution_authorization_fingerprint="sha256:" + "c" * 64,
        observation_cutoff="2026-08-31T11:05:35+00:00",
        imported_listing_refs=(
            (
                "judiciary-year-1997-page-1",
                _year_locator(1997, 1),
                "retained/1997/1",
                f"sha256:{sha256(body_1997).hexdigest()}",
                len(body_1997),
            ),
            (
                "judiciary-year-1998-page-1",
                _year_locator(1998, 1),
                "retained/1998/1",
                f"sha256:{sha256(body_1998).hexdigest()}",
                len(body_1998),
            ),
        ),
    )
    initial = build_cases_work_graph(
        cycle_id="cyc_retry_isolation",
        observation_cutoff="1998-12-31T00:00:00Z",
        retained_prefix=prefix,
        locator_for_year_page=_year_locator,
    )
    graph = CasesWorkGraph(
        initial.cycle_id,
        initial.observation_cutoff,
        tuple(node for node in initial.nodes if node.page == 1),
    )
    state_root = tmp_path / "retry-isolation"
    first = run_cases_resumable_graph(
        state_root=state_root,
        graph=graph,
        retained_prefix=prefix,
        transport=_Transport(),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(20, 1_000_000_000, 3_600, 2_000),
    )
    graph = expand_cases_graph_from_verified_listings(
        graph=graph,
        report=first,
        reader=_VerifiedReader({"retained/1997/1": body_1997, "retained/1998/1": body_1998}),
        contract_version="1.0.13",
    )
    retry_node = next(
        node
        for node in graph.nodes
        if node.year == 1997 and node.kind is CasesWorkKind.JUDGMENT_ARTIFACT
    )
    report = run_cases_resumable_graph(
        state_root=state_root,
        graph=graph,
        retained_prefix=prefix,
        transport=_OneRetryTransport(retry_node.scheduled.identity.work_item_id),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(20, 1_000_000_000, 3_600, 2_000),
    )
    by_id = {item.work_item_id: item for item in report.item_dispositions}

    assert (
        by_id[retry_node.scheduled.identity.work_item_id].transition
        is JournalTransition.RETRYABLE_FAILURE
    )
    assert all(
        by_id[node.scheduled.identity.work_item_id].transition
        is JournalTransition.CAPTURED_VERIFIED
        for node in graph.nodes
        if node.year == 1998 and node.kind is CasesWorkKind.JUDGMENT_ARTIFACT
    )


def test_retryable_listing_blocks_only_its_own_projected_year(tmp_path: Path) -> None:
    """The manifest projector must preserve successful independent year shards."""
    body_1997 = _complete_one_page_body(1997, dis_offset=0)
    body_1998 = _complete_one_page_body(1998, dis_offset=100_000)
    prefix = RetainedJudiciaryPrefix(
        "judiciary-baseline",
        "sha256:" + "a" * 64,
        "sha256:" + "b" * 64,
        "sha256:" + "c" * 64,
        "retained",
        (
            (
                "judiciary-year-1997-page-1",
                _year_locator(1997, 1),
                "retained/1997/1",
                f"sha256:{sha256(body_1997).hexdigest()}",
                len(body_1997),
            ),
            (
                "judiciary-year-1998-page-1",
                _year_locator(1998, 1),
                "retained/1998/1",
                f"sha256:{sha256(body_1998).hexdigest()}",
                len(body_1998),
            ),
        ),
    )
    initial = build_cases_work_graph(
        cycle_id="cyc_listing_isolation",
        observation_cutoff="1998-12-31T00:00:00Z",
        retained_prefix=prefix,
        locator_for_year_page=_year_locator,
    )
    graph = CasesWorkGraph(
        initial.cycle_id,
        initial.observation_cutoff,
        tuple(node for node in initial.nodes if node.page == 1),
    )
    state_root = tmp_path / "listing-isolation"
    first = run_cases_resumable_graph(
        state_root=state_root,
        graph=graph,
        retained_prefix=prefix,
        transport=_Transport(),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )
    graph = expand_cases_graph_from_verified_listings(
        graph=graph,
        report=first,
        reader=_VerifiedReader({"retained/1997/1": body_1997, "retained/1998/1": body_1998}),
        contract_version="1.0.13",
    )
    complete = run_cases_resumable_graph(
        state_root=state_root,
        graph=graph,
        retained_prefix=prefix,
        transport=_Transport(),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )
    listing_1997 = next(
        node
        for node in graph.nodes
        if node.year == 1997 and node.kind is CasesWorkKind.LISTING_PAGE
    )
    report = replace(
        complete,
        result=AcquisitionCycleResult.INCOMPLETE_RETRYABLE,
        item_dispositions=tuple(
            CheckpointItem(
                item.work_item_id,
                item.latest_sequence,
                JournalTransition.RETRYABLE_FAILURE,
                1,
                None,
                "2026-09-07T00:00:00+00:00",
            )
            if item.work_item_id == listing_1997.scheduled.identity.work_item_id
            else item
            for item in complete.item_dispositions
        ),
    )
    bundle_refs = persist_verified_cases_judgment_bundles(
        state_root=state_root, graph=graph, report=complete, store=_BundleStore()
    )
    manifest = project_cases_manifest_from_runner(
        graph=graph,
        report=report,
        discrepancy_refs=(),
        judgment_bundle_refs=bundle_refs,
    )

    assert manifest.year_dispositions[0].result is AcquisitionCycleResult.INCOMPLETE_RETRYABLE
    assert manifest.year_dispositions[1].result is AcquisitionCycleResult.COMPLETE


def test_relationships_are_journal_terminal_and_verified_bundles_replace_raw_capture_refs(
    tmp_path: Path,
) -> None:
    """Dropping relationship work or projecting raw captures would make this fail."""
    body = _complete_one_page_body(1997, dis_offset=0)
    prefix = _prefix_for_1997(body)
    initial = build_cases_work_graph(
        cycle_id="cyc_bundle",
        observation_cutoff="1997-12-31T00:00:00Z",
        retained_prefix=prefix,
        locator_for_year_page=_year_locator,
    )
    graph = CasesWorkGraph(initial.cycle_id, initial.observation_cutoff, initial.nodes[:1])
    state_root = tmp_path / "bundle-cycle"
    first = run_cases_resumable_graph(
        state_root=state_root,
        graph=graph,
        retained_prefix=prefix,
        transport=_Transport(),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )
    graph = expand_cases_graph_from_verified_listings(
        graph=graph,
        report=first,
        reader=_VerifiedReader({"retained/1997/1": body}),
        contract_version="1.0.13",
    )
    second = run_cases_resumable_graph(
        state_root=state_root,
        graph=graph,
        retained_prefix=prefix,
        transport=_Transport(),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )
    store = _BundleStore()

    bundle_refs = persist_verified_cases_judgment_bundles(
        state_root=state_root, graph=graph, report=second, store=store
    )
    manifest = project_cases_manifest_from_runner(
        graph=graph,
        report=second,
        discrepancy_refs=(),
        judgment_bundle_refs=bundle_refs,
    )

    relationships = [node for node in graph.nodes if not node.captures_body]
    disposition_by_id = {item.work_item_id: item for item in second.item_dispositions}
    assert relationships
    assert all(
        disposition_by_id[node.scheduled.identity.work_item_id].transition
        is JournalTransition.ACCOUNTED_EXCLUDED
        for node in relationships
    )
    assert len(bundle_refs) == manifest.year_dispositions[0].verified_judgments
    assert all(ref.startswith("cases/judgment-bundles/sha256/") for ref in bundle_refs)
    assert not any(ref.startswith("test/cases/") for ref in bundle_refs)
    assert all(store.read(ref) for ref in bundle_refs)


@pytest.mark.parametrize(
    ("runner_result", "expected_result"),
    [
        (
            AcquisitionCycleResult.BUDGET_EXHAUSTED,
            AcquisitionCycleResult.BUDGET_EXHAUSTED,
        ),
        (
            AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE,
            AcquisitionCycleResult.EVIDENCE_INTEGRITY_FAILURE,
        ),
        (
            AcquisitionCycleResult.AUTHORIZATION_FAILURE,
            AcquisitionCycleResult.AUTHORIZATION_FAILURE,
        ),
        (
            AcquisitionCycleResult.SOURCE_CONTRACT_CHANGED,
            AcquisitionCycleResult.SOURCE_CONTRACT_CHANGED,
        ),
        (
            AcquisitionCycleResult.RETRY_EXHAUSTED,
            AcquisitionCycleResult.RETRY_EXHAUSTED,
        ),
    ],
)
def test_full_projection_preserves_unattributed_runner_stop_result(
    tmp_path: Path,
    runner_result: AcquisitionCycleResult,
    expected_result: AcquisitionCycleResult,
) -> None:
    """A runner-owned stop cannot disappear behind otherwise complete shard facts."""
    body = _complete_one_page_body(1997, dis_offset=0)
    prefix = _prefix_for_1997(body)
    initial = build_cases_work_graph(
        cycle_id=f"cyc_runner_stop_{runner_result.value.lower()}",
        observation_cutoff="1997-12-31T00:00:00Z",
        retained_prefix=prefix,
        locator_for_year_page=_year_locator,
    )
    graph = CasesWorkGraph(initial.cycle_id, initial.observation_cutoff, initial.nodes[:1])
    state_root = tmp_path / runner_result.value.lower()
    first = run_cases_resumable_graph(
        state_root=state_root,
        graph=graph,
        retained_prefix=prefix,
        transport=_Transport(),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )
    expanded = expand_cases_graph_from_verified_listings(
        graph=graph,
        report=first,
        reader=_VerifiedReader({"retained/1997/1": body}),
        contract_version="1.0.13",
    )
    complete = run_cases_resumable_graph(
        state_root=state_root,
        graph=expanded,
        retained_prefix=prefix,
        transport=_Transport(),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )
    bundle_refs = persist_verified_cases_judgment_bundles(
        state_root=state_root,
        graph=expanded,
        report=complete,
        store=_BundleStore(),
    )

    manifest = project_cases_manifest_from_runner(
        graph=expanded,
        report=replace(complete, result=runner_result),
        discrepancy_refs=(),
        judgment_bundle_refs=bundle_refs,
    )

    assert manifest.year_dispositions[0].result is AcquisitionCycleResult.COMPLETE
    assert manifest.result is expected_result


def test_only_full_reconciliation_with_exact_predecessor_can_prove_no_change() -> None:
    """An RSS-only or unaccepted equality claim must remain non-successful."""
    shards = (
        YearShardDisposition(
            1997,
            "1997-07-01",
            1,
            1,
            1,
            1,
            0,
            AcquisitionCycleResult.COMPLETE,
        ),
    )
    prior = build_cases_acquisition_manifest(
        cycle_id="cyc_prior",
        observation_cutoff="1997-12-30T00:00:00Z",
        year_dispositions=shards,
        judgment_bundle_refs=("cases/judgment-bundles/sha256/" + "1" * 64 + ".json",),
        discrepancy_refs=(),
        journal_head_fingerprint="sha256:" + "a" * 64,
    )
    accepted = CasesAcceptedPredecessorState.issue(prior, "accepted/cases/prior")
    reconciled = build_cases_acquisition_manifest(
        cycle_id="cyc_current",
        observation_cutoff="1997-12-31T00:00:00Z",
        year_dispositions=shards,
        judgment_bundle_refs=prior.judgment_bundle_refs,
        discrepancy_refs=(),
        journal_head_fingerprint="sha256:" + "b" * 64,
        cycle_mode=CasesCycleMode.FULL_RECONCILIATION,
        accepted_predecessor=accepted,
    )
    incremental = build_cases_acquisition_manifest(
        cycle_id="cyc_incremental",
        observation_cutoff="1997-12-31T00:00:00Z",
        year_dispositions=shards,
        judgment_bundle_refs=prior.judgment_bundle_refs,
        discrepancy_refs=(),
        journal_head_fingerprint="sha256:" + "c" * 64,
        cycle_mode=CasesCycleMode.INCREMENTAL_DISCOVERY,
        accepted_predecessor=accepted,
    )

    assert reconciled.result is AcquisitionCycleResult.NO_CHANGE
    assert incremental.result is AcquisitionCycleResult.INCOMPLETE_TERMINAL


def test_accepted_predecessor_revalidates_its_exact_manifest() -> None:
    """A re-fingerprinted wrapper cannot bless a forged predecessor dataclass."""
    valid = build_cases_acquisition_manifest(
        cycle_id="cyc_prior_exact",
        observation_cutoff="1997-12-30T00:00:00Z",
        year_dispositions=(
            YearShardDisposition(
                1997,
                "1997-07-01",
                1,
                1,
                0,
                0,
                0,
                AcquisitionCycleResult.COMPLETE,
            ),
        ),
        judgment_bundle_refs=(),
        discrepancy_refs=(),
        journal_head_fingerprint="sha256:" + "a" * 64,
    )

    with pytest.raises(ValueError, match="CASES_RETAINED_PREFIX_INVALID"):
        CasesAcceptedPredecessorState.issue(
            replace(valid, fingerprint="sha256:" + "0" * 64),
            "accepted/cases/forged",
        )


def _year_locator(year: int, page: int) -> str:
    return (
        "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?"
        "selSchct=FA&selSchct=CA&selSchct=HC&selSchct=CT&selSchct=DC&selSchct=FC&"
        "selSchct=LD&selSchct=OT&selDatabase2=JU&isadvsearch=1&selall2=1&"
        f"selallct=1&stem=1&txtselectopt3=5&day1=&month=&txtSearch3=%2F%2F{year}&"
        f"year={year}&page={page}"
    )


def _prefix_for_1997(body: bytes) -> RetainedJudiciaryPrefix:
    return RetainedJudiciaryPrefix(
        source_attempt_id="judiciary-baseline",
        source_report_fingerprint="sha256:" + "a" * 64,
        authority_manifest_fingerprint="sha256:" + "b" * 64,
        execution_authorization_fingerprint="sha256:" + "c" * 64,
        observation_cutoff="2026-08-31T11:05:35+00:00",
        imported_listing_refs=(
            (
                "judiciary-year-1997-page-1",
                _year_locator(1997, 1),
                "retained/1997/1",
                f"sha256:{sha256(body).hexdigest()}",
                len(body),
            ),
        ),
    )


def test_retained_prefix_is_reconstructed_from_exact_receipt_objects() -> None:
    """A retained receipt, not its summary coordinate, supplies the W continuation."""
    body = b"<html>retained Judiciary W page</html>"
    reference = RetainedImportedObjectReference(
        endpoint_id="judiciary-year-2011-page-363",
        work_item_id="wi-retained-2011-363",
        media_type="text/html",
        final_url="https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?page=363",
        body_length=len(body),
        content_fingerprint=f"sha256:{sha256(body).hexdigest()}",
        object_ref="retained/judiciary/363",
        authority_manifest_fingerprint="sha256:" + "b" * 64,
        execution_authorization_fingerprint="sha256:" + "c" * 64,
    )
    receipt = RetainedImportReceipt(
        source_family="CASES",
        source_report_fingerprint="sha256:" + "a" * 64,
        imported_item_count=1,
        reused_object_bytes=len(body),
        journal_head_fingerprint="sha256:" + "d" * 64,
        archive_members=None,
        archive_pairs=None,
        publication_specifications=None,
        semantic_proof_fingerprint="sha256:" + "e" * 64,
        last_listing=(1997, 1),  # Deliberately false: it must not drive continuation.
        cycle_id="cyc_retained_w",
        source_attempt_id="judiciary-live-baseline-20260831w",
        imported_object_references=(reference,),
    )
    reader = _RetainedEvidenceReader(body)

    prefix = retained_judiciary_prefix_from_receipt(receipt, reader)

    assert prefix.last_listing == (2011, 363)
    assert reader.references == [reference]


def test_cases_baseline_resumes_after_2011_page_363() -> None:
    """Removing retained-prefix continuation would incorrectly restart the official listing."""
    plan = build_cases_baseline_plan(
        retained_prefix=RetainedJudiciaryPrefix(
            source_attempt_id="judiciary-live-baseline-20260831w",
            source_report_fingerprint="sha256:" + "a" * 64,
            authority_manifest_fingerprint="sha256:" + "b" * 64,
            execution_authorization_fingerprint="sha256:" + "c" * 64,
            observation_cutoff="2026-08-31T11:05:35+00:00",
            imported_listing_refs=(
                (
                    "judiciary-year-2011-page-363",
                    "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?page=363",
                    "retained/judiciary/363",
                    "sha256:" + "d" * 64,
                    1,
                ),
            ),
        )
    )

    assert plan.first_network_item.identity.stage == "LISTING_PAGE"
    assert plan.first_network_item.identity.parent_id == "year-2011"
    assert "page=364" in plan.first_network_item.identity.locator


def test_retryable_year_shard_cannot_be_projected_as_complete() -> None:
    """A partial listing or artifact shard must remain withheld from downstream use."""
    manifest = build_cases_acquisition_manifest(
        cycle_id="cyc_cases_2026_09_06",
        observation_cutoff="2026-09-06T00:00:00Z",
        year_dispositions=(
            YearShardDisposition(
                year=1997,
                first_in_scope_date="1997-07-01",
                final_page=1,
                verified_listing_pages=1,
                discovered_judgments=1,
                verified_judgments=0,
                retryable_items=1,
                result=AcquisitionCycleResult.INCOMPLETE_RETRYABLE,
            ),
        ),
        judgment_bundle_refs=(),
        discrepancy_refs=("hklII:lead-1",),
        journal_head_fingerprint="sha256:" + "f" * 64,
    )

    assert manifest.result.value == "INCOMPLETE_RETRYABLE"


def test_manifest_cannot_complete_without_every_year_through_cutoff() -> None:
    """A single empty 1997 disposition can never stand in for the baseline."""
    manifest = build_cases_acquisition_manifest(
        cycle_id="cyc_cases_2026_09_06",
        observation_cutoff="2012-12-31T00:00:00Z",
        year_dispositions=(
            YearShardDisposition(
                year=1997,
                first_in_scope_date="1997-07-01",
                final_page=1,
                verified_listing_pages=1,
                discovered_judgments=0,
                verified_judgments=0,
                retryable_items=0,
                result=AcquisitionCycleResult.COMPLETE,
            ),
        ),
        judgment_bundle_refs=(),
        discrepancy_refs=(),
        journal_head_fingerprint="sha256:" + "f" * 64,
    )

    assert manifest.result is AcquisitionCycleResult.INCOMPLETE_TERMINAL


@pytest.mark.parametrize(
    "observation_cutoff",
    [
        "1997-02-30T00:00:00Z",
        "1997-12-31T24:00:00Z",
        "1997-12-31T00:00:00+00:00",
    ],
)
def test_manifest_rejects_impossible_or_noncanonical_utc_cutoff(
    observation_cutoff: str,
) -> None:
    """Regex-shaped dates and equivalent offsets must not enter producer manifests."""
    with pytest.raises(ValueError, match="CASES_RETAINED_PREFIX_INVALID"):
        build_cases_acquisition_manifest(
            cycle_id="cyc_invalid_cutoff",
            observation_cutoff=observation_cutoff,
            year_dispositions=(
                YearShardDisposition(
                    year=1997,
                    first_in_scope_date="1997-07-01",
                    final_page=1,
                    verified_listing_pages=1,
                    discovered_judgments=0,
                    verified_judgments=0,
                    retryable_items=0,
                    result=AcquisitionCycleResult.COMPLETE,
                ),
            ),
            judgment_bundle_refs=(),
            discrepancy_refs=(),
            journal_head_fingerprint="sha256:" + "f" * 64,
        )


def test_cases_manifest_round_trips_only_its_fingerprinted_fields() -> None:
    """Adding caller-only envelope fields to manifest bytes must invalidate its fingerprint."""
    manifest = build_cases_acquisition_manifest(
        cycle_id="cyc_cases_2026_09_06",
        observation_cutoff="1997-12-31T00:00:00Z",
        year_dispositions=(
            YearShardDisposition(
                year=1997,
                first_in_scope_date="1997-07-01",
                final_page=1,
                verified_listing_pages=1,
                discovered_judgments=0,
                verified_judgments=0,
                retryable_items=0,
                result=AcquisitionCycleResult.COMPLETE,
            ),
        ),
        judgment_bundle_refs=(),
        discrepancy_refs=(),
        journal_head_fingerprint="sha256:" + "f" * 64,
    )

    document = manifest.to_json()

    assert set(document) == {
        "cycle_id",
        "discrepancy_refs",
        "earliest_decision_date",
        "fingerprint",
        "journal_head_fingerprint",
        "judgment_bundle_refs",
        "observation_cutoff",
        "result",
        "year_dispositions",
    }
    assert type(manifest).from_json(document) == manifest
    projected = parse_hk_v1_cases_acquisition_manifest(canonicalize(document))
    assert projected.manifest_fingerprint == manifest.fingerprint
    assert projected.journal_head_fingerprint == manifest.journal_head_fingerprint
    assert projected.scope_ids == ("HK-CASE-BINDING-POST-1997",)


def test_reporting_accepts_producer_valid_case_reference_order_and_discrepancy_duplicates() -> None:
    """Mutation caught: a consumer cannot add sorting rules absent from the producer."""
    bundle_refs = (
        "cases/judgment-bundles/sha256/" + "b" * 64 + ".json",
        "cases/judgment-bundles/sha256/" + "a" * 64 + ".json",
    )
    discrepancy_refs = ("review/z", "review/z", "review/a")
    manifest = build_cases_acquisition_manifest(
        cycle_id="cyc_cases_reference_order",
        observation_cutoff="1997-12-31T00:00:00Z",
        year_dispositions=(
            YearShardDisposition(
                year=1997,
                first_in_scope_date="1997-07-01",
                final_page=1,
                verified_listing_pages=1,
                discovered_judgments=2,
                verified_judgments=2,
                retryable_items=0,
                result=AcquisitionCycleResult.COMPLETE,
            ),
        ),
        judgment_bundle_refs=bundle_refs,
        discrepancy_refs=discrepancy_refs,
        journal_head_fingerprint="sha256:" + "f" * 64,
    )

    projected = parse_hk_v1_cases_acquisition_manifest(canonicalize(manifest.to_json()))

    assert projected.verified_evidence_refs == bundle_refs
    assert projected.review_issue_refs == discrepancy_refs


def test_cases_producer_rejects_duplicate_judgment_bundle_references() -> None:
    """Producer parity preserves the producer's duplicate prohibition for bundle refs."""
    duplicate = "cases/judgment-bundles/sha256/" + "a" * 64 + ".json"

    with pytest.raises(ValueError, match="CASES_RETAINED_PREFIX_INVALID"):
        build_cases_acquisition_manifest(
            cycle_id="cyc_cases_duplicate_bundle",
            observation_cutoff="1997-12-31T00:00:00Z",
            year_dispositions=(
                YearShardDisposition(
                    year=1997,
                    first_in_scope_date="1997-07-01",
                    final_page=1,
                    verified_listing_pages=1,
                    discovered_judgments=2,
                    verified_judgments=2,
                    retryable_items=0,
                    result=AcquisitionCycleResult.COMPLETE,
                ),
            ),
            judgment_bundle_refs=(duplicate, duplicate),
            discrepancy_refs=(),
            journal_head_fingerprint="sha256:" + "f" * 64,
        )


def test_reporting_rejects_duplicate_case_bundle_refs_forbidden_by_producer() -> None:
    """A resealed duplicate bundle list cannot bypass the producer's uniqueness rule."""
    refs = (
        "cases/judgment-bundles/sha256/" + "a" * 64 + ".json",
        "cases/judgment-bundles/sha256/" + "b" * 64 + ".json",
    )
    manifest = build_cases_acquisition_manifest(
        cycle_id="cyc_cases_unique_bundles",
        observation_cutoff="1997-12-31T00:00:00Z",
        year_dispositions=(
            YearShardDisposition(
                year=1997,
                first_in_scope_date="1997-07-01",
                final_page=1,
                verified_listing_pages=1,
                discovered_judgments=2,
                verified_judgments=2,
                retryable_items=0,
                result=AcquisitionCycleResult.COMPLETE,
            ),
        ),
        judgment_bundle_refs=refs,
        discrepancy_refs=(),
        journal_head_fingerprint="sha256:" + "f" * 64,
    )
    document = manifest.to_json()
    document["judgment_bundle_refs"] = [refs[0], refs[0]]
    document.pop("fingerprint")
    document["fingerprint"] = f"sha256:{sha256(canonicalize(document)).hexdigest()}"

    with pytest.raises(ValueError, match=r"^HK_V1_TWO_FAMILY_ACQUISITION_INVALID$"):
        parse_hk_v1_cases_acquisition_manifest(canonicalize(document))


def test_cases_work_graph_contains_every_year_and_only_resumes_2011_after_w() -> None:
    """W is a reusable prefix, never a substitute for all later baseline shards."""
    prefix = RetainedJudiciaryPrefix(
        source_attempt_id="judiciary-live-baseline-20260831w",
        source_report_fingerprint="sha256:" + "a" * 64,
        authority_manifest_fingerprint="sha256:" + "b" * 64,
        execution_authorization_fingerprint="sha256:" + "c" * 64,
        observation_cutoff="2026-08-31T11:05:35+00:00",
        imported_listing_refs=(
            (
                "judiciary-year-2011-page-363",
                "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?page=363",
                "retained/judiciary/363",
                "sha256:" + "d" * 64,
                1,
            ),
        ),
    )

    graph = build_cases_work_graph(
        cycle_id="cyc_20260906_cases",
        observation_cutoff="2012-12-31T00:00:00Z",
        retained_prefix=prefix,
        locator_for_year_page=lambda year, page: (
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            f"?year={year}&page={page}"
        ),
    )

    listing_nodes = [node for node in graph.nodes if node.kind is CasesWorkKind.LISTING_PAGE]
    assert {node.year for node in listing_nodes} == set(range(1997, 2013))
    resumed = next(node for node in listing_nodes if node.year == 2011 and node.page == 364)
    assert resumed.scheduled.identity.observation_cutoff == "2012-12-31T00:00:00Z"
    assert resumed.depends_on == ("judiciary-year-2011-page-363",)


def test_cases_runner_imports_w_and_never_redownloads_it(tmp_path: Path) -> None:
    """The shared runner receives the retained W page as a preverified import."""
    prefix = RetainedJudiciaryPrefix(
        source_attempt_id="judiciary-live-baseline-20260831w",
        source_report_fingerprint="sha256:" + "a" * 64,
        authority_manifest_fingerprint="sha256:" + "b" * 64,
        execution_authorization_fingerprint="sha256:" + "c" * 64,
        observation_cutoff="2026-08-31T11:05:35+00:00",
        imported_listing_refs=(
            (
                "judiciary-year-2011-page-363",
                "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?page=363",
                "retained/judiciary/363",
                "sha256:" + "d" * 64,
                1,
            ),
        ),
    )
    graph = build_cases_work_graph(
        cycle_id="cyc_20260906_cases",
        observation_cutoff="2011-12-31T00:00:00Z",
        retained_prefix=prefix,
        locator_for_year_page=lambda year, page: (
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp"
            f"?year={year}&page={page}"
        ),
    )
    transport = _Transport()

    report = run_cases_resumable_graph(
        state_root=tmp_path / "cases",
        graph=graph,
        retained_prefix=prefix,
        transport=transport,
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 1_000),
    )

    retained_id = next(
        node for node in graph.nodes if node.page == 363
    ).scheduled.identity.work_item_id
    assert report.result is AcquisitionCycleResult.COMPLETE, report.to_json()
    assert retained_id not in transport.calls


def test_late_page_two_retry_preserves_durable_provisional_page_one_descendants(
    tmp_path: Path,
) -> None:
    """A late listing retry cannot block or admit work already found on page one."""
    body = (
        Path(__file__).parents[3]
        / "packages/source-connectors/tests/fixtures"
        / "judiciary_result_page_1997_attempt_f_sanitized.html"
    ).read_bytes()
    body = body.replace(
        b'<span id="searchresult-total">1627</span>',
        b'<span id="searchresult-total">20</span>',
    ).replace(
        b'<span id="searchresult-totalpages">163</span>',
        b'<span id="searchresult-totalpages">2</span>',
    )
    parsed = parse_judiciary_year_result_page(body, year=1997, page=1, contract_version="1.0.13")
    assert parsed.advertised_next_page == 2
    prefix = RetainedJudiciaryPrefix(
        source_attempt_id="judiciary-baseline",
        source_report_fingerprint="sha256:" + "a" * 64,
        authority_manifest_fingerprint="sha256:" + "b" * 64,
        execution_authorization_fingerprint="sha256:" + "c" * 64,
        observation_cutoff="2026-08-31T11:05:35+00:00",
        imported_listing_refs=(
            (
                "judiciary-year-1997-page-1",
                (
                    "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?"
                    "selSchct=FA&selSchct=CA&selSchct=HC&selSchct=CT&selSchct=DC&selSchct=FC&"
                    "selSchct=LD&selSchct=OT&selDatabase2=JU&isadvsearch=1&selall2=1&"
                    "selallct=1&stem=1&txtselectopt3=5&day1=&month=&txtSearch3=%2F%2F1997&"
                    "year=1997&page=1"
                ),
                "retained/1997/1",
                f"sha256:{sha256(body).hexdigest()}",
                len(body),
            ),
        ),
    )
    initial = build_cases_work_graph(
        cycle_id="cyc_two_page",
        observation_cutoff="1997-12-31T00:00:00Z",
        retained_prefix=prefix,
        locator_for_year_page=lambda year, page: (
            "https://legalref.judiciary.hk/lrs/common/search/search_result_form.jsp?"
            "selSchct=FA&selSchct=CA&selSchct=HC&selSchct=CT&selSchct=DC&selSchct=FC&"
            "selSchct=LD&selSchct=OT&selDatabase2=JU&isadvsearch=1&selall2=1&"
            f"selallct=1&stem=1&txtselectopt3=5&day1=&month=&txtSearch3=%2F%2F{year}&"
            f"year={year}&page={page}"
        ),
    )
    graph = CasesWorkGraph(initial.cycle_id, initial.observation_cutoff, initial.nodes[:1])
    state_root = tmp_path / "two-page"
    first = run_cases_resumable_graph(
        state_root=state_root,
        graph=graph,
        retained_prefix=prefix,
        transport=_Transport(),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )

    expanded = expand_cases_graph_from_verified_listings(
        graph=graph,
        report=first,
        reader=_VerifiedReader({"retained/1997/1": body}),
        contract_version="1.0.13",
    )
    page_two = next(
        node
        for node in expanded.nodes
        if node.kind is CasesWorkKind.LISTING_PAGE and node.year == 1997 and node.page == 2
    )
    second = run_cases_resumable_graph(
        state_root=state_root,
        graph=expanded,
        retained_prefix=prefix,
        transport=_OneRetryTransport(page_two.scheduled.identity.work_item_id),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )
    by_id = {item.work_item_id: item for item in second.item_dispositions}
    page_one_judgments = tuple(
        node
        for node in expanded.nodes
        if node.page == 1 and node.kind is CasesWorkKind.JUDGMENT_ARTIFACT
    )
    page_one_relationships = tuple(
        node for node in expanded.nodes if node.page == 1 and not node.captures_body
    )
    bundle_refs = persist_verified_cases_judgment_bundles(
        state_root=state_root,
        graph=expanded,
        report=second,
        store=_BundleStore(),
    )
    manifest = project_cases_manifest_from_runner(
        graph=expanded,
        report=second,
        discrepancy_refs=(),
        judgment_bundle_refs=bundle_refs,
    )

    assert len(expanded.occurrences) == 10
    assert all(not occurrence.reconciled_in_scope for occurrence in expanded.occurrences)
    assert len(page_one_judgments) == 10
    assert len(page_one_relationships) == 60
    assert all(
        by_id[node.scheduled.identity.work_item_id].transition
        is JournalTransition.CAPTURED_VERIFIED
        for node in page_one_judgments
    )
    assert all(
        by_id[node.scheduled.identity.work_item_id].transition
        is JournalTransition.ACCOUNTED_EXCLUDED
        for node in page_one_relationships
    )
    assert (
        by_id[page_two.scheduled.identity.work_item_id].transition
        is JournalTransition.RETRYABLE_FAILURE
    )
    assert expanded.reconciled_partitions == ()
    assert bundle_refs == ()
    assert manifest.year_dispositions[0].result is AcquisitionCycleResult.INCOMPLETE_RETRYABLE
    assert manifest.result is not AcquisitionCycleResult.COMPLETE


def test_reconciled_year_marks_only_rows_through_cutoff_for_admission(
    tmp_path: Path,
) -> None:
    """Known post-cutoff facts remain provisional and outside admitted accounting."""
    body = _complete_one_page_body(1997, dis_offset=0)
    prefix = _prefix_for_1997(body)
    initial = build_cases_work_graph(
        cycle_id="cyc_cutoff_partition",
        observation_cutoff="1997-10-01T00:00:00Z",
        retained_prefix=prefix,
        locator_for_year_page=_year_locator,
    )
    graph = CasesWorkGraph(initial.cycle_id, initial.observation_cutoff, initial.nodes[:1])
    state_root = tmp_path / "cutoff-partition"
    first = run_cases_resumable_graph(
        state_root=state_root,
        graph=graph,
        retained_prefix=prefix,
        transport=_Transport(),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )

    expanded = expand_cases_graph_from_verified_listings(
        graph=graph,
        report=first,
        reader=_VerifiedReader({"retained/1997/1": body}),
        contract_version="1.0.13",
    )

    judgments = tuple(
        node for node in expanded.nodes if node.kind is CasesWorkKind.JUDGMENT_ARTIFACT
    )
    assert len(expanded.reconciled_partitions) == 1
    assert expanded.reconciled_partitions[0].reported_results == 10
    assert len(judgments) == 10
    assert len(expanded.occurrences) == 10
    assert sum(occurrence.reconciled_in_scope for occurrence in expanded.occurrences) == 2
    excluded_occurrence = next(
        occurrence for occurrence in expanded.occurrences if not occurrence.reconciled_in_scope
    )
    excluded_judgment = next(
        node for node in judgments if node.key == excluded_occurrence.judgment_node_key
    )
    second = run_cases_resumable_graph(
        state_root=state_root,
        graph=expanded,
        retained_prefix=prefix,
        transport=_ImmediateRetryTransport(excluded_judgment.scheduled.identity.work_item_id),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(100, 1_000_000_000, 3_600, 2_000),
    )
    by_id = {item.work_item_id: item for item in second.item_dispositions}
    bundle_refs = persist_verified_cases_judgment_bundles(
        state_root=state_root,
        graph=expanded,
        report=second,
        store=_BundleStore(),
    )
    manifest = project_cases_manifest_from_runner(
        graph=expanded,
        report=second,
        discrepancy_refs=(),
        judgment_bundle_refs=bundle_refs,
    )

    assert len(bundle_refs) == 2
    assert second.result is AcquisitionCycleResult.RETRY_EXHAUSTED
    assert (
        by_id[excluded_judgment.scheduled.identity.work_item_id].transition
        is JournalTransition.RETRY_EXHAUSTED
    )
    assert manifest.year_dispositions[0].discovered_judgments == 2
    assert manifest.year_dispositions[0].verified_judgments == 2
    assert manifest.result is AcquisitionCycleResult.COMPLETE


def test_publisher_count_drift_retains_provisional_descendants_and_poisons_shard(
    tmp_path: Path,
) -> None:
    """Numeric page completion cannot bypass the source-owned publisher-count proof."""
    body = _complete_one_page_body(1997, dis_offset=0).replace(
        b'<span id="searchresult-total">10</span>',
        b'<span id="searchresult-total">11</span>',
    )
    prefix = _prefix_for_1997(body)
    initial = build_cases_work_graph(
        cycle_id="cyc_count_drift",
        observation_cutoff="1997-12-31T00:00:00Z",
        retained_prefix=prefix,
        locator_for_year_page=_year_locator,
    )
    graph = CasesWorkGraph(initial.cycle_id, initial.observation_cutoff, initial.nodes[:1])
    report = run_cases_resumable_graph(
        state_root=tmp_path / "count-drift",
        graph=graph,
        retained_prefix=prefix,
        transport=_Transport(),
        retained_verifier=_Verifier(),
        clock=_Clock(),
        sleeper=lambda _seconds: None,
        budget=CycleBudget(20, 1_000_000, 60, 200),
    )

    expanded = expand_cases_graph_from_verified_listings(
        graph=graph,
        report=report,
        reader=_VerifiedReader({"retained/1997/1": body}),
        contract_version="1.0.13",
    )
    manifest = project_cases_manifest_from_runner(
        graph=expanded,
        report=report,
        discrepancy_refs=(),
        judgment_bundle_refs=(),
    )

    assert expanded.reconciliation_failures == (1997,)
    assert (
        len(tuple(node for node in expanded.nodes if node.kind is CasesWorkKind.JUDGMENT_ARTIFACT))
        == 10
    )
    assert len(expanded.occurrences) == 10
    assert all(not occurrence.reconciled_in_scope for occurrence in expanded.occurrences)
    assert manifest.year_dispositions[0].result is AcquisitionCycleResult.SOURCE_CONTRACT_CHANGED
    assert manifest.result is AcquisitionCycleResult.SOURCE_CONTRACT_CHANGED
