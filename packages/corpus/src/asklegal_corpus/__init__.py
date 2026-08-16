"""Immutable release, desired-state, coverage, and proposal construction."""

from .builder import (
    PROPOSAL_ROLE_PATHS,
    compose_desired_state,
    freeze_corpus_release,
    freeze_coverage_status,
    freeze_proposal_package,
    serving_payload_fingerprint,
)
from .model import (
    CorpusError,
    CorpusErrorCode,
    CorpusRelease,
    CorpusReleaseInput,
    CoverageScopeStatus,
    CoverageState,
    CoverageStatusManifest,
    CoverageWarning,
    DesiredStateInventory,
    FlattenedRecord,
    ProposalArtifact,
    ProposalPackage,
    ProposalPackageInput,
    ReleaseRecordEntry,
    ServingRecord,
)

PACKAGE_ROLE: str = "corpus"

__all__ = [
    "PACKAGE_ROLE",
    "PROPOSAL_ROLE_PATHS",
    "CorpusError",
    "CorpusErrorCode",
    "CorpusRelease",
    "CorpusReleaseInput",
    "CoverageScopeStatus",
    "CoverageState",
    "CoverageStatusManifest",
    "CoverageWarning",
    "DesiredStateInventory",
    "FlattenedRecord",
    "ProposalArtifact",
    "ProposalPackage",
    "ProposalPackageInput",
    "ReleaseRecordEntry",
    "ServingRecord",
    "compose_desired_state",
    "freeze_corpus_release",
    "freeze_coverage_status",
    "freeze_proposal_package",
    "serving_payload_fingerprint",
]
