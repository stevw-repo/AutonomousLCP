---
status: accepted
date: 2026-08-13
amended_by:
  - 0059
amends:
  - 0014
  - 0049
  - 0050
  - 0052
  - 0055
refines:
  - 0016
  - 0053
  - 0056
  - 0057
depends_on:
  - 0011
  - 0018
---

# Store one directional case-treatment relationship with two internal views

The pipeline records both how an earlier Case Proposition has been treated and
how a later judgment treats earlier propositions. It does this from one
authoritative directional relationship, not by storing the same legal fact
twice.

The complete relationship remains internal. Pinecone receives only ordinary
material Case Proposition records and the selected incoming treatment rendered
in `metadata.authority_note`. It does not receive separate relationship
records, citation-graph vectors, an outbound-treatment metadata field, or a
generated whole-case treatment list.

## One authoritative directional relationship

One resolved Later Treatment relationship records one treatment assertion from
the later treating decision to one exact earlier treated Case Proposition. One
later judgment may therefore create many relationships, including several that
share the same treating passages.

Every resolved relationship requires:

- one stable relationship ID;
- the treating Judicial Decision, Official Version, opinion, judges, and exact
  treating passages;
- zero or more treating Case Proposition IDs when those passages also support
  separately searchable propositions in the later judgment;
- one exact treated earlier Case Proposition ID;
- treatment class, expression mode, affected scope, materiality, court and
  jurisdiction authority, opinion status, finality, and applicable appellate-
  disposition facts;
- exact evidence, source and context fingerprints, cutoff, Source Rulebook,
  ordered Rule Trace, Legal Desk decision, and review state; and
- its accepted internal, authority-note, Quarantine, withholding, retirement,
  or reinstatement consequence.

The treating proposition link is optional. The relationship is supported by
the later decision, opinion, and passages, so a valid judgment that creates no
searchable proposition of its own may still treat or overrule an earlier
proposition. The pipeline never invents a later proposition merely to anchor a
treatment relationship.

When the earlier target cannot yet be resolved, the system preserves a
separate unresolved Treatment Lead with its exact evidence and bounded
candidate set where possible. It does not create a settled incoming
relationship or whole-case label until the target is resolved under the
Source Rulebook.

## Two derived internal views

The Management Register deterministically derives two projections from the
same relationship set at each frozen cutoff:

- the **Incoming Treatment View**, keyed by the treated earlier Case
  Proposition, answers which later judgments treated it and how; and
- the **Outgoing Treatment View**, keyed by the treating later judgment and,
  when available, its treating Case Proposition, answers which earlier
  propositions the judgment treated and how.

Both projections carry the same relationship ID and fingerprint. They are
indexes over one fact, not independent legal facts. A projection mismatch,
missing active relationship, extra relationship, duplicated edge, or different
status is a contract failure.

Unresolved Treatment Leads may appear in the outgoing investigative view and
in internal affected-impact accounting. They do not appear as settled incoming
treatment or LLM-facing authority support. A credibly adverse bounded lead may
still quarantine the smallest affected proposition set under the accepted
uncertainty rules.

## Immutable corrections and reverse impact

An accepted relationship is never overwritten. If corrected reasons,
withdrawal, reversal, or supersession changes its support or legal effect, the
pipeline reopens the treatment decision work and appends the new relationship,
decision, or supersession event required by the versioned contract. The former
relationship and evidence remain preserved.

The Outgoing Treatment View identifies every earlier proposition that may be
affected by the later judgment's change. The pipeline then recomputes each
affected proposition's Incoming Treatment View and current-authority result at
the new cutoff. Each affected relationship and proposition is accounted for
exactly once even when several paths discover it.

## Pinecone serving boundary

Serving is intentionally asymmetric:

- the earlier proposition's `metadata.authority_note` may contain selected
  material **incoming** treatment because that information qualifies how the
  downstream LLM may currently rely on the earlier proposition;
- a later judgment's `metadata.text` includes its source-supported treatment
  of earlier authority only when that reasoning forms part of a genuine,
  material, self-contained Case Proposition from the later judgment; and
- that later record's own `metadata.authority_note` describes subsequent
  treatment of the later proposition. It is not an outbound list of authorities
  that the later judgment discussed.

The pipeline does not add exhaustive outgoing citation or treatment lists to
`metadata.text`, does not copy them into `metadata.authority_note`, and does not
create a second whole-case overview vector. Bare citations and immaterial
treatment remain internal.

This preserves the standardized six-field serving envelope and avoids
duplicated vectors, retrieval crowding, unnecessary token use, and disagreement
between relationship copies. It also means Pinecone alone does not guarantee an
exhaustive citator-style answer such as “list every earlier proposition this
judgment treated.” A future exact citator feature must expose the internal graph
through a separately approved Query Contract and query path; it cannot be
inferred from semantic retrieval completeness.

## Required conformance additions

The initial Hong Kong treatment catalogue, later frozen by ADR 0059, adds
direct deterministic
coverage for:

- a resolved relationship whose treating decision, opinion, and passages are
  complete but whose treating proposition link is correctly absent;
- one accepted relationship producing exact incoming and outgoing projections
  without a duplicate relationship, Search Record, vector, or metadata field;
  and
- corrected or superseded treating evidence preserving the old relationship,
  appending the required successor or supersession facts, and using reverse
  impact to recompute every affected incoming result exactly once.

## Consequences and authorization

The Management Register needs one authoritative relationship store plus exact
incoming and outgoing projections. Legal Desk, impact-analysis, audit,
correction, reporting, and reprocessing tools may use both views. Corpus and
promotion code consumes only the accepted current consequence for affected
Search Records; it does not vectorize the graph.

This decision authorizes documentation only. It does not authorize
implementation, source access, model or embedding calls, release publication,
Pinecone mutation, promotion, deployment, or a change to Ask.Legal's query
path.
