"""M6 manifest-last proposal-package preparation owned by the control plane."""

from collections.abc import Mapping
from pathlib import Path

from asklegal_contracts import SchemaRegistry, parse_json_bytes
from asklegal_corpus import (
    CorpusError,
    CorpusErrorCode,
    ProposalPackage,
    ProposalPackageInput,
    freeze_proposal_package,
)


class ProposalPreparationService:
    """Validate, freeze, store, and read back immutable local proposal packages."""

    def __init__(self, contracts_root: Path) -> None:
        """Load the closed repository schema registry and an empty local store."""
        self._schemas = SchemaRegistry.from_contracts_root(contracts_root)
        self._packages: dict[str, ProposalPackage] = {}

    def prepare(
        self,
        contents_by_role: Mapping[str, bytes],
        inputs: ProposalPackageInput,
    ) -> ProposalPackage:
        """Commit a schema-valid proposal root only after every member is frozen."""
        package = freeze_proposal_package(contents_by_role, inputs)
        value = parse_json_bytes(package.manifest_bytes, max_bytes=1_000_000)
        self._schemas.validate(
            value,
            "schemas/promotion-domain.schema.json#/$defs/proposal_package_manifest",
        )
        existing = self._packages.get(package.package_id)
        if existing is not None and existing != package:
            raise CorpusError(CorpusErrorCode.FINGERPRINT_MISMATCH, "package collision")
        self._packages[package.package_id] = package
        if self.read(package.package_id) != package:
            raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN, "read-back")
        return package

    def read(self, package_id: str) -> ProposalPackage:
        """Read back one exact immutable proposal package."""
        try:
            return self._packages[package_id]
        except KeyError as error:
            raise CorpusError(CorpusErrorCode.PROPOSAL_NOT_FROZEN) from error
