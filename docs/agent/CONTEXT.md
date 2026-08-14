# AskLegal Legal Database Pipeline — Domain Context

This glossary defines the stable language of the autonomous legal-database
pipeline. Architecture and policy decisions belong in `DECISIONS.md` and
`docs/adr/`; current work belongs in `WORKING_STATE.md`.

## Collaboration and decision-escalation preference

For the remaining Hong Kong Regulatory Materials design, do not ask the user
to approve choices whose answer is already dictated by accepted ADRs, exact
evidence boundaries, internal consistency, safety, or an obviously dominant
technical approach. Make those choices, validate them, and keep the canonical
design and continuity files current.

Escalate only a genuine unresolved choice that materially changes legal
meaning, product behavior, acceptable risk, cost, quality, human-review burden,
or another outcome for which no clearly dominant option follows from the
accepted design. Explain the concrete tradeoff and recommendation when
escalating. Routine case enumeration, identifier assignment, schema mechanics,
cross-reference repair, validation, and documentation consistency do not need
separate user approval. This preference authorizes design work only and does
not expand any implementation or operational authorization boundary.

## Repository memory boundary

This glossary and the adjacent greenfield continuity files are authoritative
only for `AskLegal-LegalDBPipeline`. No instruction, decision, approval,
priority, status, or next step from a legacy Ask.Legal workspace applies here
unless the user explicitly restates it for this repository. Availability of
another workspace root creates no shared memory or authorization.

## Source and evidence

**Registered Source**: An approved official or publisher-authorized product
and evidence role with a stable source ID, exact fact authority, outage impact,
monitoring tier, endpoint records, and responsible Legal Desk.
_Avoid_: Website, data source

**Source Endpoint**: One versioned technical or physical location through which
a Registered Source is checked or an artifact is obtained. URLs, languages,
formats, generated download routes, and archive holdings may change without
changing the source ID.
_Avoid_: Registered Source identity, permanent URL

**Fact Authority**: The exact fact that evidence from a Registered Source is
permitted to prove. Authority is not global: one source may prove a legal event
without proving the resulting consolidated text.
_Avoid_: Controlling source for everything, newest source wins

**Source Outage Impact**: The recorded effect of source unavailability:
release-blocking, blocking only affected work that requires the source, or
nonblocking. A detected conflict may block affected work even when an outage
would not.
_Avoid_: Every official-source outage stops everything

**Source Rulebook Contract**: The common required structure that every
jurisdiction-and-material source rulebook must satisfy. It standardizes the
questions, evidence bindings, decision records, versioning, and fail-closed
behavior without making the answers the same across jurisdictions.
_Avoid_: Universal legal-status rules, source list

**Source Rulebook**: One immutable versioned and fingerprinted decision manual
for one jurisdiction-and-material pair. It references Registered Source IDs and
states what evidence those sources may prove, the stable rules a Legal Desk may
apply, and the permitted outcomes.
_Avoid_: Connector configuration, credentials, cross-jurisdiction Principles rulebook

**Source Rulebook Package**: The strict immutable policy package that binds one
Source Rulebook version's coverage, source-role Fact Authorities,
interpretation locks, declarative rules, stable codes, contract locks,
conformance universe, scope readiness, and impact declaration. Activation and
runtime decisions remain outside it.
_Avoid_: Executable application, evidence archive, endpoint configuration

**Release Scope Decision Readiness**: A rulebook-package state declaring
whether one owned Release Scope has every required source role, rule, code,
contract, registry, and test binding needed to support decisions. A not-ready
scope cannot masquerade as complete and does not automatically invalidate an
independent ready scope.
_Avoid_: Source availability, release approval, jurisdiction-wide readiness

**Rulebook Conformance Attestation**: An immutable external proof binding one
exact Source Rulebook Package fingerprint to one exact processing build and its
successful complete conformance results. It proves compatibility, not legal
authority or permission to access sources or promote data.
_Avoid_: Rulebook package, deployment approval, unit-test summary

**Rule Trace**: The ordered list of stable Source Rulebook rule IDs actually
applied to one observation, item, location, or release decision, together with
the evidence, established and unresolved facts, identity effects, and final
outcome. Human explanations, executable rules, fixtures, and decisions use the
same IDs.
_Avoid_: Free-form rationale, execution log, AI chain of thought

**Watcher**: A source-specific monitor that detects a possible addition,
change, disappearance, or legal-status event.
_Avoid_: Scraper, legal checker

**Scraper**: A source-specific retriever that captures the complete changed
content, required attachments, and source metadata.
_Avoid_: Watcher, desk

**Observation**: One recorded result of checking a Registered Source at a
specific time.
_Avoid_: Run, snapshot

**Observation Freshness**: The time since the latest complete successful
Observation for one Registered Source role. It is a release gate defined by the
source's monitoring tier and is separate from the age of the publisher's legal
text or most recent Official Version.
_Avoid_: Source publication date, proof that law changed

**Source Snapshot**: An immutable preserved capture of the source evidence used
for a decision.
_Avoid_: Current page, working copy

**Source Contract Review**: A bounded review opened when a relied-on source
schema, data dictionary, notice, enum, field meaning, verification rule, or
other interpretation specification changes, conflicts, becomes stale, or no
longer validates observed input. It resolves interpretation before affected
new processing resumes; it is not itself a legal-text update.
_Avoid_: Automatic schema acceptance, legal-status event, global pipeline outage

**HKLII Discovery Evidence**: A non-controlling snapshot from Registered Source
`HK-CASE-HKLII-DISCOVERY` showing that HKLII displayed a candidate judgment,
alias, citation, inventory difference, link, or possible treatment relationship
at one time. It may open originating-source acquisition or reconciliation but
cannot prove judgment wording, version, authority, proposition, treatment,
authority note, or retirement.
_Avoid_: Official judgment, case-law Fact Authority, no-change evidence

**Hong Kong Binding-Case Coverage**: The ordinary searchable Hong Kong Case
scope accepted in ADR 0046. It covers written decisions and reasons from the
Court of Final Appeal, Court of Appeal, Court of First Instance, and Competition
Tribunal, plus separately accountable corresponding historical superior-court
and Hong Kong Privy Council material. Standalone lower-body decisions remain
outside this scope even when technically extractable.
_Avoid_: Every Hong Kong judgment, specialist-persuasive material, HKLII index

**Official Judgment Listing Entry**: One source result observed in an official
Judiciary inventory at a fixed cutoff. It must be accounted for but is not
automatically one Judicial Decision, Official Version, or Search Record.
_Avoid_: Judgment Legal Item, Pinecone record, proof of complete acquisition

**Official Judgment Artifact**: One exact originating source file or official
rendered representation that publishes one Official Version of a Judicial
Decision. Source bytes or the exact official capture remain preserved even
when a working conversion is used for parsing.
_Avoid_: Generated conversion, listing entry, Judiciary Translation Artifact

**Judiciary Translation Artifact**: An official Judiciary translation linked
to the exact Hong Kong judgment Official Version, opinion, and passages. It is
preserved evidence for alignment, review, terminology, and cross-language
evaluation but is not another judgment, authority, Official Version, or
default serving-language record under ADR 0047.
_Avoid_: Court-authored original, language duplicate, machine translation

**Evidence Vault**: The durable store of Source Snapshots, official-status
evidence, releases, approvals, reports, and recovery material.
_Avoid_: Pinecone, management register

## Legal material

**Legal Desk**: The named logical decision authority for exactly one
jurisdiction-and-material pair. It applies one immutable active Source Rulebook
to preserved evidence, accepted structured facts, prior register state, and any
permitted evidence-bound proposal; records the exact Rule Trace, established
and unresolved facts, and structured legal and serving consequences; and fails
closed when no rule or sufficient evidence supports a result. It may accept
fully resolved ordinary work automatically. It is not itself a person, LLM,
source connector, renderer, release builder, promotion reviewer, or deployment
service and holds no source, model-provider, Pinecone, Azure, or routing
credentials.
_Avoid_: Virtual lawyer, human review queue, AI agent, source connector, publisher

**Legal Desk Owner**: The accountable authorized legal-domain role responsible
for governing one Legal Desk's coverage, Source Rulebook, stable rules, codes,
reference decisions, and exact human-review triggers. The owner may be a person
or organizational legal function; ordinary runtime Legal Desk decisions do not
require the owner to inspect every item manually.
_Avoid_: Every-run reviewer, promotion approver, model provider

**Legal Desk Decision**: One immutable cutoff-bound result issued under one
exact Legal Desk and Source Rulebook fingerprint. It binds admitted evidence,
prior state, any accepted proposal, established and unresolved facts, ordered
Rule Trace, membership or authority, identity and continuity, legal state,
material disposition, processing and coverage effects, record eligibility and
required authority-note meaning, review route, and decision fingerprint. It is
an input to deterministic rendering and corpus construction, not a Search
Record or permission to publish.
_Avoid_: Model answer, free-form legal opinion, Approval, Pinecone mutation

**Legal Item**: A uniquely tracked legal authority such as an Act, judgment, or
publisher-maintained Principles Title.
_Avoid_: Search record, source file

**Official Version**: One immutable source-supported consolidation,
compilation, correction, edition, rolling publisher update, or other published
version belonging to a Legal Item. For Principles, “official” means publisher-
authorized; it does not make the material primary law.
_Avoid_: Latest file, current record, legal-status event without published text

**Legal Status Event**: An immutable sourced change in legal effect or status,
such as commencement, repeal, expiry, or revival, that does not by itself claim
that a new Official Version was published.
_Avoid_: Fabricated Official Version, inferred current text

**Hong Kong Gazette Event Evidence**: The exact issued Gazette artifact,
operative provision, publication identity, dates, and affected-location mapping
used to prove a specific Hong Kong legislation event. It proves the event, not
the resulting consolidated wording.
_Avoid_: HKeL Official Version, HTML search result, reconstructed consolidation

**Provision**: A stable legal location within legislation from which one or
more search records may be derived.
_Avoid_: Chunk

**Case Proposition**: One material legal answer from one precisely attributed
judicial reasoning path. Its searchable record carries a labelled source-
faithful derived statement, the necessary facts, issue, qualifications,
application and result, and the smallest complete set of exact original-
language judgment passages needed to verify it under ADR 0060. One judgment
may produce zero, one, or many.
_Avoid_: Principle, sentence, whole-case summary, unsupported paraphrase

**Case Proposition Coverage Ledger**: The complete accounting of every
identified opinion, Coverage Unit, context dependency, candidate, accepted
proposition, and evidence role for one exact Official Version under ADR 0062.
It ends in one reproducible completion, Quarantine, blocked, or invalid result.
It prevents silent truncation and unsupported zero-proposition claims, but its
arithmetic does not by itself prove that every semantic judgment was correct.
It is an internal evidence artifact rather than a Search Record.
_Avoid_: Model context window, proposition count, proof from extractor silence

**Coverage Unit**: One ordered, source-mapped structural part of an accepted
original judgment artifact, such as an opinion paragraph, heading, footnote,
table, order, disposition, schedule, appendix, or source-scaffolding part. Each
unit occurs exactly once in primary coverage and ends resolved, quarantined,
or blocked. A resolved unit is proposition evidence, necessary context, or
examined non-propositional material.
_Avoid_: Token chunk, model packet, untracked repeated context

**Reference Proposition Map**: The hidden versioned Hong Kong Cases Legal Desk
answer map for one semantic extraction evaluation judgment under ADR 0063. It
records required and forbidden legal meanings, exact attribution and evidence,
controlling qualifications, permitted equivalent wording and boundaries, and
the correct zero, Quarantine, or blocked result. It is not one preferred
summary string and is never supplied to the evaluated workflow.
_Avoid_: Model answer, production proposition, prose-similarity target

**Case Proposition Workflow Admission**: The decision that one exact complete
combination of parser, structure and segmentation contracts, extraction method,
validators, renderer, Source Rulebook, processing build, evaluation packages,
applicable model, prompt, settings, provider contract, and operational profiles
passed ADR 0067's exact semantic, deterministic, context, retry, cost,
monitoring, and revalidation gates. Admission has immutable `CANDIDATE`,
`EVALUATING`, `ADMITTED`, `SUSPENDED`, `REVOKED`, and `SUPERSEDED` lifecycle
states. It never transfers to a changed component or authorizes production by
itself.
_Avoid_: Approved model name, deployment approval, aggregate benchmark score

**Case Proposition Workflow Admission Profile**: The immutable ADR 0068
candidate definition that binds one exact complete workflow, one Evaluation
Suite Package and evaluator fingerprint, and the exact provider, model
snapshot, prompts, executable schemas, settings, token and output ceilings,
timeouts, backoff, concurrency, currency budgets, ordinary diagnostic
thresholds, provider data-handling values, and non-critical drift thresholds.
The protected sealed inventory and Reference Proposition Maps belong to the
suite, and evaluation results belong to the Run Set; neither is profile
content. A profile instantiates ADR 0067 but cannot weaken its complete-
workflow identity, 20% minimum context reserve, repetitions, exact
deterministic gates, zero-critical-error rule, high-risk gates, bounded
attempts, or suspension rules.
_Avoid_: Mutable deployment settings, model alias, permission to tune until pass

**Case Proposition Evaluation Suite Package**: The immutable ADR 0068 package
that binds the exact synthetic and sealed-real catalogues, coverage and
selection matrices, three permissioned evidence views, hidden Reference
Proposition Maps, adjudications, deterministic fixtures, evaluator, fixed
gates, schemas, inventory, and canonical root fingerprint used to evaluate one
candidate profile. It contains evaluation truth but no candidate output,
admission result, secret, or production authority.
_Avoid_: Test directory, model benchmark report, admission profile

**Sealed Admission Judgment**: One real Hong Kong judgment selected through
ADR 0068's branch-driven matrix whose exact admission membership, Reference
Proposition Map, adjudication, evaluator labels, and case-level results remain
protected from the evaluated task and ordinary workflow developers. “Sealed”
does not claim the public judgment was absent from provider training. Exposure
removes pristine admission and canary eligibility and triggers replacement and
impact review.
_Avoid_: Secret judgment, guaranteed unseen text, development example

**Evaluation Run Set**: The immutable complete case-by-repetition execution and
result package for one exact Case Proposition Evaluation Suite Package and one
exact frozen Workflow Admission Profile under ADR 0068. It preserves every
attempt, output, deterministic artifact, semantic assertion, metric, gate,
invalid or blocked result, and final `ELIGIBLE` or `NOT_ELIGIBLE` conclusion.
Eligibility permits only the later dual attestation and admission decision.
_Avoid_: Aggregate score, mutable dashboard, production Approval

**Case Proposition Extraction Conformance Catalogue**: The frozen initial Hong
Kong extraction coverage universe under ADR 0064: 132 permanent direct cases,
132 matching primary coverage cells, and 31 high-risk positive/near-miss pairs.
Its synthetic cases define required semantic and deterministic boundaries but
do not replace the mandatory sealed real-judgment extension needed for workflow
admission.
_Avoid_: Model benchmark alone, permanent test-count ceiling, treatment catalogue

**Case Proposition Boundary**: The evidence-backed division between distinct
legal answers under ADR 0061. Independently usable answers split; the elements,
exceptions, qualifications, applications, and exact support needed for one
complete answer remain together. The boundary is decided before token or byte
measurement and never arises merely from paragraphs, headings, or model limits.
_Avoid_: Chunk boundary, paragraph boundary, token split, topic similarity

**Indivisible Overlong Case Proposition**: One complete Case Proposition that
still exceeds a pinned serving limit after optional repetition is removed, the
smallest complete exact support is used, and faithful concise derived wording
is revalidated. It enters Quarantine rather than being fragmented into records
that require a query-time join.
_Avoid_: Serving parts, shortened qualification, evidence-only fragment

**Case Dossier**: A non-authoritative grouping object connecting separately
delivered trial, appeal, supplementary, costs, remedy, and procedural decisions
from related litigation. Each delivered judicial decision remains its own
Legal Item.
_Avoid_: Judgment Legal Item, whole-case Search Record

**Later Treatment**: One evidence-backed directional relationship from the
exact decision, version, opinion, and passages of a later judgment to one exact
earlier Case Proposition. It records how the later judgment applies, follows,
distinguishes, doubts, criticises, disapproves, overrules, or otherwise affects
that proposition. Affirmance, variation, reversal, setting aside, and remittal
are recorded separately as appellate-disposition facts rather than being
collapsed into the treatment class. A link to a separately searchable
proposition in the later judgment is useful when one exists but is not
required.
_Avoid_: Prediction, whole-case label, duplicate incoming and outgoing edges

**Incoming Treatment View**: The internal projection keyed by one treated
earlier Case Proposition that shows which later judgments treated it and how.
It is derived from the authoritative Later Treatment relationships and may
drive the earlier proposition's current `authority_note` or selection result.
_Avoid_: Separate relationship copy, raw citation list, Pinecone record

**Outgoing Treatment View**: The internal projection keyed by one treating
later judgment and, when available, its treating Case Proposition that shows
which exact earlier propositions it treated and how. It is derived from the
same Later Treatment relationships and supports impact analysis, corrections,
audit, and reprocessing.
_Avoid_: Whole-case treatment summary vector, outbound authority-note field

**Exceptional Change Review**: Human Hong Kong Cases treatment review reserved
for a controlling decision that changes the structure of binding authority
itself, or expressly replaces a foundational constitutional or jurisdiction-
wide doctrine with independently cross-doctrinal and high corpus impact. A
Court of Final Appeal decision, novelty, bounded overruling, reinstatement, a
new legal test, or a large uniform batch does not qualify by itself.
_Avoid_: Review of every adverse treatment, subjective importance label,
operational anomaly stop

**Principles**: A jurisdiction-specific material family of source-faithful
publisher-derived legal principles, named with its jurisdiction, such as
Australian Principles or Singapore Principles.
_Avoid_: One cross-jurisdiction Reference Works family, Case Propositions

**Principle**: One source-faithful publisher paragraph, or one deterministic
serving part of that paragraph, represented as a `type: "principle"` Search
Record.
_Avoid_: Case Proposition, silently rewritten atomic rule

**Hong Kong Regulatory Materials**: The jurisdiction-specific material family
for formal non-legislative regulatory requirements administered by an accepted
Hong Kong regulator or front-line regulatory body. Its initial scope is the
HKEX Main Board and GEM Listing Rules under ADR 0054, represented with
`type: "regulatory"`.
_Avoid_: Policy, Hong Kong Legislation, Hong Kong Principles, general guidance

**HKEX Listing Rule**: One current effective formal requirement or expressly
incorporated rule component from the Main Board or GEM Listing Rules. It is a
non-statutory exchange regulatory rule made under the Securities and Futures
Ordinance and approved by the SFC, not legislation or publisher commentary.
_Avoid_: SFC statutory rule, consultation proposal, FAQ, unincorporated guidance

**Hong Kong English Regulatory Record**: One `type: "regulatory"` Search Record
containing the exact prevailing English HKEX Listing Rule text and English
applicability context for one market, rule location, effective state, and
transition branch under ADRs 0072 and 0073. It uses the smallest complete
official rule-bearing unit that is independently usable with its required
governing context and contains no official or generated Chinese source block.
_Avoid_: Bilingual regulatory record, Chinese-only duplicate, parallel language vector

**HKEX English Source Unit**: One ordered source-supported semantic part of an
accepted prevailing English HKEX product, such as a rule, definition entry,
list item, note, table header or row group, fee branch, Form instruction or
field group, appendix paragraph, or Practice Note unit. Website containers,
PDF pages, line wraps, individual blank fields, and renderer-created parts are
not units merely from presentation.
_Avoid_: Token chunk, page region, Pinecone record, arbitrary sentence

**HKEX English Partition Frontier**: The ordered set of largest complete
official English child units that are individually safe to serve with all
required context after an overlong normal HKEX record recursively descends
through its source structure under ADR 0073.
_Avoid_: Fixed paragraph level, character chunks, sliding-window overlap

**HKEX English Source-Unit Coverage Proof**: One immutable internal ADR 0073
proof mapping every meaning-bearing current English unit to exactly one primary
record owner or explicit blocked or quarantined result, labelling repeated
dependencies, and accounting separately for context-only, presentation-only,
future, historical, and excluded units. Complete accounting does not itself
prove that a Release Scope is serving-ready.
_Avoid_: Record count, parser-success report, Pinecone metadata field

**HKEX Regulatory Conformance Suite Package**: The immutable ADR 0074 package
binding one evidence-to-decision catalogue, one decision-to-artifact
deterministic catalogue, one frozen coverage matrix, strict case packages,
applicable `hk-regulatory` rulebook and contract fingerprints, high-risk pairs,
critical-error rules, reproducibility proof, and complete package fingerprint.
It proves an exact processing build only through a separate conformance
attestation and does not prove real-source currency or authorize serving.
_Avoid_: Retrieval benchmark, production source snapshot, model admission, release approval

**HKEX Regulatory Evidence-to-Decision Case**: One strict synthetic ADR 0074
case that tests whether accepted source-shaped evidence produces the correct
structured Legal Desk result for source authority, membership, ownership,
effective state, disposition, record boundary, dependency, or uncertainty. Its
hidden accepted result never enters a later proposal component's inputs.
_Avoid_: Free-form answer grading, deterministic renderer fixture, real-law decision

**HKEX Regulatory Decision-to-Artifact Fixture**: One strict synthetic ADR 0074
fixture that begins from frozen accepted facts or a Legal Desk Decision and
requires exact canonical records, measurements, partitions, source-unit
coverage, traceability, identity, readiness, failure, and no-side-effect
artifacts. It does not rediscover legal meaning.
_Avoid_: Semantic proposal task, retrieval evaluation, live pipeline run

**HKEX Regulatory Semantic Proposal Tasks**: The four change-gated ADR 0076
generative-LLM task contracts: update analysis, update challenge, record
analysis, and record challenge. They propose exact evidence-bound mappings,
semantic boundaries, dependencies, transitions, and objections only after
deterministic admission and only for baseline, changed, or unresolved work.
They never decide legal state, rewrite source text, render final records, issue
identity, or authorize serving.
_Avoid_: Legal Desk, generic regulatory chatbot, final record generator, scheduled model call

**Regulatory Retrieval and Answer Admission Package**: The immutable ADR 0077
profile binding one exact English Regulatory corpus, multilingual query and
relevance suite, embedding and Pinecone-compatible retrieval workflow,
Ask.Legal Query Contract and application build, downstream answer model and
prompt, three-layer results, slice gates, critical-error rules, monitoring, and
complete fingerprint. It separately proves retrieval, frozen-context answer
behavior, and their end-to-end integration and authorizes none of them merely
by existing.
_Avoid_: Regulatory conformance suite, model marketing claim, production serving approval

**HKEX Optional Chinese Translation Evidence**: An official HKEX Chinese
translation preserved outside ordinary serving and release readiness for
terminology, evaluation, investigation, audit, or possible future design. It
does not replace required English evidence or change a Search Record merely by
changing. It affects current processing only when it exposes a possible defect
in the controlling English identity, version, effective state, wording, or
completeness.
_Avoid_: Current wording authority, release dependency, Pinecone Chinese block

**HKEX Rule Component Instance**: One Main Board-owned or GEM-owned Legal
Location that official evidence proves is part of that exact Listing Rule
rulebook, such as a rule, incorporated note, appendix unit, Practice Note,
Regulatory Form, or Fees Rule. Identical wording or one shared source artifact
does not merge the two board-owned identities.
_Avoid_: Website entry, shared HKEX record, guidance page, PDF page

**HKEX Applicability Branch**: One exact Listing Rule wording plus the
supported cohort, transaction, reporting period, time window, external
condition, or other limitation controlling when it applies. ADR 0071 decides
effective state at this level because one update or Legal Location may contain
several differently timed or concurrently current branches.
_Avoid_: Whole-update state, universalized transition, update number as effect

**HKEX Effective-State Decision**: One immutable cutoff-bound ADR 0071 result
that binds an applicability branch to its component, board, exact update and
current-product evidence, effective facts, transition, lineage, applied rule,
state, reason, and fingerprint. Branch decisions are authoritative; the
component inventory retains a derived summary for complete accounting.
_Avoid_: Publication-date inference, clock-only promotion, serving approval

**HKEX Rule Component Inventory Package**: One immutable cutoff-bound ADR 0069
package that explicitly accounts for every entry in the declared HKEX
rule-component inventory universe; assigns separate membership, board
ownership, derived component effective-state, complete branch decisions,
material-disposition, and processing results; and
reports source-entry, component, current-state, and serving-readiness
completeness for Main Board and GEM separately. The actual component list is a
versioned registry artifact, not an ADR or a Pinecone inventory.
_Avoid_: Website crawl, PDF table of contents, Search Record list, current rulebook alone

**HKEX Core Current-Source Set**: The five ordinary ADR 0070 Registered Source
roles used to bound and construct the current Hong Kong Regulatory Materials
database: rulebook catalogue, consolidated rulebooks, Regulatory Forms, Fees
Rules, and final rule updates. Their reconciled union defines the declared
source-entry universe; no one role proves it alone.
_Avoid_: Every potentially useful HKEX page, downstream LLM context, one controlling source

**HKEX Supplemental Trigger Source**: The exact official Registered Source
temporarily assigned a heightened checking obligation while one pending
conditional Listing Rule amendment depends on its event. The source and its
evidence remain historically preserved after the condition ends; only the
extra monitoring obligation is temporary.
_Avoid_: Generic external-trigger feed, absence of evidence proves no trigger

**HKEX Rulebook Basis Evidence**: Fingerprinted official statements pinned to
one `hk-regulatory` Source Rulebook version to justify source precedence,
language relationship, component inclusion or exclusion, and the standing SFC
approval framework. It is not a separately polled current-rule feed or content
automatically sent to the downstream LLM.
_Avoid_: Ordinary release dependency, current rule text, SFC per-update approval receipt

**Principles Title**: One independently publisher-maintained title or work
tracked as a Legal Item within a jurisdiction's Principles. A platform or
collection containing several titles is a grouping boundary rather than one
legal authority.
_Avoid_: Principles paragraph, publisher website, cross-jurisdiction family

**Legal Location**: One register-tracked place within a Legal Item, such as a
provision, Schedule item, judgment location, or maintained Principles paragraph.
Its internal identity is separate from its visible locator.
_Avoid_: Section number alone, filename, Search Record

**Structured Legal Location**: A Schedule, Schedule Part or item, table, form,
form Part, or other officially identified legislation structure tracked under
its parent Legal Item or Legal Location. Independently locatable official units
may receive child identities; ordinary cells, blanks, visual rows, coordinates,
and renderer-created parts do not receive identity merely from layout.
_Avoid_: PDF region, every cell as a Legal Location, serving-part identity

**Search Record**: One immutable validated, independently searchable
representation of legal material. A Serving State whose approved payload
changes must select a different exact Search Record, including when
`authority_note` changes. A previously unseen payload receives a new ID; an
exact preserved record may be reselected only with proved current support.
_Avoid_: Mutable vector, source snapshot, permanent Legal Item

**Serving Payload Fingerprint**: The lowercase `sha256:<64-hex>` digest of the
RFC 8785 JCS-canonical UTF-8 bytes of one Search Record's exact six-field
`metadata` object. It excludes the register-issued Search Record ID so identity
and content proof remain separate. The Desired-State Inventory's Search Record
`content_fingerprint` has this meaning under ADR 0078.
_Avoid_: Hash of record ID, vector fingerprint, raw serializer output

**Hong Kong Bilingual Legislation Record**: One Hong Kong legislation Search
Record whose single `metadata.text` contains corresponding English and
Traditional Chinese content for the same Legal Location, Official Version, and
operative state. It is embedded and delivered as one record.
_Avoid_: English-only record, Traditional-Chinese-only duplicate, language-field join

**Hong Kong Bilingual Text Layout**: The canonical English-first, Traditional-
Chinese-second representation of one Hong Kong Bilingual Legislation Record.
Both blocks are labelled as authentic text; English-first is a deterministic
format, not an authority ranking. Overlong records split only at matching
official legal boundaries and keep both languages together.
_Avoid_: Monolingual fallback, arbitrary token chunk, observation-date header

**Partition Frontier**: The ordered set of largest complete, source-supported
bilingual legal units that are individually safe to place in an overlong
record part with all required context. Only an oversized branch descends to its
next official aligned level.
_Avoid_: Sentence chunks, one fixed split level, token slices

**Dependency Closure**: The smallest complete source-supported set of governing
headings, lead-ins, headers, local definition scope, qualifications, notes, and
other context needed to understand one record part independently. It is
bilingual for HKeL legislation and prevailing-English-only for HKEX Regulatory
Materials. Required repeated context is labelled and measured; useful but
unnecessary background is not included.
_Avoid_: Sliding-window overlap, omitted lead-in, copied target provision

**Primary Source-Unit Coverage Proof**: An internal proof that every authentic
English and Traditional Chinese source unit occurs exactly once as primary
content and in source order across a record partition. Labelled repeated
dependencies point to their original units without concealing a gap or primary
duplication.
_Avoid_: Text-present check, Pinecone metadata field, unlabelled duplication

**HKeL Dual-Representation Evidence Bundle**: The matching English and
Traditional Chinese HKeL XML, corresponding verified or assisted official HKeL
copies, source metadata, hashes, deterministic mappings, and reconciliation
report for one applicable Official Version. XML constructs the canonical
serving payload; the matching HKeL copies support its official text and
version. Both representations must reconcile before the record can proceed.
_Avoid_: PDF serving payload, XML-only authority proof, fuzzy text match

**HKeL Reconciliation Fixture**: One immutable stable synthetic example that
binds minimal HKeL-shaped XML and applicable PDF evidence, pinned source
interpretation, expected legal-content mapping, canonical bilingual output when
permitted, ordered rule references, and an exact pass, block, or Quarantine
result. It tests the rulebook but proves no real law.
_Avoid_: Production source snapshot, approximate example, AI evaluation prompt

**HKeL Fixture Package**: One immutable synthetic conformance package containing
a strict `fixture.json`, separately hashed declared inputs, and separately
hashed exact expected artifacts. Structural and semantic validation together
prove the fixture; the package is not a Pinecone schema or production evidence.
_Avoid_: One giant escaped JSON file, broad feature tag, real source snapshot

**HKeL Fixture Catalogue**: The frozen strict `catalogue.json` that binds every
required HKeL fixture ID, group, package path, package fingerprint, and common
contract fingerprint. Completeness is exact; an unlisted or missing package is
a failure.
_Avoid_: Test discovery glob, representative sample, mutable test list

**Statutory Note**: A footnote or note that the pinned HKeL specification and
Hong Kong Legislation Source Rulebook classify as part of the legislation or
its prescribed legal structure. Its exact marker, body, attachment, order, and
bilingual relationship are preserved in `metadata.text`.
_Avoid_: Every item visually labelled “note”, HKeL publisher context

**HKeL Publisher Note**: Official HKeL explanatory, editorial, navigation, or
source context that the pinned rules classify as non-legislative. It remains in
evidence and internal traceability, not in `metadata.text`. If it reveals a
material reliance limitation, the Legal Desk must approve a separate controlled
English authority-note warning clause or withhold the record.
_Avoid_: Statutory Note, HKeL Editorial Record, raw publisher prose as warning

**Official Textual Equivalent**: Complete structured text supplied by the
official publisher and explicitly mapped by the pinned specification and
rulebook as a faithful equivalent of a meaningful image. OCR, AI-generated alt
text, reviewer prose, and nearby text are not official textual equivalents.
_Avoid_: Image summary, extracted guess, convenient replacement text

**Cross-Reference Relationship**: An internal evidence-backed link from exact
official referring words to an officially identified target or an explicit
unresolved or out-of-scope target state. It preserves target resolution without
pasting target wording into the referring Search Record or creating a query-
time join.
_Avoid_: Expanded quotation, silent citation correction, LLM lookup dependency

**HKeL Assisted-Copy Evidence Bundle**: The matching English and Traditional
Chinese HKeL XML, corresponding official HKeL assisted copies, source metadata,
hashes, deterministic mappings, source-classification record, and
reconciliation report for any covered Hong Kong Legislation item. XML
constructs the canonical serving payload; the assisted copies provide accepted
Ask.Legal text-and-version evidence without being represented as statutorily
verified. A newer complete assisted version may proceed instead of an older
verified version under ADR 0081.
_Avoid_: Verified-copy claim, non-HKeL webpage, monolingual fallback, PDF-only construction

**HKeL Publication Specification Bundle**: The exact fingerprinted official
XSD, data dictionaries, Important Notices, catalogue descriptions, and explicit
interpretation mapping pinned by one Hong Kong Legislation Source Rulebook
version. It defines how HKeL artifacts are parsed and verified but proves no
item-specific legal event or wording.
_Avoid_: HKeL legal-text bundle, mutable live documentation, serving content

**HKeL Instrument Disposition Registry**: The immutable versioned part of the
Hong Kong Legislation Source Rulebook that accounts for every observed HKeL
Instruments & Others entry and every legal object it represents or proves. It
separates the A-series source filing category from actual legal nature,
Release Scope ownership, serving disposition, evidence relationships,
authority-note consequences, and identity.
_Avoid_: Include-all A-number list, HKeL category as legal classification

**HKeL Past-Data Evidence**: On-demand HKeL inventory, XML, and applicable
verified PDFs for an earlier legislation version, used only for a specific
baseline, investigation, recovery, audit, or evaluation task. It has no
ordinary weekly freshness gate. Exact past wording requires reconciliation
with matching past verified PDFs; similarity or disappearance cannot prove
present law, a legal event, or identity continuity.
_Avoid_: Current-law source, legal event evidence, historical Pinecone record

**HKeL Editorial Record**: An official record with legal status that identifies
editorial amendments, affected legislation, and effective dates. It proves its
stated editorial event but is not the resulting consolidated Official Version
or serving text.
_Avoid_: Gazette instrument, verified consolidated text, reconstructed version

**Excluded LegCo Legislative-History Material**: Legislative Council Bills,
Bills Database records, proceedings, debates, votes, explanatory memoranda, and
committee papers that are outside the automated Hong Kong Legislation
pipeline. They may be consulted manually as non-controlling research but are
not Registered Sources, required evidence, Source Snapshots, or serving input.
_Avoid_: Gazette event evidence, current law, mandatory discovery source

**Reconstructed Consolidation Artifact**: One immutable internal Hong Kong
Legislation result permitted by ADR 0080 when a complete proved chain of
operative amendments can be applied deterministically to the latest applicable
bilingual HKeL base supported by matching verified or assisted official HKeL
copies under ADR 0081. It is not an HKeL Official Version. Its Search Records otherwise follow ordinary legislation serving,
source, citation, quotation, retrieval, and ranking rules with the exact
mandatory reconstruction authority note. ADR 0079 is the fallback when any
reconstruction proof fails. ADR 0085 fixes its strict `rca_` package: complete
authentic-language trees and source units, reconstructed location units,
bilingual and dependency proofs, derivation map, identity-lineage result, and
ordinary-renderer requirements.
_Avoid_: HKeL Official Version, guessed consolidation, model-authored final
text, separate serving material type

**Reconstruction Derivation Map**: The complete ADR 0085 proof assigning every
final source unit and changed structural relation to either byte-identical base
content or one exact admitted operation and its authentic-language amendment
evidence. It has no generated, inferred, translated, manual, corrected-by-
engine, or catch-all origin.
_Avoid_: General provenance note, model rationale, best-effort source link

**Hong Kong Reconstruction Operation Registry**: The immutable, versioned,
fingerprinted ADR 0082 allow-list of exact amendment tree-and-text operations.
It fixes eight stable operation classes, their evidence, selectors,
preconditions, ordering, atomicity, postconditions, failure reasons,
traceability, and required conformance coverage. Anything not defined by the
registry is unsupported and produces no reconstructed result.
_Avoid_: Free-text patch, catch-all operation, fuzzy amendment application,
implementation-private edit

**Reconstruction Plan**: One immutable complete ordered set of registry
operation instances for an exact HKeL base, evidence set, cutoff, applicability
branch, and dependency closure. It must pass deterministic validation before
execution and is never serving text. ADR 0084 fixes its strict JCS JSON
contract and register-issued `rpl_` identity; its `rop_` operation instances
bind exact amendment and effect events, source units, selectors, before and
after states, dependencies, atomic groups, and authentic-language order.
_Avoid_: Model answer, partial amendment list, mutable work queue

**Reconstruction Execution Report**: The immutable machine-checkable account
of every operation's before state, exact match, result, after state, bilingual
and dependency checks, hashes, and final outcome. It proves reproduction and is
linked through traceability rather than placed in Pinecone. ADR 0084 fixes its
strict JCS JSON contract and register-issued `rex_` identity. A failed Report
accounts for applied, failed, and not-run operations and emits an explicit zero
artifact result rather than partial text.
_Avoid_: Free-text reasoning, authority note, source snapshot

**Hong Kong Reconstruction Conformance Suite**: The strict two-layer ADR 0083
suite, expanded by ADRs 0086 and 0087, that freezes 32 evidence-to-plan and 31
plan-to-artifact cases, 63 matching primary coverage cells, and 35 controlled
high-risk pairs. Together with the 121 ordinary Hong Kong Legislation cases, a
reconstruction-enabled profile has 184 direct cases. Every case, cell, and pair
member is mandatory; there is no pass-percentage substitute.
_Avoid_: Sample test set, model evaluation score, real-source currency proof

**Reconstruction Capability Profile**: One immutable exact specification of
the rulebook, registries, contracts, conformance universe, deterministic build,
security boundaries, runtime identity, and candidate-writing capabilities that
must agree before real Hong Kong reconstruction processing may be activated.
ADR 0087 gives it a register-issued `rcp_` identity. The repository currently
has design documents only and therefore remains `DESIGN_ONLY`.
_Avoid_: Accepted ADR, implementation plan, production deployment permission

**Reconstruction Capability Attestation**: Independent immutable proof that
one exact Reconstruction Capability Profile and build passed every mandatory
ordinary and reconstruction case, reproducibility run, containment test, and
architecture boundary. ADR 0087 gives it a register-issued `rct_` identity.
It can support candidate-processing activation but is never human Approval or
permission to promote, access Pinecone, or change Azure.
_Avoid_: Unit-test report, legal opinion, promotion Approval

**Reconstruction Comparison Basis**: The ADR 0086 proof that a reconstructed
artifact and later valid HKeL text represent the same Legal Item, safely
reconciled locations, authentic languages, event horizon, applicability
branch, operative period, and dependency boundary. Additional overlapping
changes make comparison non-isolatable; the pipeline never reverses them to
manufacture a score.
_Avoid_: Latest-versus-old raw diff, reverse reconstruction, similarity score

**Status Coverage Map**: The complete internal assignment of every relevant
Legal Location in one HKeL item to exactly one current-law serving disposition
at a fixed observation cutoff. It records inherited status only when the
Source Rulebook proves the inheritance rule and records every exact child
exception. It is release-accounting evidence, not Pinecone metadata.
_Avoid_: One status flag for a mixed item, authority-note field, inferred inheritance

**Bilingual Alignment Group**: One or more consecutive English source units
and one or more consecutive Traditional Chinese source units that official
identifiers and a pinned rule establish as the same item, version, location,
operative state, and parent relationship. One-to-one, one-to-many,
many-to-one, and many-to-many groups are allowed; translation similarity cannot
create the mapping.
_Avoid_: Translated chunk pair, equal paragraph-count assumption, LLM pairing

**Authority Note**: The required `metadata.authority_note` string carried with
every Search Record and delivered unchanged to the downstream LLM. The exact
value `"None"` means no approved record-level authority note applies at that
Serving State's observation cutoff. A real note uses controlled evidence-backed
warning clauses first, budgeted material support clauses second, and material
neutral context clauses last. It has no fixed support- or explanation-clause
count and is a compact current authority summary, not an exhaustive citation
history or numerical authority score.
_Avoid_: Case-only treatment field, optional lookup-only note, raw citation
list, citation-count score, reviewer notes, null

**Hong Kong Authority Note**: A real `metadata.authority_note` on any Hong Kong
Search Record, written in English only and delivered unchanged as an internal
authority-and-reliance instruction to the downstream LLM. It is not translated
merely because Hong Kong legislation `metadata.text` is bilingual. ADR 0080's
reconstruction note expressly instructs the model to reproduce its warning
portion in an answer that uses the record; the instruction portion itself
remains internal.
_Avoid_: Bilingual authority note, embedded note, translated reconstruction
warning, exposed instruction clause

**Identity Alias**: A source URL, provider identifier, title, citation, visible
locator, or other external label attached to a register-owned identity as
evidence or display data.
_Avoid_: Authoritative internal identity

**Lineage Relationship**: An immutable typed evidence-backed link explaining
how identities relate through correction, replacement, renumbering, split,
merge, reinstatement, or another material-specific event.
_Avoid_: Silent overwrite, inferred similarity

**Search Record Selection Event**: An immutable append-only fact recording
that one frozen Serving State selected, stopped selecting, or reselected an
exact Search Record at its cutoff. It is separate from Search Record lineage,
so reselecting an older exact record never creates a backward lineage edge.
_Avoid_: Search Record mutation, cyclic lineage, current-state flag on a record

**Semantic Treatment Evaluation**: A schema-bound evaluation of whether an
LLM proposes the correct judgment passages, proposition mapping, treatment,
scope, opinion attribution, and uncertainty. It tests semantic understanding,
not byte-exact serving consequences or preferred prose.
_Avoid_: End-to-end promotion test, free-form similarity score, legal decision

**Treatment Contract Fixture**: One strict synthetic deterministic package
that starts from frozen treatment facts and requires exact validation, Rule
Trace, authority note, identity, selection, lineage, embedding, release,
review-routing, and no-side-effect artifacts. It proves contract behavior, not
real law or LLM understanding.
_Avoid_: Model benchmark, real judgment evidence, approximate expected output

**Treatment Coverage Matrix**: The frozen complete list of required Hong Kong
later-treatment conformance cells and their direct semantic or deterministic
cases, high-risk positive and near-miss pairs, checkpoints, and contract
bindings. It—not file discovery or a target count—proves catalogue completeness.
_Avoid_: Test tags, directory scan, aggregate score, arbitrary fixture count

**Hong Kong Treatment Conformance Catalogue**: The accepted initial catalogue
frozen by ADR 0059: 155 permanent direct cases, 155 matching primary coverage
cells, and 21 high-risk positive and near-miss pairs. Its counts arise from the
accepted coverage matrix; future requirements may add versioned cases but may
not reassign or silently change an existing ID or normative result.
_Avoid_: Suggested examples, fixed test quota, model-admission proof

**Treatment Conformance Package**: One immutable hashed semantic evaluation or
deterministic fixture with a strict non-leaking manifest, declared inputs,
expected artifacts, coverage cells, contract bindings, and package inventory.
The model never receives package or expected-answer metadata.
_Avoid_: Prompt folder, unregistered real judgment, self-discovered test

## Processing and model boundaries

**Generative-LLM Task Runner**: The sole legal-processing-worker gateway that
may hold generative-LLM provider credentials and make generative-LLM calls. It
accepts only a stable explicitly enabled task contract and returns a structured
evidence-bound proposal; it has no approval, retirement, release, or serving
authority.
_Avoid_: AI worker, general model access, autonomous Legal Desk

**Pipeline LLM Task**: One stable schema-bound use of the Generative-LLM Task
Runner with pinned evidence inputs, prompt, model configuration, output schema,
and evaluation rules. ADR 0053 allocates Hong Kong later-treatment analysis and
ADR 0065 allocates Hong Kong Case Proposition extraction. The latter's ADR 0066
task contracts may run only as part of an `ADMITTED` exact workflow under ADR
0067, instantiated through ADR 0068's suite, protected-evidence, run-set, and
pre-frozen profile contract; they remain disabled until actual executable
packages and a profile pass. Hong Kong later treatment remains disabled pending
its own exact runtime task contracts and admission.
ADR 0043 continues to defer Gazette-event extraction and other unallocated
candidate tasks.
_Avoid_: Unnamed AI step, assumed enabled task, legislation status decision

**Case Proposition Analysis Task**: The first bounded semantic LLM pass under
ADRs 0065 and 0066, with stable identity
`hk-case-proposition-analysis/v1`. It receives only admitted, source-mapped
judgment evidence and proposes material legal answers, unit uses, exact supporting ranges,
qualifications, context, applications, boundaries, attribution, handoffs, and
uncertainty. It cannot prove complete coverage, accept its proposal, determine
current authority, or create a serving record.
_Avoid_: One-shot judgment distillation, Legal Desk decision, record publisher

**Case Proposition Challenge Task**: The separate semantic LLM pass under ADR
0065, fixed as `hk-case-proposition-challenge/v1` by ADR 0066, that actively
tests an already validated proposition proposal for
omissions, unsupported breadth, missing qualifications, wrong attribution,
wrong boundaries, incomplete dependencies, and an unsafe zero or complete
result. It emits exact evidence-linked objections and cannot edit, accept, or
reject the proposal.
_Avoid_: Majority vote, duplicate analysis, automatic correction

**Semantic Task Pass**: One complete semantic workflow over one exact judgment,
not necessarily one provider call. Under ADR 0066, a short judgment may fit one
call, while a long judgment may require complete opinion-aware packet calls
plus one judgment-level integration or result-challenge call. Every primary
Coverage Unit remains accounted for, so model context cannot define coverage.
_Avoid_: Exactly one API call, token-window coverage, silent chunking

**Evidence Range ID**: An immutable request-scoped identifier for one exact
original-language span already mapped by deterministic processing to preserved
judgment evidence. Under ADR 0066, an LLM selects these IDs for evidence roles;
deterministic code copies the preserved text into authoritative quotation
fields.
_Avoid_: Model-generated quotation, paragraph number as permanent identity

**Semantic Task Request Kind**: One closed schema branch inside an admitted
Pipeline LLM Task that changes packet shape without expanding semantic
authority. ADR 0066 fixes four analysis kinds and four challenge kinds for
complete judgment, packet, judgment-level integration or result challenge, and
bounded re-analysis or final challenge.
_Avoid_: Free-form mode, new task authority, implementation retry

For Hong Kong later treatment, the LLM is the primary semantic proposal
mechanism because judgment language varies. Deterministic processing validates
evidence, structure, identities, authority facts, schemas, coverage, and
permitted claims; it does not infer substantive treatment from keywords or the
absence of keywords. The Legal Desk retains decision authority.

For Hong Kong Case Proposition extraction, deterministic processing owns
source admission, complete structure, exact evidence, ledger arithmetic,
proposal validation, identity, rendering, and finalization. The **Case
Proposition Analysis Task** proposes legal meaning and the independent **Case
Proposition Challenge Task** searches for semantic mistakes or omissions.
Deterministic reconciliation resolves every objection, and the Legal Desk
accepts only a fully accounted result. Human review is reserved for exact
unresolved ambiguity or an accepted Source Rulebook trigger.

**Embedding Adapter**: The promotion-worker component that sends only
validated selected `metadata.text` to a pinned embedding model. An embedding
model produces retrieval vectors; it is not a generative LLM and cannot make a
legal conclusion.
_Avoid_: LLM task runner, legal classifier, record approver

**Ask.Legal Answer LLM**: The downstream application model that receives
retrieved Pinecone metadata and produces an answer. It is outside this pipeline
and does not authorize any pipeline task to call a generative LLM.
_Avoid_: Pipeline LLM Task, embedding model, Legal Desk

## Corpus and promotion

**Management Register**: The durable ledger of sources, observations, legal
items, states, decisions, work, approvals, and serving history.
_Avoid_: Evidence vault, report

**Initial Current Baseline**: The first accepted complete current-state
accounting for one Release Scope when the pipeline has no preserved previous
accepted current bundle. It may establish clear present state from complete,
consistent accepted current evidence without replaying the full history, but
it makes no unsupported historical event, date, or continuity assertion.
_Avoid_: No-change release, historical reconstruction, legacy-index import

**Hong Kong Cases Current-Authority Baseline**: The first complete greenfield
accounting of every required Hong Kong binding-case court-year scope at one
cutoff, including propositions, material later treatment, authority notes,
current-authority exclusions, zero-record decisions,
Quarantines, and Coverage Gaps.
It has no arbitrary case-age cutoff and imports no legacy identity.
_Avoid_: Judgment dump, recent-cases window, legacy Pinecone migration

**Hong Kong Cases Ordinary Update**: The post-baseline comparison of one new
frozen cutoff with one exact accepted predecessor. It acquires only affected
judgments, follows their complete proposition-and-treatment impact across
court-year scopes, reuses exact unaffected records and releases, and keeps
no-change, accounting, serving, blocked, and quarantined results distinct.
HKLII may generate leads but cannot establish any database effect.
_Avoid_: Whole-corpus reprocessing, HKLII-driven legal update, delta release

**Court-Year Case Release Scope**: The Hong Kong Cases ownership and rebuild
boundary defined by one issuing-court family and the original decision calendar
year. It does not limit cross-scope treatment or legal authority; all required
scopes compose into one Hong Kong Cases target.
_Avoid_: Publication-year batch, treatment boundary, separate legal database

**Release Scope**: A stable, versioned, non-overlapping ownership boundary for
which one responsible desk must account for the complete set of Search Records
at an observation cutoff.
_Avoid_: Folder, arbitrary batch, Pinecone target

**Corpus Release**: A sealed immutable complete snapshot of one Release Scope
at one observation cutoff, containing zero or more validated Search Records and
its completeness, non-searchable disposition, and integrity evidence. It is not
a delta.
_Avoid_: Distillation output, change list, latest dataset

**Desired-State Inventory**: One immutable complete composition for a serving
target. It selects exactly one Corpus Release for every required Release Scope
and materializes the exact expected Search Record IDs, fingerprints, and owners.
_Avoid_: One profile release, release-reference list, deletion list

**Promotion Manifest**: The sole sealed immutable approval and execution
envelope joining the base Serving State, candidate Serving State Definition,
desired states, exact targets, routing, settings, changes, recovery evidence,
validations, ordered actions, rollback, and invalidation conditions under one
fingerprint.
_Avoid_: Report, deployment script, secret bundle, permission to improvise

**Approval**: One immutable authenticated human decision bound to one exact
Promotion Manifest fingerprint and one execution lineage, with a validity
window, objective preconditions, and append-only lifecycle events.
_Avoid_: Permission to improvise, reusable token, general consent

**Serving State Definition**: The sealed immutable fingerprinted description of
one complete candidate search state: environment, routing, indexes,
inventories, query contracts, coverage, verification requirements,
predecessor, and recovery references.
_Avoid_: Activation record, mutable status, index-name setting

**Serving State**: A Serving State Definition whose append-only build and
verification evidence proves it is eligible to serve Ask.Legal.
_Avoid_: Partially updated index, latest index, unverified definition

**Serving State Lifecycle Event**: An immutable append-only fact recording what
happened to one Serving State, such as verification, activation, rollback
activation, failure, protection, or retirement.
_Avoid_: Mutable state-status field, overwritten serving history

**Query Contract**: The versioned, fingerprinted rules that define the serving
record shape and how every Ask.Legal query path reads, filters, and passes those
records to the downstream LLM.
_Avoid_: Incidental application build, undocumented metadata convention

**Record Traceability Lookup**: An immutable fingerprinted internal map keyed
by Search Record ID that points to its legal identities, source evidence,
release ownership, authority-note evidence, and optional review grouping or citation
data. It contains pointers rather than source files and is not read by
Ask.Legal or the downstream LLM during an ordinary query.
_Avoid_: Query database, Evidence Vault, LLM authority-note channel

**Record Traceability Lookup Revision**: One complete immutable strict package
whose canonical manifest binds every serving-record profile and exactly one
declared shard for every Release Scope selected into the target. Its external
root fingerprint transitively binds all shard bytes without a self-reference.
_Avoid_: Mutable lookup table, query-time join, directory scan

**Record Traceability Shard**: One immutable manifest-declared, fingerprinted,
Search-Record-ID-sorted NDJSON entry file for one exact Release Scope and
selected Corpus Release. An unchanged shard may be reused in a later lookup
revision; a traceability-only correction replaces only the affected shard and
root revision.
_Avoid_: Unbounded monolithic lookup, inferred file set, Corpus Release

**Pinecone Index Generation**: One immutable, fully built and verified
Pinecone Index for a jurisdiction, identified by a date-led unique name.
_Avoid_: Live index being edited, latest index

**Routing Configuration**: The complete versioned mapping from every served
jurisdiction to its exact Pinecone Index Generation. Ask.Legal receives the
active index names through Azure App Service application settings.
_Avoid_: Independent uncoordinated index-name changes, latest indexes

**Cutover**: The controlled switch from one verified Serving State to another.
_Avoid_: Upsert, deployment start

## Uncertainty and coverage

**Quarantine**: A preserved state for material that cannot safely proceed
because evidence, identity, legal status, or processing support is incomplete
or conflicting.
_Avoid_: Rejection, deletion, no change

**Coverage Gap**: A known period or area in which the searchable corpus may not
reflect supported current material.
_Avoid_: No search result, quarantine

**Carry-Forward Selection**: An explicit Desired-State Inventory choice to keep
previously approved material searchable with a visible Coverage Gap. Ordinary
carry-forward applies when no affirmative change is proved; ADR 0079 defines a
separate known-stale analytical mode for one exact legislation condition.
_Avoid_: Silent reuse, verified current release

**Known-Stale Analytical Carry-Forward**: The narrow serving mode used when
accepted official evidence proves that legislation changed but the updated
official consolidated text is not yet available and ADR 0080 reconstruction
cannot pass. Every affected location for which valid latest applicable
official HKeL text is held receives a searchable warned analytical fallback,
whether its supporting copy is verified or assisted and whether or not it was
previously selected in Pinecone. The record uses unchanged official text, a
mandatory English authority-note warning, a new warned serving-payload
identity, coverage status, and complete release accounting. It is analytical
material, not current or reconstructed text.
_Avoid_: Current wording, silent stale record, reconstructed consolidation,
historical-search feature

**Withholding Release**: A new complete Corpus Release that omits unsafe or
unsupported records from its searchable set while accounting for every
withheld item, reason, and supporting evidence. Withholding is not a declaration
that the Legal Item ceased to exist.
_Avoid_: Empty placeholder, inferred retirement

**Waiting Room**: Preserved enacted or assented legislation that has not met
the commencement and official-consolidation requirements for search.
_Avoid_: Searchable prospective law

**Frozen Principles Scope**: A jurisdiction-and-source-specific Principles
scope whose exact last approved records remain selected and usable after
licence expiry while every source-specific acquisition and content update is
stopped.
_Avoid_: Withholding, retirement, deletion, verified-current refresh

## Relationships

- A **Registered Source** produces many **Observations**.
- A jurisdiction-and-material **Source Rulebook** satisfies the common **Source
  Rulebook Contract**, references one or more Registered Sources, and binds each
  Legal Desk decision to a stable rule ID, version, fingerprint, and preserved
  evidence.
- Every Hong Kong current-update decision preserves its ordered **Rule Trace**.
  Passing a later rule cannot cure an earlier evidence or reconciliation
  failure, and schema-valid output with the wrong trace fails conformance.
- An **Observation** may trigger one **Scraper** capture and one or more
  **Source Snapshots**.
- Every Hong Kong **Official Judgment Listing Entry** at a fixed cutoff has one
  explicit acquisition outcome. One Judicial Decision may have several
  listings and **Official Judgment Artifacts**, while one valid decision may
  produce zero Case Proposition Search Records. Inventory accounting, evidence
  coverage, and search output remain separate completeness results.
- Every accepted Hong Kong judgment and identified opinion has complete
  **Case Proposition Coverage Ledger** accounting. A qualifying record puts
  both its clearly labelled derived legal statement and its minimum exact
  original-language judgment support in `metadata.text`, because the
  downstream LLM cannot read the internal traceability store during an
  ordinary query. An unresolved possible proposition enters Quarantine rather
  than becoming a guessed record or a valid zero-record decision. Every
  **Coverage Unit** and proposition candidate has an exact outcome, every
  accepted record maps back to the ledger, and a valid no-proposition result
  requires complete source and treatment-screening accounting.
- Every Hong Kong **Case Proposition Boundary** follows independent legal use
  and meaning rather than source layout or size. Same-opinion repetition
  consolidates, opinion roles remain separate except for exact express
  adoption, and an **Indivisible Overlong Case Proposition** enters Quarantine
  rather than being split into incomplete query-dependent fragments.
- Hong Kong Case Proposition extraction uses separate semantic evaluation and
  deterministic contract-conformance suites. A hidden **Reference Proposition
  Map** controls semantic truth; exact fixtures control mechanical truth; and
  **Case Proposition Workflow Admission** binds only the complete fingerprinted
  workflow. ADR 0067 requires all 132 synthetic cases plus the sealed real-
  judgment extension, three ordinary and five high-risk semantic repetitions,
  exact deterministic repetition, no critical error, every high-risk
  distinction in every repetition, and separate dimension and slice gates. ADR
  0068 separates the immutable Evaluation Suite Package, pre-frozen Workflow
  Admission Profile, complete Evaluation Run Set, and final dual-attested
  admission; fixes protected evidence views and branch-driven real-judgment
  selection; and forbids tuning thresholds on sealed results. ADR 0067 also
  fixes a 20% minimum context reserve, bounded attempts, cost reservation,
  weekly canaries, a complete suite at least every 90 days, change-triggered
  revalidation, and automatic suspension. Retrieval quality remains a separate
  later gate.
- The initial Hong Kong **Case Proposition Extraction Conformance Catalogue**
  freezes 132 direct cases, 132 primary coverage cells, and 31 high-risk pairs.
  Future real-judgment admission cases extend rather than rewrite its synthetic
  boundaries.
- Hong Kong Case Proposition extraction follows ADR 0065's two-pass staged
  hybrid. Deterministic processing admits and maps the complete source,
  validates and reconciles proposals, and finalizes accepted records. The
  **Case Proposition Analysis Task** proposes legal meaning; the independent
  **Case Proposition Challenge Task** looks for omissions and unsafe results.
  The Legal Desk accepts complete resolved ordinary work, while only exact
  unresolved ambiguity or a versioned rulebook trigger reaches human review.
- Hong Kong source roles use daily, weekly, monthly or event-triggered, or
  on-demand monitoring tiers. HKeL past material and official archival Gazette
  evidence are on demand only; Editorial Records remain weekly. A deterministic
  unchanged Watcher result creates no LLM, embedding, or large-artifact work.
  A generative LLM may run only through an enabled **Pipeline LLM Task** after
  a real signal survives acquisition, deduplication, and deterministic
  validation.
- A **Legal Desk** applies one immutable jurisdiction-and-material Source
  Rulebook to preserved evidence and prior state and emits an immutable **Legal
  Desk Decision** and Rule Trace. It may accept fully resolved ordinary work
  automatically; its **Legal Desk Owner** governs the rules and exact human-
  review triggers rather than reviewing every item.
- A **Legal Item** has one or more **Official Versions** and may have many
  **Legal Status Events**.
- A **Principles Title** is a Legal Item; its editions or complete rolling
  update states are Official Versions and its publisher paragraphs are Legal
  Locations.
- The Main Board Listing Rules and GEM Listing Rules are separate Legal Items
  and Release Scopes within **Hong Kong Regulatory Materials**. Their complete
  effective consolidated states are Official Versions and their rule-bearing
  units are Legal Locations.
- Every frozen Hong Kong Regulatory Materials cutoff has one **HKEX Rule
  Component Inventory Package**. It accounts for every entry in the exact
  registered inventory universe and keeps membership, board ownership,
  effective state, material disposition, processing outcome, and serving
  readiness separate. Complete accounting may expose a blocked or quarantined
  scope and therefore does not itself make the scope ready to serve.
- The **HKEX Core Current-Source Set** supplies that registered inventory
  universe through five reconciled roles. Optional online-rulebook research,
  general SFC material, guidance, and consultations are not ordinary release
  dependencies or downstream LLM inputs.
- One `FUTURE_CONDITIONAL` rule may depend on an **HKEX Supplemental Trigger
  Source**. Only its heightened monitoring obligation ends after resolution;
  the Registered Source and exact evidence remain immutable history.
- **HKEX Rulebook Basis Evidence** belongs to the versioned Source Rulebook,
  not the Search Record metadata or ordinary Pinecone corpus.
- Every searchable HKEX component produces one **Hong Kong English Regulatory
  Record** under ADRs 0072 and 0073. Its complete official unit, dependency
  closure, canonical projection, overlong partition, and exhaustive source-unit
  accounting are proved by one **HKEX English Source-Unit Coverage Proof**.
  Official Chinese translations are **HKEX Optional Chinese Translation
  Evidence**, not ordinary release dependencies or serving text. Chinese-query
  retrieval must still pass complete multilingual evaluation before the family
  can serve.
- The **HKEX Regulatory Conformance Suite Package** separately proves evidence-
  to-decision correctness and exact decision-to-artifact behavior through one
  frozen branch-driven coverage matrix. Its future complete successful build
  attestation does not prove real-source currency or authorize a release,
  Pinecone, or deployment.
- Each accepted **HKEX Rule Component Instance** belongs to exactly one Main
  Board or GEM Legal Item. One source artifact may prove components in both
  rulebooks, but it does not create one cross-market component or Search
  Record. Nearby guidance remains accounted non-rule material rather than
  entering the component inventory through website placement.
- A **Case Dossier** groups related judicial-decision **Legal Items** without
  merging their identities.
- An **Official Version** may produce zero or more **Search Records**.
- Every searchable Hong Kong legislation location produces one **Hong Kong
  Bilingual Legislation Record**, never parallel language-only records.
- Every Hong Kong Bilingual Legislation Record follows the **Hong Kong
  Bilingual Text Layout**. Operational traceability stays outside
  `metadata.text`, and any serving parts remain aligned to official structure.
- Every applicable HKeL-derived current-law record is supported by an **HKeL
  Dual-Representation Evidence Bundle**. The XML-built text and both authentic-
  language verified or assisted official HKeL copies must reconcile; the files
  and comparison evidence remain outside Pinecone and the ordinary query path.
- An **HKeL Reconciliation Fixture** fixes how a small evidence condition must
  be interpreted. `PASS` clears only the reconciliation gate; missing evidence
  or an invalid deterministic candidate blocks; existing conflicting evidence
  enters Quarantine; and unknown source semantics open Source Contract Review.
- Every partially operative HKeL item has a complete **Status Coverage Map**.
  A mixed-status authority-note warning clause may qualify only an otherwise searchable record; it
  cannot place an uncommenced, repealed, expired, historical, or unknown
  location into current search.
- Every authentic-language unit belongs to exactly one **Bilingual Alignment
  Group**. A mismatch blocks or quarantines the smallest safely separable legal
  branch; governing or unbounded context broadens the affected branch.
- A **Statutory Note** remains exact bilingual legislation and stays attached
  to what it qualifies. An **HKeL Publisher Note** stays outside legal text; a
  material reliance limitation instead requires a separate approved English
  authority note or withholding decision.
- A meaningful image contributes serving text only through an **Official
  Textual Equivalent**. Without one, complete image evidence is preserved but
  the affected location is quarantined rather than described by AI or OCR.
- Exact source cross-reference words remain in `metadata.text`; their
  **Cross-Reference Relationship** is resolved and revised internally without
  expanding, modernizing, or silently correcting the source words.
- The pinned **HKeL Publication Specification Bundle** defines how that source
  evidence is interpreted. A changed or conflicting specification opens
  **Source Contract Review** rather than silently changing a parser, rule, or
  serving record.
- The **HKeL Instrument Disposition Registry** routes every Instruments &
  Others legal object by actual legal nature rather than its A-series filing
  category. It assigns one Release Scope and one primary serving disposition,
  while separately recording evidence relationships and authority-note consequences.
  Unknown or unaccounted entries cannot enter current search.
- A Hong Kong **Legal Status Event** and its exact affected-location mapping
  may exist before a new official consolidation. The pipeline does not use
  them to materialize a **Reconstructed Consolidation** under the current
  design.
- **Hong Kong Gazette Event Evidence** may support that event, while the
  matching **HKeL Dual-Representation Evidence Bundle** separately supports
  the searchable consolidated text.
- **HKeL Past-Data Evidence** may supply a missing historical baseline or
  bounded investigation evidence on demand, while an **HKeL Editorial Record**
  proves its official editorial amendment and remains weekly monitored. Neither
  replaces the current **HKeL Dual-Representation Evidence Bundle**.
- **Excluded LegCo Legislative-History Material** creates no automated
  pipeline outcome, source dependency, authority note, or Search Record. Optional
  manual consultation cannot replace accepted Gazette or HKeL evidence.
- A **Legal Item** contains zero or more **Legal Locations**, whose visible
  locators may change without automatically changing their internal identities.
- A **Structured Legal Location** preserves official parentage and identifiers.
  Its deterministic plain-text representation keeps complete table header
  paths, form controls, dependencies, and source order without treating visual
  geometry as identity.
- A changed Search Record has a new ID and an explicit **Lineage Relationship**
  to its predecessor or predecessors.
- A later judicial-decision **Legal Item** may create **Later Treatment** for an
  exact earlier **Case Proposition** without changing the earlier judgment's
  Official Version. A no-proposition later judgment may still create the
  relationship because its decision, opinion, and treating passages are the
  required source anchor.
- Every accepted case-treatment relationship remains once in the internal
  graph. The Management Register derives its **Incoming Treatment View** and
  **Outgoing Treatment View** from the same ID and fingerprint; the views do
  not duplicate the edge, Search Record, or vector.
  The related **Authority Note** renders a budgeted current selection: every
  distinct mandatory warning first, then every material non-repetitive support
  and neutral explanation that fits. Equivalent events are consolidated and
  ranking controls ordering and compression near the pinned budget rather than
  imposing a fixed clause count. Bare citation, consolidated repetition,
  citation counts, and numeric strength scores remain outside the downstream
  LLM note.
- Material source-supported treatment reasoning may appear in the later
  judgment's ordinary Case Proposition `metadata.text`. Pinecone receives no
  separate treatment-relationship record, exhaustive outgoing-treatment list,
  case-specific metadata field, or whole-case treatment vector. Exact citator-
  style enumeration would require a separately approved graph query path.
- Only the **Generative-LLM Task Runner** may execute a **Pipeline LLM Task**.
  The applicable Legal Desk and deterministic validators retain decision
  authority. ADR 0053 accepts whole-judgment discovery and candidate-level
  proposal stages for Hong Kong later treatment. ADR 0065 accepts separate
  proposition-analysis and proposition-challenge stages for Hong Kong Case
  Proposition extraction, and ADR 0067 permits those stages only inside an
  exact `ADMITTED` workflow whose immutable **Case Proposition Workflow
  Admission Profile** passes all gates through ADR 0068's exact Evaluation
  Suite Package and Evaluation Run Set. No such executable package or profile
  has been created or admitted. Their outputs remain non-authoritative. ADR
  0043 still defers Gazette-event extraction and every other unallocated task.
- The **Embedding Adapter** is a separate promotion capability, and the
  **Ask.Legal Answer LLM** is a separate downstream application capability.
- Every **Search Record** carries one **Authority Note** string. Changing it,
  including between `"None"` and a real note, changes the serving payload.
- A real **Hong Kong Authority Note** is English only. The downstream LLM
  applies it regardless of query language and may express its effect in the
  answer language.
- Every selected **Search Record** has one matching **Record Traceability
  Lookup** entry validated before promotion. Ask.Legal does not join that
  lookup at query time.
- A **Frozen Principles Scope** keeps its exact last approved Search Records,
  authority-note values, and reusable embeddings in later serving states while
  blocking every update for that Principles source.
- An **Initial Current Baseline** freezes one cutoff, accounts for every item
  in its Release Scope, and may accept a clear present state without proving
  every earlier legal event. A named ambiguity opens targeted historical work;
  unresolved material remains quarantined rather than reconstructed.
- The **Hong Kong Cases Current-Authority Baseline** selects every required
  **Court-Year Case Release Scope** at one cutoff and reconciles material later
  treatment across all scopes. Old age alone does not remove a proposition,
  and a no-proposition decision still participates in treatment screening.
- A **Hong Kong Cases Ordinary Update** starts from that accepted baseline or a
  later accepted predecessor, expands every genuine change through its complete
  treatment impact, and reuses unrelated court-year releases. **HKLII Discovery
  Evidence** may open the work but never proves its legal result.
- A **Corpus Release** belongs to one **Release Scope** and contains zero or
  more **Search Records**.
- A **Desired-State Inventory** selects exactly one Corpus Release for every
  required Release Scope and contains the matching flattened expected-record
  inventory for one serving target.
- A **Promotion Manifest** contains one or more Desired-State Inventories and
  receives at most one current **Approval**.
- A **Routing Configuration** names the exact Pinecone Index Generation for
  every jurisdiction in one Serving State.
- A **Promotion Manifest** binds one candidate **Serving State Definition**.
- Successful build and verification events make its exact definition an
  eligible **Serving State**.
- A successful **Cutover** appends an activation event that makes one verified
  **Serving State** active for its environment.
- **Pinecone** is part of a Serving State but is never the Evidence Vault or
  Management Register.

## Example dialogue

> **Developer:** “The Watcher found that an Act page changed. Can the Scraper
> send the new text to Pinecone?”
>
> **Legal-domain owner:** “No. Preserve a Source Snapshot first. The Legal Desk
> must decide whether it is a supported Official Version. Valid Search Records
> then enter a Corpus Release, the complete Desired-State Inventory, and a
> frozen Promotion Manifest before the human can approve a new Serving State.”

## Flagged ambiguities

- **Current** is material-specific: operative official text for legislation;
  a case proposition together with required later-treatment information for
  cases; and either the latest maintained source-faithful paragraph for a
  jurisdiction's Principles or the exact last approved Principle selected
  under a licence-expiry freeze; and, for Hong Kong Regulatory Materials, the
  exact HKEX rule text and applicability proved effective at the frozen cutoff,
  including any current transitional branch.
- **Principle** refers only to the jurisdiction-specific Principles material
  family. Judicial material uses **Case Proposition**.
- **Stage** previously implied a separate repository. In the greenfield system,
  acquisition, legal processing, release construction, approval, and promotion
  are capability boundaries inside one modular monorepo.
- **Release** does not mean authorization. A **Corpus Release** is an immutable
  artifact; production still requires a valid **Approval** for a complete
  **Promotion Manifest**.
- A zero-record **Corpus Release** is valid only when its complete accounting
  proves that the scope has no supported current Search Records or explicitly
  withholds every item under evidence-backed decisions. A failure or Quarantine
  without those dispositions cannot masquerade as an empty release.
- The accepted serving envelope uses the five legacy base fields plus required
  `authority_note`. This contract does not adopt Distillation's source-path-and-locator
  identity semantics. Greenfield identity is register-owned and will be
  specified independently.
- For legislation, a matching URL, title, citation, visible provision number,
  wording, or document position never proves continuity by itself. Source
  moves preserve proved identities; new official consolidations create new
  Official Versions; repeal-and-substitution, split, merge, and re-enactment
  create the new Legal Item or Legal Location identities required by ADR 0012.
- For case law, one separately delivered judicial decision is one Legal Item;
  the wider litigation belongs in a Case Dossier. An exact proposition
  conclusively overruled by an authoritative court is retired from current
  Pinecone rather than served with a warning clause, while doubted or criticised
  propositions remain eligible only with the authority note required by ADR
  0014 as amended by ADRs 0050 and 0055. A former exact supported record may be
  reselected through a new Search Record Selection Event without backward
  lineage.
- For each jurisdiction's Principles, the Principles Title is the Legal Item,
  the publisher's edition or complete rolling update state is the Official
  Version, and the paragraph is the Legal Location. Licence expiry freezes and
  carries forward only the affected jurisdiction-and-source scope without
  authority-note change, withholding, retirement, or further updates under ADRs
  0015, 0017, and 0050.
