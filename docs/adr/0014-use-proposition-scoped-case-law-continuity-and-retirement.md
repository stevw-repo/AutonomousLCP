---
status: accepted
date: 2026-08-11
amended_by:
  - 0039
  - 0050
  - 0053
  - 0055
  - 0058
depends_on:
  - 0013
supersedes_in_part:
  - decision-2026-08-06-pinecone-current-copy
---

# Use proposition-scoped case-law continuity and retirement

One separately delivered judicial decision is one Legal Item. The entire
lawsuit or litigation history is not one Legal Item. A **Case Dossier** groups
related trial, appeal, supplementary, costs, remedy, and procedural decisions
for navigation and accounting, but the dossier is not itself a legal authority
or Search Record.

Within one judicial-decision Legal Item:

- an **Official Version** is one official publication, correction, revision,
  or reissue of that same decision;
- hierarchical **Legal Locations** identify majority, joint, concurring,
  dissenting, plurality, or court reasons and their supporting paragraphs or
  passages; and
- each **Search Record** is one exact self-contained material Case Proposition
  supported by one or more attributed Legal Locations.

A trial judgment, appellate judgment, supplementary judgment, and separately
delivered costs or remedy judgment are normally separate Legal Items linked in
the same Case Dossier. An official correction or revised-reasons publication
is instead a new Official Version of the same Legal Item when the issuing court
expressly presents it as a correction or replacement of that decision.

## Judgment and proposition continuity

| Event | Identity and serving result |
|---|---|
| Official URL, provider location, or mirror moves while the artifact is proved unchanged | Keep the Legal Item, Official Version, and Legal Locations. Reuse a Search Record only when its complete six-field payload is exact. |
| Duplicate official copy is discovered | Attach the new evidence or alias to the existing identities; do not duplicate records. |
| Case name, citation, or proceeding number is officially corrected | Keep the Legal Item. Allocate a new Official Version only when a corrected judgment was published. Select a different exact Search Record if any serving field changed; allocate it when that payload is new. |
| Court publishes corrected or revised reasons for the same decision | Keep the Legal Item and allocate a new Official Version. Reconcile every opinion and passage; replace only affected proposition records and reuse exact unaffected records whose continuing support is proved. |
| An unofficial copy differs from the approved official judgment | Do not create an Official Version from it. Preserve and quarantine any unresolved authenticity or content conflict. |
| Court delivers supplementary reasons, a later costs decision, remedy decision, or another separately delivered decision | Normally allocate a new Legal Item linked through the Case Dossier. Treat it as an Official Version only when the court expressly says it corrects or replaces the earlier decision. |
| Several proceeding numbers receive one delivered set of reasons | Use one Legal Item with all proved proceeding numbers as aliases; do not duplicate its propositions per number. |
| Similar names identify separate delivered decisions | Allocate separate Legal Items; title similarity never establishes identity. |
| Paragraphs or opinion structure change in an official revision | Continue a Legal Location only after complete reconciliation proves that it is the same reasons or passage. New, removed, split, merged, or differently attributed opinions receive the appropriate new or ended locations. |
| Our processing corrects the wording of one proposition | Keep the judgment identities. Select a different exact Search Record when the serving payload changes; allocate it with processing-correction lineage when that payload is new. |
| Review discovers an additional supported proposition | Create a new Search Record supported by exact locations; do not invent a predecessor. |
| One record improperly combines two propositions | Retire the combined record from current serving and create the supported successor records linked as split from it. |
| Several records duplicate or improperly fragment one proposition | Create one supported successor linked as merged from the predecessor records and retire those predecessors from current serving. |
| A record is invented, materially unsupported, or wrongly attributed | Retire it as invalid processing output, preserve it and its evidence, and do not describe the event as later judicial treatment. |

No proposition may blend reasons from different opinions or present dissenting,
concurring, or plurality reasoning as a majority holding. A change to judge or
opinion attribution requires review of every affected proposition because its
authority may materially change.

## Later treatment and current-law serving

Later treatment changes the current authority of an earlier proposition; it
does not alter the text or Official Version of the earlier judgment. The later
judgment is a separate Legal Item and the treatment is an evidence-backed
relationship to the exact affected Case Proposition.

| Later event | Current-law result |
|---|---|
| Pending appeal | Record the pending event in the human report. Do not infer a treatment result or automatically change Pinecone. |
| Cited only | Keep the relationship internally. Citation alone proves no endorsement or authority strength and creates no `authority_note` clause. |
| Explained | Keep the proposition. Add `[CONTEXT: EXPLAINED]` only when the explanation materially clarifies the exact proposition's meaning, scope, or use; never render explanation as endorsement. |
| Applied | Keep the proposition. Add a selected `[SUPPORT: APPLIED]` clause when the application is materially useful to proposition-level authority assessment. |
| Followed or approved | Keep the proposition and make the exact treatment eligible for the budget-based `[SUPPORT: ...]` authority summary. Include every material non-repetitive signal that fits; consolidate equivalent repetitive events. |
| Distinguished | Keep the proposition. A distinction alone does not mean the proposition is wrong; add a warning clause only when the Legal Desk determines that the later decision materially limits how the record may safely be stated. |
| Doubted or criticised | Keep the proposition only with a mandatory controlled `[WARNING: ...]` clause in `metadata.authority_note` identifying the treating authority, support, and reliance qualification. |
| Expressly disapproved or refused to follow | When court authority, opinion status, finality, scope, evidence, and an exact consequence rule are clear, automatically accept and report the bounded authority-note or continued-serving result. Uncertainty or a missing rule enters review or Quarantine. |
| Expressly and conclusively overruled in full by an authoritative court | Retire the exact affected proposition from ordinary current-law Pinecone serving. Preserve its identity, payload, evidence, releases, serving history, and `overruled_by` lineage outside Pinecone. |
| Partly overruled | Retire the affected part. Split a combined record only when the earlier judgment itself supports a standalone unaffected proposition; do not rewrite the earlier court into a narrower rule it did not express. |
| Judgment reversed or set aside | Review and retire only propositions whose current authority was actually removed. Do not erase every proposition from the earlier judgment automatically. |
| Treatment scope, court authority, or affected proposition is unclear | Preserve all evidence and quarantine the treatment decision. Do not guess, silently retire, or present the treatment as settled. |
| The overruling or adverse treatment is later withdrawn, reversed, corrected, or superseded | Perform a new evidence-backed Legal Desk decision. A clear rulebook-supported note removal or exact reinstatement may be accepted automatically and reported; disappearance or changed words alone never imply reinstatement. |

This supersedes the earlier warning-only rule for expressly overruled
propositions. An authority-note warning clause is appropriate when a
proposition remains potentially usable but requires qualification. It is not
an adequate safeguard for an exact proposition conclusively shown to be no
longer current authority in the target jurisdiction.

Retirement means exclusion from the next approved current Desired-State
Inventory, not deletion. It requires the complete Corpus Release, inventory,
Promotion Manifest, Approval, and replacement-index process already accepted
for serving changes. Unaffected propositions from the same judgment remain
eligible.

## Authority-note behavior

ADRs 0013 and 0050 apply to every case Search Record.
`metadata.authority_note` is always present. It is exactly `"None"` when no
approved warning, selected material support, or selected material explanation
applies. A controlled rendering places mandatory warning clauses first,
selected support clauses second, and neutral `[CONTEXT: EXPLAINED]` clauses
last. Neutral context is not endorsement. The note is passed with
`metadata.text` to the downstream LLM but excluded from embedding input.

Adding, changing, or removing an authority note makes the Serving State select
a different exact Search Record. It creates a new Search Record ID and forward
authority-note-revision lineage when that exact payload has never been issued;
ADR 0055 instead reselects a preserved exact record when current support is
proved. The full structured treatment history remains in the Management
Register and Evidence Vault. One concise approved current note is rendered into
metadata; raw or conflicting treatment messages are not sent directly to the
LLM. Every accepted relationship remains internally traceable. The renderer
uses operative opinion status, Hong Kong court authority, treatment
significance, exact scope, and continuing status for ordering and budget-based
compression. There is no fixed support- or explanation-clause count. Every
current material non-repetitive signal that fits the pinned metadata and
downstream-context budget is rendered; equivalent events are consolidated.
Bare citations, consolidated repetitive treatment, citation counts, and
numerical authority-strength scores do not enter the note. A treatment event
changes the selected record only when it changes the approved rendering.

ADR 0055 supplies the exact immutable transition map. Internal treatment that
does not change the six-field rendering reuses the Search Record. Full
overruling ends selection with no successor. Partial overruling replaces a
combined record only with narrower propositions independently supported by the
earlier judgment. Exact reinstatement may reselect a former record through a
new append-only selection event; it never creates backward Search Record
lineage.

Every distinct current mandatory warning meaning must fit and appear before
support or context. If faithful consolidation still cannot fit it, the
proposition cannot serve with an incomplete note and follows Quarantine,
withholding, or no-new-target rules. Optional support and context that cannot
fit after faithful consolidation remain internal under the deterministic
ranking rule.

## Required evidence and authority

Every identity or treatment decision records:

- the court, jurisdiction, decision date, proceeding numbers, case names, and
  official citations;
- the complete preserved official judgment and artifact fingerprint;
- official correction, revision, withdrawal, replacement, or appeal evidence;
- the full opinion, judge, and paragraph inventory for each Official Version;
- the exact earlier proposition and supporting passages;
- the later judgment's operative opinion and exact treatment passages;
- the court and jurisdiction relationship that gives the treatment its legal
  effect;
- whether the treatment is whole, partial, or limited to particular facts or
  issues;
- the responsible Legal Desk decision and review state; and
- every created, reused, replaced, split, merged, authority-note-revised,
  retired, quarantined,
  or reinstated identity.

Automated rules may establish source facts, exact equality, and candidate
relationships. Under ADR 0039, only `case-proposition-extraction` and
`later-treatment-proposal` may use the legal-processing worker's generative-LLM
task runner. Those modules may propose structured propositions, citations, and
treatment classifications. Neither an automated rule nor an LLM proposal may
decide that a proposition is overruled, retire it, or resolve ambiguous scope
without the applicable written Legal Desk rule and required human review.

## Consequences

The Management Register needs Case Dossiers, hierarchical opinion and passage
locations, proposition-scoped treatment relationships, authority-note revisions, and
retirement reasons. Corpus construction must support unaffected-record reuse,
processing corrections, proposition split and merge, and exact proposition-
level retirement.

Each jurisdiction's case-law source rulebook must still identify authoritative
courts, official judgment and correction sources, hierarchy rules, required
finality or status evidence, and the exact meaning of treatment classifications
in that legal system. The final Record Traceability Lookup field encoding also
remains open.
