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
    compose_desired_state,
    freeze_corpus_release,
    freeze_coverage_status,
    freeze_proposal_package,
    serving_payload_fingerprint,
)

_NOW = "2026-08-16T00:00:00Z"


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
