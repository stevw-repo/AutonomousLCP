# AskLegal Legal Database Pipeline — Working State

Updated: 2026-08-14

## Repository isolation checkpoint

The user required strict separation between this greenfield repository and all
legacy Ask.Legal workspaces on 2026-08-13. This file contains only greenfield
state. Legacy instructions, operational priorities, approvals, target names,
and next steps do not apply here and must not be imported. Cross-project
inspection occurs only after an explicit user request and never merges project
memory or authority.

## Topic-review working rule

The user directed on 2026-08-14 that remaining design topics be handled one at
a time. When one approach is clearly optimal and does not require a genuine
product decision, adopt and document it without asking for approval. Escalate
only a real choice whose alternatives materially change product behavior,
risk, cost, or legal-processing scope. Keep each topic and its outcome clear
before moving to the next.

## HKEX Listing Rules classified as Hong Kong Regulatory Materials

The user approved the Regulatory classification on 2026-08-12. ADR 0054 adds
**Hong Kong Regulatory Materials** as a separate material family, exposes the
user-facing category **Regulatory**, and adds `metadata.type: "regulatory"` to
the existing six-field serving envelope. The initial scope is the current
effective Main Board and GEM Listing Rules. `Policy` is rejected as the family
name because it would blur formal exchange regulatory requirements with
ordinary guidance and the project's internal rulebook policy.

Main Board and GEM are separate Legal Items and Release Scopes. Each scope
must completely inventory every Chapter, note, appendix, Practice Note,
Regulatory Form, Fees Rule, or other component that HKEX expressly makes part
of that rulebook. Guidance letters, FAQs, listing decisions, circulars,
consultations, and other non-rule material remain outside the initial
searchable scope; any regulatory-guidance corpus requires another explicit
decision.

HKEX-maintained consolidated PDFs control current wording over the
Thomson Reuters-maintained online rulebook presentation. Official amendment
packages and update notices provide their assigned change, effective-date,
external-trigger, and transition facts. The pipeline does not equate newest
publication with current effect. Future or conditional amendments remain
outside ordinary search, and concurrently applicable transitional cohorts
remain explicit.

Each ordinary record contains the complete prevailing English rule text and
English applicability context for one market, rule location, effective state,
and transition branch. It contains no Chinese source block, Chinese-only
duplicate, or parallel Chinese vector. Official Chinese translations may be
preserved as optional non-serving evidence and do not block a supported English
record unless they expose a possible defect in the controlling English result.

ADR 0069 now settles the component-inventory and completeness contract. The
actual Main Board and GEM inventory rows remain future registry artifacts. ADR
0070 now settles the lean five-role Registered Source and Fact Authority
contract. ADR 0071 now settles branch-level effective-state and transition
rules. ADR 0072 now settles English-only serving and supersedes ADR 0054's
original bilingual layout for this material family. ADR 0073 now settles exact
conceptual English record construction, official-boundary partitioning, and
source-unit coverage proof. ADR 0074 now settles the two linked Regulatory
conformance layers, strict suite package, frozen coverage-matrix mechanics,
high-risk pairs, critical errors, reproducibility, and separate build
attestation. ADR 0075 now freezes the audited exact catalogue at 284 direct
cases, 284 matching primary cells, and 57 high-risk pairs. ADR 0076 settles
change-gated two-pass update and record semantic proposal tasks around
deterministic fast paths, Legal Desk authority, and deterministic finalization.
ADR 0077 settles separate multilingual retrieval, frozen-context answer, and
complete query-path admission for the English-only corpus.

The high-level Hong Kong Regulatory Materials design checkpoint is complete.
Executable rulebook codes, schemas, package bytes, source registry rows, task
contracts, sealed real-source evaluations, models, prompts, numerical limits,
retrieval queries and thresholds, implementation, and operational evidence
remain separately gated artifacts.

## Current objective and checkpoint

The user approved the completed Hong Kong Case Proposition evaluation-package
checkpoint and selected the detailed Hong Kong Regulatory Materials design as
the next greenfield task on 2026-08-14. That design checkpoint is now complete:
ADR 0054's policy boundary has been turned into a complete high-level
`hk-regulatory` source and rulebook design. ADR 0069 settles the Main Board and GEM component-inventory
and inclusion-proof contract, and ADR 0070 now settles the lean source
register. ADR 0071 now settles effective-state and transition rules. Bilingual
serving is superseded by ADR 0072's English-only design, and ADR 0073 now
settles English record construction. ADR 0074 settles the Regulatory
conformance architecture, ADR 0075 the exact frozen catalogue, ADR 0076 the
high-level semantic task allocation, and ADR 0077 multilingual retrieval and
answer admission. No unresolved high-level Regulatory design choice is known.
The next work is executable specification and implementation planning only
after separate user authorization. No source acquisition, schema
implementation, model call, corpus construction, or production action is
authorized.

The user approved ADR 0078 and moved to the signed coverage-status interface on
2026-08-14. This cross-cutting design is now active. Its purpose is to stop a
known source, consolidation, Quarantine, withholding, or no-rebuild gap from
looking like an ordinary no-result answer. One genuine product choice remains:
when no valid signed or still-valid cached coverage snapshot can be verified,
should Ask.Legal continue with an unavoidable prominent `COVERAGE STATUS
UNAVAILABLE` warning, or refuse answers for the affected jurisdiction until
status verification recovers?

During this interface design, the user corrected the treatment of a known
official legislation change whose updated official consolidated text is not
yet available. ADR 0080 now permits exact evidence-bound reconstructed
bilingual legislation with the approved warning. Under ADR 0081, ordinary
records, reconstruction bases, and ADR 0079 fallbacks may use the latest
applicable official HKeL copy whether verified or assisted. A newer eligible
assisted version is not held back by an older verified version. Exactly one
result serves per affected unit. This settles the high-level
consolidation-gap serving behavior; it does not settle the separate coverage-
snapshot-service outage choice above.

The preceding Hong Kong Case Proposition task began on 2026-08-13 and is now
complete at the current design level. ADR 0060's output-and-evidence contract
settles what qualifies as one material proposition, what one searchable
record must contain, how the downstream LLM receives both a labelled derived
statement and minimum exact judgment support, and when one judgment correctly
produces zero, one, or many records. ADR 0061 settles split, merge, opinion,
adoption, overlong-record,
and correction-lineage boundaries. ADR 0062 now settles the immutable complete
source-unit, dependency, candidate, evidence-role, result, and zero-proposition
Coverage Ledger. ADR 0063 separates semantic evaluation from deterministic
conformance, ADR 0064 freezes the initial 132-case extraction catalogue, and
ADR 0065 now settles the high-level extraction allocation: deterministic
admission, validation, reconciliation, and finalization surround separate LLM
analysis and challenge passes, followed by Legal Desk acceptance and narrowly
triggered human review. ADR 0066 fixes their evidence-bound semantic task
contracts, and ADR 0067 now settles the complete-workflow admission, context,
evaluation-repetition, retry, cost, provider-data, monitoring, suspension, and
revalidation policy. ADR 0068 now settles the future executable evaluation-
suite package, protected evidence views, sealed real-judgment selection,
Reference Proposition Map adjudication, evaluator and run-result contract,
pre-frozen evidence-derived admission profile, and final non-circular
admission binding.

The preceding Hong Kong Cases later-treatment task is complete at the current
design level. Classification axes, evidence thresholds,
proposition mapping, uncertainty behavior, Legal Desk acceptance, authority-
note rendering, and immutable serving transitions are now settled through ADR
0055. ADR 0056 settles the two-suite, coverage-driven conformance architecture,
ADR 0057 settles permanent non-leaking IDs, strict package mechanics,
catalogues, coverage-matrix semantics, and expected artifact roles, and ADR
0058 settles one directional treatment relationship, two derived internal
views, and the Pinecone boundary. The final design-level audit is now complete
in `docs/design/HONG_KONG_CASE_TREATMENT_DESIGN_AUDIT.md`. It corrected omitted
boundaries and non-exact catalogue rows. The resulting exact initial coverage-
cell and case table is accepted and frozen by ADR 0059 with 155 direct cases,
155 matching primary coverage cells, and 21 high-risk pairs. No immediate Hong
Kong treatment-catalogue decision remains. Detailed Hong Kong Regulatory
Materials source and rulebook design was the next task and is now complete at
the high-level design checkpoint. ADRs 0054, 0069, 0070,
0071, 0072, 0073, and 0074 are the accepted Regulatory decisions.

The preceding Hong Kong Cases checkpoint remains settled. ADR 0052 defines
ordinary bounded-impact updates and HKLII's discovery-only role. ADR 0053
defines staged hybrid later-treatment analysis: deterministic admission and
structure, whole-judgment LLM discovery, candidate-specific evidence analysis,
deterministic validation, and a controlling Legal Desk decision. Provider use
remains disabled until exact task contracts, models, evaluations, thresholds,
review rules, costs, and failure behavior are accepted.

### Current handoff

- **Progress:** the treatment architecture and conformance universe are
  settled, and ADR 0060 now accepts the first Case Proposition qualification,
  serving-text, evidence, one-record, coverage, zero-record, and Quarantine
  rules. ADR 0061 now accepts the exact conceptual-boundary, same-opinion
  deduplication, multi-opinion, adoption, overlong-record, and correction-
  lineage rules. ADR 0062 now accepts the exact Coverage Ledger identity,
  exhaustive source-unit and opinion inventory, segmentation and dependency
  arithmetic, unit and candidate outcomes, completion states, and zero-
  proposition proof. ADR 0063 now accepts separate semantic and deterministic
  extraction suites, hidden adjudicated Reference Proposition Maps, coverage-
  driven catalogues, exact complete-workflow admission, critical-error gates,
  and the separate retrieval-quality boundary. ADR 0064 now freezes the exact
  initial 132 direct cases, 132 primary coverage cells, seven group counts, 31
  high-risk pairs, synthetic-versus-sealed-real boundary, and immutable
  expansion rule. ADR 0065 now accepts the seven-stage two-pass hybrid
  extraction allocation, mandatory independent LLM challenge, deterministic
  objection reconciliation, automatic ordinary Legal Desk acceptance, and
  narrow exact human-review triggers. ADR 0066 now fixes the two task-family
  IDs, closed request kinds, exact evidence-bound conceptual requests and
  responses, long-judgment multi-call rule, translation and predecessor default
  exclusions, deterministic quotation-copy boundary, independent challenge,
  no-confidence rule, and representation-only schema repair. ADR 0067 now
  accepts complete-workflow rather than model-name admission, immutable
  lifecycle states, a 20% minimum context reserve, all 132 synthetic cases plus
  sealed real judgments, three ordinary and five high-risk semantic
  repetitions, exact deterministic runs, no critical errors, bounded retries
  and re-analysis, pre-reserved per-judgment cost, weekly canaries, a complete
  suite at least every 90 days, automatic suspension, and evidence-backed
  restart. ADR 0068 now separates the candidate-independent Evaluation Suite
  Package, one pre-frozen Workflow Admission Profile, the complete Evaluation
  Run Set, and final dual-attested Workflow Admission. It fixes canonical
  inventories and fingerprint order, model-facing versus protected evidence,
  a branch-driven sealed real-case matrix, exposure and replacement rules,
  independent Reference Map review, evaluator stages and statuses, explicit
  per-dimension and per-slice results, and the prohibition on changing a
  threshold after viewing sealed results merely to make a candidate pass.
  ADR 0069 now accepts immutable cutoff-bound HKEX component inventories,
  separate observed-entry and board-owned component identities, exact
  membership and ownership, separate effective-state, disposition and
  processing results, four completeness proofs, shared-artifact behavior,
  immutable updates, and fail-closed uncertainty. ADR 0070 now accepts exactly
  five ordinary current-source roles, their Fact Authorities, union-based
  inventory responsibility, bounded outage effects, deterministic monitoring,
  on-demand trigger evidence, optional-source boundary, approval inference,
  and downstream-LLM separation. ADR 0071 now accepts applicability-branch
  state as the atomic decision, one derived component summary, exact fixed-date
  and external-trigger behavior, complete concurrent transitions, strict
  superseded-versus-withdrawn evidence, source-lag Quarantine, and separate
  serving disposition. ADR 0072 now accepts complete prevailing English
  serving text, removes Chinese from the ordinary release dependency and
  Pinecone payload, preserves it as optional support, and requires complete
  Chinese-query evaluation without fabricated Chinese source text. ADR 0073
  now accepts the smallest complete class-specific English record unit,
  canonical renderer, minimum governing context, non-recursive
  cross-references, exact final-payload fit checks, recursive official-
  structure partitioning, and immutable English source-unit coverage proof.
  ADR 0074 now accepts one evidence-to-decision catalogue, one exact
  decision-to-artifact deterministic catalogue, one frozen branch-driven
  coverage matrix, strict packages, non-answer-bearing IDs, hidden reference
  results, high-risk pairs, critical-error gates, two-run reproducibility, and
  separate build attestation; it did not itself settle task allocation, which
  ADR 0076 now settles.
  ADR 0075 freezes the exact `62/51/30/35/24/20/24/38` checkpoint counts,
  284 direct cases and matching cells, and 57 complete pairs. ADR 0076 accepts
  four change-gated update and record analysis-and-challenge proposal tasks,
  with deterministic admission and finalization and Legal Desk authority. ADR
  0077 accepts separate multilingual retrieval, frozen-context answer, and
  complete query-path admission profiles and defers any Chinese-serving redesign
  unless supported English-only candidates later fail mandatory gates.
- **Decision-escalation rule:** complete obvious or ADR-entailed work without
  requesting approval. Ask the user only about a genuine unresolved tradeoff
  that materially changes legal meaning, product behavior, acceptable risk,
  cost, quality, or human-review burden. Routine group expansion, exact rows,
  pair membership, IDs, audit, validation, and consistency repairs do not need
  user approval.
- **Completed autonomous work:** coverage groups 3 through 6, exact row
  expansion, pair membership, branch audit, catalogue freeze, Regulatory LLM-
  versus-deterministic allocation, and multilingual retrieval and downstream-
  answer admission architecture. No genuine user decision was exposed.
- **Remaining work:** exact executable Source Rulebook and reason codes,
  schemas, fixture bytes, current source and component registry rows, task
  contracts and admission packages, sealed real-HKEX evaluations, models,
  prompts, numerical limits, query and relevance artifacts, thresholds, and
  implementation. These are specification or implementation artifacts rather
  than unresolved high-level product decisions.
- **Blockers:** implementation and every source, evaluation, provider,
  Pinecone, Azure, promotion, and deployment action remain unauthorized.
- **Files changed for the ADR 0074 checkpoint:** ADR 0074; refinement
  references in ADRs 0054, 0069, 0070, 0071, 0072, and 0073; `README.md`; the
  canonical overall design; and all three continuity files. The glossary and
  canonical design now also define the Legal Desk, its owner, decision record,
  inputs, outputs, and forbidden capabilities explicitly.
- **Files changed for the first accepted catalogue group:** new canonical
  `docs/design/HONG_KONG_REGULATORY_CONFORMANCE_CATALOGUE.md`, `README.md`, the
  canonical overall design, `docs/agent/DECISIONS.md`, and this working state.
- **Files changed for the second accepted catalogue group:** the canonical
  Regulatory catalogue, `README.md`, the canonical overall design,
  `docs/agent/DECISIONS.md`, and this working state.
- **Latest user instruction:** for the seven remaining Regulatory topics,
  resolve clearly optimal and already entailed design choices autonomously and
  surface only genuine consequential decisions. This preference is also
  preserved in `docs/agent/CONTEXT.md` and `docs/agent/DECISIONS.md`.
- **Files changed for completion:** ADRs 0075, 0076, and 0077; refinements to
  ADRs 0039, 0043, 0072, 0074, and 0075; the exact Regulatory catalogue;
  `README.md`; the canonical overall design; and all three continuity files.
- **Completed shared contract:** ADR 0078 fixes the closed six-field Serving
  Record, JCS and SHA-256 fingerprint meanings, exact traceability entry,
  Release-Scope shards, root manifest, one-to-one validation, and lookup-only
  revision behavior. No genuine product decision required escalation.
- **Files changed for ADR 0078:** ADR 0078; refinement references and later-
  decision notes in ADRs 0004, 0008, 0009, 0011, 0013, 0016, and 0050;
  `README.md`; the canonical overall design; and all three continuity files.
- **Completed known-consolidation-gap rule:** ADR 0079 keeps valid last-
  verified official wording searchable for each affected legislation location,
  uses a new warned Search Record identity while
  permitting eligible text-embedding reuse, exposes the gap to both the UI and
  downstream LLM, and is now ADR 0080's safe fallback.
- **Files changed for ADR 0079:** ADR 0079; amendments to ADRs 0005, 0012,
  0023, 0025, 0026, 0033, 0034, 0038, and 0044; refinement metadata in ADRs
  0011, 0013, 0050, and 0078; `README.md`; the canonical design and Hong Kong
  Legislation design audit; and all three continuity files.
- **Completed reconstruction decision:** ADR 0080 supersedes ADR 0023, permits
  exact deterministic bilingual reconstruction with the approved warning and
  ordinary legislation serving behavior, and makes ADR 0079 the fallback.
- **Files changed for ADR 0080:** ADR 0080; reconstruction-related ADR
  back-references and current-rule corrections; `README.md`; the canonical
  design and Hong Kong Legislation design audit; and all three continuity
  files.
- **Completed reconstruction specification sequence:** ADRs 0082 through 0087
  now settle the operation registry, conformance universe, Plan and Report,
  final artifact, later-HKeL reconciliation, and readiness/activation boundary.
  Implementation and every external capability remain separately unauthorized.

## Settled Serving Record and Record Traceability Lookup encoding

The user continued into this shared design checkpoint on 2026-08-14. ADR 0078
fixes a closed Serving Record with one `rec_` plus 48-lowercase-hex ID and
exactly six required metadata strings. Registered JSON Schema Draft 2020-12
profiles may narrow values and byte ceilings but cannot add fields. Vectors,
dates, provenance, evidence, releases, grouping, and citations remain outside
the Pinecone record.

All contract JSON uses RFC 8785 JCS canonical UTF-8 bytes. Fingerprints are
SHA-256 encoded as `sha256:` plus 64 lowercase hexadecimal characters. The
Serving Payload Fingerprint hashes canonical `metadata` only and excludes the
register-issued ID. The authority-note fingerprint hashes the exact UTF-8 note
string. The Desired-State Inventory's record `content_fingerprint` now has this
exact serving-payload meaning.

The complete internal lookup uses one canonical manifest and one explicitly
declared, Search-Record-ID-sorted NDJSON shard for every selected Release
Scope. Every entry binds one record to its profile, Legal Item, Official
Versions, Legal Locations, Release Scope, Corpus Release, evidence references,
and authority-note decision. Even `"None"` has a decision binding. Empty
scopes have zero-byte shards, and unchanged shards may be reused in later
lookup revisions.

Promotion validation requires a perfect one-to-one join between the flattened
Desired-State Inventory and the complete lookup, exact profile, scope, release,
identity, evidence, note, count, order and fingerprint agreement, and two-run
reproducibility. Lookup-only corrections create new immutable affected shards
and a root revision without changing exact Serving Records or vectors.
Ask.Legal continues to perform no ordinary query-time lookup join.

## Settled known-stale legislation carry-forward

The user decided on 2026-08-14 that an official announcement of an operative
provision change must not make the latest applicable official HKeL wording
disappear merely because HKeL has not yet issued updated consolidated text.
ADR 0079 therefore creates `KNOWN_STALE_ANALYTICAL_CARRY_FORWARD`, and ADR 0081
allows its source copy to be verified or assisted.

For every affected location for which valid latest applicable official HKeL
text is held, the candidate release selects a new warned six-field payload
containing the exact unchanged `metadata.text`. A newer eligible assisted copy
is selected over an older verified copy. The mandatory English
`metadata.authority_note`
states that an official change is known, updated consolidated text is missing,
and the retained wording must not be presented as current or used to
reconstruct the change. A changed authority note means a new Search Record ID;
the exact text embedding may be reused only when the admitted embedding
contract is unchanged. Valid official text without a prior serving record may
be rendered into the warned payload through the ordinary gates. A location
without valid applicable official HKeL text produces no carry-forward record.

The event, affected-location evidence, Coverage Gap, record lineage, release,
and note decision remain fully traceable. Coverage status independently warns
the application and downstream LLM. When matching official consolidated text
later passes every gate, true current records replace the warned analytical
records and the gap is resolved. No arbitrary age cutoff removes the warned
records while the gap remains unresolved. ADR 0080 now makes reconstruction
the preferred eligible result; this known-stale mode remains its fallback and
does not enable general historical search or serving invalid records.

## Settled searchable reconstruction design

**Accepted decision:** ADR 0080 permits reconstructed legislation to be
searchable with explicit warnings when an official operative change is known
but updated official HKeL consolidation is unavailable.

**Replaced boundary:** ADR 0080 supersedes ADR 0023's prohibition. ADRs 0079
and 0081 now serve warned latest applicable official HKeL text only as the
fallback when exact reconstruction cannot pass.

**Accepted direction:** reconstruction is an ordinary legislation
record carrying one mandatory reconstruction warning, rather than as a
separate material or source-handling class. It is not an Official Version or
HKeL verified copy. Use the latest applicable bilingual official HKeL base,
supported by matching verified or assisted copies under ADR 0081, exact Gazette
or Editorial-Record change evidence, proved commencement and event ordering,
and separately applied English and Traditional Chinese operations. Construct
the final text deterministically from an enumerated supported-operation
rulebook. Unsupported location mapping, competing amendments, conditional or
partial effect, structural ambiguity, bilingual disagreement, or any failed
coverage proof must produce no reconstructed record and retain ADR 0079's
warned old text instead.

**Serving rule:** select one reconstructed Search Record per affected
serving unit rather than serving both old and reconstructed versions as
competing semantic results. Keep the old official record and all derivation
evidence outside the active selection. Apart from the mandatory English
reconstruction warning in `metadata.authority_note`, the record follows the
same legislation metadata type, Pinecone index, retrieval, ranking, source,
citation, quotation, and downstream handling rules as official legislation.
Do not create a separate material type, namespace, query path, source-treatment
rule, or quotation restriction. The reconstructed record's
`metadata.authority_note` itself must contain an explicit instruction that, if
the model uses the record in an answer, it must put the reconstruction warning
in that response. The application may also display the same warning; these are
two deliveries of the same warning, not separate source treatments. The Record
Traceability Lookup must bind the base Official Version, every amendment and
commencement artifact, ordered operations, reconstruction-engine and rulebook
versions, bilingual proof, and later official reconciliation.

**Approved warning:** the user requires the warning to explain that HKeL
had not yet published updated consolidated text incorporating the proved
operative amendments, and that the record is a reconstructed consolidation
made from the latest applicable HKeL copy and those proved amendments. The
approved controlled template is one stable string:

```text
[WARNING: RECONSTRUCTED CONSOLIDATION] As at [observation cutoff], HKeL had not yet published an updated consolidated copy incorporating the proved operative amendments affecting this provision. This record is a reconstructed consolidation using the latest applicable HKeL copy, version date [base version date], and the official amendment and commencement evidence identified in metadata.source, effective [effective date or exact applicability condition]. [INSTRUCTION: If you use this record to support any part of an answer, you must explicitly include the preceding warning in your response.]
```

The renderer fills only evidence-backed values, identifies multiple effective
dates or applicability branches rather than compressing them falsely, and
must not claim that HKeL is generally out of date. The cutoff-specific wording
states only that HKeL had not yet published the matching updated consolidation
at that proved time. The record otherwise uses the ordinary legislation source
and citation handling. The instruction is part of the same
`metadata.authority_note`; no separate downstream-model mechanism is designed
at this stage. Retrieval alone does not trigger the instruction. Using the
record to support any part of an answer does.

**Replacement and monitoring:** when HKeL later publishes the matching
applicable consolidation, compare it exactly with the derived result, replace
the reconstructed record with the ordinary HKeL record, and use every mismatch as
operation-class evaluation evidence. A material mismatch suspends the affected
reconstruction rule or operation class until corrected and re-admitted.

**Completed operation-registry checkpoint:** ADR 0082 now freezes eight closed
source-backed operation classes, exact instance inputs and preconditions,
ordering, atomic dependency-closure behavior, authentic-language execution,
unsupported-operation fallback, Reconstruction Plan and Execution Report
traceability, and stable result reasons. There is no catch-all or fuzzy patch.

**Completed reconstruction-conformance checkpoint:** ADRs 0083, 0086, and 0087
and the canonical catalogue freeze 32 evidence-to-plan cases, 31 plan-to-
artifact cases, 63 matching primary cells, and 35 controlled pairs. All are
mandatory. A reconstruction-enabled profile therefore has 184 direct Hong Kong
Legislation cases rather than the 121-case ordinary baseline alone.

**Completed Plan-and-Report checkpoint:** ADR 0084 fixes strict immutable JCS
JSON contracts, register-issued `rpl_`, `rop_`, `rex_`, and `rca_` identities,
complete event and effect bindings, dependency closure, authentic-language
streams, per-operation results, atomic zero-output failure, and the internal-
versus-serving boundary.

**Completed reconstructed-artifact checkpoint:** ADR 0085 fixes the immutable
eleven-role `rca_` package, complete authentic-language trees and source units,
reconstructed location units, derivation ownership for every byte and changed
relationship, bilingual and dependency proofs, identity-lineage result, and
ordinary-renderer boundary.

**Completed later-HKeL checkpoint:** ADR 0086 fixes scalable change-triggered
monitoring, ordinary HKeL priority, exact common-basis comparison, non-
isolatable additional-change behavior, mismatch attribution, smallest-safe-
scope suspension, impacted-record fallback, regression expansion, and safe
restart. It expands the reconstruction catalogue to 58 cases and 32 pairs.

**Completed readiness checkpoint:** ADR 0087 requires one exact immutable
`rcp_` capability profile, full mandatory conformance, independent `rct_`
attestation, active candidate-processing authority, runtime fingerprint checks,
and exact suspension handling. Candidate processing remains separate from
source, model, Approval, embedding, Pinecone, Azure, deployment, and routing
capabilities. The repository remains `DESIGN_ONLY`. ADR 0087 expands the
catalogue to 63 cases and 35 pairs.

**Exact next consequential design decision:** settle ADR 0043's LLM-versus-
deterministic allocation, particularly whether an admitted model may propose or
challenge structured Reconstruction Plans or extract Gazette event candidates.
This choice affects cost and trust and is therefore not being silently decided.
Executable schemas, fixture bytes, expected bytes, and implementation remain
separately unauthorized.

## Active signed coverage-status interface design

**Settled inputs:** ADR 0005 already requires visible gaps for carried-forward,
withheld, and no-rebuild outcomes. ADR 0009 already binds a baseline coverage
manifest into the immutable Serving State Definition. The canonical design
already requires coverage status outside Pinecone because missing records
cannot explain their own absence. ADRs 0050 and 0078 keep the downstream LLM's
ordinary legal context at the exact six metadata strings.

**Recommended structure:** one immutable signed Coverage Status Snapshot binds
one exact Serving State, predecessor snapshot, issue and expiry times, complete
Release Scope registry, every scope's last verified cutoff and current status,
every active Coverage Gap and public-safe explanation, and its canonical
fingerprint and signature profile. Append-only coverage activation events may
advance this snapshot without rebuilding Pinecone. A request pins both the
Serving State activation and one verified coverage snapshot for its full life.

**Recommended query behavior:** `VERIFIED_CURRENT` creates no warning context.
Carried-forward, partial withholding, bounded Quarantine, consolidation gaps,
and retained-old-target/no-rebuild states allow unaffected search to continue
but require an application banner and deterministic six-field coverage context
for the downstream LLM. That context is generated from the verified snapshot,
uses `metadata.type: "coverage_status"`, is neither indexed nor embedded, and
does not become a Search Record. If a query has no material-family filter, all
active gaps for the selected jurisdiction are included; no LLM or semantic
guess may suppress them.

An exact scope with no safe searchable state is blocked rather than answered
from misleading or absent material. Every mandatory applicable coverage notice
must fit; if it cannot, answer generation is blocked while the application
shows the gap directly. Normal gap publication and evidence-backed clearing are
deterministic and reported rather than waiting for routine human review.

**Open product decision:** if the coverage snapshot service fails and no
still-valid cached snapshot exists, the recommendation is to keep search
available but show and inject an unavoidable `COVERAGE STATUS UNAVAILABLE`
warning. The alternative is to refuse all affected-jurisdiction answers until
verification recovers. Silent continuation or indefinite trust in expired
status is rejected under either choice.

## Settled HKEX rule-component inventory contract

The user approved ADR 0069 on 2026-08-14. Every frozen Hong Kong Regulatory
Materials cutoff uses one immutable HKEX Rule Component Inventory Package with
separate Main Board and GEM results. The stable contract governs the inventory;
the changing live component list remains a versioned registry artifact.

The package's declared universe is bounded by exact Registered Source inventory
and reconciliation roles rather than an unbounded HKEX website crawl. Every
observed entry is classified as a rule component, evidence-only, excluded
non-rule material, or unresolved membership. Every accepted rule component is
owned by exactly one Main Board or GEM Legal Item. One source artifact may
support both, but it does not create one ambiguous cross-market component.

Membership and ownership remain separate from effective state, material
disposition, and processing outcome. Current, transitional-current,
future-fixed-date, future-conditional, superseded, withdrawn, and unknown
states remain distinct. A proposed non-rule item has no rule-component state.
`PASS` does not mean searchable: correctly excluded guidance may pass, while a
known current component with missing evidence is blocked.

Each package reports source-entry accounting, component ownership and
structure, current-state accounting, and serving readiness separately. A
complete inventory may expose Quarantine or blocked work and therefore remain
not ready to serve. Missing, duplicate, unowned, double-owned, orphaned,
silently skipped, or fingerprint-mismatched material invalidates the applicable
proof. Bounded board-specific failures remain isolated, while a shared
unbounded gap cannot be hidden through scope partitioning.

Inventory versions are cutoff-, predecessor-, source-, contract-, evidence-,
and fingerprint-bound. Moves, renames, renumbering, splits, merges, withdrawal,
disappearance, and reappearance create explicit observations and comparisons;
disappearance is not proof of legal withdrawal. Supported no change requires
every due source role, entry, and component to reconcile exactly and creates no
record, embedding, or Pinecone work merely to record silence.

## Settled lean HKEX Registered Source decision

The user approved ADR 0070 on 2026-08-14. Exactly five roles are ordinary
current-database inputs: `HK-REG-HKEX-RULEBOOK-CATALOGUE`,
`HK-REG-HKEX-CONSOLIDATED-RULEBOOKS`,
`HK-REG-HKEX-REGULATORY-FORMS`, `HK-REG-HKEX-FEES-RULES`, and
`HK-REG-HKEX-RULE-UPDATES`. URLs, languages, formats, update numbers, dates,
and filenames remain versioned endpoint or artifact facts rather than source
identity.

The five roles have narrow Fact Authorities. The catalogue bounds top-level
product families; consolidated rulebooks prove their contained prevailing
English wording and structure; Forms and Fees Rules prove their separately
published required English inventories, membership, and content; and final
updates prove assigned amendment, date, condition, transition, mapping, and
withdrawal facts. Optional Chinese translations remain non-serving support. An
update does not prove occurrence of an external condition or replace the
applicable current product. The complete inventory universe is the reconciled
union of all five roles, not one page, search count, navigation tree, or PDF
table of contents.

All five receive lightweight deterministic daily checks and require a complete
successful Observation within 24 hours of the weekly cutoff. Large artifacts
are acquired only after a trustworthy signal or when unchanged bytes cannot
otherwise be proved. Supported no change creates no LLM, embedding, record
rebuild, or Pinecone work.

The online Thomson Reuters rulebook is optional non-controlling discovery and
cross-check material rather than a release dependency. Precedence, language,
component-inclusion, exclusion, and the standing SFC approval framework are
pinned rulebook-basis evidence instead of separate routinely polled sources.
Guidance, consultations, FAQs, decisions, circulars, announcements, and general
pages receive an exact on-demand registration only when a real bounded decision
requires them.

There is no generic external-trigger source. Each conditional amendment names
an exact official source whose heightened monitoring obligation exists only
while the condition is live. Stale or unavailable evidence when the event may
have occurred makes the component unresolved. A final HKEX update, matching
current product, and pinned SFC framework may support
`APPROVAL_SATISFIED_BY_FINAL_PUBLICATION`; proposals, drafts, consultations,
and pending approvals may not.

Source material remains pipeline evidence. It is not automatically sent to the
downstream legal-analysis LLM or indexed in Pinecone. The LLM receives only the
approved six-field Search Record metadata selected for serving.

## Settled HKEX effective-state and transition rules

The user approved ADR 0071 on 2026-08-14. State is assessed for one exact
rule-component **applicability branch** at one frozen cutoff, not for a whole
update notice. A branch is the rule text plus the exact cohort, transaction,
reporting period, time window, or external condition to which it applies. One
update and one Legal Location may therefore have several simultaneous state
decisions.

ADR 0069's one inventory state per component is a derived summary rather than
a replacement for branch decisions. One ordinary current branch summarizes as
current; materially limited or concurrently current branches summarize as
transitional-current; a pending future amendment alone does not make its
ordinary predecessor transitional; and an unresolved fact that could change
what is current summarizes as unknown.

The evidence order is:

1. confirm rule-component membership and board ownership;
2. apply exact withdrawal, replacement, fixed-date, external-trigger, and
   transition evidence to each mapped branch;
3. reconcile the resulting branch with the controlling current prevailing
   English product; and
4. separately decide material disposition and `PASS`, `BLOCK`, or
   `QUARANTINE`. A legal-state label alone never authorizes serving.

The accepted state meanings are:

- `CURRENT`: effective at the cutoff for ordinary application, with no material
  special branch, and reconciled to the controlling current product;
- `TRANSITIONAL_CURRENT`: legally live at the cutoff only for an exact supported
  branch, including when old and new requirements concurrently govern different
  cohorts;
- `FUTURE_FIXED_DATE`: final published change whose exact effective date is
  later than the cutoff;
- `FUTURE_CONDITIONAL`: final published change whose exact external condition
  has not been proved to occur;
- `SUPERSEDED`: a supported successor now governs every former current
  application of the branch;
- `WITHDRAWN`: official evidence removes the branch for every current
  application without a supported successor for that same obligation;
- `UNKNOWN`: the state itself cannot safely be established because required
  timing, trigger, mapping, language, or current-product evidence is missing,
  stale, ambiguous, or conflicting; and
- `NOT_APPLICABLE`: permitted only for a non-rule entry.

A fixed date or proved trigger does not cause clock-only promotion. On or after
the effective point, the changed wording must reconcile with the controlling
current product. If the update says the change is effective but the product is
old or conflicting, the branch becomes `UNKNOWN` and is quarantined; the
pipeline does not reconstruct the rule. Before a future date, an early-posted
future product does not make the change current. A preserved and still-
supported predecessor may continue under ADR 0005 only as an explicit
last-approved carry-forward, never as newly verified current law.

Every decision binds one immutable cutoff timestamp. Calendar dates use the
Hong Kong calendar unless the controlling source expressly supplies another
time zone. Express times control, while ambiguous timing becomes `UNKNOWN`
rather than receiving invented precision.

For a conditional change, positive trigger evidence is required. A condition
may remain `FUTURE_CONDITIONAL` only while its exact official trigger source is
fresh enough to support non-occurrence. If the event could have happened and
that evidence is stale or unavailable, the result is `UNKNOWN`. All-of
conditions require every condition; any-of conditions require one proved
condition to activate and positive non-occurrence of all alternatives to
remain future.

Transitions preserve every concurrently live branch. Different operative
wording or obligations produce separate current Search Records; the same
wording with one simple applicability condition may remain one record with the
condition in `metadata.text`. A material branch or reliance limitation may
also use the controlled English `metadata.authority_note`; otherwise that
field remains `"None"`. An old branch is not globally superseded while any
supported cohort still uses it. Open-ended transitions remain live until exact
official evidence or provable cohort exhaustion ends them; the pipeline does
not guess.

Serving disposition remains separate: current and transitional-current
branches may be searchable only after all other gates pass; future branches go
to the Waiting Room; superseded and withdrawn branches remain historical;
unknown branches go to Quarantine; and non-rule entries produce no regulatory
Search Record. Technical source failure without affirmative change evidence
uses ADR 0005's explicit carry-forward, withhold, or no-rebuild decision rather
than pretending that an old record was freshly verified.

Verified official examples informing the decision are HKEX Update 153, whose
parts use different fixed dates and include issuer/guarantor transitional
arrangements; Update 152, whose parts combine two separate external triggers
with one fixed date; and Update 150, whose effective change still distinguished
new applicants from existing issuers. These examples demonstrate why update
number, publication date, and one update-wide state are insufficient.

## Settled HKEX English-only serving contract

The user approved ADR 0072 on 2026-08-14. Each Hong Kong Regulatory Materials
Search Record contains the complete prevailing English HKEX rule text and
English applicability context only. It contains no Chinese source block,
Chinese-only duplicate, parallel Chinese vector, or machine-generated Chinese
source text. This change is specific to Regulatory Materials; it does not
alter bilingual Hong Kong Legislation.

The applicable English consolidated rulebook, Regulatory Form, Fees Rule, and
final update evidence remain mandatory. Missing or conflicting English cannot
be repaired with Chinese, a warning, the online rulebook, similarity, or LLM
translation. Optional official Chinese translations may be preserved outside
Pinecone for terminology, evaluation, investigation, audit, and possible
future design. They are not ordinary release dependencies and do not change a
Search Record merely by changing.

A Chinese discrepancy is non-blocking unless it positively exposes a possible
English identity, version, effective-state, wording, or completeness defect.
In that case the English controlling decision is investigated; Chinese does
not become a competing wording authority.

English-only serving requires a pinned multilingual retrieval workflow to pass
complete Traditional-Chinese and mixed-language query evaluation. The
downstream LLM may explain the controlling English rule in Chinese, but it may
not claim that its explanation is HKEX's official translation or fabricate a
Chinese quotation. Failed Chinese-query gates block serving and return the
design for an explicit official-Chinese retrieval-aid or bilingual decision;
they do not authorize silent extra fields, duplicates, or vectors.

ADR 0073 later fixes how that English text is turned into exact records.

## Settled HKEX English record-construction contract

The user approved ADR 0073 on 2026-08-14. Every current or transitional-current
applicability branch uses the smallest complete official English rule-bearing
unit that is independently usable with its required governing context.
`Complete` means that unit is uncut and keeps its qualifications; it does not
force every subrule sharing one number into every record. Ordinary rules,
definition entries, lists, notes, Practice Notes, appendices, tables, Fees
Rules, and Regulatory Forms use class-specific official boundaries. Separate
normal units are not packed merely to fill an embedding budget.

Each record repeats only the minimum exact governing context needed for correct
use, such as a grammatical lead-in, local scope, attached note, table header,
Form instruction, fee basis, or transition condition. Global definitions
remain separately searchable. Cross-references preserve the referring words,
exact target locator, and eligible official heading but do not recursively
copy target rule text. An unsafe child remains with a larger official parent or
is quarantined when no faithful unit can fit.

The canonical renderer labels material, market, component, exact location,
optional official heading, material effective context, and serving part. It
then includes optional required-governing-context and referenced-location
blocks and the complete prevailing English primary block. Closed source-
faithful projections preserve tables, Fees Rules, Forms, blank controls, and
meaningful notes while excluding Chinese, generated summaries, URLs, page
furniture, internal IDs, operational dates, reviewer prose, and model output.

Exact fit uses the complete final `metadata.text` and all six metadata strings,
including real part labels and `authority_note`, against separately pinned
embedding-token and metadata-byte ceilings. An overlong unit descends only
through official English structure and uses the fewest valid consecutive
parts, filling each earlier part as fully as possible. Page, sentence,
punctuation, character, token-position, visual, and sliding-window cuts are
forbidden unless independently official semantic boundaries. An indivisible
overlong branch is quarantined with a Coverage Gap rather than truncated.

Every result carries one immutable HKEX English Source-Unit Coverage Proof.
Every meaning-bearing current unit has one primary owner or an explicit blocked
or quarantined outcome; repeated dependencies point to that owner; and
context-only, presentation-only, future, historical, and excluded units remain
separately accounted. Complete accounting does not make a scope serving-ready
when a required current unit is blocked or quarantined.

ADR 0075 now freezes the exact Regulatory catalogue, ADR 0076 the semantic
task allocation, and ADR 0077 multilingual retrieval and downstream-answer
admission. No high-level Regulatory design task remains open.

## Settled Legal Desk meaning and boundary

The user requested an exact explanation on 2026-08-14. A Legal Desk is the
named logical decision authority for one jurisdiction-and-material pair. It is
not a human-review queue, LLM, virtual lawyer, source connector, renderer, or
promotion service. One accountable Legal Desk Owner governs its coverage,
Source Rulebook, reference decisions, and review triggers, but fully resolved
ordinary work may be accepted automatically under the written rules.

The Desk receives preserved evidence, structured source facts, prior register
state, and any permitted evidence-bound proposal. It applies one immutable
active Source Rulebook, confirms permitted Fact Authorities and evidence
completeness, records established and unresolved facts and an ordered Rule
Trace, and emits one immutable Legal Desk Decision containing the permitted
membership, identity, legal state, disposition, processing, coverage, record-
eligibility, authority-note-meaning, and review consequences. Missing rules,
evidence, or unresolved conflict produces an exact blocked or Quarantine path;
the Desk cannot invent a result.

The Desk does not acquire or change source evidence, alter its rulebook during
a decision, treat model confidence as authority, render final bytes, issue
Search Record IDs, construct releases, approve promotion, deploy, or hold
source, model-provider, Pinecone, Azure, backup, routing, or production
credentials. Deterministic downstream modules consume the accepted decision.
The authenticated promotion reviewer remains a separate authority.

## Settled HKEX Regulatory conformance architecture

The user approved ADR 0074 on 2026-08-14. One immutable `hk-regulatory`
conformance suite contains two linked but non-substitutable catalogues and one
frozen coverage matrix. The evidence-to-decision catalogue proves that complete
synthetic source-shaped evidence produces the correct structured Legal Desk
result. The decision-to-artifact deterministic catalogue begins from frozen
accepted facts and proves exact canonical records, authority notes,
measurements, partitions, source-unit coverage, traceability, identity,
readiness, failures, and forbidden-side-effect artifacts. Retrieval remains a
later independent gate.

ADR 0076 now separately settles the high-level LLM-versus-deterministic
allocation. Proposal components receive only ordinary evidence and task inputs,
never case IDs, coverage labels, pair roles, expected answers, or adjudication.
The Regulatory Legal Desk owns hidden structured reference results; exact final
artifacts remain deterministic.

Strict `suite.json`, `coverage-matrix.json`, `decision-catalogue.json`, and
`deterministic-catalogue.json` manifests explicitly bind every case, contract,
artifact, path, role, and SHA-256 fingerprint. Package-local normalized paths,
closed schemas, `EXACT`/`NONE`/`NOT_APPLICABLE` artifact roles, deliberate-
absence declarations, and no-glob, no-network, no-undeclared-file rules prevent
silent incompleteness and answer leakage.

The coverage matrix rather than a chosen count proves completeness. Every
required cell has a direct primary case, every case owns a cell, every stable
rule and result branch has direct coverage, and every high-risk boundary has a
positive and near-miss pair. Critical errors cannot be averaged away. Two
isolated deterministic runs must produce identical artifacts and fingerprints,
and a separate conformance attestation binds one exact suite, rulebook,
processing build, dependency lock, runner, and complete passing result set.

The user approved the scalable case-selection method on 2026-08-14. Direct
branch cases, both sides of high-risk boundaries, and direct mechanical failure
cases are exhaustive within the accepted conformance universe. Combined cases
are added only when interaction can change the result; the catalogue does not
multiply every independent fact against every other fact. A combined case can
add secondary proof but cannot substitute for a missing direct primary case.

ADR 0075 now freezes the audited canonical catalogue at 284 direct cases and
matching primary cells, divided `62/51/30/35/24/20/24/38`, with 57 exact high-
risk pairs. The 143 evidence-to-decision and 141 deterministic rows cover every
accepted ADR branch and critical-error family without a Cartesian product.
Every row, result, primary cell, pair role, and membership is immutable.

## Settled HKEX Regulatory semantic task allocation

ADR 0076 accepts four change-gated tasks:
`hk-regulatory-update-analysis`, `hk-regulatory-update-challenge`,
`hk-regulatory-record-analysis`, and `hk-regulatory-record-challenge`.
Supported no change stops before model work. Deterministic admission and fast
paths resolve source-explicit facts; update tasks propose evidence-bound change,
date, trigger, cohort, transition, and lineage mappings; record tasks propose
semantic units, governing dependencies, references, and table, fee, and Form
relationships. Separate challenge passes test omissions and unsafe proposals.

The Legal Desk remains the rulebook executor and decision authority. Complete
ordinary work may auto-accept only after both passes, deterministic validation,
one exact rule path, conformance admission, and no review trigger. Human review
is reserved for exact ambiguity, conflict, novel structure, missing rule
coverage, or another written trigger. State, rendering, notes, measurement,
partitioning, coverage, identity, release, embedding, promotion, Pinecone,
Azure, and deployment remain outside generative-model authority. Exact task
contracts and sealed real-source admission evidence remain unimplemented.

## Settled HKEX multilingual retrieval and answer admission

ADR 0077 requires separate multilingual retrieval, frozen-context downstream-
answer, and complete query-path evaluations. The immutable profile binds exact
English, Traditional-Chinese, and mixed-language queries and judgments; corpus,
embedding, Pinecone-compatible retrieval, Ask.Legal Query Contract and build,
downstream model and prompt; per-slice gates; critical errors; repetitions; and
monitoring and revalidation rules.

Retrieval must find all required English records within the real context budget
without wrong-board, state, family, or guidance crowding. The downstream model
receives only six metadata fields, follows `authority_note`, preserves English
legal meaning in Chinese explanation, and neither claims official-translation
status nor fabricates Chinese source quotations. Every active path must pass
the note unchanged. Aggregate scores cannot hide mandatory slice or critical
failures.

Exact executable query sets, relevance judgments, models, thresholds, and run
results remain future artifacts. If supported English-only candidates later
fail mandatory Chinese or mixed-language gates, serving remains blocked and a
genuine user choice then arises between a compact official-Chinese retrieval
aid and full bilingual serving. No redesign is chosen without that evidence.

## Settled Case Proposition evaluation packages and admission profiles

The user approved ADR 0068 on 2026-08-14. The decision defines future
executable package contracts but creates no executable artifact and authorizes
no evaluation.

### Non-circular admission evidence

Case Proposition admission binds four immutable objects in order:

1. the **Evaluation Suite Package** defines candidate-independent cases,
   protected truth, evaluator, fixed gates, and completeness;
2. the **Workflow Admission Profile** freezes one exact candidate workflow and
   evidence-derived values before sealed scoring;
3. the **Evaluation Run Set** preserves the full case-by-repetition execution
   and all results for that exact suite and profile; and
4. the final **Workflow Admission** binds those objects and separate Hong Kong
   Cases Legal Desk and system-owner attestations.

The suite does not contain candidate outputs or an admission decision. The
profile does not depend on its sealed run results. The run set cannot change
the suite, profile, or evaluator. The admission record refers to all three
without creating a fingerprint cycle.

Every future package uses one pinned canonical JSON serialization, declared
artifact inventory, SHA-256 content fingerprints, immutable paths or external
object references, and strict schemas. Directory discovery, globs, mutable
aliases, counts, or an undeclared file cannot prove completeness. Secrets and
key values remain outside packages.

### Protected evidence and honest sealing

Every semantic case has three permissioned views:

- model-facing input contains exactly the legal identity, original source
  evidence, Coverage Units, ranges, dependencies, and task fields that ordinary
  runtime receives;
- evaluator reference contains the hidden Reference Proposition Map, required
  and forbidden meanings, permitted equivalents, exact evidence, slices,
  pairs, critical labels, and scoring assertions; and
- adjudication evidence records legal mapping, independent review,
  disagreements, resolution, freeze, correction, and supersession.

The model necessarily sees the real case name and citation when ADR 0066
requires them. It never sees the evaluation ID, human test label, selection
cell, pair role, expected result, map, critical label, score, or admission
state. Complete real judgments, exact sealed membership, maps, adjudications,
raw outputs, and case-level results stay in protected registered storage
outside Git.

“Sealed” does not claim a public judgment was absent from provider training.
It means exact set membership, evaluator truth, adjudication, and case-level
results are hidden from the task and ordinary developers. A disclosed sealed
case loses pristine admission and canary eligibility, triggers an incident,
impact review, package replacement, and affected re-evaluation, and may remain
only as a regression case.

### Real-judgment selection and maps

The Hong Kong Cases Legal Desk and evaluation owner freeze an exact branch-
driven selection matrix before inspecting candidate sealed results. Every
required cell has a primary real judgment, and every selected judgment owns at
least one primary cell. Counts or many similar easy cases cannot substitute.

The matrix directly covers every in-scope court family, original English,
Traditional Chinese and mixed language, material opinion structures, short and
segmented judgments, source-format and evidence forms, zero/one/many results,
materiality, qualifications, independent grounds, adoption, treatment-only
work, Quarantine, blocked work, and safely adjudicable critical and high-risk
branches. Synthetic cases retain malformed, hostile, impossible, leakage, and
exact mechanical branches that real law should not be distorted to reproduce.

Cases used to tune, demonstrate, debug, or select the candidate workflow or
threshold profile are `DEVELOPMENT` and cannot count for admission. Protected
cases use `SEALED_ADMISSION`, `SEALED_CANARY`, or `REGRESSION` roles with a
reserve for versioned replacement. Developers receive aggregate dimension and
slice diagnostics rather than protected case identities, maps, or canary
rotation.

The primary mapper freezes a Reference Proposition Map without seeing
candidate outputs. High-risk, critical, contestable, plurality, uncertain-
attribution, and alternate-boundary maps require independent second legal
review. An unresolved reference makes the evaluator blocked. An unlisted
possible equivalent cannot receive an ad hoc pass: blinded adjudication either
rejects it or creates a new map and suite version followed by equal affected
reruns.

### Evaluator, runs, thresholds, and admission

The evaluator applies package preflight, execution integrity, deterministic
conformance, semantic comparison, and gates in that order. It records explicit
produced-to-reference proposition matching and every dimension and slice's
numerator, denominator, aggregation rule, and case contribution. An
uncontrolled evaluator LLM cannot define truth or admission.

Every required execution ends in exactly one state:

- `PASS` — applicable assertions passed;
- `FAIL` — a validly evaluated wrong or unsafe workflow result;
- `INVALID_RUN` — package, binding, infrastructure, or execution integrity
  prevented valid evaluation;
- `EVALUATOR_BLOCKED` — reference truth or evaluator support could not decide;
  or
- `NOT_RUN` — the declared execution did not occur.

Only `PASS` satisfies a repetition. Invalid runs preserve every attempt and
may repeat only under the same frozen identity and attempt rules. Evaluator-
blocked cases require a versioned correction and equal affected reruns. A
not-run case makes the set incomplete. The final run-set result is
`ELIGIBLE` or `NOT_ELIGIBLE`; eligibility permits only the two admission
attestations and grants no production authority.

The profile serializes but cannot weaken ADR 0067's 132-case and sealed-real
completeness, two deterministic runs, three ordinary and five high-risk
semantic repetitions, all-repetition high-risk gate, zero-critical-error rule,
separate dimensions and slices, 20% context reserve, bounded attempts, cost
reservation, canaries, periodic suites, suspension, or restart rules.

Every other profile value must carry its unit, scope, measurement method,
evidence, sample and period, estimator, uncertainty or margin, owner, and
rationale. It freezes before sealed scoring. Small slices use exact per-case or
per-distinction gates instead of misleading percentages. A threshold cannot be
lowered after viewing a failure just to pass that candidate; a changed profile
is a new candidate and must run the complete applicable suite.

The final admission requires matching suite, profile, run set, Legal Desk
attestation, and system-owner technical and operational attestation. Neither
role may waive a failed or missing gate. This admission remains separate from
human Approval of a production Promotion Manifest.

## Settled Hong Kong Case Proposition output and evidence

The user approved this contract on 2026-08-13. ADR 0060 is normative.

### Plain-language rule

One searchable Case Proposition record should contain **one legal answer from
one attributed judicial reasoning path**, together with the minimum facts,
issue, limits, application, result, and exact judgment words needed to
understand and verify that answer without opening the full judgment.

A proposition is material when it could help answer a later legal question and
the judgment uses, establishes, materially explains, or materially qualifies
it. Material does not mean novel. A familiar rule may still be material when
it genuinely resolves a live issue in the case. A sentence is not material
merely because it contains legal language or cites another case.

One judgment may correctly produce:

- zero records when it contains no distinct material legal proposition;
- one record when one self-contained legal proposition matters; or
- several records when it decides several independently searchable legal
  issues or establishes several independently usable propositions.

The system must not create a whole-case overview record, one record per
sentence, a duplicate record for an official translation, or a proposition
invented merely to anchor later treatment.

### Accepted qualification test

A candidate qualifies only when all of the following are true:

1. the legal issue or question is identifiable;
2. the judgment supplies an identifiable legal answer, test, standard,
   interpretation, burden, exception, or other legally usable conclusion;
3. the exact opinion and authority role are known, including whether the
   reasoning is joint or majority reasoning, adopted reasoning, a concurrence,
   dissent, plurality position, obiter discussion, or another precisely
   attributed form;
4. exact source passages support the proposition and every material
   qualification stated in the record;
5. the minimum facts, procedural posture, and result needed to understand the
   proposition's scope can be stated without speculation;
6. the proposition can stand as one honest searchable unit without blending
   separate opinions or collapsing distinct rules; and
7. no unresolved source, version, opinion, support, or attribution conflict
   makes the record unsafe.

Procedural chronology, party submissions, quotations not adopted by the
court, bare citations, issue-free fact findings, outcome-only statements,
administrative directions, and repeated legal wording that does no material
work in the reasons do not qualify by themselves.

### Accepted `metadata.text` layout

The six-field serving envelope does not change. `metadata.type` remains
`"case"`, and `metadata.authority_note` remains a separate required string.
The accepted contract affects the content rendered inside `metadata.text`
only.

Each proposition text uses a stable labelled layout containing:

1. **Case** — case name and official citation;
2. **Court and decision date** — enough to identify the deciding authority;
3. **Opinion and authority role** — exact opinion attribution and whether the
   proposition is operative majority or joint reasoning, adopted reasoning,
   concurrence, dissent, plurality, obiter, or another supported role;
4. **Legal issue** — the narrow question answered by this proposition;
5. **Proposition — derived statement** — a concise source-faithful statement
   of the legal answer, visibly labelled as a derived statement rather than a
   quotation from the court;
6. **Material context** — only the facts and procedural posture necessary to
   understand when the proposition applies;
7. **Qualifications or exceptions** — every source-supported limit needed to
   prevent the proposition from being broader than the judgment;
8. **Application and relevant result** — how this reasoning affected the issue
   and the result relevant to this proposition; and
9. **Exact judgment support** — the smallest complete set of verbatim original-
   language passages, with stable paragraph or passage locators, that proves
   the derived statement, limits, application, and authority attribution.

Empty optional sections should use one versioned renderer rule rather than
free-form filler. The renderer must never say that no qualification exists
merely because an extractor failed to find one.

The derived statement and exact support should both reach the downstream LLM.
The derived statement makes retrieval and comprehension practical; the exact
passages let the model check what the court actually said. Because the user has
fixed the downstream boundary to Pinecone metadata only, keeping all exact
support solely in the Record Traceability Lookup would be insufficient.

The full judgment, all source artifacts, complete opinion and passage map,
translation artifacts, fingerprints, extraction proposal, validation and
review history, internal identities, and non-selected context remain outside
Pinecone in the Management Register and Evidence Vault. `metadata.text` carries
the minimum complete legal content, not the entire evidential dossier.

### Accepted one-record boundary

Keep a multi-element legal test in one record when its elements work together
as one rule. Split records when propositions answer different legal questions
or can be applied independently. Do not split a qualification or exception
away from the rule it limits merely to make shorter vectors.

One record may cite several non-contiguous passages from the same attributed
reasoning path. It may not combine a majority proposition with a dissent's
different reasoning. Express adoption must be preserved exactly. A later
judgment that merely says it agrees with an earlier case, without stating a
self-contained legal proposition of its own, need not create a duplicate Case
Proposition; the Later Treatment relationship can record that following or
approval.

### Accepted uncertainty and complete-coverage behavior

The complete accepted judgment and every identified opinion must be accounted
for. Long judgments may be processed in opinion-aware, structure-preserving
parts with a coverage ledger, but no method may silently truncate the source.
Each part must end in an accounted result: candidate proposition support,
non-propositional material, a cross-reference to context examined elsewhere,
or a named blocked or quarantined condition.

If the evidence supports no material proposition, record a valid zero-record
decision after complete review. If a material proposition may exist but its
meaning, scope, opinion, support, or attribution is unresolved, preserve the
candidate in Quarantine. Do not call uncertainty a valid zero-record result,
and do not publish a guessed proposition.

### Allocation boundary

This accepted contract defines the required result independently of how it is
produced. It does not decide whether candidate discovery, proposition wording,
or materiality analysis is performed by deterministic code, a generative LLM,
the Legal Desk, a human, or a defined combination. ADR 0043 initially deferred
that allocation; ADR 0065 later settles the staged two-pass hybrid. That
allocation must satisfy this same evidence, coverage, attribution, uncertainty,
and serving contract.

## Settled Hong Kong Case Proposition split and merge rules

The user approved this contract on 2026-08-13. ADR 0061 is normative.

### Plain-language rule

First decide how many genuine legal propositions the judgment contains. Only
after that should the system measure record size. Token limits must never
decide legal meaning.

The default rule is:

- **split** when two legal answers could be searched, stated, or applied
  independently; and
- **keep together** when removing one element, condition, exception, or piece
  of context would make the remaining statement incomplete or misleading.

Merge repeated or fragmented expression of the same proposition only when the
legal answer, issue, scope, opinion, and authority role are the same. Do not
merge merely because wording or topic is similar.

### Conceptual split test

Create separate Case Propositions when any of these conditions applies:

1. the judgment answers different legal questions;
2. either answer can govern a later case without the other;
3. the answers use materially different legal tests, burdens, standards,
   statutory interpretations, exceptions, remedies, or jurisdictional rules;
4. the answers arise from different opinions or different authority roles;
5. the judgment gives independent alternative grounds, each sufficient to
   support the relevant result; or
6. one application establishes a materially distinct legal branch rather than
   merely applying the same rule to another fact.

Do not split merely because the judgment uses several paragraphs, headings,
citations, steps, examples, parties, factual findings, or applications.

### Integrity test — what must stay together

Keep the following in one proposition when they operate as one rule:

- the elements of one cumulative or balancing test;
- a rule and the exception, proviso, threshold, definition, burden, or
  qualification that controls its meaning;
- a general statement and the application needed to show what the court
  actually decided;
- a proposition stated in one passage and narrowed or clarified later in the
  same reasoning path; and
- non-contiguous passages needed together to prove one complete answer.

The pipeline must not publish the earlier broad wording as one proposition and
the later qualification as another when the judgment itself makes the latter
limit the former. That would create a broader rule than the court expressed.

### Repetition and same-opinion merging

When the same opinion repeats, paraphrases, or applies the same proposition
several times with the same legal scope, create one record. Select the smallest
complete non-repetitive set of exact supporting ranges and preserve every
other occurrence in the internal evidence and coverage ledger.

Several fragments in the same opinion may merge into one proposition when one
states the rule, another supplies its qualification, and another shows its
application. Different wording does not prevent merging when the legal answer
is truly the same. Identical wording does not justify merging when the issue,
scope, authority role, or legal effect differs.

A general rule and a fact-specific application normally remain one record.
Create another application-specific proposition only when the judgment makes
that application an independently usable legal conclusion or a distinct branch
of the rule. Mere repetition on a second set of facts creates no new record.

### Multi-opinion judgments

Opinion boundaries are legal boundaries, not formatting boundaries:

- one joint or lead opinion joined by other judges produces one proposition
  record per genuine proposition, not one duplicate per judge;
- a judge who says only that they agree creates no duplicate proposition;
- a concurrence or dissent may produce its own material proposition, but it
  remains a separate record with that authority role stated prominently in
  `metadata.text`;
- additional reasoning in a partial concurrence is separate from the exact
  lead reasoning that the judge adopted;
- separate opinions reaching the same result are not merged merely because
  their wording or outcome overlaps; and
- a plurality without one expressly supported common reasoning path is not
  rewritten into a synthetic majority proposition. Each qualifying position
  remains separately attributed, and unresolved current authority is
  quarantined at the smallest safe boundary.

One record may use passages from another opinion within the same delivered
judgment only when the operative opinion expressly adopts those exact reasons
and the adopted scope is clear. The record must include both the adopting
passage and the adopted support and label the attribution accurately. Similar
reasoning, silence, shared outcome, or inferred agreement is not adoption.

When a later separately delivered judgment merely adopts, follows, or approves
an earlier judgment without restating a self-contained proposition, it creates
Later Treatment rather than a duplicate proposition. If it independently
states and applies a complete proposition, that later proposition may qualify
on its own evidence while the treatment relationship is recorded separately.

### Independent and alternative grounds

Independent grounds become separate propositions. For example, if an appeal is
dismissed both because it was filed out of time and because the substantive
claim fails under a distinct legal test, the limitation or procedural ground
and the merits ground are independently searchable legal answers.

A statement made only on an assumed, hypothetical, or unnecessary basis is not
represented as an operative holding. It may qualify separately only when it is
material under ADR 0060 and its obiter or hypothetical role is explicit.

### Shared context without a case-overview record

Each record repeats only the smallest context needed to stand alone. Several
propositions from one judgment may therefore repeat a short case identifier or
material fact, but they do not copy a large common factual narrative. There is
no context-only record and no whole-case overview that the downstream LLM must
retrieve alongside the proposition.

The internal register may group records by judgment and issue for processing,
audit, and retrieval-quality evaluation. That grouping does not create another
vector or a new Pinecone metadata field.

### Overlong propositions

The system first applies the legal split test and renders every genuine
proposition under ADR 0060. It then measures the exact final `metadata.text`
with the pinned embedding tokenizer and measures the complete six-field
metadata payload against the pinned byte ceiling.

When a record is too large, the permitted order is:

1. remove only genuinely optional and repetitive context under the canonical
   renderer;
2. use only the smallest complete non-repetitive exact source ranges, with
   every omitted range remaining internally preserved and no invisible
   alteration inside a quotation;
3. shorten the derived wording only when the complete legal meaning and every
   material qualification remain exact and the new wording passes the full
   proposition contract again; and
4. split only if the legal analysis proves that the candidate actually
   contains independently usable propositions.

If one indivisible, fully supported proposition still exceeds a hard limit, it
enters Quarantine with a Coverage Gap. The pipeline does not create arbitrary
token, sentence, paragraph, or evidence fragments; it does not create several
records that require a query-time join; and it does not omit a qualification,
application, result, authority role, or necessary exact support merely to fit.

The separate authority-note budget rules still apply. A mandatory warning is
never shortened away to make an overlong proposition fit.

### Initial extraction versus correction lineage

When the first extraction correctly finds several propositions, they are
independent initial records and do not need artificial split lineage.

If later review shows that one existing record improperly combined several
propositions, stop selecting it and create or select the supported separate
records with `split_from` processing-correction lineage. If several existing
records improperly duplicate or fragment one proposition, stop selecting them
and create or select one complete record with `merged_from` processing-
correction lineage.

This is a correction to pipeline output, not judicial treatment. All old
records, evidence, release history, and selection events remain preserved.
A newly discovered proposition has no invented predecessor. An official
corrected judgment instead follows ADR 0014: re-evaluate every proposition
whose support, context, attribution, or boundary changed, reuse exact
unaffected records only with proved continuing support, and create the
required new immutable records and lineage for affected payloads.

### Allocation boundary

These rules define the required legal and serving result independently of the
technology that finds it. ADR 0065 later settles the staged hybrid extraction
allocation; that workflow must produce the same split, merge, evidence, size,
coverage, uncertainty, and lineage outcomes.

## Settled Hong Kong Case Proposition Coverage Ledger

The user approved this contract on 2026-08-13. ADR 0062 is normative.

### Plain-language purpose and limitation

The Coverage Ledger is the checklist and reconciliation proof for one exact
official judgment version. It answers:

> Did the pipeline account for every opinion and every part of the accepted
> original judgment, and can every proposition result be traced to exact
> source material?

It prevents silent truncation, skipped opinions, unaccounted footnotes, and a
bare “the model found nothing” result. It does **not** prove by arithmetic alone
that every semantic decision was correct. A system may consistently label
every paragraph and still misunderstand one. Semantic accuracy therefore also
requires the later extraction evaluations, conformance cases, runtime
uncertainty behavior, and correction monitoring.

The ledger remains internal. It creates no Pinecone vector or metadata field
and is not read by Ask.Legal during an ordinary query.

### One immutable ledger identity

Create one immutable, fingerprinted ledger result for one exact combination
of:

- Judicial Decision and Official Version identities;
- accepted original judgment artifact fingerprints;
- complete opinion and judge-attribution inventory;
- parser and structural-normalization contract;
- source rulebook and observation cutoff;
- Case Proposition output, boundary, and renderer contracts;
- extraction task or decision contract used, without assuming whether it is
  deterministic, LLM-assisted, Legal Desk, or human;
- processor build and, when applicable, model, prompt, and settings identities;
  and
- resulting candidate, proposition, and ledger fingerprints.

Any result-affecting source, parser, structure, extraction, model, prompt,
rulebook, or proposition-contract change creates a new ledger result or
requires an explicit impact decision. It never mutates the accepted earlier
ledger. Optional Judiciary translations remain auxiliary linked evidence and
do not replace or redefine original-language coverage.

### Exhaustive original-source inventory

Before semantic analysis, deterministic structure processing creates an
ordered exhaustive inventory of the accepted original artifact. It includes:

- every identified joint, majority, lead, adopted, concurring, dissenting,
  plurality, court, or other opinion;
- every numbered and unnumbered paragraph;
- opinion headings and subheadings;
- footnotes and endnotes;
- lists, tables, quoted blocks, orders, dispositions, schedules, and
  appendices; and
- cover, appearance, administrative, or other source material that may later
  be classified as non-propositional but cannot be silently absent.

Each Coverage Unit records its register-owned Legal Location where available,
source locator or canonical fallback span, opinion ownership, source order,
original language, exact normalized text fingerprint, and mapping back to the
preserved source artifact. Visible paragraph numbers and byte positions are
locators and evidence, not permanent legal identity.

If the parser cannot enumerate or faithfully map the complete artifact, the
ledger is `BLOCKED`; it cannot proceed by covering only the parts the parser
understands.

### Segmentation and dependency accounting

A judgment that fits one processing packet still receives the full unit
inventory and ledger. Context-window fit is not a substitute for coverage
proof.

When segmentation is required:

- segments stay within one opinion for their primary content;
- every Coverage Unit belongs to exactly one segment as primary content;
- the union of primary segment inventories equals the complete ordered source-
  unit inventory exactly, with no omission, duplication, or reordering;
- a segment may repeat a unit only as an explicit context dependency;
- every repeated dependency points to its one primary unit and exact
  fingerprint and does not count as primary coverage again;
- cross-references, defined terms, earlier tests, qualifications, reasons,
  and dispositions required to understand a segment become recorded
  dependencies rather than assumed context; and
- no segment may end through silent truncation.

An adoption path across opinions is represented by an explicit dependency and
the exact adoption evidence required by ADR 0061. It does not merge primary
opinion inventories or infer agreement.

### Unit resolution and evidence roles

Every Coverage Unit receives exactly one final resolution state:

- `RESOLVED` — the entire unit was accounted for;
- `QUARANTINED` — existing evidence or semantic interpretation remains
  materially conflicting or unsafe; or
- `BLOCKED` — required text, structure, dependency, or processing support is
  unavailable.

Every `RESOLVED` unit then has exactly one primary use:

- `PROPOSITION_EVIDENCE` — it supports one or more accepted Case
  Propositions;
- `CONTEXT_EVIDENCE` — it supplies necessary facts, procedure, attribution,
  or result for a proposition but is not itself a legal answer; or
- `NON_PROPOSITIONAL` — it was examined and supports no Case Proposition.

A proposition-evidence unit may link to several propositions and may carry
several exact evidence roles, such as legal issue, derived answer,
qualification, application, result, authority attribution, selected exact
quotation, or supplementary supporting occurrence. Mixed content is not
hidden: the exact linked ranges and roles show which words support which
proposition. Repeated supporting language remains `PROPOSITION_EVIDENCE` with
a supplementary role even when it is omitted from the minimum serving text.

Every `NON_PROPOSITIONAL` unit requires a stable reason family, such as source
scaffolding, procedural or factual narrative not used as proposition context,
unadopted party position, unadopted citation or quotation, outcome without a
legal answer, agreement-only opinion, non-material discussion, or treatment-
only reasoning. Exact machine reason codes remain later schema work.

`TREATMENT_ONLY` is not a discard code. It must link to the separate citation
and treatment-screening inventory so a judgment with no proposition of its own
can still affect an earlier proposition.

### Candidate accounting

Every candidate proposition discovered by any permitted method receives one
final outcome:

- accepted as one Case Proposition;
- rejected as not satisfying ADR 0060, with an exact reason;
- merged into another candidate under ADR 0061;
- split into identified candidates under ADR 0061;
- quarantined; or
- blocked.

No candidate may disappear between discovery and final output. Each accepted
proposition links back to all required issue, answer, context, qualification,
application, result, attribution, and exact-quotation evidence roles. Every
serving record links to an accepted proposition and the exact ledger
fingerprint. Orphan records, orphan candidates, and unsupported renderer
sections invalidate the result.

### Exact completeness arithmetic

A structurally valid ledger proves all of the following:

1. the expected opinion inventory equals the covered opinion inventory;
2. every expected Coverage Unit occurs exactly once in primary segment
   coverage and in original source order;
3. every dependency resolves to one covered primary unit and exact
   fingerprint;
4. every unit has exactly one resolution state;
5. every resolved unit has exactly one primary use;
6. every candidate has exactly one final outcome;
7. every accepted proposition has the complete ADR 0060 evidence-role set;
8. every proposition and serving-text quotation maps to exact source ranges;
9. the accepted proposition inventory equals the ledger's accepted candidates;
   and
10. no unaccounted, duplicate, orphaned, fingerprint-mismatched, blocked, or
    quarantined object is hidden inside a complete result.

The ledger records exact totals for opinions, units, primary segments,
dependencies, candidates, accepted propositions, each unit use, Quarantines,
and blocked work. The arithmetic must reproduce from the declared inventories;
free-form totals cannot establish completeness.

### Final ledger results

One ledger ends in exactly one result:

- `COMPLETE_WITH_PROPOSITIONS` — all coverage and evidence checks pass and at
  least one proposition is accepted;
- `COMPLETE_NO_PROPOSITION` — all checks pass, no proposition is accepted, no
  candidate remains unresolved, and every source unit has a resolved non-
  proposition result;
- `ACCOUNTED_WITH_QUARANTINE` — the complete source structure is accounted for
  but at least one material unit, candidate, attribution, dependency, or
  proposition question remains quarantined;
- `BLOCKED` — complete examination cannot be performed because required source
  text, structure, dependency, or processing support is unavailable; or
- `INVALID` — identity, fingerprint, inventory, arithmetic, schema, or contract
  validation failed. This is a processing defect, not a legal conclusion.

Clear independent proposition candidates may continue as preserved candidate
work beside a bounded Quarantine, but the judgment ledger is not called
complete and no release may hide the unresolved boundary.

### Exact zero-proposition rule

`COMPLETE_NO_PROPOSITION` is permitted only when:

- the exact accepted original Official Version is complete;
- every opinion and Coverage Unit is present and resolved;
- every candidate has a supported rejection, merge, or split outcome leaving
  zero accepted propositions;
- there is no blocked or quarantined unit, candidate, dependency, opinion, or
  attribution issue;
- there is no `PROPOSITION_EVIDENCE` unit; and
- every treatment-only or citation-bearing unit is handed to the separate
  treatment-screening inventory.

This distinguishes three different results:

1. **no proposition exists** — the ledger is
   `COMPLETE_NO_PROPOSITION`;
2. **propositions exist but none currently serve** — the ledger is
   `COMPLETE_WITH_PROPOSITIONS`, while later-treatment and selection rules
   produce zero selected Search Records; and
3. **the system cannot safely decide** — the ledger is quarantined or blocked,
   never a valid zero.

A release-level zero-record result still requires the separate acquisition,
treatment-screening, authority, and release accounting accepted in ADRs 0048
and 0049. The proposition ledger alone does not prove that the judgment cannot
affect earlier authority.

### Traceability, correction, and allocation boundary

The Evidence Vault preserves the complete ledger artifact; the Management
Register records its identity, status, relationships, and supersession; and
the Record Traceability Lookup points each selected Case Proposition Search
Record to the exact ledger fingerprint. None of this creates an ordinary
Ask.Legal query dependency.

An official corrected judgment receives a new Official Version and ledger.
A changed parser, structure, extraction, model, prompt, or proposition contract
requires a new result and impact declaration rather than mutation. Earlier
ledgers and decisions remain reproducible.

Structural enumeration, hashing, exact unit arithmetic, dependency integrity,
schema checks, and fingerprint checks are deterministic safety controls.
ADR 0065 later assigns semantic proposition, materiality, unit-use, and
candidate proposals and challenges to two LLM passes, while deterministic
processing owns the ledger contract and reconciliation. Private chain of
thought is not stored; structured outcomes, evidence links, objections,
reasons, and uncertainty are sufficient.

## Settled Hong Kong Case Proposition extraction conformance

The user approved this architecture on 2026-08-13. ADR 0063 is normative and
does not choose an extraction technology.

### Plain-language purpose

Before any extractor is allowed to process real release work, it must pass two
different examinations:

1. **Semantic extraction evaluation:** did it understand the judgment and find
   the right legal propositions with the right limits, attribution, and exact
   support?
2. **Deterministic contract conformance:** did the surrounding pipeline account
   for every source unit and candidate, validate every evidence link, render the
   exact permitted record, and fail safely without side effects?

These questions must stay separate. A model can understand a judgment but be
wrapped in broken ledger or renderer code. Perfect ledger arithmetic can also
package a legally wrong proposition. One blended score would hide which kind
of failure occurred.

Admission applies to the complete fingerprinted extraction workflow, not to a
model name alone. The exact parser, structural normalizer, segmentation rules,
task contract, prompt, model and settings when applicable, validators,
renderer, Source Rulebook, and processing build pass or fail together.

### Adjudicated Reference Proposition Map

Each semantic evaluation judgment receives a hidden, independently prepared
**Reference Proposition Map**. This is not one preferred summary string. It
records:

- the exact accepted original judgment artifact and opinion inventory;
- every required material proposition's issue, legal answer, controlling
  qualifications, opinion and authority role, necessary context, application,
  result, and exact source ranges;
- interpretations, omitted qualifications, false attribution, and unsupported
  propositions that must not be accepted;
- permitted equivalent derived wording and any genuinely acceptable alternate
  split or merge representation that preserves the same legal meaning;
- the supported zero-proposition, Quarantine, or blocked result when
  applicable;
- required citation-bearing or treatment-only handoffs; and
- critical-error and coverage-matrix labels used only by the evaluator.

The Reference Proposition Map is adjudicated under the Hong Kong Cases Legal
Desk. High-risk or genuinely contestable maps require independent second
review and recorded resolution before entering the sealed admission set. This
offline benchmark adjudication is different from routine human review of
production judgments.

The reference does not require every permitted extraction method to discover
the same intermediate candidate count. Methods may explore different
candidates. It requires the same safe final legal content, complete accounting
of every candidate that the method did discover, and no disappearance between
candidate discovery and final output.

### Semantic extraction evaluation

The semantic suite uses the exact judgment evidence and permitted task inputs
that the eventual workflow would receive. It measures separate dimensions:

| Dimension | Simple question |
|---|---|
| Material-proposition recall | Did it find each legal answer that should exist? |
| Supported precision | Did it avoid inventing propositions that the judgment does not support? |
| Qualification completeness | Did it preserve every limit, exception, burden, and threshold needed to avoid overstating the rule? |
| Issue and answer integrity | Does the proposition answer the issue the judgment actually decided? |
| Opinion attribution | Is majority, joint, adopted, concurring, dissenting, plurality, and obiter reasoning labelled correctly? |
| Boundary correctness | Are independent propositions split and inseparable rules, qualifications, and applications kept together? |
| Evidence sufficiency | Do the exact ranges prove the derived statement, attribution, qualifications, application, and result? |
| Context and result | Is the minimum necessary factual and procedural context present without irrelevant narrative? |
| Language fidelity | Is the original English, Traditional Chinese, or genuinely mixed-language reasoning preserved accurately? |
| Uncertainty calibration | Does a true zero remain distinct from Quarantine, blocked work, and propositions that exist but are not selected? |

Derived prose is not graded byte for byte. The evaluator checks required and
forbidden meanings, exact evidence, and permitted structural alternatives.
Automated semantic comparison may assist, but the evaluated extractor or an
uncontrolled evaluator LLM cannot define its own truth. The adjudicated map
and exact deterministic evidence checks remain controlling.

### Deterministic contract conformance

The deterministic suite begins from frozen inputs and expected artifacts. It
requires exact reproducible results for:

- source, Official Version, opinion, Coverage Unit, dependency, and contract
  fingerprints;
- exhaustive ordered ledger arithmetic and final ledger state;
- exactly one outcome for every candidate actually emitted by the workflow;
- existence and exact source mapping of every evidence range;
- byte-exact verbatim quotations and prohibition of invented or silently
  edited quotation text;
- ADR 0060 and 0061 evidence, split, merge, opinion, adoption, and overlong-
  record invariants;
- canonical `metadata.text` rendering, six-field payload, token and byte limit,
  and `metadata.authority_note` separation;
- original-language, Quarantine, blocked, invalid, and zero-proposition
  behavior;
- immutable identities, correction impact, ledger and record traceability,
  and expected zero, one, or many serving records; and
- no source, provider, Pinecone, Azure, routing, deployment, credential,
  production-store, or undeclared-file side effect.

Every expected artifact role is explicitly `EXACT`, `NONE`, or
`NOT_APPLICABLE`. Missing output cannot pass as empty output. Two clean
deterministic runs must produce identical canonical artifacts and fingerprints.

### Coverage-driven catalogue

The catalogue should be driven by required boundaries rather than an
arbitrary target number. It needs direct cases across at least:

- CFA, CA, CFI, Competition Tribunal, historical superior-court, and Hong Kong
  Privy Council material;
- original English, original Traditional Chinese, and genuinely mixed-language
  reasoning, with optional translations kept outside the answer;
- zero, one, and many propositions;
- joint, lead, adopted, concurring, dissenting, plurality, agreement-only, and
  court opinions;
- ratio, material obiter, familiar applied rules, new rules, procedure,
  remedies, jurisdiction, and treatment-only reasoning;
- cumulative tests, qualifications, exceptions, definitions, alternative
  grounds, repeated statements, fact-specific applications, and cross-opinion
  adoption;
- contiguous and non-contiguous support, footnotes, tables, quotations,
  submissions, defined terms, cross-references, and dispositions;
- short judgments, long segmented judgments, cross-segment dependencies,
  indivisible overlong propositions, and unsupported source structures;
- corrected judgments, version changes, parser changes, and reprocessing
  impact; and
- hostile instruction-like text, malformed inputs, fabricated locators,
  hidden truncation, and other model or pipeline safety failures.

High-risk distinctions use linked positive and near-miss pairs. Required pairs
include adopted versus unadopted quotations, operative majority versus dissent,
express adoption versus shared outcome, cumulative test versus independent
grounds, repeated application versus a distinct legal branch, genuine no-
proposition judgment versus a missed proposition, material qualification versus
optional repetition, and treatment-only reasoning versus a proposition of the
later judgment.

Small synthetic boundary packages may live in Git. Complete real judgments,
adjudicated answers, model outputs, and operational results remain in sealed
registered evaluation storage outside Git. Permanent opaque IDs, exact
manifests, fingerprints, and hidden expected results prevent answer leakage.
Development cases and the sealed admission set remain separate; later
production failures become new versioned regression cases rather than silently
rewriting old expected answers.

### Admission gates

No single average score admits the workflow. Admission requires all of these:

1. every deterministic conformance case passes exactly;
2. the frozen semantic admission set contains no designated critical error;
3. every separately pinned semantic dimension passes its minimum threshold;
4. every high-risk slice passes its own minimum threshold, so strong English
   or short-judgment results cannot hide weak Chinese, multi-opinion, long-
   judgment, zero-result, or Quarantine behavior;
5. repeated evaluation runs meet the stability rule, with no critical failure
   averaged away; and
6. the evaluation package, workflow, contracts, build, and all applicable
   model, prompt, and setting fingerprints match the proposed admitted
   combination exactly.

Designated critical errors should include:

- a fabricated or unsupported proposition;
- fabricated, altered, nonexistent, or materially mismapped judgment support;
- a false `COMPLETE_NO_PROPOSITION` when a material proposition exists;
- omission of a qualification that makes the proposition materially broader;
- presenting dissent, concurrence, plurality, or obiter as operative majority
  reasoning;
- merging incompatible opinions or manufacturing a common majority path;
- treating required uncertainty, missing structure, or incomplete coverage as
  a confident complete result; and
- allowing hostile source text to alter the task, contract, evidence boundary,
  or output behavior.

Zero tolerance on the frozen admission set means the workflow must pass every
designated critical case before admission. It is not a claim that a
probabilistic method can never make an unseen runtime error. Exact numerical
thresholds and sealed real-judgment corpus details are pinned only with the
future executable package and cannot be relaxed merely to admit a preferred
method. ADR 0067 later fixes three ordinary and five high-risk semantic
repetitions and two clean deterministic runs.

### Runtime and retrieval boundaries

Admission does not replace runtime safety. Every production judgment still
requires ADR 0062's Coverage Ledger, deterministic validation, honest
Quarantine or blocked outcomes, correction monitoring, drift checks, and
risk-based sampling. Clear ordinary extraction may proceed automatically under
an admitted workflow; ambiguity and materially unsafe uncertainty follow the
accepted review boundary. Every discovered runtime failure creates an impact
assessment and a new regression case.

Extraction evaluation must not be mixed with search-retrieval evaluation. A
perfect proposition can still embed or rank badly, and a retrievable record can
still be legally wrong. English and Chinese query retrieval, crowding,
ranking, embedding, and downstream-answer evaluation form a separate later
gate after the extraction output itself is admitted.

### Later decisions after this architecture

ADR 0064 later settles the exact conceptual coverage matrix and catalogue, and
ADR 0065 later settles the high-level task allocation. ADR 0066 fixes the task
contracts, and ADR 0067 fixes workflow-admission repetitions, context, retries,
cost, monitoring, suspension, and revalidation. ADR 0068 fixes the suite,
protected-evidence, real-selection, evaluator-result, and pre-frozen profile
package contracts. Exact schemas, fixture bytes, selected judgments and maps,
ordinary numerical thresholds, evaluator code, and evidence-derived profile
values remain uncreated artifacts.

## Settled exact Case Proposition extraction catalogue

The user approved the full coverage-cell and case table in
`docs/design/HONG_KONG_CASE_PROPOSITION_EXTRACTION_CONFORMANCE_CATALOGUE.md`.
ADR 0064 freezes it.

### Accepted exact universe

| Suite and checkpoint | Direct cases |
|---|---:|
| Semantic materiality and discovery | 18 |
| Semantic proposition content and evidence | 18 |
| Semantic boundary and opinion attribution | 22 |
| Semantic court, language, length, uncertainty, and safety | 20 |
| Deterministic structure and Coverage Ledger | 20 |
| Deterministic candidate, evidence, renderer, and output | 16 |
| Deterministic correction, package, security, and admission | 18 |
| **Total** | **132** |

Every case is the direct primary case for one matching coverage cell. The
catalogue also declares 31 exact high-risk pair IDs with one positive and one
near-miss member. The count follows the enumerated ADR 0060 through 0063
branches and is not a permanent ceiling or target chosen in advance.

The 78 semantic cases define synthetic legal boundary packages. They cover
material and non-material legal discussion, adopted and unadopted material,
complete proposition content, split and merge rules, opinion roles, all Hong
Kong court families, original English and Traditional Chinese and mixed
language, long segmented judgments, true zero, Quarantine, blocked work,
overlong propositions, corrections, and hostile source text.

The 54 deterministic cases define exact fixture responsibilities for source
and ledger inventories, dependencies, candidate outcomes, evidence roles,
quotation bytes, rendering, limits, traceability, correction lineage, strict
packages, non-leaking evaluation, reproducibility, forbidden side effects, and
complete-workflow fingerprint admission.

Synthetic cases alone cannot admit an extraction workflow. A later task-
admission contract must add sealed real judgments and adjudicated hidden
Reference Proposition Maps across the same coverage dimensions. Development
and sealed admission cases remain separate. Real cases extend the catalogue;
they do not replace or rewrite these synthetic IDs.

### Accepted frozen consequence

ADR 0064 freezes:

- 132 permanent case IDs and 132 matching primary coverage-cell IDs;
- the group counts `18/18/22/20/20/16/18`;
- 31 exact high-risk pair IDs and their membership;
- every row's scenario and required result;
- non-answer-bearing IDs and strict explicit coverage rather than discovery,
  globs, broad tags, or counts;
- the sealed real-judgment extension requirement; and
- immutable future additions and corrections.

This catalogue approval does not create fixtures, select a model, set numerical
admission thresholds, or authorize provider calls. ADR 0065 separately settles
the high-level LLM-versus-deterministic allocation.

## Settled staged hybrid Case Proposition extraction

The user approved this Hong Kong Case Proposition LLM-versus-deterministic
allocation on 2026-08-13. ADR 0065 is normative. The approval does not enable a
model call.

### Plain-language rule

Use deterministic code for facts that can be proved mechanically. Use an LLM
for legal meaning expressed in variable judicial language. Do not let either
one pretend to do the other's job.

The pipeline should use **two separate semantic LLM passes**:

1. a **proposition analysis pass** discovers and drafts candidate legal
   propositions from exact opinion-aware evidence; and
2. a **challenge pass** independently looks for missed propositions, omitted
   qualifications, wrong opinion attribution, bad split or merge boundaries,
   insufficient context, and unsafe zero or complete results.

The challenge pass does not vote with the first pass and does not rewrite the
result directly. It emits structured objections tied to exact source ranges.
Deterministic reconciliation either proves that the objection is already
accounted for, reopens the affected candidate for another bounded analysis, or
routes the exact unresolved issue to Quarantine or human review.

### Why not pure deterministic extraction

Judges express rules, qualifications, adoption, obiter reasoning, and the
difference between a repeated application and a new legal branch in many
different ways. Keywords and fixed grammatical rules cannot reliably decide:

- whether a passage states a material legal answer;
- whether quoted or party-proposed language was adopted;
- where one proposition ends and another begins;
- whether later words narrow an earlier broad statement;
- which context and application are legally necessary; or
- whether a complete judgment genuinely contains no proposition.

Deterministic code may find headings, paragraphs, formal citations, defined
terms, and candidate signals, but those signals cannot establish the semantic
answer or prove that silence means no proposition.

### Why not one-shot or pure LLM extraction

An LLM cannot prove source authenticity, completeness, stable identity,
quotation accuracy, ledger arithmetic, token limits, or release eligibility.
Asking one model to “read the judgment and produce database records” would
combine discovery, interpretation, evidence selection, validation, rendering,
and acceptance into one uncheckable output. It would make omissions especially
hard to see.

The LLM therefore proposes structured legal analysis only. It never writes
directly to Pinecone, creates register identity, declares source completeness,
accepts its own evidence, renders the final record, determines current
authority, or authorizes release or promotion.

### Proposed staged workflow

#### Stage 1 — deterministic admission and source structure

Deterministic processing owns:

- accepted Source Snapshot and Official Version identity and fingerprints;
- artifact integrity, media and parser-profile validation;
- original and optional translation role;
- court, decision, citation, date, judge, and known opinion facts supported by
  source or register evidence;
- exhaustive ordered Coverage Unit inventory;
- structural opinion and paragraph candidates, headings, footnotes, tables,
  quoted blocks, orders, dispositions, schedules, and appendices;
- formal citation extraction, exact text ranges, normalized hashes, and source
  maps;
- initial opinion-aware segmentation and explicit dependency packets; and
- task admission, size, schema, credential, network, and evidence-boundary
  checks.

A doubtful opinion boundary, attribution, or structure is not guessed. It is
marked unresolved for semantic analysis or blocked when the source cannot be
faithfully enumerated.

#### Stage 2 — LLM proposition analysis

The first LLM task is the primary semantic analyser. For each complete opinion
or structure-preserving segment packet, it may propose:

- candidate legal issues and material legal answers;
- proposition-support, context, and non-propositional unit uses;
- opinion and authority role interpretations that are not already established
  mechanically;
- controlling qualifications, exceptions, burdens, definitions, thresholds,
  application, and relevant result;
- split, merge, repetition, independent-ground, and adoption relationships;
- the smallest complete set of exact source ranges and evidence roles;
- a source-faithful derived statement in the original language;
- treatment-only and citation-bearing handoffs; and
- structured uncertainty, ambiguity, missing-context, or possible-no-
  proposition findings.

It must cite only Coverage Units and ranges supplied in its packet. It cannot
invent locators, silently add outside knowledge, decide current authority, or
mark the complete judgment finished.

When the judgment fits one safe task packet, the LLM may receive the complete
accepted original judgment. It still performs only Stage 2 proposal work and
cannot skip the ledger, challenge, validation, and acceptance stages. Long
judgments use ADR 0062's complete opinion-aware segmentation and dependency
accounting.

#### Stage 3 — deterministic proposal validation and assembly

Deterministic checks reject or reopen proposals with:

- nonexistent, altered, overlapping, or mismatched source ranges;
- wrong source, Official Version, opinion, unit, language, or fingerprint;
- missing required fields or ADR 0060 evidence roles;
- forbidden opinion blending or impossible candidate relationships;
- unsupported cross-opinion adoption paths;
- broken ADR 0061 split, merge, and lineage invariants that can be established
  from the structured proposal;
- unaccounted units, candidates, dependencies, treatment handoffs, or ledger
  arithmetic;
- candidate or serving payloads over pinned limits; or
- schema, task, model, prompt, setting, cost, retry, or security violations.

These checks can prove that a proposal is mechanically invalid. They cannot
prove that the LLM found every material proposition or correctly understood a
qualification merely because the schema is valid.

#### Stage 4 — separate LLM challenge pass

A second schema-bound LLM task receives the accepted original evidence,
complete structural inventory, Stage 2 candidate inventory, proposed evidence
roles, proposed non-propositional reasons, and deterministic validation report.
It receives no hidden evaluation answer and must not simply edit Stage 2.

It must actively test:

- whether any Coverage Unit or reasoning path contains a missed material
  proposition;
- whether a proposed proposition is unsupported or materially overbroad;
- whether a qualification, exception, definition, burden, application, or
  result was omitted;
- whether independent propositions were merged or one proposition was
  fragmented;
- whether majority, joint, adopted, concurring, dissenting, plurality, obiter,
  or agreement-only reasoning was misclassified;
- whether context or cross-segment dependencies are incomplete;
- whether `NON_PROPOSITIONAL`, `COMPLETE_NO_PROPOSITION`, Quarantine, or blocked
  reasoning is unsafe; and
- whether hostile source text affected the task rather than being treated as
  evidence.

Every objection cites exact source ranges and names the affected candidate,
unit, dependency, or proposed completion state. “I disagree” without evidence
creates no change.

The challenge task should normally use a separately pinned prompt and fresh
model context. The exact model may be the same admitted model or a separately
admitted model; using a different provider or model family is not inherently
required and does not substitute for evaluation. The task's value comes from
independent instructions, inputs, outputs, and reconciliation—not from calling
two models and taking a majority vote.

#### Stage 5 — deterministic objection reconciliation

Deterministic reconciliation assigns every challenge result exactly one
outcome:

- `ALREADY_ACCOUNTED` with the exact candidate, evidence, or ledger link;
- `INVALID_OBJECTION` because the cited range or structured claim fails exact
  validation;
- `REOPEN_CANDIDATE` for another bounded Stage 2 analysis using the challenged
  evidence;
- `QUARANTINE` when the disagreement exposes material unresolved meaning;
- `BLOCKED` when required evidence or supported processing is absent; or
- `HUMAN_REVIEW` under the narrow triggers below.

The first LLM does not decide whether the challenger is wrong, and the
challenger does not approve its own objection. If re-analysis resolves the
issue, the changed result receives another deterministic validation and one
final bounded challenge. Repeated semantic cycling is forbidden. The exact
retry ceiling is a later task-contract value; exhausting it creates
Quarantine or human review rather than accepting the last answer.

#### Stage 6 — Legal Desk acceptance and human-review boundary

The Hong Kong Cases Legal Desk owns the accepted proposition decision under a
versioned Source Rulebook. It automatically accepts and reports an ordinary
result only when:

- the complete admitted workflow and exact evidence fingerprints apply;
- every deterministic check passes;
- every Coverage Unit, candidate, dependency, evidence role, treatment handoff,
  and challenge objection is exactly resolved;
- the Coverage Ledger can end in `COMPLETE_WITH_PROPOSITIONS` or
  `COMPLETE_NO_PROPOSITION` without hidden uncertainty; and
- no rulebook human-review trigger applies.

Human review is not required merely because the judgment is long, important,
from the CFA, Chinese, contains many propositions, states a new legal test,
creates an ordinary zero-proposition result, or required one resolved
re-analysis loop. Those facts can be common and scalable.

Human review is required only for a bounded unresolved semantic conflict after
the permitted re-analysis, uncertain operative opinion or adoption path,
genuinely unsafe plurality or attribution issue, inability to determine
whether a material proposition exists, an indivisible overlong proposition
requiring a serving-policy decision, a novel source structure outside the
accepted parser or rulebook, repeated critical-validator or challenge failure,
or another exact Source Rulebook trigger. Missing evidence remains blocked;
it is not cured by human interpretation.

The human reviewer receives the exact disputed source ranges, Stage 2
proposal, deterministic report, challenge objections, reconciliation history,
and proposed consequence. A human correction creates structured accepted
fields and evidence links, not free-form replacement of the ledger.

#### Stage 7 — deterministic finalization

Only after Legal Desk acceptance may deterministic processing:

- finalize the immutable Coverage Ledger and Rule Trace;
- create or select register-owned proposition and Search Record identities;
- render canonical `metadata.text` and the six-field payload;
- measure token and byte limits and validate exact quotation bytes again;
- create the Record Traceability Lookup entry;
- declare candidate release output and correction or reuse effects; and
- hand accepted candidate records to corpus construction.

Later-treatment analysis separately determines current authority and
`metadata.authority_note`. Corpus construction, embedding, Pinecone, Approval,
promotion, and production routing remain outside extraction and keep their
existing permission boundaries.

### Ownership summary

| Decision or task | Deterministic code | LLM | Legal Desk / human |
|---|---:|---:|---:|
| Source authenticity, exact version, fingerprints, structure inventory | Owns | Cannot decide | Reviews only unresolved source-policy issues |
| Candidate proposition discovery and legal-language interpretation | Supplies evidence and signals | Primary proposer | Accepts result; human only on named ambiguity |
| Materiality, qualifications, necessary context, application, and derived wording | Validates structure and exact support | Primary proposer and independent challenger | Accepts or corrects bounded disputed meaning |
| Exact opinion and authority role | Owns sourced mechanical facts | Proposes interpretation where reasoning role is semantic | Accepts unresolved role or adoption issue |
| Split, merge, repetition, independent grounds, and adoption scope | Enforces structured invariants | Proposes semantic boundary; challenger tests it | Accepts unresolved boundary |
| Exact quotations, locators, hashes, evidence existence | Owns | May select supplied ranges only | Cannot waive failed evidence |
| Coverage completeness and ledger arithmetic | Owns mechanical accounting | Proposes unit uses and challenges semantic omissions | Accepts only fully resolved ledger |
| Valid zero-proposition result | Proves complete arithmetic | Proposes and challenges semantic zero | Legal Desk accepts; human only if unresolved |
| Final renderer, identities, token/byte limits, traceability | Owns | Cannot decide | Cannot bypass constraints |
| Current authority, authority note, release, Pinecone, promotion | Separate later stages | Cannot decide through extraction | Existing treatment and approval authorities apply |

### Reuse, cost, and failure behavior

The system does not rerun both LLM passes over every unchanged judgment on
every update. Exact accepted Stage 2, challenge, reconciliation, and ledger
results are reused when the source, Official Version, parser, structure,
contracts, Source Rulebook, model, prompts, settings, validators, and relevant
evidence fingerprints all remain exact. A result-affecting change triggers the
bounded impact path in ADR 0062.

Provider outage, timeout, malformed output, cost-limit exhaustion, or task-
admission mismatch blocks or quarantines the affected new work. It never
becomes an empty proposition inventory, a valid zero, a deterministic fallback
interpretation, or permission to reuse a semantically stale result.

The model sees only exact evidence and task instructions. It has no source,
Pinecone, Azure, routing, deployment, credential, code-execution, or external-
tool access. Private chain of thought is neither requested nor stored;
structured candidates, evidence, objections, reasons, and uncertainty are
sufficient.

### Accepted consequence

This decision settles the high-level Hong Kong Case Proposition extraction
allocation and narrows ADR 0043's remaining deferral to other unallocated tasks
such as Gazette-event extraction. It does not select a provider or model,
choose whether Stage 2 and Stage 4 use the same model, set context, retry, cost,
or numerical admission values, create executable schemas, or authorize
implementation or model calls.

## Settled exact Case Proposition LLM task contracts

The user approved this contract boundary on 2026-08-14. ADR 0066 is normative.
It is not an executable JSON Schema, prompt, model selection, or authorization
for a provider call.

### Plain-language rule

There are exactly two semantic task families:

1. `hk-case-proposition-analysis/v1` reads admitted judgment evidence and
   proposes what the material Case Propositions are; and
2. `hk-case-proposition-challenge/v1` independently inspects the evidence and
   validated proposal and identifies possible semantic mistakes or omissions.

“Two passes” means two independent semantic workflows, not necessarily only
two API calls. A short judgment may need one analysis call and one challenge
call. A long judgment may require several structure-preserving calls within
each task family plus a judgment-level integration call under the same task
contract. Packet count changes cost and orchestration, not the semantic stages
or authority boundary.

### Common request envelope

Every request to either task carries a deterministic envelope. The model may
use the supplied content but cannot alter these facts:

| Input group | Required content |
|---|---|
| Contract identity | Task family and version, request kind, execution ID, attempt number, packet ID, and parent judgment-work ID |
| Exact workflow identity | Source Rulebook, parser, structure, segmentation, Coverage Ledger, prompt, schema, model-settings, validator, and processing-build fingerprints |
| Exact legal source identity | Judicial Decision, Official Version, original artifact, source snapshot, cutoff, court, date, citation, judges, opinions, and original-language facts already established from admitted evidence |
| Complete-coverage position | Complete opinion and Coverage Unit manifest, units assigned to this packet, their place in the complete judgment, prior and next packet boundaries, and every declared dependency |
| Supplied evidence | Immutable unit IDs, exact original-language text, source locators, range IDs, fingerprints, structural roles, opinion ownership, and formal citation leads |
| Task constraints | Permitted output claims, forbidden decisions, allowed IDs and enums, required evidence roles, original-language rule, output-size budget, and source-text-is-data instruction |
| Prior stage material | Only the exact material permitted for the request kind, such as a validated proposal for challenge or one evidence-linked objection for targeted re-analysis |

The task runner checks the envelope before a model call. A missing fingerprint,
unit, dependency, opinion, range map, contract version, or required permission
blocks the call. The model never receives credentials, URLs to fetch, tools,
code execution, Pinecone state, Azure state, approval state, deployment data,
or hidden evaluation answers.

The original court-authored text is the controlling evidence. An official
Judiciary translation and a predecessor extraction result are excluded by
default. This avoids translation dependence and anchoring on an old answer.
An auxiliary translation or prior result could be added only through a later
explicitly admitted request kind that labels it non-controlling, proves exact
alignment, and passes separate no-bias and language-fidelity evaluation.

### Analysis task request kinds

The same analysis contract permits only these request kinds:

| Request kind | Purpose |
|---|---|
| `FULL_JUDGMENT` | Analyse one complete judgment that safely fits while retaining the complete ledger manifest |
| `EVIDENCE_PACKET` | Analyse every primary Coverage Unit in one opinion-aware packet and its exact context dependencies |
| `JUDGMENT_INTEGRATION` | Reconcile the complete assembled candidate and unit-use inventory across packets, including overlap, adoption, repetition, split, and merge questions; it receives exact relevant evidence ranges, not merely summaries |
| `TARGETED_REANALYSIS` | Reconsider one exact challenged candidate, unit use, dependency, boundary, or no-proposition claim using the objection and bounded evidence supplied by deterministic reconciliation |

If a complete judgment uses `FULL_JUDGMENT`, no integration call is needed
unless validation identifies a bounded integration issue. A segmented judgment
must cover every primary unit through `EVIDENCE_PACKET` calls and must use
`JUDGMENT_INTEGRATION` before the proposal can be called judgment-wide. A unit
is never silently cut to fit. An accepted structural subrange may be used only
when it maps exactly to the preserved full unit and supplies all required
dependencies; otherwise the work is blocked.

### Analysis task response

The analysis model returns strict schema-valid data only. It does not return
the final Pinecone record or private chain of thought.

| Output group | Required content |
|---|---|
| Response binding | Exact request, packet, contract, evidence-manifest, and proposal fingerprints |
| Unit-use proposals | One proposed use for every assigned primary unit: proposition evidence, context evidence, non-propositional, or unresolved; each use has a stable reason code and exact target IDs |
| Candidate propositions | Local candidate ID, original-language legal issue, source-faithful derived statement, proposed opinion and authority role, materiality reason, and structured semantic state |
| Evidence-role map | Exact supplied range IDs for issue, legal answer, attribution, qualification, context, application, result, and selected quotation roles |
| Boundaries and relationships | Proposed split, merge, repetition, independent-ground, express-adoption, duplicate, and cross-packet relationships using only supplied IDs |
| Necessary content | Material facts and procedure, every identified qualification, exception, definition, burden or threshold, application, and relevant result |
| Handoffs | Formal citation, treatment-only, or possible-treatment handoffs tied to exact supplied ranges |
| Uncertainty | Stable uncertainty codes, exact affected candidates or units, exact evidence, missing-context request where applicable, and the narrow unresolved question |
| Packet conclusion | Propositions proposed, no proposition within this packet, or unresolved; never a judgment-wide completion decision from a partial packet |

The model selects immutable `range_id` values for exact judgment support. It
does not copy a passage into an authoritative quotation field. After
acceptance, deterministic code copies the exact preserved bytes for those
ranges into the renderer. The model drafts only the clearly labelled derived
statement and other source-faithful summaries. Any optional diagnostic text is
short, structured, evidence-linked, and non-serving.

A proposed no-proposition result requires an explicit reason for every assigned
primary unit and complete citation or treatment handoffs. Model silence, an
empty candidate array, or `NO_PROPOSITION_IN_PACKET` cannot establish
`COMPLETE_NO_PROPOSITION`.

### Challenge task input

The challenge receives a fresh prompt context and:

- the same controlling original evidence and complete-coverage position;
- the deterministically validated, assembled proposal and its fingerprint;
- every candidate, unit-use proposal, evidence-role map, dependency,
  non-propositional reason, uncertainty, and handoff;
- the deterministic validation report, including any permitted warnings; and
- for a final bounded challenge, the exact earlier objection, reconciliation
  outcome, changed proposal, and changed evidence fingerprint.

It does not receive a hidden Reference Proposition Map, expected test answer,
Legal Desk acceptance, provider or model reputation, the first task's self-
reported confidence, or a suggestion that agreement is preferred.

### Challenge task request kinds and response

The challenge contract permits:

| Request kind | Purpose |
|---|---|
| `FULL_JUDGMENT_CHALLENGE` | Challenge the complete validated result where the source and proposal safely fit together |
| `COVERAGE_PACKET_CHALLENGE` | Examine every assigned original unit and its proposed use for a missed proposition or unsafe non-propositional result |
| `JUDGMENT_RESULT_CHALLENGE` | Challenge the assembled judgment-wide candidates, cross-packet boundaries, opinion paths, dependencies, and proposed zero or complete result |
| `FINAL_TARGETED_CHALLENGE` | Check only whether one reopened objection was safely resolved after re-analysis |

A segmented judgment requires complete `COVERAGE_PACKET_CHALLENGE` coverage
and a `JUDGMENT_RESULT_CHALLENGE`. The challenge response contains:

- exact response and evidence bindings;
- one coverage row for every assigned unit, candidate, relationship, and
  proposed judgment state;
- zero or more evidence-linked objections;
- for each objection, one stable type such as missed proposition, unsupported
  proposition, missing qualification, wrong attribution, wrong boundary,
  incomplete context, bad evidence role, unsafe non-propositional result,
  unsafe zero, unsafe completion, or hostile-source instruction followed;
- exact target IDs and supporting range IDs;
- whether resolving the objection could change serving content, ledger-only
  accounting, or has an unknown material effect; and
- the narrow re-analysis question and required evidence scope.

The challenger may describe the suspected correction but cannot edit the
proposal, choose the reconciliation outcome, accept or reject the judgment,
route directly to human review, or determine current authority. An empty
objection list is valid only with complete challenge coverage; it means “no
supported objection found,” not “approved.”

### No numeric confidence

Neither task returns a percentage or numeric confidence score. Such numbers
are not dependable proof and would invite arbitrary thresholds such as “accept
at 90%.” The contracts instead require concrete states and evidence:

- supported proposal;
- unresolved semantic question;
- missing supplied context;
- conflicting supplied evidence; or
- no proposition found within the completely assigned scope.

Deterministic checks, independent challenge, the Coverage Ledger, admitted
evaluation performance, Source Rulebook rules, and exact unresolved facts—not
model self-confidence—control acceptance and review.

### Response and failure rules

Both tasks return strict JSON conforming to their exact versioned schema. Text
outside the response object, unknown fields, unknown enum values, unbound IDs,
unmapped ranges, missing assigned-object coverage, wrong-language derived
wording, input text copied into instruction fields, or inconsistent
fingerprints makes the response invalid.

One schema-repair request may correct representation only and receives the
same evidence and result fingerprint. It cannot silently change semantic
content. A semantic change is a new analysis or re-analysis result and must
pass validation and challenge. The exact provider retry count, timeout, token
budgets, packet limits, and cost ceiling remain the next admission-values
decision. Exhaustion blocks or quarantines work; it never creates a valid zero
or accepts the latest answer.

### Reuse and storage

Exact task results may be reused only when every result-affecting source,
Official Version, unit, dependency, rulebook, contract, prompt, model,
settings, validator, and processing fingerprint remains exact. The Evidence
Vault preserves requests, structured responses, validation and reconciliation
artifacts, and fingerprints under the accepted retention policy. The
Management Register records their state and lineage. Private chain of thought
is neither requested nor stored, and none of these internal artifacts enters
Pinecone.

## Settled Case Proposition workflow admission

The user approved this runtime-admission policy on 2026-08-14. ADR 0067 is
normative. It does not select a model or provider, create an executable
evaluation, or authorize a provider call.

### Plain-language rule

Do not approve a model merely because it is powerful, popular, new, or cheap.
Approve one exact **complete workflow** only after the whole combination proves
that it can safely perform this specific work.

The admitted object includes the source and parser contracts, Coverage Ledger,
packet construction, both LLM task contracts, models, prompts and settings,
deterministic validators, objection reconciliation, Legal Desk rules, renderer,
evaluation packages, thresholds, and processing build. Changing any result-
affecting part creates a different candidate workflow.

An admission permits only Case Proposition processing within its declared Hong
Kong court, language, artifact, opinion, length, and request-kind scope. It is
not source-access permission, production approval, Pinecone permission, or a
general licence to use the same model elsewhere.

### Admission states

The Management Register records immutable state transitions:

| State | Meaning |
|---|---|
| `CANDIDATE` | Complete proposed workflow exists but cannot make operational provider calls |
| `EVALUATING` | Exact workflow may run only against registered evaluation evidence under separate evaluation authorization |
| `ADMITTED` | Exact workflow passed every gate and may process permitted new work through the sole task runner |
| `SUSPENDED` | New calls stop immediately while evidence, drift, provider, cost, or security concerns are investigated |
| `REVOKED` | Workflow can no longer process new work; restoration requires a new admitted identity or an exact evidence-backed re-admission event |
| `SUPERSEDED` | A later admitted workflow replaces it for new work while its historical results remain reproducible |

Only `ADMITTED` may process ordinary new judgments. Suspension or revocation
does not silently delete or invalidate earlier results. A bounded impact review
decides which preserved results require reprocessing, Quarantine, withholding,
or no change.

### Exact admission package

One admission package binds:

- exact workflow identity and every result-affecting fingerprint;
- permitted task families and all eight ADR 0066 request kinds;
- source, artifact, court, opinion, language, length, and structure scope;
- provider endpoint, exact model snapshot or immutable version, API contract,
  tokenizer, region and provider data-handling contract;
- prompts, schemas, decoding settings, output limits, packet builder,
  validators, reconciliation rules, renderer, and processing build;
- frozen synthetic and sealed real-judgment evaluation packages and results;
- the admission repetition, threshold, context, retry, cost, concurrency,
  timeout, retention, monitoring, and revalidation profiles;
- semantic attestation by the Hong Kong Cases Legal Desk; and
- deterministic, security, capability, and operational attestation by the
  responsible system owner.

The Legal Desk attests legal evaluation and boundary correctness. The system
owner attests exact technical conformance and operational controls. Neither can
waive the other's failed gate, and neither attestation is the later human
Approval for a production Promotion Manifest.

### Model selection

Evaluate one or more exact model and settings candidates. A candidate cannot
rely on a floating alias such as “latest.” A silent provider upgrade, snapshot
change, tokenizer change, API behavior change, or result-affecting safety-
filter change breaks the admitted identity and suspends new calls until impact
and re-admission are complete.

The analysis and challenge tasks may use the same admitted model or different
admitted models. Different providers are not required. Independence comes from
separate prompts, fresh contexts, different inputs and outputs, and
deterministic reconciliation—not brand diversity or model voting.

If several complete workflows pass every gate, choose among the passing set by
lower total cost, latency, capacity risk, and operational complexity. Quality
or safety thresholds are not relaxed to prefer a cheaper candidate. Automatic
fallback to another model is forbidden unless that exact fallback combination
has its own complete admission and an explicit deterministic routing rule.

### Context and packet budget

Before every call, the task runner counts tokens with the admitted tokenizer.
The measured fixed prompt and schema, supplied evidence and prior-stage data,
and maximum permitted response must occupy no more than **80% of the admitted
model's total context window**. At least 20% remains as a hard safety reserve.

The reserved maximum response is counted even if the model usually emits less.
A caller cannot borrow that space, rely on provider truncation, or silently
lower the response ceiling. If the request does not fit, deterministic packet
construction creates smaller complete opinion-aware packets with exact
dependencies. A Coverage Unit is not cut merely to meet the budget; an exact
structural subrange is allowed only under ADR 0066. If safe packet construction
still cannot fit, the work is `BLOCKED` or enters the applicable structural
Quarantine.

The 20% reserve is a minimum admission rule, not a target for wasting context.
Each admitted profile also pins exact input, dependency, output, and per-
judgment token ceilings derived from the largest passing evaluation cases.

### Evaluation and quality gate

Admission evaluates the complete assembled workflow rather than an isolated
prompt or model response:

1. every deterministic conformance case passes exactly in two clean isolated
   runs with byte-identical deterministic artifacts;
2. all 132 frozen synthetic proposition cases are executed and accounted for;
3. every required sealed real judgment satisfies its independently adjudicated
   hidden Reference Proposition Map;
4. every required court, original-language, opinion, length, zero-result,
   Quarantine, segmentation, boundary, and hostile-text slice passes;
5. no critical error occurs in any admission run; and
6. every analysis, challenge, validation, reconciliation, Legal Desk, ledger,
   renderer, and failure-path fingerprint matches the proposed workflow.

Every ordinary semantic case and sealed real judgment runs independently
**three times**. Every case participating in a high-risk pair or carrying a
critical-error label runs **five times**. Every deterministic case passes
exactly; every high-risk pair distinction passes every repetition; no critical
error occurs in any repetition; and every separately pinned semantic dimension
and required slice meets its own threshold. Equivalent source-faithful derived
wording and expressly permitted alternate boundaries remain valid under the
hidden Reference Proposition Map; byte-identical model prose is not required.

This is intentionally stricter than accepting one blended average but does not
pretend probabilistic prose must be byte-identical or make every non-critical
ordinary semantic variation fatal. A known critical or high-risk failure
cannot be hidden by many easy successes, and weak Chinese, segmented, multi-
opinion, zero-result, or Quarantine performance cannot be averaged away. If no
workflow passes, the system remains disabled and the design or candidate
improves; thresholds are not weakened merely to admit a preferred model.

The executable evaluation manifest must nevertheless publish dimension and
slice metrics for diagnosis. Material-proposition recall, supported precision,
qualification completeness, issue-and-answer integrity, opinion attribution,
boundary correctness, evidence sufficiency, context and result, language
fidelity, and uncertainty calibration remain separately visible. Retrieval and
downstream-answer quality remain a separate later gate.

### Retry and bounded re-analysis

Retries have different meanings and are never mixed:

- one initial provider attempt plus at most **two transient retries** for an
  admitted timeout, rate limit, or provider transport failure;
- exactly **one representation-only schema repair** for a response that is
  semantically bound but fails the strict JSON representation, as settled by
  ADR 0066;
- exactly **one targeted semantic re-analysis** for one deterministically
  reconciled objection batch, followed by exactly one final targeted challenge;
  and
- no retry merely because the answer was legally inconvenient or because
  repeated sampling might eventually produce a passing answer.

Transport retries use the same immutable request and idempotency identity and
record every provider attempt. A different response is preserved, not
silently substituted. Schema repair cannot alter semantic fields. A remaining
material objection after targeted re-analysis and final challenge enters
Quarantine or the exact human-review route under ADR 0065.

Per-call timeouts and backoff values are pinned in the admission profile from
measured provider behavior. Exhaustion never becomes a valid zero, empty
candidate inventory, accepted latest answer, or permission for an unadmitted
model fallback.

### Cost and concurrency

Before the first semantic call for one judgment, deterministic planning
calculates the complete expected analysis, integration, challenge, possible
repair, and permitted re-analysis call plan. The task runner reserves the
profile's hard per-judgment budget before work begins. It does not knowingly
start a judgment that it cannot afford to finish safely.

The admission profile pins:

- maximum input and output tokens and currency cost per call;
- maximum calls, tokens and currency cost per judgment;
- maximum concurrent calls per task and provider;
- rolling provider and total pipeline budgets; and
- behavior at 80%, 90%, and 100% of each budget.

At 80%, the system reports and reduces non-urgent concurrency. At 90%, it stops
admitting new ordinary judgment work while allowing already reserved complete
work to finish. At 100%, it makes no new provider call. Urgent work requires a
separately authorized budget change; urgency never permits partial coverage or
weaker validation.

Exact currency amounts and concurrency numbers are versioned operational
profile values derived from evaluation and capacity evidence. They are not
guessed in this architecture decision and do not require a new ADR unless they
change the safety or authority boundary.

### Provider and storage behavior

The admitted provider contract must prohibit training on submitted task data
and use the shortest available provider-side retention compatible with the
approved operational need. Provider logging, region, encryption, abuse-
monitoring exceptions, and deletion behavior are pinned and reviewed as part
of admission. A material change suspends new calls pending impact review.

The Evidence Vault preserves the exact admitted requests, structured
responses, provider attempt metadata, validations, objections,
reconciliations, Legal Desk decisions, evaluation results, and fingerprints for
the lifetime required to reproduce every dependent accepted record and release,
subject to the later cross-cutting retention and deletion policy. Private chain
of thought is neither requested nor stored.

### Runtime monitoring and revalidation

Every production judgment still receives 100% deterministic validation,
complete Coverage Ledger accounting, independent challenge, objection
reconciliation, and Legal Desk acceptance. There is no lower runtime quality
mode.

Monitoring records at least:

- request, response, schema-repair, transport-retry and failure rates;
- challenge-objection, targeted-reanalysis, Quarantine and blocked rates;
- token, cost, latency and packet-count distributions;
- results by court, original language, opinion structure, judgment length and
  request kind;
- provider snapshot, endpoint, tokenizer, safety-policy and API-contract drift;
  and
- every deterministic or critical semantic incident.

A small sealed canary subset covering every critical-error family and high-risk
slice runs **weekly**. The complete admitted evaluation suite runs at least
every **90 days**. Immediate complete or impact-scoped revalidation occurs after
any result-affecting source, parser, structure, task contract, prompt, schema,
model, setting, validator, renderer, rulebook, provider-policy, or processing-
build change, and after any production critical incident.

No routine human review of clear production judgments is added. The canary and
full-suite results use already adjudicated sealed evaluation material. Humans
enter ordinary judgment work only under ADR 0065's exact exceptional triggers.

### Automatic suspension

New provider calls suspend immediately when:

- any critical canary or complete-suite case fails;
- an exact model, endpoint, tokenizer, prompt, schema, validator, rulebook, or
  build fingerprint no longer matches admission;
- a deterministic invariant, evidence-range, ledger, quotation, capability, or
  no-side-effect check fails;
- provider retention, training, security, or region behavior materially
  changes or becomes unknown;
- the admitted quality, cost, latency, schema-failure, retry, Quarantine, or
  drift stop threshold is crossed; or
- a security or data-handling incident affects the task boundary.

Suspension stops new calls and preserves in-flight and prior evidence. The
system reports the exact affected scope. Restart requires recorded resolution,
impact analysis, every required revalidation result, and a new admission event
for the exact applicable identity. It is not an informal toggle.

### What remains a later specification

This accepted policy does not choose a provider or model. ADR 0068 now fixes
the immutable package structure and selection method and assigns the remaining
contents to two distinct objects:

- the candidate-independent suite owns the sealed real-judgment inventory,
  Reference Proposition Maps, executable evaluator, and diagnostic encoding;
  and
- the exact candidate profile owns the provider, model snapshot, prompts,
  schemas, decoding settings, token and output ceilings, timeouts, backoff,
  concurrency and currency limits, ordinary thresholds, provider retention,
  region and security values, and non-critical warning and stop thresholds.

Those contents are derived through development, provider, capacity, and Legal
Desk evidence and frozen before sealed candidate scoring. They cannot weaken
the accepted complete-pass, zero-critical-error, context-reserve, retry,
capability, suspension, or review boundaries. The schemas, evidence, maps,
profile values, evaluator, results, and attestations remain uncreated.

The repository remains design-only. The final Hong Kong Legislation
consistency and completeness audit requested by the user is complete and is
recorded in
`docs/design/HONG_KONG_LEGISLATION_DESIGN_AUDIT.md`.

The audit verdict is:

- the Hong Kong policy architecture is coherent after ADRs 0043 and 0044;
- Ordinances and subsidiary legislation have complete policy architecture but
  still need executable specification and implementation artifacts;
- the constitutional-and-other-instruments scope remains deliberately
  `NOT_READY` pending the user's later review of HKeL Instruments & Others;
- the complete pipeline is not implementation-ready; and
- no new user policy decision is required to close this audit.

The user selected Hong Kong Cases as the next design area on 2026-08-12. ADRs
0046 through 0049 now settle ordinary court coverage, original-language
serving, official-judgment acquisition and accounting, and the first current-
authority baseline, and ADR 0052 now settles ordinary Hong Kong Cases update
rules. The
related serving-contract question about exposing positive case treatment to the
downstream LLM is now settled by ADR 0050: one standardized
`metadata.authority_note` field carries controlled warning clauses, selected
material support, and selected material explanatory context. No case-only
`treatment` field is added. Later-
treatment acquisition, fixtures, and packaging follow. Do not start
implementation unless the user explicitly authorizes implementation.

## Settled Hong Kong Cases court-coverage boundary

The user rejected judgments from non-binding lower courts and approved ADR
0046's boundary on 2026-08-12. A covered court qualifies when the ratio of its
decision can bind at least one lower Hong Kong court. It does not mean only a
court whose every proposition binds every other Hong Kong court.

Settled result:

- cover every publicly released written judicial decision or written reason
  from the Court of Final Appeal, Court of Appeal, Court of First Instance, and
  Competition Tribunal;
- include the corresponding pre-1997 Hong Kong superior courts and pre-1997
  Privy Council appeals from Hong Kong through separately accountable
  historical coverage;
- exclude District and Family Courts, Magistrates' Courts, Lands Tribunal,
  Labour Tribunal, Small Claims Tribunal, Obscene Articles Tribunal, Coroner's
  Court, Juvenile Court, and similar lower bodies from ordinary searchable case
  coverage because their propositions do not bind another Hong Kong court;
- do not promise to capture every hearing, oral ruling, order without reasons,
  private proceeding, restricted artifact, pleading, transcript, or court
  filing;
- treat the Judiciary Legal Reference System's judgments, reasons for verdict,
  reasons for sentence, and applicable miscellaneous judicial decisions as the
  primary official online publication products only within the accepted
  superior-court coverage;
- treat the relevant court registry as an item-specific official fallback when
  a known judgment is unavailable online or authenticity, correction, or
  version is unclear;
- treat the Judiciary Library judgment and Privy Council collections as
  historical inventory and on-demand evidence rather than routine current
  monitoring;
- preserve the Judiciary's official anonymization or redaction and never
  restore concealed personal information; and
- account for every covered official decision even when it yields no material
  Case Proposition and therefore no Pinecone record.

Technical extractability does not expand this authority scope. Relevant CFI,
CA, and CFA appellate decisions remain included based on the court that issued
them even when the underlying proceeding arose in an excluded body.

HKLII is separately settled in ADR 0045. It is registered as
`HK-CASE-HKLII-DISCOVERY` for automated discovery and cross-checking. Legal and
policy review is deferred to the legal team and does not block design or later
implementation. HKLII remains non-controlling for technical accuracy: it
cannot by itself prove judgment wording, version, authority, treatment,
authority note, or retirement, and its outage is nonblocking.

Verified current source facts from read-only research on 2026-08-12:

- the [Judiciary Judgments page](https://www.judiciary.hk/en/legal_ref/judgments.htm)
  exposes newly added judgments, judgments, reasons for verdict, and reasons
  for sentence, and directs requests for unavailable online judgments to the
  relevant registry;
- the [Judgments & Ruling page](https://www.judiciary.hk/en/judgments_legal_reference/Jud_Ruling.html)
  also exposes a miscellaneous product;
- the [Judiciary court list](https://www.judiciary.hk/en/courts/index.html)
  includes the Court of Final Appeal, High Court, Competition Tribunal,
  District and Family Courts, Lands Tribunal, Magistrates' Courts, Labour,
  Small Claims and Obscene Articles Tribunals, and Coroner's Court;
- the [Judiciary Fact Sheet](https://www.judiciary.hk/en/publications/judfactsheet.html)
  describes a bilingual court system in which Chinese or English may be used;
- the [Department of Justice litigation overview](https://www.doj.gov.hk/en/legal_dispute/litigation.html)
  states that a lower court is bound by the ratio decidendi of a superior
  court;
- the [Department of Justice common-law overview](https://www.doj.gov.hk/en/our_legal_system/the_common_law.html)
  states that Hong Kong common law is found primarily in superior-court
  judgments;
- the [Judiciary Library collections](https://www.judiciary.hk/en/judgments_legal_reference/collections.html)
  describe about 158,000 unreported Hong Kong judgments dating from specified
  periods beginning in 1946 and 182 pre-1997 Privy Council appeal judgments;
  and
- [HKLII's legal policy](https://www.hklii.hk/legal) documents its own source
  and completeness limitations. Legal and policy restrictions are not treated
  as design or implementation prerequisites under the user's compliance
  assumption; technical incompleteness still limits its Fact Authority.

### Approved lower-body exclusion rationale

The user asked on 2026-08-12 whether published Family Court, Lands Tribunal,
and Labour Tribunal judgments can be cleanly extracted and whether they should
be included. Read-only inspection produced the following distinction:

- **Family Court**: the published material is technically tractable. HKLII's
  current Family Court inventory exposes 1,806 files with case name, neutral
  citation, action number, and date. A representative current item linked
  directly to a vetted Judiciary DOCX; that newest item was temporarily
  Word-only. The Judiciary also exposes dedicated Family Court judgment-list
  and search routes. This supports reliable extraction of *published* items,
  but not a promise to capture every Family Court decision. Official family-
  procedure material describes selective publication for longer trials or
  hearings touching legal principles and requires anonymisation.
- **Lands Tribunal**: the published material is also technically tractable.
  HKLII's current inventory exposes 1,918 files with the same stable identity
  fields. A representative item linked to a vetted Judiciary Word document and
  rendered numbered paragraphs, multiple joined action numbers, and nested
  tables. Extraction therefore needs table preservation, joined-case identity,
  and legacy `.doc` support, but does not require a fundamentally different
  case pipeline.
- **Labour Tribunal**: individual published reasons are technically parseable,
  but the public corpus is not remotely comprehensive. HKLII's current
  inventory contains only five files, all dated 2009 or 2012. A representative
  item had a neutral citation, action number, direct Judiciary `.doc`, numbered
  reasons, and structured tables. The Judiciary describes a quick and informal
  forum where judgment may be delivered at the end of the hearing or later;
  leave to appeal goes to the Court of First Instance on a point of law or
  jurisdiction. Five isolated written reasons cannot support a credible
  ordinary-coverage promise.

Settled result: keep all three outside the ordinary searchable
binding-case scope. Their binding appellate decisions are already captured in
the accepted superior-court scope. If the product later wants specialist but
non-binding material, the Lands Tribunal is the strongest of the three
candidates and should enter only through a separately labelled
`specialist-persuasive` scope. Family Court could be reconsidered only as a
selective, officially anonymised specialist source. Labour Tribunal should not
be reconsidered without a materially better originating-source inventory.

No specialist-persuasive scope is currently active. Any later inclusion
requires a separate accepted decision; it cannot be inferred from source
availability or parser capability.

## Settled Hong Kong Cases language and translation boundary

Read-only official-source and current-publication inspection on 2026-08-12
established that Chinese and English may be used in Hong Kong proceedings,
Judiciary judgment translation is selective, and the LRS distinguishes a
court's judgment from the other-language `Translation`. In the inspected Court
of Appeal example `[2025] HKCA 762`, the English file was the judgment and the
Traditional Chinese file was expressly headed `[Chinese Translation — 中譯本]`;
both shared one neutral citation and action number.

The initial recommendation to place every available Judiciary translation in
the same `metadata.text` was reconsidered after the user questioned whether
translation quality justified permanent token usage. Because `metadata.text`
is both the embedding input and the text sent to the downstream LLM, full
duplication adds storage and embedding length once and adds downstream context
tokens on every retrieval. Translation availability is also selective rather
than complete.

The user approved the revised result in ADR 0047 on 2026-08-12:

- the language actually used in each court-authored opinion or passage is the
  controlling original language for proposition evidence;
- an official Judiciary translation is a Translation Artifact attached to the
  exact judgment Official Version and passages, not a second judgment, Legal
  Item, authority, or competing Official Version;
- create one original-language Case Proposition Search Record, not one record
  per language, and do not place a full translation in `metadata.text` by
  default;
- preserve every available Judiciary translation in the Evidence Vault and
  link it through the Management Register and Record Traceability Lookup for
  processing assistance, human review, terminology checks, evaluation, and
  possible later serving enrichment;
- serve the supported original-language record whether or not an official
  translation exists. Missing optional translation does not block an
  otherwise valid case or create a Coverage Gap;
- do not place a machine- or LLM-generated translation in `metadata.text`
  unless a later explicit translation-enrichment decision defines evidence,
  evaluation, labelling, review, and failure rules;
- preserve genuinely mixed-language court-authored text as original text and
  assign language at opinion or passage level rather than assuming one
  language for the whole case;
- align translations by judgment identity, Official Version, opinion,
  paragraph or passage, and complete meaning. Citation or paragraph-number
  similarity alone is insufficient;
- an unmatched, incomplete, or conflicting translation is quarantined as
  translation enrichment while the proved original-language record may
  proceed. A conflict that also calls the original artifact into question
  blocks the affected case;
- a later translation, corrected translation, or translation withdrawal does
  not create a new judgment Official Version or change the original-language
  Search Record while translations remain outside serving;
- press summaries, unofficial translations, HKLII-rendered text, and the
  Judiciary site's machine-generated Simplified Chinese pages do not replace
  the originating judgment or accepted Judiciary translation; and
- ADR 0020 as amended by ADR 0050 remains unchanged in substance:
  `metadata.authority_note` is English only and exactly
  `"None"` when no authority note applies.

Before selecting the embedding model, the pipeline must evaluate original-
language-only records with representative English and Traditional Chinese
queries in both directions: Chinese query to English judgment and English
query to Chinese judgment. The evaluation must measure retrieval coverage,
ranking, proposition accuracy, and downstream answer grounding rather than
assuming that a nominally multilingual model is sufficient.

If original-language-only records pass the accepted cross-language thresholds,
no translation is added to serving. If they fail materially, the next design
choice should be the smallest effective fix: a short, clearly labelled and
evidence-aligned translation retrieval aid for affected records. Full bilingual
proposition-and-passage duplication is the last fallback, not the default. A
future serving enrichment must never remove or truncate controlling original
text, create an unlabeled translation-only authority, or create duplicate
language records that can crowd retrieval.

## Settled Hong Kong Cases acquisition and accounting boundary

The user approved this contract in ADR 0048 on 2026-08-12.

The contract distinguishes three things that source pages often combine:

1. an **Official Judgment Listing Entry** observed in a Judiciary inventory;
2. one separately delivered **Judicial Decision** tracked as a Legal Item; and
3. the **Official Judgment Artifacts** that publish one Official Version in
   Word, HTML, PDF, or another accepted format.

One listing entry is not automatically one decision or one Search Record. One
decision may have several proceeding numbers, files, formats, and an optional
translation. Duplicate listings may point to the same decision. One valid
decision may produce zero Case Propositions.

Settled source roles:

- the Judiciary Legal Reference System inventory is the primary current
  official publication inventory for the accepted courts and artifact classes;
- the originating Judiciary judgment file or rendered judgment is the primary
  official text evidence;
- the relevant court registry is an item-specific official fallback when a
  known artifact is unavailable or its authenticity, correction, or version is
  unresolved;
- Judiciary Library and Privy Council collections support separately
  accountable historical baseline and bounded investigations;
- Judiciary translations are optional linked Translation Artifacts under ADR
  0047 and do not define coverage; and
- `HK-CASE-HKLII-DISCOVERY` remains a nonblocking discovery and cross-check
  source under ADR 0045.

For every observed official listing entry at one fixed cutoff, the Management
Register requires exactly one acquisition outcome:

- `ACQUIRED` — complete accepted original judgment evidence is preserved;
- `DUPLICATE_OR_ALIAS` — the entry is proved to identify an already acquired
  decision or artifact;
- `TRANSLATION_ARTIFACT` — the entry is an optional translation linked to an
  acquired original;
- `OUT_OF_SCOPE` — the issuing court, artifact class, or publication falls
  outside ADR 0046, with the exact reason recorded;
- `BLOCKED_UNAVAILABLE` — an in-scope original is known but cannot currently be
  obtained or completely validated; or
- `QUARANTINED` — evidence conflicts or decision, version, language, opinion,
  or artifact identity remains unresolved.

Post-cutoff items belong to the next observation and are not disguised as an
outcome for the earlier cutoff. A successful acquisition then receives one
processing and release-accounting outcome: one or more supported Case
Propositions, validly no material proposition, processing Quarantine, or the
applicable explicit unavailable-scope outcome. A missing file is never called
“no proposition.”

The resulting completeness proof reports three separate facts:

- **inventory accounting complete** — every observed entry has exactly one
  outcome;
- **evidence coverage complete or gapped** — every in-scope decision either has
  accepted originating evidence or an explicit unresolved gap; and
- **search output** — how many acquired decisions produced zero, one, or many
  Case Proposition Search Records.

This prevents record count from masquerading as source completeness. A release
cannot claim supported no change merely because no new records were produced.
All due official inventory checks must succeed, entries and preserved prior
inventory must reconcile, every in-scope change must have a disposition, and
no unresolved blocking conflict may be hidden. A complete accounting can show
a Coverage Gap; it does not make the gap safe or make the release eligible.

The acquisition bundle preserves the exact source bytes, source URL and
endpoint version, observation time and cutoff, response and publication
metadata, source labels, case name, court, date, neutral or reported citation,
all proceeding numbers, language and original-or-translation role, media type,
hash, and parser or rendering report. Generated working conversions never
replace the source artifact.

There is no Hong Kong Cases equivalent of legislation's mandatory
XML-plus-PDF pair. If only one complete accepted official original format is
published, it may support acquisition. When the Judiciary offers several
official original-language representations, preserve every relied-on variant
and deterministically reconcile their legal content. A material unexplained
difference quarantines the affected version. A stable URL whose bytes change
is always a new observation; it becomes a new Official Version only when
official evidence supports correction, revision, or replacement rather than a
silent website change.

For scalability, monitoring uses overlapping tiers:

- lightweight newly-added or RSS checks each working day;
- metadata-only court, product, and time-partition reconciliation on the
  frequency assigned to that partition;
- full artifact acquisition only for a new, changed, missing, conflicted, or
  specifically reviewed item; and
- historical-library acquisition only for the initial historical baseline or
  a bounded question.

Recent partitions are checked more frequently than old stable
partitions, but a partition must be successfully checked when its rulebook
freshness is due. The connector reuses hashes and preserved artifacts
rather than repeatedly downloading unchanged judgments. The exact endpoint,
partition sizes, parser profiles, retry values, and clock intervals remain
implementation contracts, not user policy decisions.

Before an LRS-based baseline or no-change result can proceed, technical
conformance must prove that the connector enumerates the complete promised
scope. An unproved enumeration limit remains visible and blocks the unsupported
claim; HKLII discovery cannot cure it. Acquisition, hashing, inventory
reconciliation, and coverage arithmetic use no generative LLM.

A disappeared listing or failed download is not proof that a judgment was
withdrawn. The pipeline preserves the prior evidence, opens bounded registry
or source reconciliation, and applies ADR 0005 if the affected current scope
cannot be supported. It also preserves the Judiciary's official anonymisation
and redaction exactly and never attempts to restore concealed information.

## Settled Hong Kong Cases first-baseline boundary

The user approved this framework, including the no-arbitrary-age-cutoff rule,
in ADR 0049 on 2026-08-12.

The first baseline answers one exact question:

> At one fixed cutoff, what complete set of Case Propositions from every
> required Hong Kong binding-case scope is supported for ordinary current-law
> search, after all in-scope later judgments through that cutoff have been
> screened for material treatment?

The Hong Kong Legislation baseline pattern transfers only in part. Cases reuse
one frozen cutoff, complete source accounting, greenfield identity, explicit
Quarantine and Coverage Gaps, immutable first releases, and separation of
post-cutoff changes. Cases cannot infer present authority from one current
publisher state because there is no official consolidated “current judgment.”
Every later in-scope judgment through the cutoff must be screened for material
treatment of earlier propositions.

### Settled Release Scope partition

Use one stable Release Scope per issuing-court family and decision calendar
year, for example:

- `HK-CASE-CFA-2026`;
- `HK-CASE-CA-2026`;
- `HK-CASE-CFI-2026`;
- `HK-CASE-CT-2026`;
- corresponding historical-superior-court year scopes; and
- separate Hong Kong Privy Council year scopes.

The actual court identity and original decision date assign the scope. A later
publication, correction, translation, or treatment event does not move the
decision to another scope. A correction supported as a new Official Version
updates the release for the decision's original scope. A later judgment that
changes an older proposition may require a new release for the older
proposition's scope.

These partitions are ownership and rebuild boundaries, not statements that
case law operates one court or year at a time. All required scopes still form
one Hong Kong Cases target, and treatment reconciliation remains corpus-wide.
This avoids rebuilding one enormous all-years release while preventing a
single missing old artifact from being silently lost in a global record count.

### Settled ordered baseline path

1. Freeze one observation cutoff, Source Rulebook version, Release Scope
   registry, source inventory set, format contracts, and processing contracts.
2. Prove that the accepted official inventory path can enumerate every required
   court-and-year scope, or mark the affected scope not ready. Do not invent a
   start date or describe an unverified historical period as complete.
3. Apply ADR 0048 to every official listing entry and preserve every accepted
   originating judgment, optional translation, exclusion, failure, and
   conflict.
4. Allocate new register-owned Legal Item, Official Version, opinion, passage,
   and other required identities. Legacy Distillation and Pinecone IDs remain
   non-authoritative comparison aliases only.
5. Parse every acquired decision and account for its opinions and passages.
6. Produce supported candidate Case Propositions or a reviewed valid
   no-material-proposition result. A no-proposition decision still proceeds to
   citation and later-treatment screening because it may affect an older case.
7. Screen all acquired in-scope later judgments through the cutoff against
   earlier propositions, resolve material treatment under ADR 0014, and perform
   a corpus-wide dangling-citation and treatment-completeness check.
8. Assign each proposition its supported current result: searchable with
   `authority_note: "None"`, searchable with one controlled authority note,
   non-searchable
   because it is conclusively overruled or otherwise invalid for current use,
   or Quarantine where authority or treatment remains unresolved.
9. Seal one initial Corpus Release per complete court-year scope with no
   predecessor, then compose all required scopes into one complete candidate
   Desired-State Inventory. The artifacts remain candidates and authorize no
   embedding, Pinecone operation, or deployment.

A later rule cannot cure an earlier acquisition or inventory failure. Correct
proposition text does not cure missing later-treatment coverage.

### Historical judgments

Do not exclude a judgment merely because it is old or came from a historical
collection. “Historical” describes its time and acquisition route, not whether
its legal proposition remains usable today. A supported old proposition stays
eligible until evidence establishes an authority note, retirement, or other current-
authority limitation.

The baseline does not need to reproduce a complete narrative of every time a
case was cited. It must nevertheless screen the complete accepted later-
judgment universe through the cutoff and resolve every material treatment that
could change current serving. A later judgment can also reverse or supersede an
earlier adverse treatment, so the system cannot stop at the first negative
label it finds.

The exact earliest supported year and historical inventory boundaries are
source-verification facts, not convenient defaults. If the official source can
prove some periods but not others, the Release Scope registry records the
ready and not-ready periods explicitly. The accepted complete coverage promise
cannot be silently narrowed to match whichever files are easiest to download.

### Missing evidence and incomplete treatment coverage

The initial baseline has no previous greenfield release, so carry-forward is
not available. A known missing in-scope judgment creates both an acquisition
gap and a possible treatment gap because its text may affect earlier
propositions.

The Legal Desk may narrow the impact only with evidence and a written rule. If
the affected propositions cannot be bounded, the system cannot claim treatment
complete or assign `authority_note: "None"` across the uncertain universe. A
generic authority note does not cure unknown source text. The applicable scope is withheld,
remains not ready, or prevents a complete Hong Kong Cases candidate target
under ADR 0005.

An unresolved identity, opinion-attribution, proposition-support, treatment,
or hierarchy question quarantines the smallest safely separable proposition,
decision, or scope. Independent clear work may continue as candidate work, but
the complete target cannot hide an unresolved required scope.

### Treatment and zero-record distinctions

The baseline keeps these different outcomes distinct:

- a valid decision with no material proposition of its own;
- a decision with propositions that remain searchable without an authority note;
- a decision with propositions searchable only with an authority-note warning clause;
- a decision whose otherwise supported propositions are all non-searchable
  because current authority was removed;
- an unavailable or unreadable decision; and
- a decision or proposition in Quarantine.

A zero-record result is valid only after acquisition, parsing, proposition
review, and later-treatment relevance are accounted for. It cannot stand for a
failed file, skipped processing, or uncertainty.

### Frozen cutoff and later changes

Anything first observed after the cutoff belongs to the ordinary update path.
If a new judgment or correction appears while baseline work is open, either
re-freeze at a later cutoff or finish the internally consistent original
baseline and process the later signal as an ordinary update before claiming
later currency. Never mix convenient post-cutoff judgments into only part of
the baseline.

### LLM boundary

Cutoff control, inventory reconciliation, acquisition outcomes, hashes,
identity allocation, scope accounting, authority-note validation, and release
arithmetic use no generative LLM. Hong Kong Case Proposition extraction uses
ADR 0065's staged deterministic, LLM analysis, deterministic validation, LLM
challenge, reconciliation, Legal Desk, and deterministic finalization flow.
Hong Kong treatment screening uses ADR 0053's staged hybrid proposal flow.
Every model result must cite exact passages and cannot decide authority,
authority notes, retirement, Quarantine, release eligibility, or production
action.

### Minimum future conformance examples

- a clear current judgment produces one proposition with
  `authority_note: "None"`
  after complete treatment screening;
- an old superior-court proposition remains searchable because age alone is
  not adverse treatment;
- a decision has no new proposition but expressly overrules an older
  proposition, so the decision produces no record of its own while changing
  the earlier proposition's current result;
- a later judgment conclusively overrules only one of several earlier
  propositions, so only the affected proposition is non-searchable;
- a known listed judgment is unavailable, so it is not called a valid
  zero-proposition decision and the treatment gap remains visible;
- an official correction published in a later year remains in the original
  decision's court-year scope as a new Official Version;
- a legacy Pinecone record appears identical, but the baseline allocates new
  greenfield identity; and
- a post-cutoff judgment opens the ordinary update path rather than changing
  the frozen baseline.

## Settled standardized authority-note metadata boundary

The user requires the serving metadata fields to remain standardized across
legislation, cases, Principles, and approved Regulatory Materials. The earlier
open proposal to retain `warning` and add case-specific `treatment` is
superseded by this revised contract. The user approved it on 2026-08-12, and
ADR 0050 records the accepted decision.

The target contract replaces `metadata.warning` with one universal required string named
`metadata.authority_note`. Keep the standardized six-field envelope:
`text`, `country`, `jurisdiction`, `type`, `source`, and `authority_note`.

`authority_note` is the complete controlled note that the downstream LLM must
use when assessing how safely and strongly it may rely on the retrieved
record. It applies across material families:

- **cases** — material positive, explanatory, limiting, mixed, or adverse
  later treatment;
- **legislation** — operative-scope, constitutional-interpretation, assisted-
  copy, source, or other material reliance qualifications; and
- **Principles** — publisher currency, withdrawal, qualification, or other
  approved reliance limitations; and
- **Regulatory Materials** — effective-date, transitional applicability,
  market-scope, source, representation, or other approved reliance
  limitations.

The exact value is `"None"` when no approved LLM-facing authority note applies.
It does not claim that no citation, event, or unobserved treatment exists
beyond the accepted evidence cutoff. The field remains English only for Hong
Kong, is excluded from embeddings, and is passed unchanged with
`metadata.text` to the downstream LLM.

The field uses a controlled clause grammar so mandatory instructions cannot be
confused with support or neutral context. Mandatory warning clauses appear
first, selected support clauses second, and selected neutral explanatory
context last:

```json
{
  "authority_note": "[SUPPORT: FOLLOWED] This proposition was followed in HKSAR v Example [2026] HKCA 100 at [42]-[47]."
}
```

```json
{
  "authority_note": "[WARNING: CRITICISED] This proposition was criticised in Example v Secretary [2026] HKCA 101 at [70]-[75]. Do not state it as settled without this qualification. [SUPPORT: FOLLOWED] It was earlier followed in Earlier Example [2024] HKCA 50 at [31]-[35]."
}
```

```json
{
  "authority_note": "[SUPPORT: APPROVED] This proposition was approved by the Court of Final Appeal in Example [2026] HKCFA 10 at [40]-[44]. [SUPPORT: FOLLOWED] It was followed by the Court of Appeal in Later Example [2027] HKCA 20 at [31]-[35]. [CONTEXT: EXPLAINED] Its scope was explained in Another Example [2028] HKCA 30 at [52]-[58]."
}
```

For legislation:

```json
{
  "authority_note": "[WARNING: LIMITED OPERATIVE SCOPE] This record is current only for the identified commenced provision; do not generalize it to uncommenced locations."
}
```

The complete structured case-treatment graph and non-case status evidence
remain in the Management Register and Evidence Vault. `authority_note` is a
concise approved rendering, not a raw list. Every accepted treatment remains
internally traceable. Bare citations, non-material applications, repetitive
unselected treatment, unresolved proposals, model output, reviewer notes, and
long histories remain internal.

For cases, `APPROVED` and `FOLLOWED` are eligible support. `APPLIED` enters when
materially useful to authority assessment. `EXPLAINED` enters only when it
materially clarifies the exact proposition's meaning, scope, or use, and is
rendered as neutral `[CONTEXT: EXPLAINED]` rather than endorsement.
`CITED_ONLY` never creates a note. There is no fixed support- or explanation-
clause count. The renderer includes every current material non-repetitive
signal that fits the pinned authority-note metadata and downstream-context
budget and consolidates equivalent events. Different court-authority levels,
proposition scopes or issues, later confirmation after adverse or limiting
treatment, materially different reasoning, and other independent authority
signals remain distinct. Operative opinion status, Hong Kong court authority,
treatment significance, exact scope, continuing status, and stable tie-breakers
control ordering and compression when the budget is approached. Citation count
is not legal authority and no numerical authority-strength score is emitted.

Support or context never cancels, hides, or weakens a warning. If any mandatory
warning applies, it is rendered first and validated as controlling. Context is
not support. Promotion must prove that every clause agrees with the structured
evidence, cutoff, and exact source passages.

Every distinct current mandatory warning meaning must fit. Faithful templates
may consolidate equivalent warnings but cannot drop a material effect. If the
mandatory warning meaning still cannot fit the pinned budget, the proposition
cannot serve with an incomplete note and follows Quarantine, withholding, or
no-new-target rules. Optional support and context that exceed the remaining
budget after consolidation are ranked for the most legally informative
rendering and remain fully traceable internally when omitted.

An expressly and conclusively overruled proposition remains outside ordinary
current Pinecone under ADR 0014. It is not retained merely to display an
authority note. Its treatment and retirement history remains outside Pinecone.

Changing `authority_note`, including between `"None"` and a real note, changes
the immutable serving payload and selects a different exact Search Record. A
previously unseen payload receives a new ID; ADR 0055 permits a preserved exact
record to be reselected when current support is proved. When `metadata.text`
and the embedding contract remain exact, the embedding may be reused. To limit
churn, a new citation or consolidated repetitive treatment does not
automatically change the note; only an approved change to the budgeted material
rendering does.

The user approved this expanded selected-treatment summary on 2026-08-13. The
field remains standardized across all material families; only the case-specific
controlled clause vocabulary and selection rules are expanded.

ADRs 0008, 0011, 0013, 0014, 0015, 0016, and 0020 are amended by ADR 0050;
warning-dependent Hong Kong rules and fixture descriptions now use the same
authority-note contract. Implementation must still prove that every Ask.Legal
query path passes `authority_note` unchanged. No schema or application
implementation is authorized by this design decision.

## Settled Hong Kong Cases ordinary-update boundary

The user approved this framework on 2026-08-12. ADR 0052 records the settled
decision.

An ordinary update compares one new frozen cutoff with the exact previously
accepted Hong Kong Cases state. It should process only genuinely affected work
while still proving that no required source or treatment effect was missed.

### Ordered update path

1. Freeze the new cutoff, predecessor Serving State and Corpus Releases,
   Source Rulebook, Release Scope registry, due Observations, format contracts,
   and processing contracts.
2. Decide whether all due official inventory and endpoint checks support no
   change, reveal one or more affected signals, or are unavailable.
3. Deduplicate signals and acquire only complete new, changed, missing,
   conflicting, or specifically reviewed judgment artifacts under ADR 0048.
4. Compare each affected listing, decision, Official Version, opinion, passage,
   translation, and source fact with the preserved accepted predecessor.
5. Apply the case identity and continuity rules in ADR 0014 before changing any
   proposition or record.
6. Build a transitive affected-impact graph from every new or changed decision
   to its own propositions, every treatment relationship it may create, change,
   or remove, and every older proposition and court-year scope whose current
   result may change.
7. Reprocess and review only that complete affected graph, expanding it until
   no unresolved dependency can change another serving result.
8. Reuse exact unaffected Search Records and Corpus Releases; create new
   immutable releases only for court-year scopes whose evidence, accounting,
   proposition, authority note, treatment, or record selection changed.
9. Compose all changed and reused scopes into one complete candidate Desired-
   State Inventory and preserve all post-cutoff events for the next update.

Source signals are not legal conclusions. A new listing, changed hash,
disappeared page, revised metadata field, or HKLII result merely opens bounded
work.

### Supported no change

`SUPPORTED_NO_CHANGE` is permitted only when:

- every official inventory and time partition due at the cutoff completed
  successfully and within its freshness rule;
- all entries, endpoint roles, and artifact fingerprints reconcile with the
  accepted predecessor;
- no new, changed, missing, reappearing, or unexplained item remains open;
- no official correction, withdrawal, or source-contract change remains open;
- no accepted urgent or human-raised signal remains unresolved; and
- every due treatment-coverage check is complete.

When those conditions pass, preserve the Observations and comparison proof,
reuse all existing Corpus Releases, and perform no acquisition, proposition,
treatment, embedding, or Pinecone work. Do not create an empty release merely
to record silence.

HKLII remains nonblocking. Its outage cannot prevent supported no change when
all required originating-source checks pass. Conversely, an unchanged or empty
HKLII result cannot prove no change.

### Exact HKLII role during an update

HKLII is an extra discovery net. It may expose a candidate missing or older
judgment, inventory difference, alternate case name or citation, duplicate,
citation lead, or possible treatment relationship. Each result opens only a
bounded work item.

Before the database can change, the pipeline must obtain the accepted
originating judgment and prove the exact decision, opinion, passages, court
relationship, affected proposition, and material legal effect. An HKLII lead
may then be closed as confirmed, stale, duplicate, false, or out of scope. It
cannot itself create a proposition, support or warning clause, retirement,
withholding, reinstatement, release change, or Pinecone change.

An HKLII outage is nonblocking because required official checks own the
coverage promise. An affirmative in-scope difference is nevertheless not
ignored: originating-source evidence must resolve or evidentially dismiss it,
or it remains explicit affected work. Complete official enumeration can
disprove a lead; HKLII cannot repair an official enumeration failure.

### Signals that open affected work

Affected work opens for at least:

- a newly published in-scope judgment or reasons;
- a late-published decision whose decision year is older than the observation
  year;
- changed bytes or a changed official rendering at an existing locator;
- an official correction, revision, reissue, replacement, or withdrawal;
- a case name, court, decision date, citation, proceeding-number, language,
  opinion, or source-role correction;
- a new, corrected, withdrawn, unmatched, or conflicting Judiciary
  Translation Artifact;
- a new duplicate or alias relationship;
- a disappeared entry or failed artifact download;
- a changed source schema, format profile, interpretation rule, or processing
  contract;
- an accepted urgent or human-raised source signal; or
- an HKLII discovery difference requiring originating-source investigation.

Signals are deduplicated by source entry, artifact fingerprint, decision
identity, and open work lineage. Repeated observation of the same unresolved
signal does not create duplicate jobs or legal conclusions.

### Identity and artifact changes

- A genuinely new separately delivered decision receives a new Legal Item and
  belongs to its issuing-court-and-original-decision-year scope.
- Several proceeding numbers for one delivered decision remain aliases.
- A duplicate file or moved URL adds evidence and does not duplicate authority.
- An express correction or revised-reasons publication becomes a new Official
  Version of the same decision and triggers complete opinion-and-passage
  reconciliation.
- Supplementary reasons, costs, remedy, or another separately delivered
  decision normally receive their own Legal Item and remain linked through the
  Case Dossier.
- A silent byte change is preserved as a new Source Snapshot but does not
  become a new Official Version without supporting official evidence.
- A disappeared listing is not proof of withdrawal, reversal, or retirement.

### Transitive affected-impact graph

One new judgment always affects its own court-year accounting even when it
creates no proposition. It may also affect older scopes through treatment.

For example, a 2026 Court of Appeal judgment may:

- create two new 2026 propositions;
- follow one 2019 CFI proposition without changing its authority note because
  the treatment is not material enough for an LLM-facing support clause;
- criticise one 2008 CA proposition, creating a new authority-note-bearing Search Record in
  the 2008 scope; and
- overrule one 1997 proposition, removing only that proposition from ordinary
  serving in its historical scope.

The update therefore creates or replaces releases only for the 2026 scope and
the older scopes whose accounting or records changed. Every unrelated court-
year release is reused.

A corrected later judgment may remove or change an earlier treatment passage.
That reopens the exact affected earlier proposition. Authority-note removal or
reinstatement is never automatic; it requires a new evidence-backed Legal Desk
decision and ordinary immutable lineage.

### Proposition and record continuity

After a changed Official Version is reconciled:

- reuse an exact proposition Search Record only when all six serving fields are
  byte-exact and continuing judgment and current-authority support is proved;
- select a different exact Search Record for changed proposition text or
  authority note, creating a new ID only when that exact payload has not
  already been issued;
- add newly discovered supported propositions without inventing predecessors;
- represent processing corrections, proposition splits, and merges with typed
  lineage;
- remove a proposition no longer supported by an official correction through
  correction lineage, not by calling it later judicial treatment; and
- preserve every replaced, authority-note-revised, withheld, retired, or invalid record outside
  Pinecone.

Changing only `metadata.authority_note` selects a different exact Search Record
but may reuse the existing embedding because the embedding input remains exact
`metadata.text`. A former exact record may be reselected under ADR 0055 without
backward lineage. A citation, alias, grouping, or evidence-pointer correction
that changes no serving field creates only the required register or Record
Traceability Lookup revision.

### Update outcomes and external work

Keep these update results separate:

- `SUPPORTED_NO_CHANGE` — reuse every release and record;
- `ACCOUNTING_ONLY_CHANGE` — source, translation, evidence, zero-record, or
  traceability accounting changes while the exact serving-record set remains
  unchanged;
- `SERVING_CHANGE` — at least one proposition record is added, replaced,
  authority-note-revised, withheld, retired, split, merged, or reinstated;
- `BLOCKED` — required evidence or a required Observation is unavailable; and
- `QUARANTINED` — existing evidence conflicts or cannot support a safe result.

An accounting-only change may require a new Corpus Release, traceability
revision, coverage proof, and later Serving State, while requiring zero new
embeddings and no replacement Pinecone index when the exact selected record
inventory remains unchanged. Any activation still follows the accepted
manifest and Approval rules; the update outcome itself authorizes nothing.

A serving change embeds only new or text-changed records. Authority-note-only changes
reuse the exact cached embedding when its fingerprinted embedding contract is
unchanged. The eventual promotion still builds and verifies the complete
approved target under the replacement-index rules.

### Source outage, disappearance, and uncertainty

A stale, failed, partial, or unreconciled required official Observation is not
no change. After bounded retries, apply ADR 0005:

- carry forward the last approved scope only when there is no affirmative
  evidence of change and the Legal Desk supports continued use with a visible
  Coverage Gap;
- create a complete Withholding Release when available evidence makes the old
  records potentially misleading and every affected item can be accounted for;
  or
- produce no new complete Hong Kong Cases target when neither result is safe.

A missing new judgment may create an unknown treatment gap affecting older
propositions. The impact may be narrowed only by accepted evidence and a
written rule. A generic authority note cannot cure unreadable source text.

Unrelated clear candidate work may continue, but no required gap is hidden as
no change, zero records, retirement, or a proved-empty scope.

### Processing-contract and rulebook changes

A parser, proposition, treatment, authority-note renderer, or Source Rulebook change is not a
source-law event. Its immutable replacement includes an impact declaration
identifying which decisions, propositions, treatments, authority notes, scopes, and
records require re-evaluation.

Reprocessing creates ordinary correction lineage and new releases where
results change. It never rewrites the historical decision produced by the old
contract. A processing bug does not masquerade as a court correction or later
treatment.

### Frozen cutoff and concurrency

Every ordinary update has exactly one accepted predecessor and one cutoff.
Events first observed after the cutoff belong to the next update. Overlapping
work is deduplicated or serialized against the same predecessor; if the
accepted base changes before approval or execution, the candidate package must
be rebuilt rather than silently rebased.

### LLM boundary

Watchers, source differences, acquisition admission, hashes, deterministic
parsing, identity, impact-graph traversal, exact payload comparison, scope
accounting, and release arithmetic use no generative LLM. Proposition
extraction follows ADR 0065's two-pass staged hybrid allocation, and Hong Kong
treatment screening follows ADR 0053's staged hybrid allocation. Model output
remains evidence-bound and cannot decide legal effect, authority notes,
retirement, Quarantine, release eligibility, Approval, or production action.

### Minimum future conformance examples

- all due official checks are unchanged and produce supported no change;
- a new judgment creates propositions but no treatment changes;
- materially important proposition-level following adds a controlled support
  clause to `authority_note`, creates a successor when the payload is new, and
  reuses the unchanged text embedding;
- a no-proposition judgment overrules one older proposition;
- an official correction changes one passage and only affected proposition
  records are replaced;
- a new translation changes evidence but not serving records;
- a moved URL with exact bytes adds an alias only;
- a silent byte change remains quarantined rather than becoming a correction;
- a disappeared page does not automatically retire its records;
- a late-published old decision updates its original court-year scope;
- a criticism creates a new authority-note record while reusing the text embedding;
- a nonblocking HKLII outage does not block official-source no change;
- a required official inventory outage invokes ADR 0005; and
- a post-cutoff judgment waits for the next update.

## Settled Hong Kong Cases later-treatment evidence and classification

This section preserves the accepted evidence, classification, review,
consequence, conformance, and LLM-allocation rules now recorded across ADRs
0053 through 0059. It is no longer an active recommendation.

### Settled decision — separate treatment from consequence

The user approved this model on 2026-08-13. The subsequent evidence,
acceptance, consequence, and conformance rules are settled below and in ADRs
0053 through 0059.

Do not use one flat treatment label as the database decision. Preserve five
separate axes:

1. `judicial_treatment` records what the later reasons did with the earlier
   proposition: `CITED_ONLY`, `EXPLAINED`, `APPLIED`, `FOLLOWED`, `APPROVED`,
   `DISTINGUISHED`, `LIMITED`, `DOUBTED`, `CRITICISED`, `DISAPPROVED`,
   `REFUSED_TO_FOLLOW`, `OVERRULED`, or `UNRESOLVED`;
2. `expression_mode` records whether that result is `EXPRESS`, follows by
   `NECESSARY_REASONING`, or remains `AMBIGUOUS`;
3. proposition mapping and scope record an exact proposition, a bounded set,
   case-level-only or unresolved mapping, plus whole, partial, issue-, fact-,
   or procedural-context scope;
4. opinion, hierarchy, jurisdiction, finality, and any separate appellate
   disposition remain structured authority facts rather than being hidden in
   the treatment label; and
5. `serving_consequence` separately records internal only, support note,
   warning note, Quarantine, withholding, retirement, or reinstatement.

`AFFIRMED`, `VARIED`, `REVERSED`, `SET_ASIDE`, and `REMITTED` belong in a
separate appellate-disposition field. They trigger proposition review but do
not automatically classify or retire every proposition in the earlier
decision. Only express and conclusive `OVERRULED`, with exact proposition
mapping and sufficient court and opinion authority, may support retirement.
No treatment word directly causes a serving consequence without an accepted
Legal Desk Rule Trace.

Axis 4 creates no independent serving change. It is the authority gate that
determines what consequences the treatment finding is legally capable of
supporting. The same criticism, for example, can justify materially different
results depending on whether it appears in operative reasons of a higher Hong
Kong court, a coordinate court, a lower court, a dissent, or a foreign
judgment. Lower-court, dissenting, concurring, plurality, foreign, and non-
operative statements remain recorded with exact attribution but cannot be
represented as overruling by the operative Hong Kong court. Only an accepted
combination of treatment, exact proposition and scope, authority facts, and
Rule Trace may produce an internal-only result, authority-note change,
Quarantine, withholding, retirement, or reinstatement.

The next decision is the minimum evidence required to accept each treatment
class, including the stricter proof required for adverse treatment and
retirement.

### Settled decision — exact treatment evidence thresholds and semantic analysis

The user approved these thresholds on 2026-08-13 and expressly prefers LLM
semantic analysis of judgments because judicial wording varies. The LLM is the
primary semantic proposal mechanism; deterministic rules are evidence,
structure, identity, hierarchy, schema, completeness, and permitted-output
guards rather than a keyword-based substitute for reading the judgment. The
Legal Desk retains accepted legal-effect authority.

Every accepted substantive treatment relationship requires one reproducible
evidence packet containing:

1. the complete accepted treating judgment Official Version, exact source
   fingerprint, decision identity, court, date, disposition, and complete
   opinion inventory;
2. the exact treatment passage and every necessary surrounding paragraph,
   cross-reference, defined term, fact, issue, qualification, result, and order
   needed to understand it, with a fingerprint of the supplied context;
3. exact opinion attribution and operative status, including the judges who
   joined it and any dissent, concurrence, plurality, adoption, or common
   reasoning;
4. the exact cited-decision identity or an explicit unresolved identity, with
   the citation words and alias-resolution evidence;
5. the complete accepted earlier judgment Official Version, exact Case
   Proposition ID and its source passages, or an explicit bounded, case-level,
   or unresolved mapping without inventing a proposition;
6. the proposed treatment, expression mode, whole or partial scope, material
   issue or factual distinction, jurisdiction, hierarchy, finality, and any
   separate appellate disposition;
7. a check for later correction, withdrawal, reversal, supersession, or other
   accepted evidence that changes the treating judgment's effect; and
8. the Source Rulebook version, applied rule IDs, proposal method,
   deterministic validation result, Legal Desk decision, review state, and
   resulting serving consequence.

An independent reviewer must be able to reproduce the relationship from this
packet without trusting an LLM explanation. Model confidence, repeated model
agreement, an HKLII label or summary, a headnote, citation count, similarity,
or a treatment keyword without its context is not evidence.

The proposed minimum label tests are:

- `CITED_ONLY`: exact reference, but no supported adoption, application,
  approval, limitation, or adverse assessment;
- `EXPLAINED`: the later reasons materially describe or interpret the earlier
  proposition, but the decision does not use that act alone as approval or
  rejection;
- `APPLIED`: the operative reasoning uses the exact proposition to resolve a
  material issue on the stated facts, with the reasoning-to-result link shown;
- `FOLLOWED`: the operative reasoning expressly follows, or necessarily adopts
  as its governing approach, the exact proposition;
- `APPROVED`: the operative reasons expressly endorse the proposition's
  correctness or authority; ordinary application is insufficient;
- `DISTINGUISHED`: the exact proposition is identified and the later reasons
  give a material issue or factual difference explaining why it does not
  govern; a merely different outcome is insufficient;
- `LIMITED`: the later reasons identify the previously supportable broader
  reading and establish the precise narrower boundary; a fact-specific result
  without that boundary is insufficient;
- `DOUBTED`: the reasons express material uncertainty about the proposition's
  correctness or continuing authority; a rhetorical question or reserved
  issue is insufficient;
- `CRITICISED`: the reasons identify a material defect in the proposition or
  its reasoning; disagreement about unrelated facts or outcome is
  insufficient;
- `DISAPPROVED`: the reasons expressly reject the proposition's correctness or
  acceptance; adverse tone or criticism alone is insufficient;
- `REFUSED_TO_FOLLOW`: the reasons identify the proposition, consider it, and
  expressly choose not to follow it; distinguishing it as inapplicable is
  insufficient;
- `OVERRULED`: the operative reasons of a court with sufficient Hong Kong
  authority expressly and conclusively overrule the exact mapped proposition,
  with whole or partial scope established and no unresolved opinion, order,
  identity, finality, or later-status conflict; and
- `UNRESOLVED`: credible treatment evidence exists but identity, label,
  expression, proposition, scope, authority, opinion, finality, or later status
  cannot be safely resolved.

`EXPRESS` means that the passage directly communicates the treatment; it does
not require a magic word such as “criticised” or “overruled”. `AMBIGUOUS`
expression cannot support an accepted substantive label or serving change. The
accepted treatment result is `UNRESOLVED`, while the plausible candidate
labels remain proposal evidence. `APPROVED`, `DOUBTED`, `CRITICISED`,
`DISAPPROVED`, `REFUSED_TO_FOLLOW`, and `OVERRULED` require `EXPRESS`.
`NECESSARY_REASONING` may support `APPLIED`, `FOLLOWED`, `DISTINGUISHED`, or
`LIMITED` only when the complete reasoning chain is preserved and the Legal
Desk accepts that the conclusion is necessary rather than merely plausible.

One passage may create several separate proposition-scoped relationships. One
case-level label is never copied automatically to every proposition in the
earlier judgment. Partial treatment supports a narrower successor only when
the earlier judgment itself supplies the standalone unaffected proposition;
the pipeline cannot rewrite the earlier court's rule to salvage a record.

The Legal Desk acceptance, review, consequence, and conformance architecture is
settled below and in ADRs 0053 through 0058. Exact Source Rulebook codes,
schemas, fixture bytes, and runtime task-admission values remain specification
and implementation work.

### Settled review principle and high exceptional-change threshold

The user replaced the earlier review proposal on 2026-08-13. Normal and common
treatment changes are accepted automatically after the approved LLM semantic
analysis, complete evidence contract, deterministic validation, and exact
Source Rulebook rule pass. This includes routine internal relationships and
routine additions, changes, or removals of support and warning clauses. The
system records the complete Rule Trace and reports the result and exact serving
diff to the human; it does not request separate treatment approval.

The treatment workflow is:

1. `PROPOSED` — the LLM proposes the relationship, scope, materiality, and
   consequence from the accepted judgment evidence;
2. `VALIDATED` — deterministic checks prove the source, passages, identities,
   opinion, schema, authority facts, and permitted evidence boundary;
3. `AUTO_ACCEPTED_AND_REPORTED`, `HUMAN_REVIEW_REQUIRED`, `UNRESOLVED`, or
   `REJECTED` — the Source Rulebook applies the accepted routing rule; and
4. an accepted automated or human-corrected result creates the immutable Legal
   Desk decision, consequence, and Rule Trace used for candidate construction.

Automatic acceptance may produce `INTERNAL_ONLY`, a support-note or warning-
note revision, or another ordinary consequence expressly defined by a tested
rule. It requires complete evidence, exact or rule-permitted bounded mapping,
one supported class and scope, clear opinion and authority facts, no open
conflict, a current admitted LLM task and evaluation result, all deterministic
validations, and a result within the rule's anomaly and impact limits. Model
confidence alone never qualifies. The human report shows the treating case,
affected proposition, classification, authority facts, exact passages, old and
new `authority_note`, record and release effects, and Rule Trace.

Human treatment review is used only for:

- `UNCERTAINTY_REVIEW`: ambiguous language, competing plausible classes,
  unsafe proposition or scope mapping, unclear majority or adoption, material
  hierarchy or jurisdiction uncertainty, unresolved finality or later status,
  conflicting accepted judgments or source evidence, or no exact rulebook rule;
  and
- `EXCEPTIONAL_CHANGE_REVIEW`: an objectively identified major change to the
  current authority structure rather than an ordinary treatment update.

At the user's direction, the accepted `EXCEPTIONAL_CHANGE_REVIEW` bar is high.
Importance, novelty, a Court of Final Appeal judgment, an express overruling,
reinstatement, a new legal test, or a large but uniform routine batch does not
qualify by itself. Clear effects on an exact bounded proposition set remain
ordinary automated treatment.

The objective triggers are limited to:

1. **authority-structure change** — the operative controlling decision changes
   the rule of precedent or hierarchy itself, such as which bodies or classes
   of decision bind which Hong Kong courts, or invalidates an entire class of
   authorities rather than treating identified propositions; or
2. **systemic doctrinal replacement** — an operative controlling decision
   expressly replaces a foundational constitutional or jurisdiction-wide
   doctrine, the affected impact crosses multiple independent doctrinal lines
   rather than one citation chain, and it exceeds both the high absolute and
   proportional impact thresholds pinned by the Source Rulebook.

A clear express overruling of one or a bounded set of propositions, a clear
reversal or setting aside, an evidence-backed reinstatement, and a new or
changed test whose affected universe is safely bounded all remain automated
normal changes. They produce their exact rulebook consequence and report.
Unbounded impact, a consequence with no accepted rule, or uncertainty about
whether a structural trigger is satisfied routes through `UNCERTAINTY_REVIEW`
rather than being called exceptional by the LLM.

Separate operational anomaly or promotion controls may still pause an unusual
volume, cost, retirement count, or target diff. That safety stop is not human
legal-treatment review and does not reclassify a clear routine legal change as
exceptional.

Clear routine `APPLIED`, `FOLLOWED`, `APPROVED`, `DISTINGUISHED`, `LIMITED`,
`DOUBTED`, `CRITICISED`, `DISAPPROVED`, and `REFUSED_TO_FOLLOW` results may
therefore be accepted and reported automatically, including their normal
authority-note consequences. Clear bounded `OVERRULED` treatment, reinstatement,
and routine appellate dispositions may also produce their enumerated exact
proposition consequences automatically. Ambiguity, conflict, missing rules, or
the narrow structural triggers above route the work to human review; the
treatment word, court level, novelty, or record count alone does not.

`UNRESOLVED`, missing evidence, failed validation, or unsafe mapping is never
auto-accepted. The system preserves and quarantines the smallest safely
bounded work. For an already served record, this workflow Quarantine does not
silently remove it; ADR 0005 governs carry-forward, complete withholding, or
no new target pending resolution.

The exceptional human review packet displays the exact treating and earlier
passages, necessary context, opinion and joining judges, proposition mapping,
plausible alternatives, scope, authority and finality facts, later-status
checks, validations, current record, and proposed diff. It does not expose or
require private model chain of thought. A reviewer accepts, rejects, or makes a
structured correction, which is revalidated and re-rendered rather than edited
into a frozen artifact.

This changes per-treatment review only. The already settled, separate human
Approval for the complete frozen Promotion Manifest remains in force unless
the user explicitly reopens that production-control decision. Routine
treatment results are reports rather than individual treatment-approval
requests, but they still enter the later complete package.

The user accepted this policy on 2026-08-13 as the current design and wants to
judge it from eventual results. The future evaluation contract must therefore
report automatic and human routing, structured corrections or reversals,
sampled missed treatment, and exact serving effects. A threshold or routing
change must create a new versioned Source Rulebook or ADR with an impact
declaration. No implementation may silently tune the rule after observing the
outcomes. Sampling is a non-blocking quality audit rather than routine
per-treatment approval.

### Keep four layers separate

1. A **citation observation** records that exact words in one opinion refer to
   a possible earlier authority.
2. A **treatment lead** records that the surrounding passage may say something
   legally material about that authority.
3. A **treatment proposal** maps the passage to an exact earlier Case
   Proposition and proposes one controlled classification and scope.
4. An **accepted treatment decision** is the evidence-backed Legal Desk result
   that may affect `metadata.authority_note`, retirement, Quarantine, or no
   serving field at all.

A citation is therefore not automatically treatment, a treatment lead is not a
legal result, and a proposal has no serving authority.

### Ordered evidence path

1. Acquire and validate the complete accepted originating judgment under ADR
   0048, including its exact Official Version, opinion boundaries, judges,
   paragraphs, source bytes, and fingerprints.
2. Screen every operative, concurring, dissenting, plurality, and other
   identified opinion for candidate citations. A judgment with no new Case
   Proposition still receives this screening because it may affect an older
   proposition.
3. Resolve each citation against register-owned Judicial Decision identities
   using citations, case names, proceeding numbers, aliases, and source links
   as evidence rather than identity. Preserve unmatched and ambiguous
   citations rather than guessing.
4. Capture the complete treatment context: the exact treating passages plus
   every surrounding paragraph, cross-reference, qualification, result, and
   opinion context necessary to understand what the court actually did. A
   fixed sentence window is insufficient when meaning depends on wider reasons.
5. Map the passage to each exact earlier Case Proposition it affects. Create
   one resolved relationship per proposition; keep a bounded candidate set in
   a separate unresolved Treatment Lead when exact mapping is not possible.
   Case-level criticism is not copied automatically to every proposition from
   that judgment.
6. Produce a controlled treatment result such as cited only, applied,
   followed, distinguished, limited, doubted, criticised, disapproved, refused
   to follow, overruled, or unresolved. Record affirmance, variation, reversal,
   setting aside, or remittal separately as an appellate disposition.
7. Apply the Hong Kong Cases hierarchy, jurisdiction, opinion-status,
   finality, materiality, scope, and evidence rules. Record the Legal Desk
   decision and Rule Trace.
8. Recompute only the affected propositions' current results and render any
   approved authority-note changes under ADR 0050. Retirement remains exact
   proposition-level exclusion rather than deletion.

### Required structured evidence

Every accepted or unresolved treatment relationship records at least:

- treating Judicial Decision, Official Version, court, decision date, and
  source fingerprint;
- treating opinion, judge or court attribution, exact passage locators, and
  complete context fingerprint;
- exact citation words and the resolved or unresolved cited-decision identity;
- one exact affected earlier Case Proposition ID and its supporting passages
  for each resolved relationship, or the bounded candidate set for a separate
  unresolved Treatment Lead;
- controlled treatment class, full or partial scope, relevant issue or facts,
  and whether mapping is exact or unresolved;
- court hierarchy and jurisdiction relationship, opinion status, and required
  finality or appeal facts;
- evidence cutoff, source rulebook version, applied rule IDs, proposal method,
  review state, responsible Legal Desk, and decision fingerprint;
- resulting no-effect, internal-only, authority-note, Quarantine, withholding,
  retirement, or reinstatement consequence; and
- predecessor or superseded treatment relationships when evidence changes.

The Management Register and Evidence Vault retain the complete graph and
history. Pinecone receives only the current controlled `authority_note` when a
serving note is required.

### Classification and serving consequences

- **Cited only**: record internally; no authority-note change.
- **Explained**: record internally; add `[CONTEXT: EXPLAINED]` only when it
  materially clarifies the exact proposition, and never present it as support.
- **Applied**: record internally; add `[SUPPORT: APPLIED]` when materially
  useful to authority assessment.
- **Followed or approved**: keep the proposition and make the treatment
  eligible for the budget-based support summary; include every material non-
  repetitive signal that fits and consolidate equivalent events.
- **Distinguished**: normally internal only; add `[WARNING: ...]` only when the
  distinction materially limits safe use of the earlier proposition.
- **Doubted or criticised**: keep the proposition only with the approved
  warning clause.
- **Disapproved or refused to follow**: when evidence, mapping, authority,
  finality, and one exact consequence rule are clear, accept the ordinary
  authority-note or other bounded consequence automatically and report it;
  uncertainty or a missing rule enters review or Quarantine.
- **Expressly and conclusively overruled**: retire only the exact proposition
  whose authority was removed.
- **Reversed or set aside**: review which propositions actually lost
  authority; do not erase all propositions from the earlier judgment.
- **Later treatment itself withdrawn, reversed, corrected, or superseded**:
  perform a new evidence-backed decision. A clear rulebook-supported note
  removal or exact reinstatement may be accepted automatically and reported;
  disappearance or changed words alone never imply reinstatement.

Support and context clauses never cancel a warning clause. Ordinary citations
and repetitive or unselected treatment remain internal to avoid record churn.

The user approved budget-based aggregation on 2026-08-13. Fixed support and
explanation clause counts are rejected.

### Settled immutable record transitions

The user approved ADR 0055's consequence rule on 2026-08-13:

- reuse the same Search Record when accepted internal treatment changes but
  the exact six-field serving payload, including the rendered authority note,
  remains unchanged;
- create a successor Search Record whenever an authority note is added,
  removed, or changes, while permitting exact cached-embedding reuse when
  `metadata.text` and the embedding contract remain identical;
- when a former exact six-field record becomes supported again, reselect that
  preserved record through a new append-only serving-selection or
  reinstatement event rather than creating a backward Search Record lineage
  edge; Search Record lineage remains acyclic;
- fully overruled propositions have no selected successor in the next current
  inventory, while all prior identities, payloads, evidence, and serving
  history remain preserved outside current Pinecone;
- partial overruling retires the combined record and creates or reuses only
  narrower propositions independently supported by the earlier judgment; it
  never rewrites the earlier court's proposition merely to preserve a record;
- unresolved treatment causes no guessed record transition and instead uses
  the accepted Quarantine, carry-forward, withholding, or no-new-target rules;
  and
- all serving changes still occur through a complete frozen release,
  Promotion Manifest, human Approval, replacement Pinecone Index, and routing
  switch rather than direct live-record editing.

This rule distinguishes a payload replacement from legal retirement. A
payload replacement means that a still-current proposition now needs different
LLM-facing metadata. Legal retirement means that the proposition itself is no
longer selected as current authority. The earlier illustrative backward arrow
from a newer record to an older reselected record is rejected because it would
conflict with the accepted acyclic-lineage rule. The accepted exact catalogue
now covers these transitions; executable expected artifacts remain later
implementation work.

### Settled Hong Kong treatment conformance architecture

The user approved ADR 0056 on 2026-08-13. It separates two linked forms of proof instead of
requiring a generative model to reproduce one exact prose answer:

1. **Semantic model evaluations** give the LLM complete synthetic or licensed
   judgment evidence and test whether it identifies the correct treating
   passages, earlier proposition, treatment class, expression mode, scope,
   materiality, opinion attribution, and uncertainty. Acceptable structured
   variants may be defined, but invented passages, missed mandatory treatment,
   wrong proposition mapping, or unsupported certainty fail.
2. **Deterministic contract fixtures** start from a frozen candidate proposal
   or accepted Legal Desk decision and require exact outputs: validation result,
   Rule Trace, treatment-graph delta, controlled authority note and fingerprint,
   Search Record reuse or allocation, forward lineage, Search Record Selection
   Event, embedding action, Corpus Release diff, update outcome, review route,
   and Promotion Manifest eligibility.

The catalogue should be coverage-driven rather than sized by an arbitrary
fixture count. Every legal-treatment class, authority and opinion boundary,
expression mode, scope result, renderer budget branch, immutable transition,
uncertainty path, correction or later reversal, update outcome, LLM safety
failure, and review-routing branch must have at least one direct fixture. Each
high-risk boundary should have a paired near-miss showing why the opposite
result is rejected.

Every deterministic fixture should contain one strict manifest; minimal
synthetic earlier and treating judgments; exact opinion, paragraph, court,
hierarchy, finality, cutoff, identity, predecessor-record, and treatment-graph
facts; pinned rulebook and contract fingerprints; and exact expected artifacts.
The test must compare canonical bytes, stable reason and rule IDs, complete
selected-record arithmetic, and the absence of forbidden side effects. A
fixture proves contract behavior only and never proves a real legal fact.

The accepted coverage groups include:

- internal-only citation and non-material treatment;
- material explained, applied, followed, and approved treatment;
- factual distinction versus a material limiting distinction;
- doubt, criticism, disapproval, refusal to follow, and overruling;
- majority, concurrence, dissent, plurality, foreign-court, and lower-court
  authority boundaries;
- express meaning, necessary reasoning, and ambiguity;
- exact, partial, fact-specific, issue-specific, procedural, bounded-unknown,
  and unbounded-unknown proposition scope;
- warning-first rendering, support and explanation selection, equivalent-event
  consolidation, changed references, optional overflow, and mandatory-warning
  overflow;
- same-record reuse, new successor, exact former-record reselection, full
  retirement, supported partial-retirement successors, no honest narrower
  proposition, and traceability-only change;
- corrected reasons, removed passages, later reversal, supersession, and
  evidence-backed reinstatement;
- no-proposition treating judgment, unmatched citation, HKLII-only lead,
  missing originating text, and treatment Coverage Gap;
- complete-judgment fit, structure-preserving segmentation, coverage-ledger
  completeness, silent truncation failure, invented evidence, wrong identity,
  and impossible hierarchy effect;
- ordinary automatic acceptance and reporting, uncertainty review, the narrow
  exceptional-change review, and a separate operational anomaly pause; and
- supported no change, accounting-only change, serving change, blocked,
  quarantined, post-cutoff deferral, and stale-predecessor rejection.

The recommended acceptance rule is strict: every deterministic fixture must
pass exactly; no required fixture may be skipped; the model evaluation must
meet separately pinned aggregate thresholds and zero-tolerance critical-error
rules before the model task is enabled. One model evaluation does not by itself
prove deterministic serving correctness, and deterministic fixtures do not
prove that the LLM can understand varied judgment language.

The next task is to freeze stable fixture IDs, the exact coverage matrix and
catalogue rows, fixture-package structure, and expected artifact inventory.
Model choice, prompts, numerical thresholds, real-judgment evaluation-set
composition, retries, and provider settings remain later task-admission values.

### Settled conformance catalogue and package contract

The user approved ADR 0057 on 2026-08-13. Stable namespaces encode only the suite and primary checkpoint,
not the expected legal answer. This prevents fixture IDs from leaking answers
to the model and avoids renaming IDs when terminology is refined:

- `HKCASE-TREAT-SEM-DIS-NNN` — whole-judgment discovery evaluation;
- `HKCASE-TREAT-SEM-ANA-NNN` — candidate-level semantic analysis evaluation;
- `HKCASE-TREAT-DET-VAL-NNN` — deterministic proposal and evidence validation;
- `HKCASE-TREAT-DET-DEC-NNN` — Legal Desk decision and review routing;
- `HKCASE-TREAT-DET-NTE-NNN` — authority-note rendering and budget behavior;
- `HKCASE-TREAT-DET-REC-NNN` — Search Record, embedding, lineage, and selection;
- `HKCASE-TREAT-DET-REL-NNN` — release, update, promotion-eligibility, and
  no-live-mutation consequences; and
- `HKCASE-TREAT-PAIR-NNN` — a stable link between a high-risk positive example
  and its near-miss. Pair IDs are relationships, not executable cases.

`NNN` is a zero-padded register-issued sequence within its namespace. It never
encodes the court, treatment class, expected pass or failure, real case name, or
source locator. IDs are never reassigned. A changed normative input or expected
answer receives a new case ID and package fingerprint; the old package remains
preserved. One case has one primary checkpoint. It may assert downstream
secondary checkpoints, but every required coverage cell must still name a
direct primary case so broad integration cases cannot hide a missing boundary.

The accepted logical layout is:

```text
hk-case-treatment-conformance/
├── coverage-matrix.json
├── semantic-catalogue.json
├── deterministic-catalogue.json
├── semantic/
│   ├── discovery/<semantic-case-id>/
│   │   ├── evaluation.json
│   │   ├── input/
│   │   └── expected/
│   └── analysis/<semantic-case-id>/
│       ├── evaluation.json
│       ├── input/
│       └── expected/
└── deterministic/<primary-checkpoint>/<deterministic-case-id>/
    ├── fixture.json
    ├── input/
    └── expected/
```

Small synthetic packages may live in Git. A sealed real-judgment semantic case
uses the same logical manifest and expected-answer contract but references an
opaque registered external artifact and fingerprints; its judgment bytes,
answers, model outputs, and operational evaluation results remain outside Git.
Neither the model task nor its evidence packet receives the case ID, title,
coverage labels, pair ID, expected answer, or critical-error tags.

All three top-level JSON catalogues and both manifest forms are strict Draft
2020-12 JSON with `additionalProperties: false`. Each frozen catalogue lists
every case explicitly with its manifest path or external artifact reference,
hash, package fingerprint, evidence class (`SYNTHETIC` or `SEALED_REAL`), task
or checkpoint, status, and applicable contract fingerprints. Ranges, directory
globs, dynamic test discovery, and undeclared files cannot establish
completeness.

Every manifest uses a common strict envelope containing schema and contract
versions, stable ID, suite, primary checkpoint, frozen status, evidence class,
contracts and fingerprints, declared input slots and hashes, primary and
secondary coverage-cell IDs, optional pair ID and pair role, assertion scopes,
expected-artifact declarations, package inventory, and package fingerprint.
Human titles and purposes are non-normative and never enter the model packet.

Semantic `evaluation.json` additionally declares the model-stage task contract,
complete evidence packet or sealed artifact reference, expected coverage-ledger
requirements, one or more explicitly accepted structured results, exact
passage and proposition evidence, adjudication state, scoring dimensions, and
critical-error categories. Free-form chain-of-thought is neither requested nor
stored. Several accepted results are permitted only when a human-approved
adjudication record proves that their difference is legally immaterial.

Deterministic `fixture.json` additionally declares exact prior register,
treatment-graph, record, release, inventory, cutoff, hierarchy, finality, and
rulebook state; the frozen proposal or Legal Desk decision under test; and one
state for every expected artifact role: `EXACT`, `NONE`, or `NOT_APPLICABLE`.
Missing output can therefore never satisfy an expected zero result.

The deterministic artifact-role inventory is:

- validation result and ordered reason codes;
- accepted Legal Desk decision and ordered Rule Trace;
- treatment-graph delta and treatment-screening accounting;
- authority-note bytes and fingerprint;
- created, reused, reselected, withheld, and retired Search Record inventory;
- forward Search Record lineage and append-only Search Record Selection Events;
- embedding plan stating exact reuse, generate, or omit;
- Corpus Release diff and record arithmetic;
- Desired-State Inventory diff and record arithmetic;
- ordinary-update outcome;
- human-review route and separate operational-control result;
- promotion-eligibility result;
- forbidden-side-effect assertions, including no network, provider, Azure,
  Pinecone, routing, credential, or undeclared-file access; and
- canonical fixture execution report.

Each role is exact when applicable, explicitly `NONE` when the correct result is
zero output, or `NOT_APPLICABLE` only when the coverage matrix proves that the
checkpoint is outside the fixture's assertion scope. Structured artifacts must
validate against pinned schemas and then match canonical expected bytes. Two
isolated clean runs must produce byte-identical deterministic artifacts.

`coverage-matrix.json` is the completeness authority. Every required coverage
cell has a stable ID, description, suite, primary case IDs, required positive
or near-miss role, linked pair when high risk, and applicable contract version.
Secondary tags do not satisfy a missing primary case. Every case must be used
by at least one coverage cell. Every high-risk cell must have both pair roles.
No required cell or case may be silently skipped, marked inapplicable, or
removed; a new frozen catalogue version and impact declaration are required.

The accepted contract fixes package mechanics without choosing an arbitrary
count. ADR 0059 now freezes the audited initial coverage-cell and case table at
155 direct cases because that count follows the accepted legal and technical
branches. Future requirements may add cases without renumbering or silently
changing these accepted IDs.

### Accepted exact initial treatment catalogue

`docs/design/HONG_KONG_CASE_TREATMENT_CONFORMANCE_CATALOGUE.md` now contains the
complete proposed row-by-row matrix. The design audit expanded the earlier
144-case draft after finding omitted accepted baseline, update, language,
security, identity, relationship, and reversal boundaries and several rows
that did not state one exact deterministic result. Its corrected branch-
derived result is:

| Primary checkpoint | Direct cases and matching primary cells |
|---|---:|
| Semantic whole-judgment discovery | 13 |
| Semantic candidate analysis | 40 |
| Deterministic validation and package safety | 32 |
| Deterministic Legal Desk decision and routing | 22 |
| Deterministic authority-note rendering | 14 |
| Deterministic record, embedding, lineage, and selection | 12 |
| Deterministic release, update, and promotion boundary | 22 |
| **Total** | **155** |

The proposal also freezes 21 high-risk positive and near-miss pair
relationships. Each case has one matching primary coverage cell, so no broad
integration case or secondary tag hides a missing direct boundary. Local
validation confirms all 155 rows, the group counts, all 21 pairs, exactly two
members per pair, and no undeclared or unused pair.

The 53 semantic rows are synthetic boundary evaluations. They do not make a
future model task admission-ready. A later task-admission contract must add the
sealed representative real-judgment cases and pin their protected artifacts,
adjudicated answers, thresholds, critical-error policy, repeated-run rules,
model, prompt, settings, cost, retention, and revalidation triggers. Those rows
extend rather than replace the synthetic catalogue.

ADR 0059 freezes all 155 case IDs, 155 coverage-cell IDs, 21 pair IDs,
normative scenarios, and required results. Exact JSON Schemas, manifests,
synthetic bytes, stable rule and reason codes, canonical expected artifacts,
and validators remain later specification and implementation work and are not
authorized by this design decision.

### Settled directional treatment relationship and two-view model

The user approved ADR 0058 on 2026-08-13. The system records both how an earlier
Case Proposition has been treated and how a later judgment treats earlier
propositions, without storing two relationships or adding another Pinecone
metadata field.

One accepted directional Later Treatment relationship should record:

- one stable relationship ID;
- required treating Judicial Decision, Official Version, opinion, judges, and
  exact treating passages;
- zero or more treating Case Proposition IDs when the treatment reasoning also
  supports separately searchable propositions in the later judgment;
- one required exact treated earlier Case Proposition ID for a resolved
  relationship;
- treatment class, expression mode, whole or partial scope, materiality,
  authority, opinion status, finality, and appellate-disposition facts;
- evidence, source and context fingerprints, cutoff, rulebook, Rule Trace,
  Legal Desk decision, review state, and supersession status; and
- the accepted internal, note, Quarantine, withholding, retirement, or
  reinstatement consequence.

An unresolved target remains a separate Treatment Lead with its exact evidence
and bounded candidate set where possible. It does not become a settled incoming
relationship until resolved.

The Management Register then derives two projections of the authoritative
relationship set at each cutoff:

- **incoming view**, keyed by the treated earlier proposition: “which later
  judgments treated this proposition, and how?”; and
- **outgoing view**, keyed by the treating later judgment and, where available,
  its treating proposition: “which earlier propositions did this judgment
  treat, and how?”

The relationship remains valid when the treating judgment has no separately
searchable proposition of its own. Treating proposition IDs are therefore
optional; treating decision, opinion, and passages are always required. This
preserves the accepted rule that a no-proposition judgment may still overrule
an older proposition.

The two projections carry the same relationship ID and fingerprint and do not
create duplicate treatment edges, Search Records, or vectors. Corrections,
reversal, withdrawal, or supersession never overwrite an accepted
relationship. They reopen the decision work, append the required successor or
supersession facts, and use the outgoing view to find every earlier proposition
whose incoming current-authority result may change.

Serving remains asymmetric by design:

- the earlier proposition's `metadata.authority_note` may render selected
  material **incoming** treatment because it qualifies how safely the earlier
  proposition can now be used;
- the later judgment's own Case Proposition `metadata.text` contains its
  source-supported reasoning about earlier authority when that reasoning forms
  part of the proposition; and
- the later record's `metadata.authority_note` describes later treatment of
  that later proposition, not a list of cases it treated.

Therefore no exhaustive outbound-treatment list is appended to
`metadata.text`, no outbound list is copied into `authority_note`, no new case-
specific metadata field is added, no relationship or whole-case summary vector
is created, and Ask.Legal performs no query-time graph join. Bare citations and
immaterial treatment remain internal. Full incoming and outgoing views remain
available internally for Legal Desk work, impact analysis, audit, reports,
corrections, and later reprocessing.

Pinecone alone does not promise exhaustive citator-style enumeration. A future
exact graph lookup would require a separately approved Query Contract and
Ask.Legal query-path change. The accepted catalogue incorporates three
direct deterministic cases: optional treating-proposition linkage
(`DET-VAL-031`), exact one-edge/two-view projection (`DET-REL-016`), and
correction-driven reverse impact (`DET-REL-017`).

### Unmapped and uncertain treatment

If the treating passage cannot be mapped to an exact earlier proposition, the
pipeline keeps an unresolved treatment lead. It does not apply one label to
the whole earlier case merely for convenience.

When the passage is credibly adverse and the possible affected propositions
can be bounded, quarantine that smallest set pending resolution. If the effect
cannot be bounded across required current records, report the treatment
Coverage Gap and apply ADR 0005. A generic authority note cannot cure an
unknown target or missing judgment text.

A dissent, concurrence, plurality, lower-court statement, foreign authority,
or non-operative discussion retains its exact attribution. It cannot be
presented as treatment by the operative Hong Kong court without a rule that
supports that legal effect.

### Corrections and scalable reuse

For each new or changed judgment, build a complete outgoing citation-and-
treatment inventory and compare it with the previous accepted Official
Version. Added, removed, or changed passages reopen only the affected
relationships and earlier propositions. Removal of words from a corrected
judgment does not automatically remove a warning or reinstate a record.

Maintain an internal citation and reverse-treatment index outside Pinecone.
Ordinary updates scan complete new or changed judgments, not the whole corpus.
If processing later discovers a new proposition in an old judgment, use the
stored later-citation observations to identify which later judgments need
screening. A rulebook or processing-contract change carries an impact
declaration and re-evaluates only the identified universe unless that universe
cannot be safely bounded.

HKLII can contribute candidate citation or treatment leads to this inventory,
but every accepted relationship still relies on the originating judgment.
Citation and treatment edges create no vectors of their own.

### Completeness accounting

Every acquired in-scope Judicial Decision receives a treatment-screening
result even when it creates no proposition:

- screening complete with no cited earlier authority;
- citations found but no material treatment accepted;
- every material treatment lead resolved;
- treatment screening blocked by missing required evidence; or
- treatment evidence or mapping quarantined.

Every citation observation is likewise accounted for as unmatched, cited
only, mapped but non-material, accepted material treatment, out of scope, or
unresolved. Record counts cannot substitute for this proof.

### LLM boundary

ADR 0053 accepts the high-level staged hybrid allocation for Hong Kong later-
treatment work. Every result must satisfy the same schema, exact-passage,
evaluation, rulebook, review, and failure contract. No model output may decide
authority-note text, retirement, Quarantine, release eligibility, Approval, or
production action.

The accepted allocation is:

- deterministic code acquires and parses the official judgment, identifies
  opinion and paragraph boundaries, extracts formally recognizable citations,
  resolves exact identities and aliases, checks court hierarchy, gathers
  candidate context, traverses the citation graph, validates schemas and exact
  passage support, and computes record and release consequences after approval;
- a schema-bound generative-LLM task proposes treatment-bearing passages,
  implicit or linguistically unusual references, exact proposition mappings,
  controlled treatment classes, scope, and materiality for the bounded
  candidate universe;
- deterministic validators reject nonexistent citations, missing passages,
  wrong identities, impossible hierarchy effects, invalid classes, unsupported
  mappings, and output outside the supplied evidence; and
- the applicable Legal Desk makes every accepted legal-effect decision that
  can revise `authority_note`, quarantine, withhold, retire, or reinstate a
  proposition.

The model may inspect the complete judgment when it fits the accepted task
limits, because treatment meaning can depend on the facts, issue, result, and
reasoning outside the paragraph containing a citation. That whole-judgment
pass is discovery and orientation only; it must not produce a directly
accepted treatment result. It first proposes a candidate inventory that
accounts for every supplied opinion or segment, but neither its apparent
completeness nor model silence proves that no treatment exists. Each candidate
then receives a smaller evidence packet containing the exact
passages and necessary context, and the model returns the structured mapping,
class, scope, materiality, and uncertainty for deterministic validation and
Legal Desk decision. If a judgment cannot safely fit, opinion-aware,
structure-preserving segments are processed with an explicit coverage ledger;
silent truncation is forbidden.

A one-shot instruction such as “read this judgment and update the database” is
forbidden even when the judgment fits in the model context window. It
mixes discovery, legal interpretation, identity, validation, and serving
consequences into one uncheckable answer and makes omissions difficult to
detect.

Pure deterministic interpretation is not recommended because courts express
treatment through varied legal language and context rather than one reliable
keyword vocabulary. Pure LLM processing is not recommended because it is
unnecessarily expensive for exact citation and graph work and cannot safely own
identity, hierarchy, evidence, or serving consequences. The later allocation
decision is complete for this task, but later task-enablement contracts must
still define the exact runtime task IDs, schemas, models, prompts, evaluations,
confidence and review rules, cost limits, and failure thresholds before any
provider call.

### Minimum conformance examples

- a bare citation creates internal citation evidence and no serving change;
- a material explanation creates `[CONTEXT: EXPLAINED]` without being
  represented as endorsement;
- one controlling approval is selected ahead of repetitive weaker treatments,
  while every omitted relationship remains internally traceable;
- an express material following of an exact proposition creates a support
  clause while reusing the text embedding;
- adding another bare citation or equivalent repetitive following that does
  not change the consolidated clause creates no Search Record churn;
- a repetitive lower-court application is recorded but produces no support
  clause;
- a factual distinction does not warn, while a material limiting distinction
  does;
- criticism in a dissent retains dissent attribution and is not represented as
  operative majority treatment;
- a lower court purports to reject superior authority but cannot overrule it;
- the Court of Final Appeal expressly overrules one of several propositions,
  retiring only that proposition;
- partial overruling of a combined record produces only source-supported
  narrower successors, otherwise Quarantine;
- an adverse case-level passage cannot be mapped to one proposition, so the
  smallest possible affected set is quarantined rather than globally labelled;
- a no-proposition judgment overrules an older proposition;
- corrected reasons remove a treatment passage, requiring a new decision
  rather than automatic reinstatement;
- an unmatched HKLII treatment lead creates no legal or serving result;
- missing treating judgment text creates a treatment Coverage Gap; and
- later reversal of the treating decision requires new evidence-backed
  treatment and serving decisions.

## Current repository state

- Greenfield modular monorepo design; no application code or technical stack.
- Planned applications: control plane, review application, acquisition worker,
  legal-processing worker, and restricted promotion worker.
- Applications may depend on shared packages; packages do not depend on
  applications. Domain and contracts do not depend on infrastructure.
- Runtime identities, credentials, networks, deployments, and data roles remain
  separate even though code will share one repository.
- Git contains code, schemas, prompts, small synthetic fixtures, evaluation
  definitions, infrastructure configuration, and documentation only. Corpora,
  source snapshots, releases, runtime state, backups, and credentials stay
  outside Git.
- Legacy Ask.Legal Distillation, Releases, and Pinecone repositories are
  reference material only and create no production dependency.
- Pinecone is a replaceable serving copy. The Management Register records what
  the system believes and does; the Evidence Vault preserves the proof.

## Hong Kong Legislation audit corrections

### ADRs 0043, 0053, and 0065 through 0068 — deferred allocation with accepted exceptions

The legal-processing worker's LLM task runner remains the sole internal
generative-model gateway. Model output is proposal-only and cannot establish
source authenticity, legal status, identity, authority note, disposition, release,
Approval, retirement, or production action.

Hong Kong later-treatment runtime contracts remain unpinned. Gazette-event
extraction and other unallocated tasks remain non-authorizing candidates under
ADR 0043. Hong Kong Case Proposition conceptual tasks, admission policy, and
evaluation/profile package architecture are settled by ADRs 0066 through 0068,
but their actual executable packages, evidence, evaluator, and evidence-derived
profile remain uncreated.

ADR 0053 accepts the staged hybrid allocation for Hong Kong later treatment:
whole-judgment LLM discovery and candidate-level LLM analysis create proposals
between deterministic preparation and validation, while the Legal Desk retains
legal-effect authority. The model stages remain disabled until their exact
runtime task contracts pass admission.

ADR 0065 accepts the two-pass staged hybrid allocation for Hong Kong Case
Proposition extraction. Deterministic source admission and structure precede
LLM proposition analysis; deterministic validation precedes an independent LLM
challenge; deterministic reconciliation and Legal Desk acceptance precede
deterministic finalization. ADR 0066 fixes the two exact conceptual task
contracts, ADR 0067 fixes complete-workflow admission and monitoring, and ADR
0068 fixes the package and protected-evaluation architecture. The model stages
remain disabled until actual executable packages and an immutable evidence-
derived admission profile pass every accepted gate.

Deterministic safety controls, evidence citations, Source Rulebooks, Legal Desk
authority, required human review, and task-admission rules remain settled.
Embedding is a separate promotion capability; Ask.Legal's answer LLM remains
outside this pipeline.

### ADR 0044 — normalized results and completed test coverage

Hong Kong results keep these dimensions separate:

- processing outcome: `PASS`, `BLOCK`, or `QUARANTINE`;
- legal disposition: current, Waiting Room, evidence-only, historical,
  Quarantine, or `NOT_APPLICABLE` at an earlier checkpoint;
- coverage effect;
- Source Contract Review state;
- record output; and
- workflow or reason code.

`PASS` does not imply searchable law. A Coverage Gap is not a legal
disposition. `SUPPORTED_NO_CHANGE` is a workflow result.

Two direct `HKLEG-CURRENT-OBS-003` cases were added:

- `HKLEG-CURRENT-CASE-017`: release-blocking Observation unavailable; and
- `HKLEG-CURRENT-CASE-018`: one affected-work source unavailable while
  independent work may proceed.

The frozen Hong Kong conformance universe is now:

| Catalogue | Count |
|---|---:|
| HKeL reconciliation fixtures | 89 |
| Ordinary current-update cases | 18 |
| First-baseline cases | 14 |
| **Total** | **121** |

## Settled Hong Kong Legislation design

- Three non-overlapping Release Scopes: Ordinances, subsidiary legislation,
  and constitutional-and-other instruments.
- HKeL source categories and A-numbers are evidence aliases, not ownership.
  The Instrument Disposition Registry routes each item by legal nature.
- One bilingual Search Record holds authentic English and Traditional Chinese
  for the same Legal Location in one `metadata.text`.
- Every record has English-only `metadata.authority_note`; exact `"None"` persists
  when no authority note applies. The note reaches the downstream LLM but is not
  part of the embedding input.
- Bilingual current HKeL XML constructs the record. Matching verified bilingual
  PDFs normally prove text and version. Eligible constitutional items may use
  matching official HKeL assisted copies only under ADR 0029.
- Gazette artifacts prove exact legal events; HKeL proves the resulting
  consolidated serving text. Event-before-consolidation creates an exact
  Coverage Gap and no reconstructed current wording; ADR 0079 creates warned
  analytical records wherever valid latest applicable official HKeL text is held, while
  a location without that text emits no record.
- Reconstructed consolidations are disabled internally and in Pinecone. A
  later explicit ADR may reopen the option.
- HKeL past data is acquired only for a named baseline, historical,
  investigation, recovery, audit, or evaluation question. The first baseline
  proves present state without inventing a complete event history.
- Editorial Records prove their assigned official editorial changes but never
  replace the complete current bilingual evidence bundle.
- LegCo Bills and proceedings are excluded from automated ingestion and
  serving. Optional human research is non-controlling.
- Monitoring uses daily lightweight current-law signals, weekly supporting
  checks, monthly or event-triggered cross-checks, and on-demand large or
  historical artifacts.
- Current updates use stable `HKLEG-CURRENT-*` rules and preserve an ordered
  Rule Trace. The first baseline uses separate `HKLEG-BASE-*` rules.
- Legal status is assigned at the exact supported Legal Location. Waiting Room,
  evidence-only, historical, Quarantine, and Coverage Gap are not synonyms.
- IDs are opaque and register-issued. Source identifiers are aliases. A changed
  serving payload selects another exact Search Record; a new payload creates a
  forward successor, while a former exact supported payload may be reselected
  without backward lineage.
- Record splitting follows complete official bilingual structure, recursive
  fit checks, dependency closure, canonical grouping, and exact primary-source
  unit coverage. Arbitrary token, character, sentence, or punctuation splits
  are forbidden.
- One frozen `hk-legislation` Source Rulebook Package binds coverage, sources,
  interpretation, rules, codes, contract locks, tests, readiness, activation,
  and impact. A separate attestation binds one exact processing build to all
  121 passing tests.
- Processing produces candidate records and immutable releases only. It cannot
  approve, embed, mutate Pinecone, or deploy.

## Release Scope readiness

| Release Scope | Policy architecture | Current state |
|---|---|---|
| `HK-LEG-ORDINANCES` | Complete | Requires executable artifacts and conformance attestation before `DECISION_READY` |
| `HK-LEG-SUBSIDIARY` | Complete | Requires executable artifacts and conformance attestation before `DECISION_READY` |
| `HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS` | Deliberately incomplete | `NOT_READY` pending the mandatory Instruments & Others review and registry rows |

## Deliberately deferred user decisions

- Entire HKeL Instruments & Others approach and row-level Instrument
  Disposition Registry. The user explicitly expects to revisit and revise it.
- Exact runtime contracts and admission values for the allocated Hong Kong
  later-treatment and Case Proposition tasks, plus the still-deferred Gazette-
  event and other candidate-task allocations.
- Query-facing dates and recency filtering or ranking. Internal dates remain
  preserved, but the six-field serving contract has no date field.
- Azure production activation details and the final date-led unique Pinecone
  index naming contract.
- Source-specific rights, contracts, and compliance controls. The design uses
  the user's assumption that registered uses are legally compliant and leaves
  later compliance work to the legal team.

## Implementation artifacts still required

These are not open Hong Kong policy questions:

- exact machine schemas for rulebooks, rules, codes, decisions, reports,
  traceability, fixtures, and expected outputs;
- all 121 synthetic fixture or case packages and exact expected artifacts;
- semantic validators and deterministic parsing, XML/PDF reconciliation,
  bilingual alignment, status mapping, rendering, partitioning, and coverage
  proof;
- controlled-English authority-note templates and exact stable reason-code entries;
- high absolute and proportional exceptional-impact threshold values derived
  from the accepted evaluation method and pinned in the Source Rulebook;
- connectors, endpoint discovery, health checks, retry counts, clock times,
  backoff, timeouts, and provider-throttling settings;
- the pinned embedding model, tokenizer, token ceiling, metadata byte ceiling,
  and canonical serialization;
- executable Serving Record and Record Traceability Lookup schemas, fixtures,
  and validators implementing ADR 0078; and
- an exact processing build and Rulebook Conformance Attestation.

Implementation remains unauthorized.

## Cross-cutting design work still open

The canonical list is in section 18 of
`docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md`. High-impact items are:

1. define how Ask.Legal receives and displays signed coverage status;
2. choose the next jurisdiction-and-material rulebook after the shared record
   contracts are stable;
3. instantiate ADR 0068's Case Proposition packages and profile only after
   implementation authorization, and settle other remaining generative-LLM
   allocations;
4. define Approval validity, reviewer roles, revocation, and emergency authority;
5. define Quarantine ownership, deadlines, escalation, and re-entry;
6. define backup isolation, key recovery, retention, recovery targets, and drills;
7. set anomaly, security, capacity, cost, service-level, and deletion policies;
   and
8. settle Azure production-candidate activation and final Pinecone index naming.

## ADR-count forecast

Assessment date: 2026-08-14. This is a planning estimate, not an approved ADR
quota, delivery plan, or complete jurisdiction scope.

The repository currently has 78 accepted ADRs. Based on the open-decision
register, approximately **10 to 15 additional ADRs** should be enough to settle
the presently visible Hong Kong-first and cross-cutting architecture, for an
estimated design total of roughly **88 to 93 ADRs**. The likely remainder is:

- 1 to 2 for remaining Hong Kong LLM workflow boundaries and the still-deferred
  Gazette or other model allocation;
- 0 to 1 for the deferred Hong Kong Instruments & Others review if the user
  reopens it at this design stage;
- 2 for Azure activation, Pinecone naming, and the remaining coverage-status
  interface choices, grouped where they form one coherent decision;
  and
- 7 to 10 for Approval, Quarantine, recovery, anomaly, capacity and cost,
  security, service-level, retention, and deletion policy, with related choices
  grouped when they form one coherent hard-to-reverse decision.

This estimate excludes routine executable schemas, reason-code tables,
fixtures, prompt text, model settings, timeout numbers, and similar reversible
specification values unless they expose a genuinely hard-to-reverse
architecture choice. Those belong in versioned contracts and configuration,
not automatically in separate ADRs.

There is no defensible final ADR count for the entire multi-jurisdiction
project yet because the complete jurisdiction-and-material Source Register is
still open. A materially new jurisdiction-and-material pair may require
approximately 3 to 8 additional ADRs for coverage, source authority, language,
legal-status or treatment, record construction, update behavior, and
conformance where existing common decisions do not transfer. Similar pairs
that genuinely fit existing contracts may require fewer. Therefore, the final
whole-project count depends on the later explicit scope rather than on the
current ADR sequence.

## Stable user preferences and constraints

- Explain choices in simple language and define specialist terms when needed.
- Be intellectually honest; challenge material risks rather than agreeing by
  default.
- Keep all important context handoff-ready in project files; do not rely on
  conversation memory.
- Keep the HKEX Regulatory source model lean: only the five accepted ordinary
  source roles are routine current-database dependencies; optional research
  and source evidence are not automatically sent to the downstream LLM or
  indexed in Pinecone.
- Keep this repository's memory, decisions, priorities, approvals, and working
  state separate from every legacy Ask.Legal workspace. Do not read or update
  another project's continuity without an explicit cross-project request.
- Do not reopen the deferred Instruments & Others or remaining LLM-allocation
  choices unless the user chooses that topic. Hong Kong later-treatment
  allocation is settled by ADR 0053.
- For Hong Kong later-treatment work, use an LLM as the primary semantic
  analyser of variable judgment language. Deterministic rules validate exact
  evidence and constraints; they do not replace semantic reading with keywords.
- Automatically accept and report normal, clear Hong Kong treatment results;
  reserve separate human treatment review for uncertainty or ambiguity and
  for the narrow structural exceptional-change triggers accepted on
  2026-08-13. Importance, novelty, court level, bounded overruling, or volume
  alone is not exceptional.
- Keep every accepted case-treatment relationship internally, but expose a
  budgeted current evidence-based authority summary to the downstream LLM.
  Use no fixed support- or explanation-clause count: include every material
  non-repetitive signal that fits, consolidate equivalent events, keep all
  mandatory warning meaning, and use ranking only for ordering and compression
  near the pinned budget. `CITED_ONLY` stays internal; citation counts and
  numeric authority-strength scores are forbidden.
- Store each resolved treatment once as a directional relationship and derive
  incoming and outgoing internal views from its ID and fingerprint. Do not put
  relationship records, exhaustive outbound lists, graph vectors, a new
  metadata field, or whole-case treatment summaries in Pinecone. Material
  treatment reasoning may appear only in a genuine later Case Proposition;
  an exact future citator feature requires a separately approved graph query
  path.
- For Principles licence expiry, keep serving and reusing the existing records
  but stop updating that exact jurisdiction-and-source scope.
- Classify current HKEX Main Board and GEM Listing Rules as Hong Kong
  Regulatory Materials with serving `type: "regulatory"`; do not call the
  family Policy or mix non-rule guidance into rule records.
- Downstream Ask.Legal receives only the six Pinecone metadata fields, including
  `metadata.text` and `metadata.authority_note`.
- Test Hong Kong later-treatment semantics and deterministic serving
  consequences in separate suites. Use a coverage matrix and paired high-risk
  near-misses rather than an arbitrary fixture count or one blended score.

## Key documentation

- `docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md` — canonical whole-system
  design.
- `docs/design/HONG_KONG_LEGISLATION_DESIGN_AUDIT.md` — current audit verdict,
  classification, corrections, and readiness.
- `docs/design/HONG_KONG_CASE_TREATMENT_CONFORMANCE_CATALOGUE.md` — accepted
  exact 155-case Hong Kong treatment coverage-cell and case table.
- `docs/design/HONG_KONG_REGULATORY_CONFORMANCE_CATALOGUE.md` — canonical
  accepted exact 284-case, 284-cell, and 57-pair Regulatory conformance
  catalogue.
- `docs/design/HONG_KONG_CASE_PROPOSITION_EXTRACTION_CONFORMANCE_CATALOGUE.md`
  — accepted exact 132-case, 132-cell, and 31-pair Case Proposition extraction
  coverage universe.
- `docs/design/HONG_KONG_CASE_TREATMENT_DESIGN_AUDIT.md` — completed treatment
  design audit, corrections, readiness boundary, and remaining decisions.
- `docs/agent/CONTEXT.md` — stable terminology.
- `docs/agent/DECISIONS.md` — settled decisions.
- `docs/adr/0018-use-versioned-jurisdiction-and-material-source-rulebooks.md` —
  common Source Rulebook contract.
- ADRs 0019 through 0042 — Hong Kong coverage, evidence, sources, current and
  baseline rules, fixtures, packaging, and LLM boundary history.
- `docs/adr/0043-defer-final-generative-llm-task-allocation.md` — current LLM
  allocation state.
- `docs/adr/0044-normalize-hong-kong-current-update-results-and-complete-observation-failure-cases.md`
  — current result semantics and 121-test universe.
- `docs/adr/0045-register-hklii-as-a-non-controlling-automated-discovery-source.md`
  — accepted automated HKLII discovery role, deferred compliance review, and
  originating-source evidence boundary.
- `docs/adr/0075-freeze-the-initial-hkex-regulatory-conformance-catalogue.md`
  — freezes the exact initial Regulatory conformance universe.
- `docs/adr/0076-use-change-gated-two-pass-hybrid-analysis-for-hkex-regulatory-materials.md`
  — settles Regulatory deterministic and generative-LLM proposal allocation.
- `docs/adr/0077-admit-hkex-multilingual-retrieval-and-downstream-answer-behavior-separately.md`
  — settles separate multilingual retrieval, answer, and complete-path
  admission.
- `docs/adr/0078-define-serving-record-and-record-traceability-lookup-encoding.md`
  — settles the closed Serving Record, canonical content and note
  fingerprints, traceability entry, reusable Release-Scope shards, root
  manifest, and complete one-to-one validation encoding.
- `docs/adr/0046-limit-ordinary-hong-kong-case-coverage-to-binding-courts.md`
  — accepted Hong Kong court and written-decision coverage boundary.
- `docs/adr/0047-serve-hong-kong-case-propositions-in-original-language-by-default.md`
  — accepted original-language serving, Judiciary-translation evidence, and
  cross-language evaluation boundary.
- `docs/adr/0048-account-for-every-official-hong-kong-judgment-listing-entry.md`
  — accepted official listing, judicial-decision, artifact, acquisition, and
  three-part completeness-accounting boundary.
- `docs/adr/0049-establish-the-first-hong-kong-cases-current-authority-baseline.md`
  — accepted court-year scope, corpus-wide treatment, no-age-cutoff, and first-
  baseline completeness boundary.
- `docs/adr/0050-use-one-standardized-authority-note-metadata-field.md`
  — accepted universal six-field serving contract, controlled warning-and-
  support grammar, query delivery, embedding exclusion, and identity behavior.
- `docs/adr/0052-update-hong-kong-cases-through-bounded-impact-reconciliation.md`
  — accepted ordinary-update, transitive impact, reuse, outcome, outage, and
  exact HKLII discovery boundary for Hong Kong Cases.
- `docs/adr/0053-use-staged-hybrid-analysis-for-hong-kong-later-treatment.md`
  — accepted whole-judgment discovery, candidate-level LLM proposal,
  deterministic validation, and Legal Desk decision boundary.
- `docs/adr/0054-classify-hkex-listing-rules-as-hong-kong-regulatory-materials.md`
  — accepted Hong Kong Regulatory family, serving type, Main Board and GEM
  scope, source precedence, effective-state, original serving layout later
  amended by ADR 0072, and guidance exclusion boundary.
- `docs/adr/0055-use-immutable-selection-transitions-for-hong-kong-case-treatment.md`
  — accepted exact reuse, successor, reselection, retirement, partial-
  retirement, uncertainty, embedding-reuse, and acyclic-lineage behavior for
  Hong Kong case treatment.
- `docs/adr/0056-separate-semantic-evaluations-from-deterministic-hong-kong-treatment-fixtures.md`
  — accepted two-suite, coverage-driven conformance boundary separating LLM
  semantic evaluation from byte-exact deterministic contract fixtures.
- `docs/adr/0057-use-strict-non-leaking-hong-kong-treatment-conformance-packages.md`
  — accepted permanent non-answer-bearing IDs, strict semantic and
  deterministic manifests, expected-artifact roles, catalogue completeness,
  coverage-matrix semantics, hashing, and no-side-effect requirements.
- `docs/adr/0058-store-one-directional-case-treatment-relationship-with-two-internal-views.md`
  — accepted single relationship, incoming and outgoing projection, immutable
  correction, and Pinecone serving boundary.
- `docs/adr/0059-freeze-the-initial-hong-kong-treatment-conformance-catalogue.md`
  — accepted frozen 155-case, 155-cell, and 21-pair initial conformance
  universe and immutable expansion rules.
- `docs/adr/0060-define-the-hong-kong-case-proposition-output-and-evidence-contract.md`
  — accepted proposition qualification, labelled serving text, exact judgment
  support, one-record, coverage, zero-record, and Quarantine boundary; ADR 0065
  later allocates the method without changing this output contract.
- `docs/adr/0061-define-hong-kong-case-proposition-split-and-merge-rules.md`
  — accepted independent-use and integrity boundaries, opinion and adoption
  rules, overlong-record Quarantine, and processing-correction lineage.
- `docs/adr/0062-define-the-hong-kong-case-proposition-coverage-ledger.md`
  — accepted exhaustive source-unit, dependency, candidate, evidence-role,
  completion-result, traceability, and exact zero-proposition accounting.
- `docs/adr/0063-separate-semantic-evaluation-from-deterministic-hong-kong-case-proposition-conformance.md`
  — accepted semantic-versus-deterministic suite boundary, adjudicated
  Reference Proposition Maps, branch-driven coverage, critical errors,
  complete-workflow admission, and separate retrieval gate.
- `docs/adr/0064-freeze-the-initial-hong-kong-case-proposition-extraction-conformance-catalogue.md`
  — accepted frozen 132-case, 132-cell, and 31-pair initial Case Proposition
  extraction conformance universe and immutable expansion rules.
- `docs/adr/0065-use-two-pass-hybrid-analysis-for-hong-kong-case-proposition-extraction.md`
  — accepted deterministic admission and finalization around separate LLM
  analysis and challenge passes, exact objection reconciliation, Legal Desk
  acceptance, narrow human review, and strict permission boundaries.
- `docs/adr/0066-define-the-hong-kong-case-proposition-llm-task-contracts.md`
  — accepted task-family IDs, closed request kinds, common evidence envelope,
  strict structured responses, complete long-judgment handling, immutable
  Evidence Range IDs, independent challenge, no-confidence, failure, repair,
  reuse, storage, and capability boundaries.
- `docs/adr/0067-admit-and-monitor-complete-hong-kong-case-proposition-workflows.md`
  — accepted complete-workflow identity and lifecycle, 20% context reserve,
  evaluation repetitions and gates, bounded attempts, cost reservation,
  provider-data conditions, monitoring, suspension, and revalidation policy.
- `docs/adr/0068-package-hong-kong-case-proposition-evaluations-and-admission-profiles.md`
  — accepted non-circular Evaluation Suite Package, protected evidence views,
  branch-driven sealed real selection, Reference Map adjudication, evaluator
  and run statuses, pre-frozen profile values, and dual-attested admission
  binding.
- `docs/adr/0069-account-for-every-hkex-listing-rule-component.md`
  — accepted immutable HKEX component-inventory, membership, board ownership,
  effective-state, disposition, processing, completeness, shared-artifact,
  update, and no-change contract.
- `docs/adr/0070-use-a-lean-hkex-regulatory-source-register.md`
  — accepted five-role current-source set, union-based inventory, bounded
  outages, deterministic monitoring, supplemental-trigger, approval-inference,
  optional-evidence, and downstream-LLM boundary.
- `docs/adr/0071-decide-hkex-effective-state-per-applicability-branch.md`
  — accepted branch-level effective-state, derived component summary,
  fixed-date, external-trigger, transition, retirement, source-lag,
  disposition, and no-reconstruction rules.
- `docs/adr/0072-serve-hkex-regulatory-materials-in-english-only.md`
  — accepted prevailing-English serving text, optional non-serving Chinese
  evidence, Chinese-query evaluation, prohibited fabricated translation, and
  no-silent-fallback contract.
- `docs/adr/0073-construct-complete-source-faithful-english-hkex-records.md`
  — accepted class-specific complete English record units, canonical renderer,
  minimum dependency closure, non-recursive cross-references, recursive
  official-structure partitioning, and exact source-unit coverage proof.
- `docs/adr/0074-use-two-linked-conformance-layers-for-hkex-regulatory-materials.md`
  — accepted evidence-to-decision and deterministic decision-to-artifact
  conformance layers, strict package and catalogue mechanics, frozen coverage
  matrix, high-risk pairs, critical errors, reproducibility, and separate
  build-attestation boundary.
- `docs/adr/0081-allow-official-hkel-assisted-copies-for-current-and-reconstructed-text.md`
  — accepts the latest applicable official HKeL verified or assisted copies
  for ordinary current records, reconstruction bases, and warned unchanged-
  text fallbacks while preserving exact reconciliation and traceability.
- `docs/adr/0082-use-a-closed-deterministic-hong-kong-reconstruction-operation-registry.md`
  — freezes eight source-backed amendment operation classes, closed target and
  before-state rules, atomic authentic-language execution, fallback, and
  plan/report traceability.
- `docs/adr/0083-freeze-the-hong-kong-reconstruction-conformance-catalogue.md`
  — freezes the initial two-layer catalogue, expanded by ADRs 0086 and 0087 to
  63 cases, 63 cells, and 35 pairs, with strict pass and package boundaries.
- `docs/design/HONG_KONG_RECONSTRUCTION_CONFORMANCE_CATALOGUE.md`
  — contains every frozen reconstruction case scenario, required result, and
  controlled-pair relationship.
- `docs/adr/0084-define-the-hong-kong-reconstruction-plan-and-execution-report-contracts.md`
  — fixes strict immutable Plan and Report schemas, identities, event and
  operation bindings, result accounting, reproducibility, and serving
  isolation.
- `docs/adr/0085-define-the-reconstructed-consolidation-artifact-contract.md`
  — fixes the immutable bilingual final-tree package, exact source-unit
  derivation, coverage and identity proofs, and ordinary renderer input.
- `docs/adr/0086-reconcile-reconstructed-hong-kong-legislation-with-later-hkel.md`
  — fixes scalable monitoring, common-basis comparison, HKeL replacement,
  defect attribution, bounded suspension, impact fallback, and safe restart.
- `docs/adr/0087-require-attested-reconstruction-capability-before-processing-or-promotion.md`
  — fixes exact capability-profile, attestation, candidate-processing
  activation, suspension, runtime, and separate promotion-Approval gates.

## Verified prior research

Read-only official-source research on 2026-08-11 established the roles encoded
in ADRs 0022, 0025, 0026, 0028, 0031, and 0032, including HKeL verified copies,
current and past XML inventories, electronic Editorial Records, GLD Gazette
products and archival escalation, the LegCo Bills Database, and the Basic Law
portal. No corpus package was downloaded. Read-only HKLII checking established
the technical limitations supporting its current non-controlling Fact
Authority. The user has separately directed that legal and policy review not
block design or later implementation.

Read-only official-source research on 2026-08-12 established that the HKEX
Listing Rules are made under section 23 of the Securities and Futures Ordinance
and approved under section 24; the Exchange is the front-line listing
regulator; HKEX-maintained consolidated PDFs prevail over the
Thomson Reuters-maintained presentation; English prevails over the official
Chinese translation; formal rule components and unincorporated guidance are
distinguished; and amendments may have future, conditional, split, or
cohort-specific effective arrangements. No source artifact was downloaded.

Read-only official-source inspection on 2026-08-14 confirmed the separately
published HKEX catalogue, consolidated rulebooks, Regulatory Forms, Fees Rules,
and update products, plus the standing SFC statement that Listing Rule changes
require approval. It did not identify a dependable public SFC product exposing
one separate approval notice for every HKEX update. ADR 0070 therefore uses the
lean five-role current-source set and an explicit final-publication approval
inference instead of inventing a per-update approval feed. No source artifact
was downloaded. Updates 153, 152, and 150 also confirmed split fixed dates,
external-event conditions, and cohort-specific transitions informing ADR
0071's applicability-branch decision. Current official English and Chinese
rulebook pages confirm separate language publications, English precedence,
parallel Main Board and GEM structures, and separately published Forms and
Fees products informing ADR 0072's English-only serving decision.

Read-only official-source inspection on 2026-08-14 additionally confirmed that
current HKEX products expose large term-by-term definition rules, separately
identified Practice Notes, part-based Regulatory Forms, and fee tables whose
headers, brackets, calculations, and notes carry meaning. These structures
inform ADR 0073's class-specific record boundaries. No source artifact was
downloaded.

## Validation status

Current documentation validation passed on 2026-08-14:

- `git diff --check` and touched-file trailing-whitespace checks reported no
  errors;
- all 86 ADRs have accepted parseable YAML frontmatter and valid four-digit ADR
  references;
- all 98 Markdown files have balanced code fences;
- all 97 local documentation links in `README.md` resolve, and all 104 local
  links across the repository resolve;
- the reconstruction catalogue contains exactly 32 evidence-to-plan cases, 31
  plan-to-artifact cases, 63 matching primary cells, and 35 controlled pairs;
- the frozen HKEX Regulatory catalogue contains exactly 284 unique direct case
  IDs and matching primary cells in checkpoint counts
  `62/51/30/35/24/20/24/38`;
- all 57 HKEX Regulatory pair IDs exist with exactly one positive and one near-
  miss member and no undeclared or unused pair;
- the five conceptual HKeL catalogues contain exactly 89 unique fixture IDs;
- ADR 0033 contains exactly 18 current-update case IDs;
- ADR 0034 contains exactly 14 first-baseline case IDs;
- all 15 `HKLEG-CURRENT-*` rules have direct case coverage;
- all 12 `HKLEG-BASE-*` rules have direct case coverage;
- ADR 0032 still contains exactly 14 unique Hong Kong Registered Source IDs;
- the canonical design has 23 Mermaid diagrams and 60 balanced fence lines;
- the exact approved reconstruction authority note appears identically in ADRs
  0080 and 0081, the canonical design, the decision log, and this working state;
- all five normative JSON examples in ADR 0078 parse, and its five example
  `rec_`, `rtl_`, and `rts_` IDs have their exact 48-lowercase-hex bodies;
- current serving-contract language uses `metadata.authority_note`; remaining
  references to the former `warning` field occur only where its supersession is
  recorded historically;
- approved Regulatory Materials consistently use `metadata.type` value
  `"regulatory"`, retain the six-field envelope, and do not treat unknown-type
  fallback as application compatibility; and
- the accepted high `EXCEPTIONAL_CHANGE_REVIEW` bar is consistent across the
  glossary, decision log, ADR 0053, and canonical design; clear bounded
  overruling and evidence-backed reinstatement are automated and reported,
  while uncertainty and missing rules remain review gates; and
- budget-based Hong Kong case-treatment rendering is consistent across ADRs
  0014 and 0050 and the canonical design: all distinct warning meanings are
  mandatory, material non-repetitive support and explanation have no fixed
  clause cap, equivalent events consolidate, `CITED_ONLY` stays internal, and
  citation-count or numerical authority scoring is forbidden; and
- ADR 0055 consistently separates immutable forward Search Record lineage from
  append-only selection history: new payloads receive successors, exact former
  supported records may be reselected, full overruling has no successor, and
  partial overruling cannot invent a narrower proposition; and
- ADR 0056 consistently separates semantic model evaluation from deterministic
  exact-output fixtures, uses coverage rather than an arbitrary fixture count,
  requires paired high-risk near-misses, and confines critical-error zero
  tolerance to the frozen admission set while retaining runtime controls; and
- ADR 0057 consistently uses non-answer-bearing permanent IDs, strict declared
  packages, explicit `EXACT`/`NONE`/`NOT_APPLICABLE` artifact states, a frozen
  coverage matrix rather than discovery or counts, non-leaking model packets,
  and deterministic no-side-effect and reproducibility assertions; and
- ADR 0058 consistently stores one directional treatment relationship, derives
  incoming and outgoing views with the same ID and fingerprint, preserves
  superseded relationships immutably, and keeps relationship records,
  exhaustive outbound lists, and graph vectors outside Pinecone; and
- the completed Hong Kong treatment design audit separates treatment classes
  from appellate dispositions, verifies the accepted evidence-to-serving
  chain, identifies later specification and task-admission work without
  mislabelling it as a policy contradiction, and found no further design issue
  preventing the now-completed catalogue approval; and
- the accepted Hong Kong case-treatment catalogue contains exactly 155 direct
  case rows in the declared 13/40/32/22/14/12/22 group counts and exactly 21
  declared high-risk pairs with two used members each; and
- ADR 0059 consistently freezes those 155 cases, 155 primary coverage cells,
  and 21 pairs without treating the count as a permanent ceiling or
  authorizing executable packages, model admission, or implementation; and
- ADR 0060 consistently requires one attributed material legal answer per
  proposition record, a labelled derived statement plus minimum exact original-
  language judgment support in `metadata.text`, complete judgment-and-opinion
  coverage, honest zero-record results, and Quarantine for unresolved possible
  propositions; ADR 0065 separately settles the extraction allocation; and
- ADR 0061 consistently splits only independently usable legal answers, keeps
  controlling elements and qualifications together, deduplicates only the
  same attributed proposition, preserves multi-opinion boundaries and exact
  adoption, quarantines indivisible overlong propositions, and uses immutable
  processing-correction lineage without choosing the extraction method; and
- ADR 0062 consistently binds one immutable ledger to one exact judgment
  version and complete ordered source-unit inventory, accounts for every
  dependency and candidate, distinguishes complete, Quarantine, blocked, and
  invalid results, requires an exact zero-proposition proof, keeps the ledger
  outside Pinecone, and remains compatible with ADR 0065's allocation; and
- ADR 0063 consistently separates semantic legal understanding from exact
  deterministic conformance, uses hidden adjudicated Reference Proposition
  Maps and branch-driven paired coverage, binds admission to one complete
  workflow, forbids critical-error compensation, retains runtime controls,
  and separates retrieval quality; ADR 0065 separately settles the high-level
  extraction allocation; and
- ADR 0064 and its accepted catalogue consistently freeze exactly 132 direct
  cases, 132 matching primary coverage cells, the seven group counts
  `18/18/22/20/20/16/18`, and 31 complete high-risk pairs, retain mandatory
  sealed real-judgment extension, and use immutable non-answer-bearing IDs. A
  validation-discovered omitted `P013 +` row label was synchronized with the
  already accepted pair index without changing any scenario, result, count, or
  membership; and
- ADR 0065 consistently assigns exact source facts, complete structure,
  validation, objection reconciliation, identities, rendering, and
  finalization to deterministic processing; assigns legal-meaning proposal and
  independent semantic challenge to two bounded LLM passes; retains Legal Desk
  acceptance and exact narrow human-review triggers; and keeps current
  authority, release, Pinecone, Approval, promotion, and routing outside
  extraction; and
- ADR 0066 consistently fixes two stable Case Proposition semantic task
  families and their closed request kinds, treats one pass as complete judgment
  coverage rather than one provider call, excludes translations and
  predecessor answers by default, requires immutable Evidence Range IDs instead
  of model-authored quotations, forbids numeric model confidence, and retains
  strict validation, independent challenge, capability, failure, and reuse
  boundaries; and
- ADR 0067 consistently binds admission to one exact complete workflow, fixes
  a 20% minimum context reserve, all 132 synthetic cases plus the sealed real-
  judgment extension, three ordinary and five high-risk semantic repetitions,
  two exact deterministic runs, no critical errors, bounded attempts, pre-
  reserved judgment cost, weekly canaries, a complete suite at least every 90
  days, automatic suspension, and evidence-backed revalidation and restart,
  while leaving provider, model, executable package, ordinary threshold, and
  other evidence-derived profile values open; and
- ADR 0068 consistently separates the immutable suite, frozen candidate
  profile, complete run set, and final dual-attested admission; defines
  protected model, evaluator, and adjudication views; uses branch-driven
  sealed real-judgment selection without claiming training-data novelty;
  freezes maps and evidence-derived values before scoring; preserves invalid,
  blocked, failed, and not-run outcomes distinctly; and leaves every actual
  executable package, candidate, value, run, and attestation uncreated; and
- ADR 0069 consistently requires immutable cutoff-bound Main Board and GEM
  component inventories, accounts for every entry in a declared registered
  universe, separates membership, ownership, effective state, disposition,
  processing and readiness, prevents shared artifacts from merging board
  identity, preserves scope-bounded failure, and leaves the changing component
  rows and actual endpoint records as future artifacts; and
- ADR 0070 contains exactly five ordinary HKEX current-source IDs, defines
  their separate Fact Authorities, reconciled-union inventory, bounded outage
  behavior, daily deterministic checks, optional and on-demand evidence,
  conditional-trigger and approval-inference rules, and keeps all source
  material outside downstream LLM context and Pinecone by default; and
- ADR 0071 consistently decides state per applicability branch, keeps complete
  concurrent transitions, requires current-product reconciliation after dates
  and triggers, forbids reconstruction, and maps unknown state to Quarantine;
  and
- ADR 0072 consistently serves prevailing English only, leaves Chinese outside
  the ordinary release and Pinecone paths, requires evaluated Chinese-query
  behavior, and prohibits fabricated Chinese source text; and
- ADR 0073 consistently uses class-specific complete official English units,
  bounded exact governing context, non-recursive cross-references, a closed
  canonical renderer, exact token and byte fit checks, recursive official-
  structure partitioning, and exhaustive source-unit coverage without treating
  complete accounting as serving readiness; and
- ADR 0074 consistently separates evidence-to-decision from exact decision-to-
  artifact conformance, uses strict explicit catalogues and one branch-driven
  coverage matrix, prevents answer leakage, requires direct rule and result-
  branch coverage and paired high-risk cases, forbids critical-error
  compensation, and separates package validity, build attestation, real-source
  currency, retrieval, and production authority; and
- ADR 0075 and the canonical catalogue consistently freeze 284 direct cases,
  284 matching primary cells, the eight checkpoint counts
  `62/51/30/35/24/20/24/38`, and 57 complete high-risk pairs without treating
  those counts as an implementation or production authorization; and
- ADR 0076 consistently reserves four named update and record analysis-and-
  challenge tasks for change-gated semantic proposals, keeps exact processing
  and finalization deterministic, and leaves final decisions with the Legal
  Desk under narrow human-review triggers; and
- ADR 0077 consistently separates multilingual retrieval, frozen-context
  answer behavior, and complete Ask.Legal query-path admission, while keeping
  Chinese text outside the ordinary Regulatory serving payload unless later
  evidence exposes a genuine redesign choice; and
- ADR 0078 consistently keeps the live record at exactly six metadata strings,
  defines JCS and SHA-256 content and authority-note fingerprints, separates
  identity from payload proof, and uses a complete reusable Release-Scope-
  sharded lookup with exact one-to-one pre-promotion validation and no runtime
  query join; and
- ADRs 0079 and 0081 consistently preserve valid latest applicable official
  HKeL legislation text for analysis during a proved official-consolidation
  gap, require a new
  warned payload and independent coverage notice, permits ordinary-gated record
  construction when no prior serving record exists, forbids current-text claims,
  and is now ADR 0080's fallback without changing the 121-case pre-
  reconstruction Hong Kong Legislation conformance count; and
- ADR 0080 consistently permits only complete evidence-bound deterministic
  bilingual reconstruction, uses ordinary legislation serving and source
  handling with the exact approved warning, selects one result per serving
  unit, and falls back to ADR 0079 when any proof fails; and
- Legal Desk language is consistent across the glossary, decision log,
  canonical design, ADRs 0018, 0039, 0042, and 0074, and current handoff: it is
  one jurisdiction-and-material rule-bound logical authority with an
  accountable owner and immutable decisions, not an LLM, universal human queue,
  source connector, renderer, promotion reviewer, or credentialed production
  actor; and
- stale claims of a final two-task LLM allocation, a 119-test universe, and 16
  current-update cases are absent from current documentation.

## Authorization state

Documentation changes, read-only public-source inspection, and local validation
only. No application implementation, dependency installation, corpus or source-
artifact acquisition, AI or embedding provider call, release publication,
Pinecone or backup operation, deployment, Azure or routing change, commit,
push, or other remote mutation has been performed or authorized.
