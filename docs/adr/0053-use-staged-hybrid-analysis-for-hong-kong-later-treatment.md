---
status: accepted
date: 2026-08-12
amended_by:
  - 0056
amends:
  - 0039
  - 0043
  - 0049
  - 0052
refines:
  - 0014
  - 0018
  - 0031
  - 0048
  - 0050
---

# Use staged hybrid analysis for Hong Kong later treatment

Hong Kong Cases later-treatment screening uses a hybrid of deterministic
processing, bounded generative-LLM proposals, and Legal Desk decisions. This
settles the high-level allocation for this task only. Case Proposition
extraction, Gazette-event extraction, and the allocation of every other
candidate task remain deferred under ADR 0043.

The LLM may inspect a complete judgment to discover and understand possible
treatment, but its whole-judgment answer is never accepted directly as a legal
or serving result. A one-shot instruction such as “read this judgment and
update the database” is forbidden.

## Staged processing

1. **Deterministic admission and structure.** The pipeline validates the
   accepted originating judgment, fingerprints it, identifies opinions and
   paragraph boundaries, extracts formally recognizable citations, resolves
   known identities and aliases, checks court relationships, and prepares the
   coverage ledger.
2. **Whole-judgment discovery.** Through the sole task runner established by
   ADR 0039, a schema-bound LLM may inspect the complete accepted judgment when
   it fits the enabled task limits. It proposes a candidate inventory of
   treatment-bearing passages, including linguistically unusual or implicit
   references. This pass provides context and discovery only; silence is not
   proof that no treatment exists.
3. **Candidate evidence analysis.** Each candidate is processed separately
   with an exact evidence packet containing the treating passages and all
   necessary facts, issues, results, cross-references, qualifications, opinion
   attribution, and earlier-proposition evidence. The LLM may propose the
   affected proposition, controlled treatment class, scope, materiality,
   uncertainty, and exact support.
4. **Deterministic validation.** Non-LLM checks reject nonexistent citations,
   missing passages, wrong identities, mixed opinions, impossible hierarchy
   effects, invalid classifications, unsupported proposition mappings,
   incomplete required fields, and claims outside the supplied evidence.
5. **Legal Desk decision.** The Hong Kong Cases Legal Desk automatically
   accepts and reports a clear ordinary result under an exact Source Rulebook
   rule, or routes uncertainty, ambiguity, and objectively exceptional legal
   change to human treatment review. Only an accepted automated or human-
   reviewed decision can revise `metadata.authority_note`, withhold, retire,
   or reinstate a proposition. Release and production controls remain
   separately deterministic and approval-bound.

If a judgment cannot fit safely in one model task, the pipeline uses
opinion-aware, structure-preserving segments and an explicit ledger accounting
for every supplied opinion and segment. Silent truncation is forbidden. A
second model opinion does not replace missing evidence, deterministic
validation, or Legal Desk authority.

Ordinary updates apply this work only to new, changed, or otherwise affected
judgments within the bounded impact universe from ADR 0052. They do not reread
the complete unchanged corpus on every run. Initial-baseline treatment
screening still accounts for every in-scope judgment required by ADR 0049.

## Semantic-analysis responsibility

The LLM is the primary semantic analyser for treatment-bearing judgment
language. Courts may communicate application, approval, distinction,
limitation, doubt, criticism, rejection, or overruling without using one fixed
vocabulary. Deterministic keyword or phrase rules therefore cannot establish a
substantive treatment class, and failure to match a phrase cannot establish
that no treatment exists.

Deterministic processing still owns source admission, exact passages, opinion
structure, formal citation leads, identities, court and jurisdiction facts,
hierarchy constraints, schema validation, coverage accounting, and rejection
of claims outside the supplied evidence. Those checks constrain and verify the
proposal; they do not substitute for semantic reading. The Legal Desk remains
responsible for accepting, correcting, rejecting, or quarantining the legal
effect.

An express treatment result depends on direct semantic meaning, not the
presence of a magic word. Model confidence, repeated model agreement, HKLII
classification, a headnote, citation count, similarity score, or keyword match
is not legal evidence.

Normal and common treatment consequences do not require individual human
treatment approval once the complete admitted task, evidence, validation, and
rulebook contracts pass. They are automatically accepted with an immutable
Rule Trace and reported to the human. Human treatment review is reserved for
uncertainty or ambiguity and for fixed rulebook triggers identifying an
exceptional change in the current authority structure. This per-treatment
automation does not alter the separately required human Approval for the
complete frozen Promotion Manifest.

## Human-review threshold

The exceptional-change threshold is deliberately narrow. Importance, novelty,
a Court of Final Appeal judgment, express overruling, reinstatement, a new
legal test, or a large but uniform batch is not exceptional by itself. Clear
bounded overruling, reversal or setting aside, evidence-backed reinstatement,
and a safely bounded new or changed test remain automatic rulebook decisions
and are reported.

`EXCEPTIONAL_CHANGE_REVIEW` is permitted only when an operative controlling
decision either:

1. changes the structure of precedent or hierarchy itself, including which
   bodies or classes of decision bind which Hong Kong courts, or invalidates
   an authority class rather than identified propositions; or
2. expressly replaces a foundational constitutional or jurisdiction-wide
   doctrine, affects multiple independent doctrinal lines rather than one
   citation chain, and exceeds both high absolute and proportional Source
   Rulebook impact thresholds.

An LLM does not decide that a trigger is met. Unbounded impact, a missing
accepted rule, or uncertainty about the trigger is `UNCERTAINTY_REVIEW`.
Operational anomaly controls may separately stop unusual volume, cost,
retirement count, or target diffs, but that stop does not reclassify a clear
legal result as exceptional treatment review.

The pinned evaluation contract must report routing outcomes, structured human
corrections or reversals, sampled missed treatment, and exact serving effects.
Changing an impact threshold or routing rule requires a new versioned
rulebook or ADR with an impact declaration; silent calibration is forbidden.
Evaluation sampling does not hold every ordinary treatment for approval.

ADR 0056 separates semantic model evaluation from deterministic contract
fixtures. The model is graded on structured meaning and exact evidence rather
than preferred prose. Downstream authority-note, identity, lineage, selection,
release, and promotion consequences require their own byte-exact fixtures; a
single end-to-end score cannot substitute for either suite.

## Trust boundary

The model is trusted to propose research findings, not to establish current
law. Context-window fit does not prove complete or accurate reading. The
pipeline therefore preserves three distinct artifacts:

- the whole-judgment discovery proposal;
- each candidate's exact evidence-bound treatment proposal; and
- the accepted Legal Desk treatment decision and Rule Trace.

The model cannot establish judgment identity, court hierarchy, opinion status,
legal effect, current authority, authority-note wording, retirement,
Quarantine disposition, release eligibility, Approval, or production action.

## Remaining task-enablement work

This decision accepts the staged hybrid architecture but does not enable a
provider call. Before implementation can enable either model stage, the Source
Rulebook or a later accepted technical contract must pin its stable task IDs,
schemas, prompts, permitted evidence, model and settings, token and size
limits, evaluation corpus and thresholds, confidence and review rules, retry
and failure behavior, cost limits, retention, and revalidation triggers.

This decision authorizes documentation only. It does not authorize
implementation, source access, an LLM or embedding-provider call, release
publication, Pinecone mutation, promotion, or deployment.
