# AskLegal contracts Python boundary

This package is the local Python proof for the implementation-neutral JSON
contracts in the repository root `contracts/` directory. It supplies strict
raw-byte parsing, an offline Draft 2020-12 schema registry, an RFC 8785 adapter,
SHA-256 fingerprints, and a small strict Pydantic boundary model.

The repository-wide type-boundary gate combines official Pyright strict with
`tools/python_boundary_check.py`. It automatically discovers Python below
future `packages/*` and `apps/*` trees, rejects explicit `Any`, bare collection
annotations, unapproved casts and error suppressions, and prevents domain or
application packages from importing infrastructure or leaking HTTP frameworks
into domain/contract code. Its six current exceptions are exact file-and-line
entries with durable reasons; stale entries fail the gate.

The root schemas and fixtures remain normative. This package has no network,
database, Azure, provider, source-acquisition, approval, or production effect.

From the repository root, after installing the pinned toolchains:

```sh
uv sync --locked --all-packages
npm ci --ignore-scripts
uv run ruff check packages tools
uv run ruff format --check packages tools
npm run typecheck
env -u PYTHONPATH PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 uv run pytest -q
node tools/validate-contracts.mjs
```

The explicit environment cleanup prevents a host-level ROS Python path and
ambient pytest plugins from entering the locked Python 3.14 environment.
