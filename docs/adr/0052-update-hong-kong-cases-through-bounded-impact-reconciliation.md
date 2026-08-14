---
status: accepted
date: 2026-08-12
amended_by:
  - 0053
  - 0055
  - 0056
  - 0058
refines:
  - 0003
  - 0005
  - 0011
  - 0014
  - 0018
  - 0045
  - 0048
  - 0049
  - 0050
---

# Update Hong Kong Cases through bounded impact reconciliation

After the first accepted Hong Kong Cases current-authority baseline, every
ordinary update compares one new frozen cutoff with one exact accepted
predecessor. The pipeline processes the complete effect of genuine changes
without reprocessing every unchanged judgment or rebuilding every unchanged
court-year Release Scope.

## Ordered update path

1. Freeze the cutoff, predecessor Serving State and Corpus Releases, Source
   Rulebook, Release Scope registry, due source Observations, format contracts,
   and processing contracts.
2. Reconcile every required official inventory and time partition due at the
   cutoff with the accepted predecessor.
3. Deduplicate signals and acquire complete artifacts only for new, changed,
   missing, conflicting, or specifically reviewed judgments under ADR 0048.
4. Reconcile affected listings, Judicial Decisions, Official Versions,
   opinions, passages, translations, identities, and source facts.
5. Build a transitive affected-impact graph from each affected decision to its
   own propositions, every treatment relationship it may add, change, or
   remove, and every earlier proposition and court-year scope whose current
   serving result may change.
6. Expand and resolve that graph until no unresolved dependency can change
   another serving result.
7. Reuse exact unaffected Search Records and Corpus Releases. Create immutable
   successor records and releases only where evidence, accounting,
   propositions, treatment, `authority_note`, or selection changed.
8. Compose the changed and reused scopes into one complete candidate
   Desired-State Inventory. Preserve post-cutoff events for the next update.

A source signal is not a legal conclusion. A listing, changed hash,
disappearance, corrected label, or discovery-source difference opens bounded
work; it does not itself create, change, warn, support, retire, or reinstate a
Search Record.

## Supported no change

`SUPPORTED_NO_CHANGE` is valid only when every required official check due at
the cutoff completed within its freshness rule, all inventories and artifact
fingerprints reconcile with the predecessor, every relevant signal is
resolved, every due treatment-coverage check is complete, and no required
correction, withdrawal, source-contract change, or conflict remains open.

When those conditions pass, the pipeline preserves the comparison proof,
reuses all existing Corpus Releases and Search Records, and performs no
acquisition, proposition, treatment, embedding, or Pinecone work. It does not
create an empty release merely to record silence.

## Exact HKLII role

HKLII remains Registered Source `HK-CASE-HKLII-DISCOVERY`. In an ordinary
update it can do five useful things:

1. **candidate discovery** — identify a judgment or older publication that may
   have been missed or published through an unexpected route;
2. **inventory cross-checking** — expose a difference between its index and the
   accepted official Judiciary inventory;
3. **alias reconciliation** — suggest another case name, citation, proceeding
   number, locator, or duplicate relationship;
4. **citation leads** — identify a later judgment that may cite an earlier
   case; and
5. **treatment leads** — suggest that a later judgment may have applied,
   followed, distinguished, doubted, criticised, disapproved, or overruled an
   earlier proposition.

Each result creates at most a discovery or reconciliation work item. Before it
can affect the legal database, the pipeline must obtain the matching accepted
originating judgment and verify the exact decision, opinion, passages, court
relationship, affected proposition, and material legal effect. The resulting
decision relies on that originating evidence and the Hong Kong Cases rulebook,
not on HKLII.

HKLII therefore cannot by itself:

- prove that official-source coverage is complete or that nothing changed;
- establish authentic judgment wording or an Official Version;
- create a Case Proposition or decide later treatment;
- add a support or warning clause to `metadata.authority_note`;
- retire, withhold, or reinstate a proposition; or
- require a Pinecone or Release Scope change.

An HKLII outage, empty result, delay, or connector failure is nonblocking when
all required originating-source checks pass. Conversely, an affirmative
in-scope HKLII difference is not silently ignored. It is resolved against the
originating sources, closed as stale, duplicate, false, or out of scope with
evidence, or remains an explicit affected investigation. Complete official
enumeration can disprove the lead. HKLII never cures an official enumeration
gap.

## Identity, treatment, and impact behavior

A new decision belongs to its issuing-court-family and original-decision-year
scope. A later publication, correction, or treatment event does not move the
earlier decision. Express corrected or revised reasons create a new Official
Version of the same Judicial Decision; supplementary, costs, remedy, and other
separately delivered decisions normally receive separate Legal Items linked by
the Case Dossier.

One new judgment always affects its own scope accounting even if it creates no
Case Proposition. It may also affect older scopes through treatment. For
example, one 2026 Court of Appeal judgment may create new 2026 propositions,
materially follow a 2019 proposition, criticise a 2008 proposition, and
conclusively overrule a 1997 proposition. Only those affected court-year
releases change; unrelated releases are reused.

An exact unchanged six-field Search Record is reused only with proved
continuing judgment and current-authority support. Changed proposition text or
`authority_note` selects a different exact Search Record. A previously unseen
payload receives a new ID; a preserved exact payload may be reselected under
ADR 0055 without backward lineage. An authority-note-only change may reuse the
exact cached embedding because the embedding input remains `metadata.text`. A
citation, alias, grouping, or evidence-reference correction that changes no
serving field creates only the necessary Management Register or Record
Traceability Lookup revision.

## Update outcomes

Each update keeps these results distinct:

- `SUPPORTED_NO_CHANGE` — every required check supports exact reuse;
- `ACCOUNTING_ONLY_CHANGE` — evidence, translation, zero-record, alias, or
  traceability accounting changed while the exact serving-record set did not;
- `SERVING_CHANGE` — at least one proposition was added, replaced,
  authority-note-revised, withheld, retired, split, merged, or reinstated;
- `BLOCKED` — required evidence or a required Observation is unavailable; and
- `QUARANTINED` — available evidence conflicts or cannot support a safe result.

A missing in-scope judgment may create both an acquisition gap and an unknown
treatment gap. A generic authority note cannot cure unreadable text. After
bounded retries, ADR 0005 controls explicit carry-forward, complete
withholding, or no new Hong Kong Cases target. No gap is hidden as no change,
zero records, retirement, or a proved-empty scope.

## Contract changes and concurrency

A parser, proposition, treatment, authority-note renderer, or Source Rulebook
change is not a source-law event. Its immutable replacement declares the exact
decisions, treatments, scopes, and records requiring re-evaluation. Changed
results use processing-correction lineage rather than pretending that a court
changed the law.

Every update has one predecessor and one cutoff. Overlapping work is
deduplicated or serialized against that predecessor. If the accepted base
changes before approval or execution, the candidate is rebuilt rather than
silently rebased.

Watcher checks, differences, acquisition admission, hashes, deterministic
parsing, identity, impact-graph traversal, exact payload comparison, scope
accounting, and release arithmetic use no generative LLM. Proposition
extraction remains allocation-deferred under ADR 0043. Hong Kong later-
treatment work uses ADR 0053's staged hybrid proposal flow. No proposal may
decide legal effect, authority notes, retirement, Quarantine, release
eligibility, Approval, or production action.

## Consequences and authorization

The Hong Kong Cases Source Rulebook needs stable ordinary-update rules,
affected-impact relationships, result codes, HKLII-lead outcomes, and complete
conformance examples for no change, serving changes, accounting-only changes,
corrections, disappearances, outages, uncertainty, and post-cutoff events.
ADR 0056 requires direct deterministic fixture coverage of each applicable
outcome and its near-miss boundary, separate from semantic model evaluation.

This decision authorizes documentation only. It does not authorize connector
implementation, source access, model or embedding calls, release publication,
Pinecone mutation, promotion, or deployment.
