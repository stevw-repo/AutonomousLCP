# Hong Kong Case Treatment Design Audit

Status: **Complete — catalogue accepted by ADR 0059**

Audit date: 2026-08-13

## Verdict

The Hong Kong later-treatment architecture is coherent after the corrections
recorded below. It consistently answers these questions:

- what evidence may establish treatment;
- how variable judgment language is analysed;
- who may accept the legal result;
- how treatment attaches to exact Case Propositions;
- how incoming and outgoing views are derived without duplicate facts;
- what the downstream LLM receives through Pinecone;
- how corrections, reversal, uncertainty, retirement, and reinstatement affect
  immutable records; and
- how exact conformance and promotion boundaries are proved.

The audit found no remaining product-policy contradiction that requires a new
user decision that prevented conformance-catalogue approval. It did find
omitted test boundaries and several proposed rows with non-exact outcomes.
Those defects have been corrected. The accepted catalogue contains **155
direct cases, 155 matching primary coverage cells, and 21 high-risk positive
and near-miss pairs**.

This is a design-completeness verdict, not an implementation-readiness verdict.
The source rulebook, executable contracts, real-judgment evaluations, runtime
task admission, exact Case Proposition extraction contracts, and cross-cutting
query integration still require later work. ADR 0065 later settles the high-
level extraction allocation without making it implementation-ready.

## Scope reviewed

The audit checked the canonical design, glossary, decision log, working state,
and the applicable ADR chain, especially:

- ADR 0014 — proposition-scoped continuity, treatment, and retirement;
- ADR 0046 — binding-court coverage;
- ADR 0047 — original-language case serving;
- ADR 0048 — official judgment acquisition and accounting;
- ADR 0049 — first current-authority baseline;
- ADR 0050 — standardized `metadata.authority_note`;
- ADR 0052 — bounded ordinary updates and HKLII discovery;
- ADR 0053 — staged hybrid LLM analysis and Legal Desk authority;
- ADR 0055 — immutable record and selection transitions;
- ADR 0056 — semantic and deterministic conformance suites;
- ADR 0057 — strict non-leaking packages and catalogues; and
- ADR 0058 — one directional relationship with two internal views; and
- ADR 0065 — the later two-pass hybrid Case Proposition extraction allocation.

The review traced every accepted rule through evidence, semantic proposal,
deterministic validation, Legal Desk decision, relationship storage,
authority-note rendering, record selection, release construction, and
promotion eligibility.

## Corrections made by the audit

| Problem found | Why it mattered | Correction |
|---|---|---|
| Treatment classes and appellate dispositions were mixed in two briefing passages | `REVERSED` and `SET_ASIDE` describe what happened on appeal; they do not by themselves say how every proposition was treated | The glossary and working state now keep treatment classification separate from `AFFIRMED`, `VARIED`, `REVERSED`, `SET_ASIDE`, and `REMITTED` disposition facts |
| One older evidence description allowed a resolved relationship to contain several treated proposition IDs | ADR 0058 requires one authoritative relationship per exact treated proposition | Resolved relationships now have one treated proposition; exact multiple mappings create separate relationships and uncertain mappings remain Treatment Leads |
| Several catalogue rows allowed alternative results such as “A or B” | A deterministic fixture must have one exact result from one frozen input | Rows now bind one exact class, validation result, route, or declared Source Rulebook consequence |
| Reversal had no direct near-miss between exact proposition effect and disposition-only uncertainty | Reversal of a result must not silently retire every proposition | A new high-risk pair distinguishes exact evidence-backed retirement from `UNCERTAINTY_REVIEW` |
| Hostile or instruction-like source text had no direct semantic boundary pair | Judgment text is evidence, never an instruction to the model | A new semantic pair distinguishes operative judicial treatment from identical words inside an unadopted quoted submission or instruction-like passage |
| Multi-target resolved treatment edges had no direct validation case | Allowing them would weaken proposition scope and make incoming projections ambiguous | A new validation case rejects the edge and requires separate exact relationships or one unresolved lead |
| A bounded unresolved lead had no direct projection case | It must not appear as settled incoming authority | A new release-level case keeps it in outgoing investigative and impact views only, with no note, guessed edge, or vector |
| The first-baseline no-predecessor and complete-screening result was only implied | It cannot be represented as ordinary `SUPPORTED_NO_CHANGE` | A direct case now seals a no-predecessor baseline with exact `authority_note: "None"` only after complete screening |
| The accepted no-arbitrary-age-cutoff rule lacked a direct catalogue row | Old supported authority must not disappear merely because of age | A direct case keeps a completely screened old superior-court proposition eligible |
| Official correction scope continuity lacked a direct catalogue row | A later correction must not move a decision into a new court-year Release Scope | A direct case keeps the decision in its original scope while updating only affected facts and records |
| Legacy identity isolation lacked a direct deterministic row | A matching legacy vector must not become greenfield identity or lineage | A direct record case requires register-owned identity and no invented predecessor |
| Unsupported listing disappearance lacked a direct update row | Disappearance is not withdrawal, retirement, or no-change proof | A direct case preserves prior evidence and opens bounded reconciliation |
| The Hong Kong English-only authority-note rule lacked a direct deterministic case for a Chinese proposition | The downstream internal warning must stay English without replacing original Chinese legal text | A direct renderer case preserves Chinese `metadata.text` and emits the controlled note in English only |

## Consistency findings

### 1. Evidence and source authority — coherent

The originating Judiciary judgment, accepted registry evidence, or another
rulebook-approved official artifact supplies the text and version facts. HKLII
may discover a possible relationship but cannot prove wording, treatment,
authority, retirement, reinstatement, or no change. A missing judgment remains
a Coverage Gap rather than a valid no-proposition decision.

Exact Hong Kong source IDs, endpoint profiles, historical inventory boundaries,
and format contracts still belong in the future Hong Kong Cases Source Register
and Source Rulebook Package. That is specification work, not a missing product
decision.

### 2. Search and identity unit — coherent

One separately delivered judicial decision is one Legal Item. One material,
self-contained proposition is one case Search Record. Case Dossiers, full
judgments, translations, aliases, duplicate formats, and treatment
relationships do not create duplicate vectors.

ADR 0065 later allocates Case Proposition extraction to a two-pass staged
hybrid. The treatment design remains independently frozen, but the complete
Hong Kong Cases pipeline cannot be implementation-ready until extraction has
its exact evidence, task, evaluation, and authority contracts.

### 3. Treatment semantics and court authority — coherent architecture,
exact rulebook still required

Treatment class, expression mode, proposition scope, materiality, court and
jurisdiction relationship, opinion status, finality, and appellate disposition
remain separate axes. Deterministic keywords do not decide meaning. The LLM
proposes semantics; deterministic validation and the Hong Kong Cases Legal Desk
control the accepted legal effect.

The future Source Rulebook must still encode the exact court-authority and
finality matrix, including the Court of Final Appeal, Court of Appeal, Court of
First Instance, Competition Tribunal, corresponding historical superior
courts, and Hong Kong Privy Council material. It must also pin exact consequence
codes for clear `DISAPPROVED`, `REFUSED_TO_FOLLOW`, reversal, and related
results. If no exact rule applies, the accepted result is review or Quarantine,
not an invented consequence.

These values should be established from authoritative Hong Kong law and Legal
Desk validation. They do not require the product owner to guess legal doctrine
during this architecture review.

### 4. LLM and deterministic boundary — coherent

Whole-judgment LLM discovery may find unusual or implicit treatment language.
Candidate-level analysis may propose class, expression, scope, materiality, and
evidence. Neither pass may directly update the database. Deterministic checks
own source admission, exact passages, identities, opinion structure, hierarchy
constraints, schemas, coverage, and permitted claims. The Legal Desk owns the
accepted legal result.

The catalogue now directly tests instruction-like source text. Runtime
admission must still pin the model, prompt, schema, evidence packet, token and
size limits, thresholds, critical errors, retries, costs, retention, sampling,
and revalidation. A sealed representative real-Hong-Kong-judgment evaluation
set remains mandatory; synthetic cases alone cannot establish model readiness.

### 5. Human review threshold — coherent

Clear ordinary treatment is accepted automatically under an exact tested rule
and reported. Human treatment review is reserved for uncertainty, ambiguity,
missing rules, and the narrow accepted exceptional structural changes. A high
volume, costly, or surprising but clear update may trigger an operational pause
without being relabelled exceptional legal review. Complete promotion still
requires the separate human Approval bound to one frozen manifest.

### 6. Relationship graph — coherent

One accepted directional relationship runs from the later decision, version,
opinion, and passages to one exact earlier proposition. A treating proposition
link is optional. Incoming and outgoing views derive from the same relationship
ID and fingerprint. An unresolved lead is not a settled incoming relationship.

Correction, withdrawal, reversal, or supersession preserves former
relationships and appends successor or supersession facts. The outgoing view
finds every earlier proposition that must be recomputed. Accepted history is
never overwritten.

### 7. Pinecone and downstream LLM boundary — coherent

Pinecone receives no relationship records, graph vectors, exhaustive outgoing
lists, whole-case treatment summaries, or new case-specific metadata field.
The earlier proposition may receive selected incoming treatment through
`metadata.authority_note`. The later judgment may describe treatment in
`metadata.text` only when it is part of a genuine material Case Proposition.

The later proposition's own `authority_note` concerns subsequent treatment of
that proposition, not authorities it discussed. Bare citations remain
internal. Pinecone therefore supports proposition retrieval but does not
promise exact citator-style enumeration.

Every production query path must still prove that it passes `authority_note`
unchanged, and Chinese-query evaluation must prove that the English internal
note affects downstream reliance. Those are cross-cutting Query Contract and
answer-evaluation tests, not additional treatment-graph records.

### 8. Immutable record and serving transitions — coherent

An unchanged six-field payload reuses the same record. A new payload receives a
forward successor. A former exact payload may be reselected through an
append-only selection event. Full conclusive overruling selects no successor;
partial overruling permits only independently supported narrower propositions.
Uncertainty creates no guessed transition.

Every serving change still requires complete releases, one complete
Desired-State Inventory, one frozen Promotion Manifest, valid Approval, a
replacement Pinecone Index, verification, and controlled routing. No accepted
treatment rule authorizes a live-index patch.

### 9. Baseline and ordinary updates — coherent after added cases

The first baseline has no predecessor and is not ordinary supported no change.
It has no arbitrary age cutoff. Ordinary updates use one predecessor and one
cutoff, expand transitive impact, preserve unrelated court-year scopes, and
distinguish no change, accounting-only change, serving change, blocked, and
quarantined outcomes.

Corrections stay with the original decision scope. Listing disappearance is
not withdrawal. Missing evidence cannot be hidden as zero records or no change.
Contract changes use processing-correction lineage rather than pretending that
the court changed the law.

### 10. Conformance packaging — coherent after catalogue expansion

Semantic evaluations and deterministic fixtures remain separate. Opaque case
IDs do not leak answers to the model. Strict catalogues, manifests, declared
files, hashes, expected-artifact states, coverage cells, and positive/near-miss
pairs prove completeness. Every deterministic role is exact, explicitly zero,
or proved not applicable; missing output cannot pass as zero.

The revised accepted table contains:

| Primary checkpoint | Direct cases |
|---|---:|
| Semantic whole-judgment discovery | 13 |
| Semantic candidate analysis | 40 |
| Deterministic validation and package safety | 32 |
| Deterministic Legal Desk decision and routing | 22 |
| Deterministic authority-note rendering | 14 |
| Deterministic record, embedding, lineage, and selection | 12 |
| Deterministic release, update, and promotion boundary | 22 |
| **Total** | **155** |

The 21 declared high-risk pairs each have one positive and one near-miss member.
The user approved the table on 2026-08-13, and ADR 0059 freezes it.

## Remaining work after catalogue approval

The following work remains necessary before implementation or provider use:

1. Build the Hong Kong Cases Source Register and exact Source Rulebook,
   including court hierarchy, finality, historical coverage, source roles,
   stable rules, consequence codes, and complete impact declarations.
2. Specify ADR 0065's separate Case Proposition analysis and challenge tasks;
   do not assume that the accepted treatment LLM contracts cover extraction.
3. Instantiate the 155-row design as strict machine-readable catalogues,
   schemas, synthetic packages, expected artifacts, rule and reason codes, and
   validators.
4. Add the sealed representative real-judgment semantic evaluation set and pin
   the complete runtime task-admission contract.
5. Prove the six-field Query Contract across every Ask.Legal path, including
   unchanged authority-note delivery and Chinese-query reliance behavior.
6. Produce the Rulebook Conformance Attestation for the exact processing build.

These are not authorized by this audit.

## User decisions still open

No immediate Hong Kong treatment-catalogue decision remains. Later user
decisions remain deliberately separate:

- the exact task contracts and admission values for ADR 0065's accepted Case
  Proposition extraction allocation;
- the exact treatment model, prompt, thresholds, cost limits, and operating
  policy after representative evaluation evidence exists; and
- whether Ask.Legal should ever gain an exact citator-style graph lookup.

The last option is not required by the accepted Pinecone design and remains
closed unless the user deliberately reopens it.

## Authorization

This audit and its corrections authorize documentation only. They do not
authorize implementation, source acquisition, real-judgment collection,
generative-model or embedding calls, release publication, Pinecone or Azure
access, promotion, deployment, commit, push, or any other remote action.
