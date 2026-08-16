---
status: accepted
date: 2026-08-15
refined_by:
  - "0092"
  - "0093"
  - "0094"
refines:
  - "0001"
  - "0006"
  - "0007"
  - "0009"
  - "0011"
  - "0088"
  - "0089"
  - "0090"
---

# Use Azure SQL for the Management Register

## Decision

The production Management Register uses one Azure SQL Database. It is accessed
from Python through Microsoft's first-party `mssql-python` DB-API driver. The
exact Azure SQL service tier, compute size, zone configuration, backup
retention, connection limits, and dependency version remain measured
implementation and operations decisions; they are not implicit defaults.

The database is the authoritative durable ledger for business state, legal and
operational decisions, work state, Approval lifecycle, promotion admission,
and Serving State history. It is not the Evidence Vault, a legal-corpus store,
a workflow-history substitute, or an external-provider transaction manager.

Applications do not use a general-purpose ORM on the authoritative write path.
They call versioned, schema-qualified T-SQL command procedures through a narrow
typed `ManagementRegisterStore` adapter. Application identities receive only
`EXECUTE` on their owned commands and `SELECT` on their owned views. They do
not receive direct table mutation or DDL privileges. SQLAlchemy is not part of
the initial register boundary; adding it later for a proved read-only need must
not change write SQL, isolation, migration bytes, or normative storage.

## Why Azure SQL wins this comparison

Both Azure SQL Database and Azure Database for PostgreSQL Flexible Server can
provide ACID transactions, exact relational constraints, serializable critical
sections, private networking, Microsoft Entra authentication, application-role
separation, point-in-time restore, and transactionally coupled outbox/inbox
records. PostgreSQL also has the more mature Python driver family, native async
support, strong static typing, excellent concurrency behavior, and greater
engine portability.

Azure SQL is selected because it has the stronger complete fit here:

- append-only ledger tables prevent ordinary `UPDATE` and `DELETE` operations
  even by privileged database users and bind inserted rows into the database
  ledger;
- database digests can be written outside the database to immutable storage
  and independently verified, providing a native tamper-evidence mechanism for
  the register's highest-value audit facts;
- transaction-owned application locks, filtered indexes, exact constraints,
  row-versioned reads, and targeted serializable transactions can enforce the
  required promotion, Approval, identity, and idempotency invariants;
- `mssql-python` is now a generally available Microsoft driver, implements
  Python DB-API 2.0, supports Python 3.10 and later, includes connection
  pooling and Microsoft Entra authentication, and uses Direct Database
  Connectivity rather than requiring a separately installed ODBC manager;
- Azure SQL supplies private endpoints, contained Microsoft Entra database
  users, point-in-time restore, geo-restore options, and long-term retention;
  and
- Ask.Legal already operates SQL Server from both its Node backend and Python
  AI service, so this avoids adding a second database engine and its separate
  schema, backup, tuning, incident, and on-call knowledge.

The final point is supporting evidence, not the deciding rule. The existing
Ask.Legal repositories remain non-authoritative reference material and create
no schema, code, deployment, credential, or operational dependency.

Azure SQL's ledger and existing operational familiarity outweigh PostgreSQL's
driver maturity and portability for this audit-centered register. Cost does
not establish a stable winner without measured storage, transaction, replica,
retention, and recovery requirements. The selected Azure SQL tier must later
be justified from a workload and recovery model rather than copied from an
existing service.

## Authoritative data shape

The register separates three kinds of data:

1. **Immutable authoritative facts.** A small fixed set of explicitly declared
   append-only ledger tables stores immutable objects or references, domain and
   lifecycle events, command claims and results, outbox intents and delivery
   events, promotion receipts, and applied migration facts.
2. **Current projections.** Ordinary relational tables and views provide
   rebuildable current state, pending-work indexes, reports, and exact lookup
   paths. Their rows may be updated or replaced because they are not the
   historical authority.
3. **External immutable objects.** Source bytes, legal text, reports, release
   packages, and other large artifacts remain in the Evidence Vault or the
   appropriate immutable artifact store. The register stores only their opaque
   IDs, exact fingerprints, roles, and bounded metadata.

Ledger is enabled explicitly per selected authoritative table. It is not a
database-wide default and is not applied indiscriminately to caches,
projections, leases, or operational scratch state. An append-only ledger table
cannot later be converted back to a regular table, updated, deleted, or
truncated. Every proposed ledger column is therefore subject to data-
classification and retention review before production. Secrets, credentials,
unbounded reviewer text, raw source content, and unnecessary personal data are
forbidden from ledger payloads.

Ledger digests must be exported automatically to a separately permissioned
immutable store and verified on a schedule and during restoration exercises.
ADR 0094 selects a private Azure Confidential Ledger for automatic digest
upload and separately preserved verified digest-and-receipt checkpoints in the
Azure Recovery Vault. Until that external digest path and verification
evidence exist, native ledger tables improve structure but do not prove end-
to-end tamper evidence.

Authoritative structured payloads are stored as their already validated RFC
8785 JCS UTF-8 bytes in `varbinary` columns together with the exact lowercase
`sha256:` fingerprint and typed relational columns needed for constraints and
queries. SQL Server JSON parsing, collation, or reserialization is not
normative. Identifiers, codes, and fingerprints use exact-length types, binary
comparison, closed checks, and unique constraints. Floating-point values are
not used for normative facts.

Domain timestamps are explicit contract values; the database must not invent a
legal-effective or source-observation time. A separate database-generated UTC
transaction timestamp may record when a row was committed. `rowversion` may be
used only as a projection concurrency token and never as a time, identity, or
artifact fingerprint.

## Command and transaction boundary

One register command executes as one short database transaction with
`autocommit` disabled. No network call, file operation, workflow wait, model
call, embedding call, clock wait, or user interaction occurs while that
transaction is open.

Every mutating command supplies:

- a register-issued command ID;
- a caller-scoped idempotency key;
- the exact command contract version;
- the canonical request bytes and fingerprint;
- the authenticated application identity; and
- every expected base ID, lifecycle state, object fingerprint, and concurrency
  token needed by that command.

Within the same transaction, the command procedure:

1. takes a finite, transaction-owned application lock only when the invariant
   requires logical serialization;
2. proves that an existing idempotency key has the same request fingerprint or
   rejects it as a collision;
3. appends the command claim;
4. validates exact current state and database constraints;
5. appends the immutable object and lifecycle events;
6. inserts every resulting outbox intent;
7. updates only rebuildable projections; and
8. appends a bounded command result that allows an exact retry response.

The claim, authoritative facts, outbox intents, projections, and result commit
or roll back together. Inbox and outbox are register tables, not a distributed
transaction. An outbox dispatcher performs an external effect only after the
intent commits, then appends an immutable attempt or result event in a later
transaction. A mutable dispatch projection may make pending scans efficient
but is always rebuildable from the immutable facts.

Ordinary commands use Azure SQL's read-committed snapshot behavior plus exact
constraints and conditional writes. Commands that enforce a cross-row
invariant use a narrow `SERIALIZABLE` transaction or equivalent locking in the
stored procedure. Promotion activation, rollback, Approval consumption, and
other single-winner transitions also take a finite transaction-owned
`sp_getapplock` keyed by the exact environment, target, Approval, or execution
lineage. Every negative lock result is handled explicitly and the transaction
is rolled back; the default infinite wait is forbidden.

For example, Serving State activation serializes on one environment-and-target
resource, checks the exact expected base activation and candidate fingerprint,
appends one activation event, and conditionally changes the one-row current
projection in the same transaction. The application lock is not the invariant
by itself: primary, unique, foreign-key, check, and compare-and-set constraints
must still make an invalid committed state impossible.

## Failure and retry rule

A retry unit is the complete repository command, never an arbitrary statement
inside a partially completed write transaction. Deadlock or serialization
victims roll back completely and may be retried with bounded exponential
backoff and jitter only when the command is fingerprint-bound and idempotent.
Configuration, authentication, schema, constraint, and programming failures
fail closed.

A lost connection during commit creates an ambiguous outcome. The application
must open a new connection and query the immutable command claim/result by
idempotency key and request fingerprint. It returns the committed result if
present, reports a collision for a different fingerprint, and retries only
when absence is proved. It must never blindly replay an external effect or a
write whose commit status is unknown.

## Python driver and concurrency boundary

`mssql-python` is isolated behind the typed register adapter. Exact dependency
versions are pinned in the implementation lock only after the driver passes
the Python 3.14, Pyright strict, parameter binding, Unicode, binary payload,
timestamp, decimal, transaction, pooling, failover, retry, and ambiguous-
commit tests.

The selected driver API is synchronous. An async FastAPI route calls the
synchronous register adapter through a dedicated bounded AnyIO worker-thread
limiter. A connection and cursor are acquired, used, committed or rolled back,
and released entirely inside that worker invocation; they are never shared
between threads or across an `await`. Synchronous worker activities may call
the same adapter directly.

Driver pooling is configured once before the first connection. Its per-process
maximum is explicit and the sum across application replicas stays below the
selected database tier's safe connection budget. The driver's default pool
size is not accepted as a production capacity decision. Connections use
managed identity, strict encryption and certificate verification, bounded
login and statement timeouts, consistent connection strings, and private
networking.

`mssql-python` is newer than `psycopg`; that is a real implementation risk.
Failure of its bounded admission proof reopens only the Python driver choice
first, with `pyodbc` as an evaluable SQL Server fallback. It does not silently
authorize a driver substitution or overturn the database decision.

## Local-first development boundary

Azure SQL is the production deployment target, not a requirement for ordinary
development. The pipeline is built and exercised locally first with synthetic
fixtures, local fakes for every external effect, ordinary local Python
processes or containers, and a supported local SQL Server Developer container
for T-SQL, stored-procedure, transaction, locking, migration, and ledger
conformance. A developer must not need Azure credentials or a shared cloud
database to run the normal unit, contract, integration, concurrency, migration,
and restart suites.

The local SQL Server instance is disposable test infrastructure, never a
source of production truth. Tests create isolated databases from exact
migrations and may destroy only those explicitly identified test databases.
SQLite and mocked SQL are useful for neither register integration nor
dialect-conformance proof and cannot replace the local SQL Server suite.

Azure is introduced only in separately authorized non-production proofs for
behaviors a local server cannot establish: managed identity, private endpoints
and DNS, Azure service limits, zone or platform failover, point-in-time and
long-term restore, external immutable ledger-digest storage, Azure monitoring,
and the selected hosting network. Those proofs complement the local suites;
they do not turn a shared Azure environment into the main development loop.

## Roles and capability separation

The database has a distinct contained Microsoft Entra user and custom database
role for each separately deployed application, plus separate migration,
projection-rebuild, read-only audit, digest-verification, and break-glass
roles. At minimum:

- the control plane can execute only coordination, registry, coverage, and
  work-state commands;
- the Review Application can execute only inspection, comment, rejection,
  Approval, revocation, and related reviewer commands;
- acquisition can append only owned observation and evidence-reference facts;
- legal processing can append only candidate, interpretation, validation, and
  owned work facts;
- promotion can execute only exact promotion, receipt, Serving State, and
  rollback commands; and
- only the migration identity can change database objects.

Production application roles receive no membership in broad fixed roles, no
DDL, and no direct authoritative table DML. Row-level security is available as
defence in depth if a later concrete row-scoped rule requires it, but it does
not replace separate identities, stored-procedure capabilities, schemas,
views, networks, or deployments.

## Exact migration mechanism

Register schema changes use a repository-owned, deliberately small migration
runner over `mssql-python`, not ORM model generation or Alembic autogeneration.
Each forward-only migration is an immutable directory containing:

- a monotonic fixed-width migration ID and descriptive slug;
- a closed manifest listing every T-SQL batch in exact execution order;
- the SHA-256 fingerprint and byte length of every UTF-8/LF batch;
- the migration package fingerprint;
- the compatible application-contract range; and
- whether the migration is an expand, contract, projection rebuild, or
  corrective operation.

The runner performs no template substitution, environment interpolation,
implicit file discovery, or `GO` parsing. `GO` is forbidden because it is a
client-tool separator rather than T-SQL. Each listed file is sent as one exact
batch, allowing procedure definitions to occupy their required batch while all
batches remain inside the enclosing transaction.

Before execution, the runner validates the complete manifest, exact bytes,
ordered prefix, and every previously recorded fingerprint. It acquires one
finite transaction-owned migration application lock, executes all listed
batches inside one transaction, and appends the migration ID, package
fingerprint, runner build, database identity, executor identity, and applied
time to an append-only migration ledger table before commit. An applied ID
with different bytes is a hard failure.

The initial runner permits only transaction-safe migrations. A change that
cannot be completed transactionally requires a later explicit operational
migration design with resumable states and independent evidence; it cannot be
smuggled into an ordinary package. Migrations are forward-only. Recovery uses
point-in-time restore or a new corrective migration, not an automated `down`
script that attempts to delete ledger history.

Rolling changes follow expand-and-contract compatibility: add compatible
structures, deploy compatible code, verify that the old code is absent, and
only then remove obsolete projections or permissions. Immutable ledger facts
are not rewritten in place; a material event-shape change introduces a new
version and a compatible projection. Migrations never seed legal facts,
rulebooks, approvals, capabilities, or production policy. Those enter through
their normal evidence-bound commands.

## Recovery boundary

Azure SQL automated backups provide the primary point-in-time restore
mechanism. Long-term retention, geo-redundancy, zone configuration, recovery
objectives, and independent recovery copies remain explicit governance and
operations decisions. Provider statements that backups exist are not restore
evidence.

Scheduled restore drills must create an isolated replacement database, verify
the exact migration prefix, run database-ledger verification against external
digests, rebuild every projection from immutable facts, reconcile authoritative
counts and fingerprints, exercise least-privilege access, and preserve an
immutable signed result outside the restored database. A restore does not
authorize routing or promotion.

Local tests use a supported SQL Server container with only synthetic data.
SQLite is not an acceptable substitute for T-SQL, ledger, collation,
transaction, locking, stored-procedure, or migration conformance. Azure-only
identity, networking, failover, backup, and ledger-digest behavior requires a
separately authorized non-production Azure proof before production admission.

## Primary evidence

- [Azure SQL ledger overview and external digest model](https://learn.microsoft.com/en-us/azure/azure-sql/database/ledger-landing?view=azuresql)
- [Append-only ledger table behavior](https://learn.microsoft.com/en-us/sql/relational-databases/security/ledger/ledger-append-only-ledger-tables?view=sql-server-ver17)
- [Ledger limitations and irreversible constraints](https://learn.microsoft.com/en-us/sql/relational-databases/security/ledger/ledger-limits?view=sql-server-ver17)
- [`mssql-python` driver and production baseline](https://learn.microsoft.com/en-us/sql/connect/python/mssql-python/python-sql-driver-mssql-python?view=sql-server-ver17)
- [`mssql-python` transaction management](https://learn.microsoft.com/en-us/sql/connect/python/mssql-python/transaction-management?view=sql-server-ver17)
- [`mssql-python` connection pooling](https://learn.microsoft.com/en-us/sql/connect/python/mssql-python/connection-pooling?view=sql-server-ver17)
- [`mssql-python` retry and ambiguous-outcome guidance](https://learn.microsoft.com/en-us/sql/connect/python/mssql-python/retry-logic?view=sql-server-ver17)
- [Azure SQL transaction isolation](https://learn.microsoft.com/en-us/sql/t-sql/statements/set-transaction-isolation-level-transact-sql?view=sql-server-ver17)
- [Transaction-owned application locks](https://learn.microsoft.com/en-us/sql/relational-databases/system-stored-procedures/sp-getapplock-transact-sql?view=sql-server-ver17)
- [Azure SQL row-level security](https://learn.microsoft.com/en-us/sql/relational-databases/security/row-level-security?view=sql-server-ver17)
- [Azure SQL automated backups, point-in-time restore, and long-term retention](https://learn.microsoft.com/en-us/azure/azure-sql/database/automated-backups-overview?view=azuresql)
- [Azure SQL private endpoints](https://learn.microsoft.com/en-us/azure/azure-sql/database/private-endpoint-overview?view=azuresql)
- [Azure Database for PostgreSQL backup and restore](https://learn.microsoft.com/en-us/azure/postgresql/backup-restore/concepts-backup-restore)
- [`psycopg` static typing](https://www.psycopg.org/psycopg3/docs/advanced/typing.html)
- [`psycopg` synchronous and asynchronous pooling](https://www.psycopg.org/psycopg3/docs/api/pool.html)

## Considered alternatives

### Azure Database for PostgreSQL Flexible Server

PostgreSQL is technically strong and would have been a sound choice for a team
without an existing database standard or a native-ledger requirement.
`psycopg` provides mature synchronous and asynchronous APIs and a strong type
surface; PostgreSQL provides serializable snapshot isolation, advisory locks,
partial indexes, row-level security, and excellent relational constraints.

It was not selected because this project would introduce a second production
database engine and still need a separately designed append-only and external
tamper-evidence mechanism. Its portability and driver advantages do not
outweigh Azure SQL's selective cryptographic ledger, first-party Python driver,
and existing Ask.Legal operational capability for this register.

### SQLAlchemy ORM or ORM-owned migrations

Rejected for authoritative writes. Unit-of-work behavior, generated SQL,
implicit flushes, identity maps, and autogeneration would obscure the exact
commands, lock order, isolation, constraints, and migration bytes that define
the register's audit boundary.

### Alembic with handwritten SQL

This could be made safe, but it would introduce SQLAlchemy and a dialect layer
only to execute migration bytes while still requiring project-specific
fingerprint, manifest, lock, ledger, and compatibility rules. The narrow
runner has a smaller authority surface and must be tested as strictly as any
other register component.

### Azure SQL Managed Instance or a database per application

No accepted requirement needs instance-level SQL Server compatibility, and
Managed Instance would add cost and operational surface. Separate databases
would weaken the single atomic boundary for register command, event, inbox,
outbox, and projection changes. One Azure SQL Database with separate identities,
roles, schemas, procedures, and views preserves both atomicity and least
privilege.

## Consequences

- Azure SQL Database, T-SQL, and `mssql-python` become accepted production-
  stack components subject to local and Azure-specific admission proof.
- The register gains native ledger tamper evidence but accepts Azure SQL and
  T-SQL vendor coupling.
- The newer driver and synchronous API require explicit admission tests,
  bounded thread offload in async APIs, and deliberate pool sizing.
- Application roles cannot bypass stored procedures to mutate authoritative
  tables.
- Append-only ledger schema and retained data are difficult to reverse; data
  minimization, classification, retention, and digest storage must be settled
  before production creation.
- Application scaffolding must not start merely because this database decision
  is accepted. ADR 0092 later selects Azure Container Apps with one isolated
  environment and subnet per application without changing the register
  boundary, and ADR 0093 later selects managed Durable Task Scheduler while
  keeping the register authoritative for business and legal state.

## Authorization boundary

This ADR authorizes documentation and design selection only. It does not
authorize application or migration-runner implementation, dependency or SQL
Server installation, container execution, Azure resource access or creation,
database or digest-store creation, schema migration, source access, model or
embedding calls, corpus publication, evidence or backup mutation, Pinecone
access, deployment, routing changes, commits, pushes, or any other remote
effect. Every operational capability remains disabled.
