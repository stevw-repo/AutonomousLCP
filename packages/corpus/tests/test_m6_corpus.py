"""M6 immutable release, desired-state, coverage, and proposal proofs."""

from hashlib import sha256
from pathlib import Path

import pytest
from asklegal_contracts import SchemaRegistry, parse_json_bytes
from asklegal_corpus import (
    PROPOSAL_ROLE_PATHS,
    CorpusError,
    CorpusErrorCode,
    CorpusRelease,
    CorpusReleaseInput,
    CoverageScopeStatus,
    CoverageState,
    CoverageWarning,
    ProposalPackageInput,
    ServingRecord,
    SourceCoverageCycleBinding,
    compose_desired_state,
    freeze_corpus_release,
    freeze_coverage_status,
    freeze_proposal_package,
    freeze_v1_coverage_status,
    serving_payload_fingerprint,
    source_coverage_cycle_binding_from_json,
    verify_v1_coverage_release_gate,
)

_NOW = "2026-08-16T00:00:00Z"


def _source_cycle(
    *,
    accounting_complete: bool = True,
    release_blocking: bool = False,
    missing_source_ids: tuple[str, ...] = (),
    gap_source_ids: tuple[str, ...] = (),
) -> SourceCoverageCycleBinding:
    return SourceCoverageCycleBinding(
        "PRIMARY",
        "poc/report/source-coverage-cycle/full_periodic/" + "a" * 64,
        "v" + "b" * 64,
        "sha256:" + "a" * 64,
        1024,
        _NOW,
        accounting_complete,
        release_blocking,
        missing_source_ids,
        (),
        gap_source_ids,
    )


def _record(identity: str = "1", *, scope: str = "scope-a") -> ServingRecord:
    return ServingRecord(
        "rec_" + identity * 48,
        f"Synthetic legal text for {scope}.",
        "ZZZ",
        "zzz",
        "TEST_LEGAL_MATERIAL",
        "synthetic-source",
        "Synthetic authority only.",
        "art_" + identity * 48,
        ("evi_" + identity * 48,),
    )


def _release(scope: str, record: ServingRecord) -> CorpusRelease:
    return freeze_corpus_release(
        CorpusReleaseInput(
            scope,
            _NOW,
            ("evi_" + "1" * 48,),
            ("val_" + "1" * 48,),
        ),
        (record,),
    )


def test_release_and_desired_state_are_complete_deterministic_and_exact() -> None:
    """Selection order cannot change a release or flattened desired state."""
    first = _record("1", scope="scope-a")
    second = _record("2", scope="scope-b")
    release_a = _release("scope-a", first)
    release_b = _release("scope-b", second)
    desired = compose_desired_state(
        ("scope-a", "scope-b"),
        (release_b, release_a),
        target_key="zzz-test",
        observation_cutoff=_NOW,
    )
    repeated = compose_desired_state(
        ("scope-a", "scope-b"),
        (release_a, release_b),
        target_key="zzz-test",
        observation_cutoff=_NOW,
    )
    assert desired == repeated
    assert tuple(item.record_id for item in desired.records) == (first.record_id, second.record_id)
    assert desired.records[0].content_fingerprint == serving_payload_fingerprint(first)


def test_release_and_desired_state_reject_ambiguous_or_unaccounted_inputs() -> None:
    """Duplicates, missing scopes, and unexplained empty scopes fail closed."""
    record = _record()
    with pytest.raises(CorpusError) as empty:
        freeze_corpus_release(CorpusReleaseInput("scope-a", _NOW, ("evi_x",), ("val_x",)), ())
    assert empty.value.code is CorpusErrorCode.ZERO_RECORD_UNJUSTIFIED
    with pytest.raises(CorpusError) as duplicate:
        freeze_corpus_release(
            CorpusReleaseInput("scope-a", _NOW, ("evi_x",), ("val_x",)),
            (record, record),
        )
    assert duplicate.value.code is CorpusErrorCode.DUPLICATE_RECORD
    with pytest.raises(CorpusError) as missing:
        compose_desired_state(
            ("scope-a", "scope-b"),
            (_release("scope-a", record),),
            target_key="zzz-test",
            observation_cutoff=_NOW,
        )
    assert missing.value.code is CorpusErrorCode.RELEASE_SCOPE_MISMATCH


def test_coverage_is_complete_and_warning_codes_cannot_drift() -> None:
    """Every expected scope has one evidence-consistent user-facing state."""
    statuses = (
        CoverageScopeStatus(
            "scope-a", CoverageState.CURRENT, _NOW, (), (), (), CoverageWarning.NONE
        ),
        CoverageScopeStatus(
            "scope-b",
            CoverageState.KNOWN_GAP,
            _NOW,
            ("gap_" + "2" * 48,),
            (),
            (),
            CoverageWarning.KNOWN_GAP,
        ),
    )
    manifest = freeze_coverage_status("srv_" + "1" * 48, _NOW, ("scope-a", "scope-b"), statuses)
    assert tuple(item.scope_id for item in manifest.scopes) == ("scope-a", "scope-b")
    with pytest.raises(CorpusError) as mismatch:
        freeze_coverage_status(
            manifest.serving_state_id,
            _NOW,
            ("scope-a", "scope-b"),
            (statuses[0],),
        )
    assert mismatch.value.code is CorpusErrorCode.COVERAGE_INCOMPLETE
    with pytest.raises(CorpusError):
        freeze_coverage_status(
            manifest.serving_state_id,
            _NOW,
            ("scope-a",),
            (
                CoverageScopeStatus(
                    "scope-a",
                    CoverageState.CURRENT,
                    _NOW,
                    (),
                    (),
                    (),
                    CoverageWarning.KNOWN_GAP,
                ),
            ),
        )


def test_v1_coverage_binds_the_exact_source_cycle_and_blocks_release_wide_gaps() -> None:
    """A release-blocking source cycle becomes fail-visible in every expected scope."""
    cycle = _source_cycle(
        release_blocking=True,
        gap_source_ids=("HK-LEG-GLD-EGAZETTE",),
    )
    manifest = freeze_v1_coverage_status(
        "srv_" + "1" * 48,
        _NOW,
        ("scope-a", "scope-b"),
        (
            CoverageScopeStatus(
                "scope-a", CoverageState.CURRENT, _NOW, (), (), (), CoverageWarning.NONE
            ),
            CoverageScopeStatus(
                "scope-b", CoverageState.CURRENT, _NOW, (), (), (), CoverageWarning.NONE
            ),
        ),
        cycle,
    )

    assert manifest.source_cycle == cycle
    assert all(scope.status is CoverageState.NOT_READY for scope in manifest.scopes)
    assert all(scope.warning is CoverageWarning.NOT_READY for scope in manifest.scopes)
    assert all(scope.source_failure_refs for scope in manifest.scopes)
    assert b'"source_cycle":' in manifest.canonical_bytes
    with pytest.raises(CorpusError) as blocked:
        verify_v1_coverage_release_gate(manifest)
    assert blocked.value.code is CorpusErrorCode.COVERAGE_INCOMPLETE


def test_v1_release_gate_requires_complete_nonblocking_source_cycle() -> None:
    """The V1 release gate accepts only an exact complete source-cycle binding."""
    status = CoverageScopeStatus(
        "scope-a", CoverageState.CURRENT, _NOW, (), (), (), CoverageWarning.NONE
    )
    manifest = freeze_v1_coverage_status(
        "srv_" + "1" * 48,
        _NOW,
        ("scope-a",),
        (status,),
        _source_cycle(),
    )

    verify_v1_coverage_release_gate(manifest)

    without_cycle = freeze_coverage_status(
        manifest.serving_state_id,
        _NOW,
        ("scope-a",),
        (status,),
    )
    with pytest.raises(CorpusError, match="source cycle missing"):
        verify_v1_coverage_release_gate(without_cycle)

    incomplete = _source_cycle(
        accounting_complete=False,
        missing_source_ids=("HK-LEG-HKEL-CURRENT-INVENTORY",),
    )
    incomplete_manifest = freeze_v1_coverage_status(
        manifest.serving_state_id,
        _NOW,
        ("scope-a",),
        (status,),
        incomplete,
    )
    with pytest.raises(CorpusError, match="source cycle accounting"):
        verify_v1_coverage_release_gate(incomplete_manifest)


def test_acquisition_source_cycle_handoff_parses_without_losing_exact_identity() -> None:
    """The acquisition result projection maps exactly into corpus coverage authority."""
    cycle = _source_cycle()
    parsed = source_coverage_cycle_binding_from_json(
        {
            "accounting_complete": cycle.accounting_complete,
            "byte_length": cycle.byte_length,
            "duplicate_source_ids": list(cycle.duplicate_source_ids),
            "fingerprint": cycle.fingerprint,
            "gap_source_ids": list(cycle.gap_source_ids),
            "logical_key": cycle.logical_key,
            "missing_source_ids": list(cycle.missing_source_ids),
            "observation_cutoff": cycle.observation_cutoff,
            "release_blocking": cycle.release_blocking,
            "vault": cycle.vault,
            "version_id": cycle.version_id,
        }
    )

    assert parsed == cycle
    with pytest.raises(CorpusError, match="source cycle handoff"):
        source_coverage_cycle_binding_from_json({"release_blocking": False})
    with pytest.raises(CorpusError, match="source cycle handoff"):
        source_coverage_cycle_binding_from_json({"unsupported": object()})


def test_proposal_package_commits_the_exact_schema_valid_inventory_last() -> None:
    """One immutable root fingerprint covers every canonical review artifact."""
    contents = {role: ("{}\n" + role).encode() for role in PROPOSAL_ROLE_PATHS}
    promotion_fingerprint = "sha256:" + sha256(contents["PROMOTION_MANIFEST"]).hexdigest()
    package = freeze_proposal_package(
        contents,
        ProposalPackageInput(
            _NOW,
            "pmn_" + "1" * 48,
            promotion_fingerprint,
            "srv_" + "2" * 48,
            "sha256:" + "b" * 64,
            "srv_" + "3" * 48,
            "sha256:" + "c" * 64,
        ),
    )
    assert len(package.artifacts) == len(PROPOSAL_ROLE_PATHS) == 11
    assert all(item.content == contents[item.role] for item in package.artifacts)
    value = parse_json_bytes(package.manifest_bytes, max_bytes=100_000)
    registry = SchemaRegistry.from_contracts_root(Path(__file__).parents[3] / "contracts")
    registry.validate(
        value,
        "schemas/promotion-domain.schema.json#/$defs/proposal_package_manifest",
    )
    changed = dict(contents)
    changed["VALIDATION"] = b"changed"
    assert (
        freeze_proposal_package(
            changed,
            ProposalPackageInput(
                _NOW,
                "pmn_" + "1" * 48,
                promotion_fingerprint,
                "srv_" + "2" * 48,
                "sha256:" + "b" * 64,
                "srv_" + "3" * 48,
                "sha256:" + "c" * 64,
            ),
        ).fingerprint
        != package.fingerprint
    )
