---
status: accepted
date: 2026-08-13
refines:
  - 0014
  - 0060
depends_on:
  - 0011
  - 0043
  - 0055
refined_by: "0065"
---

# Define Hong Kong Case Proposition split and merge rules

Case Proposition boundaries follow legal meaning rather than paragraph,
sentence, heading, token, or model-context boundaries. The system decides the
genuine proposition boundaries before measuring the final serving payload.

The default rule is:

- split when two legal answers can be searched, stated, or applied
  independently; and
- keep material together when removing one element, condition, exception, or
  piece of context would make the remainder incomplete or misleading.

Repeated or fragmented expression merges only when the legal answer, issue,
scope, opinion, and authority role are the same. Similar words or subject
matter are insufficient.

## Conceptual split test

Create separate Case Propositions when any of these conditions applies:

1. the judgment answers different legal questions;
2. either answer can govern a later case without the other;
3. the answers use materially different legal tests, burdens, standards,
   statutory interpretations, exceptions, remedies, or jurisdictional rules;
4. the answers arise from different opinions or authority roles;
5. the judgment gives independent alternative grounds, each sufficient to
   support the relevant result; or
6. an application establishes a materially distinct legal branch rather than
   merely applying the same rule to another fact.

Several paragraphs, headings, citations, steps, examples, parties, factual
findings, or applications do not by themselves prove that several
propositions exist.

## Integrity test

Keep the following together when they operate as one rule:

- the elements of one cumulative or balancing test;
- a rule and the exception, proviso, threshold, definition, burden, or
  qualification that controls its meaning;
- a general statement and the application needed to show what the court
  actually decided;
- a proposition stated in one passage and narrowed or clarified later in the
  same reasoning path; and
- non-contiguous passages needed together to prove one complete answer.

The system must not publish earlier broad wording as one proposition and a
later controlling qualification as another. Doing so would create a broader
rule than the judgment expressed.

## Repetition and same-opinion merging

When one opinion repeats, paraphrases, or applies the same proposition several
times with the same scope, create one record. Its `metadata.text` uses the
smallest complete non-repetitive exact supporting ranges. Every other
occurrence remains preserved in the internal evidence and Case Proposition
Coverage Ledger.

Several same-opinion fragments may form one proposition when one states the
rule, another supplies its qualification, and another shows its application.
Different wording does not prevent merging when the legal answer is the same.
Identical wording does not justify merging when issue, scope, authority role,
or legal effect differs.

A general rule and fact-specific application normally remain one record. A
separate application proposition exists only when the judgment makes that
application an independently usable legal conclusion or a distinct branch of
the rule. Repeating one rule against another set of facts creates no new
record.

## Multi-opinion judgments

Opinion boundaries are legal boundaries:

- one joint or lead opinion joined by other judges produces one proposition
  record per genuine proposition, not one duplicate per judge;
- a judge who only agrees creates no duplicate proposition;
- a concurrence or dissent may produce its own material proposition, but it
  remains a separate record whose authority role is prominent in
  `metadata.text`;
- additional reasoning in a partial concurrence remains separate from the
  exact lead reasoning the judge adopted;
- separate opinions reaching the same result do not merge merely because
  wording or outcome overlaps; and
- a plurality without one expressly supported common reasoning path is not
  rewritten into a synthetic majority proposition. Each qualifying position
  remains separately attributed, and unresolved current authority enters
  Quarantine at the smallest safe boundary.

One record may use passages from another opinion within the same delivered
judgment only when the operative opinion expressly adopts those exact reasons
and the adopted scope is clear. The record contains the adopting passage and
adopted support and labels the attribution accurately. Similarity, silence,
shared outcome, or inferred agreement is not adoption.

A separately delivered later judgment that merely adopts, follows, or approves
an earlier judgment without stating a self-contained proposition creates Later
Treatment rather than a duplicate proposition. When it independently states
and applies a complete proposition, that proposition may qualify under ADR
0060 while the treatment relationship remains separately recorded.

## Independent and alternative grounds

Independent grounds become separate propositions. For example, a time-bar
ground and a distinct merits ground are independently searchable even when
both support dismissal.

Reasoning stated only on an assumed, hypothetical, or unnecessary basis is not
presented as an operative holding. It qualifies separately only when it meets
ADR 0060's materiality rule and its obiter or hypothetical role is explicit.

## Shared context

Every proposition repeats only the smallest context required to stand alone.
Several records from one judgment may repeat a short identifier or necessary
fact, but they do not duplicate a large common narrative. There is no context-
only vector or whole-case overview that the downstream LLM must retrieve with
the proposition.

Internal judgment and issue grouping supports processing, audit, and retrieval-
quality evaluation. It creates no additional Search Record, vector, or
Pinecone metadata field.

## Overlong indivisible propositions

After applying the legal boundary rules, the system renders the exact final
`metadata.text` under ADR 0060, measures it with the pinned embedding tokenizer,
and measures the complete six-field metadata payload against the pinned byte
ceiling.

For an overlong record, the only permitted order is:

1. remove genuinely optional and repetitive context under the canonical
   renderer;
2. retain only the smallest complete non-repetitive exact source ranges, while
   preserving every omitted range internally and making no invisible change
   inside a quotation;
3. shorten the derived statement only when the complete meaning and every
   material qualification remain exact and the new wording passes ADR 0060
   again; and
4. split only when the legal boundary test proves that independently usable
   propositions actually exist.

An indivisible, fully supported proposition that still exceeds a hard limit
enters Quarantine and creates the applicable Coverage Gap. It is not divided
into token, sentence, paragraph, or evidence fragments; no set of records may
require a query-time join to restore its meaning; and no qualification,
application, result, authority role, or necessary exact support may be omitted
to force a fit.

ADR 0050's authority-note budget remains independent. A mandatory warning is
never removed or weakened to make the complete record fit.

## Initial extraction and correction lineage

Several propositions correctly found during first extraction are independent
initial records. They receive no artificial split lineage.

When later review finds that one existing record improperly combines several
propositions, the next serving state stops selecting it and creates or selects
the supported separate records with `split_from` processing-correction
lineage. When several records improperly duplicate or fragment one
proposition, the next state stops selecting them and creates or selects one
complete record with `merged_from` processing-correction lineage.

These are pipeline corrections, not judicial treatment. Every prior record,
evidence item, release, selection event, and serving history remains preserved.
A newly discovered proposition receives no invented predecessor.

An official corrected judgment follows ADR 0014. Every proposition whose
support, context, attribution, or boundary changed is re-evaluated. An exact
unaffected record is reused only with proved continuing support; affected
payloads receive the required new immutable records and lineage.

## Allocation boundary

This decision defines the required split, merge, evidence, size, uncertainty,
and lineage result. It does not choose whether deterministic code, a
generative LLM, the Legal Desk, a human, or a combination finds the boundary.
ADR 0043 initially deferred that allocation; ADR 0065 later assigns semantic
boundary proposals and challenge to two LLM passes, exact invariant validation
to deterministic processing, and acceptance or bounded unresolved ambiguity
to the Legal Desk and narrow human review.

## Consequences

The Hong Kong Cases Source Rulebook, renderer, schemas, Case Proposition
Coverage Ledger, extraction evaluations, correction rules, Query Contract,
and retrieval-quality tests must agree with this decision. Exact coverage-
ledger encoding, conformance catalogue, overlong limits, and exact runtime
task admission remain later work.

This decision authorizes documentation only. It does not authorize
implementation, source acquisition, model or embedding calls, release
publication, Pinecone or Azure access, promotion, deployment, commit, or any
remote action.
