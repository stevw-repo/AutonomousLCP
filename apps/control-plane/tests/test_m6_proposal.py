"""M6 control-plane manifest-last proposal preparation proof."""

from hashlib import sha256
from pathlib import Path

from asklegal_control_plane import ProposalPreparationService
from asklegal_corpus import PROPOSAL_ROLE_PATHS, ProposalPackageInput


def test_control_plane_prepares_and_reads_back_one_exact_proposal() -> None:
    """Only the control service commits the schema-valid root after all members."""
    contents = {role: ("{}\n" + role).encode() for role in PROPOSAL_ROLE_PATHS}
    promotion_fingerprint = "sha256:" + sha256(contents["PROMOTION_MANIFEST"]).hexdigest()
    service = ProposalPreparationService(Path(__file__).parents[3] / "contracts")
    package = service.prepare(
        contents,
        ProposalPackageInput(
            "2026-08-16T00:00:00Z",
            "pmn_" + "1" * 48,
            promotion_fingerprint,
            "srv_" + "2" * 48,
            "sha256:" + "b" * 64,
            "srv_" + "3" * 48,
            "sha256:" + "c" * 64,
        ),
    )
    assert service.read(package.package_id) == package
    assert (
        service.prepare(
            contents,
            ProposalPackageInput(
                "2026-08-16T00:00:00Z",
                "pmn_" + "1" * 48,
                promotion_fingerprint,
                "srv_" + "2" * 48,
                "sha256:" + "b" * 64,
                "srv_" + "3" * 48,
                "sha256:" + "c" * 64,
            ),
        )
        == package
    )
