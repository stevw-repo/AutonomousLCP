---
status: accepted
date: 2026-08-15
refined_by:
  - "0095"
refines:
  - "0001"
  - "0006"
  - "0007"
  - "0091"
  - "0092"
  - "0093"
---

# Use Azure Blob for primary and recovery vaults

## Decision

Keep the evidence and recovery design Azure-only.

Use dedicated Azure Blob Storage general-purpose v2 accounts as the logical
primary **Evidence Vault**. Use separate Azure Blob Storage general-purpose v2
accounts in a dedicated recovery subscription as the **Recovery Vault**. The
recovery subscription remains under Ask.Legal's existing Microsoft Entra
tenant so the system needs one cloud, identity platform, billing model, policy
language, and operator skill set.

The two vaults do not share a storage account, subscription, resource group,
runtime role, storage policy, network boundary, deployment identity, or
day-to-day storage administrator. Where source rights and data-location rules
permit, the Recovery Vault uses a different Azure region pair from the primary
vault. A location constraint that prevents that separation is recorded as a
known recovery limitation rather than hidden.

Both vaults use standard-performance, flat-namespace accounts and block blobs,
with blob versioning, change feed, blob and container soft delete,
version-level immutability enabled when the account is created, locked default
time-based WORM policies per retention-profile container, exact-version legal
holds, and infrastructure encryption. Hierarchical namespace, NFS, SFTP,
append-write exceptions, public container access, Shared Key authorization,
and public network access are disabled. Production uses RA-GZRS where the
selected region and complete configuration support it; any weaker redundancy
requires an explicit recorded decision based on location, recovery, and cost.

The normal application path uses only the primary vault. Only the promotion
worker receives a narrow managed-identity capability to create and verify
Recovery Vault copies. Recovery administration and clean-room read access are
separate break-glass roles and are not available to an ordinary runtime
identity.

Use Microsoft-managed encryption keys plus infrastructure encryption for both
vaults. A source contract or later policy may require a customer-managed or
client-side key for one named artifact class, but that class remains disabled
until key escrow, rotation, revocation, and clean-room restoration have passed.

Azure SQL uploads database-ledger digests automatically to a separate private
Azure Confidential Ledger. Verified digest checkpoints and receipts are also
included in Recovery Vault checkpoints. Azure SQL automated backups,
Pinecone-native backups, the two Blob vaults, and Confidential Ledger each
address a different recovery or integrity need and do not replace one another.

This design accepts a clear residual risk: the Recovery Vault is isolated from
ordinary application, storage-account, subscription, administrator, and
regional failures, but it is **not independent of Azure or the shared Entra
tenant**. It does not protect against an Azure-wide failure or a compromise
that controls the whole tenant. That is the deliberate tradeoff for the user's
Azure-only, simple operating model. The artifact and recovery-manifest
contracts remain provider-neutral enough to add a different tenant or provider
later without changing legal or business identity.

## Why this is the simplest sufficient boundary

| Requirement | Primary Evidence Vault | Azure Recovery Vault |
|---|---|---|
| Normal access | Owned application identities use narrowly scoped Azure RBAC through private endpoints | No routine access for four applications; only promotion can create and verify copies |
| Immutability | Locked version-level WORM and exact-version legal holds | The same controls under separately administered accounts and subscription |
| Regional resilience | RA-GZRS where supported | Separate primary region pair where permitted, plus its selected Azure redundancy |
| Administrative isolation | Primary subscription, administrators, policies, and networks | Dedicated recovery subscription, administrators, policies, locks, and networks |
| Integrity proof | Register identity, SHA-256, byte length, exact Blob version ID, retention state, and read-back proof | Same bytes and SHA-256, a different exact Blob version ID, retention state, and sealed recovery manifest |
| Provider or tenant failure | Exposed | Also exposed; this limitation is accepted explicitly |

Adding a second cloud would introduce another account hierarchy, identity and
credential system, network and egress path, policy language, audit stack,
cost model, incident process, and operator skill requirement. The user has
stated that such a provider is unlikely to be available. A second Azure
subscription therefore gives useful account and administrative separation
without making an unavailable platform part of the baseline.

Azure Blob object replication is not part of the baseline. It asynchronously
copies source changes, while source updates or deletes can fail to replicate
to a destination version protected by immutability. The pipeline already needs
an exact complete recovery manifest and read-back proof before promotion. One
explicit copy-and-verify protocol is therefore simpler and more auditable than
operating both object replication and the manifest protocol. No deletion is
propagated between vaults.

## Artifact and authority boundaries

The primary vault preserves exact immutable bytes and strict packages,
including as applicable:

- Source Snapshots, official-status evidence, source metadata, and acquisition
  receipts;
- accepted structured facts, Legal Desk decisions, traceability packages, and
  protected evaluation evidence under their data policy;
- Corpus Releases, Desired-State Inventories, Promotion Manifests, Approvals,
  reports, and effect receipts;
- admitted model requests and responses when their retention profile permits
  preservation;
- reusable search-preparation and recovery material; and
- independently generated Management Register recovery packages.

The Management Register remains authoritative for identity, lifecycle,
capability, ownership, Approval, work, and Serving State. Blob names,
directories, metadata, tags, ETags, access tiers, accounts, containers, and
version IDs never become legal or business identity. The Register binds each
artifact's opaque ID and SHA-256 fingerprint to its exact primary and verified
recovery versions.

Git, Scheduler history, Container Apps filesystems, logs, caches, and the local
`var/` adapter are not production evidence stores. Pinecone is a replaceable
serving copy. Azure SQL backups restore the database but do not preserve legal
artifact bytes. Confidential Ledger stores database digests and receipts, not
the corpus.

## Primary write-once admission

There is no distributed transaction between Blob Storage and Azure SQL. One
artifact is admitted through this restartable protocol:

1. The owning application obtains an artifact ID, role, retention profile,
   expected length, and expected SHA-256 from the Register.
2. It computes SHA-256 over the final exact bytes before upload. A partial
   source read or incomplete hash can never be admitted.
3. It creates one block blob under an opaque single-assignment path with
   `If-None-Match: *` and an Azure-supported transport checksum.
4. The locked container default protects the new exact version immediately.
   The application records its Blob version ID, ETag, length, checksum,
   retention state, and request result.
5. It reads that exact version back and verifies the complete length and
   normative SHA-256. MD5 or CRC64 transport checks do not replace SHA-256.
6. Only then does one Register command bind the artifact to that version and
   append its admission event. A successful upload without that event is an
   orphan, not admitted evidence.
7. Reconciliation detects orphans, missing references, unexpected versions,
   retention mismatches, and fingerprint failures. An exact retry may adopt an
   orphan only after proving the original command and every expected fact.

Application roles can create and read only their owned artifact classes. They
cannot delete a blob version, account, or container; change retention, legal
holds, lifecycle, role assignments, storage keys, or resource locks; or obtain
Shared Key access. Each storage account also has a `CanNotDelete` resource
lock as control-plane defense in depth.

## Recovery-copy protocol

For every admitted primary artifact required by a checkpoint, the promotion
worker:

1. resolves and re-verifies the exact primary Blob version from the Register;
2. creates the matching opaque recovery object with `If-None-Match: *` under
   the recovery container's locked default policy;
3. records the recovery account, container, Blob version ID, checksum, length,
   retention state, and request result;
4. reads the exact recovery version back and verifies its byte length and
   SHA-256; and
5. appends the immutable copy result to the Register.

A checkpoint is complete only when a strict recovery manifest lists every
required primary and recovery version, all entries pass verification, and the
manifest itself is written and locked in both vaults. It records omissions and
failures and can never call a partial copy complete.

Before a production mutation, the promotion worker proves that every release,
reusable search artifact, Approval dependency, previous Serving State,
rollback dependency, and Management Register checkpoint named by the frozen
Promotion Manifest appears in a current complete recovery manifest. A stale or
incomplete manifest blocks promotion.

The promotion identity has only the exact recovery-object create, read-back,
and retention-read permissions required by this protocol. It has no object
delete, retention-policy, legal-hold, lifecycle, role-assignment, storage-key,
or account administration permission. The recovery account's private endpoint
is reachable only from the approved promotion and clean-room recovery paths.

## Retention, holds, and destruction

Before a production account or container is created, a written matrix assigns
each artifact class its data location, source rights, minimum and maximum
retention, legal-hold eligibility, storage-tier eligibility, recovery-time
requirement, encryption profile, and destruction authority.

Retention expiry creates technical eligibility for deletion; it does not
authorize deletion. Automated lifecycle deletion is forbidden for
authoritative evidence. Lifecycle rules may change storage tier only after
restore tests prove retrieval time and complete cost.

Destruction requires one immutable manifest naming every exact primary and
recovery Blob version, fingerprint, retention and hold result, reason,
authorizing identity, and expected remaining copy. A separately permissioned
maintenance procedure deletes only those versions, records Azure receipts,
and proves unrelated versions remain. No production application has this
permission, and no prefix, folder, date, age label, or inferred set is a valid
deletion target.

## Encryption and database-ledger digests

Both vaults use TLS in transit, Microsoft-managed encryption at rest, and
infrastructure encryption. Customer-managed keys are not the baseline because
disabling or deleting one can make retained WORM data unreadable; WORM prevents
object deletion, not key loss.

Azure SQL automatic digest upload targets one dedicated private Azure
Confidential Ledger outside the database and ordinary Evidence Vault write
roles. The SQL logical-server identity can contribute digests but cannot
administer the ledger. A separate verifier checks the database ledger, ledger
identity, and receipts and records a bounded result. Database, storage,
infrastructure, and ledger administration remain separate roles.

The Confidential Ledger resource has a `CanNotDelete` lock. Its hard-delete
behavior still requires exported verified digest and receipt checkpoints in
the Recovery Vault. Exact region, capacity, verification schedule, recovery
objective, and cost remain measured settings.

## Restoration and proof

RA-GZRS regional replication is asynchronous. Last-sync time bounds possible
loss, and immutability-policy changes after that time may not exist in the
secondary. Account failover is never automatic: recovery fences writers,
records last-sync evidence, inventories exact versions, restores and verifies
required WORM policies, and starts a new Register recovery lineage.

The separately written Recovery Vault is not an active multi-master. A
clean-room restoration uses a complete manifest to reconstruct one exact
checkpoint in an isolated target. It does not depend on ordinary application
credentials, although it still depends on Azure and the shared Entra tenant.

A recovery copy is trusted only after an isolated drill that:

1. obtains the break-glass recovery role without a running pipeline;
2. restores the selected complete manifest and every named artifact;
3. verifies every byte length and SHA-256;
4. restores or reconstructs the Management Register from its admitted package
   and exact migration prefix;
5. verifies ledger history against Confidential Ledger and exported receipts;
6. rebuilds projections, releases, reusable search inputs, and a selected
   non-production serving target;
7. runs record, traceability, retrieval, authority-note, and negative-access
   checks; and
8. preserves an immutable drill result with measured recovery point, duration,
   cost, discrepancies, and corrective actions.

Provider inventory or a successful metadata read is not a restore test. A
drill never authorizes a production cutover or mutation.

## Monitoring, capacity, and cost

Azure Activity logs, Blob resource logs, change feed, and Blob Inventory are
enabled for both vaults and retained under a separately governed audit policy.
Alerts cover unexpected writes or versions, overwrite and delete attempts,
retention or hold changes, public or Shared Key access, unexpected networks or
identities, missing objects, checksum mismatches, copy delays, replication lag,
encryption changes, ledger digest failures, and failed restore drills.

The complete cost model includes storage and retained versions, RA-GZRS or
other accepted redundancy, operations, inventory, change feed, soft delete,
tiering and retrieval, private endpoints, DNS and firewall processing,
monitoring, audit retention, full copy verification, Confidential Ledger,
restore drills, and operator time. A fixed estimate is not credible until
artifact size, count, growth, retention, region, access frequency, and recovery
objectives are measured.

## Local and Azure proof boundary

Ordinary implementation remains local-first. A filesystem-backed `var/`
adapter with synthetic bytes proves opaque paths, conditional create,
fingerprints, orphan reconciliation, copy manifests, missing and corrupt
objects, holds, expiry, exact destruction manifests, and restoration checks.
It never claims WORM, Azure identity, private networking, geo-redundancy, or
administrative isolation.

Separately authorized non-production Azure proofs must establish locked
version-level retention, negative overwrite and delete behavior, exact-version
holds, per-application RBAC, private endpoints and DNS, public and Shared Key
denial, recovery-subscription isolation, the narrow promotion copy role,
read-back equality, regional behavior and failover, Confidential Ledger digest
verification, clean-room restoration, capacity, and complete secure-topology
cost.

## Alternatives considered

| Alternative | Assessment |
|---|---|
| One Azure storage account for both copies | Rejected. It is simple but does not isolate account deletion, policy, access, capacity, or administrator mistakes. |
| Two accounts in the same application subscription | Better than one account, but a dedicated recovery subscription adds meaningful policy and administration separation for little conceptual complexity. |
| Separate Entra tenant | Stronger tenant-compromise isolation, but adds cross-tenant identity, emergency-access, policy, deployment, and recovery operations that conflict with the requested simple baseline. It remains a later option. |
| A second cloud provider | Stronger provider isolation, but the user expects it not to be available and prefers an Azure-only operating model. It is not part of the baseline. |
| Azure Blob object replication | Useful asynchronous copying, but immutable destination versions can reject replicated source changes. The exact explicit manifest and read-back protocol is already required, so a second copy mechanism adds state without replacing a required control. |
| Azure Data Lake Storage Gen2 | Hierarchical namespace is unnecessary for opaque immutable objects and does not support version-level WORM. |
| Azure Confidential Ledger for all artifacts | Appropriate for small digests and receipts, not large source files, releases, and recovery packages. |
| A workstation, NAS, or self-hosted object store | Does not provide a managed off-machine WORM, regional, policy, monitoring, and restore boundary without operating additional infrastructure. |

## Consequences

- The production storage design remains entirely within Azure and reuses the
  selected Entra managed-identity and private-network model.
- A dedicated recovery subscription provides meaningful application,
  account, subscription, administrator, policy, and regional isolation.
- Provider-wide and shared-tenant failures remain an accepted gap. The design
  must never describe the Recovery Vault as provider- or tenant-independent.
- Every artifact is a single-assignment exact version; a bad object is retained
  and superseded rather than edited.
- Locked retention prevents convenient correction and early deletion.
- Provider-managed keys avoid one customer key becoming a shared data-loss
  switch; restricted key-controlled classes remain gated.
- Exact retention, regions, redundancy exceptions, tiers, recovery point and
  time, legal-hold authority, Management Register package format, drill
  frequency, capacity, and cost remain open. No production vault can be
  created until those values are settled.

## Primary references

- [Azure immutable Blob Storage overview](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-storage-overview)
- [Azure version-level WORM policies](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-version-level-worm-policies)
- [Configure version-level immutability](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-policy-configure-version-scope)
- [Azure Blob versioning](https://learn.microsoft.com/en-us/azure/storage/blobs/versioning-overview)
- [Azure Blob change feed](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-blob-change-feed)
- [Azure Storage redundancy](https://learn.microsoft.com/en-us/azure/storage/common/storage-redundancy)
- [Azure Storage encryption](https://learn.microsoft.com/en-us/azure/storage/common/storage-service-encryption)
- [Azure Blob RBAC](https://learn.microsoft.com/en-us/azure/storage/blobs/assign-azure-role-data-access)
- [Azure Blob monitoring](https://learn.microsoft.com/en-us/azure/storage/blobs/monitor-blob-storage)
- [Azure Storage resource locks](https://learn.microsoft.com/en-us/azure/storage/common/lock-account-resource)
- [Azure Blob object replication](https://learn.microsoft.com/en-us/azure/storage/blobs/object-replication-overview)
- [Azure SQL ledger digest management](https://learn.microsoft.com/en-us/sql/relational-databases/security/ledger/ledger-digest-management?view=sql-server-ver17)
- [Azure Confidential Ledger](https://learn.microsoft.com/en-us/azure/confidential-ledger/overview)
- [Azure SQL database-ledger verification](https://learn.microsoft.com/en-us/sql/relational-databases/security/ledger/ledger-database-verification?view=sql-server-ver17)

## Authorization boundary

This ADR authorizes documentation and design selection only. It does not
authorize implementation, dependency or credential installation, Azure
subscription, account, resource, identity, network, or storage-policy
creation; evidence or backup writes; source, database, or ledger access; model
or embedding calls; corpus publication; Pinecone access; restoration,
deletion, deployment, routing changes, commits, pushes, or any other remote
effect. Every operational capability remains disabled.
