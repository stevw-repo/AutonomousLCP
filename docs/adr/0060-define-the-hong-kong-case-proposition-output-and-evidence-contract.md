---
status: accepted
date: 2026-08-13
refines:
  - 0014
  - 0047
  - 0049
  - 0050
depends_on:
  - 0008
  - 0016
  - 0043
refined_by: "0065"
---

# Define the Hong Kong Case Proposition output and evidence contract

One searchable Hong Kong Case Proposition record represents **one material
legal answer from one attributed judicial reasoning path**. It contains the
minimum facts, issue, qualifications, application, result, and exact original-
language judgment passages needed to understand and verify that answer without
opening the full judgment.

The record is neither a sentence chunk nor a whole-case summary. One judgment
may produce zero, one, or many proposition records.

## Qualification rule

A candidate qualifies as a Case Proposition only when all of these conditions
are satisfied:

1. the legal issue or question is identifiable;
2. the judgment supplies an identifiable legal answer, test, standard,
   interpretation, burden, exception, or other legally usable conclusion;
3. the exact opinion and authority role are established, including joint or
   majority reasoning, adopted reasoning, concurrence, dissent, plurality,
   obiter discussion, or another precisely attributed role;
4. exact source passages support the proposition and every material
   qualification stated in the record;
5. the necessary factual context, procedural posture, application, and result
   can be stated without speculation;
6. the proposition can stand as one honest searchable unit without blending
   separate opinions or collapsing distinct rules; and
7. no unresolved source, version, opinion, support, or attribution conflict
   makes the record unsafe.

Materiality does not require novelty. A familiar rule remains material when the
judgment genuinely uses, establishes, materially explains, or materially
qualifies it in resolving a live issue.

Procedural chronology, party submissions not adopted by the court, bare
citations, quotations that do no material work in the court's reasoning,
issue-free factual findings, outcome-only statements, administrative
directions, and repeated legal wording do not qualify by themselves.

## Required `metadata.text` content

The six-field serving envelope remains unchanged. Every record still has
`text`, `country`, `jurisdiction`, `type`, `source`, and `authority_note`, with
`type: "case"`. This decision fixes a labelled layout inside `metadata.text`:

1. **Case** — case name and official citation;
2. **Court and decision date** — the deciding authority and date;
3. **Opinion and authority role** — exact attribution and the supported role
   of that reasoning;
4. **Legal issue** — the narrow question addressed;
5. **Proposition — derived statement** — a concise source-faithful statement
   of the legal answer, explicitly labelled as derived rather than quoted;
6. **Material context** — only the facts and procedural posture necessary to
   understand scope;
7. **Qualifications or exceptions** — every material source-supported limit;
8. **Application and relevant result** — how the reasoning affected the issue
   and its relevant result; and
9. **Exact judgment support** — the smallest complete set of verbatim original-
   language passages, with stable paragraph or passage locators, that supports
   the derived statement, limits, application, and attribution.

The versioned renderer defines how an inapplicable optional section is
represented. It must never state that no qualification or exception exists
merely because an extractor did not find one.

Both the derived statement and its exact judgment support enter
`metadata.text`, so both are embedded and delivered to the downstream LLM. The
derived statement supports retrieval and direct comprehension. The quoted
passages allow the downstream model to distinguish the pipeline's distillation
from the court's actual words. Exact support cannot remain solely in the
Record Traceability Lookup because Ask.Legal does not join that lookup during
ordinary queries.

The complete judgment, source artifacts, full opinion and passage map,
Judiciary Translation Artifacts, fingerprints, extraction proposals,
validation and review history, internal identities, and non-selected context
remain outside Pinecone in the Management Register and Evidence Vault. The
record carries the minimum complete legal content, not the full evidential
dossier.

## One-record boundary

A multi-element legal test remains one record when its elements operate
together as one rule. Different legal questions or independently applicable
propositions become separate records. A qualification or exception remains
with the rule it limits unless the judgment independently supports it as a
separately usable proposition.

One proposition may rely on several non-contiguous passages within the same
attributed reasoning path. It may not combine incompatible reasoning from
different opinions or present dissenting, concurring, plurality, or obiter
reasoning as an operative majority holding. Express adoption must be recorded
exactly rather than inferred from similarity.

A later judgment that only agrees with, follows, or approves an earlier
authority without expressing a self-contained material legal proposition of
its own does not receive an invented duplicate proposition. The accepted Later
Treatment relationship records that legal effect.

The system creates no sentence-level record, whole-case overview record,
official-translation duplicate, or proposition invented to anchor treatment.

## Coverage, zero records, and uncertainty

Every complete accepted judgment and every identified opinion must be
accounted for. Long judgments may be processed in opinion-aware, structure-
preserving parts with a complete coverage ledger, but silent truncation is
forbidden. Each supplied source part ends in an accounted result: proposition
support, non-propositional material, a recorded dependency on context examined
elsewhere, or a named blocked or quarantined condition.

A valid zero-record result requires complete examination and support for the
conclusion that no distinct material proposition exists. When a material
proposition may exist but its meaning, scope, opinion, support, or attribution
is unresolved, the candidate enters Quarantine. Uncertainty cannot become a
zero-record result, and the pipeline never publishes a guessed proposition.

## Language and authority-note boundaries

ADR 0047 controls language. The derived statement and exact judgment support
use the language actually authored by the court in the supporting opinion or
passages, including genuinely mixed-language material. An optional official
Judiciary translation remains linked evidence and does not create another
record or enter `metadata.text` by default.

`metadata.authority_note` remains a separate required string under ADR 0050.
It summarizes approved current authority information such as material later
treatment; it is not a replacement for the proposition's opinion attribution
or exact supporting passages.

## Allocation remains deferred

This decision specifies the required output, evidence, coverage, and failure
behavior independently of how the candidate is produced. It does not allocate
candidate discovery, materiality analysis, proposition wording, validation,
Legal Desk decision, or human review between deterministic code and a
generative LLM.

ADR 0043 initially deferred the extraction-task allocation. ADR 0065 later
settles the high-level two-pass staged hybrid allocation. That allocation must
satisfy this output contract and separately pin its task identities, evidence
boundaries, schemas, prompts, models, deterministic validation, evaluations,
review rules, costs, and failure behavior before a provider call can be
enabled.

## Consequences

The Hong Kong Cases Source Rulebook, Query Contract, renderer, extraction
conformance universe, cross-language evaluations, Search Record schema, and
Record Traceability Lookup must agree with this contract. Exact splitting for
overlong proposition records, proposition merge and split rules, coverage-
ledger encoding, renderer syntax, schemas, fixtures, and exact runtime task
admission remain later design or specification work.

This decision authorizes documentation only. It does not authorize
implementation, source acquisition, model or embedding calls, release
publication, Pinecone or Azure access, promotion, deployment, commit, or any
remote action.
