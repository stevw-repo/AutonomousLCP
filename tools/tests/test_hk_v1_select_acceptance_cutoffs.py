"""Focused Task 10 acceptance-cutoff selector tests."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import canonicalize, parse_json_bytes
from asklegal_contracts.json_types import JsonValue, checked_json_value

from tools import hk_v1_select_acceptance_cutoffs as selector

_T1 = "1997-07-02T00:00:00Z"
_T2 = "1997-07-03T00:00:00Z"
_SCOPES = (
    "HK-CASE-BINDING-POST-1997",
    "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
    "HK-LEG-ORDINANCES",
    "HK-LEG-SUBSIDIARY",
)


def _seal(body: dict[str, object]) -> bytes:
    checked = checked_json_value(body)
    assert type(checked) is dict
    document = {
        **checked,
        "fingerprint": f"sha256:{sha256(canonicalize(checked)).hexdigest()}",
    }
    return canonicalize(document)


def _cases(cutoff: str, *, content: str = "a", result: str = "COMPLETE") -> bytes:
    return _seal(
        {
            "cycle_id": f"cyc_cases_{cutoff[:10].replace('-', '_')}",
            "discrepancy_refs": [],
            "earliest_decision_date": "1997-07-01",
            "journal_head_fingerprint": "sha256:" + cutoff[8:10] * 32,
            "judgment_bundle_refs": (
                [f"cases/judgment-bundles/sha256/{content * 64}.json"]
                if result == "COMPLETE"
                else []
            ),
            "observation_cutoff": cutoff,
            "result": result,
            "year_dispositions": [
                {
                    "discovered_judgments": 1 if result == "COMPLETE" else 0,
                    "final_page": 1,
                    "first_in_scope_date": "1997-07-01",
                    "result": result,
                    "retryable_items": 0 if result == "COMPLETE" else 1,
                    "verified_judgments": 1 if result == "COMPLETE" else 0,
                    "verified_listing_pages": 1,
                    "year": 1997,
                }
            ],
        }
    )


def _legislation(cutoff: str, *, content: str = "b", result: str = "COMPLETE") -> bytes:
    raw_cutoff = cutoff.removesuffix("Z") + "+00:00"
    scopes = (
        "HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS",
        "HK-LEG-ORDINANCES",
        "HK-LEG-SUBSIDIARY",
    )
    return _seal(
        {
            "schema_id": "asklegal.legislation-acquisition-manifest",
            "schema_version": "1.0.0",
            "cycle_id": f"cyc_legislation_{cutoff[:10].replace('-', '_')}",
            "observation_cutoff": raw_cutoff,
            "scope_dispositions": [
                {
                    "scope_id": scope,
                    "required_item_count": 1,
                    "verified_item_count": 1 if result == "COMPLETE" else 0,
                    "retryable_item_count": 0 if result == "COMPLETE" else 1,
                    "rejected_item_count": 0,
                    "result": result,
                }
                for scope in scopes
            ],
            "verified_item_refs": (
                [f"legislation-item/stable-key/{content * 64}"] if result == "COMPLETE" else []
            ),
            "review_issue_refs": [],
            "journal_head_fingerprint": "sha256:" + cutoff[8:10] * 32,
            "source_register_fingerprint": "sha256:" + "c" * 64,
            "source_baseline_fingerprint": "sha256:" + "d" * 64,
            "work_plan_fingerprint": "sha256:" + "e" * 64,
            "result": result,
        }
    )


def _family_evidence(cases: bytes, legislation: bytes) -> bytes:
    cases_document = parse_json_bytes(cases, max_bytes=16_777_216)
    legislation_document = parse_json_bytes(legislation, max_bytes=16_777_216)
    assert type(cases_document) is dict
    assert type(legislation_document) is dict
    documents: tuple[dict[str, JsonValue], dict[str, JsonValue]] = (
        cases_document,
        legislation_document,
    )
    root_cycle_id = cases_document["cycle_id"]
    assert type(root_cycle_id) is str
    children: list[JsonValue] = []
    for family, content, document in zip(
        ("CASES", "LEGISLATION"), (cases, legislation), documents, strict=True
    ):
        cycle_id = document["cycle_id"]
        manifest_fingerprint = document["fingerprint"]
        journal_head_fingerprint = document["journal_head_fingerprint"]
        result = document["result"]
        assert type(cycle_id) is str
        assert type(manifest_fingerprint) is str
        assert type(journal_head_fingerprint) is str
        assert type(result) is str
        fingerprint = f"sha256:{sha256(content).hexdigest()}"
        children.append(
            {
                "source_family": family,
                "cycle_id": cycle_id,
                "journal_ref": f"acquisition-journals/{cycle_id}",
                "manifest_fingerprint": manifest_fingerprint,
                "journal_head_fingerprint": journal_head_fingerprint,
                "result": result,
                "manifest_reference": {
                    "vault": "PRIMARY",
                    "logical_key": f"retained/{cycle_id}/{family.casefold()}.json",
                    "version_id": "v" + fingerprint[7:],
                    "fingerprint": fingerprint,
                    "byte_length": len(content),
                },
            }
        )
    return canonicalize(
        checked_json_value(
            {
                "schema_id": "asklegal.hk-v1.acceptance-family-acquisition-evidence",
                "schema_version": "1.0.0",
                "root_cycle_id": "manual-" + root_cycle_id,
                "root_plan_fingerprint": "sha256:" + "9" * 64,
                "evidence_reference": {
                    "vault": "PRIMARY",
                    "logical_key": "retained/manual/family-acquisition-evidence.json",
                    "version_id": "v" + "8" * 64,
                    "fingerprint": "sha256:" + "8" * 64,
                    "byte_length": 1,
                },
                "children": children,
            }
        )
    )


def _write_pair(
    root: Path,
    label: str,
    cutoff: str,
    *,
    content: tuple[str, str] = ("a", "b"),
    results: tuple[str, str] = ("COMPLETE", "COMPLETE"),
) -> None:
    pair = root / label
    pair.mkdir(parents=True)
    cases = _cases(cutoff, content=content[0], result=results[0])
    legislation = _legislation(cutoff, content=content[1], result=results[1])
    (pair / "cases-acquisition-manifest.json").write_bytes(cases)
    (pair / "legislation-acquisition-manifest.json").write_bytes(legislation)
    (pair / "family-acquisition-evidence.json").write_bytes(_family_evidence(cases, legislation))


def test_selects_exact_complete_two_family_cutoffs_deterministically(tmp_path: Path) -> None:
    """The same four canonical manifests always select the same exact output."""
    root = tmp_path / "retained"
    _write_pair(root, "t1", _T1)
    _write_pair(root, "t2", _T2, content=("f", "b"))

    first = selector.select_acceptance_cutoffs(root)
    second = selector.select_acceptance_cutoffs(root)

    assert first == second
    assert first == canonicalize(json.loads(first))
    document = json.loads(first)
    assert document["families"] == ["CASES", "LEGISLATION"]
    assert document["scope_ids"] == list(_SCOPES)
    assert document["t1"]["observation_cutoff"] == _T1
    assert document["t2"]["observation_cutoff"] == _T2
    assert document["t1"]["authentic_changed_families"] == []
    assert document["t2"]["authentic_changed_families"] == ["CASES"]
    assert (
        document["t1"]["family_acquisition_evidence"]["children"][0]["manifest_fingerprint"]
        == document["t1"]["cases_manifest_fingerprint"]
    )


def test_missing_or_drifted_family_evidence_cannot_be_selected(tmp_path: Path) -> None:
    """Manual T1/T2 cannot fall back to component files without retained lineage."""
    root = tmp_path / "retained"
    _write_pair(root, "t1", _T1)
    _write_pair(root, "t2", _T2, content=("f", "b"))
    evidence_path = root / "t2" / "family-acquisition-evidence.json"
    evidence_path.unlink()
    with pytest.raises(selector.AcceptanceCutoffSelectionError) as missing:
        selector.select_acceptance_cutoffs(root)
    assert missing.value.code == "COMMON_CUTOFF_INCOMPLETE"

    evidence_path.write_bytes(
        _family_evidence(
            (root / "t1" / "cases-acquisition-manifest.json").read_bytes(),
            (root / "t2" / "legislation-acquisition-manifest.json").read_bytes(),
        )
    )
    with pytest.raises(selector.AcceptanceCutoffSelectionError) as drifted:
        selector.select_acceptance_cutoffs(root)
    assert drifted.value.code == "COMMON_CUTOFF_INCOMPLETE"


@pytest.mark.parametrize("changed_family", ["CASES", "LEGISLATION"])
def test_accepts_only_digest_bound_controlling_content_delta(
    tmp_path: Path, changed_family: str
) -> None:
    """Either family's digest-bearing evidence refs may prove authentic change."""
    root = tmp_path / "retained"
    _write_pair(root, "t1", _T1)
    _write_pair(
        root,
        "t2",
        _T2,
        content=(
            "f" if changed_family == "CASES" else "a",
            "f" if changed_family == "LEGISLATION" else "b",
        ),
    )

    document = json.loads(selector.select_acceptance_cutoffs(root))

    assert document["t2"]["authentic_changed_families"] == [changed_family]


def test_cycle_cutoff_and_journal_drift_alone_is_not_authentic_change(tmp_path: Path) -> None:
    """New cycle metadata cannot masquerade as a controlling content delta."""
    root = tmp_path / "retained"
    _write_pair(root, "t1", _T1)
    _write_pair(root, "t2", _T2)

    with pytest.raises(selector.AcceptanceCutoffSelectionError) as error:
        selector.select_acceptance_cutoffs(root)

    assert error.value.code == "AUTHENTIC_CHANGE_NOT_FOUND"


@pytest.mark.parametrize(
    "failure",
    ["PAIR_CUTOFF_MISMATCH", "T1_NOT_BEFORE_T2", "CASES_INCOMPLETE", "LEGISLATION_INCOMPLETE"],
)
def test_rejects_any_non_common_or_incomplete_pair(tmp_path: Path, failure: str) -> None:
    """Both families must be exact, complete, common-cutoff pairs ordered T1 before T2."""
    root = tmp_path / "retained"
    t1 = _T2 if failure == "T1_NOT_BEFORE_T2" else _T1
    _write_pair(
        root,
        "t1",
        t1,
        results=(
            "INCOMPLETE_RETRYABLE" if failure == "CASES_INCOMPLETE" else "COMPLETE",
            "INCOMPLETE_RETRYABLE" if failure == "LEGISLATION_INCOMPLETE" else "COMPLETE",
        ),
    )
    _write_pair(root, "t2", _T2, content=("f", "b"))
    if failure == "PAIR_CUTOFF_MISMATCH":
        (root / "t2" / "legislation-acquisition-manifest.json").write_bytes(
            _legislation("1997-07-04T00:00:00Z", content="f")
        )

    with pytest.raises(selector.AcceptanceCutoffSelectionError) as error:
        selector.select_acceptance_cutoffs(root)

    assert error.value.code == "COMMON_CUTOFF_INCOMPLETE"


def test_path_escape_and_symlink_are_rejected_without_reading_outside_root(tmp_path: Path) -> None:
    """A manifest symlink cannot cross the retained-root read boundary."""
    root = tmp_path / "retained"
    outside = tmp_path / "outside.json"
    outside.write_bytes(_cases(_T1))
    _write_pair(root, "t1", _T1)
    _write_pair(root, "t2", _T2, content=("f", "b"))
    (root / "t1" / "cases-acquisition-manifest.json").unlink()
    (root / "t1" / "cases-acquisition-manifest.json").symlink_to(outside)

    with pytest.raises(selector.AcceptanceCutoffSelectionError) as error:
        selector.select_acceptance_cutoffs(root)

    assert error.value.code == "COMMON_CUTOFF_INCOMPLETE"
    assert outside.read_bytes() == _cases(_T1)


def test_cli_current_var_shape_fails_truthfully_without_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The incomplete current layout emits no JSON and returns its exact blocker."""
    root = tmp_path / "current-var-with-no-complete-pairs"
    root.mkdir()

    assert selector.main(["--retained-root", str(root)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "COMMON_CUTOFF_INCOMPLETE\n"


def test_cli_atomically_freezes_exact_canonical_selection_with_mode_0600(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An explicit output path retains exact bytes without duplicating them on stdout."""
    root = tmp_path / "retained"
    _write_pair(root, "t1", _T1)
    _write_pair(root, "t2", _T2, content=("f", "b"))
    output = tmp_path / "selection.json"

    assert selector.main(["--retained-root", str(root), "--output", str(output)]) == 0

    captured = capsys.readouterr()
    content = output.read_bytes()
    assert captured.out == ""
    assert captured.err == ""
    assert content == canonicalize(json.loads(content))
    assert output.stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".selection.json.*.tmp"))


def test_output_conflict_and_symlink_are_rejected_without_overwrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Neither an existing file nor a symlink can be replaced by the freeze operation."""
    root = tmp_path / "retained"
    _write_pair(root, "t1", _T1)
    _write_pair(root, "t2", _T2, content=("f", "b"))
    existing = tmp_path / "existing.json"
    existing.write_bytes(b"preserve")
    link = tmp_path / "link.json"
    link.symlink_to(existing)

    assert selector.main(["--retained-root", str(root), "--output", str(existing)]) == 2
    first = capsys.readouterr()
    assert first.out == ""
    assert first.err == "ACCEPTANCE_CUTOFF_OUTPUT_CONFLICT\n"
    assert existing.read_bytes() == b"preserve"

    assert selector.main(["--retained-root", str(root), "--output", str(link)]) == 2
    second = capsys.readouterr()
    assert second.out == ""
    assert second.err == "ACCEPTANCE_CUTOFF_OUTPUT_CONFLICT\n"
    assert link.is_symlink()
    assert existing.read_bytes() == b"preserve"


def test_noncanonical_or_mismatched_readback_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A publication is not reported successful unless exact canonical bytes read back."""
    root = tmp_path / "retained"
    _write_pair(root, "t1", _T1)
    _write_pair(root, "t2", _T2, content=("f", "b"))
    output = tmp_path / "selection.json"
    original_read = selector._read_output  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001

    def noncanonical(path: Path) -> bytes:
        return original_read(path) + b"\n"

    monkeypatch.setattr(selector, "_read_output", noncanonical)

    assert selector.main(["--retained-root", str(root), "--output", str(output)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "ACCEPTANCE_CUTOFF_OUTPUT_READBACK_FAILED\n"


def test_output_path_must_be_absolute(tmp_path: Path) -> None:
    """The CLI refuses a location whose identity depends on the process working directory."""
    root = tmp_path / "retained"
    _write_pair(root, "t1", _T1)
    _write_pair(root, "t2", _T2, content=("f", "b"))

    assert selector.main(["--retained-root", str(root), "--output", "selection.json"]) == 2
