"""Closed conformance tests for the local architecture proof."""

from dataclasses import replace
from pathlib import Path

from tools.architecture_spike import (
    MANIFEST_PATH,
    ArchitectureCode,
    ArchitecturePolicy,
    MemberPolicy,
    check_architecture,
    check_repository,
    load_policy,
    run_spike,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _policy() -> ArchitecturePolicy:
    return ArchitecturePolicy(
        members=(
            MemberPolicy(
                distribution="asklegal-base",
                module="asklegal_base",
                path="packages/base",
                kind="package",
                role="base",
                allowed_internal_distributions=(),
                allowed_external_distributions=(),
                capability_ports=(),
            ),
            MemberPolicy(
                distribution="asklegal-worker",
                module="asklegal_worker",
                path="apps/worker",
                kind="application",
                role="worker",
                allowed_internal_distributions=("asklegal-base", "asklegal-z-adapter"),
                allowed_external_distributions=(),
                capability_ports=("exclusive_effect",),
            ),
            MemberPolicy(
                distribution="asklegal-z-adapter",
                module="asklegal_z_adapter",
                path="packages/z-adapter",
                kind="package",
                role="adapter",
                allowed_internal_distributions=("asklegal-base",),
                allowed_external_distributions=(),
                capability_ports=(),
            ),
        ),
        exclusive_capability_owners={"exclusive_effect": "asklegal-worker"},
        fingerprint="sha256:synthetic",
    )


def _write_member(root: Path, member: MemberPolicy) -> None:
    member_root = root / member.path
    dependencies = "\n".join(
        f'  "{dependency}",' for dependency in member.allowed_internal_distributions
    )
    sources = "\n".join(
        f"{dependency} = {{ workspace = true }}"
        for dependency in member.allowed_internal_distributions
    )
    pyproject = (
        "[project]\n"
        f'name = "{member.distribution}"\n'
        'version = "0.0.0"\n'
        'requires-python = "==3.14.7"\n'
        f"dependencies = [\n{dependencies}\n]\n\n"
        '[build-system]\nrequires = ["uv-build==0.12.5"]\n'
        'build-backend = "uv_build"\n\n'
        "[tool.uv.build-backend]\n"
        f'module-name = "{member.module}"\n\n'
        f"[tool.uv.sources]\n{sources}\n"
    )
    member_root.mkdir(parents=True, exist_ok=True)
    (member_root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    module_root = member_root / "src" / member.module
    module_root.mkdir(parents=True)
    declaration = (
        f'APPLICATION_NAME: str = "{member.role}"\n'
        f"CAPABILITY_PORTS: tuple[str, ...] = {member.capability_ports!r}\n"
        if member.kind == "application"
        else f'PACKAGE_ROLE: str = "{member.role}"\n'
    )
    (module_root / "__init__.py").write_text(declaration, encoding="utf-8")


def _write_repository(root: Path, policy: ArchitecturePolicy) -> None:
    workspace_members = "\n".join(f'  "{member.path}",' for member in policy.members)
    (root / "pyproject.toml").write_text(
        f"[tool.uv.workspace]\nmembers = [\n{workspace_members}\n]\n",
        encoding="utf-8",
    )
    for member in policy.members:
        _write_member(root, member)


def _codes(root: Path, policy: ArchitecturePolicy) -> set[ArchitectureCode]:
    return {finding.code for finding in check_architecture(root, policy)}


def test_real_repository_has_exact_closed_architecture() -> None:
    """Prove every current workspace member and exclusive effect is governed."""
    policy = load_policy(REPOSITORY_ROOT / MANIFEST_PATH)
    report = run_spike(REPOSITORY_ROOT)
    assert check_repository(REPOSITORY_ROOT) == ()
    assert report.applications == 5
    assert report.packages == 14
    assert report.dependency_edges == 80
    assert report.capability_ports == 31
    assert policy.exclusive_capability_owners == {
        "approval_command": "asklegal-review-api",
        "asklegal_routing": "asklegal-promotion-worker",
        "backup_mutation": "asklegal-promotion-worker",
        "embedding_provider": "asklegal-promotion-worker",
        "external_source_read": "asklegal-acquisition-worker",
        "generative_llm_provider": "asklegal-legal-processing-worker",
        "pinecone_mutation": "asklegal-promotion-worker",
        "proposal_package_prepare": "asklegal-control-plane",
        "recovery_copy": "asklegal-promotion-worker",
        "revocation_command": "asklegal-review-api",
    }
    members = {member.distribution: member for member in policy.members}
    control = members["asklegal-control-plane"]
    assert {
        "asklegal-corpus",
        "asklegal-evidence-vault",
        "asklegal-promotion",
    } <= set(control.allowed_internal_distributions)
    assert "proposal_package_prepare" in control.capability_ports
    assert "proposal_package_prepare" not in members["asklegal-promotion-worker"].capability_ports
    assert members["asklegal-acquisition-worker"].allowed_external_distributions == ("patchright",)
    assert all(
        members[name].allowed_external_distributions == ()
        for name in (
            "asklegal-legal-processing-worker",
            "asklegal-promotion-worker",
        )
    )


def test_future_member_cannot_escape_policy(tmp_path: Path) -> None:
    """Fail closed when a future workspace package is not added to the manifest."""
    policy = _policy()
    _write_repository(tmp_path, policy)
    future = tmp_path / "packages" / "future"
    future.mkdir(parents=True)
    (future / "pyproject.toml").write_text("[project]\nname = 'future'\n", encoding="utf-8")
    assert ArchitectureCode.MEMBER_COVERAGE in _codes(tmp_path, policy)


def test_import_and_capability_drift_are_rejected(tmp_path: Path) -> None:
    """Reject undeclared internal imports and application authority drift."""
    policy = _policy()
    _write_repository(tmp_path, policy)
    (tmp_path / "packages/base/src/asklegal_base/__init__.py").write_text(
        'PACKAGE_ROLE: str = "base"\nimport asklegal_z_adapter\n',
        encoding="utf-8",
    )
    (tmp_path / "apps/worker/src/asklegal_worker/__init__.py").write_text(
        'APPLICATION_NAME: str = "worker"\nCAPABILITY_PORTS: tuple[str, ...] = ()\n',
        encoding="utf-8",
    )
    assert {ArchitectureCode.IMPORT, ArchitectureCode.CAPABILITY} <= _codes(tmp_path, policy)


def test_packages_cannot_depend_on_applications(tmp_path: Path) -> None:
    """Reject any package-to-application dependency even if policy text lists it."""
    policy = _policy()
    base = replace(policy.members[0], allowed_internal_distributions=("asklegal-worker",))
    changed = replace(policy, members=(base, *policy.members[1:]))
    _write_repository(tmp_path, changed)
    assert ArchitectureCode.DEPENDENCY in _codes(tmp_path, changed)


def test_internal_dependency_cycles_are_rejected(tmp_path: Path) -> None:
    """Reject a policy and metadata pair that form an internal package cycle."""
    policy = _policy()
    base = replace(policy.members[0], allowed_internal_distributions=("asklegal-z-adapter",))
    changed = replace(policy, members=(base, *policy.members[1:]))
    _write_repository(tmp_path, changed)
    assert ArchitectureCode.CYCLE in _codes(tmp_path, changed)
