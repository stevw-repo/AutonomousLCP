"""Focused tests for the resumable Task 10 Acquisition config materializer."""

from __future__ import annotations

import json
import stat
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import canonicalize
from asklegal_contracts.json_types import JsonValue, checked_json_value
from asklegal_legal_desks.hk_legislation_authentic import (
    HkelAuthenticAdmissionFacts,
    HkelAuthenticAdmissionReceipt,
    HkelAuthenticArchiveReuseKey,
)

from tools import hk_v1_prepare_acquisition_config as preparer

_CUTOFF = "2026-08-28T22:20:23+08:00"
_GLD_CUTOFF = "2026-08-28T14:20:23+00:00"
_REGISTER_FINGERPRINT = "sha256:be2dc02b4ef087ac2357ad96dc05be5a36127e2a7f395bffe5b7a98f6408de67"


def _canonical(value: JsonValue) -> bytes:
    return canonicalize(checked_json_value(value))


def _gld_window() -> bytes:
    body: dict[str, JsonValue] = {
        "source_id": "HK-LEG-GLD-EGAZETTE",
        "endpoint_id": "sep_00000000000000000000000000000000000000000000003b",
        "endpoint_version": "1.0.0",
        "source_profile_version": "1.1.0",
        "register_version": "2026-08-28.3",
        "register_fingerprint": _REGISTER_FINGERPRINT,
        "start_date": "2026-08-28",
        "end_date": "2026-08-28",
        "language": "BILINGUAL",
        "observation_cutoff": _GLD_CUTOFF,
        "entries": [],
    }
    body["listing_fingerprint"] = f"sha256:{sha256(_canonical(body)).hexdigest()}"
    return _canonical(body)


def _source_tree(tmp_path: Path) -> tuple[Path, preparer.RetainedAcquisitionProfile]:
    source_root = tmp_path / "source"
    hkel = source_root / "hkel" / "attempts" / "hkel-fixture"
    judiciary = source_root / "judiciary" / "attempts" / "judiciary-fixture"
    hkel.mkdir(parents=True)
    judiciary.mkdir(parents=True)

    hkel_report = _canonical(
        {
            "attempt_id": "hkel-fixture",
            "observation_cutoff": _CUTOFF,
            "source_family": "HKEL",
            "result": "COMPLETE",
            "readback_verified": True,
            "endpoint_counts": {"CAPTURED": 56},
        }
    )
    form = b"<html><form id='advanced-search'></form></html>"
    form_digest = sha256(form).hexdigest()
    judiciary_report = _canonical(
        {
            "attempt_id": "judiciary-fixture",
            "observation_cutoff": "2026-08-31T23:59:00+08:00",
            "source_family": "JUDICIARY",
            "result": "SOURCE_OUTAGE",
            "readback_verified": True,
            "endpoint_counts": {"CAPTURED": 5590, "OUTAGE": 1},
            "endpoints": [
                {
                    "body_fingerprint": f"sha256:{form_digest}",
                    "byte_length": len(form),
                    "endpoint_id": "advanced-form",
                    "endpoint_version": "1.0.12",
                    "media_type": "text/html",
                    "method": "GET",
                    "object_key": f"objects/{form_digest}.bin",
                    "requested_url": "https://legalref.judiciary.hk/advanced",
                    "status": 200,
                    "terminal_code": "CAPTURED",
                }
            ],
        }
    )
    (hkel / "report.json").write_bytes(hkel_report)
    (judiciary / "report.json").write_bytes(judiciary_report)
    objects = source_root / "judiciary" / "objects"
    objects.mkdir()
    (objects / f"{form_digest}.bin").write_bytes(form)
    profile = preparer.RetainedAcquisitionProfile(
        hkel_report_relative=Path("hkel/attempts/hkel-fixture/report.json"),
        hkel_report_fingerprint=f"sha256:{sha256(hkel_report).hexdigest()}",
        judiciary_report_relative=Path("judiciary/attempts/judiciary-fixture/report.json"),
        judiciary_report_fingerprint=f"sha256:{sha256(judiciary_report).hexdigest()}",
        judiciary_form_endpoint_id="advanced-form",
        judiciary_form_fingerprint=f"sha256:{form_digest}",
    )
    return source_root, profile


def _receipt(report_fingerprint: str) -> HkelAuthenticAdmissionReceipt:
    keys = tuple(
        HkelAuthenticArchiveReuseKey.issue(
            f"sep_{index:048x}",
            f"sha256:{index + 1:064x}",
            "sha256:" + "a" * 64,
        )
        for index in range(10, 22)
    )
    return HkelAuthenticAdmissionReceipt.issue(
        HkelAuthenticAdmissionFacts(
            "hkel-fixture",
            _CUTOFF,
            report_fingerprint,
            "sha256:" + "b" * 64,
            "sha256:" + "c" * 64,
            12_858,
            3_157,
            7,
            keys,
            ("hkel-structure/fixture/1",),
        )
    )


def _inputs(
    tmp_path: Path,
) -> tuple[preparer.AcquisitionConfigInputs, preparer.RetainedAcquisitionProfile]:
    source_root, profile = _source_tree(tmp_path)
    gld_path = tmp_path / "gld-window.json"
    gld = _gld_window()
    gld_path.write_bytes(gld)
    return (
        preparer.AcquisitionConfigInputs(
            source_root=source_root,
            gld_window_path=gld_path,
            expected_gld_window_fingerprint=f"sha256:{sha256(gld).hexdigest()}",
            output_root=tmp_path / "generated",
        ),
        profile,
    )


def test_missing_gld_input_stops_before_hkel_scan_or_publication(tmp_path: Path) -> None:
    """The preparer cannot invent or acquire the authentic GLD listing window."""
    inputs, profile = _inputs(tmp_path)
    inputs.gld_window_path.unlink()
    calls = 0

    def admit(_reference: object, _reader: object) -> HkelAuthenticAdmissionReceipt:
        nonlocal calls
        calls += 1
        return _receipt(profile.hkel_report_fingerprint)

    with pytest.raises(preparer.AcquisitionConfigPreparationError) as raised:
        preparer.prepare_acquisition_config(inputs, profile=profile, admit_hkel=admit)

    assert raised.value.code == "GLD_WINDOW_INPUT_REQUIRED"
    assert calls == 0
    assert not inputs.output_root.exists()


def test_creates_five_exact_files_then_replays_without_hkel_rescan(tmp_path: Path) -> None:
    """A valid existing output is reused byte-for-byte without reparsing archives."""
    inputs, profile = _inputs(tmp_path)
    calls = 0

    def admit(_reference: object, _reader: object) -> HkelAuthenticAdmissionReceipt:
        nonlocal calls
        calls += 1
        return _receipt(profile.hkel_report_fingerprint)

    first = preparer.prepare_acquisition_config(inputs, profile=profile, admit_hkel=admit)
    second = preparer.prepare_acquisition_config(inputs, profile=profile, admit_hkel=admit)

    assert first == second
    assert calls == 1
    assert {path.name for path in inputs.output_root.iterdir()} == set(preparer.CONFIG_FILENAMES)
    assert stat.S_IMODE(inputs.output_root.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in inputs.output_root.iterdir())
    report = json.loads(first)
    assert report["result"] == "READY"
    assert report["artifact_count"] == 5
    assert report["hkel_report_fingerprint"] == profile.hkel_report_fingerprint
    assert report["judiciary_report_fingerprint"] == profile.judiciary_report_fingerprint


def test_rejects_existing_output_drift_and_symlink_without_rescan(tmp_path: Path) -> None:
    """Replay never overwrites drift and never follows a generated-file symlink."""
    inputs, profile = _inputs(tmp_path)
    calls = 0

    def admit(_reference: object, _reader: object) -> HkelAuthenticAdmissionReceipt:
        nonlocal calls
        calls += 1
        return _receipt(profile.hkel_report_fingerprint)

    preparer.prepare_acquisition_config(inputs, profile=profile, admit_hkel=admit)
    target = inputs.output_root / "judiciary-advanced-search-form.html"
    target.unlink()
    target.symlink_to(inputs.gld_window_path)

    with pytest.raises(preparer.AcquisitionConfigPreparationError) as raised:
        preparer.prepare_acquisition_config(inputs, profile=profile, admit_hkel=admit)

    assert raised.value.code == "ACQUISITION_CONFIG_OUTPUT_DRIFT"
    assert calls == 1


@pytest.mark.parametrize("mutation", ["digest", "noncanonical", "contract"])
def test_rejects_unpinned_or_invalid_gld_window_before_hkel_scan(
    tmp_path: Path, mutation: str
) -> None:
    """Both the byte pin and the owning GLD parser must accept the explicit input."""
    inputs, profile = _inputs(tmp_path)
    if mutation == "digest":
        inputs = replace(inputs, expected_gld_window_fingerprint="sha256:" + "f" * 64)
    elif mutation == "noncanonical":
        document = json.loads(inputs.gld_window_path.read_bytes())
        inputs.gld_window_path.write_text(json.dumps(document, indent=2))
        inputs = replace(
            inputs,
            expected_gld_window_fingerprint=(
                f"sha256:{sha256(inputs.gld_window_path.read_bytes()).hexdigest()}"
            ),
        )
    else:
        document = json.loads(inputs.gld_window_path.read_bytes())
        document["listing_fingerprint"] = "sha256:" + "0" * 64
        changed = _canonical(document)
        inputs.gld_window_path.write_bytes(changed)
        inputs = replace(
            inputs, expected_gld_window_fingerprint=f"sha256:{sha256(changed).hexdigest()}"
        )
    calls = 0

    def admit(_reference: object, _reader: object) -> HkelAuthenticAdmissionReceipt:
        nonlocal calls
        calls += 1
        return _receipt(profile.hkel_report_fingerprint)

    with pytest.raises(preparer.AcquisitionConfigPreparationError) as raised:
        preparer.prepare_acquisition_config(inputs, profile=profile, admit_hkel=admit)

    assert raised.value.code == "GLD_WINDOW_INPUT_INVALID"
    assert calls == 0


def test_rejects_judiciary_form_object_drift_without_publication(tmp_path: Path) -> None:
    """The configured form is materialized only from its exact retained report object."""
    inputs, profile = _inputs(tmp_path)
    form = next((inputs.source_root / "judiciary" / "objects").iterdir())
    form.write_bytes(b"changed")

    with pytest.raises(preparer.AcquisitionConfigPreparationError) as raised:
        preparer.prepare_acquisition_config(
            inputs,
            profile=profile,
            admit_hkel=lambda _reference, _reader: _receipt(profile.hkel_report_fingerprint),
        )

    assert raised.value.code == "RETAINED_JUDICIARY_INPUT_INVALID"
    assert not inputs.output_root.exists()
