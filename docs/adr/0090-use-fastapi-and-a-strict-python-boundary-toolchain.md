---
status: accepted
date: 2026-08-15
refined_by:
  - "0091"
  - "0092"
  - "0093"
  - "0096"
refines:
  - "0001"
  - "0088"
  - "0089"
---

# Use FastAPI and a strict Python boundary toolchain

## Decision

The control-plane and Review Application HTTP APIs use FastAPI with Pydantic
version 2 boundary models and run as ASGI applications under Uvicorn. Workers
do not acquire FastAPI merely to expose pipeline behavior; their durable work
continues through the selected workflow boundary and bounded adapters.

The accepted Python development and contract toolchain is:

| Concern | Selected tool or rule |
|---|---|
| HTTP API adapter | FastAPI |
| HTTP boundary models | Pydantic v2, configured strict, closed, and frozen |
| ASGI server | Uvicorn |
| Static type checker | Official Pyright CLI in strict mode |
| Lint and format | Ruff |
| Python workspace and dependency lock | uv workspaces and one committed `uv.lock` |
| Normative JSON parsing | Repository-owned strict raw-byte parser built on the Python standard-library JSON decoder |
| JSON Schema | `jsonschema` with an explicit `Draft202012Validator` and a preloaded `referencing.Registry` |
| JCS canonicalization | Trail of Bits `rfc8785`, behind a repository-owned adapter |
| Tests | pytest, Hypothesis, HTTPX, and AnyIO's pytest integration |

Exact dependency versions are resolved and pinned only when implementation is
explicitly authorized. Selection of a library family here does not authorize
installation and does not allow floating production dependencies.

## Framework boundary

FastAPI belongs only in application HTTP adapters. Domain and contract
packages must not import FastAPI, Starlette, Uvicorn, or HTTP-specific types.
Pydantic belongs only at application, provider, configuration, and transport
boundaries. Stable domain values use ordinary fully typed Python constructs,
including frozen slotted dataclasses, enums, protocols, discriminated unions,
and explicit result types.

Boundary models use the equivalent of `strict=True`, `extra="forbid"`, and
`frozen=True`. They must use closed field types and must not expose untyped
dictionaries. Because Pydantic freezing is not deep immutability, contained
collections also use immutable types wherever the domain value is intended to
be immutable.

FastAPI-generated OpenAPI is the versioned HTTP description used for
documentation and later admin-portal client generation. It is not the
normative source for repository artifacts. Repository-owned Draft 2020-12
schemas remain authoritative, and CI must detect drift between an HTTP
operation and every normative schema it exposes.

## Normative JSON path

FastAPI and Pydantic normally parse or convert request bodies. That behavior is
not authoritative for evidence-, manifest-, Approval-, or fingerprint-bound
JSON. Such operations must instead:

1. read one explicitly size-bounded request body as raw bytes;
2. reject a byte-order mark and decode UTF-8 strictly;
3. use the repository-owned parser to reject duplicate keys, invalid Unicode,
   invalid or non-finite numbers, negative zero, and integers outside the
   accepted safe range;
4. validate the resulting value with the explicit Draft 2020-12 schema and an
   in-memory registry containing every permitted local reference;
5. bind the already parsed Python value to a strict closed Pydantic boundary
   model or a closed domain constructor without coercion;
6. canonicalize through the repository JCS adapter; and
7. calculate or compare the exact lowercase `sha256:` fingerprint.

Normative endpoints must not call Pydantic's JSON parser directly. No schema
reference may cause HTTP, file, provider, or other implicit retrieval. Every
schema is checked before use, `format` behavior is explicit rather than
assumed, and validation errors are normalized into stable repository-owned
error codes rather than exposing library messages as contracts.

The `rfc8785` package is an implementation component, not an authority. The
adapter must prove the RFC vectors, every repository JCS fixture, safe-integer
behavior, Unicode ordering, repeated-process byte identity, and equivalence
with the independent Node conformance oracle. A future canonicalizer may
replace it behind the same adapter only after the same proof; fingerprints and
canonical bytes may not change.

The package was still marked Beta and its latest published release was from
2024 when this decision was researched. Before production admission, its exact
source, licence, provenance, Python 3.14 behavior, and maintenance risk must be
reviewed. The narrow adapter and independent oracle are required partly so that
this supply-chain risk cannot become a contract dependency.

## Static and package discipline

Pyright runs against all production and test Python with
`typeCheckingMode = "strict"` and Python 3.14 as the target. Unknown and
implicit `Any` values are errors. An incomplete third-party type surface is
contained in its adapter and repaired with a narrow typed wrapper or reviewed
local stub; it is not silenced across a package. Inline ignores require a
specific rule, explanation, and focused test.

The official npm Pyright package is used rather than treating the community
PyPI wrapper as first-party. It is pinned in the repository's development-tool
lock. This does not make Node.js a backend runtime; the repository already has
a browser client direction and an independent Node conformance validator.

Each Python application and shared package has its own `pyproject.toml` member
inside one uv workspace. The workspace shares one committed `uv.lock` so every
member resolves together. Application images install only the member and
dependency groups they need. uv itself, Python, Pyright, Ruff, and container
base inputs are also version-pinned in implementation and CI configuration.
The repository must prove a clean locked install and must not rely on ambient
global packages.

Ruff is the only Python linter and formatter. Pyright is the only required
static type checker; running both Pyright and mypy as permanent gates would add
duplicate configuration and disagreement without a demonstrated benefit.

## Test discipline

pytest is the test runner. Hypothesis supplies property-based coverage for raw
JSON, identities, state machines, retry and deduplication, serialization, and
fingerprint boundaries. HTTPX and AnyIO exercise FastAPI routes through their
ASGI boundary without starting external services.

The suite must include:

- exact positive and negative contract fixtures;
- raw-body tests proving framework parsing cannot precede strict parsing;
- OpenAPI snapshots and admin-client compatibility checks;
- import and dependency-direction tests;
- two-process reproducibility tests;
- lifecycle, retry, idempotency, stale-approval, and duplicate-event tests;
- provider adapters tested only through local fakes until separately
  authorized; and
- a test that no durable work is started with FastAPI background tasks.

## Rationale

FastAPI is preferred to Flask for this greenfield boundary because it combines
standard Python annotations, Pydantic integration, OpenAPI generation,
response filtering, dependency hooks, and ASGI operation. Those properties
reduce the amount of custom API plumbing needed for the initial review client
and the later Ask.Legal admin portal.

Flask remains a sound framework and Ask.Legal has operational familiarity with
it. However, its WSGI request model, separately assembled schema/OpenAPI
extensions, and weaker default connection between type annotations and HTTP
contracts provide no compensating benefit here. Flask's own documentation also
notes that an async view still occupies one worker for one request and that
spawned background tasks are not a durable execution mechanism.

FastAPI is not selected as a workflow engine, a security boundary, a contract
authority, or proof of strict input. Its documented default behavior includes
reading JSON and converting types, while Pydantic is coercive by default and
its strict JSON path remains looser for some types. The raw-byte path above is
therefore part of the decision, not optional hardening.

## Considered alternatives

### Flask plus explicit models and OpenAPI tooling

This would align with the existing Ask.Legal AI service and is adequate for a
small synchronous API. It was not selected because matching the accepted typed
OpenAPI and boundary-validation outcome would require additional libraries and
project-specific wiring while still retaining WSGI as the primary interface.

### Django or Django REST Framework

These provide a mature full web platform but couple the API to a larger ORM,
admin, migration, and application model that the separately permissioned
pipeline services do not need.

### Pydantic as the normative schema and JSON parser

Rejected. Generated schemas and successful model creation do not prove the
repository's exact Draft 2020-12, I-JSON, duplicate-key, Unicode, numeric, JCS,
or byte-fingerprint rules.

### mypy instead of Pyright

mypy can enforce a strict Python codebase and Pydantic supplies a mypy plugin.
Pyright is selected because its strict mode distinguishes unknown types from
deliberate `Any`, checks unannotated code, and fits the accepted no-unknown
profile without a framework-specific checker plugin. Maintaining both as
mandatory gates is not justified.

### pip, Poetry, or PDM instead of uv workspaces

All can support responsible packaging. uv is selected because one workspace
lock spans separately installable monorepo members and provides direct locked
execution and synchronization. Its documented workspace limitation does not
enforce import ownership, so architecture tests remain mandatory.

### A custom JCS implementation

Rejected as the starting point because canonical numeric and Unicode behavior
is security- and fingerprint-sensitive. A small internal adapter around an
existing RFC 8785 implementation plus independent conformance tests is less
risky than inventing the algorithm, while preserving replaceability.

## Consequences

- The first authorized implementation work can use one concrete Python
  framework and toolchain rather than reopening routine tooling choices.
- The admin portal can consume a stable OpenAPI-described Review Application
  API later without coupling pipeline correctness to the first UI.
- Normative routes require a little more adapter code than ordinary FastAPI
  routes because raw bytes are validated before model binding.
- Python and Node development tools have separate locks; production backend
  images contain only Python runtime dependencies needed by that application.
- Database, workflow service, hosting, evidence storage, identity topology,
  deployment, observability, provider, and operational policies remain
  separate decisions under this toolchain ADR. ADR 0091 later selects Azure
  SQL, ADR 0092 selects the five-environment Container Apps host, and ADR 0093
  selects managed Durable Task Scheduler without changing the framework
  boundary.
- Substitution of a selected library is allowed only behind the accepted
  boundary and after equivalent local proof; it cannot silently alter
  contracts or canonical bytes.

## Authorization boundary

This ADR authorizes documentation and design selection only. It does not
authorize application scaffolding, dependency installation, external source
access, model or embedding calls, corpus publication, Azure resource access or
creation, Evidence Vault or backup mutation, Pinecone access, deployment,
routing changes, commits, pushes, or any other remote effect. Every operational
capability remains disabled.
