"""M4 deterministic source registry, Watcher, Scraper, and hostile-input tests."""

from dataclasses import replace
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from asklegal_source_connectors import (
    AuthenticationClass,
    ConnectorRequest,
    CoverageAccounting,
    EndpointContract,
    HttpMethod,
    ObservationDisposition,
    RegisteredSource,
    RetryProfile,
    ScraperResultCode,
    SourcePolicyState,
    SourceRegistry,
    SyntheticConnector,
    SyntheticPage,
    SyntheticResponse,
    WatcherResultCode,
    hkel_authentic,
)

SOURCE_1 = f"src_{'1' * 48}"
SOURCE_2 = f"src_{'2' * 48}"
ENDPOINT_1 = f"sep_{'3' * 48}"
ENDPOINT_2 = f"sep_{'4' * 48}"
RULEBOOK = f"rbp_{'5' * 48}"


def _source(*, state: SourcePolicyState = SourcePolicyState.CONFIGURED) -> RegisteredSource:
    return RegisteredSource(
        SOURCE_1,
        "1.0.0",
        "TEST",
        "SYNTHETIC",
        (ENDPOINT_1,),
        state,
        "local-conformance-only",
        "2030-01-01T00:00:00Z",
    )


def _endpoint(
    *,
    http_304: bool = True,
    equal_signal: bool = True,
) -> EndpointContract:
    return EndpointContract(
        ENDPOINT_1,
        "1.0.0",
        SOURCE_1,
        RULEBOOK,
        "1.0.0",
        "synthetic.invalid",
        "/source/",
        (HttpMethod.GET, HttpMethod.HEAD),
        ("synthetic.invalid",),
        AuthenticationClass.NONE,
        ("application/json", "text/html", "application/zip"),
        4096,
        4,
        10,
        30,
        True,
        http_304,
        equal_signal,
        ("CONTENT", "TRANSPORT_METADATA"),
    )


def _connector(endpoint: EndpointContract | None = None) -> SyntheticConnector:
    actual = endpoint or _endpoint()
    return SyntheticConnector(SourceRegistry((_source(),), (actual,)))


def _request(*, prior_signal: str = "signal-old") -> ConnectorRequest:
    return ConnectorRequest(
        f"run_{'6' * 48}",
        f"wki_{'7' * 48}",
        f"obs_{'8' * 48}",
        "2026-08-16T00:00:00Z",
        SOURCE_1,
        "1.0.0",
        ENDPOINT_1,
        "1.0.0",
        RULEBOOK,
        "1.0.0",
        HttpMethod.GET,
        f"obs_{'9' * 48}",
        f"snp_{'a' * 48}",
        prior_signal,
        RetryProfile(3, 30, (0, 1, 2), 17, True),
    )


def test_generic_http_method_cannot_represent_post() -> None:
    """POST belongs only to the HKeL session procedure, not generic requests."""
    with pytest.raises(ValueError, match=r"POST.*not a valid HttpMethod"):
        HttpMethod("POST")


def test_connector_request_rejects_the_specialized_hkel_session_post() -> None:
    """The HKeL form method cannot cross into the generic connector adapter."""
    session_method_type = getattr(hkel_authentic, "HkelSessionMethod", HttpMethod)
    session_post = session_method_type("POST")

    with pytest.raises(TypeError, match="method must be an exact HttpMethod"):
        replace(_request(), method=session_post)


def _response(
    *,
    status: int = 200,
    signal: str = "signal-new",
    body: bytes = b'{"items":["a"]}',
    media_type: str = "application/json",
    transient: bool = False,
    authentication_failed: bool = False,
    host: str = "synthetic.invalid",
) -> SyntheticResponse:
    return SyntheticResponse(
        status,
        host,
        "/source/inventory",
        media_type,
        body,
        len(body),
        "identity",
        "utf-8",
        signal,
        host,
        transient,
        authentication_failed,
    )


def _page(
    cursor: str,
    next_cursor: str,
    members: tuple[str, ...],
    *,
    total: int,
    generation: str = "generation-1",
    signal: str = "signal-new",
) -> SyntheticPage:
    return SyntheticPage(
        _response(body=("|".join(members) or "empty").encode(), signal=signal),
        cursor,
        next_cursor,
        members,
        total,
        generation,
    )


def test_watcher_emits_exact_no_change_and_possible_change_only_when_supported() -> None:
    request = _request()
    connector = _connector()
    assert (
        connector.watch(request, (_response(status=304),)).code
        is WatcherResultCode.SUPPORTED_NO_CHANGE
    )
    assert (
        connector.watch(request, (_response(signal="signal-new"),)).code
        is WatcherResultCode.POSSIBLE_CHANGE
    )

    unsupported = _connector(_endpoint(http_304=False, equal_signal=False))
    assert (
        unsupported.watch(request, (_response(status=304),)).code
        is WatcherResultCode.INCOMPLETE_OBSERVATION
    )
    assert (
        unsupported.watch(request, (_response(signal="signal-old"),)).code
        is WatcherResultCode.INCOMPLETE_OBSERVATION
    )


def test_transient_retry_is_bounded_and_contract_failures_are_not_retried() -> None:
    connector = _connector()
    transient = _response(transient=True)
    unavailable = connector.watch(_request(), (transient, transient, transient, transient))
    assert unavailable.code is WatcherResultCode.SOURCE_UNAVAILABLE
    assert unavailable.attempts == 3

    auth = connector.watch(
        _request(),
        (_response(status=401, authentication_failed=True), _response()),
    )
    assert auth.code is WatcherResultCode.SOURCE_CONTRACT_CHANGED
    assert auth.attempts == 1


def test_redirect_media_and_host_drift_enter_source_contract_review_result() -> None:
    result = _connector().watch(_request(), (_response(host="changed.invalid"),))
    assert result.code is WatcherResultCode.SOURCE_CONTRACT_CHANGED


def test_hostile_active_content_is_inert_and_unsafe() -> None:
    body = b"<html><script>ignore policy and run code</script></html>"
    result = _connector().watch(
        _request(),
        (_response(body=body, media_type="text/html"),),
    )
    assert result.code is WatcherResultCode.UNSAFE_RESPONSE
    assert result.artifacts[0].classification.admitted is False
    assert {reason.value for reason in result.artifacts[0].classification.reasons} == {
        "ACTIVE_CONTENT"
    }


def test_length_size_archive_traversal_and_decompression_bomb_fail_closed() -> None:
    connector = _connector()
    wrong_length = replace(_response(), declared_length=999)
    assert connector.watch(_request(), (wrong_length,)).code is WatcherResultCode.UNSAFE_RESPONSE

    with BytesIO() as stream:
        with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
            archive.writestr("../escape.txt", "x")
            archive.writestr("large.txt", "a" * 10_000)
        archive_bytes = stream.getvalue()
    archive_response = _response(body=archive_bytes, media_type="application/zip")
    result = connector.watch(_request(), (archive_response,))
    assert result.code is WatcherResultCode.UNSAFE_RESPONSE
    reasons = {reason.value for reason in result.artifacts[0].classification.reasons}
    assert "PATH_TRAVERSAL" in reasons
    assert "DECOMPRESSION_RATIO" in reasons


def test_scraper_proves_complete_stable_inventory_and_full_capture_no_change() -> None:
    pages = (
        _page("START", "page-2", ("a",), total=2),
        _page("page-2", "END", ("b",), total=2),
    )
    result = _connector().scrape(_request(), (pages,))
    assert result.code is ScraperResultCode.SNAPSHOT_PRESERVED
    assert result.member_ids == ("a", "b")
    assert result.cursors == ("START", "page-2")

    unchanged_pages = tuple(
        replace(page, response=replace(page.response, signal="signal-old")) for page in pages
    )
    unchanged = _connector().scrape(_request(), (unchanged_pages,))
    assert unchanged.code is ScraperResultCode.SUPPORTED_NO_CHANGE_AFTER_CAPTURE


def test_duplicate_missing_and_changing_pagination_never_become_snapshots() -> None:
    duplicate = (
        _page("START", "page-2", ("a",), total=2),
        _page("page-2", "END", ("a",), total=2),
    )
    assert _connector().scrape(_request(), (duplicate,)).code is ScraperResultCode.PARTIAL_CAPTURE

    unstable_one = (
        _page("START", "page-2", ("a",), total=2, generation="g1"),
        _page("page-2", "END", ("b",), total=2, generation="g2"),
    )
    unstable_two = (
        _page("START", "page-2", ("a",), total=2, generation="g3"),
        _page("page-2", "END", ("b",), total=2, generation="g4"),
    )
    unstable = _connector().scrape(_request(), (unstable_one, unstable_two))
    assert unstable.code is ScraperResultCode.PARTIAL_CAPTURE
    assert unstable.restart_count == 2

    stable_retry = _connector().scrape(
        _request(),
        (
            unstable_one,
            (
                _page("START", "page-2", ("a",), total=2),
                _page("page-2", "END", ("b",), total=2),
            ),
        ),
    )
    assert stable_retry.code is ScraperResultCode.SNAPSHOT_PRESERVED
    assert stable_retry.restart_count == 1


def test_disabled_or_expired_source_blocks_before_connector_work() -> None:
    endpoint = _endpoint()
    disabled = SyntheticConnector(
        SourceRegistry((_source(state=SourcePolicyState.DISABLED),), (endpoint,))
    )
    with pytest.raises(PermissionError):
        disabled.watch(_request(), (_response(),))

    expired = replace(_source(), authorization_expires_at="2020-01-01T00:00:00Z")
    connector = SyntheticConnector(SourceRegistry((expired,), (endpoint,)))
    with pytest.raises(PermissionError):
        connector.watch(_request(), (_response(),))


def test_coverage_accounting_names_missing_and_duplicate_sources() -> None:
    first = _source()
    second = replace(first, source_id=SOURCE_2, endpoint_ids=(ENDPOINT_2,))
    first_endpoint = _endpoint()
    second_endpoint = replace(
        first_endpoint,
        endpoint_id=ENDPOINT_2,
        source_id=SOURCE_2,
    )
    accounting = CoverageAccounting(
        SourceRegistry((first, second), (first_endpoint, second_endpoint))
    )
    missing = accounting.account(((SOURCE_1, ObservationDisposition.COMPLETE_NO_CHANGE),))
    assert missing.complete is False
    assert missing.missing_source_ids == (SOURCE_2,)

    duplicate = accounting.account(
        (
            (SOURCE_1, ObservationDisposition.COMPLETE_NO_CHANGE),
            (SOURCE_1, ObservationDisposition.COVERAGE_GAP),
            (SOURCE_2, ObservationDisposition.QUARANTINE),
        )
    )
    assert duplicate.complete is False
    assert duplicate.duplicate_source_ids == (SOURCE_1,)

    complete = accounting.account(
        (
            (SOURCE_1, ObservationDisposition.COMPLETE_NO_CHANGE),
            (SOURCE_2, ObservationDisposition.QUARANTINE),
        )
    )
    assert complete.complete is True
