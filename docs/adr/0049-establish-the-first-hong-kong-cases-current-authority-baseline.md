---
status: accepted
date: 2026-08-12
amended_by:
  - 0053
  - 0056
  - 0058
  - "0065"
refines:
  - 0003
  - 0005
  - 0011
  - 0014
  - 0018
  - 0046
  - 0048
depends_on:
  - 0013
  - 0043
  - 0047
---

# Establish the first Hong Kong Cases current-authority baseline

The first Hong Kong Cases baseline answers one question at one fixed cutoff:

> What complete set of Case Propositions from every required Hong Kong
> binding-case scope is supported for ordinary current-law search after all
> in-scope later judgments through the cutoff have been screened for material
> treatment?

The baseline is not a dump of judgment files and is not an import of the
existing Pinecone corpus. It establishes the first greenfield judgment,
proposition, treatment, authority-note, non-searchable, Quarantine, and completeness
state against which ordinary updates can later be compared.

## Transfer from the legislation baseline

The case baseline reuses the safe structural rules of the Hong Kong
Legislation baseline:

- freeze one observation cutoff and one complete versioned decision package;
- account for every required source object;
- issue new register-owned identities instead of importing legacy identity;
- preserve missing and conflicting evidence as explicit gaps or Quarantine;
- create immutable first Corpus Releases with no accepted predecessor; and
- keep post-cutoff changes outside the frozen baseline.

It cannot reuse legislation's present-consolidation shortcut. No official
publisher supplies a consolidated “currently good law” judgment. Every later
in-scope decision through the cutoff must therefore be screened for treatment
that can change the current use of an earlier Case Proposition.

## Court-family-and-year Release Scopes

Hong Kong Cases use one Release Scope per issuing-court family and original
decision calendar year. The semantic pattern is
`HK-CASE-{COURT_FAMILY}-{DECISION_YEAR}`. It covers the Court of Final Appeal,
Court of Appeal, Court of First Instance, Competition Tribunal, corresponding
historical superior-court families, and Hong Kong Privy Council appeals within
ADR 0046.

The actual issuing-court identity and original decision date assign ownership.
A later publication, translation, correction, treatment event, or processing
date does not move the decision. An official correction supported as a new
Official Version updates the release for the decision's existing scope. A
later judgment that changes an older proposition may require a replacement
release for the older proposition's court-year scope.

These scopes are ownership, failure-isolation, and rebuild boundaries. They do
not mean legal authority or treatment is limited to one court or year. Every
required scope still composes into one complete Hong Kong Cases serving target,
and treatment reconciliation remains corpus-wide at one cutoff.

Exact court-family codes and the first and last year represented by each
historical family belong in the versioned Release Scope registry. They cannot
be inferred from filenames, current court names, or convenient download
availability.

## Ordered baseline path

The baseline runs in this order:

1. freeze the observation cutoff, Source Rulebook, Release Scope registry,
   Registered Source set, inventory captures, format profiles, and processing
   contracts;
2. prove that the accepted official inventory path enumerates every required
   court-year scope, or record the affected scope as not ready;
3. apply ADR 0048 to every official listing entry and preserve every acquired
   original, optional translation, exclusion, unavailable item, and conflict;
4. allocate new register-owned Legal Item, Official Version, opinion, passage,
   and other required identities from accepted evidence;
5. parse every acquired decision and account for every opinion and passage;
6. create supported candidate Case Propositions or a reviewed valid
   no-material-proposition outcome;
7. screen all acquired in-scope judgments through the cutoff for citations and
   material treatment of earlier propositions, resolve that treatment under
   ADR 0014, and perform corpus-wide dangling-citation and treatment-
   completeness checks;
8. assign every proposition its supported current result;
9. prove complete acquisition, processing, treatment, authority-note, non-searchable,
   Quarantine, gap, and zero-record accounting for every required scope; and
10. seal one initial Corpus Release per complete scope and compose all required
    scopes into one candidate Desired-State Inventory.

A later step cannot cure an earlier evidence failure. Correct proposition text
does not cure missing judgment acquisition or incomplete later-treatment
coverage.

## Proposition results

Every supported proposition has exactly one current result at the cutoff:

- searchable with `metadata.authority_note: "None"` when no approved note applies;
- searchable with one controlled authority note under ADRs 0013, 0014, and 0050;
- non-searchable because conclusive overruling or another accepted current-
  authority rule removes it from ordinary serving; or
- Quarantine because identity, attribution, support, hierarchy, treatment, or
  scope remains materially unresolved.

An old judgment is not automatically historical or non-searchable. Age and
acquisition route do not decide current authority. A supported old proposition
remains eligible until accepted evidence establishes an authority-note change,
retirement, or
another limitation. An arbitrary rolling age cutoff would create a recent-case
product rather than the accepted current-law coverage.

The baseline need not reproduce a narrative of every citation ever made. It
must still screen the complete accepted later-judgment universe through the
cutoff and resolve every material treatment that can change current serving.
It also checks later reversal, withdrawal, or supersession of earlier adverse
treatment rather than stopping at the first negative label.

## Zero-record decisions remain material to completeness

A valid decision may contain no material proposition of its own. It still
passes citation and later-treatment screening because it may follow,
criticise, disapprove, reverse, or overrule an earlier proposition.

The baseline distinguishes:

- a valid decision with no material proposition;
- propositions searchable without an authority note;
- propositions searchable only with an authority-note warning clause;
- supported propositions non-searchable under current-authority rules;
- an unavailable or unreadable decision; and
- a decision or proposition in Quarantine.

Zero Search Records is a valid decision outcome only after acquisition,
parsing, proposition review, and treatment relevance are accounted for. It can
never stand for a missing file, skipped work, processing failure, or
uncertainty.

## Initial historical boundary and controlled growth

The baseline has no arbitrary age cutoff. Its initial historical boundary is
the earliest court-and-period boundary for which accepted official-source
evidence can support the exact coverage promise. A verified source boundary is
an evidence fact, not a claim that older law is irrelevant.

If some periods can be completely enumerated and others cannot, the Release
Scope registry records those ready and not-ready periods. The accepted coverage
promise is not silently narrowed to whichever artifacts are easy to download.
All required scopes must be accounted for before the complete Hong Kong Cases
target can claim the accepted coverage.

The absence of an age cutoff does not place every judgment page in Pinecone.
Growth is controlled because:

- only material current Case Propositions create vectors;
- a valid no-proposition decision creates no vector;
- full judgments and processing evidence remain outside Pinecone;
- there is no duplicate whole-case vector or translation-language duplicate;
- several proceeding numbers and duplicate formats do not duplicate authority;
- conclusively overruled propositions leave ordinary current serving; and
- exact unchanged records and embeddings may be reused in later replacement
  targets.

Pinecone therefore grows by net supported material propositions rather than by
every page of every judgment. Court-year scopes keep later rebuilds bounded
even though the complete serving target composes all current scopes.

## Missing evidence and treatment gaps

The first baseline has no previous greenfield release, so carry-forward is not
available. A known missing in-scope judgment creates an acquisition gap and a
possible treatment gap because its text may affect earlier propositions.

The Legal Desk may narrow the impact only with accepted evidence and a written
rule. If the affected proposition universe cannot be bounded, the pipeline
cannot claim treatment completeness or assign `authority_note: "None"` across that
uncertain universe. A generic authority note does not cure unknown source text.

The affected scope may use a complete evidence-backed withholding result only
when every affected item and consequence can be accounted for under ADR 0005.
Otherwise it remains not ready or prevents a complete Hong Kong Cases candidate
target. Independent clear scopes may continue as candidate work, but an
unresolved required scope cannot be hidden.

An identity, opinion, support, treatment, or hierarchy uncertainty quarantines
the smallest safely separable proposition, decision, or scope. It broadens only
when the dependency cannot be bounded.

## Greenfield identity and legacy material

The Management Register allocates all new identities from accepted evidence.
Legacy Distillation paths, record IDs, Pinecone IDs, citations, URLs, and
filenames may support comparison, gap discovery, or traceability but cannot
define identity, current authority, completeness, or serving selection.

An apparently identical legacy record receives a new greenfield Search Record
ID. The baseline does not invent predecessor lineage merely to connect it to a
legacy vector.

## Frozen cutoff and later changes

An item first observed after the cutoff belongs to the ordinary update path.
If a new judgment, correction, or other material source change appears while
baseline work remains open, the pipeline either:

- abandons and re-freezes the affected baseline at a later cutoff; or
- completes the internally consistent original baseline and processes the new
  signal through ordinary update rules before any state claiming later
  currency can be promoted.

The baseline never mixes post-cutoff judgments into only convenient scopes.

## LLM and authority boundary

Cutoff control, inventory reconciliation, acquisition outcomes, hashes,
identity allocation, scope accounting, authority-note validation, and release
arithmetic use no generative LLM.

ADR 0065 accepts staged hybrid Hong Kong Case Proposition extraction with
separate proposition-analysis and proposition-challenge LLM passes inside
deterministic admission, validation, reconciliation, and finalization. ADR 0053
accepts staged hybrid Hong Kong later-treatment screening: whole-judgment and
candidate-level LLM passes produce proposals for deterministic validation and
Legal Desk decision. No proposal can decide authority, authority notes,
retirement, Quarantine, release eligibility, Approval, or production action.
The baseline is not decision-ready until both exact task families pass their
required conformance, evaluation, and runtime admission gates.

## Required conformance boundaries

ADR 0056 separates semantic model evaluations from byte-exact deterministic
contract fixtures. The following boundaries must appear in its frozen coverage
matrix rather than being treated as one undifferentiated end-to-end score.

Future fixtures must at least prove that:

- a clear proposition becomes searchable with `authority_note: "None"` only after
  complete treatment screening;
- an old superior-court proposition is not excluded merely because of age;
- a no-proposition judgment can still overrule an older proposition;
- partial overruling removes only the exact affected proposition;
- a known unavailable judgment remains a source and treatment gap rather than
  a valid zero-record decision;
- a later official correction remains in the original decision's court-year
  scope as a new Official Version;
- a matching legacy record does not supply greenfield identity; and
- a post-cutoff judgment enters the ordinary update path rather than mutating
  the frozen baseline.

## Consequences

The Hong Kong Cases Source Rulebook must define the exact baseline rules,
court-family codes, historical inventory boundaries, current-authority and
treatment evidence, zero-record decision contract, gap propagation, and
conformance catalogue. The first complete candidate target cannot exist until
all required court-year scopes and the corpus-wide treatment graph reconcile at
one cutoff.

This decision authorizes documentation only. It does not authorize source
access, implementation, AI or embedding calls, release publication, Pinecone
mutation, promotion, or deployment.
