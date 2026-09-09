"""Neutral application-boundary proof for resumable V1 legislation acquisition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from zipfile import ZIP_DEFLATED, ZipFile

from asklegal_acquisition_worker import v1_pipeline as acquisition_pipeline
from asklegal_acquisition_worker.acquisition_journal import JournalTransition
from asklegal_acquisition_worker.resumable_acquisition import CaptureOutcome
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_durable_task import ActivityContext
from asklegal_evidence_vault import LocalImmutableVault, VaultName
from asklegal_legal_processing_worker import v1_pipeline as legal_pipeline

if TYPE_CHECKING:
    import pytest
    from asklegal_acquisition_worker.hk_legislation_acquisition import LegislationWorkNode
    from asklegal_acquisition_worker.v1_infrastructure import V1AcquisitionInfrastructure
    from asklegal_contracts.json_types import JsonValue

_CUTOFF = "2026-09-04T00:00:00+00:00"
_ARCHIVE_FINGERPRINTS = (
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
_PUBLICATION_PROFILE = "sha256:747c168d4bd8a3836f4c95b541a3d203d120d579102bcbfffc254e30a9585737"


class _Clock:
    def __init__(self) -> None:
        self.elapsed = 0

    def monotonic_ns(self) -> int:
        return self.elapsed

    @staticmethod
    def now() -> datetime:
        return datetime(2026, 9, 4, tzinfo=UTC)

    def sleep(self, seconds: float) -> None:
        self.elapsed += round(seconds * 1_000_000_000)


class _Vault:
    """Read authentic retained objects plus locally captured exact test objects."""

    def __init__(self, source_root: Path) -> None:
        self._source_root = source_root / "hkel-attempt-b"
        self.captured: dict[str, bytes] = {}
        self.reads: list[str] = []

    @staticmethod
    def resolve_current(logical_key: str) -> str:
        return logical_key

    def read_exact(self, reference: object) -> bytes:
        assert type(reference) is str
        self.reads.append(reference)
        body = self.captured.get(reference)
        if body is not None:
            return body
        return (self._source_root / reference).read_bytes()


class _Outcomes:
    def __init__(self, vault: _Vault, changed_archive: bytes) -> None:
        self._vault = vault
        self._changed_archive = changed_archive

    def capture(self, node: LegislationWorkNode) -> CaptureOutcome:
        identity = node.scheduled.identity
        body = (
            self._changed_archive
            if node.endpoint_id == "sep_00000000000000000000000000000000000000000000000a"
            else node.stable_key.encode()
        )
        fingerprint = f"sha256:{sha256(body).hexdigest()}"
        object_ref = f"task5-captured/{node.stable_key}/{fingerprint.removeprefix('sha256:')}"
        self._vault.captured[object_ref] = body
        return CaptureOutcome(
            work_item_id=identity.work_item_id,
            transition=JournalTransition.CAPTURED_VERIFIED,
            status_code=200,
            media_type=identity.media_type,
            final_url=identity.locator,
            body_length=len(body),
            body_fingerprint=fingerprint,
            object_ref=object_ref,
            failure_code=None,
            retry_not_before=None,
            read_back_verified=True,
            redirect_chain=(),
        )


class _Credential:
    @staticmethod
    def reveal() -> bytes:
        return b"http://127.0.0.1:8080"


@dataclass(frozen=True, slots=True)
class _LegalInfrastructure:
    primary_vault: LocalImmutableVault
    model_provider_credential: _Credential
    model_egress_proxy_credential: _Credential


def _reuse_keys() -> list[JsonValue]:
    result: list[JsonValue] = []
    for index, archive_fingerprint in enumerate(_ARCHIVE_FINGERPRINTS, start=10):
        body: dict[str, JsonValue] = {
            "archive_endpoint_id": f"sep_{index:048x}",
            "archive_fingerprint": f"sha256:{archive_fingerprint}",
            "publication_profile_fingerprint": _PUBLICATION_PROFILE,
        }
        result.append({**body, "fingerprint": f"sha256:{sha256(canonicalize(body)).hexdigest()}"})
    return result


def _admission_document() -> bytes:
    body = {
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
        "archive_reuse_keys": _reuse_keys(),
        "review_issue_refs": [
            "hkel-structure/HKEL_ARCHIVE_ROOT_LANGUAGE_CONFLICT/3",
            "hkel-structure/HKEL_BILINGUAL_ROOT_KIND_CONFLICT/1",
        ],
    }
    exact = canonicalize(cast("JsonValue", body))
    return canonicalize(
        cast("JsonValue", {**body, "fingerprint": f"sha256:{sha256(exact).hexdigest()}"})
    )


def _observation_document(changed_fingerprint: str | None = None) -> bytes:
    keys = _reuse_keys()
    if changed_fingerprint is not None:
        first = keys[0]
        assert type(first) is dict
        body = {
            "archive_endpoint_id": first["archive_endpoint_id"],
            "archive_fingerprint": changed_fingerprint,
            "publication_profile_fingerprint": first["publication_profile_fingerprint"],
        }
        keys[0] = {
            **body,
            "fingerprint": f"sha256:{sha256(canonicalize(body)).hexdigest()}",
        }
    body = {
        "schema_id": "asklegal.hkel-archive-observation",
        "schema_version": "1.0.0",
        "archive_reuse_keys": keys,
    }
    exact = canonicalize(cast("JsonValue", body))
    return canonicalize(
        cast("JsonValue", {**body, "fingerprint": f"sha256:{sha256(exact).hexdigest()}"})
    )


def _window_document() -> bytes:
    entry: dict[str, JsonValue] = {
        "stable_identity": "gld-gazette-2026-0001",
        "gazette_class": "LEGAL_SUPPLEMENT_1",
        "issue_kind": "ORDINARY",
        "publication_date": "2026-09-04",
        "artifact_endpoint_id": "sep_00000000000000000000000000000000000000000000003d",
        "artifact_endpoint_version": "1.0.0",
        "source_profile_version": "1.1.0",
        "register_version": "2026-08-28.3",
        "register_fingerprint": (
            "sha256:be2dc02b4ef087ac2357ad96dc05be5a36127e2a7f395bffe5b7a98f6408de67"
        ),
        "artifact_locator": "issued/2026/0001",
    }
    body: dict[str, JsonValue] = {
        "source_id": "HK-LEG-GLD-EGAZETTE",
        "endpoint_id": "sep_00000000000000000000000000000000000000000000003b",
        "endpoint_version": "1.0.0",
        "source_profile_version": "1.1.0",
        "register_version": "2026-08-28.3",
        "register_fingerprint": entry["register_fingerprint"],
        "start_date": "2026-09-04",
        "end_date": "2026-09-04",
        "language": "BILINGUAL",
        "observation_cutoff": _CUTOFF,
        "entries": [entry],
    }
    return canonicalize(
        {**body, "listing_fingerprint": f"sha256:{sha256(canonicalize(body)).hexdigest()}"}
    )


def _valid_archive() -> bytes:
    xml = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<lawDoc xmlns="http://www.xml.gov.hk/schemas/hklm/1.0" '
        b'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xml:lang="en" '
        b'xsi:schemaLocation="http://www.xml.gov.hk/schemas/hklm/1.0 '
        b'https://www.elegislation.gov.hk/schemas/hklm.xsd">'
        b"<heading>valid</heading></lawDoc>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("cap_1_en_c/cap_1_20260904000000_en_c.xml", xml)
    return buffer.getvalue()


def _payload(cycle_id: str) -> dict[str, object]:
    return {
        "source_family": "LEGISLATION",
        "cycle_id": cycle_id,
        "observation_cutoff": _CUTOFF,
        "budget": {
            "maximum_starts": 100,
            "maximum_retained_bytes": 100_000_000_000,
            "maximum_elapsed_seconds": 60,
            "maximum_redirects": 1_000,
        },
    }


def test_normal_services_persist_changed_cycle_then_restart_to_no_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A/B/restart-C crosses both registered activities and durable local ports."""
    source_root = Path(__file__).resolve().parents[2] / "var/hk-v1/source-admission"
    admission_path = tmp_path / "admission.json"
    admission_path.write_bytes(_admission_document())
    observation_path = tmp_path / "observation.json"
    observation_path.write_bytes(_observation_document())
    window_path = tmp_path / "window.json"
    window_path.write_bytes(_window_document())
    cases_form_path = tmp_path / "current-advanced-search-form.html"
    cases_form_path.write_bytes(b"<html><form id='advanced-search'></form></html>")
    cases_form_fingerprint_path = tmp_path / "current-advanced-search-form.sha256"
    cases_form_fingerprint_path.write_text(
        f"sha256:{sha256(cases_form_path.read_bytes()).hexdigest()}\n"
    )
    archive = _valid_archive()
    archive_fingerprint = f"sha256:{sha256(archive).hexdigest()}"
    vault = _Vault(source_root)
    outcomes = _Outcomes(vault, archive)
    clock = _Clock()
    monkeypatch.setattr(acquisition_pipeline, "_SystemAcquisitionClock", lambda: clock)
    monkeypatch.setattr(acquisition_pipeline.time, "sleep", clock.sleep)
    infrastructure = cast(
        "V1AcquisitionInfrastructure",
        SimpleNamespace(
            source_egress_proxy_credential=_Credential(),
            primary_vault=vault,
            due_cycle_state_root=tmp_path / "cycle-state",
        ),
    )
    environment = {
        "ASKLEGAL_HK_V1_SOURCE_ADMISSION_ROOT": str(source_root),
        "ASKLEGAL_HK_V1_HKEL_ADMISSION_RECEIPT": str(admission_path),
        "ASKLEGAL_HK_V1_GLD_WINDOW_SNAPSHOT": str(window_path),
        "ASKLEGAL_HK_V1_HKEL_ARCHIVE_OBSERVATION": str(observation_path),
        "ASKLEGAL_HK_V1_LEGISLATION_STATE_ROOT": str(tmp_path / "legislation-state"),
        "ASKLEGAL_HK_V1_JUDICIARY_ADVANCED_SEARCH_FORM": str(cases_form_path),
        "ASKLEGAL_HK_V1_JUDICIARY_ADVANCED_SEARCH_FORM_FINGERPRINT": str(
            cases_form_fingerprint_path
        ),
    }
    legal_environment = {"ASKLEGAL_HK_V1_LEGISLATION_SPOOL_ROOT": str(tmp_path / "legal-spool")}
    context = ActivityContext("task5", 1)
    results: list[str] = []
    stage_counts: list[int] = []
    for index, cycle_id in enumerate(
        (
            "cyc_20260904_legislation_a",
            "cyc_20260904_legislation_b",
            "cyc_20260904_legislation_c",
        )
    ):
        if index == 1:
            observation_path.write_bytes(_observation_document(archive_fingerprint))
        acquisition = acquisition_pipeline.build_activities(
            infrastructure,
            environment,
            legislation_admitted_outcomes=outcomes,
        )
        emitted = acquisition.run_legislation_acquisition(context, _payload(cycle_id))
        document = parse_json_bytes(emitted, max_bytes=len(emitted))
        assert type(document) is dict
        results.append(cast("str", document["result"]))
        legal = legal_pipeline.build_activities(
            _LegalInfrastructure(
                LocalImmutableVault(tmp_path / "legal-vault", VaultName.PRIMARY),
                _Credential(),
                _Credential(),
            ),
            legal_environment,
        )
        accepted = legal.accept_legislation_manifest(context, emitted)
        assert type(accepted) is dict
        assert accepted["accepted"] is True
        stage_counts.append(len(legal.legislation_dispatch_stages))

    assert results == ["COMPLETE", "COMPLETE", "NO_CHANGE"]
    assert stage_counts == [4, 8, 8]
    assert len(tuple((tmp_path / "legal-spool").glob("*/*.json"))) == 8
    assert archive_fingerprint in {
        f"sha256:{sha256(body).hexdigest()}" for body in vault.captured.values()
    }
    assert any(value.startswith("objects/") for value in vault.reads)
