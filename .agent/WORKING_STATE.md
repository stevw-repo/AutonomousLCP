# AskLegal Legal Database Pipeline — Working State

Updated: 2026-08-22 — docpro-MS-7D99 (Ubuntu 24.04.4 LTS, x86-64), branch `main`

## Current goal

Advance dependency-ordered HKV1-0 through HKV1-10 to one working, honestly
scoped full-Hong-Kong local V1. Continue safe reversible local implementation
and validation; stop only for a genuine user decision, new external authority,
or destructive/live-host operation.

## Current checkpoint

HKV1-8 now has durable Review decision recording, pinned-key authentication,
restart-safe Promotion reconstruction, exact single-use no-effect Approval
consumption, mutually exclusive durable revocation/invalidation, and a
Promotion-only no-effect execution-authorization transition for the exact
consumed lineage. All eleven proposal members are semantically validated before
Review or Promotion can use them. No Effect Intent or promotion effect is
enabled. HKV1-1 is locally complete but remains `IN PROGRESS` until the current
CI definition receives a hosted run.

HKV1-3 now has fail-closed publication/enactment, commencement,
cessation/revival, text-changing event, bounded pre-Plan semantic, and complete
deterministic ADR 0084 Plan-validation checkpoints. Frozen package `0.27.0`
contains 33 rules and 216 deterministic
fixtures; its readiness contract is
mechanically generated from the actual rule and fixture inventory.
Twelve new cases bind exact operative-provision and event-evidence fingerprints,
classify default, fixed, appointed, conditional, and progressive partial
commencement, and return exact operative/pending locations at the cutoff.
Future or unsatisfied events remain in the Waiting Room; incomplete evidence
blocks and conflicts or invalid affected sets quarantine. This is synthetic
conformance only; all three scopes remain `NOT_READY`.

Fourteen additional cases cover whole/partial and future/operative repeal,
revocation, expiry, and revival. They bind pre/post operative/ceased partitions
and the prior event-history fingerprint. Cessation preserves identity; revival
requires explicit continuity. Ambiguous continuity, evidence, or state
quarantines without an Official Version or Search Record.

Sixteen additional cases cover operative and future amendments, express
official corrections, and HKeL Editorial Record events. They enforce
fact-specific source authority, distinct principal/source-event identity,
complete bilingual operation mapping, exact whole/partial affected locations,
effective timing, resulting-bundle consistency, and append-only event history.
They route but never construct text, an Official Version, or a Search Record.

Thirteen additional cases classify exact ordinary and Extraordinary Gazette
publication facts across Legal Supplement Nos. 1–3, Main Gazette notices, and
other supplements. The decision binds issue/artifact/source/bilingual evidence,
requires enabling authority for a Main Gazette notice, and produces no
commencement, current-law, identity, continuity, version, or record conclusion.

Thirteen additional cases implement the first Reconstruction Plan
decision/challenge gate. One exact admitted, evidence-bound, closed-registry,
challenge-confirmed result produces only an
`UNTRUSTED_STRUCTURED_PLAN_CANDIDATE`. The other cases block or quarantine
missing profiles/results, invalid contracts, incomplete evidence spans,
unsupported operations, model-authored final text, challenge objection or
uncertainty, conflicting semantic results, and failed deterministic prechecks.
No branch creates an executable Plan, executes an operation, constructs text,
calls a provider, activates a profile, emits a record, or performs an effect.

The complete shipping command passed after the Plan-validation slice with strict Pyright 0,
Ruff clean/375 formatted, boundary 187 files/the unchanged 12 exceptions,
architecture 5 apps/14 packages/80 edges/31 ports, contract fingerprint
`sha256:7bd2858bd0099271bc5be1e8d5c380521d81fb15bee8a4110de8fe6629d3094e`,
and 959 passed/4 intentional opt-in skips.

The 21-case ADR 0084 Plan validator binds the existing candidate identity and
canonical fingerprint only after every closed contract, authority, base,
event-chain, applicability, dependency, evidence-ownership, bilingual-stream,
operation, event-binding, atomic-group, and revalidation condition passes. It
executes no operation, constructs no text or artifact, emits no record, and
performs no external effect. All three real scopes remain `NOT_READY`.

## HKV1-3 work now implemented

- `HKLEG-CURRENT-COMMENCEMENT-001` never infers legal effect from publication or
  HKeL `InEffect` alone and emits no Search Record or Official Version.
- Operative decisions carry the exact operative-provision fingerprint, retained
  event-evidence fingerprints, publication/effective dates,
  `event_operative_at_cutoff`, and exact affected/operative/pending locations for
  later missing-consolidation routing.
- Fixed and appointed future dates plus exact unsatisfied conditional events are
  preserved as `WAITING_ROOM`; operative whole-instrument events route to
  `HKLEG-CURRENT-EVENT-001`.
- Progressive partial commencement retains the prior operative locations,
  changes only the exact newly named set, and keeps the remainder pending.
- Missing authenticity/completeness, missing effective or appointment facts,
  and future publication observations block. Conflicting notice/evidence chains
  or unbounded/inconsistent location sets quarantine.
- The builder refreshes `contracts/readiness-contract.json` before building the
  manifest. Tests require its 32 rule IDs and 195 fixture IDs to equal the
  actual frozen package inventory, eliminating the stale baseline-only list.
- `HKLEG-CURRENT-CESSATION-001` moves only exact affected locations between
  operative and ceased state. Future events preserve pre-event state; accepted
  events append to the bound prior history while failed decisions preserve it.
- Repeal/revocation/expiry preserve identities and cannot imply substitution or
  a successor. Revival routes onward only with explicit continuity proof.
- `HKLEG-CURRENT-TEXT-EVENT-001` accepts only exact Gazette amendment/express-
  correction authority or exact HKeL Editorial Record authority, complete
  bilingual operation maps, effective timing, exact affected locations, and a
  distinct source-event identity. Matching HKeL bundles return to ordinary
  evidence validation; missing consolidation creates a Coverage Gap; future
  events preserve pre-event text. Failed paths preserve prior history.
- `HKLEG-CURRENT-PUBLICATION-001` preserves exact Gazette publication facts and
  class-specific authority without inferring commencement or current text.
  Legal Supplement No. 3 is inventory-only; other supplements are discovery-
  only; Extraordinary timing does not change the material class.
- `HKLEG-RECON-PLAN-SEMANTIC-001` validates only exact admitted decision and
  challenge result claims. Successful output remains an untrusted structured
  candidate for the full deterministic ADR 0084 Plan validator. It cannot mint
  an `rpl_` identity, execute ADR 0082 operations, or author text.
- `HKLEG-RECON-PLAN-001` validates the complete ADR 0084 Plan envelope and
  returns the existing `rpl_` candidate identity and canonical fingerprint only
  after all deterministic gates pass. It executes no operation and mints no
  artifact or record.
- Package version `0.27.0` has fingerprint
  `sha256:f5eabc5748274e0cb1301ab1d10a7251f3c307bfe375808a6d5b5db253e0cbe7`.

## HKV1-8 work now implemented

- Review re-reads the exact proposal root plus all 11 member versions from the
  Primary Vault, checks canonical bytes, identity, role, path, media type,
  length, fingerprint, and the executable Promotion Manifest bindings, and
  displays the real inventory rather than repeated placeholder hashes.
- Approval validity predicates now carry exact
  `(contract_id, version, fingerprint)` triples as required by Approval 1.1.0.
- A delegated named-human `PipelineAdministrator` can record a schema-valid
  approve/reject event through the generic atomic register command only after a
  complete proposal reread and current identity/authority-evidence check.
- The Review decision command has no effect intent and creates no provider,
  target, backup, routing, or promotion authority. Replay is exact; stale,
  competing, role-removed, app-token, manifest-drift, and tamper paths fail
  closed.
- Control proposal registration and Review decision are separate
  application-owned aggregate versions. Registration creates Control version 1;
  the first decision expects Review version 0 and creates Review version 1.
- SQL migration `000004` exposes the proposal receipt plus optional decision to
  only Review and Promotion roles and denies direct fact-table access.
- A pinned-key Entra v2 access-token verifier now checks exact RS256 key,
  issuer, tenant, audience, allowed client, delegated scope, lifetime, stable
  object identity, role, and token kind without discovery/JWKS network fallback.
  Production V1 composition remains disabled until its exact admitted profile
  and current-authority adapter exist.
- Promotion reconstructs only an approved candidate from the durable SQL
  projection, independently rereads all twelve Primary Vault objects, validates
  the executable manifest and schema-valid decision, and binds current base,
  predicates, reviewer authority, validity window, command window, and one exact
  execution lineage.
- Migration `000005` exposes one specialized atomic consumption procedure only
  to Promotion, records a single no-effect `APPROVAL_CONSUMED` event, resolves
  exact replay, rejects a competing lineage, and expressly denies Promotion the
  generic command writer.
- Migration `000006` adds a Review-only named-human revocation command and a
  Promotion-only objective invalidation command. Both share consumption's exact
  per-Approval lock and terminal winner, emit no Effect Intent, replay exactly,
  and block later consumption.
- Migration `000007` adds the Promotion-only durable
  `EXECUTION_PLANNED -> EXECUTION_AUTHORIZED` transition. It proves the exact
  consumed proposal, decision, manifest, `exe_` lineage/fingerprint, worker
  identity, validation evidence, and canonical authorization fingerprint before
  execution aggregate version 1. Replay and lost acknowledgement resolve
  exactly; unmatched consumption and changed bindings fail. It emits no Effect
  Intent and enables no handler.
- One shared contract validates the exact eleven-role set, canonical JSON,
  role-specific fields, release/desired-state/coverage/traceability identity,
  complete coverage evidence, cost/capacity, recovery readiness, serving-state
  bindings, validation results, Review report, and executable Promotion
  Manifest. Control/Promotion use it after all twelve exact-version reads;
  Review calls it independently. Correctly hashed placeholders and
  cross-member drift fail before listing, decision, or Approval reconstruction.

## Validation performed on the current slice

- Focused Review/Approval/promotion tests: 74 passed.
- Registered Review/projection/migration tests after the final typing fix:
  23 passed.
- Entra plus Review/Control API tests: 25 passed.
- Architecture/application-image/wheelhouse/artifact tests: 58 passed.
- All application-runtime tests with loopback permission: 50 passed.
- Focused strict Pyright: 0 errors; focused Ruff formatting/lint: clean.
- `uv lock --check --offline`: resolved 89 packages, success.
- `git diff --check`: clean before the continuity update.
- Focused registered Review/Promotion/projection/migration tests: 35 passed.
- Fresh digest-pinned disposable SQL Server proof: 1 passed with migrations
  `000001` through `000006`, decision projection reads, exact single-use
  consumption, revocation, invalidation, replay, later-consumption denial,
  app-specific permissions, and concurrent terminal single-winner behavior.
  The temporary container and generated credential file were removed.
- Pre-semantic terminal-lifecycle shipping gate: strict Pyright 0; Ruff
  clean/370 formatted; Python
  boundary 183 files/12 unchanged exceptions; architecture 5 apps/14 packages/
  80 edges/31 ports; 932 passed/4 skipped.
- Semantic proposal checkpoint: 37 focused tests passed; complete shipping gate
  then passed with strict Pyright 0, Ruff clean/373 formatted, Python boundary
  185 files/12 unchanged exceptions, architecture 5 apps/14 packages/80 edges/
  31 ports, and 943 passed/4 skipped.
- Registered execution-authorization checkpoint: 20 focused tests passed;
  focused Pyright 0 and Ruff clean. A fresh digest-pinned disposable SQL Server
  applied migrations `000001` through `000007` twice and passed exact
  consumed-lineage authorization, replay, acknowledgement-loss recovery,
  command-tamper rejection, unconsumed/changed-lineage rejection, application
  permissions, event read-back, and unchanged Effect Intent count. The exact
  temporary container was removed.
- Previous complete shipping gate: strict Pyright 0; Ruff clean/375 formatted;
  Python boundary 187 files/12 unchanged exceptions; architecture 5 apps/14
  packages/80 edges/31 ports; 951 passed/4 skipped in 42.20 seconds. Package
  conformance and two isolated byte-identical contract snapshots passed.
- Previous Hong Kong Legislation package proof: 53 passed. Focused strict
  Pyright reports 0 errors, focused Ruff is clean, and `git diff --check`
  passed before the continuity update.
- Previous `0.24.0` Hong Kong Legislation package proof: 55 passed. Focused
  strict Pyright reports 0 errors; focused Ruff lint/format and
  `git diff --check` pass.
- Previous complete shipping gate: strict Pyright 0; Ruff clean/375 formatted;
  Python boundary 187 files/12 unchanged exceptions; architecture 5 apps/14
  packages/80 edges/31 ports; 953 passed/4 skipped in 44.01 seconds. Package
  conformance and two isolated byte-identical contract snapshots passed.
- Current `0.25.0` Hong Kong Legislation package proof: 57 passed. Focused
  strict Pyright reports 0 errors; focused Ruff lint/format and
  `git diff --check` pass.
- Current `0.26.0` Hong Kong Legislation package proof: 59 passed. Focused
  strict Pyright reports 0 errors; focused Ruff lint/format and
  `git diff --check` pass.
- Latest complete shipping gate: strict Pyright 0; Ruff clean/375 formatted;
  Python boundary 187 files/12 unchanged exceptions; architecture 5 apps/14
  packages/80 edges/31 ports; 957 passed/4 skipped in 47.27 seconds. Package
  conformance and two isolated byte-identical contract snapshots passed.
- Current `0.27.0` Reconstruction Plan validation slice: 61 focused
  rulebook tests passed; its JSON schema parses; 21 input and 21 expected
  fixtures are present; focused strict Pyright reports 0 errors; Ruff lint
  and format checks pass.
- Latest complete shipping gate after `0.27.0`: strict Pyright 0; Ruff clean/
  375 formatted; Python boundary 187 files/12 unchanged exceptions;
  architecture 5 apps/14 packages/80 edges/31 ports; reproducible contracts;
  959 passed/4 intentional opt-in skips in 52.27 seconds.
- A fresh read-only host check on 2026-08-22 confirms all fourteen declared
  AskLegal services are active, no AskLegal timers are installed, and the
  unsupervised `acq-batch` and `cp-test` containers are still running alongside
  the declared stack. No host state was changed.

No live database, service, source, provider, model, embedding, Pinecone target,
backup, or Ask.Legal route was accessed or changed.

## Corrections discovered

- The initial real-engine count expected only the proposal-registration
  command/event. Migration `000004` correctly adds a distinct Review
  command/event/recovery pair; the proof assertion now accounts for both and
  passes from a clean database.
- Approval schema 1.1.0 makes the validity-condition contract version
  mandatory. Earlier two-part predicates could only produce a schema-valid
  decision by inventing a version; the model now carries the source version.
- The API dependency types previously accepted only the local opaque-token
  fake. They now consume an `IdentityVerifier` protocol, allowing the real
  verifier without weakening local tests.
- PyJWT 2.13 and cryptography 50 were already pinned transitively. They are now
  declared direct application-runtime dependencies, the lock remains
  offline-consistent, and architecture/image input fingerprints were refreshed.
- The first real-engine `000005` run exposed UTF-8 canonical JSON bytes being
  decoded as UTF-16 `nvarchar`. The procedure converts stored bytes to
  `varchar` before `JSON_VALUE`. The later normative execution-lineage fix from
  `lin_` to `exe_` refreshed package fingerprint `000005` to
  `424a4e26ba16a4ff7880553c4c1cff64906a78418f36d9457d55ff0f9f4b5301`.
- A second SQL audit found that missing JSON fields could exploit SQL's
  three-valued `NULL` logic and bypass an `OR`-joined guard. Every required
  consumption field now uses explicit null rejection, and the real engine
  rejects a command with its action omitted.
- The complete gate rejected three new static casts even though focused Pyright
  passed. The verifier now uses runtime narrowing with `TypeIs`; the reviewed
  boundary exception set remains unchanged.
- The first `000007` engine run exposed SQL Server promoting a `CONCAT` that
  included `JSON_VALUE` to UTF-16 before hashing the canonical authorization
  document. The procedure now explicitly converts that canonical ASCII JSON to
  `varchar` before `varbinary`; the fresh engine reproduced the application
  fingerprint. Migration `000007` package fingerprint is
  `0582254e629486770cfaa026060295855ad618caa0d61728c265fd0d5ca5314d`.
- The legislation readiness contract was a stale manually maintained subset: it
  listed only the original baseline rules and fixtures while the package
  manifest carried every later current-update slice. The package builder now
  regenerates that contract from every actual `HKLEG-*.json` rule and declared
  fixture group before fingerprinting the manifest; package tests compare it to
  the loader-visible inventory.

## Remaining HKV1-8 frontier

1. Admit and compose exact Entra tenant/client/scope/signing-key metadata plus a
   real current-authority evidence source.
2. Define the separately guarded `EXECUTION_AUTHORIZED -> EXECUTION_RUNNING`
   `BEGIN` transition and first atomic Effect Intent, while leaving it
   unavailable until exact HKV1-7 capability/profile inputs are admitted.
   The audit found that the current executable M6 manifest carries only opaque
   `action_ids` and one global `capability_enabled` boolean. It does not yet bind
   each action's effect type, exact capability-profile reference, destination,
   retry/stop policy, remote precondition, success postcondition, or
   compensation. `BEGIN` must not infer those values at runtime; this manifest
   authority contract is a prerequisite, not an implementation default.
3. Only after that chain and HKV1-7 profiles exist, implement real local
   backup/cutover/reverse-swap/rollback orchestration.

No provider effect may be re-enabled while exact model/embedding/target profiles
and the complete approved durable command chain remain unadmitted.

## Other V1 blockers kept visible

- HKV1-0/2: GLD e-Gazette is the earliest originating official Gazette source,
  but its lawful Turnstile-gated procedure is not technically admitted; HKeL is
  complementary recovery/backcapture, not a complete substitute.
- HKV1-3: all three real Hong Kong Legislation scopes are `NOT_READY`.
- HKV1-4: no executable Hong Kong Cases package exists.
- HKV1-5: no executable HKEX Regulatory package exists.
- HKV1-6: Principles publisher/title/licence scope needs user selection before
  the accepted design can claim the complete Hong Kong jurisdiction.
- HKV1-7: placeholder/ad-hoc semantic and target profiles are not admitted.
- HKV1-9: orphan host containers, stale deployed images, credential staging,
  missing timers/telemetry, and recovery/reboot proof remain.
- HKV1-10: no complete real baseline, Approval, activation, or rollback exists.

## Working-copy and authorization state

- Branch `main`; last pushed checkpoint `3f340c7`; no later commit/push.
- The large dirty tree is intentional accumulated V1 work. Preserve it.
- The user authorized continued V1 work and the completed isolated local
  package/SQL/Durable/image proofs.
- No authorization exists for another commit/push, external legal-source fetch,
  provider/model/Pinecone call, deployment, credential rotation, stopping live
  host services, applying migrations to the live SQL container, or production
  mutation.
- Continue reversible local HKV1-8 implementation with synthetic keys/data and
  disposable proofs while all external-effect adapters remain disabled.

## Files added or materially changed in this checkpoint

- `apps/review-api/src/asklegal_review_api/registered_proposals.py`
- `apps/review-api/src/asklegal_review_api/governance.py`
- `apps/review-api/src/asklegal_review_api/api.py`
- `apps/review-api/src/asklegal_review_api/v1_infrastructure.py`
- `apps/review-api/tests/test_registered_proposals.py`
- `apps/review-api/tests/test_registered_governance.py`
- `packages/management-register-adapter/migrations/000004_proposal_decisions/`
- `packages/management-register-adapter/src/asklegal_management_register/store.py`
- `packages/management-register-adapter/tests/test_review_ready_store.py`
- `packages/management-register-adapter/tests/test_sql_server_integration.py`
- `packages/application-runtime/src/asklegal_application_runtime/entra_identity.py`
- `packages/application-runtime/src/asklegal_application_runtime/identity.py`
- `packages/application-runtime/tests/test_entra_identity.py`
- `apps/promotion-worker/src/asklegal_promotion_worker/registered_approval.py`
- `apps/promotion-worker/tests/test_registered_approval.py`
- `packages/contracts/src/asklegal_contracts/proposal_members.py`
- `packages/contracts/tests/test_proposal_members.py`
- `packages/promotion/src/asklegal_promotion/proposal.py`
- `tools/tests/proposal_member_fixture.py`
- `packages/management-register-adapter/migrations/000005_registered_approval_consumption/`
- `packages/management-register-adapter/migrations/000006_registered_approval_terminal_lifecycle/`
- `apps/promotion-worker/src/asklegal_promotion_worker/registered_execution.py`
- `apps/promotion-worker/tests/test_registered_execution.py`
- `packages/management-register-adapter/migrations/000007_registered_execution_authorization/`
- `packages/legal-desks/src/asklegal_legal_desks/hk_legislation.py`
- `packages/legal-desks/src/asklegal_legal_desks/__init__.py`
- `packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package/`:
  version `0.27.0`, publication/enactment, commencement, cessation/revival,
  text-changing-event, bounded Reconstruction Plan semantic, and complete
  deterministic Plan-validation rules/schemas/catalogues, 89 input/expected
  fixtures across those newest slices, and regenerated readiness
  contract/catalogues/manifest
- `packages/legal-desks/tests/test_rulebook_package.py`
- `tools/build_hk_legislation_rulebook.py`
- Promotion/Approval model and conformance literals carrying versioned validity
  predicates; `packages/application-runtime/pyproject.toml`, `uv.lock`,
  `tools/architecture_spike_manifest.json`, and application-image inputs.
- `.agent/CONTEXT.md`, `.agent/DECISIONS.md`, `.agent/ROADMAP.md`,
  `.agent/HANDOFF.md`, and this file.

## Exact next steps

1. Implement exact validated-Plan-to-operation execution and immutable
   Reconstruction Report/artifact validation behind `HKLEG-RECON-PLAN-001`,
   preserving source-unit ownership and executing no undeclared operation.
2. Keep the Promotion `BEGIN` boundary fail-closed until the executable manifest
   owns a complete per-action effect/capability authority contract and HKV1-7
   supplies exact admitted profiles; do not infer either from `action_ids` or a
   boolean.
3. Keep every provider handler disabled and update continuity before any
   operational boundary.
