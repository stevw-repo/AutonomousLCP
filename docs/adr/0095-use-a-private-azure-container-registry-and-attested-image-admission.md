---
status: accepted
date: 2026-08-15
refines:
  - "0001"
  - "0090"
  - "0092"
  - "0094"
---

# Use a private Azure Container Registry and attested image admission

## Decision

Use one shared **Azure Container Registry Premium** registry for the five
production pipeline applications. The registry is a shared platform service,
not a shared application capability. It uses `RBAC Registry + ABAC Repository
Permissions`, private endpoints and private DNS, disabled public network
access, and Microsoft Entra identities only. The registry admin user,
anonymous pull, Shared Key-style credentials, floating deployment tags, and
registry-wide application data-plane roles are forbidden.

Premium is selected because the private endpoint already required by ADR 0092
is a Premium feature. Five Premium registries would multiply fixed registry,
private-endpoint, DNS, policy, monitoring, and recovery operations without a
demonstrated security benefit while repository-prefix ABAC can enforce the
required data-plane boundaries.

The registry has four repository families:

- `base/<name>` contains admitted external base images;
- `tool/<name>` contains admitted build, SBOM, scanner, and scanner-database
  artifacts;
- `candidate/<application>` contains unadmitted builds for exactly one of
  `control-plane`, `review-api`, `acquisition`, `legal-processing`, or
  `promotion`; and
- `release/<application>` contains only images that completed the exact image-
  admission protocol.

Every build, copy, signature, scan, admission, deployment, rollback, export,
and retirement names an OCI manifest or image-index digest. Tags are
single-use discovery labels only. A Container Apps revision names
`release/<application>@sha256:<digest>` and never `latest`, an environment
name, or another floating tag.

Use **Notation** with one Azure **Artifact Signing Private Trust** certificate
profile as the central production image-signing trust root. Artifact Signing
provides short-lived certificates, managed HSM-backed certificate lifecycle,
and timestamping without making the project operate private signing keys.
The exact Notation, plug-in, trust-bundle, and profile versions are pinned in
the image-admission policy. Strict verification binds the expected certificate
subject, admitted Private Trust signing chain, Microsoft timestamp roots,
registry scope, release repository, and exact digest. The signed transaction
evidence is preserved.

The one signing profile is intentionally a shared software-release trust root.
It does not merge application runtime, build, pull, deployment, database,
secret, network, or production-data capabilities. A later requirement for
independent software-release administrators may split it into per-application
profiles without changing image or application contracts.

Container Apps does not currently provide the documented AKS-style Ratify
admission control that verifies Notation signatures inside the hosting
platform. The separately permissioned deployment job must therefore verify
the exact signature and complete Image Admission Record immediately before it
creates a revision. A deny-mode Azure Policy also rejects Container Apps image
references outside the one ACR `release/` family or without an `@sha256:`
digest. Neither control is described as protection from a tenant, subscription
Owner, policy-exemption, or Container Apps control-plane compromise.

Use a pinned **Syft** build to produce one SPDX JSON SBOM for the exact final
image and a pinned **Grype** build plus fingerprinted vulnerability database
snapshot for the deterministic admission scan. A small repository-owned
licence-policy evaluator reads the normalized SPDX package and licence fields;
no third licence engine interprets policy. BuildKit produces the build
provenance attestation in in-toto/SLSA form. Exact tool versions are selected
only when an authorized implementation spike verifies their releases,
signatures or attestations, checksums, licences, Python-image coverage, output
contracts, known-vulnerable fixtures, and clean offline execution.

Microsoft Defender for Cloud may later provide an independent continuous
signal, but it is not the admission authority. Its scan can arrive hours after
a push and access to a private registry requires an explicit trusted-service
network exception. The baseline instead reruns the pinned scanner through the
private registry path on a schedule and before every deployment or rollback.

The registry is deployed in an availability-zone-supporting region. Azure's
automatic zone redundancy applies there. It is geo-replicated to every region
from which an admitted production or recovery Container Apps deployment may
start. Geo-replication is active-active, asynchronous availability protection,
not a backup: writes and deletes propagate. Exact OCI image-layout recovery
packages, signatures, SBOMs, provenance, policy, scanner inputs, and admission
records are therefore preserved through ADR 0094 in both the Evidence Vault
and Recovery Vault.

## Repository and identity boundary

Repository ABAC conditions are mandatory. An ABAC-capable role without a
condition acts registry-wide and therefore fails admission. Ordinary build,
runtime, and deployment identities do not receive the separate repository-
catalog lister role.

| Identity | Permitted repository capability | Explicitly absent |
|---|---|---|
| External-artifact curator | Import exact approved digests into named `base/` and `tool/` repositories | Application candidates, releases, deployment, signing, broad delete |
| Build identity for one application | Read admitted `base/` and `tool/` inputs; write without delete only to that application's `candidate/` repository | Other candidates, every release repository, signing, deployment, production data |
| Image-admission copy identity | Read one application's admitted candidate and write without delete to its release repository | Signing key or profile, deployment, runtime or production-data access |
| Image-signing identity | Read and attach a signature only to the named release repository; invoke the Artifact Signing profile | Candidate writes, deployment, registry administration, application data |
| Verification identity | Read the named release repository and its OCI referrers | Write, sign, deploy, delete |
| Pull identity for one Container App | Read only that application's release repository | Catalog listing, another app's image, candidate, base, tool, write, delete |
| Deployment identity for one Container App | Update only that app's image and admitted revision-scoped settings after verification | Registry write, role assignment, another app, runtime data, infrastructure administration |
| Exact-maintenance identity | Delete only digests named by an independently approved retirement manifest | Prefix, age, tag-pattern, or inferred deletion; deployment or production data |
| Registry administrator | Control-plane configuration under privileged workflow | Routine build, signing, deployment, application, or maintenance use |

Each application uses a distinct user-assigned registry-pull identity. Where
the Container Apps identity-lifecycle control can make that identity available
to the platform for image pull but unavailable to the main container, it is
configured that way and proved by a negative token test. If the admitted
platform version cannot enforce that separation, the identity remains limited
to read-only access to the application's own release repository and that
residual visibility is recorded rather than hidden.

Every private build, admission, signing, verification, deployment, scheduled-
scan, and recovery path needs network line of sight to the ACR private endpoint
and complete private DNS records for the registry and every regional data
endpoint. GitHub-hosted or Azure-DevOps-managed agents do not receive a public
registry exception. The exact private ephemeral runner is a later deployment-
platform choice. ACR Tasks and Quick Builds are not part of this baseline.

The ACR path is private; Artifact Signing is not falsely described as a Private
Link service. Current Microsoft guidance exposes a regional Artifact Signing
service endpoint plus certificate and timestamp endpoints. The signing runner
therefore receives narrowly allowlisted outbound access only to the exact
selected endpoints and Entra authentication, while trust roots are admitted
and pinned rather than downloaded during a release. Failure or unavailability
blocks new signing but does not invalidate a timestamped already admitted
release. The selected Private Trust profile, certificate chain, timestamp,
revocation, expiry, and offline long-term verification must pass the Azure
proof before production signing is enabled.

## Exact image-admission protocol

An **Image Admission Record** is immutable deployment evidence, not a legal-
corpus Promotion Manifest or Approval. Signing an application image does not
authorize a corpus promotion, provider call, Pinecone mutation, Ask.Legal
routing change, or any application effect.

One image is admitted through this restartable sequence:

1. **Resolve source.** The job binds the repository commit and tree, build
   definition, application member, `uv.lock`, every source and dependency
   fingerprint, and every admitted base, build, and scanner image digest.
   Builds have no production credentials and cannot fetch a floating base or
   tool image.
2. **Build once from closed inputs.** The isolated builder produces the final
   non-root minimal OCI image or image index, full BuildKit provenance, and
   exact build log. Network access is absent after explicitly mirrored inputs
   are present. Secrets are never Docker build arguments, layers, provenance,
   or image configuration.
3. **Push candidate.** Only the owning build identity pushes the result to its
   `candidate/<application>` repository. The receipt records the exact digest,
   media types, platforms, layer digests, byte sizes, and registry result.
4. **Inventory and inspect.** Pinned Syft emits SPDX JSON for the final image.
   The process proves required packages and both OS and Python dependencies are
   represented, rejects malformed or incomplete output, scans for embedded
   secrets and unsafe image configuration, and verifies non-root, entry-point,
   and read-only-filesystem compatibility.
5. **Evaluate vulnerability and licence policy.** Pinned Grype scans the exact
   SBOM and image against a database snapshot no more than 24 hours old. The
   record binds scanner and database fingerprints, severity sources, complete
   findings, VEX or exception inputs, and policy result. The repository-owned
   licence evaluator binds the exact approved, denied, review-required, and
   unknown licence catalogue.
6. **Reproduce.** A second clean isolated build with the same closed inputs
   must produce the same OCI digest, SBOM content after its explicitly excluded
   observation fields are normalized, and result-determining provenance. A
   mismatch blocks admission and preserves both results.
7. **Copy without rebuilding.** The image-admission identity copies the exact
   candidate manifest, complete referenced blob graph, and required
   attestations into `release/<application>`. It reads the destination back and
   proves the release digest and graph equal the admitted candidate. It may not
   substitute, rebuild, or retag a different digest.
8. **Sign and verify.** Only after the preceding checks pass does the signing
   identity sign the exact release digest. A separate verifier applies the
   strict Notation trust policy, validates timestamp and signer identity,
   inventories the signature and all required referrers, and binds the Artifact
   Signing transaction evidence.
9. **Seal and preserve.** The exact release tag, image/index manifest,
   platform manifests where applicable, signature, SBOM, provenance, and
   required referrers receive `writeEnabled=false` and
   `deleteEnabled=false`. An OCI image-layout recovery package and the complete
   Image Admission Record are written and verified in both vaults under ADR
   0094. The Management Register records the admitted digest only after all
   checks pass.
10. **Deploy after fresh verification.** The application-specific deployment
    job resolves the record, repeats signature and graph verification, reruns
    current vulnerability and licence policy, proves the policy and Azure
    Policy assignments, and updates only its Container App to the exact
    `release/...@sha256:` reference. Readiness and negative-access checks must
    pass before the prior revision can be retired.

An upload, tag, signature, scanner success, or ready revision on its own never
means `ADMITTED`. Failed and partial attempts remain candidates or failed
records and cannot be pulled by a runtime identity.

## Vulnerability and licence admission

The initial closed vulnerability rule is:

- a known-exploited vulnerability blocks regardless of nominal severity;
- a Critical finding blocks;
- a High finding with an available fix blocks;
- an unfixed High finding requires one exact time-bounded security risk
  acceptance; and
- Medium, Low, and Negligible findings remain visible and receive owned
  remediation dispositions rather than being silently dropped.

Unknown severity, unsupported package ecosystems, missing layers, stale or
unverifiable scanner data, scanner errors, and incomplete SBOM coverage block.
An exception names the exact image digest, package, version, vulnerability,
reason, compensating controls, owner, approval evidence, and expiry. It cannot
be copied to another digest or converted into a global ignore file.

The initial closed licence rule is:

- every detected package has an SPDX identifier, an exact approved custom
  licence fingerprint, or an explicit `UNKNOWN` result;
- the policy catalogue classifies it as allowed, denied, or review-required;
- denied licences block;
- unknown, conflicting, missing, or review-required licences block until an
  authorized legal or compliance decision is bound to the exact component,
  version, licence evidence, use, distribution posture, and image digest; and
- notices and source-offer obligations required by an accepted licence become
  named release artifacts and are verified before signing.

The actual approved and denied licence catalogue is not invented by this ADR.
Production image admission remains disabled until the authorized owner
configures it. A software licence decision is not a legal-material Source
Rulebook decision and cannot change legal database content.

Scheduled scans reevaluate every deployed and rollback-eligible digest against
fresh scanner and policy inputs. A new disallowed finding creates an incident,
blocks new deployment or rollback of that digest, and requires remediation or
an exact expiring exception. It does not automatically terminate healthy
running replicas and create an availability failure.

## Base and tool artifact admission

Production builds do not pull base images, build tools, scanner engines, or
scanner databases directly from public registries. A narrow curator imports an
exact upstream digest into `base/` or `tool/` only after preserving:

- upstream registry, repository, digest, media type, and retrieval time;
- upstream signature or attestation and strict verification result where one
  exists;
- release checksums, source and licence references, and supplier identity;
- vulnerability, licence, malware, secret, and configuration results;
- the approved intended use and refresh or expiry rule; and
- the exact ACR import receipt and destination digest-equality proof.

Absence of an upstream signature is a visible supplier-risk decision, never a
successful verification result. Floating upstream tags may be used for
discovery but not admission. Tool executables, container images, databases,
policies, and generator plug-ins are all inputs and receive their own
fingerprints; the scanner is not exempt from its own supply-chain review.

## Retention, retirement, and recovery

ACR is a deployable copy, not the evidence or recovery authority. Automatic
untagged-manifest retention and ACR soft delete remain disabled: retention is
Preview, can remove digest-addressed content, and soft delete is incompatible
with some selected availability configurations. Candidate cleanup and release
retirement use exact manifests only.

Release images and referrers remain locked while any active, prior, rollback,
recovery, incident, or audit record refers to them. Expiry creates eligibility
for retirement, not authority. A separate maintenance decision names every
exact tag, manifest, referrer, and digest; proves no protected reference
remains; proves both vault recovery packages; unlocks only those objects;
deletes them; records provider receipts; and verifies unrelated objects remain.
Prefix, repository, wildcard, age, and “all untagged” deletion are forbidden.

Geo-replication cannot recover an accidental or malicious replicated delete.
A clean-room registry restoration imports one complete OCI image-layout
package into a new private ACR, proves every digest and referrer, verifies the
Notation signature and timestamp using the preserved trust bundle, recreates
ABAC and network policy independently, and deploys only after the normal fresh
admission checks. A restore drill never authorizes production use.

## Monitoring, break-glass, and cost

Activity and registry resource logs alert on public-access changes, admin-user
enablement, registry-wide or unconditional repository roles, catalog grants,
unexpected imports or pushes, release-repository writes, signature changes,
unlock and delete operations, policy exemptions, tag-only Container Apps
references, failed verification, scanner staleness, geo-replication lag, and
recovery-export failure.

Break-glass cannot mean “skip evidence.” An emergency deployment or rollback
uses a separately authenticated, time-bounded identity and an immutable reason,
target application, digest, current findings, accepted risk, approvers,
configuration, expiry, and restoration plan. It still uses an existing locked
release digest, records every Azure result, and cannot grant roles, upload new
code, sign a new digest, or change another application.

The complete cost model includes one Premium registry, every geo-replica,
storage and retained referrers, private endpoints and DNS, network processing
and inter-region egress, Artifact Signing, private build and admission runners,
SBOM and scanning compute, scanner-data mirroring, logs and retention, OCI
exports to both vaults, restore drills, and operator time. One shared Premium
registry is the cost simplification; security controls are not silently removed
to reduce the bill. Exact regions, throughput, storage, retention, recovery
objectives, runner platform, logging duration, and measured cost remain open.

## Local and Azure proof boundary

Ordinary development builds and runs the same OCI images locally without Azure
credentials. A local OCI registry or image store, synthetic base images,
fixture SBOMs, a test-only signing key, fake Artifact Signing receipts, and
repository-owned policy fixtures prove digest pinning, graph copying,
signature verification, scan and licence outcomes, stale data, exceptions,
locking state, deployment admission, exact retirement, and restoration. The
test trust root is cryptographically and configurationally incapable of
production trust.

Separately authorized Azure proofs must establish repository-prefix ABAC and
negative access from every wrong identity; private endpoints and DNS from all
five environments and the private runner; disabled public, anonymous, admin,
and catalog access; pull-identity lifecycle behavior; exact OCI graph copy;
Artifact Signing and timestamp verification; deny-mode Container Apps image
policy; release locks; geo-replication behavior; scheduled scanning; clean-room
restore; break-glass restrictions; capacity; and complete secure-topology cost.

## Alternatives considered

| Alternative | Assessment |
|---|---|
| Five Premium ACR registries | Stronger registry control-plane blast-radius separation, but five times the fixed private registry surface. Repository ABAC, separate identities, locked release graphs, and recovery exports preserve the current requirements more simply. Split later if a genuinely different administrator, geography, classification, or recovery objective requires it. |
| One Standard ACR | Less expensive, but Private Link is unavailable. It conflicts with ADR 0092's accepted private Azure service path. |
| Separate build and release registries | A clear physical boundary, but duplicates Premium and private-network cost. Candidate and release repository families plus ABAC prevent runtime pull of candidates while exact copy, signing, and locking preserve admission. |
| GitHub Container Registry or another cloud registry | Adds a second provider, credential and public-network path without a requirement that ACR cannot meet. It conflicts with the requested Azure-only baseline. |
| ACR Tasks as the build authority | Convenient but adds a registry-hosted code-execution and task-permission surface and complicates the ABAC boundary. A privately connected isolated builder keeps untrusted build execution outside the registry control plane. |
| Azure Key Vault signing certificate | Strong and supported by Notation, but makes this project own certificate issuance, rotation, expiry, and timestamp operations. Artifact Signing Private Trust is the simpler managed signing boundary. |
| Unsigned digest-only images | Digests prove content identity but not who admitted it. They do not satisfy the publisher-authenticity requirement. |
| Microsoft Defender for Cloud as sole admission scanner | Valuable continuous signal, but asynchronous results and a private-registry trusted-service exception do not provide the exact reproducible pre-signing gate. |
| Trivy as the initial single scanner | Broad capability, but a separate local SBOM, vulnerability, and licence-policy boundary is easier to test independently. The March 2026 compromised Trivy releases also reinforce the rule that scanner tools and databases must never be downloaded or floated during admission. |
| Automatic ACR retention or purge | Unsafe for digest-pinned rollback and recovery graphs and unable to express the exact authority and dependency checks required before deletion. |

## Consequences

- The five applications share one Azure registry control plane and one signing
  trust root, but not repository, pull, build, deployment, or runtime access.
- Premium, private endpoints, ABAC, Artifact Signing, scanning, geo-
  replication, and OCI recovery exports are production requirements, not
  optional hardening labels.
- The registry has no public path, but the isolated signing runner needs a
  narrow outbound path to the selected regional Artifact Signing, Entra, and
  timestamp endpoints until a proved private alternative exists.
- The application deployment workflow becomes an explicit security authority
  and must fail closed before changing a Container App revision.
- Azure Policy and deployment-time verification mitigate unsupported images,
  but Container Apps does not provide the selected AKS-style in-platform
  signature admission. Tenant and control-plane compromise remain outside this
  boundary.
- ACR availability replicas are not backups. ADR 0094 vault packages remain
  required even when geo-replication is healthy.
- Production admission remains disabled until exact tool versions, the licence
  catalogue, regions, retention, recovery objectives, runner design, and cost
  have passed their separately authorized proofs.

## Primary references

- [ACR service tiers and Premium features](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-skus)
- [ACR Private Link and private endpoints](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-private-endpoints)
- [ACR Entra ABAC repository permissions](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-rbac-abac-repository-permissions)
- [ACR roles and repository referrer access](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-rbac-built-in-roles-overview)
- [Container Apps managed-identity image pull](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity-image-pull)
- [ACR OCI signing and verification overview](https://learn.microsoft.com/en-us/azure/container-registry/overview-sign-verify-artifacts)
- [Notation with Azure Artifact Signing](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-tutorial-sign-verify-notation-artifact-signing)
- [Azure Artifact Signing overview](https://learn.microsoft.com/en-us/azure/artifact-signing/overview)
- [Azure Artifact Signing trust models](https://learn.microsoft.com/en-us/azure/artifact-signing/concept-trust-models)
- [ACR image locking](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-image-lock)
- [ACR geo-replication](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-geo-replication)
- [ACR zone redundancy](https://learn.microsoft.com/en-us/azure/container-registry/zone-redundancy)
- [ACR import and OCI referrer permissions](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-import-images)
- [ACR untagged-manifest retention](https://learn.microsoft.com/en-us/azure/container-registry/container-registry-retention-policy)
- [Defender image-scanning timing](https://learn.microsoft.com/en-us/azure/defender-for-cloud/agentless-vulnerability-assessment-azure)
- [Container Apps allowed-registry policy example](https://learn.microsoft.com/en-us/samples/azure-samples/aca-azure-policy/aca-azure-policy/)
- [BuildKit build attestations](https://docs.docker.com/build/metadata/attestations/)
- [Syft SBOM generation](https://oss.anchore.com/docs/guides/sbom/)
- [Grype vulnerability database](https://oss.anchore.com/docs/guides/vulnerability/database/)
- [Trivy March 2026 security incident](https://github.com/aquasecurity/trivy/discussions/10425)

## Authorization boundary

This ADR authorizes documentation and design selection only. It does not
authorize application or infrastructure implementation, container build or
execution, dependency or tool installation, registry or signing access,
scanner-database download, Azure resource creation, identity or role
assignment, private endpoint or DNS changes, image import, push, copy, signing,
scan, locking, export, deployment, rollback, deletion, external source access,
provider calls, corpus promotion, Pinecone or routing mutation, commit, push,
or any other remote effect. Every operational capability remains disabled.
