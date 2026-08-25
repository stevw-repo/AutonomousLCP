# Where the project stands — 2026-08-25

Read this first, then `.agent/ROADMAP.md` and `.agent/WORKING_STATE.md`.

## Repository checkpoint

- Root: `/home/docpro/Desktop/Ask.Legal Database/AskLegal-LegalDBPipeline`
- Host: `docpro-MS-7D99`, Ubuntu 24.04.4 LTS, x86-64
- Branch: `main`; substantive V1 code checkpoint `da90a87` and its later
  continuity checkpoint `d165161` were pushed to `origin/main` on 2026-08-22.
  `d165161` is the base of the complete validated V1 checkpoint described here;
  inspect Git directly for its committed checkpoint hash and remote alignment.
- GitHub accepted the push through the configured old remote but reported that
  the repository moved to `https://github.com/stevw-repo/AutonomousLCP.git`.
  The configured remote has not been changed; reconcile it before relying on
  the old URL for a later checkpoint.
- The disposable branches `v1-poc-runtime-proven` and
  `demo/expo-source-transformation` are informational only. Do not import or
  cherry-pick their code.
- Docker commands in this login session require `sg docker -c '...'`.
- Exact local tools: `/home/docpro/.local/bin/uv` 0.12.5,
  `/home/docpro/.local/bin/node` 24.19.0, workspace Python 3.14.7.

## Verified engineering state

The complete shipping command passed on 2026-08-25:

```sh
python3 -m tools.dev_test \
  --uv /home/docpro/.local/bin/uv \
  --node /home/docpro/.local/bin/node
```

Verified result:

- strict Pyright: 0 errors, warnings, or information messages;
- Ruff lint: clean;
- Ruff format: all 454 Python files formatted;
- Python boundary: 255 files, the same 12 exact reviewed exceptions;
- architecture: 5 applications, 14 packages, 80 dependency edges, 31
  capability ports;
- contracts: reproducible package fingerprint
  `sha256:92b5193ca9fa45d2260ee2012cd350818136f4d12b1d93e763a67b827d15c455`;
- ordinary suite: 1524 passed, 4 skipped in 181.91 seconds.

The four skipped tests are the intended opt-in gates. All four were run
separately and passed:

- package spike: 5 passed, including path-distinct builds and clean locked
  network-disabled installs for all 19 workspace packages;
- SQL Server: 1 passed against a new digest-pinned disposable SQL Server. The
  proof applies migrations `000001` through `000007`, commits real Review-ready
  and decided proposals, proves Review/Promotion projection reads, consumption,
  revocation, invalidation, no-effect execution authorization, replay/lost-ack
  recovery, permission isolation, tamper and changed-lineage rejection, one
  concurrent terminal winner, and denial of direct fact-table access;
- Durable Task: 1 passed against a new digest-pinned disposable emulator;
- image admission: full opt-in proof passed. Two canonical executions reproduced
  image digest
  `sha256:52bd434d68d024291a83e44c5c0c8c360880001f98dfd36954bad501241c462c`
  and all unsigned evidence fingerprints. Ephemeral signed graph hashes differed
  as designed; recovery equalled the signed graph within each execution.

Every disposable SQL, Durable Task, and BuildKit proof container/builder was
removed. Their downloaded digest-pinned images and ignored `/tmp` input caches
may remain.

M7 was explicitly reset and rerun under authorization: all 32 scenarios passed,
with report marker `local synthetic platform proved`. The report content digest
printed by the CLI was
`sha256:9d4f00dfb43ac73634cec69f0311d23b819637830161ce0b51ee7699b712de38`;
the report file SHA-256 is
`9bc2dec2b642444b4fd84728ac8458d918085d9cd6e772e71f50eb0eb80b4dbf`.
A normal second run returned exactly `SYNTHETIC_STATE_RESET_REQUIRED`.

## CI state

`azure-pipelines.yml` now runs the same complete shipping gate on a fresh
unprivileged Ubuntu 24.04 Microsoft-hosted agent. `tools/ci/bootstrap.sh`
downloads and verifies exact uv 0.12.5 and Node 24.19.0 archives, installs
Python 3.14.7 with `--no-bin`, and writes no profile/home executable. A clean
bootstrap run completed on 2026-08-22. The pipeline contains no service
connection, private pool, deployment environment, provider credential, or
production authority.

The CI files are now pushed in checkpoint `da90a87`. The hosted execution has
not yet been observed, so HKV1-1 remains `IN PROGRESS` for that single remote
observation.

## Image-proof corrections

The authorized rerun found and fixed two genuine reproducibility defects:

1. the old gate checked that some BuildKit v0.26.2 node existed but hardcoded
   actual builds to mutable builder `default` (currently v0.32.2);
2. the tracked synthetic image fixture lacked the dpkg status record required
   for Syft to inventory the declared BusyBox package.

The policy now binds named builder `asklegal-image-admission-v0262`, BuildKit
image digest
`sha256:de10faf919fc71ba4eb1dd7bd6449566d012b0c9436b1c61bfee21d621b009aa`,
Docker 29.7.2, and Grype database build `2026-08-21T06:17:24Z` with exact
archive/database hashes. `tools/image_admission_bootstrap.py` is the verified
reproduction path. `tools/image_admission_direct_runner.sh` is a non-elevating,
Docker/Buildx-only adapter for a shell that already has Docker permission.

## Current V1 position

HKV1-0 and HKV1-2 remain acquisition/scope work. Direct GLD e-Gazette is the
earliest originating official Gazette source and remains in V1, but its lawful
Turnstile-gated acquisition procedure is not admitted. HKeL Gazette remains
complementary backcapture, recovery, reconciliation, and gap evidence. The
repository has 79 endpoint contracts, 56 enabled; five source roles are
configured, five partially configured, one technically blocked, and three out
of V1 scope.

HKV1-3 through HKV1-6 remain the largest product gaps:

- all three Hong Kong Legislation scopes remain `NOT_READY`. Frozen package
  `0.41.0` contains the unchanged 39 rules and 277 deterministic fixtures plus closed
  source-neutral canonical language-tree and bilingual-alignment schemas and
  a supported textual bilingual renderer declaration and all 22 source-neutral
  recursive official-boundary partition conditions. Its fingerprint is
  `sha256:f5bad65a948de6c4a5e27f4e474dcd7607fb36e70d5afaf104dfa4354fe1f9e7`. The
  commencement rule covers exact default, fixed, appointed, conditional, and
  progressive partial commencement and produces exact operative/pending
  locations without inferring effect from publication or HKeL `InEffect` alone.
  A second rule covers exact whole/partial and future/operative repeal,
  revocation, expiry, and continuity-proved revival, binding pre/post state and
  append-only event history without creating versions, successors, or records.
  The readiness contract is generated from the complete actual rule/fixture
  inventory rather than the former stale baseline-only list. A third rule
  classifies operative/future amendments, express corrections, and Editorial
  Record events, routes matching bundles to ordinary evidence validation and
  missing consolidation to a Coverage Gap, and never constructs text, an
  Official Version, or a Search Record;
  a fourth rule classifies ordinary/Extraordinary Gazette publication and
  enactment facts across Legal Supplement Nos. 1–3, Main Gazette notices, and
  other supplements without inferring commencement, current law, identity,
  continuity, an Official Version, or a Search Record;
  a fifth bounded pre-Plan semantic rule covers all 13 terminal
  decision/challenge outcomes. Even its successful exact confirmed result is
  only an untrusted structured candidate for the full deterministic ADR 0084
  Plan validator; it creates no Plan identity, executes no operation, authors
  no text, emits no record, and performs no provider or external effect;
  a sixth deterministic rule validates the complete ADR 0084 Plan contract,
  authority, latest base, event chain, dependency/evidence closure, authentic
  bilingual streams, closed operations, event bindings, atomic groups, and
  revalidation across 21 cases. It binds only the existing candidate identity
  and fingerprint. Current source now transactionally executes every ADR 0082
  operation on verified canonical trees, proves complete final source-unit
  inventory and bilingual alignment, binds OP008 to the exact supported
  renderer, and rolls back every provisional output on failure. The complete
  request/result schema, 17-code catalogue, execution rule, and 13 exact frozen
  fixture/result pairs now reproduce this boundary from package bytes. The
  provisional result feeds the exact immutable ADR 0085 artifact and ADR 0084
  Report. PASS requires
  a complete re-read artifact; BLOCK emits no artifact or record. Authentic
  HKeL XML/XSD interpretation and official-copy reconciliation remain absent;
- HKV1-4 is now `IN PROGRESS`: a strict source-neutral ADR 0046/0048 kernel
  derives court-family/year scope ownership, accounts all six official listing
  outcomes, separates inventory/evidence/processing/search counts, preserves
  valid zero-proposition decisions, and rejects HKLII completeness. Its closed
  seven-role source universe and six-family registry separate current,
  historical, original, fallback, translation, and discovery authority without
  inventing year boundaries. Concrete court-year scopes are generated only from
  one complete sorted six-family evidence-bound range set; current ranges must
  reach the cutoff and historical ranges cannot pass 1997. Seventeen synthetic
  cases pass. Frozen `_hk_cases_package` `0.11.0` now preserves one
  listing-accounting fixture, the seven-role source universe, six scope-family
  templates, seven blockers, and all 54 frozen deterministic cases: 20 permanent
  ADR 0064 deterministic structure/Coverage Ledger cases plus all 16 candidate,
  evidence, renderer, and output cases plus all 18 correction, package,
  security, and workflow-identity cases. The strict ledger
  accounts exact opinions, units, primary segments, dependencies, resolutions,
  uses, candidates, zero-proposition, Quarantine, blocked, and invalid outcomes
  without emitting a Search Record or authorizing semantic work. The output
  validator adds exact candidate arithmetic, evidence roles, UTF-8 range and
  quotation checks, traceability, canonical labelled rendering, six-field
  payload validation, explicit zero/one/many inventories, and hard-limit
  Quarantine while still creating no record. The final checkpoint validates
  unchanged reuse, official and split/merge/new/partial correction history,
  exact 132-case/132-cell/31-pair catalogue completeness, packet non-leakage,
  sealed external artifacts, two-run reproduction, forbidden-capability denial,
  and exact assembled-workflow identity. Even its positive result is only
  eligible for later admission; it creates no admission or provider authority.
  A strict ADR 0065/0066 preflight now binds both task families and all eight
  request kinds to exact workflow, judgment, complete opinion/unit, ordered
  assignment, original-language range, dependency, prior-stage, allowed-ID,
  evidence-role, and no-tool/no-hidden-reference facts. Eight supplementary
  package fixtures execute, but `VALID_REQUEST` authorizes zero provider calls
  and counts as zero of the 78 frozen semantic correctness cases.
  A separately permissioned materiality evaluator now executes all 18 frozen
  `SEM-MAT` cases from model-facing synthetic judgment packets, evaluator-only
  Reference Proposition Maps, and adjudicated observations. It checks material
  proposition recall, true zeroes, unsupported output, operative/obiter roles,
  meaning, exact evidence roles/ranges, handoffs, and downstream selection
  without receiving the case ID. Six high-risk pairs are complete; P019 remains
  pending its `SEM-RSK-016` near-miss. This is synthetic evaluator conformance,
  not a provider run or workflow admission.
  A separate content evaluator executes all 18 frozen `SEM-CNT` cases through
  the same model/reference/observation separation. It checks qualifications,
  exceptions, definitions, burdens, minimum context, application, result,
  exact quotations, ordered non-contiguous evidence, structure, dependencies,
  ambiguity, missing locators, materially broadened wording, and faithful
  equivalents without preferred-prose equality or case-ID switching. Pairs
  P006-P008 reject swapped observations.
  A separate boundary evaluator executes all 22 frozen `SEM-BND` cases through
  the same separated trust boundary. It checks cumulative tests versus
  independent grounds, repetition versus distinct branches, exact issue and
  opinion paths, joint/agreement-only/concurrence/dissent/obiter/plurality
  roles, express adoption, evidence, unit use, selection, and quarantine.
  Pairs P009-P015 reject swapped observations; unsupported plurality reasoning
  is separately attributed and quarantined instead of being manufactured into
  a majority.
  A final risk evaluator executes all 20 frozen `SEM-RSK` cases with exact
  original-language/court authority, auxiliary translation, mixed-language,
  historical format, complete segment/dependency, parser support, serving-limit,
  uncertainty, hostile-source, and correction assertions. Pairs P016-P018
  reject swapped observations and `SEM-RSK-016` completes P019 against the
  proven zero in `SEM-MAT-017`. Together the four checkpoints execute all 78
  frozen synthetic semantic cases.
  The first later-treatment semantic checkpoint now executes all 13 frozen
  `HKCASE-TREAT-SEM-DIS-NNN` whole-judgment discovery cases and P001. Its strict
  separated packets/evaluator cover complete lead, opinion, segment, context,
  correction, zero-proposition, unresolved-identity, and Chinese/mixed-language
  discovery. Missing required context remains incomplete and silence never
  becomes a no-treatment conclusion. The result has no provider, treatment-
  relationship, legal-effect, Search Record, release, or external authority.
  Package fingerprint is
  `sha256:545b9bb4ebb9dbfba16dc7bd3d54e1b83e698991331d4ffe30fe2c3ab82f77d9`;
  13/155 treatment cases and 13/53 treatment semantic cases now execute.
  It has zero
  concrete scopes, profiles, evaluations, attestations, or activation authority.
  Fail-closed source-access
  register `2026-08-24.1` freezes the same roles and authorities with zero
  endpoints, unresolved rights, and express prohibition of real source access;
  package `0.11.0` locks its fingerprint. No executable real-source package,
  connector/evidence, semantic proposition/treatment workflow, evaluation, or
  baseline exists;
- HKV1-5 is now `IN PROGRESS`: source-neutral component accounting separates
  five-source observations, entry membership, board ownership/structure,
  branch-derived state, material disposition, processing, per-board candidate
  readiness, and final serving readiness. Exact ADR 0071 contract `1.0.0` now
  rejects clock-only promotion, stale-trigger inference, disappearance-as-
  retirement, and current wording without controlling-English-product
  reconciliation. Its 22 frozen cases cover every required branch family,
  transition/retirement boundary, optional-Chinese defect signal, and ADR 0005
  outage choice while denying record/serving authority. Component-continuity
  contract `1.0.0` separately preserves identity only for proved unchanged/
  move/rename/renumber/correction/reappearance events; requires new register IDs
  for replacement/split/merge/board transfer; and quarantines disappearance or
  similarity-only evidence. ADR 0073 contract `1.0.0` now also proves one exact
  English branch tree, independent normal roots, source-ordered dependency
  closure, canonical six-field rendering, table/fee/Form completeness,
  official-child minimum-part earliest-full partitioning, actual-label
  measurement, and complete primary/context/presentation/state accounting.
  Record identity/traceability contract `1.0.0` now also preserves or reselects
  exact payloads, declares register-issued initial/forward-successor identity
  requirements, forbids backward lineage on reselection, and emits a complete
  traceability seed without allocating an ID or mutating selection. ADR 0074/
  0075 universe validation now binds all 284 permanent case IDs, 284 matching
  cells, eight checkpoint counts, all 57 positive/near-miss pairs, and the
  accepted design bytes while explicitly keeping full-suite conformance false.
  The complete 38-case package-integrity checkpoint and pairs P050–P056 run
  through one strict common-envelope decoder and a fact-derived evaluator that
  never selects a result from case ID. Exact virtual bytes, inventories, paths,
  hashes, input/output states, complete matrix/pairs, reproducibility, hostile
  controls, capability denial, authority, and attestation are frozen; negative
  cases pass only on exact rejection. The complete 62-case source-decision
  checkpoint and pairs P001–P015 now separately require exact five-role source
  accounting, closed Fact Authority, membership, board ownership/instances,
  bounded source consequences, and required-English/optional-Chinese decisions.
  Its runner derives complete structured results from proposal-safe facts and
  case ID never selects the answer. The complete 51-case Applicability-branch
  effective-state/transition checkpoint and P016–P024 are also executable. It
  reuses ADR 0071 atomic truth and explicitly derives component summaries,
  branch sets, record responsibility, effective-fact order, ADR 0005 outage
  consequences, gate denial, and UNKNOWN-repair rejection. Frozen package
  `0.14.0` also makes the complete 30-case Record Boundary, dependency,
  definition, source-structure, cross-reference, and hard-limit checkpoint plus
  P025–P031 executable. It preserves exact referring words and both board
  identities without target text and explicitly names background exclusions
  and quarantined units. The complete 35-case Canonical English rendering,
  table, fee, Regulatory Form, English-only serving, measurement, identity-
  consequence, and authority-note checkpoint plus P032–P037/P057 is also
  executable. It preserves exact canonical bytes and complete source-element
  closure, rejects Chinese serving paths, keeps authority notes outside text
  and embedding input, binds both measurements, and derives exact identity and
  quarantine consequences from facts. The complete 24-case exact-limit
  measurement and official-structure partition checkpoint plus P038–P040 is
  also executable. It reuses the accepted ADR 0073 partitioner, remeasures
  actual labels and metadata, preserves exact official unit groups and
  governing context, isolates branches, rejects arbitrary cuts, and assigns
  exact quarantine/Coverage Gap consequences. The package preserves the
  Main Board/GEM scopes, five roles, five fixtures,
  all four exact source-neutral rule/request/result contract sets, the canonical
  renderer declaration, 38 package-integrity and 62 source-decision fixture/
  report pairs, 51 state-decision fixture/report pairs, 30 boundary-decision
  fixture/report pairs, 35 rendering-decision fixture/report pairs, 24
  partition-decision fixture/report pairs, 20 source-unit coverage/readiness
  fixture/report pairs, 24 identity/lineage/traceability fixture/report pairs,
  and eleven blockers. The coverage checkpoint reuses the
  accepted ADR 0073 proof and completes P041–P045 with exact ownership,
  dependencies, source order, board isolation, fidelity, blocked-scope, and
  valid zero-output accounting. The identity checkpoint reuses the accepted
  immutable record-identity and component-continuity decisions, distinguishes
  reuse/reselection from every six-field successor, validates complete lookup
  ownership and one-to-one/split/merge lineage, and rejects cycles, collisions,
  drift, or similarity-only continuity. All 284 permanent cases and all 57
  pairs are executable across the eight source-neutral checkpoints. Generic
  terminal rules,
  admitted profiles, evaluations, attestations, real register allocation/
  selection, release accounting, and activation remain empty. No endpoint,
  authentic HKEX artifact/tree, real component inventory, Search Record, or
  baseline exists;
- Principles still needs publisher/title/licence selection. If omitted, the
  release cannot honestly be called the complete Hong Kong jurisdiction defined
  by the accepted design.

HKV1-8's first `BEGIN`/Effect Intent slice is now implemented against Promotion
action contract `1.0.0`: the approved bytes bind every exact per-action effect/
capability, input, destination, idempotency, retry/stop, pre/postcondition, and
compensation value. The service resolves the exact manifest profile against
current capability evidence, and migration `000008` atomically appends the
version-2 RUNNING event plus first intent. HKV1-7 admission and real capability-
evidence composition remain absent; no handler is registered.
Proposal packages are
manifest-last and restart-safe; Control registers a fully reread receipt through
the atomic command protocol. Review now re-reads and displays all 11 exact
members, validates the executable Promotion Manifest, and records a schema-valid
named-human approve/reject event with no effect intent. Migration `000004`
projects the optional decision to Review/Promotion. Promotion now reconstructs
the approved candidate after restart by rereading all twelve objects and
validating the exact Approval/manifest/base/predicate/authority bindings.
Migration `000005` adds a Promotion-only atomic single-use consumption command,
exact replay, competing-lineage denial, and explicit denial of the generic
writer; it emits no Effect Intent. Migration `000006` adds named-human Review
revocation and objective Promotion invalidation under the same terminal lock and
winner as consumption. Replay, later-consumption denial, app-specific
permissions, and a concurrent revoke/invalidate race pass on the real engine.
Migration `000007` adds a Promotion-only no-effect execution authorization after
it independently matches the exact consumed proposal, decision, manifest,
`exe_` lineage/fingerprint, worker identity, and validation evidence. Replay and
lost acknowledgement recover exactly. Migration `000008` consumes that exact
authorization, action sequence 1, and current capability-evidence reference in
one atomic `EXECUTION_RUNNING` event/Effect-Intent transaction. Replay, lost
acknowledgement, tamper, stale capability, changed action, and competing BEGIN
fail closed. Migrations `000003` through `000008` pass the fresh least-privilege
proof. Migration `000009`, the fenced claim/readback/attempt/receipt adapter,
and the disabled Promotion first-intent handler are now a validated checkpoint.
The first SQL run exposed grants accidentally placed inside the same batch as
`CREATE PROCEDURE`; SQL Server treated them as procedure-body text and left the
procedure uncallable. Creation and permissions are now separate exact batches.
The fresh proof passes owner-scoped readback, current fencing, renewal, stale-
fence rejection, prior-attempt accounting, attempt append, terminal receipt,
receipt replay, and wrong-owner denial. The complete gate passes Pyright 0,
Ruff clean/391 formatted, Python boundary 203 files/12 reviewed exceptions, and
1069 passed/4 intentional skips in 158.38 seconds. No handler is composed and
no provider effect is enabled. A
pinned shared semantic contract now validates all eleven member roles and their
cross-member authority bindings after exact-version reads; Review invokes the
same contract independently. Correctly hashed placeholders, failed gates, and
release/coverage/traceability/recovery/report drift remain invisible. A
pinned-key Entra v2 verifier also
passes local signature/claim/role/token-kind tests but remains unwired pending
exact admitted tenant/client/key/current-authority inputs. Still missing are
real current-state/authority/capability composition, fenced Effect Intent
handling, backup/cutover, and rollback through the real local service
boundaries.

The shared ADR 0078 lookup and its proposal trust-chain integration are now
exact and reproducible. The fixed `RECORD_TRACEABILITY` member is the canonical
lookup root; the portable receipt binds every exact-version shard. Control,
Review, and Promotion each reread all declared shard bytes, including zero-byte
proved-empty scopes, and revalidate their complete Desired-State payload/scope/
release inventory before Review or Approval consumption. Known-stale fallback
selection and later-HKeL reconciliation remain frozen in 12 cases each; none of
these boundaries may activate a real scope or provider.

The pre-partition worktree complete shipping gate passes: strict Pyright 0, Ruff
clean/383 formatted, Python boundary 195 files with the unchanged 12 reviewed
exceptions, architecture 5 apps/14 packages/80 edges/31 ports, reproducible
contracts, and 1007 passed/4 intentional skips in 141.77 seconds. The current
package is `0.41.0`, fingerprint
`sha256:f5bad65a948de6c4a5e27f4e474dcd7607fb36e70d5afaf104dfa4354fe1f9e7`;
the full legal-desk package is 127 passed. The complete repository shipping gate
passes strict Pyright 0, Ruff clean/409 formatted, Python boundary 213 files
with the unchanged 12 reviewed exceptions, all architecture/contract/package/
reproducibility gates, and 1165 passed/4 intentional skips in 157.25 seconds.

The HKEX ADR 0073 checkpoint complete shipping gate passes strict Pyright 0,
Ruff clean/411 formatted, Python boundary 215 files with the unchanged 12
reviewed exceptions, all architecture/contract/package/reproducibility gates,
and 1188 passed/4 intentional skips in 159.59 seconds. Its focused direct suite
passes 22 tests and the combined Regulatory/package sweep passes 164 tests.

The HKEX identity/traceability checkpoint complete shipping gate passes strict
Pyright 0, Ruff clean/413 formatted, Python boundary 217 files with the
unchanged 12 reviewed exceptions, all architecture/contract/package/
reproducibility gates, and 1210 passed/4 intentional skips in 156.26 seconds.
Its direct suite passes 21 tests, the identity/package sweep passes 94 tests,
and the combined Regulatory/package sweep passes 186 tests. Package `0.5.0`
fingerprint is
`sha256:bd56f5cdd0479e325cef6f8f72583c689628164a71d998004c2350915b7d0dd0`.

The HKEX ADR 0075 effective-state checkpoint complete shipping gate passes
strict Pyright 0, Ruff clean/421 formatted, Python boundary 225 files with the
unchanged 12 reviewed exceptions, all architecture/contract/package/
reproducibility gates, and 1263 passed/4 intentional skips in 161.46 seconds.
Its direct suite passes 17 tests, the combined Regulatory/package sweep passes
239 tests, and two rebuilt 356-file package trees are byte-identical. Package
`0.9.0` fingerprint is
`sha256:50fb7bf5531f87cff30062c5dafeb016e6a1f3307469b7b2031e14aa57b54f36`.

The subsequent HKEX ADR 0075 Record Boundary checkpoint complete shipping gate
passes strict Pyright 0, Ruff clean/423 formatted, Python boundary 227 files
with the unchanged 12 reviewed exceptions, all architecture/contract/package/
reproducibility gates, and 1278 passed/4 intentional skips in 161.24 seconds.
Its direct suite passes 15 tests, the combined Regulatory/package sweep passes
254 tests, and two rebuilt 421-file package trees are byte-identical. Package
`0.10.0` fingerprint is
`sha256:d68b583f60f01b179e096b76f99a23be483e0c0575256d6ddaf13e284bc2a80e`.

The subsequent HKEX ADR 0075 Canonical English rendering checkpoint complete
shipping gate passes strict Pyright 0, Ruff clean/425 formatted, Python boundary
229 files with the unchanged 12 reviewed exceptions, all architecture/contract/
package/reproducibility gates, and 1298 passed/4 intentional skips in 162.53
seconds. Its direct suite passes 20 tests, the combined Regulatory/package sweep
passes 274 tests, and two rebuilt 496-file package trees are byte-identical.
Package `0.11.0` fingerprint is
`sha256:9e6d03f18b999db768807d951a6f30fc0c3e841edbd4159d98604bfc3858c186`.

The subsequent HKEX ADR 0075 exact-limit measurement and official-structure
partition checkpoint complete shipping gate passes strict Pyright 0, Ruff
clean/427 formatted, Python boundary 231 files with the unchanged 12 reviewed
exceptions, all architecture/contract/package/reproducibility gates, and 1326
passed/4 intentional skips in 165.78 seconds. Its direct suite passes 28 tests,
the combined Regulatory/package sweep passes 302 tests, and two rebuilt
549-file package trees are byte-identical. Package `0.12.0` fingerprint is
`sha256:23d46c57eb30c7f1e59ca0a34e406e69e64f10542bdac814c2e8c0767609497e`.

The subsequent HKEX ADR 0075 English source-unit coverage and per-board
readiness checkpoint complete shipping gate passes strict Pyright 0, Ruff
clean/429 formatted, Python boundary 233 files with the unchanged 12 reviewed
exceptions, all architecture/contract/package/reproducibility gates, and 1352
passed/4 intentional skips in 163.51 seconds. Its direct suite passes 26 tests,
the combined Regulatory/package sweep passes 328 tests, and two rebuilt
594-file package trees are byte-identical. Package `0.13.0` fingerprint is
`sha256:4cb5d7f6d32de6b8f811cbb72e3eaf05abaaf0d0d316b6143b995a3fe46f6f2e`.

The final HKEX ADR 0075 Search Record identity, lineage, and traceability
checkpoint complete shipping gate passes strict Pyright 0, Ruff clean/431
formatted, Python boundary 235 files with the unchanged 12 reviewed exceptions,
all architecture/contract/package/reproducibility gates, and 1367 passed/4
intentional skips in 163.33 seconds. Its direct suite passes 15 tests, the
combined Regulatory/package sweep passes 343 tests, and two rebuilt 647-file
package trees are byte-identical. Package `0.14.0` fingerprint is
`sha256:9fffbb23d5db0902c0b6f2deb5d1f8152bd459fbf7bae9c641bcf081499e92fb`.
All 284 permanent cases and all 57 pairs are executable, but conformance
readiness, authentic-source evaluation, both real scopes, and activation remain
false.

The separate external ADR 0074 build-conformance checkpoint now passes.
Attestation `rba_3934c1b573cb9a346ce131715d23db85981986644d96e389` binds exact package
`0.14.0`, all 284 result artifacts, 39 processing-source members, the dependency
lock, isolated runner, contract set, two identical clean runs, and the successful
architecture report. The direct suite passes 10 tests, the combined HKEX sweep
passes 353 tests, and the current complete gate passes 1524 tests/4 intentional skips.
It grants `BUILD_COMPATIBILITY` only and remains outside the immutable package;
authentic evidence, real scope admission, and activation remain false.

The current Hong Kong Cases whole-judgment treatment-discovery checkpoint
passes strict Pyright 0, Ruff clean/454 formatted, Python boundary 255 files with
the unchanged 12 reviewed exceptions, all architecture/contract/package/
reproducibility gates, and 1524 passed/4 intentional skips in 181.91 seconds.
Its direct discovery/package suite passes 85 tests. Two consecutive rebuilt
559-file package trees have identical digest
`86ff3164e5e60679205d515f4b5d0a6857bfbfa44b7bb204a0cd17898063b559`.
Package `0.11.0` fingerprint is
`sha256:545b9bb4ebb9dbfba16dc7bd3d54e1b83e698991331d4ffe30fe2c3ab82f77d9`.
All 54 proposition deterministic cases, eight request-kind preflight fixtures,
78 proposition semantic cases, and 13/155 treatment cases are executable;
real-source evaluation, concrete scopes, provider workflow, treatment graph,
releases, and activation remain absent.

The preceding HKEX ADR 0075 source-decision checkpoint complete shipping gate passes
strict Pyright 0, Ruff clean/419 formatted, Python boundary 223 files with the
unchanged 12 reviewed exceptions, all architecture/contract/package/
reproducibility gates, and 1246 passed/4 intentional skips in 161.79 seconds.
Its direct suite passes 14 tests, the combined Regulatory/package sweep passes
222 tests, and two rebuilt 249-file package trees are byte-identical. Package
`0.8.0` fingerprint is
`sha256:fc3a51bc795171c67a737144de406411cb535299a6fe038573eae5d0211c92d9`.

The HKEX ADR 0075 package-integrity checkpoint complete shipping gate passes
strict Pyright 0, Ruff clean/417 formatted, Python boundary 221 files with the
unchanged 12 reviewed exceptions, all architecture/contract/package/
reproducibility gates, and 1232 passed/4 intentional skips in 161.72 seconds.
Its direct suite passes 11 tests, and the combined Regulatory/package sweep
passes 208 tests. Two rebuilt package trees are byte-identical. Package `0.7.0`
fingerprint is
`sha256:1813903379f79f3f3f07328e547ae62bdda3a48a5ab49960a3ee015165b37636`.

The HKEX ADR 0074/0075 universe checkpoint complete shipping gate passes strict
Pyright 0, Ruff clean/415 formatted, Python boundary 219 files with the
unchanged 12 reviewed exceptions, all architecture/contract/package/
reproducibility gates, and 1221 passed/4 intentional skips in 157.79 seconds.
Its direct suite passes 11 tests, conformance/package sweep passes 83 tests, and
the combined Regulatory/package sweep passes 197 tests. Package `0.6.0`
fingerprint is
`sha256:08e6bf58befc608eb9fbdfcb11f2e381591d4619f2918c726bc1e2204523b1b9`.

The newer end-to-end traceability checkpoint passes strict Pyright 0, Ruff
clean/384 formatted, Python boundary 196 files with the same 12 reviewed
exceptions, all architecture/contract/package/reproducibility gates, and 1025
passed/4 intentional skips in 141.89 seconds. The focused proposal/consumer
sweep passes 165 tests and all six M7 tests pass.

HKV1-9 also remains incomplete. The last read-only host inspection showed the
declared stack plus orphan `acq-batch` and `cp-test`; application images are
older than current source/tags, timers and useful application telemetry are
absent, and plaintext credential staging duplicates need rotation/removal.
Those host mutations require their own exact authority and are not implied by
the local proof authorization.

## Authorization and side effects

The user authorized continued V1 work plus the repository CI implementation,
deletion/recreation only of the exact marked `var/local-conformance/` state, and
isolated local Docker/host proof services. The migration `000007` proof used a
new disposable database and removed its exact container; its generated
credential existed only in process memory.

No external legal source, Azure model/embedding deployment, Pinecone target,
Ask.Legal route, production system, live host SQL database, credential, or
deployed application was accessed or mutated during this checkpoint. Public
downloads were limited to the exact SHA-verified CI/image-proof tools,
BuildKit image, and Grype database. The authorized checkpoint `da90a87` was
pushed; no external source/provider/deployment action accompanied it. Do not
create another checkpoint commit or push without new exact authorization.

## Exact next work

1. Keep production V1 composition unavailable unless the exact manifest-bound
   capability profile resolves to current admitted HKV1-7 evidence; no side
   override or global enable flag may substitute.
2. Audit retained HKeL XML/XSD, verified-copy/PDF, and publication-specification
   evidence before implementing any authentic parser. The 2026-08-24 workspace
   and disposable-demo-branch audit found zero such bytes; do not claim support
   from the completed source-neutral ADR 0040 fixtures.
3. Extend the Hong Kong Cases access register with exact official Judiciary
   endpoint/enumeration/rights/format contracts only from preserved evidence;
   freeze no concrete court-year scope until its cutoff and historical boundary
   are evidenced.
4. Implement the remaining source-neutral Cases treatment-discovery,
   treatment-candidate, graph, correction, and evaluation boundaries without
   enabling a provider call.
5. Compose exact admitted Entra/current-authority/current-state/capability
   readers once their real local inputs exist.
6. Keep the proved `BEGIN` service and every provider handler out of real
   composition until HKV1-7 target/profile admission is complete.
