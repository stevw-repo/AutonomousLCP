# Hong Kong Regulatory Materials Conformance Catalogue

Status: **Accepted and frozen by ADR 0075**

Updated: 2026-08-14

This is the canonical working design for ADR 0074's exact initial
`hk-regulatory` coverage-cell and case catalogue. It will eventually contain
every permanent direct case, matching primary coverage cell, and high-risk
pair. It does not yet freeze case IDs, row counts, pair membership, executable
JSON, fixture bytes, models, prompts, thresholds, provider calls, or production
actions.

The user accepted the scalable selection method and the first coverage group
on 2026-08-14. A later complete row-by-row audit must expand every accepted
requirement below into exact cases, prove that every applicable ADR and
rulebook branch has a direct primary case, and only then freeze the identifiers
and resulting count.

## Catalogue construction state

| Coverage group | State | Remaining work before freeze |
|---|---|---|
| 1. Source Fact Authority, membership, and board ownership | Accepted requirements | Expand into exact decision and deterministic rows; assign primary cells and high-risk pairs |
| 2. Applicability-branch effective state and transition | Accepted requirements | Expand into exact branch-decision, summary, disposition, and failure rows; assign primary cells and high-risk pairs |
| 3. English language authority and optional Chinese evidence | Settled from ADR 0072 | Expand into exact evidence, payload, identity, and failure rows; assign primary cells and high-risk pairs |
| 4. Record boundaries, dependencies, and cross-references | Settled from ADR 0073 | Expand into exact boundary, dependency, definition, list, note, and reference rows; assign primary cells and high-risk pairs |
| 5. Tables, Fees Rules, Regulatory Forms, rendering, and partitioning | Settled from ADR 0073 | Expand into exact presentation, measurement, partition, and failure rows; assign primary cells and high-risk pairs |
| 6. Source-unit coverage, identity, readiness, package integrity, and forbidden effects | Settled from ADRs 0011, 0016, 0069, 0073, and 0074 | Expand into exact proof, lineage, readiness, package, reproducibility, and safety rows; assign primary cells and high-risk pairs |

These groups organize the design conversation. ADR 0074's layer and checkpoint
names determine final executable placement. One combined case may provide
secondary evidence for several groups but cannot replace a missing direct
primary branch case.

## Accepted selection rule

The catalogue must:

- directly test every stable legal and technical result branch;
- test both controlled sides of every designated high-risk boundary;
- directly test every distinct mechanical failure or result code;
- add combined cases only when interaction can change the answer; and
- derive the final count from the audited rows rather than a target or cap.

It does not form the Cartesian product of every independent source, state,
language, boundary, renderer, coverage, and identity fact.

## Coverage group 1 — Source Fact Authority, membership, and board ownership

### Accepted decision boundary

This group proves three questions:

1. what fact each Registered Source role may and may not establish;
2. whether an observed item is a rule component, evidence only, an excluded
   non-rule item, or unresolved; and
3. whether every accepted rule-component instance belongs to exactly one Main
   Board or GEM Release Scope.

The evidence-to-decision layer proves the accepted Legal Desk answer. The
decision-to-artifact deterministic layer proves complete enumeration,
one-result accounting, owner arithmetic, bounded failure consequences, and
exact zero-output consequences.

### Five-role Fact Authority

The exact rows must give each ordinary Registered Source role at least one
direct permitted-use case and one controlled overreach case:

| Source role | Permitted fact under test | Forbidden overreach under test |
|---|---|---|
| Rulebook catalogue | Top-level Main Board and GEM product families, board association, and current product locators | Individual rule wording, effective state, or a complete component list |
| Consolidated rulebooks | Prevailing current English wording and contained official structure | Separately published Forms or Fees Rules, amendment cause, or external-trigger occurrence |
| Regulatory Forms | Separate Form inventory, express membership, board ownership, and prevailing English content | Ordinary rules, Fees Rules, amendment cause, or external-trigger occurrence |
| Fees Rules | Separate Fees Rule inventory, express membership, board ownership, and prevailing English content | Ordinary rules, Regulatory Forms, amendment cause, or external-trigger occurrence |
| Final rule updates | Final changed words, stated dates, conditions, transitions, mappings, and withdrawals | External-trigger occurrence, replacement of current compiled text, or present effect by itself |

Direct cases must also prove:

- the complete source-entry universe is the reconciled union of all five roles;
- one page, search count, navigation tree, table of contents, or successful
  source role cannot establish that union;
- optional Thomson Reuters material may open investigation but cannot override
  an accepted controlling HKEX product;
- a relevant change to pinned precedence, language, inclusion, exclusion, or
  approval-framework evidence opens Source Contract Review;
- an ordinary final HKEX update, matching current product, and pinned standing
  framework may support the exact
  `APPROVAL_SATISFIED_BY_FINAL_PUBLICATION` inference;
- a consultation, proposal, draft, pending-approval statement, or item that
  requires direct approval evidence cannot use that inference;
- complete fresh reconciled Observations for all five roles may produce
  `SUPPORTED_NO_CHANGE`, while a stale, partial, failed, or unreconciled role
  cannot; and
- a proved board-bounded failure affects only that board, while an unbounded
  shared gap affects both boards. Missing evidence needed only for a bounded
  historical investigation blocks that investigation rather than an otherwise
  supported current release.

### Membership results

Every observed source entry must receive exactly one of these accepted results:

| Result | Required meaning and consequence |
|---|---|
| `RULE_COMPONENT` | Exact official evidence proves rulebook membership; continue to board ownership and later state processing |
| `EVIDENCE_ONLY` | Preserve the item for its assigned amendment, approval, transition, interpretation, source-relationship, or review fact; create no rule record |
| `EXCLUDED_NON_RULE` | The item is outside the accepted rule corpus; create no rule-component state, owner, or Search Record |
| `UNRESOLVED_MEMBERSHIP` | The evidence cannot safely choose another result; assign no rule-component owner and quarantine the smallest affected boundary |

Direct positive rule-component coverage must include a Chapter, ordinary rule
or subrule, incorporated note, appendix, Practice Note, Regulatory Form, Fees
Rule, and another expressly included component.

Direct excluded-non-rule coverage must include guidance, an FAQ, consultation
material, a listing or review decision, a circular or general announcement,
and a checklist, template, or form not expressly incorporated into the Listing
Rules.

Evidence-only coverage must include the distinct uses of final-update,
approval, transition-or-trigger, and source-relationship or interpretation
evidence. Unresolved coverage must include absent, insufficient, and
conflicting membership proof.

Navigation placement, a similar title or number, visual style, usefulness,
HKEX or SFC publication, a link from a rule page, and semantic similarity are
each insufficient without accepted inclusion proof. The row audit must ensure
that these routes cannot silently produce `RULE_COMPONENT`.

### Board ownership and component accounting

Every `RULE_COMPONENT` instance has exactly one owner:

- `HK-REG-HKEX-MAIN-BOARD`; or
- `HK-REG-HKEX-GEM`.

Direct coverage must include correct ownership for each board; one artifact
containing many components; one artifact expressly supporting both rulebooks;
identical or similar wording that does not merge board identities; official
ownership evidence conflicting with website placement; absent and conflicting
board evidence; and missing, duplicate, orphaned, double-owned, and wrong-board
component results.

When one official artifact is expressly part of both rulebooks, the correct
result is one Main Board-owned component instance and one separate GEM-owned
instance that may reference the same preserved artifact. It is never one
ambiguous cross-board component.

### Required high-risk boundaries

The later exact pair index must include at least:

- an incorporated Regulatory Form versus a nearby unincorporated checklist or
  template;
- an expressly incorporated Practice Note or note versus nearby non-rule
  guidance;
- a source used for its permitted Fact Authority versus the same source used
  to claim a forbidden fact;
- one shared artifact correctly producing two board-owned instances versus one
  ambiguous double-owned instance; and
- a board-bounded source failure versus a shared unbounded source gap.

The pair members should differ by one controlled fact where possible.

### Critical errors

No aggregate score may compensate for:

- guidance, an FAQ, consultation, decision, announcement, checklist, template,
  or unincorporated form entering the rule corpus;
- a Main Board component assigned to GEM or a GEM component assigned to Main
  Board;
- one component instance ambiguously owned by both boards;
- an unresolved item made searchable through similarity, convenience, an
  authority note, or model confidence;
- one incomplete source role being treated as the complete source universe;
  or
- a shared unbounded gap being reported as a harmless board-specific failure.

## Coverage group 2 — Applicability-branch effective state and transition

### Accepted decision boundary

Effective state is decided for one exact applicability branch at one immutable
cutoff. One branch binds exact wording to the cohort, transaction, reporting
period, time window, external condition, or other material limitation that
governs its application. A whole update, publication, PDF, Chapter, rule number,
or update number never receives one state merely for convenience.

Every Rule Component Instance may contain several simultaneously preserved
branches. The Legal Desk decides each branch first. The component summary,
material disposition, processing result, and record consequences are separate
derived results and cannot flatten the branch evidence.

### Direct state coverage

The exact rows must directly cover every branch result and its ordinary
consequence:

| Branch state | Required meaning | Ordinary disposition under test |
|---|---|---|
| `CURRENT` | Effective for ordinary application at the cutoff and reconciled to the controlling current English product | Searchable only after every other gate passes |
| `TRANSITIONAL_CURRENT` | Effective only for an exact supported cohort, transaction, period, window, or other material branch | Searchable branch record or records with complete applicability context after every other gate passes |
| `FUTURE_FIXED_DATE` | Final published wording has an exact future effective point | Regulatory Waiting Room |
| `FUTURE_CONDITIONAL` | Final published wording awaits an unproved external condition | Regulatory Waiting Room with targeted trigger monitoring |
| `SUPERSEDED` | A supported successor covers every former current application | Historical and traceable outside Pinecone |
| `WITHDRAWN` | Exact official evidence ends the branch without a supported successor for the same obligation | Historical and traceable outside Pinecone |
| `UNKNOWN` | Permitted fresh evidence cannot safely establish what is operative | Quarantine and no newly current Search Record |
| `NOT_APPLICABLE` | The observed entry is not a Rule Component Instance | No regulatory Search Record |

The rows must keep branch state separate from `PASS`, `BLOCK`, or `QUARANTINE`,
serving disposition, authority-note behavior, and the separate ADR 0005 source-
failure choice.

### Fixed-date boundaries

Direct coverage must include:

- a final branch before its exact effective point remaining
  `FUTURE_FIXED_DATE` while its supported predecessor remains separately
  current;
- cutoffs immediately before and at the effective point, using Hong Kong time
  unless the source expressly controls another time zone;
- an effective branch whose wording and structure reconcile with the
  controlling current product becoming `CURRENT` or
  `TRANSITIONAL_CURRENT`;
- a passed effective point with lagging, omitted, or conflicting controlling
  wording becoming `UNKNOWN` rather than reconstructed current law;
- future wording published in a product before its stated date remaining
  future; and
- ambiguous date, time, or time-zone wording becoming `UNKNOWN` rather than
  receiving invented precision.

### External-condition boundaries

Every conditional case names the exact activating fact and permitted official
Registered Source. Direct coverage must include:

- fresh positive evidence of non-occurrence supporting continued
  `FUTURE_CONDITIONAL` status;
- positive occurrence evidence followed by matching current-product wording;
- an HKEX update describing a condition without proving that the external
  event occurred;
- stale, unavailable, incomplete, or conflicting trigger evidence when the
  event could already have occurred, producing `UNKNOWN` rather than presumed
  non-occurrence;
- proved occurrence followed by conflicting compiled wording, producing
  `UNKNOWN` rather than reconstructed text;
- all-of activation only after every required fact is proved;
- any-of activation after one permitted fact is proved;
- continued any-of future status only while every alternative is positively
  supported as not having occurred; and
- an unresolved any-of alternative producing `UNKNOWN`.

### Transitional and overlapping branches

Direct coverage must include:

- old and new wording concurrently current for different cohorts,
  transactions, reporting periods, or time windows;
- materially different concurrent obligations producing separate complete
  current record responsibilities;
- the same wording with one simple fully stated limitation being eligible for
  one record only when the entire limitation appears in `metadata.text`;
- an open-ended transition remaining current until exact evidence or provable
  cohort exhaustion ends it;
- complete cohort exhaustion with a successor producing `SUPERSEDED` and
  complete exhaustion without a successor producing `WITHDRAWN`;
- partial replacement leaving the remaining predecessor applications
  `TRANSITIONAL_CURRENT`;
- overlapping amendments ordered by supported effective facts rather than
  update numbers; and
- unresolved collision, gap, or precedence conflict producing `UNKNOWN`.

No current record may rely on the downstream LLM to infer an omitted cohort,
period, condition, or branch boundary.

### Supersession, withdrawal, and non-proof

`SUPERSEDED` requires a supported successor covering every former application.
`WITHDRAWN` requires exact official ending evidence and no supported successor
for the same obligation. Direct positive and near-miss coverage must distinguish
complete replacement, partial replacement, and official withdrawal from mere
disappearance, a URL or filename change, renumbering, similar wording, a reused
rule number, or a higher update number. Those aliases and observations alone
prove neither continuity nor retirement.

### Component summaries

The exact rows must prove at least:

- one ordinary current branch derives component summary `CURRENT`;
- one or more materially limited current branches, or concurrently current old
  and new branches, derive `TRANSITIONAL_CURRENT`;
- a still-effective ordinary predecessor plus a pending future amendment
  remains summary `CURRENT`, not transitional;
- one supported future family and no current branch may derive that future
  summary;
- every formerly current branch must qualify before a component summary may be
  `SUPERSEDED` or `WITHDRAWN`;
- any unresolved fact capable of changing the present answer derives
  `UNKNOWN`; and
- mixed future branches that cannot honestly be represented by one summary
  derive `UNKNOWN` unless another accepted rule proves one exact result.

The complete branch decisions remain preserved even when one component summary
is available.

### Technical source failure and serving choice

Technical unavailability without affirmative evidence of a legal change does
not invent a new current-state decision. Separate deterministic consequence
cases must cover ADR 0005's exact alternatives:

- carry forward the last approved release with its last-verified date,
  Coverage Gap, controlled warning, review deadline, and Legal Desk support;
- withhold affected records when continued serving would be materially
  misleading; and
- build no new jurisdiction target when neither course is supported.

A carry-forward remains previously approved, not freshly verified at the new
cutoff.

### Required high-risk boundaries

The later exact pair index must include at least:

- immediately before an effective point versus at that point with a matching
  current product;
- a passed date with matching wording versus a passed date with lagging or
  conflicting wording;
- fresh proof of trigger non-occurrence versus stale trigger evidence when the
  event could have occurred;
- a future amendment with an ordinary current predecessor versus genuinely
  concurrent transitional branches;
- complete replacement versus partial replacement;
- official withdrawal versus unexplained disappearance; and
- complete applicability context versus a payload that leaves the downstream
  LLM to infer the branch.

The pair members should differ by one controlled fact where possible.

### Critical errors

No aggregate score may compensate for:

- future wording served as current;
- clock-only promotion at a date without current-product reconciliation;
- external-trigger occurrence inferred from the update that merely states the
  condition;
- missing or conflicting current wording reconstructed, spliced, or silently
  corrected;
- concurrent transitional branches flattened into one universal rule;
- disappearance, renumbering, similarity, or a higher update number treated as
  supersession or withdrawal;
- an open-ended cohort guessed to be exhausted; or
- `UNKNOWN` repaired into a current result through an authority note, model
  confidence, or human-friendly prose.

## Coverage group 3 — English language authority and optional Chinese evidence

### Settled decision boundary

The complete prevailing English HKEX product is the required wording and
structure evidence and the only ordinary serving source text. Official
Traditional-Chinese translations are optional non-serving evidence. They do
not create a translation-freshness release gate, Chinese source block,
Chinese-only duplicate, parallel vector, or alternate wording authority.

This group is an exact consequence of ADR 0072 and requires no further product
choice before row expansion.

### Required evidence and payload coverage

Direct cases must cover:

- complete current English evidence with no Chinese artifact proceeding
  through later gates;
- complete English evidence with a missing, late, stale, or unavailable
  optional Chinese artifact remaining eligible;
- a Chinese discrepancy confined to the optional translation remaining non-
  blocking and producing no serving-payload change;
- a Chinese signal that positively exposes a possible English board,
  component, location, identity, version, wording, effective-state, or
  completeness defect opening the smallest English investigation and blocking
  or quarantining the affected boundary;
- missing, unreadable, stale, conflicting, or incomplete required English
  evidence blocking or quarantining the affected boundary even when Chinese
  text is available;
- prohibited Chinese substitution, LLM translation, online-rulebook repair,
  similarity repair, and warning-based repair of unavailable English;
- exact English `metadata.text` containing no Chinese source block;
- no Chinese-only duplicate Search Record and no parallel Chinese vector;
- optional Chinese preservation and traceability outside Pinecone when it was
  actually used; and
- bounded Chinese observation or acquisition without a permanent release-
  blocking Chinese monitoring requirement or complete alignment map.

### Serving and identity consequences

Direct deterministic cases must prove:

- the exact source-native English locator, heading, numbering, wording,
  punctuation, order, table relationships, Form labels, fee entries,
  transition text, and required dependencies survive canonical rendering;
- source URLs, internal IDs, fingerprints, operational dates, reviewer prose,
  model output, and optional Chinese evidence remain outside `metadata.text`;
- every Regulatory `metadata.authority_note` is an English string and is exact
  `"None"` when no approved clause applies;
- a Chinese-only change creates neither a new Search Record nor an embedding
  action when it exposes no English defect and changes no serving field;
- a Chinese signal that invalidates an accepted English decision blocks reuse
  until the English issue is resolved; and
- a material English text, applicability, dependency, partition, or authority-
  note change follows the ordinary immutable Search Record identity rules.

Chinese-query retrieval quality and downstream Chinese explanation behavior
remain a later admission suite. This conformance group proves the source and
payload boundary, not multilingual retrieval performance.

### Required high-risk boundaries

The later exact pair index must include at least:

- complete English evidence with no Chinese artifact versus missing English
  evidence with available Chinese text;
- a harmless Chinese-only discrepancy versus a Chinese signal exposing a
  possible controlling English defect;
- optional Chinese evidence preserved outside serving versus Chinese inserted
  into `metadata.text`;
- a Chinese-only publication change versus a material English serving change;
  and
- an English-only record versus an otherwise identical Chinese-only duplicate
  or parallel-vector proposal.

### Critical errors

No aggregate score may compensate for Chinese text substituted for required
English, fabricated or model-generated source wording, Chinese source text in
the ordinary serving payload, a Chinese-only duplicate or parallel vector,
optional-Chinese staleness blocking an otherwise supported English record, or
a positive Chinese defect signal being ignored.

## Coverage group 4 — Record boundaries, dependencies, and cross-references

### Settled decision boundary

Record boundaries follow official English structure and legal meaning before
size optimization. The normal unit is the smallest complete official rule-
bearing unit that can be used independently with its minimum required
governing context. The system neither packs unrelated short units nor splits a
normal unit merely to create smaller vectors.

This group is an exact consequence of ADR 0073 and requires no further product
choice before row expansion.

### Ordinary and class-specific boundaries

Direct cases must cover:

- one coherent complete rule remaining one record responsibility;
- independently usable numbered subrules becoming separate responsibilities;
- cumulative conditions, alternatives, conjunctions, shared lead-ins,
  qualifications, exceptions, provisos, and attached notes remaining together
  whenever their logic is inseparable;
- one independently usable list item carrying its grammatical parent lead-in;
- one inseparable list group remaining intact;
- a definition collection producing one record responsibility per defined term
  without losing applicable global scope text;
- a global definition remaining a separate searchable definition record rather
  than being copied into every use;
- a local definition remaining with the branch it governs;
- an incorporated note staying with the exact rule, definition, or branch it
  qualifies;
- appendix and Practice Note paragraphs following the same complete-unit test;
- a website container, navigation label, page, line wrap, table cell, blank
  field, or renderer-created part not becoming a Legal Location merely from
  presentation; and
- ambiguous source structure opening Source Contract Review or quarantining
  the smallest affected branch rather than receiving a guessed boundary.

### Governing dependency closure

Direct cases must distinguish required governing context from useful
background. Required context includes only exact source-supported material
whose omission would materially change the primary unit, such as a grammatical
lead-in, local definition or scope, qualification, exception, proviso,
transition, incorporated note, table header or unit, Form instruction, or exact
official parent.

Every repeated dependency must be labelled `Required governing context`, point
internally to its one primary source-unit owner and fingerprint, and not count
as primary coverage again. Helpful background, retrieval enrichment, generic
overlap, and copied global definitions are not dependency closure.

### Cross-reference boundary

Direct cases must cover:

- an ordinary exact cross-reference preserving its referring words and target
  locator;
- an available official target heading added only when it materially assists
  target identification;
- a chained reference represented as internal relationships without recursive
  target-text copying;
- an unresolved target entering the exact review or quarantine path rather
  than being guessed;
- a cross-board reference preserving both board identities and never copying a
  target into the wrong board record;
- a target wording change updating internal relationship or traceability facts
  without rebuilding the referring record when its six serving fields remain
  byte-identical; and
- a proposed child that cannot stand safely with its exact referring words and
  locator remaining with a larger official parent. If no complete faithful unit
  can fit later limits, it is quarantined rather than repaired with copied or
  paraphrased target text.

### Required high-risk boundaries

The later exact pair index must include at least:

- independent subrules versus inseparable cumulative conditions;
- one list item with its required lead-in versus the item stranded without it;
- required governing context versus merely helpful background;
- a global definition kept separate versus a local definition required by one
  branch;
- an incorporated note attached to its owner versus the note stranded in a
  different record;
- exact cross-reference retention versus recursive target copying; and
- a safely independent child versus an unsafe child that must remain with its
  parent.

### Critical errors

No aggregate score may compensate for a qualification, exception, proviso,
condition, note, or governing lead-in being detached from the obligation it
controls; an unofficial or guessed boundary; primary coverage counted twice
through dependency repetition; recursive target-text copying; a cross-board
reference merging identities; useful background treated as mandatory overlap;
or an unsafe child served without the context needed to understand it.

## Coverage group 5 — Tables, Fees Rules, Forms, rendering, and partitioning

### Settled decision boundary

Tables, Fees Rules, and Regulatory Forms use closed source-faithful English
presentation projections. The complete canonical candidate is rendered and
measured before any split. An overlong unit may descend only through proved
official semantic children and uses the fewest valid consecutive parts with
the earliest parts filled as fully as possible.

This group is an exact consequence of ADR 0073 and requires no further product
choice before row expansion. Exact grammar tokens and numeric ceilings remain
later executable contract values; the semantic and algorithmic results are
settled here.

### Tables and Fees Rules

Direct cases must cover:

- a complete table retaining caption, governing lead-in, complete headers,
  column ownership, row order, units, spans, attached notes, and every exact
  label-to-value relationship;
- one legally independent row group becoming a record responsibility while an
  inseparable row group remains together;
- a row-spanning or multi-level header correctly projected onto every value it
  governs;
- a presentation-only table reflow producing byte-identical canonical output;
- a material row, header, unit, amount, or note change producing changed
  canonical output and the corresponding identity consequence;
- one complete fee category or bracket group retaining amount, currency,
  calculation basis, timing, activation condition, and every applicable note;
  and
- prohibited detached table values, amounts without currency, or fees without
  calculation and timing rules.

### Regulatory Forms

Direct cases must cover:

- complete official Part and instruction-group boundaries;
- declarations, undertakings, certifications, and signing requirements kept
  with their governing scope;
- logically connected field groups remaining together;
- blank input areas and selection controls rendered through one closed neutral
  marker vocabulary without inventing completed values;
- a purely presentation-only blank or web control classified explicitly and
  omitted without losing substantive meaning;
- a substantive selection control, declaration, instruction, or signature
  requirement never discarded as presentation; and
- prohibited one-record-per-blank-field fragmentation.

### Canonical renderer

Direct exact-byte cases must cover every required and optional block in ADR
0073's canonical layout, including ordinary unrestricted current context,
material effective context, required governing context, referenced locations,
official heading, and serving-part labels. They must prove:

- exact source wording, numbering, punctuation, capitalization, order, and
  meaningful labels;
- UTF-8 NFC, LF line endings, stable block order, no trailing spaces, and no
  leading or trailing blank lines;
- deterministic omission of inapplicable optional blocks;
- exclusion of URLs, page furniture, web controls, internal IDs, fingerprints,
  operational dates, reviewer prose, model output, and Chinese evidence;
- `metadata.authority_note` remains a separate required English string and the
  embedding input remains `metadata.text` only; and
- ambiguous substantive characters, ownership, or layout fail closed rather
  than being silently normalized or corrected.

### Exact fit and recursive partitioning

Direct cases must cover:

- a complete final payload fitting both hard ceilings exactly;
- token-only overflow, metadata-byte-only overflow, and simultaneous overflow;
- actual context, dependency, reference, table or Form projection, six-field
  strings, `authority_note`, and final `Serving part: X of N` labels included in
  measurement;
- a label-induced overflow discovered only after the real total part count is
  rendered;
- a complete child fitting and remaining whole;
- recursive descent of only an oversized child through its official children;
- construction of the ordered frontier from the largest safe complete units;
- the valid contiguous partition with the fewest parts;
- earliest-full deterministic tie-breaking between equal-part solutions;
- different branches descending to different supported official depths;
- final re-render and remeasurement of every part against both ceilings;
- an indivisible overlong unit with required context entering Quarantine with a
  Coverage Gap; and
- mandatory fixed metadata alone making every part too large, with no futile
  extra text partitioning.

Page, sentence, punctuation, whitespace, token-position, character-count,
visual-column, and sliding-window cuts are direct prohibited cases unless the
same point is independently an official semantic boundary. Governing context
cannot be removed to force a fit, and an unrelated short rule cannot be packed
into an overlong sibling.

### Required high-risk boundaries

The later exact pair index must include at least:

- a complete table value with header and unit versus a detached value;
- a complete fee bracket versus an amount detached from currency, basis, timing,
  or note;
- a substantive Form control versus a presentation-only blank;
- presentation-only reflow versus a material source change;
- exact fit versus overflow caused by the final part label or authority note;
- official-child partitioning versus an arbitrary sentence or token cut; and
- a splittable overlong unit versus an indivisible overlong unit.

### Critical errors

No aggregate score may compensate for a table value losing its header or unit,
a fee losing its currency or calculation basis, a substantive Form obligation
discarded as presentation, an invented completed form value, altered source
text, an arbitrary split, removed governing context, truncated material,
unmeasured final labels or metadata, or an indivisible overlong unit being
served anyway.

## Coverage group 6 — Coverage, identity, readiness, package integrity, and safety

### Settled decision boundary

Every result must prove complete source-unit accounting, exact record and
traceability identity consequences, per-board readiness, strict package
completeness, reproducibility, and absence of forbidden external effects. These
are deterministic controls following ADRs 0011, 0016, 0069, 0073, and 0074.
They require no further product choice before row expansion.

### English source-unit coverage proof

Direct cases must prove that every meaning-bearing current or transitional-
current English unit has exactly one primary owner or one explicit blocked or
quarantined outcome. Separate direct cases cover:

- repeated governing dependencies pointing to their one primary owner and
  exact fingerprint without counting as primary again;
- context-only and presentation-only units receiving explicit classifications;
- every table header, row group, note, Form Part, field group, and meaningful
  control being accounted;
- future branches in the Waiting Room, superseded and withdrawn branches in
  history, unknown branches in Quarantine, and excluded non-rule material
  remaining excluded;
- exact source order and Main Board/GEM ownership;
- missing, duplicated, reordered, orphaned, wrong-board, and unlabelled-
  dependency units; and
- nothing silently dropped, duplicated as primary content, reordered,
  translated, summarized, corrected, or invented.

Complete accounting and serving readiness remain separate. A complete proof
that exposes one quarantined required current unit makes the affected board
not serving-ready. Record count, page count, parser success, and text-presence
checks cannot substitute for the proof.

### Immutable identity and lineage

Direct cases must cover:

- separate Main Board and GEM Search Records even when wording is identical;
- exact reuse when canonical six-field bytes and current legal support remain
  identical;
- append-only reselection of an exact preserved record with renewed support;
- a new Search Record and typed forward lineage for changed primary English
  text, material applicability context, governing dependency closure,
  referenced-location rendering, table or Form projection, canonical partition,
  serving-part label, or `metadata.authority_note`;
- no new Search Record for a URL move, page reflow, navigation change, or other
  presentation-only source change that leaves canonical six-field bytes
  identical;
- a citation, grouping, provenance, alias, or evidence-reference correction
  that leaves serving bytes unchanged creating only a new immutable Record
  Traceability Lookup revision;
- one-to-one, one-to-many, and many-to-one forward lineage with collision and
  cycle rejection; and
- ambiguous continuity entering Quarantine rather than being resolved through
  text similarity, a visible number, URL, title, or alias.

### Traceability and readiness

Every Search Record in the desired inventory must have exactly one matching
Record Traceability Lookup entry binding payload fingerprint, Legal Item,
Official Version, Legal Locations, Release Scope, Corpus Release, evidence
references, and authority-note evidence and rendering fingerprint. Missing,
duplicate, orphaned, mismatched, or wrong-board lookup entries block readiness.

The lookup remains outside the Ask.Legal query path. Its temporary
unavailability after activation is an audit-system incident, not an ordinary
search outage. Every active query path still receives only the six Pinecone
metadata strings.

Per-board readiness cases must distinguish complete accounting with every
required current unit ready, complete accounting exposing a blocked or
quarantined current unit, one proved board-bounded failure, and a shared
unbounded gap. No readiness result authorizes promotion.

### Strict package and catalogue integrity

Direct deterministic cases must cover:

- strict root and case schemas with unknown fields and enums rejected;
- exact declared case, coverage-cell, pair, contract, artifact, input,
  reference, expected-output, path, media-type, role, and SHA-256 inventories;
- package-local normalized relative POSIX paths and rejection of absolute paths,
  parent traversal, empty segments, platform separators, symlinks, URIs,
  network retrieval, globs, dynamic discovery, and undeclared files;
- exact `AVAILABLE`, `INTENTIONALLY_ABSENT`, and `UNREADABLE` input semantics;
- exact `EXACT`, `NONE`, and `NOT_APPLICABLE` expected-artifact semantics,
  including explicit zero-count proof for `NONE`;
- missing required input distinguished from deliberate absence;
- stale, conflicting, wrong-board, or differently versioned evidence supplied
  as explicit available artifacts rather than vague magic states;
- every case primary for a required cell, every required cell directly covered,
  every stable rule and result branch covered, and every pair containing exactly
  one positive and one near-miss member;
- no hidden expected answer, case title, ID, pair role, package path, coverage
  label, critical tag, or adjudication leaking into a proposal component;
- package fingerprints without self-reference cycles and immutable correction
  or supersession rather than in-place answer editing; and
- one valid package remaining distinct from one build-specific Regulatory
  Rulebook Conformance Attestation.

### Reproducibility, hostile input, and forbidden effects

Every deterministic case must match exact canonical bytes. Two isolated clean
runs must produce byte-identical artifacts, measurements, inventories, reports,
and fingerprints. Source text that resembles instructions remains inert legal
evidence and cannot alter tools, contracts, expected results, prompts, paths,
secrets, approval state, or execution.

Direct forbidden-effect cases assert no source, generative-model, embedding,
network, credential, Azure, Pinecone, backup, routing, promotion, production-
store, or undeclared-file access and no live-state mutation. A conformance pass,
package validity, or build attestation authorizes none of those capabilities.

### Required high-risk boundaries

The later exact pair index must include at least:

- complete primary ownership versus one missing, duplicated, or reordered unit;
- complete accounting and serving readiness versus complete accounting that
  exposes one quarantined current unit;
- byte-identical reuse versus a one-byte serving-payload change requiring a new
  record;
- a traceability-only correction versus an `authority_note` change;
- one declared intentionally absent input versus one accidentally missing file;
- explicit `NONE` output versus an absent expected artifact;
- a harmless source-text instruction string versus execution influenced by it;
  and
- a valid isolated conformance run versus any attempted external mutation.

### Critical errors

No aggregate score may compensate for incomplete primary source-unit coverage,
duplicate primary ownership, wrong-board coverage, a required current unit
silently omitted from readiness, mutable Search Record bytes, backward or
cyclic lineage, missing or mismatched traceability, dynamic or undeclared input,
answer leakage, non-reproducible exact artifacts, hostile source text changing
execution, or any forbidden external effect.

## Exact row expansion

Each row below is one direct primary case and one matching primary coverage
cell. A three-digit suffix expands under the case and coverage namespaces shown
for that table. Pair notation `Pnnn +` and `Pnnn -` expands to
`HKREG-PAIR-NNN`; the two members test one controlled high-risk distinction.
One row may participate in more than one pair, but every declared pair has
exactly one positive and one near-miss member.

IDs identify only the checkpoint and permanent ordinal. They do not encode the
board, source, state, expected answer, success, failure, or critical status and
never enter a proposal component's evidence packet.

### A. Source Fact Authority, membership, ownership, and language evidence

Case namespace: `HKREG-DEC-SRC-NNN`

Coverage namespace: `HKREG-COV-DSRC-NNN`

| Suffix | Pair | Synthetic evidence situation | Exact required result |
|---:|---|---|---|
| 001 | P001 + | Complete catalogue identifies the two Listing Rule product families and their market locators | Accept only those top-level family, board-association, and locator facts |
| 002 | P001 - | Catalogue entry is offered as proof of one rule's wording, state, and complete component inventory | Reject the overreach; those facts remain unproved by this role |
| 003 | P002 + | Complete controlling English consolidated rulebook contains one rule and official structure | Accept its prevailing wording and contained structure for the exact board |
| 004 | P002 - | Consolidated rulebook is offered as proof of a separately published Form, Fees Rule, amendment cause, and external trigger | Reject every out-of-role fact |
| 005 | P003 + | Complete Regulatory Forms product expressly identifies a Form as part of one rulebook | Accept the Form inventory, membership, board, and prevailing English content facts |
| 006 | P003 - | Forms product is offered as proof of an ordinary rule, Fees Rule, amendment cause, and trigger occurrence | Reject every out-of-role fact |
| 007 | P004 + | Complete Fees Rules product expressly identifies one fee component | Accept its inventory, membership, board, and prevailing English content facts |
| 008 | P004 - | Fees Rules product is offered as proof of an ordinary rule, Form, amendment cause, and trigger occurrence | Reject every out-of-role fact |
| 009 | P005 + | Accepted final update states exact changed words, mappings, dates, conditions, transitions, and withdrawal facts | Accept only the update's assigned final-change facts |
| 010 | P005 - | Final update alone is offered as proof that an external event occurred and its wording is already the current compiled product | Reject occurrence and present-currentness claims |
| 011 | P006 + | All five due source roles are complete, fresh, declared, and reconcile into one bounded union | Accept the complete source-entry universe for the cutoff |
| 012 | P006 - | One catalogue, search count, navigation tree, or table of contents claims to be the complete universe | Mark the universe incomplete and the affected scope not decision-ready |
| 013 |  | Optional Thomson Reuters presentation conflicts with an accepted HKEX current product | Preserve the discrepancy for investigation; keep the HKEX product controlling |
| 014 |  | Pinned precedence, language, inclusion, exclusion, or approval-framework statement materially changes | Open Source Contract Review and require a new rulebook decision before affected reuse |
| 015 | P007 + | Final HKEX update, matching accepted current product, and pinned standing approval framework all reconcile | Accept `APPROVAL_SATISFIED_BY_FINAL_PUBLICATION` for the ordinary change |
| 016 | P007 - | Consultation, proposal, draft, or pending-approval document is paired with the standing framework | Do not infer approval or current rule effect |
| 017 |  | Exact item says direct approval evidence is required but none is preserved | Block only that decision pending accepted direct evidence |
| 018 | P008 + | Every due role has a complete fresh Observation and exactly matches the accepted predecessor | Produce `SUPPORTED_NO_CHANGE`; create no downstream rebuild work |
| 019 | P008 - | No alert was raised, but one due Observation is stale, partial, failed, or unreconciled | Do not produce `SUPPORTED_NO_CHANGE`; expose the exact gap |
| 020 | P009 + | Consolidated evidence failure is proved to affect only Main Board | Block Main Board only; permit independently complete GEM work to continue |
| 021 | P009 - | Shared catalogue or inventory failure prevents either board's universe from being bounded | Block both boards; do not report a board-specific gap |
| 022 |  | Older update artifact is missing only for one bounded historical investigation | Block that investigation only; do not block an otherwise supported current release |
| 023 |  | Official inclusion evidence identifies a Chapter | `RULE_COMPONENT` with its exact board owner and structure |
| 024 |  | Official inclusion evidence identifies an ordinary rule or subrule | `RULE_COMPONENT` with its exact board owner and structure |
| 025 |  | Official inclusion evidence identifies an incorporated note | `RULE_COMPONENT` attached to its exact owning location |
| 026 |  | Official inclusion evidence identifies an appendix | `RULE_COMPONENT` with its exact board owner and hierarchy |
| 027 | P010 + | Official inclusion evidence expressly incorporates a Practice Note | `RULE_COMPONENT` with exact owner and inclusion ranges |
| 028 | P011 + | Official inclusion evidence expressly incorporates a Regulatory Form | `RULE_COMPONENT` with exact owner and inclusion ranges |
| 029 |  | Official inclusion evidence expressly incorporates a Fees Rule | `RULE_COMPONENT` with exact owner and inclusion ranges |
| 030 |  | Official evidence expressly includes another component class | `RULE_COMPONENT` only for the proved object and board |
| 031 | P010 - | Nearby guidance is published beside a Practice Note but expressly remains non-rule guidance | `EXCLUDED_NON_RULE`; no component state, owner, or Search Record |
| 032 |  | HKEX FAQ does not form part of the Listing Rules | `EXCLUDED_NON_RULE`; preserve only if a bounded evidence use exists |
| 033 |  | Consultation or consultation conclusion proposes or explains policy | `EXCLUDED_NON_RULE`; no current rule effect |
| 034 |  | Listing or review decision appears in the same search interface | `EXCLUDED_NON_RULE`; no rule-component identity |
| 035 |  | Circular or general announcement is not incorporated into a rulebook | `EXCLUDED_NON_RULE`; no rule-component identity |
| 036 | P011 - | Checklist, template, or Form-like object has no express incorporation proof | `EXCLUDED_NON_RULE` when exclusion is proved; never a rule from resemblance |
| 037 |  | Final update package proves assigned amendment facts but is not rule text | `EVIDENCE_ONLY`; no rule-component state, owner, or Search Record |
| 038 |  | SFC or Exchange approval artifact proves an assigned approval fact only | `EVIDENCE_ONLY`; no rule-component state, owner, or Search Record |
| 039 |  | Official transition or external-trigger evidence proves its assigned fact only | `EVIDENCE_ONLY`; no rule-component state, owner, or Search Record |
| 040 |  | Pinned source-relationship or interpretation evidence supports a rulebook rule only | `EVIDENCE_ONLY`; no rule-component state, owner, or Search Record |
| 041 |  | Object has only navigation placement, similar title or number, visual resemblance, linking, usefulness, or semantic similarity | `UNRESOLVED_MEMBERSHIP`; quarantine the smallest boundary and assign no owner |
| 042 |  | Accepted official artifacts conflict on whether an object forms part of the rulebook | `UNRESOLVED_MEMBERSHIP`; preserve conflict and assign no owner |
| 043 |  | Required inclusion evidence is absent or unreadable | `UNRESOLVED_MEMBERSHIP`; preserve the gap and assign no owner |
| 044 | P012 + | Exact official evidence assigns a component to Main Board | Own exactly one Main Board component instance |
| 045 |  | Exact official evidence assigns a component to GEM | Own exactly one GEM component instance |
| 046 | P013 + | One official artifact is expressly part of both rulebooks | Create one Main Board and one separate GEM component instance referencing the artifact |
| 047 |  | One artifact contains several separately maintained components | Create and account for every distinct supported component instance |
| 048 |  | Main Board and GEM contain identical wording under their separate rulebooks | Preserve separate component and later record identities |
| 049 |  | Website placement suggests one board but express official ownership evidence proves the other | Follow the express evidence and record the placement discrepancy |
| 050 |  | Accepted Rule Component lacks any supported board owner | Quarantine it as unowned; the ownership proof fails |
| 051 |  | Accepted evidence conflicts between Main Board and GEM ownership | Quarantine the ownership decision; do not choose by convenience |
| 052 | P013 - | One component instance is assigned simultaneously to both boards | Reject the double-owned instance; require two supported instances or quarantine |
| 053 |  | Component has no supported official parent or structural position | Reject the orphaned component and fail the applicable proof |
| 054 |  | Same supported component is instantiated twice for one board and location | Reject duplicate ownership and fail the applicable proof |
| 055 | P012 - | Main Board component is assigned to GEM, or GEM component to Main Board | Critical wrong-board result; fail the suite |
| 056 | P014 + | Required English evidence is complete and no Chinese artifact exists | Continue through later English gates; Chinese absence has no release effect |
| 057 | P014 - | Required English evidence is missing but an official Chinese translation is available | Block or quarantine the English boundary; never substitute Chinese |
| 058 | P015 + | Optional Chinese wording differs harmlessly without indicating an English defect | Preserve the discrepancy as optional evidence; no serving or identity change |
| 059 | P015 - | Chinese evidence positively signals a possible wrong English board, version, wording, state, or omission | Open the smallest English investigation and block or quarantine affected reuse |
| 060 |  | Chinese-only publication changes while all accepted English serving facts and bytes remain supported | No new Search Record, embedding, or current-release dependency |
| 061 |  | Candidate substitutes Chinese, an LLM translation, online presentation, similarity, or warning for missing English | Reject the candidate as prohibited source repair |
| 062 |  | Optional Chinese artifact is preserved for bounded terminology, evaluation, investigation, or audit use | Keep it outside Pinecone with exact traceability only when used |

### B. Applicability-branch effective state and transition

Case namespace: `HKREG-DEC-STA-NNN`

Coverage namespace: `HKREG-COV-DSTA-NNN`

| Suffix | Pair | Synthetic branch situation | Exact required result |
|---:|---|---|---|
| 001 |  | Ordinary branch is effective and reconciles exactly with the controlling current product | Branch `CURRENT`; searchable only after every separate gate |
| 002 |  | Branch applies now only to one exact cohort, transaction, period, or time window | Branch `TRANSITIONAL_CURRENT` with complete limitation facts |
| 003 |  | Final branch has a fixed effective point later than the cutoff | `FUTURE_FIXED_DATE`; keep in the Waiting Room |
| 004 | P021 + | Final conditional branch has fresh positive evidence that its trigger has not occurred | `FUTURE_CONDITIONAL`; continue targeted monitoring |
| 005 |  | Supported successor covers every former current application | `SUPERSEDED`; historical outside Pinecone |
| 006 | P024 + | Exact official evidence ends the obligation without a supported successor | `WITHDRAWN`; historical outside Pinecone |
| 007 |  | Permitted fresh evidence conflicts on operative wording or state | `UNKNOWN`; Quarantine and no newly current record |
| 008 |  | Observed entry is not a Rule Component Instance | `NOT_APPLICABLE`; no regulatory Search Record |
| 009 |  | Complete branch set contains exactly one ordinary current branch | Component summary `CURRENT` |
| 010 |  | Complete branch set contains one or more materially limited current branches | Component summary `TRANSITIONAL_CURRENT` |
| 011 | P016 + | Ordinary predecessor remains current while one amendment is only future | Component summary remains `CURRENT`, not transitional |
| 012 |  | No current branch exists and the complete operative set supports one fixed-date future family | Component summary `FUTURE_FIXED_DATE` |
| 013 |  | No current branch exists and the complete operative set supports one conditional future family | Component summary `FUTURE_CONDITIONAL` |
| 014 |  | Every formerly current branch has a complete supported successor | Component summary `SUPERSEDED` |
| 015 |  | Every formerly current branch ended without a supported successor | Component summary `WITHDRAWN` |
| 016 |  | One unresolved fact could change which branch is current | Component summary `UNKNOWN`; preserve every branch decision |
| 017 |  | Mixed future families cannot be represented honestly by one summary | Component summary `UNKNOWN` unless another exact rule proves one result |
| 018 | P017 - | Cutoff is immediately before the Hong Kong effective point | New branch remains future; predecessor remains separately accountable |
| 019 | P017 +; P018 + | Cutoff reaches the exact point and the controlling current product matches | New branch becomes `CURRENT` or `TRANSITIONAL_CURRENT` as its scope requires |
| 020 | P018 - | Effective point passed but the controlling product still has incompatible old wording or omits the change | `UNKNOWN`; no reconstruction or clock-only promotion |
| 021 |  | Publisher exposes future wording before its stated effective point | Keep the future branch in the Waiting Room; handle predecessor evidence separately |
| 022 |  | Effective wording gives an ambiguous date, time, or time zone | `UNKNOWN`; do not invent temporal precision |
| 023 |  | Source expressly supplies a time zone different from Hong Kong | Apply the exact supplied zone and cutoff before deciding state |
| 024 |  | One final update assigns several changed ranges to different fixed dates | Create and decide every mapped branch independently |
| 025 |  | One final update contains fixed-date and external-condition changes | Preserve separate fixed and conditional branches and evidence |
| 026 | P019 - | Final update describes an external condition but supplies no occurrence evidence | Keep the branch conditional or unknown under trigger freshness; do not activate it |
| 027 | P019 +; P020 + | Permitted official source proves trigger occurrence and the current product matches | Activate and classify the branch according to its exact present scope |
| 028 | P020 - | Trigger is proved but current compiled wording conflicts or lags | `UNKNOWN`; no reconstructed current wording |
| 029 | P021 - | Event could have occurred but its required source is stale, unavailable, incomplete, or conflicting | `UNKNOWN`; absence of evidence is not non-occurrence |
| 030 |  | Every fact in an all-of condition is positively proved | Activate the branch, subject to current-product reconciliation |
| 031 |  | At least one all-of fact is freshly proved not to have occurred and no alternative uncertainty changes that result | Remain `FUTURE_CONDITIONAL` |
| 032 |  | One required all-of fact is unresolved when it could have occurred | `UNKNOWN` |
| 033 |  | Any one permitted fact in an any-of condition is positively proved | Activate the branch, subject to current-product reconciliation |
| 034 |  | Every any-of alternative is freshly and positively supported as not having occurred | Remain `FUTURE_CONDITIONAL` |
| 035 |  | One any-of alternative is unresolved and could have occurred | `UNKNOWN` |
| 036 | P016 - | Old and new obligations concurrently apply to different supported cohorts | Preserve both as `TRANSITIONAL_CURRENT`; component summary transitional |
| 037 | P022 - | Concurrent branches have materially different wording or obligations | Require separate complete record responsibilities |
| 038 | P022 + | Same wording has one simple fully stated applicability limitation | One record is eligible only when `metadata.text` carries the complete limitation |
| 039 |  | Transition has no official end and cohort exhaustion is not provable | Keep the branch `TRANSITIONAL_CURRENT`; do not guess exhaustion |
| 040 | P023 + | Exact evidence proves the last old cohort ended and a successor covers its former applications | Old branch `SUPERSEDED` |
| 041 |  | Exact evidence proves the last old cohort ended without a successor obligation | Old branch `WITHDRAWN` |
| 042 | P023 - | Successor covers only part of the predecessor's former applications | Remaining old branch stays `TRANSITIONAL_CURRENT` |
| 043 |  | Overlapping amendments have update numbers out of effective order | Order branches by supported effective facts, not update numbers |
| 044 |  | Overlap creates an unresolved collision, gap, or precedence conflict | Affected branch `UNKNOWN` and quarantined |
| 045 | P024 - | Rule disappears from a page, locator, filename, or contents without ending evidence | Do not infer supersession or withdrawal; preserve prior facts and expose the gap |
| 046 |  | Similar wording, reused number, or higher update number is offered as continuity evidence | Do not infer identity, successor coverage, or retirement |
| 047 |  | Technical outage supports explicit last-approved carry-forward | Preserve last-approved status, last-verified date, Coverage Gap, warning, deadline, and support; do not call it fresh |
| 048 |  | Available evidence makes continued serving materially misleading | Withhold the affected records under ADR 0005 |
| 049 |  | Neither carry-forward nor withholding supports a safe rebuilt target | Build no new jurisdiction target |
| 050 |  | Branch state is `CURRENT` but another required gate fails | Do not create or promote a Search Record; state alone is not serving approval |
| 051 |  | Candidate uses an authority note, confidence, or prose to turn `UNKNOWN` into current | Reject the repair; retain `UNKNOWN` and Quarantine |

### C. Record boundary, governing dependency, and cross-reference decision

Case namespace: `HKREG-DEC-BND-NNN`

Coverage namespace: `HKREG-COV-DBND-NNN`

| Suffix | Pair | Synthetic source structure | Exact required result |
|---:|---|---|---|
| 001 |  | One official rule states one coherent independently usable obligation | One complete normal record responsibility |
| 002 | P025 + | Numbered subrules each state independently usable obligations | Separate complete record responsibilities for each subrule |
| 003 | P025 - | Numbered children form cumulative conditions under one shared obligation | Keep the complete inseparable condition group together |
| 004 |  | Alternatives, conjunctions, exceptions, or shared qualifications make several list items inseparable | Keep the exact complete group with its governing logic |
| 005 | P026 + | One list item is independently usable only with its grammatical lead-in | Select the item and repeat the exact lead-in as required governing context |
| 006 | P026 - | Candidate strands the same item without its governing lead-in | Reject the child boundary as unsafe; retain a larger complete unit |
| 007 |  | Qualification, exception, or proviso materially controls an obligation | Keep it with the exact obligation it limits |
| 008 | P027 + | Incorporated note qualifies one rule, definition, or branch | Attach it to that exact owner and retain it in the complete unit |
| 009 | P027 - | Candidate strands the incorporated note in another record | Reject both incomplete ownership and record boundary |
| 010 |  | Large definition collection has term-level entries and applicable global scope text | One responsibility per defined term with all required collection scope preserved |
| 011 | P028 + | Global definition applies broadly across the rulebook | Keep one separate searchable definition record and internal relationships |
| 012 | P028 - | Candidate copies the global definition into every using rule | Reject the unnecessary duplication as non-governing overlap |
| 013 |  | Definition is embedded locally and governs only one branch | Keep it with that branch as required context |
| 014 |  | Appendix has one independently usable official paragraph | One complete appendix record responsibility |
| 015 |  | Practice Note has one independently usable official paragraph | One complete Practice Note record responsibility |
| 016 |  | Website container, navigation label, PDF page, line wrap, table cell, blank field, or renderer part is offered as a Legal Location | Reject presentation-only identity; use proved legal structure |
| 017 |  | Accepted English product has ambiguous substantive structure | Open Source Contract Review or quarantine the smallest branch; do not guess |
| 018 | P029 + | Exact grammatical parent, local scope, transition, or qualification is necessary to preserve meaning | Repeat only that exact material as labelled required governing context |
| 019 | P029 - | Helpful background is proposed as generic overlap but omission changes no legal meaning | Exclude it from dependency closure and serving overlap |
| 020 |  | Required context repeats a source unit owned primarily elsewhere | Point to the exact owner and fingerprint; do not count it as primary again |
| 021 | P030 + | Rule contains an ordinary cross-reference with an exact target locator and helpful official heading | Preserve referring words, locator, and permitted heading only |
| 022 | P030 - | Candidate recursively copies the target rule text into the referring record | Reject recursive copying; retain internal relationship instead |
| 023 |  | Reference chain A to B to C is resolvable | Preserve exact separate relationships without recursively expanding B or C |
| 024 |  | Target identity or locator is unresolved | Preserve referring words and quarantine or review exact target resolution; do not guess |
| 025 |  | Main Board rule refers to a distinct GEM or cross-market location | Preserve both board identities and relationship; never merge or copy target text |
| 026 |  | Target wording changes but the referring record's six serving fields remain byte-identical | Update relationship or traceability revision only; no referring-record churn |
| 027 | P031 + | Child can stand independently with its exact locator and minimum dependencies | Accept the child as the normal complete unit |
| 028 | P031 - | Child cannot be understood safely without its official parent | Keep the larger parent together; do not serve the child alone |
| 029 |  | No complete source-supported unit plus required context can fit later hard limits | Quarantine the smallest affected branch; do not copy or paraphrase target material |
| 030 |  | Unrelated short rule would fit beside an overlong sibling | Keep it separate; never pack unrelated normal units for fill efficiency |

### D. Canonical English rendering, tables, fees, and Forms

Case namespace: `HKREG-DET-RND-NNN`

Coverage namespace: `HKREG-COV-DRND-NNN`

| Suffix | Pair | Frozen accepted facts | Exact required artifact result |
|---:|---|---|---|
| 001 |  | Ordinary current rule has no optional context blocks | Exact canonical ordinary `metadata.text` bytes in fixed block order |
| 002 |  | Equivalent source units belong separately to Main Board and GEM | Distinct exact Market context and separate canonical records |
| 003 |  | HKEX supplies an official English heading | Include exact `Official heading` line |
| 004 |  | HKEX supplies no official heading | Omit the heading block completely; do not invent one |
| 005 | P032 + | Current branch has a material cohort, period, or condition | Render the closed exact `Effective context` line plus substantive source wording |
| 006 | P032 - | Ordinary current branch has no material special limitation | Omit `Effective context`; do not add generic current prose |
| 007 |  | Primary unit requires repeated governing source text | Render exact labelled `Required governing context` block |
| 008 |  | Primary unit requires no repeated governing source text | Omit the governing-context block completely |
| 009 |  | Exact cross-reference has a permitted target heading | Render exact `Referenced locations` entry without target text |
| 010 |  | Record has no applicable referenced location | Omit the referenced-locations block completely |
| 011 |  | Source contains meaningful numbering, punctuation, capitalization, order, labels, and notes | Preserve them exactly in the closed source-faithful projection |
| 012 |  | Canonical renderer receives equivalent Unicode and line-ending presentations | Emit UTF-8 NFC, LF, stable order, no trailing spaces, and no outer blank lines |
| 013 |  | Source artifact contains URLs, page furniture, web controls, IDs, fingerprints, dates, reviewer prose, model output, and Chinese support | Exclude every forbidden item while preserving substantive English source units |
| 014 | P057 + | No approved authority-note clause applies | Emit required `metadata.authority_note` exactly `"None"`, separate from text |
| 015 | P057 - | Approved effective-date warning applies | Emit the exact English controlled warning separately; never leave `"None"` or modify source text |
| 016 |  | Authority note is present and metadata serialization is measured | Exclude it from embedding input but include its bytes in the six-field ceiling |
| 017 | P033 + | Table value has complete caption, lead-in, headers, units, spans, order, and notes | Emit exact closed table projection preserving every relationship |
| 018 | P033 - | Candidate detaches a table value from its header or unit | Reject the projection; produce no incomplete record |
| 019 |  | Multi-level or row-spanning header controls several values | Project the controlling labels unambiguously for every value without invention |
| 020 | P034 + | Table changes only page layout, wrapping, or visual placement | Emit byte-identical canonical table output |
| 021 | P034 - | One material header, row, unit, value, or note changes | Emit changed canonical bytes and the exact downstream identity consequence |
| 022 | P035 + | Fee bracket has amount, currency, basis, timing, activation condition, and notes | Emit one complete source-faithful fee branch |
| 023 | P035 - | Candidate includes a fee amount without currency, basis, timing, or applicable note | Reject the incomplete fee branch |
| 024 | P036 + | Form contains a substantive selection control, declaration, instruction, or signing requirement | Preserve it with its governing Form scope |
| 025 | P036 - | Form contains a purely presentation-only blank or web control | Classify and omit it without discarding substantive content |
| 026 |  | Form has official Parts, connected field groups, declarations, certifications, and signing requirements | Emit complete class-specific Form units, never isolated blank fields |
| 027 |  | Blank input and selection areas require neutral representation | Use the pinned neutral markers without inventing completed values |
| 028 |  | Candidate creates one Search Record per blank field | Reject fragmentation and reconstruct the complete supported Form unit |
| 029 | P037 + | Complete prevailing English record has optional Chinese evidence outside serving | Emit English-only text and one ordinary vector responsibility |
| 030 | P037 - | Candidate inserts Chinese source text, creates a Chinese duplicate, or requests a parallel vector | Reject every prohibited serving path |
| 031 |  | Character, ownership, or substantive layout is ambiguous | Fail closed and quarantine or review; do not silently normalize or correct |
| 032 |  | Approved transitional-applicability warning applies beyond the complete source context | Emit its exact controlled English clause separately from `metadata.text` |
| 033 |  | Approved market-scope warning applies | Emit its exact controlled English clause without changing board identity or source wording |
| 034 |  | Approved source limitation applies | Emit its exact controlled English warning; never use it to repair missing evidence |
| 035 |  | Approved representation or unresolved-reference limitation applies | Emit its exact controlled English warning only for the supported limitation; unresolved legal state remains quarantined |

### E. Exact-limit measurement and official-structure partitioning

Case namespace: `HKREG-DET-PAR-NNN`

Coverage namespace: `HKREG-COV-DPAR-NNN`

| Suffix | Pair | Frozen complete unit | Exact required artifact result |
|---:|---|---|---|
| 001 | P038 + | Final rendered payload fits the token and six-field byte ceilings exactly | Keep one complete unsplit record and preserve exact measurements |
| 002 |  | Final `metadata.text` exceeds only the pinned token ceiling | Enter official-structure partitioning; byte fit does not excuse token overflow |
| 003 |  | Six-field serialization exceeds only the metadata byte ceiling | Enter valid partitioning when text can cure it; token fit does not excuse byte overflow |
| 004 |  | Final payload exceeds both ceilings | Partition only through official structure and satisfy both limits |
| 005 |  | Candidate measurement omits context, references, table/Form projection, a metadata string, or authority note | Reject the incomplete measurement before any fit decision |
| 006 | P038 - | Preliminary parts fit until real `Serving part: X of N` labels are rendered | Recompute the frontier or fail; never serve a label-induced overflow |
| 007 |  | Complete official child fits with all required context | Keep the child whole in the frontier |
| 008 |  | One child remains oversized while its siblings fit | Replace only the oversized child with its complete official children and repeat |
| 009 |  | Several official depths could form a frontier | Use the largest safe complete units in exact source order |
| 010 |  | Several valid contiguous partitions exist | Select the solution with the fewest total parts |
| 011 |  | Equal-part solutions remain after minimizing part count | Fill every earlier part with the greatest possible consecutive frontier units |
| 012 |  | Different applicability branches require different supported depths | Partition each branch independently without forcing aligned depth |
| 013 |  | Final part total and labels are known | Re-render and remeasure every complete part against both ceilings |
| 014 |  | Proposed partition crosses the normal record unit's official boundary | Reject the cross-boundary partition |
| 015 |  | Unrelated short rule could fill unused capacity in an overlong sibling | Keep it separate; reject packing for utilization |
| 016 | P039 + | Oversized unit has a proved official child boundary that preserves complete meaning | Split only at that boundary and retain all required context |
| 017 | P039 - | Candidate cuts at a PDF page or visual page position with no independent semantic boundary | Reject the arbitrary cut |
| 018 |  | Candidate cuts at sentence or punctuation merely because the limit is near | Reject unless the same point is independently an official semantic boundary |
| 019 |  | Candidate cuts at whitespace, token position, or preferred size | Reject the arbitrary cut |
| 020 |  | Candidate cuts by character count, visual column, or sliding window | Reject the arbitrary cut |
| 021 |  | Candidate removes governing context to make a part fit | Reject the incomplete part; context is not optional compression |
| 022 | P040 + | Overlong unit has complete official descendants that fit after valid recursion | Emit the exact minimum-part earliest-full partition and coverage mappings |
| 023 | P040 - | Smallest complete official unit plus required context still exceeds a ceiling | Emit no record; Quarantine the smallest affected branch and record a Coverage Gap |
| 024 |  | Mandatory fixed metadata alone makes every otherwise valid part too large | Emit no record; do not attempt futile additional text splitting |

### F. English source-unit coverage and per-board readiness

Case namespace: `HKREG-DET-COV-NNN`

Coverage namespace: `HKREG-COV-DCOV-NNN`

| Suffix | Pair | Frozen construction result | Exact required artifact result |
|---:|---|---|---|
| 001 | P041 +; P042 + | Every meaning-bearing current unit has exactly one primary owner | Valid complete primary-ownership coverage proof with reproducible totals |
| 002 |  | One required current unit cannot produce a safe record | Account it explicitly as blocked or quarantined; never silently omit it |
| 003 |  | Governing source unit repeats in several records | One primary owner plus exact labelled dependency pointers and fingerprints |
| 004 |  | Heading, container, or visual element is context-only or presentation-only | Record its explicit classification and permitted consequence |
| 005 |  | Table and Form include headers, notes, Parts, groups, fields, and meaningful controls | Account every substantive and presentation unit exactly once by role |
| 006 |  | Complete tree contains future, superseded, withdrawn, unknown, and excluded units | Account them respectively in Waiting Room, history, Quarantine, and exclusion outcomes |
| 007 | P043 + | Every primary unit preserves exact source order and board ownership | Valid order-and-ownership proof |
| 008 | P041 - | One meaning-bearing source unit is absent from all outcomes | Invalidate coverage and serving readiness |
| 009 | P042 - | One source unit is counted as primary in two records | Invalidate duplicate primary ownership |
| 010 | P043 - | Primary source units are reordered | Invalidate source-order proof even when all text is present |
| 011 |  | Output contains a primary unit with no declared source-tree owner | Invalidate the orphaned output |
| 012 |  | Main Board unit is covered by a GEM record or vice versa | Invalidate wrong-board coverage |
| 013 |  | Repeated source text lacks required dependency label, owner, or fingerprint | Invalidate dependency accounting |
| 014 |  | Output silently translates, summarizes, corrects, invents, or drops source meaning | Invalidate source fidelity and coverage |
| 015 | P044 + | Complete proof has every required current unit ready and no blocking result | Board may be marked serving-ready for later gates; no promotion is authorized |
| 016 | P044 - | Complete proof exposes one quarantined required current unit | Accounting is complete but the affected board is not serving-ready |
| 017 | P045 + | Main Board has one proved bounded failure while GEM is independently complete | Main Board not ready; GEM readiness may remain valid |
| 018 | P045 - | Shared unbounded gap prevents both inventories or current sets from being proved | Neither board is serving-ready |
| 019 |  | Record count, PDF page count, parser success, or text-presence check matches expectations | Do not infer coverage or readiness without the complete source-unit proof |
| 020 |  | Complete accounting correctly produces zero Search Records | Valid zero-output proof with every source unit assigned a non-serving outcome |

### G. Search Record identity, lineage, and traceability

Case namespace: `HKREG-DET-IDN-NNN`

Coverage namespace: `HKREG-COV-DIDN-NNN`

| Suffix | Pair | Frozen prior and candidate state | Exact required identity result |
|---:|---|---|---|
| 001 |  | Main Board and GEM records have byte-identical source wording | Keep separate board-owned Legal Locations and Search Records |
| 002 | P046 + | Candidate six-field bytes exactly match an existing record and current legal support is proved | Reuse the exact Search Record; create no duplicate ID |
| 003 |  | Previously issued exact record becomes supported again after an intervening selection | Reselect through a new append-only selection event; create no backward lineage edge |
| 004 | P046 -; P048 - | Primary English serving text changes by one supported byte | Issue a new immutable Search Record with typed forward lineage |
| 005 |  | Material applicability or effective-context rendering changes | Issue a new Search Record with exact change reason |
| 006 |  | Required governing dependency closure changes | Issue a new Search Record with exact change reason |
| 007 |  | Rendered referenced-location bytes change | Issue a new Search Record when the six-field payload changes |
| 008 |  | Table or Form projection changes materially | Issue a new Search Record with exact change reason |
| 009 |  | Canonical partition boundary or final serving-part label changes | Issue the affected new Search Records and typed lineage |
| 010 | P047 - | `metadata.authority_note` changes while `metadata.text` is unchanged | Issue a new Search Record; reuse cached embedding only if the pinned text contract matches |
| 011 | P048 + | URL moves while canonical serving bytes and legal support remain exact | Reuse the existing Search Record; update aliases or traceability only |
| 012 |  | Page reflow or navigation changes with byte-identical canonical payload | Reuse the Search Record; no embedding or Pinecone record churn |
| 013 |  | Optional Chinese changes without exposing an English defect | Reuse the supported English Search Record |
| 014 | P047 + | Citation, grouping, provenance, alias, or evidence reference changes without a serving-field change | Create a new immutable Record Traceability Lookup revision only |
| 015 |  | Chinese evidence exposes a possible defect in the accepted English decision | Block reuse until the English support is resolved; do not create a Chinese record |
| 016 |  | Desired inventory contains one Search Record with one exact lookup entry | Validate payload, layered identities, scope, release, evidence, and authority-note fingerprints |
| 017 |  | Lookup entry is missing, duplicated, orphaned, or mismatched | Block readiness and promotion validation |
| 018 |  | Lookup entry binds the correct bytes to the wrong board or location | Block readiness as a critical ownership mismatch |
| 019 |  | One record replaces one predecessor | Record one-to-one forward lineage with evidence and no cycle |
| 020 |  | One record splits into several, or several merge into one | Record typed one-to-many or many-to-one forward lineage with complete evidence |
| 021 |  | Candidate lineage points backward or creates a cycle | Reject the lineage and candidate state |
| 022 | P049 + | Exact official evidence proves renumbering or other permitted continuity | Preserve or relate identities exactly as the rulebook requires |
| 023 | P049 - | Continuity is inferred only from similarity, title, URL, number, or alias | Quarantine the identity decision; do not reuse or merge IDs |
| 024 |  | Lookup authority-note evidence or rendered fingerprint disagrees with the record | Block readiness and promotion validation |

### H. Package integrity, reproducibility, and forbidden effects

Case namespace: `HKREG-DET-PKG-NNN`

Coverage namespace: `HKREG-COV-DPKG-NNN`

| Suffix | Pair | Synthetic package or run condition | Exact required result |
|---:|---|---|---|
| 001 |  | Complete strict package declares every root, catalogue, case, contract, artifact, path, role, hash, and inventory | Validate the package and its one canonical fingerprint |
| 002 |  | Root or case document contains an unknown property, enum, source role, artifact role, rule, reason, case, cell, or pair | Reject under the closed schema; never ignore for forward compatibility |
| 003 |  | Declared artifact bytes do not match SHA-256 | Reject the package before case execution |
| 004 |  | Package contains an undeclared local file used by the runner | Reject the package and undeclared access |
| 005 |  | Declared required file is absent | Reject as incomplete unless its exact input state is deliberately absent |
| 006 |  | Manifest contains an absolute path | Reject path containment failure |
| 007 |  | Path contains parent traversal, an empty segment, or a platform-specific separator | Reject normalization and containment failure |
| 008 |  | Declared path resolves through a symlink | Reject the package |
| 009 |  | Manifest requests a URI, remote retrieval, or network resource | Reject the package and assert no network access |
| 010 |  | Catalogue relies on a glob, range, filename convention, directory scan, or dynamic discovery | Reject completeness by inference; require explicit inventory |
| 011 | P050 + | Input slot is `AVAILABLE` and the exact declared artifact exists, validates, and hashes | Admit the input |
| 012 | P050 - | Input slot is `AVAILABLE` but its file is absent or mismatched | Reject the case as incomplete |
| 013 | P051 + | Input slot is `INTENTIONALLY_ABSENT` and no artifact exists | Admit the deliberate-absence condition |
| 014 | P051 - | Required file is accidentally missing without a deliberate-absence declaration | Reject; accidental absence cannot satisfy the test |
| 015 |  | Input slot is `UNREADABLE` and exact declared corrupt or unsupported bytes exist | Admit the intended unreadable-input case without parsing invented content |
| 016 |  | Evidence is stale, conflicting, wrong-board, or differently versioned | Represent it through exact `AVAILABLE` artifacts and facts, not a vague state |
| 017 | P052 + | Expected artifact is `EXACT`, exists, validates, and matches canonical bytes | Pass that artifact role |
| 018 | P052 - | `EXACT` artifact is missing, invalid, or byte-different | Fail the case |
| 019 | P053 + | Expected artifact is `NONE` with explicit zero-count and no-artifact assertions | Pass the exact zero-output role |
| 020 | P053 - | Expected output file is simply absent without explicit zero proof | Fail; absence never establishes `NONE` |
| 021 |  | Artifact role is `NOT_APPLICABLE` and the matrix proves the checkpoint is outside scope | Accept the explicit non-applicability |
| 022 |  | `NOT_APPLICABLE` is used because the implementation failed to produce an applicable output | Reject the hidden failure |
| 023 |  | Every required cell has a direct case, every case owns a cell, every stable rule and branch is covered, and every pair is complete | Validate matrix completeness |
| 024 |  | Required cell is uncovered or executable case owns no primary cell | Reject the catalogue as incomplete |
| 025 | P054 + | Declared pair contains exactly one positive and one near-miss member | Validate the pair |
| 026 | P054 - | Pair has one missing, duplicate-role, or extra member | Reject pair and catalogue completeness |
| 027 |  | Proposal evidence packet is inspected for hidden truth | Prove it contains no case ID, title, path, cell, pair role, expected result, adjudication, or critical tag |
| 028 |  | Root fingerprint would include itself, or expected truth is edited in place after use | Reject the cycle or mutation; require a new immutable superseding identity |
| 029 | P055 + | Two isolated clean deterministic executions use the same exact package and build | Require byte-identical artifacts, measurements, inventories, reports, and fingerprints |
| 030 | P055 - | Repeated clean run differs in any deterministic artifact or fingerprint | Fail reproducibility |
| 031 | P056 + | Source text contains instruction-like content aimed at tools, prompts, secrets, or expected answers | Treat it as inert evidence; execution and result remain contract-bound |
| 032 | P056 - | Instruction-like source text changes a tool, path, prompt, contract, expected result, secret, approval state, or execution | Fail the case as hostile-input control breach |
| 033 |  | Conformance run attempts source, generative-model, embedding, network, or credential access | Fail and prove no attempted capability changed state |
| 034 |  | Run attempts Azure, Pinecone, backup, routing, promotion, production-store, undeclared-file, or live-state access | Fail and prove no external mutation occurred |
| 035 |  | Suite package validates completely | Record only package validity; grant no source, provider, release, serving, or deployment authority |
| 036 |  | Attestation binds exact suite, rulebook, processing build, dependency lock, runner, results, reproducibility, and architecture tests | Validate build compatibility only |
| 037 |  | Attestation names a stale, changed, partial, or mismatched suite, rulebook, build, dependency, runner, or result set | Reject the attestation |
| 038 |  | Declared media type conflicts with bytes, or required local file permissions prevent exact read-only preflight | Reject the package or case before processing and preserve the exact preflight failure |

## Initial exact catalogue arithmetic

| Checkpoint | Direct cases and matching primary cells |
|---|---:|
| Source Fact Authority, membership, ownership, and language evidence | 62 |
| Applicability-branch effective state and transition | 51 |
| Record boundary, governing dependency, and cross-reference decision | 30 |
| Canonical English rendering, tables, fees, and Forms | 35 |
| Exact-limit measurement and official-structure partitioning | 24 |
| English source-unit coverage and per-board readiness | 20 |
| Search Record identity, lineage, and traceability | 24 |
| Package integrity, reproducibility, and forbidden effects | 38 |
| **Total** | **284** |

The catalogue declares **57 high-risk pairs**. The pair index below is the sole
pair-membership summary; the row tables remain normative for each scenario and
exact result.

| Pair range | Primary distinction |
|---|---|
| `HKREG-PAIR-001`–`015` | Source-role authority, completeness, membership, board ownership, and English/Chinese evidence |
| `HKREG-PAIR-016`–`024` | Current/future/transition, trigger, product reconciliation, replacement, and withdrawal boundaries |
| `HKREG-PAIR-025`–`031` | Independent units, governing dependencies, definitions, notes, references, and safe child boundaries |
| `HKREG-PAIR-032`–`037` | Context-block rendering, tables, fees, Forms, and English-only payload |
| `HKREG-PAIR-038`–`040` | Exact fit, official partitioning, and indivisible material |
| `HKREG-PAIR-041`–`045` | Complete source-unit ownership, order, readiness, and scope isolation |
| `HKREG-PAIR-046`–`049` | Exact reuse, changed payload, traceability-only revision, and continuity evidence |
| `HKREG-PAIR-050`–`056` | Input/output state semantics, pair completeness, reproducibility, and hostile input |
| `HKREG-PAIR-057` | No authority note versus a mandatory Regulatory warning |

## Design-level branch audit

The completed row audit maps every accepted normative family to direct primary
cases:

| Accepted source | Direct primary coverage |
|---|---|
| ADR 0005 unavailable-scope choices | `HKREG-DEC-STA-047`–`049` |
| ADR 0011 immutable layered identity | `HKREG-DET-IDN-001`–`015`, `019`–`023` |
| ADR 0016 Record Traceability Lookup | `HKREG-DET-IDN-014`, `016`–`018`, `024` |
| ADR 0050 Regulatory authority-note behavior | `HKREG-DEC-STA-051`, `HKREG-DET-RND-014`–`016`, `032`–`035`, `HKREG-DET-PAR-024`, `HKREG-DET-IDN-010`, `014`, `024` |
| ADR 0054 family, scope, inclusion, ownership, state, and serving boundary | `HKREG-DEC-SRC-001`–`062`, `HKREG-DEC-STA-001`–`051`, `HKREG-DEC-BND-001`–`030` |
| ADR 0069 component inventory and completeness | `HKREG-DEC-SRC-011`–`055`, `HKREG-DET-COV-001`–`020` |
| ADR 0070 five-role source and Fact Authority rules | `HKREG-DEC-SRC-001`–`022`, `037`–`043`, `HKREG-DEC-STA-026`–`035` |
| ADR 0071 applicability-branch state and transitions | `HKREG-DEC-STA-001`–`051`, `HKREG-DET-RND-005`–`006`, `032`, `HKREG-DET-COV-006` |
| ADR 0072 English authority and optional Chinese support | `HKREG-DEC-SRC-056`–`062`, `HKREG-DET-RND-013`, `029`–`030`, `HKREG-DET-IDN-013`, `015` |
| ADR 0073 source-faithful record construction | `HKREG-DEC-BND-001`–`030`, `HKREG-DET-RND-001`–`035`, `HKREG-DET-PAR-001`–`024`, `HKREG-DET-COV-001`–`020`, `HKREG-DET-IDN-001`–`024` |
| ADR 0074 strict two-layer conformance architecture | All 284 cases, all 284 matching primary cells, all 57 pairs, and especially `HKREG-DET-PKG-001`–`038` |

Local catalogue validation confirms:

- exactly 284 unique direct case IDs and 284 matching primary coverage-cell
  IDs across the exact checkpoint counts above;
- every row has one primary checkpoint and one matching primary cell;
- all 57 permanent pairs exist, each with exactly one positive and one near-
  miss member, with no undeclared or unused pair;
- every accepted coverage group and designated critical-error family has
  direct primary coverage; and
- the count follows the audited branches rather than a target, cap, model
  score, or Cartesian product.

Executable Source Rulebook rule and reason codes do not yet exist. When they
are created, they must bind into these frozen rows and may add new immutable
cases where a new stable branch appears; they cannot weaken, merge, mark
inapplicable, or silently rewrite an existing row.

## Frozen meaning and later expansion

ADR 0075 freezes every ID, primary checkpoint, scenario, exact required result,
pair role, and pair membership in this initial conceptual catalogue. A later
requirement adds new permanent IDs. Correcting an erroneous frozen row requires
a new catalogue version, explicit supersession or correction mapping, impact
declaration, preservation of prior packages and results, and revalidation of
every affected contract and build. Existing IDs are never reassigned.

The frozen catalogue does not select a parser, generative model, prompt,
embedding model, technical stack, numerical limit, or retrieval threshold. It
does not create executable schema bytes, fixtures, source snapshots, records,
or run results. Those remain separately governed artifacts.

This document authorizes design work only. It does not authorize executable
schemas or fixtures, source acquisition, model or embedding calls, evaluation
execution, corpus construction, Pinecone or Azure access, promotion,
deployment, commit, push, or any remote action.
