---
status: accepted
date: 2026-08-15
refined_by:
  - "0090"
  - "0091"
  - "0092"
  - "0093"
refines:
  - "0001"
  - "0088"
---

# Use Python for pipeline applications

## Decision

Python 3.14 is the production application-language baseline for the greenfield
legal-database pipeline. The first explicitly authorized local implementation
spike pins Python **3.14.7**. A later patch change must update the exact locks
and repeat the complete local proof; it is not selected implicitly from
whatever Python happens to be installed.

This decision covers:

- the control plane;
- the Review Application API;
- the acquisition worker;
- the legal-processing worker, including the sole gated generative-LLM task
  runner;
- the promotion worker; and
- shared production packages for the domain, contracts, Management Register,
  Evidence Vault, source connectors, Legal Desks, processing, corpus,
  promotion, reporting, observability, and test utilities.

The browser review surface is outside this language decision. It may initially
use React and TypeScript and is intended eventually to be replaced or absorbed
by the Ask.Legal admin portal through the separately permissioned Review
Application API.

A later application may not introduce another backend language merely for
developer preference or access to one library. A narrowly bounded native or
command-line tool is permitted only behind a typed, schema-validated,
sandboxed adapter and does not gain independent domain or operational
authority. A second application language requires a new ADR.

## Required Python standard

Python's dynamic runtime does not weaken the accepted exact contracts. A later
implementation must enforce all of the following before any production
capability can be considered:

- complete annotations for production functions, methods, attributes,
  collections, and returns;
- one strict static type checker that fails CI on every error;
- no unapproved `Any`, unparameterized collections, unchecked casts, ignored
  type errors, or stringly typed domain dictionaries;
- closed enums, frozen value objects, discriminated unions, protocols, and
  explicit result types in domain and application packages;
- strict runtime boundary models that reject unknown fields and coercion;
- raw-byte I-JSON rejection before typed binding;
- independent JSON Schema Draft 2020-12 validation against the repository-
  owned schemas;
- RFC 8785 JCS and exact SHA-256 conformance to every existing fixture;
- deterministic workflow orchestrators with all input/output, time, random,
  network, filesystem, database, provider, Pinecone, and Azure effects confined
  to activities or bounded adapters;
- architecture tests that enforce the accepted application, package,
  infrastructure, credential, and capability directions; and
- reproducible dependency locks, builds, and container inputs.

Static types and application boundary models supplement the normative schemas;
they do not replace them. The existing dependency-free Node validator remains
an independent offline conformance oracle and is not a production runtime
component.

ADR 0090 subsequently selects the API framework, ASGI server, checker,
runtime-model boundary, strict JSON path, JSON Schema and JCS libraries,
package workspace, lint/format tools, and core test tools. Database drivers and
other infrastructure-specific libraries remain separate implementation-stack
decisions. Every selected tool must still pass local synthetic proof before a
production capability is enabled.

## Rationale

The primary system requirement is exact, durable, evidence-bound workflow
execution. Microsoft currently publishes the standalone Python Durable Task
SDK as generally available with orchestrations, activities, sub-
orchestrations, timers, external events, entities, retry policies, continue-as-
new, and suspend/resume. Python therefore does not require a preview workflow
SDK or a separately introduced workflow platform to satisfy the planned
durability model.

The user's explicitly authorized read-only comparison of the existing local
Ask.Legal Core repositories found no C#/.NET and no documented single-language
backend standard. It did find active production capability in:

- Node.js 22, CommonJS JavaScript, Express, Prisma, SQL Server, Redis, Azure
  Blob, Pinecone, and Azure App Service for the platform backend; and
- Python 3.14, Flask, Gunicorn, SQLAlchemy/pyodbc, OpenAI, Pinecone, document-
  processing libraries, pytest, and Azure App Service for the AI service.

The admin and public clients use React and Vite with mixed JSX and
TypeScript/TSX. That comparison is non-authoritative reference evidence, not a
permission to reuse Core code or couple the repositories.

Python aligns with the existing AI, legal retrieval, Pinecone, document, and
Azure operational experience and has the strongest relevant document, OCR,
language, data, and model-integration ecosystem. The stricter profile above
addresses the principal disadvantage relative to C#: fewer compile-time
guarantees by default.

## Considered alternatives

### C# on .NET

C# provides stronger compile-time types, excellent ASP.NET and Worker Service
frameworks, and the strongest first-party Azure integration. It remains the
fallback if a bounded Python proof fails a requirement that the corresponding
.NET proof passes.

It was not selected because it would add a third backend language, package
ecosystem, build chain, security-patching process, debugging skill, and on-call
surface while Python provides the required GA durable-workflow path and
existing organizational capability. No accepted requirement currently needs
.NET specifically.

### TypeScript or JavaScript on Node.js

Node.js aligns with the current platform backend and browser code. It was not
selected because the existing backend is JavaScript rather than a strict
TypeScript domain model, and Microsoft's standalone JavaScript/TypeScript
Durable Task SDK remains Preview. Selecting Temporal or binding the pipeline to
Azure Functions would add or reshape the central workflow platform solely to
preserve one language.

### Java, Go, Rust, C, or C++

Java has a GA Durable Task SDK and strong types but would introduce another
unsupported organizational ecosystem without a unique advantage. Go lacks the
selected first-party Durable Task path. Rust, C, and C++ solve low-level
performance and memory-control problems that are not the pipeline's dominant
risk and would add unnecessary application complexity.

### Multiple backend languages by application

Using Node.js for the control and review APIs, Python for legal processing, and
another language for promotion would mirror existing skill islands but expand
contract drift, build matrices, dependency policies, incident knowledge, and
cross-language replay testing. The planned applications require separate
identities and deployments, not separate languages.

## Consequences

- All backend application and shared package examples, spikes, architecture
  tests, and later implementation plans use Python 3.14 unless a new ADR
  supersedes this decision.
- The implementation must establish a stricter Python profile than the existing
  Ask.Legal AI service; this is alignment of language capability, not code or
  style inheritance.
- The existing Ask.Legal repositories remain reference material only. No code,
  schema, database, deployment, approval, status, or authorization is imported.
- The initial review UI and later admin portal may remain React/TypeScript
  clients because HTTP/OpenAPI and the versioned Approval contracts are the
  language-independent boundary.
- Database, workflow service, hosting, evidence storage, security, recovery,
  observability, deployment, and provider choices remain separately
  reviewable under this language ADR. ADR 0090 later selects FastAPI, ADR 0091
  selects Azure SQL, and ADR 0092 selects the five-environment Container Apps
  host without changing the Python boundary.
- Before full application scaffolding, an explicitly authorized local spike
  must prove strict parsing, schema validation, typed binding, JCS, SHA,
  reproducibility, durable restart, duplicate events, stale fingerprints, and
  architecture boundaries using synthetic data and local fakes.

## Authorization boundary

This ADR authorizes documentation and design selection only. It does not
authorize application code, dependency installation, external source access,
model or embedding calls, corpus publication, Azure resource access or
creation, Evidence Vault or backup mutation, Pinecone access, deployment,
routing changes, commits, pushes, or any other remote effect. Every operational
capability remains disabled.
