"""Fail-closed local proof of monorepo dependencies and capability ownership."""

import argparse
import ast
import hashlib
import json
import re
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

MANIFEST_PATH = Path("tools/architecture_spike_manifest.json")
_MEMBER_ROOTS = ("apps", "packages")
_DISTRIBUTION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")

type JsonValue = bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None


class ArchitectureCode(StrEnum):
    """Stable failure codes for the architecture proof."""

    POLICY = "ARCH001"
    MEMBER_COVERAGE = "ARCH002"
    MEMBER_METADATA = "ARCH003"
    DEPENDENCY = "ARCH004"
    WORKSPACE_SOURCE = "ARCH005"
    IMPORT = "ARCH006"
    CYCLE = "ARCH007"
    DECLARATION = "ARCH008"
    CAPABILITY = "ARCH009"


class ArchitectureFailure(RuntimeError):
    """The checked-in architecture policy cannot be parsed safely."""


@dataclass(frozen=True, order=True, slots=True)
class Finding:
    """One deterministic architecture-policy violation."""

    path: str
    line: int
    code: ArchitectureCode
    detail: str


@dataclass(frozen=True, slots=True)
class MemberPolicy:
    """One exact workspace member and its direct authority boundary."""

    distribution: str
    module: str
    path: str
    kind: str
    role: str
    allowed_internal_distributions: tuple[str, ...]
    allowed_external_distributions: tuple[str, ...]
    capability_ports: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchitecturePolicy:
    """Closed policy for every package, application, and exclusive capability."""

    members: tuple[MemberPolicy, ...]
    exclusive_capability_owners: dict[str, str]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class ArchitectureReport:
    """Canonical successful proof summary."""

    applications: int
    packages: int
    dependency_edges: int
    capability_ports: int
    policy_fingerprint: str

    def to_json(self) -> dict[str, JsonValue]:
        """Return one deterministic JSON representation."""
        return {
            "applications": self.applications,
            "capability_ports": self.capability_ports,
            "dependency_edges": self.dependency_edges,
            "packages": self.packages,
            "policy_fingerprint": self.policy_fingerprint,
        }


def load_policy(path: Path) -> ArchitecturePolicy:
    """Load and strictly validate the checked-in architecture policy."""
    raw_value = cast("object", json.loads(path.read_text(encoding="utf-8")))
    raw = _mapping(raw_value, "policy")
    _require_keys(raw, {"exclusive_capability_owners", "members", "schema_version"}, "policy")
    if _integer(raw["schema_version"], "policy.schema_version") != 1:
        raise ArchitectureFailure("ARCH_POLICY_SCHEMA")
    member_values = _sequence(raw["members"], "policy.members")
    members: list[MemberPolicy] = []
    for index, value in enumerate(member_values):
        location = f"policy.members[{index}]"
        member = _mapping(value, location)
        _require_keys(
            member,
            {
                "allowed_external_distributions",
                "allowed_internal_distributions",
                "capability_ports",
                "distribution",
                "kind",
                "module",
                "path",
                "role",
            },
            location,
        )
        members.append(
            MemberPolicy(
                distribution=_string(member["distribution"], f"{location}.distribution"),
                module=_string(member["module"], f"{location}.module"),
                path=_relative_path(member["path"], f"{location}.path"),
                kind=_string(member["kind"], f"{location}.kind"),
                role=_string(member["role"], f"{location}.role"),
                allowed_internal_distributions=_string_tuple(
                    member["allowed_internal_distributions"], f"{location}.internal"
                ),
                allowed_external_distributions=_string_tuple(
                    member["allowed_external_distributions"], f"{location}.external"
                ),
                capability_ports=_string_tuple(
                    member["capability_ports"], f"{location}.capabilities"
                ),
            )
        )
    owners_raw = _mapping(raw["exclusive_capability_owners"], "policy.exclusive owners")
    owners = {
        capability: _string(owner, f"exclusive owner {capability}")
        for capability, owner in owners_raw.items()
    }
    policy = ArchitecturePolicy(
        members=tuple(members),
        exclusive_capability_owners=owners,
        fingerprint=f"sha256:{hashlib.sha256(_canonical_json(raw)).hexdigest()}",
    )
    _validate_policy(policy)
    return policy


def check_architecture(root: Path, policy: ArchitecturePolicy) -> tuple[Finding, ...]:
    """Check workspace coverage, metadata, imports, cycles, and capabilities."""
    findings: list[Finding] = []
    by_distribution = {member.distribution: member for member in policy.members}
    by_module = {member.module: member for member in policy.members}
    expected_paths = {member.path for member in policy.members}
    discovered_paths = _discover_member_paths(root)
    if expected_paths != discovered_paths:
        findings.append(
            Finding(
                "pyproject.toml",
                1,
                ArchitectureCode.MEMBER_COVERAGE,
                _set_difference("workspace member", expected_paths, discovered_paths),
            )
        )
    workspace_paths = _root_workspace_paths(root, findings)
    if workspace_paths != discovered_paths:
        findings.append(
            Finding(
                "pyproject.toml",
                1,
                ArchitectureCode.MEMBER_COVERAGE,
                _set_difference("root workspace", discovered_paths, workspace_paths),
            )
        )

    graph: dict[str, set[str]] = {member.distribution: set() for member in policy.members}
    for member in policy.members:
        _check_member_metadata(root, member, by_distribution, graph, findings)
        _check_boundary_declaration(root, member, findings)
        _check_imports(root, member, by_module, findings)
    _check_member_direction(policy, graph, findings)
    _check_cycles(graph, findings)
    _check_exclusive_capabilities(policy, findings)
    return tuple(sorted(findings))


def check_repository(root: Path) -> tuple[Finding, ...]:
    """Apply the checked-in architecture policy to the repository."""
    return check_architecture(root, load_policy(root / MANIFEST_PATH))


def run_spike(root: Path) -> ArchitectureReport:
    """Require a clean architecture proof and return its exact summary."""
    policy = load_policy(root / MANIFEST_PATH)
    findings = check_architecture(root, policy)
    if findings:
        first = findings[0]
        raise ArchitectureFailure(f"{first.code}: {first.path}:{first.line}: {first.detail}")
    return ArchitectureReport(
        applications=sum(member.kind == "application" for member in policy.members),
        packages=sum(member.kind == "package" for member in policy.members),
        dependency_edges=sum(
            len(member.allowed_internal_distributions) for member in policy.members
        ),
        capability_ports=sum(len(member.capability_ports) for member in policy.members),
        policy_fingerprint=policy.fingerprint,
    )


def _validate_policy(policy: ArchitecturePolicy) -> None:
    members = policy.members
    if tuple(sorted(members, key=lambda item: item.distribution)) != members:
        raise ArchitectureFailure("ARCH_POLICY_MEMBERS_NOT_SORTED")
    distributions = {member.distribution for member in members}
    modules = {member.module for member in members}
    paths = {member.path for member in members}
    roles = {member.role for member in members}
    if not members or min(len(distributions), len(modules), len(paths), len(roles)) != len(members):
        raise ArchitectureFailure("ARCH_POLICY_MEMBER_IDENTITY_DUPLICATE")
    for member in members:
        if member.kind not in {"application", "package"}:
            raise ArchitectureFailure("ARCH_POLICY_KIND")
        expected_prefix = "apps/" if member.kind == "application" else "packages/"
        if not member.path.startswith(expected_prefix):
            raise ArchitectureFailure("ARCH_POLICY_PATH_KIND")
        for values in (
            member.allowed_internal_distributions,
            member.allowed_external_distributions,
            member.capability_ports,
        ):
            if tuple(sorted(set(values))) != values:
                raise ArchitectureFailure("ARCH_POLICY_VALUES_NOT_CLOSED")
        if member.kind == "package" and member.capability_ports:
            raise ArchitectureFailure("ARCH_POLICY_PACKAGE_CAPABILITY")
        if member.distribution in member.allowed_internal_distributions:
            raise ArchitectureFailure("ARCH_POLICY_SELF_DEPENDENCY")
        if not set(member.allowed_internal_distributions) <= distributions:
            raise ArchitectureFailure("ARCH_POLICY_UNKNOWN_DEPENDENCY")
    if set(policy.exclusive_capability_owners.values()) - distributions:
        raise ArchitectureFailure("ARCH_POLICY_UNKNOWN_CAPABILITY_OWNER")
    if tuple(sorted(policy.exclusive_capability_owners)) != tuple(
        policy.exclusive_capability_owners
    ):
        raise ArchitectureFailure("ARCH_POLICY_EXCLUSIVE_NOT_SORTED")


def _check_member_metadata(
    root: Path,
    member: MemberPolicy,
    by_distribution: Mapping[str, MemberPolicy],
    graph: dict[str, set[str]],
    findings: list[Finding],
) -> None:
    path = root / member.path / "pyproject.toml"
    if not path.is_file():
        return
    metadata = _toml(path)
    project = _object_mapping(metadata.get("project"), f"{member.path}.project")
    tool = _object_mapping(metadata.get("tool"), f"{member.path}.tool")
    uv = _object_mapping(tool.get("uv"), f"{member.path}.tool.uv")
    backend = _object_mapping(uv.get("build-backend"), f"{member.path}.build-backend")
    if project.get("name") != member.distribution or backend.get("module-name") != member.module:
        findings.append(
            Finding(member.path, 1, ArchitectureCode.MEMBER_METADATA, "identity metadata mismatch")
        )
    dependencies_value = project.get("dependencies")
    if not isinstance(dependencies_value, list):
        findings.append(
            Finding(member.path, 1, ArchitectureCode.MEMBER_METADATA, "dependencies not strings")
        )
        return
    dependency_objects = cast("list[object]", dependencies_value)
    if not all(isinstance(item, str) for item in dependency_objects):
        findings.append(
            Finding(member.path, 1, ArchitectureCode.MEMBER_METADATA, "dependencies not strings")
        )
        return
    dependency_strings = cast("list[str]", dependency_objects)
    dependencies = {_requirement_name(item) for item in dependency_strings}
    internal = dependencies & set(by_distribution)
    external = dependencies - set(by_distribution)
    graph[member.distribution].update(internal)
    if internal != set(member.allowed_internal_distributions):
        findings.append(
            Finding(
                member.path,
                1,
                ArchitectureCode.DEPENDENCY,
                _set_difference(
                    "internal dependency", set(member.allowed_internal_distributions), internal
                ),
            )
        )
    if external != set(member.allowed_external_distributions):
        findings.append(
            Finding(
                member.path,
                1,
                ArchitectureCode.DEPENDENCY,
                _set_difference(
                    "external dependency", set(member.allowed_external_distributions), external
                ),
            )
        )
    sources_value = uv.get("sources", {})
    sources = _object_mapping(sources_value, f"{member.path}.tool.uv.sources")
    source_names = {_normalize_distribution(name) for name in sources}
    if source_names != internal or any(
        _object_mapping(value, "workspace source") != {"workspace": True}
        for value in sources.values()
    ):
        findings.append(
            Finding(
                member.path,
                1,
                ArchitectureCode.WORKSPACE_SOURCE,
                "workspace source declarations do not equal internal dependencies",
            )
        )


def _check_boundary_declaration(root: Path, member: MemberPolicy, findings: list[Finding]) -> None:
    path = root / member.path / "src" / member.module / "__init__.py"
    if not path.is_file():
        findings.append(
            Finding(member.path, 1, ArchitectureCode.DECLARATION, "boundary module missing")
        )
        return
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    values = _literal_assignments(tree)
    name_key = "APPLICATION_NAME" if member.kind == "application" else "PACKAGE_ROLE"
    if values.get(name_key) != member.role:
        findings.append(
            Finding(member.path, 1, ArchitectureCode.DECLARATION, f"{name_key} mismatch")
        )
    if member.kind == "application":
        capabilities = values.get("CAPABILITY_PORTS")
        if capabilities != member.capability_ports:
            findings.append(
                Finding(
                    member.path,
                    1,
                    ArchitectureCode.CAPABILITY,
                    "declared capability ports do not equal policy",
                )
            )


def _check_imports(
    root: Path,
    member: MemberPolicy,
    by_module: Mapping[str, MemberPolicy],
    findings: list[Finding],
) -> None:
    allowed = set(member.allowed_internal_distributions) | {member.distribution}
    source_root = root / member.path
    paths = {
        path
        for child in ("src", "tests")
        for path in (source_root / child).glob("**/*.py")
        if path.is_file()
    }
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=relative)
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _check_import_root(
                        alias.name, node.lineno, relative, allowed, by_module, findings
                    )
                continue
            if isinstance(node, ast.ImportFrom):
                if node.level == 0:
                    module = node.module or ""
                if module:
                    _check_import_root(module, node.lineno, relative, allowed, by_module, findings)


def _check_import_root(
    module: str,
    line: int,
    path: str,
    allowed: set[str],
    by_module: Mapping[str, MemberPolicy],
    findings: list[Finding],
) -> None:
    root = module.partition(".")[0]
    target = by_module.get(root)
    if target is None:
        if root.startswith("asklegal_"):
            findings.append(
                Finding(path, line, ArchitectureCode.IMPORT, f"unowned internal import {module!r}")
            )
        return
    if target.distribution not in allowed:
        findings.append(
            Finding(
                path,
                line,
                ArchitectureCode.IMPORT,
                f"{module!r} is outside the member's direct dependency boundary",
            )
        )


def _check_member_direction(
    policy: ArchitecturePolicy,
    graph: Mapping[str, set[str]],
    findings: list[Finding],
) -> None:
    kinds = {member.distribution: member.kind for member in policy.members}
    for source, targets in graph.items():
        for target in targets:
            if kinds[target] == "application":
                findings.append(
                    Finding(
                        source,
                        1,
                        ArchitectureCode.DEPENDENCY,
                        f"member depends on application {target!r}",
                    )
                )


def _check_cycles(graph: Mapping[str, set[str]], findings: list[Finding]) -> None:
    visiting: set[str] = set()
    complete: set[str] = set()

    def visit(node: str, trail: tuple[str, ...]) -> None:
        if node in complete:
            return
        if node in visiting:
            cycle = (*trail[trail.index(node) :], node)
            findings.append(Finding(node, 1, ArchitectureCode.CYCLE, " -> ".join(cycle)))
            return
        visiting.add(node)
        for target in sorted(graph[node]):
            visit(target, (*trail, node))
        visiting.remove(node)
        complete.add(node)

    for node in sorted(graph):
        visit(node, ())


def _check_exclusive_capabilities(policy: ArchitecturePolicy, findings: list[Finding]) -> None:
    owners: dict[str, list[str]] = {}
    for member in policy.members:
        for capability in member.capability_ports:
            owners.setdefault(capability, []).append(member.distribution)
    for capability, expected_owner in policy.exclusive_capability_owners.items():
        if owners.get(capability) != [expected_owner]:
            findings.append(
                Finding(
                    expected_owner,
                    1,
                    ArchitectureCode.CAPABILITY,
                    f"exclusive capability {capability!r} has owners "
                    f"{owners.get(capability, [])!r}",
                )
            )


def _literal_assignments(tree: ast.Module) -> dict[str, object]:
    result: dict[str, object] = {}
    for node in tree.body:
        name = ""
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name, value = node.target.id, node.value
        elif (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            name, value = node.targets[0].id, node.value
        if name and value is not None:
            try:
                result[name] = ast.literal_eval(value)
            except TypeError, ValueError:
                continue
    return result


def _discover_member_paths(root: Path) -> set[str]:
    return {
        path.parent.relative_to(root).as_posix()
        for member_root in _MEMBER_ROOTS
        for path in (root / member_root).glob("*/pyproject.toml")
        if path.is_file()
    }


def _root_workspace_paths(root: Path, findings: list[Finding]) -> set[str]:
    metadata = _toml(root / "pyproject.toml")
    tool = _object_mapping(metadata.get("tool"), "root.tool")
    uv = _object_mapping(tool.get("uv"), "root.tool.uv")
    workspace = _object_mapping(uv.get("workspace"), "root.tool.uv.workspace")
    members = workspace.get("members")
    if not isinstance(members, list):
        findings.append(
            Finding("pyproject.toml", 1, ArchitectureCode.MEMBER_METADATA, "workspace invalid")
        )
        return set()
    member_objects = cast("list[object]", members)
    if not all(isinstance(item, str) for item in member_objects):
        findings.append(
            Finding("pyproject.toml", 1, ArchitectureCode.MEMBER_METADATA, "workspace invalid")
        )
        return set()
    return set(cast("list[str]", member_objects))


def _toml(path: Path) -> dict[str, object]:
    return cast("dict[str, object]", tomllib.loads(path.read_text(encoding="utf-8")))


def _requirement_name(value: str) -> str:
    match = _DISTRIBUTION_PATTERN.match(value)
    if match is None:
        raise ArchitectureFailure("ARCH_DEPENDENCY_REQUIREMENT_INVALID")
    return _normalize_distribution(match.group())


def _normalize_distribution(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _set_difference(label: str, expected: set[str], actual: set[str]) -> str:
    return (
        f"{label} mismatch; missing={sorted(expected - actual)!r}; "
        f"unexpected={sorted(actual - expected)!r}"
    )


def _object_mapping(value: object, location: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ArchitectureFailure(f"ARCH_EXPECTED_MAPPING: {location}")
    mapping = cast("dict[object, object]", value)
    if not all(isinstance(key, str) for key in mapping):
        raise ArchitectureFailure(f"ARCH_EXPECTED_MAPPING: {location}")
    return cast("dict[str, object]", mapping)


def _mapping(value: object, location: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ArchitectureFailure(f"ARCH_EXPECTED_JSON_MAPPING: {location}")
    mapping = cast("dict[object, object]", value)
    if not all(isinstance(key, str) for key in mapping):
        raise ArchitectureFailure(f"ARCH_EXPECTED_JSON_MAPPING: {location}")
    return cast("dict[str, JsonValue]", mapping)


def _sequence(value: JsonValue, location: str) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ArchitectureFailure(f"ARCH_EXPECTED_SEQUENCE: {location}")
    return value


def _string(value: JsonValue | object, location: str) -> str:
    if not isinstance(value, str) or not value:
        raise ArchitectureFailure(f"ARCH_EXPECTED_STRING: {location}")
    return value


def _integer(value: JsonValue, location: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ArchitectureFailure(f"ARCH_EXPECTED_INTEGER: {location}")
    return value


def _string_tuple(value: JsonValue, location: str) -> tuple[str, ...]:
    return tuple(
        _string(item, f"{location}[{index}]")
        for index, item in enumerate(_sequence(value, location))
    )


def _relative_path(value: JsonValue, location: str) -> str:
    result = _string(value, location)
    path = Path(result)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != result:
        raise ArchitectureFailure(f"ARCH_PATH_INVALID: {location}")
    return result


def _require_keys(value: Mapping[str, object], expected: set[str], location: str) -> None:
    if set(value) != expected:
        raise ArchitectureFailure(f"ARCH_KEYS_INVALID: {location}")


def _canonical_json(value: JsonValue | object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main() -> int:
    """Run the checked-in architecture proof and print its canonical report."""
    _parser().parse_args()
    root = Path(__file__).resolve().parents[1]
    findings = check_repository(root)
    if findings:
        for finding in findings:
            print(f"{finding.path}:{finding.line}: {finding.code} {finding.detail}")
        return 1
    print(_canonical_json(run_spike(root).to_json()).decode("utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
