# AskLegal Legal Database Pipeline — Working State

Updated: 2026-08-18 — docpro-MS-7D99 (Ubuntu 24.04.4 LTS, x86-64)

## Current outcome

The user has instructed the agent to continue working toward the accepted
local V1 and stop only when a material user decision or new permission is
required. Safe repository-only implementation and validation should therefore
continue in dependency order without routine confirmation. Infrastructure
products are now selected, but exact external admission, credentials, messages,
commit/push, deployment, destructive work, and production effects remain
explicit stop gates.

The user authorized M7 with the instruction "M7." The complete offline local-
synthetic milestone is **COMPLETE** against
`docs/design/M7_END_TO_END_CONFORMANCE_PLAN.md`.

M1 through M7 now pass locally. The user subsequently authorized committing
and pushing the complete accumulated M2–M7 implementation to `main`. Git state
was re-verified on 2026-08-17: the M2–M7 implementation is commit `297afda`,
the earlier validated foundation is commit `88f8e92`, and the current clean
`main`/`origin/main` head is documentation commit `3726ee4`. Ignored local
runtime evidence under `var/` is excluded.

The accumulated Hong Kong readiness and disabled V1 POC checkpoint was
committed on 2026-08-17 as `6be9dd0` (`feat: add Hong Kong readiness and V1
POC contracts`), followed by continuity commit `5140578`. The user explicitly
confirmed the exact private destination and `main` branch; both commits were
pushed to `https://github.com/stevw-repo/AskLegal-LegalDBPipeline.git`, whose
`main` now resolves through `5140578`.

The user then authorized read-only official legal-source access and requested
that all 14 accepted Hong Kong Legislation source roles be completed together.
This means the 14 roles across the three frozen Hong Kong Legislation scopes;
it does not extend to Cases, HKEX Regulatory Materials, other jurisdictions,
models, Pinecone, deployment, publication, or production mutation. RSS is
permitted only as a discovery/change signal and never as controlling legal
evidence or proof of complete no-change.

Official-source verification started on 2026-08-17. On 2026-08-18 the user
reported that the AskLegal legal team confirmed all source rights and
permissions green for the fourteen frozen Hong Kong Legislation source roles.
The register preserves that conclusion as a separate legal-team attestation;
it does not rewrite the previously observed DATA.GOV.HK, HKeL, GLD, Basic Law,
archive, or NPC publisher notices. Legal admission is therefore clear while
technical admission remains fail-closed per source and endpoint.

The first operational source checkpoint is now implemented. The strict source
register at `packages/source-connectors/src/asklegal_source_connectors/
hk_legislation_source_register.json` binds all 14 source roles, 78 exact
endpoint contracts, seven rights-evidence entries, one legal-team attestation,
and fingerprint
`sha256:e792bc88bc3dca14dee4816927291429d002d73efef18a10b217bd640e0dfc58`.
Five source roles are configured, five are partially configured, and four are
technically blocked. The official HTTPS connector is credential-free, direct, TLS-
validating, bounded, no-redirect, proxy-free, cookie-free, content-admitting,
and fail-closed on contract drift. RSS results are discovery signals only.

A read-only live probe returned HTTP 200 with the expected media types for all
44 enabled exact endpoints. Bounded full GETs captured only the English and
Traditional Chinese current and past XML inventories plus DATA.GOV.HK's RSS
feed in memory. No ZIP corpus body was downloaded or saved. The four inventory
captures returned `CAPTURED`; RSS returned `DISCOVERY_SIGNAL_CAPTURED`. No
source artifact was written, published, or committed as legal evidence.

On 2026-08-18 the earlier build-first sequencing assumption was superseded by
the legal team's clearance. Repository-only work now includes a complete
14-role/77-endpoint engineering report, safe binding for all six declared item
URL templates, an atomic exact-member bilingual inventory connector, and a
rendered-session connector boundary. The report now identifies 62 endpoint
procedures with implemented handling and 16 endpoints requiring direct inert
evidence, catalogue, or physical procedures; five source roles are technically
complete and operationally callable.

The user selected Patchright for JavaScript-backed access. ADR 0100 pins
Patchright `1.62.1` to the acquisition worker and confines it to ephemeral,
credential-free, exact-host discovery. Browser output is reduced to a
sanitized request-map summary and can return only a discovery result; rendered
HTML cannot become legal evidence, prove completeness/no-change, or authorize
processing. Exact legal bytes still require inert direct capture and the
ordinary manifest-last evidence flow. No CAPTCHA or access-control bypass is
permitted.

The Mac now has Patchright's local Chrome for Testing and headless-shell
runtime `151.0.7922.34` (Playwright Chromium build `1234`). A bounded live NPC
run completed through the registered `/index` endpoint as
`DISCOVERY_SIGNAL_CAPTURED`, observing 17 same-host requests and producing a
3,367-byte sanitized summary. It exposed the official read-only `wjConfig` API;
the strict HTTP connector separately captured its 138-byte JSON response in
memory with fingerprint
`sha256:680b4065825b32fb4fc99ea872c824621416890e9714d53cecb99008b741a71c`.

Bounded HKeL Gazette discovery proved the exact same-host client-check paths
`/checkconfig/submitClientConfig.do`, `/client-check`, and `/grid`. The
rendered page returned 200 at `/gazette`, but the role remains technically
blocked until the grid request body, pagination/completeness proof, and exact
artifact locators are contracted. GLD e-Gazette redirected to its terms page
and requested a blocked Cloudflare Turnstile script; no terms acceptance or
challenge bypass occurred. The NPC/NPCSC official-materials site failed with
Chromium TLS cipher/version mismatch and remains blocked.

Inert inspection of the official NPC application identified its direct
read-only enumeration and aggregate metadata APIs. Both exact `GET` endpoints
are now registered. The enumeration endpoint passed the actual bounded
connector as `DISCOVERY_SIGNAL_CAPTURED`: HTTP 200, `application/json`, 7,936
bytes, fingerprint
`sha256:910dff8c504334db211dc53f527c1f4b9d39ea8233f0a4af087b6a1a6835719e`.
The aggregate endpoint separately returned HTTP 200 JSON, 3,228 bytes,
fingerprint
`sha256:c1148d4e638445cf9045dd6828ccc7df486bf84a4d4a8371ca13c31b7acb145c`,
with the publisher's aggregate classification and popularity fields. Both are
discovery metadata only and do not prove a complete law inventory or no
change. The accepted M4
method contract remains closed to `GET` and `HEAD`;
the internal NPC POST search call was not added without an exact protocol and
request-body contract.

HKeL's official verified-legislation coverage list was identified as a direct
PDF endpoint independent of its active item pages. The exact endpoint is now
enabled under the partially configured verified-copies role and passed the
actual connector as `CAPTURED`: 16,659,689 bytes, `application/pdf`, fingerprint
`sha256:098d592927bfbcb34ecdeae573077399c7429e83c2558eb516c91800143f9be5`.
The bytes remained in memory only. This proves the coverage inventory path,
not the still-disabled per-item verified-copy locator.

The official HKeL client-check page exposes a deterministic no-JavaScript
fallback, but live inspection proved that it redirects from HTTPS to HTTP and
then returns only a reduced `/no-js` page without the requested item or PDF
download metadata. The connector will not follow that downgrade or execute the
publisher's active JavaScript. Patchright now completes the isolated discovery
handshake, but this no-JavaScript path still cannot supply item/PDF locators and
is not mislabeled as source evidence.

Official fetch results now retain the exact inert transport envelope for
successful, unsafe, redirect/status-drift, and media-drift responses. A genuine
transport failure retains no invented response. This closes the evidence-loss
gap before official outcomes are composed into the acquisition worker's
manifest-last flow.

The user has now accepted a strictly internal single-Ubuntu-host V1 POC. The
user said on 2026-08-18 that they will probably do significant parts of
development on the Ubuntu machine from now on; the Mac is not retired and this
is not yet a settled change of development host. One Ubuntu
24.04 x86-64 PC with 64 GB RAM and local ext4 storage runs the five
applications, SQL Server 2025 Developer, separate general and promotion Durable
Task Scheduler emulators, separate Primary and Recovery Versity Gateway
instances, systemd credential delivery, and local telemetry. Hosted Pinecone
Cloud in a dedicated isolated POC project is the replaceable vector-serving
copy. Azure application hosting remains post-V1/deferred.

Both vaults currently share one filesystem and therefore provide only
`LOGICALLY_SEPARATE_POC_RECOVERY`. The earlier single-physical-disk premise was
a reporting mistake corrected on 2026-08-18; the host actually has three
physical disks. The recovery class is deliberately left unchanged until vault
placement is decided, because a stronger class must be earned by proved
separate-disk placement rather than inferred from disk count. Scheduler state is memory-only; loss fences
the old execution and starts reconciled replacement work from the last safe SQL
checkpoint, never a claim that lost history resumed. Exact topology, image
pins/digests, incremental implementation, and verification planning are the
current infrastructure objective. No deployment or external effect is
authorized; explicit permission is required before the first real Pinecone
write.

No credential, Azure resource,
Azure OpenAI/model or embedding call, Pinecone target, provider backup,
Ask.Legal route/slot, deployment, corpus publication, or production effect was
accessed or changed. Read-only official Hong Kong source pages and catalogue
metadata were accessed only for source-contract and rights verification; no
legal corpus was bulk-downloaded, no source artifact was published, and no
external account or resource was changed. Ask.Legal admin-portal integration
remains deferred; M7 stabilizes the Review API boundary it will later consume.

The current authorized parallel workstream is local, network-disabled Hong
Kong Legislation package readiness with `HK-LEG-ORDINANCES` first. Its frozen
readiness inventory and complete 27-rule ordinary offline path are
implemented and validated, but all real scopes remain `NOT_READY` and cannot
activate or process real observations.

The accepted Ubuntu infrastructure products, complete service/network/storage/
systemd topology, and 12-step incremental verification plan are now recorded in
`docs/design/V1_POC_UBUNTU_TOPOLOGY.md`. Its first implementation slice is
complete: `infrastructure/poc/topology.json` is a secret-free, disabled-by-
default closed inventory and `tools/v1_poc_topology.py` plus 10 focused tests
fail closed on authority, isolation, secret, surface, recovery, scheduler, and
artifact drift. The ordinary developer entrypoint now executes this gate.
All 16 services remain disabled; 3 existing artifacts are digest-pinned and 13
remain `PIN_REQUIRED`. The read-only host-admission policy and synthetic facts
validator are also complete with 14 focused cases. They require exact Ubuntu
24.04 x86-64, memory/disk/ext4/path, credential protection, nftables, sealed
journal, time, and Docker isolation facts but always return `admitted=false`.
The three durable host blockers are `CREDENTIAL_INTERFACE_PROOF`,
`HOST_PACKAGE_LOCKS`, and `PRIVATE_SUBNET_SELECTION`. The secret-free artifact
registry is also complete: 12 unique artifact entries cover all 16 services,
the SQL and shared DTS candidates are digest-pinned but require Ubuntu reproof,
10 artifact selections/builds remain, and all 12 entries are
`admitted=false`. Build, registry pull/push, service enablement, actual host
collection, and provisioning remain permission gates. Read-only credential-
interface research and the local difference, cause, proved-event, disposition,
record, and release-accounting gates are complete. After the repository-only
runtime-input and credential-loader work below, the infrastructure critical
path needs the Ubuntu host and explicit image pull/run permission; real Hong
Kong package admission separately needs complete source evidence and package-
owner authority.

The next repository-only infrastructure checkpoint is also complete.
`infrastructure/poc/application_image_inputs.json` freezes all five repository
image inputs and their complete 19-distribution closures, health commands,
topology identities/listeners, exact locks, and hardening profile. Ten focused
tests enforce five explicit blockers and `tools/dev_test.py` now runs the gate.
No runtime command is declared: every current local-fake application
entrypoint remains `ADAPTER_REQUIRED`, so it cannot be mistaken for a V1
continuous service. `tools/v1_poc_collect_host_facts.py` adds the bounded
read-only Ubuntu collector with three focused tests. It refuses macOS, reads no
credential value, writes nothing, and emits only the exact fact schema already
consumed by host admission.

`infrastructure/poc/application_runtime_inputs.json` now freezes the exact
disabled per-process runtime inputs: five application/service identities, five
operational database roles, four scheduler/task hubs, permitted vaults, 25
logical destinations, exact topology networks/listeners/outbound profiles,
and 19 credential filenames. Thirteen focused tests enforce seven remaining
blockers, and `tools/dev_test.py` runs this gate too. The application-runtime
package now provides a locally tested process-side systemd credential loader
with absolute-directory, canonical-name, no-symlink, exact `0400`, bounded-
read, and redacted-error rules. This does not resolve real addresses, start a
service, prove container credential delivery, or settle the SQL/Versity vendor
credential-interface conflict.

The Management Register adapter now provides a V1-only SQL connection factory
that composes exact non-secret topology with a redacted password value. It
allows only `sql-server:1433`, `AskLegalPocOperational`, and the five application
principals; requires strict encryption, certificate hostname validation, and
no trust bypass; bounds login time; and emits only a closed failure code. The
16 focused cases also bind the pinned driver's password-log sanitizer. Trusted
certificate issuance and application-image trust-bundle delivery remain a new
explicit `SQL_SERVER_CERTIFICATE_TRUST` blocker; no certificate or trust root
was generated.

The locked Durable Task SDK now has an exact V1 settings/factory boundary with
seven focused cases. General and promotion emulator DNS names and task hubs are
closed, Review cannot acquire a scheduler, no token or TLS is added to the
private emulator networks, worker capacity must be explicit, and memory loss
remains replacement from a safe SQL checkpoint.

Locked Boto3 `1.43.49` now supplies the disabled V1 S3-compatible vault
boundary. It disables ambient credential lookup, uses only exact credential
files, SigV4 path-style HTTPS with vault-specific CA bundles, and the frozen
three-attempt/five-second-connect/30-second-read profile. Provider version IDs
round-trip losslessly. Conditional create, SHA-256 read-back, COMPLIANCE
retention, legal hold, replay adoption, collision/corruption handling,
manifest-last writes, and primary-to-recovery copying pass against deterministic
S3 fakes. No delete API exists. Seven application-composition cases prove that
all five applications construct only their own SQL, scheduler, and authorized
Primary/Recovery vault roles and load every declared provider credential file
without connecting, inventing an unselected provider format, or reading an
environment password. Provider material without an admitted adapter remains an
opaque redacted value.

The composition audit found and corrected one V1 topology omission. The
accepted M3 protocol requires read-only evidence for Control proposal
preparation and Review evidence streaming, so both applications now have
separate Primary Vault credential references and internal network membership.
The topology therefore has 25 credential references. No vault credential,
real endpoint, certificate, bucket policy, or permission was created; those
remain blocked. `VAULT_SERVER_CERTIFICATE_TRUST` is an explicit seventh runtime
blocker.

The framework-free application-runtime package now has the complete exact V1
readiness dependency inventory for all five applications and a bounded async
gate. It rejects missing, extra, duplicate, reordered, or unbounded probes;
runs the complete set with per-probe deadlines; normalizes failure and timeout
states; and becomes ready only when every dependency succeeds. The disabled
runtime policy carries the same dependency codes and cross-checks them against
the package. SQL now has a non-mutating exact `SELECT 1` readiness check with
resource cleanup, while each S3 vault verifies versioning and Object Lock
without writing. Official Microsoft guidance documents connectivity testing
to emulator gRPC port 8080 but no non-mutating SDK/task-hub health operation.
Scheduler, telemetry, Review/egress, and actual host probe behavior therefore
remain inside `BOUNDED_READINESS_PROBES`; no private SDK API or fake mutation
was substituted.

The accepted systemd graph is now machine checked rather than prose only.
`infrastructure/poc/systemd_unit_inputs.json` binds all 16 topology services,
two disabled privileged bootstrap one-shots, and five disabled timers whose
cadences remain package/admission inputs. It fixes unit dependencies, runtime
identities, exact credential files, write paths, root-owned management, restart
policy, `NoNewPrivileges`, strict protected system paths, private temporary
space, and an empty capability bounding set. Ten focused tests reject missing
units, identity/credential/dependency drift, weaker hardening, secret-bearing
configuration, timer defaults, bootstrap enablement, or authority expansion.
Six blockers keep runtime commands, unit installation, image pulls, credential
bridging, subnets, and Ubuntu proof unavailable; the checker never contacts or
modifies systemd.

The accepted host accounts are also now machine checked. The host-identity
contract binds the ten services that own persistent application/vault/telemetry
paths to distinct locked, non-login, group-isolated accounts and all 14 exact
write paths. Numeric UID/GID values stay null and every account stays
`created=false` until collision checks occur on Ubuntu. Nine focused tests
reject missing/shared/root identities, interactive shells, invented IDs,
ownership drift, embedded secrets, or host-mutation authority. Four blockers
retain numeric allocation, container UID/GID mapping, ownership read-back, and
real Ubuntu proof. SQL remains image-defined; pathless DTS and egress container
identities are not falsely declared as host accounts.

The executable credential-interface proof now has exact machine-checked inputs
instead of prose alone. `credential_interface_proof_inputs.json` binds SQL and
both Versity services to their current artifact selections, systemd credential
names, six proof steps, seven canary-inspection surfaces, 12 required evidence
classes, restart/rotation behavior, named cleanup, and the accepted fail-closed
decision gate. All three results remain `NOT_RUN`; image and host actions remain
unauthorized. Twelve focused mutation cases reject false execution, authority,
secret-rule weakening, evidence loss, artifact/systemd drift, or embedded
material.

The V1 admission result is now one fail-closed machine verdict rather than an
inference from separate static checks. `infrastructure/poc/v1_admission_gate.json`
binds 14 ordered components and all effect authority to false;
`tools/v1_poc_admission.py` re-runs the eight implemented static checkers and
returns exactly `V1_POC_NOT_ADMITTED`, with eight static contracts validated
and 14 blockers. It cannot admit V1, mutate the host, resolve or pull an image,
create a credential, contact a source/provider, or write Pinecone. Twelve
focused mutation cases protect the component order, evidence references,
states, blockers, authority, secret-free content, aggregate verdict, and
static-check propagation.

Read-only credential-interface research is now recorded in
`docs/design/V1_POC_CREDENTIAL_INTERFACE_SPIKE.md`. Official SQL material did
not reveal a supported password-file input, and Versity documents root
credentials only through arguments/environment while its internal IAM files
are persistent plaintext. No image pull or runtime test was authorized or
possible on the current Mac. The exact-image proof therefore remains gated on
an admitted Ubuntu test host, immutable pins, synthetic credentials, and
explicit pull/run permission; a failed proof will require a user choice rather
than a silent weakening of the accepted secret rule.
Current vendor interfaces expose one fail-closed admission risk: official SQL
Server container and Versity guidance uses environment variables or command
arguments for root credentials, which does not yet prove the accepted file-only
`systemd-creds` boundary. Credential-interface spikes must resolve this before
either service can be admitted; the rule is not silently relaxed.

## Completed M7 implementation

### Stable offline conformance interface

`asklegal-local` is exposed as a second console entry point of the existing
control-plane distribution and delegates to repository tooling in
`tools/local_conformance.py`. It is not a sixth deployed application, and the
closed 5-application/14-package architecture graph is unchanged.

The accepted interfaces are implemented:

```text
uv run --frozen --all-packages asklegal-local reset --exact-test-state
uv run --frozen --all-packages asklegal-local prove --scenario <E2E-001..E2E-032>
uv run --frozen --all-packages asklegal-local prove --all
```

Reset validates the exact resolved ignored `var/local-conformance` path and its
marker before deletion. The runner denies DNS/socket access, binds exact locks,
contract/protocol/policy inputs, deterministic clocks/IDs/jitter, and one
independent expected result/fact/effect entry for every scenario.

### Complete flow and scenario matrix

`E2E-001` plans and schedules through the versioned Control API, then connects
the actual local acquisition service, primary/recovery vault fakes, ZZZ
activation/rule engine, candidate renderer, Corpus Release/DSI/
coverage/promotion builders, frozen proposal package, Review HTTP API and
loaded minimal browser client, named-human Approval, fake embedding/replacement
target/backup/routing, reverse-swap, and exact same-lineage recovery.

`E2E-002` through `E2E-032` prove supported no-change, watcher false positive,
duplicate/replay, restart, lost acknowledgement, command conflict, stale
version/fencing, overlap, cancellation before and after promotion, incomplete/
hostile/unknown source handling, non-total rules, carry-forward, withholding,
quarantine re-entry/recurrence, stale and app-token review rejection, revoked/
consumed Approval, vector/target/cost/recovery/base/coverage failures,
post-cutover rollback, digest-verified Management Register recovery, broad-
deletion denial, and ZZZ environment containment.

`prove --all` runs the complete catalogue twice under clean path-distinct roots
and compares both authoritative report bytes and every generated artifact's
relative path, byte size, and SHA-256 digest. The final report statement is
exactly `local synthetic platform proved`; its fingerprint is
`sha256:1371eca6e75e380f8a754e665850e3839aa7e2ff9de4b86e18c5061ae026d8ae`.

### Reporting and Review projection support

`asklegal_reporting` now owns strict immutable scenario and complete-report
values. An incomplete catalogue, duplicate identity, count/result drift, or
fingerprint drift fails closed. `LocalReviewProjectionStore` accepts explicit
frozen proposals and a snapshot for M7 composition while preserving its M3
defaults.

## Hong Kong Legislation readiness checkpoint

The user accepted the recommendation to start one real-package workstream and
explicitly authorized local, network-disabled implementation. The first target
is `HK-LEG-ORDINANCES`; no source access, model call, cloud work, or production
action was authorized.

The new frozen package at
`packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package/` binds:

- all 14 accepted Hong Kong Legislation stable source roles without URLs,
  credentials, or acquired bytes;
- the three accepted non-overlapping Release Scopes, with Ordinances marked as
  the current implementation target;
- exact source, rights, bytes, incomplete rule/fixture-universe, evaluation,
  model-profile, owner, and attestation blockers; and
- a package inventory/fingerprint of
  `sha256:8176705e872a1751e280093435731b7302a123e9846a94e58058e919067541f5`.

The second checkpoint adds the offline `HKLEG-BASE-INV-001` vertical slice:

- one strict package-local Draft 2020-12 schema for the source/reason
  catalogues, rule, input, fixture catalogue, fixture, and decision;
- closed bindings from declared legal nature to the three accepted Release
  Scopes and one admitted current-inventory source role;
- four terminal branches—accounted, unaccounted, duplicate-owned, and
  misassigned—with no implicit success;
- four small synthetic fixture manifests and separately hashed exact expected
  decisions; and
- a deterministic conformance evaluator that validates all locks and emits no
  legal disposition or record.

The third checkpoint adds the preceding offline `HKLEG-BASE-OBS-001` slice:

- exact synthetic rulebook, Release Scope registry, and HKeL publication-
  specification locks at one cutoff;
- the release-blocking current-inventory and Gazette observation source set;
- five terminal branches for frozen success, missing/incomplete/stale required
  source, mixed cutoff, lock mismatch, and post-cutoff source change;
- five separately hashed fixtures and expected decisions; and
- an ordered proof that only the frozen-success branch advances through
  `HKLEG-BASE-OBS-001` → `HKLEG-BASE-INV-001`.

The fourth checkpoint adds the following offline `HKLEG-BASE-EVID-001` slice:

- matching English and Traditional Chinese current XML plus matching official
  HKeL copies for the exact synthetic version;
- both ADR 0081 copy classes, `VERIFIED` and `ASSISTED`, as permitted success
  paths without treating assisted copies as verified;
- five separately hashed fixtures and expected decisions covering both success
  modes, a missing Traditional Chinese current XML block, reconciliation
  conflict quarantine, and forbidden historical substitution; and
- an ordered proof through `HKLEG-BASE-OBS-001` → `HKLEG-BASE-INV-001` →
  `HKLEG-BASE-EVID-001`, with only an exact passing bundle advancing to
  `HKLEG-BASE-STATE-001`.

The fifth checkpoint adds `HKLEG-BASE-STATE-001`:

- exact predecessor binding to passing inventory and bilingual-evidence gates;
- one clear branch requiring complete current item, provision, structure,
  location mapping, version, operative-effect, no-conflict, and written-
  rulebook support facts;
- six fail-closed branches for missing required signals, partial or ambiguous
  mapping, accepted-source conflict, unknown source semantics, unproved
  operative effect, and missing rulebook support;
- seven separately hashed fixtures and expected decisions; and
- a composed ordered proof through `HKLEG-BASE-OBS-001` →
  `HKLEG-BASE-INV-001` → `HKLEG-BASE-EVID-001` →
  `HKLEG-BASE-STATE-001`.

The passing STATE result establishes only `OPERATIVE_CURRENT` at the frozen
cutoff. It keeps legal disposition `NOT_APPLICABLE`, emits no record, and uses
`historical_assertion_scope: PENDING_LIMIT_RULE`.

The sixth checkpoint adds `HKLEG-BASE-LIMIT-001`:

- an exact predecessor binding to the successful present-state result;
- one success branch that changes the assertion scope to
  `PRESENT_STATE_ONLY` without creating a historical claim;
- four blocked branches for unsupported historical events, effective dates,
  identity or continuity relationships, and complete event chains;
- five separately hashed fixtures and expected decisions; and
- a composed ordered proof through `OBS-001`, `INV-001`, `EVID-001`,
  `STATE-001`, and `LIMIT-001`, with only the exact present-state-only result
  allowed to advance to `HKLEG-BASE-ID-001`.

The seventh checkpoint adds `HKLEG-BASE-ID-001`:

- new opaque register-owned identity requests for all four ADR 0011 layers,
  without inventing their unresolved concrete encodings;
- source identifiers and legacy Distillation/Pinecone IDs preserved only as
  aliases or trace facts;
- blocked source/legacy authoritative identity reuse and unproved lineage;
- quarantined duplicate or continuity ambiguity even when similarity is
  claimed; and
- five exact fixtures with two passes, two blocks, and one quarantine, with
  only clean allocation requests advancing to `HKLEG-BASE-DISP-001`.

The eighth checkpoint adds `HKLEG-BASE-DISP-001`:

- one exact supported result for each of `SEARCHABLE_CURRENT`, `WAITING_ROOM`,
  `EVIDENCE_ONLY`, `HISTORICAL`, and `QUARANTINE`;
- a visible Coverage Gap when an operative event is proved without matching
  current consolidation evidence;
- rejection of publication or one status signal as a disposition shortcut;
- seven separately hashed fixtures and expected decisions; and
- only the exact searchable-current branch advancing to
  `HKLEG-BASE-REC-001`; every other branch emits no record.

The ninth checkpoint adds `HKLEG-BASE-REC-001`:

- exact ADR 0021 canonical bilingual rendering with English first and
  Traditional Chinese second, NFC, LF, and language-correct punctuation;
- the repository-wide six-field Serving Record shape and exact metadata-only
  fingerprint, excluding register-issued identity;
- one synthetic metadata profile that is conformance-only and not an admitted
  production profile;
- six fixtures covering exact candidate creation, non-searchable exclusion,
  legacy identity rejection, incomplete alignment, non-canonical rendering,
  and unapproved authority notes; and
- only the exact candidate branch advancing to `HKLEG-BASE-REL-001`.

The tenth checkpoint adds `HKLEG-BASE-REL-001`:

- complete accounting for objects, locations, dispositions, candidates,
  Coverage Gaps, Quarantines, investigations, and identity decisions;
- an explicit initial-baseline marker with no predecessor release;
- seven fixtures covering success, missing and duplicate inventory,
  inconsistent disposition output, false predecessor, missing references, and
  unresolved completeness;
- one fingerprint over the complete exact accounting input; and
- eligibility only to build a candidate Corpus Release, with no publication,
  Approval, promotion, or deployment authority.

The eleventh checkpoint adds `HKLEG-BASE-REVIEW-001`:

- one exact named question, affected-object set, registered-source request,
  permitted fact, stopping condition, and responsible Legal Desk;
- four permitted on-demand historical/discovery source roles;
- five fixtures covering one successful targeted review and blocks for no
  material uncertainty, whole-history acquisition, unregistered sources, and
  mismatched fact scope; and
- no source access or historical assertion; only an exact task may advance to
  `HKLEG-BASE-HIST-001`.

The twelfth checkpoint adds `HKLEG-BASE-HIST-001`:

- six fixtures prove one exact permitted fact and block current-evidence
  substitution, similarity-only proof, unavailable/insufficient evidence, and
  discovery-only proof;
- conflicting evidence quarantines the affected decision; and
- history neither reconstructs current text nor manufactures legal events.

The thirteenth checkpoint adds `HKLEG-BASE-CHANGE-001`:

- seven fixtures cover no post-cutoff change, both permitted later-change
  strategies, lost frozen-package evidence, a missing separate Observation,
  silent cutoff mixing, and an unsupported later-currency claim; and
- no branch mutates the original freeze or authorizes an ordinary update.

The fourteenth checkpoint adds ordinary `HKLEG-CURRENT-OBS-001` through
`HKLEG-CURRENT-OBS-003`:

- six fixtures distinguish supported silence, new and deduplicated bounded
  affected work, release-blocking unavailability, item-only unavailability,
  and an open urgent signal;
- only complete, fresh, reconciled silence reuses the existing Corpus Release;
  no zero-record release is created; and
- a change signal opens acquisition work but makes no legal conclusion.

The fifteenth checkpoint adds ordinary `HKLEG-CURRENT-EVID-001` through
`HKLEG-CURRENT-EVID-004`:

- nine fixtures prove verified and assisted success, newer-assisted selection,
  and same-version verified preference;
- unavailable evidence blocks with a Coverage Gap only when current-law
  coverage actually depends on it; and
- unofficial copies, bilingual/version/content mismatches, and unresolved
  structure or identity cannot pass or be overridden.

The sixteenth checkpoint adds ordinary `HKLEG-CURRENT-DIFF-001` and
`HKLEG-CURRENT-DIFF-002`:

- seven fixtures classify exact unchanged, payload, structure/location,
  evidence-bundle-only, object-addition, and missing-baseline cases;
- exact unchanged is reuse-eligible only with separately proved continuing
  support; and
- the gate emits no record and explicitly makes no legal-identity, legal-
  status, repeal, or continuity inference.

The seventeenth checkpoint adds ordinary `HKLEG-CURRENT-CAUSE-001` and
`HKLEG-CURRENT-CAUSE-002`:

- six fixtures prove accepted Gazette and Editorial Record causes, fully exact
  non-serving technical republication, unexplained and conflicting-change
  Quarantine, and bounded Source Contract Review;
- status signals, HKeL appearance, similarity, and AI output cannot replace
  exact assigned cause evidence; and
- the gate emits no record and makes no legal-identity or status inference.

The eighteenth checkpoint adds `HKLEG-CURRENT-EVENT-001`:

- eight fixtures prove exact routing to an eligible reconstruction plan,
  verified or assisted known-stale fallback, explicit no-record gap, ordinary
  current-bundle handling, and fail-closed incomplete/conflicting/unbounded
  inputs;
- successful missing-consolidation cases record a Legal Status Event and exact
  Coverage Gap but emit no Search Record; and
- a synthetic active reconstruction state proves only selection precedence and
  grants no real reconstruction or activation authority.

The nineteenth through twenty-first checkpoints add the complete ordinary
`HKLEG-CURRENT-DISP-001` → `HKLEG-CURRENT-REC-001` →
`HKLEG-CURRENT-REL-001` tail:

- seven disposition fixtures assign each accepted primary state or fail closed
  on upstream, coverage, or single-signal uncertainty;
- eight record fixtures enforce exact six-field reuse, new immutable identity
  on any serving change, no record for non-searchable states, and Quarantine on
  same-ID mutation; and
- seven release-accounting fixtures reconcile every object, location, event,
  selected and retired record, Coverage Gap, and Quarantine before candidate
  release construction.

The loader now represents the accepted `NOT_READY` lifecycle honestly: every
not-ready scope must name blockers, ready scopes cannot retain not-ready
blockers, decision-ready or later scopes require real fixture/evaluation
inventory, and attested or later scopes require attestations. The package now
contains 27 offline conformance rules and 127 fixtures, but zero activation-
executable terminal rules, semantic profiles, evaluation IDs, or attestation
IDs. All three real scopes remain `NOT_READY`.

## Validation performed

All application bytes and effects were synthetic/local:

- stable exact uv CLI reset and all-scenario proof: **32/32 scenarios passed in
  both path-distinct runs**;
- focused M7/reporting suite: **7 passed**;
- exact developer command and complete ordinary suite: **239 passed, 4 skipped
  in 10.63 seconds**;
- repository-wide Ruff: PASS;
- strict Pyright: **0 errors, 0 warnings, 0 information messages**;
- Python boundary checker: PASS across **114 files** with the same eight exact
  reviewed exceptions and no M7 exception;
- architecture proof: PASS with 5 applications, 14 packages, 80 dependency
  edges, 31 capability ports, and unchanged fingerprint
  `sha256:5253bae3e841072f8f823a1298344404bbec569f7fa3fd7b87db8f18d5ca168c`;
- independent Node contract validator: PASS with unchanged package fingerprint
  `sha256:7bd2858bd0099271bc5be1e8d5c380521d81fb15bee8a4110de8fe6629d3094e`;
  and
- complete network-disabled package proof: two byte-identical builds and clean
  installs for all 19 wheels plus byte-identical container inputs.

Those M7 results are historical evidence for the committed M7 tree. Validation
of the current 2026-08-17 Hong Kong readiness checkpoint produced:

- focused Legal Desk loader/lifecycle and 27-rule package suite:
  **49 passed**;
- V1 POC topology, read-only host-admission/collector, artifact-inventory,
  application-image-input, application-runtime-input, and cross-application
  composition, systemd/identity/credential-proof-input, composite-admission,
  and V1 S3 adapter suites: **115 passed**;
  their CLIs
  report 16 disabled services,
  25 credential references, 12 non-admitted
  artifacts, five non-admitted repository images, five non-admitted application
  runtime profiles, 16 disabled service-unit inputs, two disabled bootstrap
  units, five disabled timers, ten uncreated host identities, seven runtime
  blockers, six systemd blockers, four identity blockers, and three explicit
  host blockers; the credential-interface CLI reports **three subjects, six
  steps, seven inspection surfaces, six blockers, executed=0**; the composite
  CLI reports **14 components, eight static contracts validated, 14 blockers,
  admitted=false**;
- V1 SQL file-credential, exact-topology, strict-TLS, readiness,
  driver-sanitizer, and secret-free-failure suite plus exact two-emulator
  scheduler and common bounded-readiness suites: **34 passed**;
- ordinary repository suite excluding its loopback-only durability file:
  **436 passed, 4 skipped**, with two durability
  tests initially denied IPv6 loopback binding by the sandbox; both passed when
  previously rerun with explicit loopback permission, for an effective
  **438 passed,
  4 skipped** across the updated test inventory;
- Ruff check and formatting for all touched Python files: PASS;
- repository-owned Python boundary checker: PASS across **129 files** with the
  same eight exact reviewed exceptions;
- architecture proof: PASS with 5 applications, 14 packages, 80 dependency
  edges, 31 capability ports, and policy fingerprint
  `sha256:7f1f055c93c44be1577588937bf92afbd0ae38315935a1e6879fa4074511b7b9`;
- JSON Schema validation of the frozen real-package manifest: PASS; and
- exact uv 0.12.5 offline wheel build: PASS in two distinct output roots with
  byte-identical SHA-256
  `734df40775d0c0f23028e6551dfa85eb759f2648ebc36d961d7890f2a7643177`;
  all current event/disposition/record/release artifacts are present; and
- deterministic package rebuild: PASS with package version `0.21.0`, package
  fingerprint `sha256:61d58fca4b695a466dbaaa73353c066614ba47df3be7cf5f3c89aa5389a1e978`,
  and `package.json` SHA-256
  `292bc2b72fcd641f3448528f949a1edc6d73243c80fe1515c209b509c2370a88`.

Validation of the official-source and Patchright checkpoint, including the
2026-08-18 build-first extension, produced:

- complete repository pytest inventory after legal clearance, NPC metadata,
  and Patchright integration: **485 passed, 4 skipped**;
- source-connectors package: **50 passed**, including strict register,
  build-accounting, locator-injection, exact bilingual-member, rendered-
  session, transport-drift, content-admission, and RSS signal cases;
- repository-wide Ruff lint: PASS;
- acquisition-worker plus source-connectors strict Pyright: **0 errors, 0
  warnings, 0 information messages**;
- Python boundary checker: PASS across **143 files** with the same eight exact
  reviewed exceptions; and
- architecture proof: PASS with five applications, fourteen packages, 80
  dependency edges, 31 capability ports, and policy fingerprint
  `sha256:e1055d5940e3b0387e482976b578bb44f990fe9b3bc93854e9c7c7987e9dbc50`;
- V1 application-image input gate: PASS while still `NOT_READY` with five
  images and five blockers; and
- V1 composite admission gate: PASS while still `NOT_ADMITTED` with fourteen
  components, eight validated static contracts, and fourteen blockers.

The complete network-disabled two-path package proof was attempted after the
Patchright lock update. It stopped during a clean acquisition-worker install
because the already locked `s3transfer 0.19.2` artifact was not available to
the offline uv cache. No network fallback occurred. This is an explicit
wheelhouse/cache blocker; it is not a Patchright runtime or source-connector
test failure.

The repository-wide `npm run typecheck` was also attempted after installing
the lock-pinned local Node dependencies. It reports 370 errors in preserved
unrelated V1 files and missing Boto stubs; the changed source-connectors package
itself passes strict Pyright. Node.js is still 24.15.0 rather than the required
24.19.0, so the complete exact developer gate remains unavailable on this Mac.

Repository-wide Ruff lint passes. Touched files pass Ruff formatting, while a
full-tree format check reports two preserved pre-existing formatting drifts in
`packages/domain/src/asklegal_domain/operations.py` and
`tools/build_synthetic_rulebook.py`. The Python boundary checker passes across
141 files with the same eight reviewed exceptions.

Repository-wide strict Pyright, the exact Node validator, and the complete
two-path package proof have not passed for this source checkpoint. The full M7 32-scenario proof
was rerun twice from clean path-distinct state and passed with current report
fingerprint
`sha256:24ba2d3ec5471276ec7c62263af3ae7662178014bf007245e4025c936fba8edb`.
Lock-pinned Node dependencies are now installed locally and ignored by Git.
Repository-wide `npm run typecheck` starts but retains the 370 unrelated
baseline errors described above. Node.js remains 24.15.0 rather than the
required 24.19.0. The user separately authorized the package-registry step that
locked Boto3 `1.43.49` and its transitive dependencies; no service or vault
endpoint was contacted.

Historical M7 reproducibility fingerprints include:

- unchanged uv lock:
  `cf0e9eb5f7c6aa14a7ee79dd55d1468a5a56cb95c5f1daf05a06b807e682ce92`;
- application-runtime wheel:
  `09d9dff744446b3ad1ee4b3253304dbd49c852ac0494d0e2637beb50ae4cd73e`;
- control-plane wheel:
  `8d6d0c0c2cec15ed4ca87a91dcbc0c43ba210da71b988fd9fcaebe28f0865b7f`;
- reporting wheel:
  `3e663f318e12c5986288a3b6b45d7cb836b04b972d8c8cabfb6eadcb33c127cb`;
  and
- package container-input archive:
  `a6ca61c29382a4b7fb8c1b2ccb327ad6dd0ad3b080e77b80db2bc5d10aa6119c`.

## M7 files changed

M7 changes are concentrated in:

- `tools/local_conformance.py` and `tools/tests/test_m7_end_to_end.py`;
- `packages/reporting/src/asklegal_reporting/local_conformance.py`, its export,
  and tests;
- `apps/control-plane/src/asklegal_control_plane/local_cli.py` and the
  `asklegal-local` entry point;
- explicit local Review projection injection support;
- root Ruff policy and README reproduction instructions; and
- `AGENTS.md` plus all canonical continuity files.

The ignored `var/local-conformance/` tree contains only disposable generated
synthetic proof state and is not a repository artifact.

## Hong Kong readiness checkpoint files changed

- `packages/legal-desks/src/asklegal_legal_desks/loader.py`;
- `packages/legal-desks/src/asklegal_legal_desks/hk_legislation.py` and package
  exports;
- `packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package/`;
- `packages/legal-desks/tests/test_rulebook_package.py`;
- `tools/build_hk_legislation_rulebook.py`;
- `README.md`; and
- the four canonical continuity files under `.agent/`.

## Official-source checkpoint files changed

- `packages/source-connectors/src/asklegal_source_connectors/official.py`;
- `packages/source-connectors/src/asklegal_source_connectors/official_http.py`;
- `packages/source-connectors/src/asklegal_source_connectors/official_binding.py`;
- `packages/source-connectors/src/asklegal_source_connectors/official_inventory.py`;
- `packages/source-connectors/src/asklegal_source_connectors/official_planning.py`;
- `packages/source-connectors/src/asklegal_source_connectors/official_rendered.py`;
- `packages/source-connectors/src/asklegal_source_connectors/
  hk_legislation_source_register.json`;
- `apps/acquisition-worker/src/asklegal_acquisition_worker/
  patchright_discovery.py` and its focused tests;
- acquisition-worker dependency metadata, the exact uv lock, architecture
  policy/test, and V1 application-image input hashes;
- `docs/adr/0100-isolate-patchright-to-non-controlling-source-discovery.md` and
  the corresponding M4 protocol clarification;
- source-connectors admission, model, and public exports;
- six focused official-source test modules plus the Patchright test module; and
- all four canonical continuity files under `.agent/`.

## Latest V1 credential-proof checkpoint files changed

- `infrastructure/poc/credential_interface_proof_inputs.json`;
- `tools/v1_poc_credential_interface.py` and its focused tests;
- the composite gate and ordinary developer entrypoint;
- `README.md` and both V1 POC design documents; and
- `CONTEXT.md`, `ROADMAP.md`, and this working state. No new product decision
  was made, so `DECISIONS.md` was not changed by this checkpoint.

## Decisions and open questions

No new product or production architecture choice was required for M7. The
implementation follows the accepted 32-scenario plan and existing M3–M6
boundaries. The user subsequently selected `HK-LEG-ORDINANCES` as the first
real-package target and authorized local, network-disabled implementation.

There is no remaining M7 implementation blocker or decision. The Ordinances
package now has an exact blocker inventory and 27 fully covered offline rules,
but remains `NOT_READY`. Legal admission is clear for all 14 official-source
roles. Five roles are configured, five are partially configured, and four are
technically blocked. Adjudicated evaluation truth, semantic deployment
profiles, complete-universe acceptance, and conformance attestations remain
open evidence work, not defaults inferred from local success.

## Current host prerequisite

The active 2026-08-18 workspace is Ubuntu 24.04.4 LTS on x86-64
(`docpro-MS-7D99`), under `/home/docpro/Desktop/Ask.Legal Database/
AskLegal-LegalDBPipeline`. This is the machine intended as the V1 runtime host.
The repository requires exact Python 3.14.7, uv 0.12.5, and Node.js 24.19.0 for
its complete developer command. That toolchain was installed on this machine on
2026-08-18, without `sudo` and without modifying any shell startup file:

- uv and uvx 0.12.5 at `~/.local/bin/`, from the GitHub release tarball
  verified against its published SHA-256;
- managed CPython 3.14.7 via `uv python install`;
- Node.js 24.19.0 and npm 11.17.0 at
  `~/.local/opt/node-v24.19.0-linux-x64/`, from the nodejs.org tarball verified
  against the official `SHASUMS256.txt`; and
- the locked workspace (`uv sync --frozen --all-packages`, 87 packages) and
  locked npm devDependency Pyright 1.1.413 (`npm ci`).

Docker is deliberately not installed. It needs root, and adding the login user
to the `docker` group would violate the accepted
`docker_group_non_root_members_forbidden` host rule. The ordinary suite skips
every Docker-marked test, so it is not required for the developer command.

The complete developer command now runs on this machine for the first time; it
could not run on the Mac, whose Node.js was 24.15.0. System Python remains
3.12.3, which is what `tools.dev_test` is invoked with. The eight pure-Python
static gates still pass and the composite gate still returns
`V1_POC_NOT_ADMITTED`.

Validation on this machine after the install: the complete developer gate
`python3 -m tools.dev_test` passed with **485 passed, 4 skipped**; the Python
boundary checker passed across 143 files with the same eight reviewed
exceptions; the architecture proof reproduced policy fingerprint
`sha256:e1055d5940e3b0387e482976b578bb44f990fe9b3bc93854e9c7c7987e9dbc50`;
repository-wide Ruff passed; and `asklegal-local prove --scenario E2E-001`
returned `GOLDEN_FLOW_RECOVERED` with fingerprint
`sha256:a8cfe0c154ba9ded80fe6f37df79db289cafda4edc962b749375bef5e10d4558`,
byte-identical to the earlier macOS arm64 run. That is the first cross-machine,
cross-architecture reproduction of the local proof.

`npm run typecheck` still reports **370 errors, 0 warnings** from Pyright. The
count is identical to the figure recorded on the Mac, so it is a pre-existing
baseline rather than an install or toolchain artifact; the earlier note
attributing it partly to Node.js 24.15.0 was wrong. The errors concentrate in
`packages/legal-desks/.../hk_legislation.py` (51),
`packages/evidence-vault/.../s3.py` (26) and its tests (23), and the
`tools/v1_poc_*.py` family, and are mostly `reportUnknownVariableType`,
`reportUnknownArgumentType`, and `reportUnknownMemberType`. Because Pyright
fails first, `npm run typecheck` never reaches the boundary checker, which
passes when run directly. Clearing this baseline is open work.

The read-only host-facts collector was run here and aborted with
`read-only probe failed: findmnt`, consistent with an unprovisioned host: the
required `/srv/asklegal/...` paths do not exist. Two accepted policy thresholds
also do not match this machine as written; see the 2026-08-18 host-fact
correction in `DECISIONS.md`.

The earlier macOS workspace remains accurate history: Darwin 25.3.0 on arm64
under `/Users/admin/Desktop/AskLegal-LegalDBPipeline`, with uv and uvx 0.12.5
at `/Users/admin/.local/bin/`, managed Python 3.14.7, system Python 3.12.3,
Node.js 24.15.0, and no Docker. Exact Node.js 24.19.0 was, and remains, a
prerequisite for the locked complete developer command.

## Latest checkpoint verification

On 2026-08-17 the user successfully ran the local reset and `E2E-001` proof on
macOS after correcting the clean-workspace command to include
`--all-packages`; it returned `GOLDEN_FLOW_RECOVERED` with fingerprint
`sha256:a8cfe0c154ba9ded80fe6f37df79db289cafda4edc962b749375bef5e10d4558`.
The user then authorized the local Hong Kong Legislation readiness checkpoint
described above. Validation results are recorded in the current validation
section.

Credential-free official Hong Kong source pages, catalogue metadata, HEAD
responses, four XML inventories, two RSS feeds, publisher JavaScript bundles,
and the NPC enumeration metadata API were accessed read-only.
Captured response bodies were bounded and held in memory only; no legal corpus
or source evidence was saved or published. No model, embedding, Azure,
Pinecone, backup, routing, deployment, production system, account, or remote
mutable resource was accessed or changed. The source-connectors wheel build
was explicitly offline.

## Continuity file location change

On 2026-08-18 the four canonical continuity files moved from `docs/agent/` to
`.agent/` using `git mv`, preserving history as `R100` renames. Path references
were updated in `AGENTS.md`, `README.md`,
`packages/management-register-adapter/README.md`, and
`docs/design/V1_POC_UBUNTU_TOPOLOGY.md`. `.agent/` matches no `.gitignore` rule
and all four files remain tracked. The change is staged and not committed. See
the dated entry in `DECISIONS.md`.

## Authorization boundary and exact next step

M7 completion grants no M8 or external authority. M8 remains a later platform
milestone only if the user separately authorizes it. The stable first-baseline
rules run through `HKLEG-BASE-CHANGE-001`; the ordinary update path now runs
through complete `HKLEG-CURRENT-REL-001` accounting, with the separate
`HKLEG-CURRENT-EVENT-001` missing-consolidation router. Further real-package
admission needs adjudicated evaluations and complete-universe acceptance;
source rights are no longer the blocker. Bounded credential-free read access
is proved for the direct endpoints currently enabled, including the NPC
metadata API.

The next repository-only source steps are the exact HKeL `/grid` request,
pagination, completeness, and artifact-locator contracts; exact NPC direct
search/detail request bodies; catalogue and physical-holding procedures;
source-specific complete-capture composition; and integration with the
acquisition worker's manifest-last Primary/Recovery evidence flow. Patchright
may discover these contracts but cannot supply the controlling evidence. None
may bypass source or endpoint technical admission state.
The user has declined external publisher/archive enquiries for now. They are
not a V1 prerequisite and no message or request has been sent. Work continues
through independently verifiable official interfaces; sources without a
complete safe procedure remain visible as partial or blocked and cannot
contribute false completeness or no-change claims.

The static V1 POC topology, host-policy, artifact, application-image,
application-runtime-input, systemd-unit-input, host-identity-input, and exact
credential-interface-proof-input contracts are complete and disabled. The
composite gate records the complete
current result as `V1_POC_NOT_ADMITTED`; it does not turn those static passes
into readiness. Process-side
systemd credential-file loading, SQL/DTS/S3 factory composition, the complete
readiness gate, and concrete SQL/vault checks are locally proved, but
host/container delivery and the other concrete probes are not. The next
infrastructure proof cannot run honestly in the current environment. Its six
inputs are exact: access to the intended Ubuntu 24.04 x86-64 host, which is now
satisfied because the repository is checked out and running static gates on that
machine, leaving five outstanding; read-only image resolution authority; permission to pull and run only the
named SQL Server and Versity proof images; selection of an exact Versity
version/digest from that read-only resolution; permission to create synthetic
one-use credentials; and permission to create, inspect, then remove only the
named throwaway proof state after evidence capture. That host proof
is limited to credential-file behavior, SQL certificate trust and hostname
rejection, canary leak
inspection, rotation, restart, and named throwaway state. It authorizes no real
credential, source, Pinecone, model, deployment, or production effect. If the
Versity proof confirms its documented interface is incompatible, the user must
choose a native file-credential product, a maintained custom build, or an
explicit bounded relaxation; the recommendation is to preserve the rule and
prefer a native file interface.

The user explicitly confirmed that the private
`https://github.com/stevw-repo/AskLegal-LegalDBPipeline.git` remote is the
approved destination and authorized synchronizing the complete committed
M2–M7/V1 checkpoint from `main` to `origin/main`. Commits `6be9dd0` and
`5140578` were pushed successfully. The official-source and Patchright
implementation was subsequently committed as `8f2501d` and pushed by the user
manually outside an agent session; `main` and `origin/main` both resolve to
`8f2501d`. Other than read-only official-source access, no deployment,
external message, cloud mutation, or other remote-system action was performed.
