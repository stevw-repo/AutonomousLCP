"""Fail-closed static policy for Python type and import boundaries."""

import ast
import re
import tokenize
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class BoundaryCode(StrEnum):
    """Stable finding codes emitted by the boundary checker."""

    ANY = "PYBOUND001"
    UNPARAMETERIZED_COLLECTION = "PYBOUND002"
    CAST = "PYBOUND003"
    IGNORED_ERROR = "PYBOUND004"
    INFRASTRUCTURE_IMPORT = "PYBOUND005"
    FRAMEWORK_IMPORT = "PYBOUND006"
    INVALID_POLICY = "PYBOUND007"
    INVALID_PYTHON = "PYBOUND008"


@dataclass(frozen=True, order=True)
class ExceptionKey:
    """Exact source position and finding kind for one reviewed exception."""

    path: str
    line: int
    code: BoundaryCode


@dataclass(frozen=True)
class ApprovedException:
    """A narrow reviewed exception with a durable explanation."""

    key: ExceptionKey
    reason: str


@dataclass(frozen=True, order=True)
class Finding:
    """One deterministic boundary-policy failure."""

    path: str
    line: int
    code: BoundaryCode
    detail: str


_SCHEMA_PATH = "packages/contracts/src/asklegal_contracts/schemas.py"
_JSON_TYPES_PATH = "packages/contracts/src/asklegal_contracts/json_types.py"
_STRICT_JSON_PATH = "packages/contracts/src/asklegal_contracts/strict_json.py"
_MSSQL_DRIVER_PATH = (
    "packages/management-register-adapter/src/asklegal_management_register/driver.py"
)

APPROVED_EXCEPTIONS: tuple[ApprovedException, ...] = (
    ApprovedException(
        ExceptionKey(_SCHEMA_PATH, 51, BoundaryCode.CAST),
        "referencing's recursive Schema alias is narrower than the validated JSON mapping",
    ),
    ApprovedException(
        ExceptionKey(_SCHEMA_PATH, 86, BoundaryCode.CAST),
        "jsonschema's dependency-owned iterator type is narrowed to the tested adapter protocol",
    ),
    ApprovedException(
        ExceptionKey(_SCHEMA_PATH, 88, BoundaryCode.IGNORED_ERROR),
        "the exact jsonschema member diagnostic is contained beside the typed adapter and tests",
    ),
    ApprovedException(
        ExceptionKey(_STRICT_JSON_PATH, 48, BoundaryCode.CAST),
        "stdlib json.loads returns Any and is immediately passed to the recursive runtime checker",
    ),
    ApprovedException(
        ExceptionKey(_JSON_TYPES_PATH, 28, BoundaryCode.CAST),
        "runtime list recognition is narrowed to object elements before recursive validation",
    ),
    ApprovedException(
        ExceptionKey(_JSON_TYPES_PATH, 33, BoundaryCode.CAST),
        "runtime mapping recognition is narrowed before every key and value is validated",
    ),
    ApprovedException(
        ExceptionKey(_MSSQL_DRIVER_PATH, 19, BoundaryCode.IGNORED_ERROR),
        "mssql-python 1.12 leaves execute parameters unknown behind this typed wrapper",
    ),
    ApprovedException(
        ExceptionKey(_MSSQL_DRIVER_PATH, 21, BoundaryCode.IGNORED_ERROR),
        "mssql-python 1.12 leaves parameterless execute unknown behind this typed wrapper",
    ),
)

_SOURCE_PATTERNS: tuple[str, ...] = (
    "packages/*/src/**/*.py",
    "packages/*/tests/**/*.py",
    "apps/*/src/**/*.py",
    "apps/*/tests/**/*.py",
)
_TYPING_MODULES = frozenset({"typing", "typing_extensions"})
_COLLECTION_NAMES = frozenset(
    {
        "AsyncGenerator",
        "AsyncIterable",
        "AsyncIterator",
        "Awaitable",
        "Callable",
        "Collection",
        "Container",
        "Coroutine",
        "DefaultDict",
        "Deque",
        "Dict",
        "Generator",
        "Hashable",
        "Iterable",
        "Iterator",
        "List",
        "Mapping",
        "MutableMapping",
        "MutableSequence",
        "MutableSet",
        "Sequence",
        "Set",
        "Tuple",
        "Type",
        "dict",
        "frozenset",
        "list",
        "set",
        "tuple",
        "type",
    }
)
_INFRASTRUCTURE_ROOTS = frozenset(
    {
        "azure",
        "durabletask",
        "mssql_python",
        "pinecone",
        "pyodbc",
        "sqlalchemy",
    }
)
_FRAMEWORK_ROOTS = frozenset({"django", "fastapi", "flask", "starlette", "uvicorn"})
_DOMAIN_EXTRA_ROOTS = frozenset({"jsonschema", "pydantic", "referencing", "rfc8785"})
_IGNORE_PATTERN = re.compile(r"#\s*(?:type:\s*ignore\b|pyright:\s*ignore\b|noqa\b)")
_PACKAGE_PATH_PARTS = 3
_MINIMUM_EXCEPTION_REASON_LENGTH = 24


class _BoundaryVisitor(ast.NodeVisitor):
    """Inspect one parsed module using its import aliases and package role."""

    def __init__(
        self,
        *,
        relative_path: str,
        approved: frozenset[ExceptionKey],
        protected_package: bool,
        domain_package: bool,
        framework_free_package: bool,
    ) -> None:
        self.relative_path = relative_path
        self.approved = approved
        self.protected_package = protected_package
        self.domain_package = domain_package
        self.framework_free_package = framework_free_package
        self.findings: list[Finding] = []
        self.used_exceptions: set[ExceptionKey] = set()
        self._typing_aliases: set[str] = set()
        self._cast_aliases: set[str] = set()
        self._collection_aliases: set[str] = set()

    def _record(self, node: ast.AST, code: BoundaryCode, detail: str) -> None:
        line = getattr(node, "lineno", 1)
        key = ExceptionKey(self.relative_path, line, code)
        if key in self.approved:
            self.used_exceptions.add(key)
            return
        self.findings.append(Finding(self.relative_path, line, code, detail))

    def _check_import_root(self, node: ast.AST, module: str) -> None:
        root = module.partition(".")[0]
        segments = frozenset(module.split("."))
        if self.protected_package and (
            root in _INFRASTRUCTURE_ROOTS or "infrastructure" in segments or "adapters" in segments
        ):
            self._record(
                node,
                BoundaryCode.INFRASTRUCTURE_IMPORT,
                f"protected package imports infrastructure module {module!r}",
            )
        if self.domain_package and root in _DOMAIN_EXTRA_ROOTS:
            self._record(
                node,
                BoundaryCode.FRAMEWORK_IMPORT,
                f"domain package imports boundary library {module!r}",
            )
        if self.framework_free_package and root in _FRAMEWORK_ROOTS:
            self._record(
                node,
                BoundaryCode.FRAMEWORK_IMPORT,
                f"domain package imports application framework {module!r}",
            )

    def visit_Import(self, node: ast.Import) -> None:
        """Record module aliases and enforce protected import roots."""
        for alias in node.names:
            self._check_import_root(node, alias.name)
            if alias.name in _TYPING_MODULES:
                self._typing_aliases.add(alias.asname or alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Record imported type helpers and enforce protected import roots."""
        module = node.module or ""
        if node.level == 0 and module:
            self._check_import_root(node, module)
        if module in _TYPING_MODULES:
            for alias in node.names:
                local_name = alias.asname or alias.name
                if alias.name == "Any":
                    self._record(node, BoundaryCode.ANY, "typing.Any import is not approved")
                elif alias.name == "cast":
                    self._cast_aliases.add(local_name)
                elif alias.name in _COLLECTION_NAMES:
                    self._collection_aliases.add(local_name)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Reject qualified typing.Any uses."""
        if (
            isinstance(node.value, ast.Name)
            and node.value.id in self._typing_aliases
            and node.attr == "Any"
        ):
            self._record(node, BoundaryCode.ANY, "typing.Any is not approved")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Require every static cast to occupy one exact reviewed position."""
        direct_cast = isinstance(node.func, ast.Name) and node.func.id in self._cast_aliases
        qualified_cast = (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in self._typing_aliases
            and node.func.attr == "cast"
        )
        if direct_cast or qualified_cast:
            self._record(node, BoundaryCode.CAST, "static cast is not explicitly approved")
        self.generic_visit(node)

    def _check_annotation(self, annotation: ast.expr) -> None:
        if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
            try:
                parsed = ast.parse(annotation.value, mode="eval")
            except SyntaxError:
                return
            ast.increment_lineno(parsed, annotation.lineno - 1)
            self._check_annotation(parsed.body)
            return
        if isinstance(annotation, ast.Subscript):
            self._check_annotation(annotation.slice)
            return
        if isinstance(annotation, ast.Name):
            if annotation.id in _COLLECTION_NAMES or annotation.id in self._collection_aliases:
                self._record(
                    annotation,
                    BoundaryCode.UNPARAMETERIZED_COLLECTION,
                    f"collection annotation {annotation.id!r} has no type arguments",
                )
            return
        if isinstance(annotation, ast.Attribute):
            if (
                isinstance(annotation.value, ast.Name)
                and annotation.value.id in self._typing_aliases
                and annotation.attr in _COLLECTION_NAMES
            ):
                self._record(
                    annotation,
                    BoundaryCode.UNPARAMETERIZED_COLLECTION,
                    f"collection annotation {annotation.attr!r} has no type arguments",
                )
            return
        for child in ast.iter_child_nodes(annotation):
            if isinstance(child, ast.expr):
                self._check_annotation(child)

    def _check_arguments(self, arguments: ast.arguments) -> None:
        all_arguments = (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
        )
        for argument in all_arguments:
            if argument.annotation is not None:
                self._check_annotation(argument.annotation)
        if arguments.vararg is not None and arguments.vararg.annotation is not None:
            self._check_annotation(arguments.vararg.annotation)
        if arguments.kwarg is not None and arguments.kwarg.annotation is not None:
            self._check_annotation(arguments.kwarg.annotation)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check every synchronous function annotation."""
        self._check_arguments(node.args)
        if node.returns is not None:
            self._check_annotation(node.returns)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Check every asynchronous function annotation."""
        self._check_arguments(node.args)
        if node.returns is not None:
            self._check_annotation(node.returns)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Check annotated variables and attributes."""
        self._check_annotation(node.annotation)
        self.generic_visit(node)

    def visit_TypeAlias(self, node: ast.TypeAlias) -> None:
        """Check Python 3.12+ type alias declarations."""
        self._check_annotation(node.value)
        self.generic_visit(node)


def _package_roles(relative_path: str) -> tuple[bool, bool, bool]:
    parts = Path(relative_path).parts
    if (
        len(parts) < _PACKAGE_PATH_PARTS
        or parts[0] not in {"apps", "packages"}
        or parts[2] != "src"
    ):
        return False, False, False
    package_name = parts[1]
    is_adapter = "adapter" in package_name or "infrastructure" in package_name
    protected_package = not is_adapter
    domain_package = package_name.startswith("domain")
    framework_free_package = package_name == "contracts" or domain_package
    return protected_package, domain_package, framework_free_package


def _comment_findings(
    *,
    source: str,
    relative_path: str,
    approved: frozenset[ExceptionKey],
) -> tuple[list[Finding], set[ExceptionKey]]:
    findings: list[Finding] = []
    used: set[ExceptionKey] = set()
    for token in tokenize.generate_tokens(iter(source.splitlines(keepends=True)).__next__):
        if token.type != tokenize.COMMENT or _IGNORE_PATTERN.search(token.string) is None:
            continue
        key = ExceptionKey(relative_path, token.start[0], BoundaryCode.IGNORED_ERROR)
        if key in approved:
            used.add(key)
        else:
            findings.append(
                Finding(
                    relative_path,
                    token.start[0],
                    BoundaryCode.IGNORED_ERROR,
                    "type or lint error suppression is not explicitly approved",
                )
            )
    return findings, used


def check_files(
    root: Path,
    paths: tuple[Path, ...],
    approved_exceptions: tuple[ApprovedException, ...] = (),
    *,
    require_all_exceptions: bool = False,
) -> tuple[Finding, ...]:
    """Check exact Python paths and optionally reject unused exception entries."""
    approved_by_key = {exception.key: exception for exception in approved_exceptions}
    findings: list[Finding] = []
    used_exceptions: set[ExceptionKey] = set()
    if len(approved_by_key) != len(approved_exceptions):
        findings.append(
            Finding("<policy>", 1, BoundaryCode.INVALID_POLICY, "duplicate exception key")
        )
    findings.extend(
        Finding(
            exception.key.path,
            exception.key.line,
            BoundaryCode.INVALID_POLICY,
            "approved exception requires a specific durable reason",
        )
        for exception in approved_exceptions
        if len(exception.reason.strip()) < _MINIMUM_EXCEPTION_REASON_LENGTH
    )

    approved_keys = frozenset(approved_by_key)
    for path in sorted(paths):
        relative_path = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=relative_path)
        except SyntaxError as error:
            findings.append(
                Finding(
                    relative_path,
                    error.lineno or 1,
                    BoundaryCode.INVALID_PYTHON,
                    "file cannot be parsed by the pinned Python grammar",
                )
            )
            continue
        protected_package, domain_package, framework_free_package = _package_roles(relative_path)
        visitor = _BoundaryVisitor(
            relative_path=relative_path,
            approved=approved_keys,
            protected_package=protected_package,
            domain_package=domain_package,
            framework_free_package=framework_free_package,
        )
        visitor.visit(tree)
        findings.extend(visitor.findings)
        used_exceptions.update(visitor.used_exceptions)
        comment_results, comment_exceptions = _comment_findings(
            source=source,
            relative_path=relative_path,
            approved=approved_keys,
        )
        findings.extend(comment_results)
        used_exceptions.update(comment_exceptions)

    if require_all_exceptions:
        findings.extend(
            Finding(
                key.path,
                key.line,
                BoundaryCode.INVALID_POLICY,
                f"approved {key.code} exception is stale or no longer used",
            )
            for key in sorted(approved_keys - used_exceptions)
        )
    return tuple(sorted(findings))


def discover_python_files(root: Path) -> tuple[Path, ...]:
    """Discover current and future package/application Python without a manual list."""
    paths: set[Path] = set()
    for pattern in _SOURCE_PATTERNS:
        paths.update(path for path in root.glob(pattern) if path.is_file())
    return tuple(sorted(paths))


def check_repository(root: Path) -> tuple[Finding, ...]:
    """Apply the complete checked-in policy to one repository root."""
    return check_files(
        root,
        discover_python_files(root),
        APPROVED_EXCEPTIONS,
        require_all_exceptions=True,
    )


def main() -> int:
    """Run the repository check and return a shell-friendly result."""
    repository_root = Path(__file__).resolve().parents[1]
    findings = check_repository(repository_root)
    if findings:
        for finding in findings:
            print(f"{finding.path}:{finding.line}: {finding.code} {finding.detail}")
        return 1
    checked_count = len(discover_python_files(repository_root))
    print(
        "PASS Python type boundaries: "
        f"{checked_count} files, {len(APPROVED_EXCEPTIONS)} exact reviewed exceptions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
