"""Closed durable outcomes for the V1 Gazette acquisition activity."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING

import asklegal_acquisition_worker.v1_pipeline as pipeline
import pytest
from asklegal_acquisition_worker.v1_infrastructure import V1AcquisitionInfrastructure
from asklegal_application_runtime import CredentialMaterial
from asklegal_domain import (
    SourceCoverageDisposition,
    SourceCoverageOutcomeCode,
    SourceOutageImpact,
)
from asklegal_durable_task import ActivityContext
from asklegal_evidence_vault import VaultName
from asklegal_source_connectors import (
    GazetteEntry,
    GazetteRegisterError,
    GazetteRegisterFailureCode,
    OfficialFetchCode,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


_ENTRY = GazetteEntry(
    gazette_id="30056",
    year="2026",
    supplement="Legal Supplement No. 1",
    gazette_number="1 of 2026",
    title_english="Appropriation Ordinance 2026",
    title_chinese="《2026年撥款條例》",
    locator="hk/2026/1",
    gazette_date="08/05/2026",
    has_english_pdf=True,
    has_chinese_pdf=True,
    has_bilingual_pdf=False,
)


class _Vault:
    def conditional_create(
        self,
        _logical_key: str,
        content: bytes,
        _retention: object,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            created=True,
            read_back_verified=True,
            reference=SimpleNamespace(
                byte_length=len(content),
                vault=VaultName.PRIMARY,
                version_id="version-1",
            ),
        )


def _activities() -> pipeline.AcquisitionActivities:
    infrastructure = V1AcquisitionInfrastructure.__new__(V1AcquisitionInfrastructure)
    object.__setattr__(
        infrastructure,
        "source_egress_proxy_credential",
        CredentialMaterial(b"http://proxy.invalid:3128"),
    )
    object.__setattr__(infrastructure, "primary_vault", _Vault())
    return pipeline.AcquisitionActivities(infrastructure)


def _context() -> ActivityContext:
    return ActivityContext("gazette-test", 1)


def _assert_hkel_coverage(
    result: dict[str, object],
    *,
    outcome: SourceCoverageOutcomeCode,
    disposition: SourceCoverageDisposition,
) -> None:
    coverage = result["coverage_report"]
    assert isinstance(coverage, dict)
    assert result["source_id"] == "HK-LEG-HKEL-GAZETTE-BACKCAPTURE"
    assert result["source_version"] == "1.1.0"
    assert coverage["outcome"] == outcome.value
    assert coverage["disposition"] == disposition.value
    assert coverage["outage_impact"] == SourceOutageImpact.NONBLOCKING.value
    assert coverage["release_blocking"] is False
    assert coverage["affected_work_blocking"] is False
    assert str(coverage["logical_key"]).startswith(
        "poc/report/source-coverage/hk-leg-hkel-gazette-backcapture/"
    )
    assert str(coverage["fingerprint"]).startswith("sha256:")
    assert coverage["read_back_verified"] is True


class _IncompleteClient:
    def __init__(self, _transport: object) -> None:
        pass

    def open_session(self) -> str:
        return "token"

    def iter_entries(self, **_kwargs: object) -> Iterator[GazetteEntry]:
        raise GazetteRegisterError(
            GazetteRegisterFailureCode.INCOMPLETE_OBSERVATION,
            "page limit exceeded",
        )


class _UnexpectedClient:
    def __init__(self, _transport: object) -> None:
        message = "publisher client must not be created for invalid input"
        raise AssertionError(message)


@pytest.mark.parametrize(
    ("date_from", "date_to"),
    [
        ("2026-01-01", "31/01/2026"),
        ("31/02/2026", "31/03/2026"),
        ("02/01/2026", "01/01/2026"),
    ],
)
def test_invalid_windows_fail_before_any_publisher_client(
    monkeypatch: pytest.MonkeyPatch,
    date_from: str,
    date_to: str,
) -> None:
    """Malformed, impossible, and reversed windows have no external effect."""
    monkeypatch.setattr(pipeline, "HkelGazetteRegisterClient", _UnexpectedClient)

    with pytest.raises(pipeline.AcquisitionPipelineError):
        _activities().capture_gazette_window(
            _context(),
            {"date_from": date_from, "date_to": date_to, "language": "en"},
        )


def test_incomplete_window_is_a_durable_result_not_a_generic_task_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Incomplete enumeration is checkpointed with an exact closed code."""
    monkeypatch.setattr(pipeline, "HkelGazetteRegisterClient", _IncompleteClient)

    result = _activities().capture_gazette_window(
        _context(),
        {"date_from": "01/01/2026", "date_to": "31/01/2026", "language": "en"},
    )

    assert isinstance(result, dict)
    assert result["code"] == pipeline.GazetteWindowOutcomeCode.INCOMPLETE_OBSERVATION.value
    assert result["failure_code"] == GazetteRegisterFailureCode.INCOMPLETE_OBSERVATION.value
    assert result["listing_manifest"] is None
    assert result["artifacts"] == []
    _assert_hkel_coverage(
        result,
        outcome=SourceCoverageOutcomeCode.INCOMPLETE_OBSERVATION,
        disposition=SourceCoverageDisposition.COVERAGE_GAP,
    )


class _CompleteClient:
    def __init__(self, _transport: object) -> None:
        pass

    def open_session(self) -> str:
        return "token"

    @property
    def session_cookies(self) -> dict[str, str]:
        return {"session": "value"}

    def iter_entries(self, **_kwargs: object) -> Iterator[GazetteEntry]:
        return iter((_ENTRY,))


class _Transport:
    def with_session(self, _cookies: dict[str, str]) -> _Transport:
        return self


class _NotPublishedClient(_CompleteClient):
    def iter_entries(self, **_kwargs: object) -> Iterator[GazetteEntry]:
        return iter((replace(_ENTRY, has_english_pdf=False),))


class _InvalidLocatorClient(_CompleteClient):
    def iter_entries(self, **_kwargs: object) -> Iterator[GazetteEntry]:
        return iter((replace(_ENTRY, locator="unexpected/2026/1"),))


def test_not_published_is_distinct_and_does_not_make_the_listing_incomplete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A publisher-declared absent language is a fact, not outage or drift."""
    monkeypatch.setattr(pipeline, "HkelGazetteRegisterClient", _NotPublishedClient)

    result = _activities().capture_gazette_window(
        _context(),
        {"date_from": "01/01/2026", "date_to": "31/01/2026", "language": "en"},
    )

    assert isinstance(result, dict)
    assert result["code"] == pipeline.GazetteWindowOutcomeCode.PARTIAL_CAPTURE.value
    assert result["listing_manifest"] is not None
    assert result["not_published"] == 1
    assert result["failed"] == 0
    assert result["artifact_outcomes"][0]["code"] == (
        pipeline.GazetteArtifactOutcomeCode.NOT_PUBLISHED.value
    )
    _assert_hkel_coverage(
        result,
        outcome=SourceCoverageOutcomeCode.PARTIAL_CAPTURE,
        disposition=SourceCoverageDisposition.COVERAGE_GAP,
    )


def test_out_of_contract_publisher_locator_is_durable_contract_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A changed grid locator shape is reported rather than indexed or fetched."""

    class _Connector:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def fetch(self, _request: object) -> SimpleNamespace:
            message = "an invalid publisher locator must not reach the transport"
            raise AssertionError(message)

    monkeypatch.setattr(pipeline, "HkelGazetteRegisterClient", _InvalidLocatorClient)
    monkeypatch.setattr(pipeline, "OfficialHttpConnector", _Connector)
    activities = _activities()
    monkeypatch.setattr(activities, "_transport", _Transport())

    result = activities.capture_gazette_window(
        _context(),
        {"date_from": "01/01/2026", "date_to": "31/01/2026", "language": "en"},
    )

    assert isinstance(result, dict)
    assert result["code"] == pipeline.GazetteWindowOutcomeCode.PARTIAL_CAPTURE.value
    assert result["artifact_outcomes"] == [
        {
            "gazette_id": "30056",
            "locator": "unexpected/2026/1",
            "code": pipeline.GazetteArtifactOutcomeCode.SOURCE_CONTRACT_CHANGED.value,
            "failure_code": "INVALID_ARTIFACT_LOCATOR",
        }
    ]
    _assert_hkel_coverage(
        result,
        outcome=SourceCoverageOutcomeCode.SOURCE_CONTRACT_CHANGED,
        disposition=SourceCoverageDisposition.SOURCE_CONTRACT_REVIEW,
    )


def test_retained_artifact_produces_one_complete_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid admitted PDF and listing produce the sole complete outcome."""

    class _Connector:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def fetch(self, _request: object) -> SimpleNamespace:
            return SimpleNamespace(
                code=OfficialFetchCode.CAPTURED,
                failure_code=None,
                fingerprint=f"sha256:{'a' * 64}",
                classification=SimpleNamespace(admitted=True),
                body=b"%PDF-1.4 admitted",
            )

    monkeypatch.setattr(pipeline, "HkelGazetteRegisterClient", _CompleteClient)
    monkeypatch.setattr(pipeline, "OfficialHttpConnector", _Connector)
    activities = _activities()
    monkeypatch.setattr(activities, "_transport", _Transport())

    result = activities.capture_gazette_window(
        _context(),
        {"date_from": "01/01/2026", "date_to": "31/01/2026", "language": "en"},
    )

    assert isinstance(result, dict)
    assert result["code"] == pipeline.GazetteWindowOutcomeCode.COMPLETE.value
    assert result["retained"] == 1
    assert result["failed"] == 0
    assert result["not_published"] == 0
    assert result["artifact_outcomes"][0]["code"] == (
        pipeline.GazetteArtifactOutcomeCode.RETAINED.value
    )
    _assert_hkel_coverage(
        result,
        outcome=SourceCoverageOutcomeCode.COMPLETE,
        disposition=SourceCoverageDisposition.COMPLETE,
    )


@pytest.mark.parametrize(
    ("fetch_code", "artifact_code", "coverage_outcome", "coverage_disposition"),
    [
        (
            OfficialFetchCode.SOURCE_UNAVAILABLE,
            pipeline.GazetteArtifactOutcomeCode.SOURCE_UNAVAILABLE,
            SourceCoverageOutcomeCode.SOURCE_UNAVAILABLE,
            SourceCoverageDisposition.COVERAGE_GAP,
        ),
        (
            OfficialFetchCode.SOURCE_CONTRACT_CHANGED,
            pipeline.GazetteArtifactOutcomeCode.SOURCE_CONTRACT_CHANGED,
            SourceCoverageOutcomeCode.SOURCE_CONTRACT_CHANGED,
            SourceCoverageDisposition.SOURCE_CONTRACT_REVIEW,
        ),
        (
            OfficialFetchCode.UNSAFE_RESPONSE,
            pipeline.GazetteArtifactOutcomeCode.UNSAFE_RESPONSE,
            SourceCoverageOutcomeCode.UNSAFE_RESPONSE,
            SourceCoverageDisposition.QUARANTINE,
        ),
    ],
)
def test_artifact_failures_remain_distinct_in_the_durable_window_result(
    monkeypatch: pytest.MonkeyPatch,
    fetch_code: OfficialFetchCode,
    artifact_code: pipeline.GazetteArtifactOutcomeCode,
    coverage_outcome: SourceCoverageOutcomeCode,
    coverage_disposition: SourceCoverageDisposition,
) -> None:
    """Outage, contract drift, and hostile content never collapse to one skip."""

    class _Connector:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def fetch(self, _request: object) -> SimpleNamespace:
            return SimpleNamespace(code=fetch_code, failure_code="EXACT_FAILURE")

    monkeypatch.setattr(pipeline, "HkelGazetteRegisterClient", _CompleteClient)
    monkeypatch.setattr(pipeline, "OfficialHttpConnector", _Connector)
    activities = _activities()
    monkeypatch.setattr(activities, "_transport", _Transport())

    result = activities.capture_gazette_window(
        _context(),
        {"date_from": "01/01/2026", "date_to": "31/01/2026", "language": "en"},
    )

    assert isinstance(result, dict)
    assert result["code"] == pipeline.GazetteWindowOutcomeCode.PARTIAL_CAPTURE.value
    assert result["failed"] == 1
    assert result["artifact_outcomes"] == [
        {
            "gazette_id": "30056",
            "locator": "2026/1!en",
            "code": artifact_code.value,
            "failure_code": "EXACT_FAILURE",
        }
    ]
    _assert_hkel_coverage(
        result,
        outcome=coverage_outcome,
        disposition=coverage_disposition,
    )
