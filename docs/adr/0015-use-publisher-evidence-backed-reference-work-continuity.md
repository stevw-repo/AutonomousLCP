---
status: accepted
date: 2026-08-11
amended_by:
  - 0017
  - 0050
depends_on:
  - 0011
  - 0013
refines:
  - 0011
---

# Use publisher-evidence-backed Principles continuity

For every jurisdiction's Principles, the tracked identity hierarchy is:

1. the publisher-maintained Principles Title is the **Legal Item**;
2. one publisher-authorized edition or complete rolling update state is an
   **Official Version** of that Legal Item;
3. one publisher paragraph or equivalent maintained unit is a **Legal
   Location**; and
4. one exact source-faithful `type: "principle"` serving payload is a **Search
   Record**.

Here, **Official Version** means the publisher-supported version of the
Principles Title. It does not mean that the material is primary law or a
government publication. A collection or platform containing several
independently maintained titles is a grouping boundary, not one Legal Item.

The pipeline preserves the publisher's paragraph. It does not silently rewrite
the paragraph into Ask.Legal's own legal rule. A long paragraph may be divided
into deterministic serving parts when the serving contract requires it, but
every part remains traceable to the same paragraph Legal Location and exact
source text.

## Continuity rules

| Publisher or source event | Identity result | Search and serving result |
|---|---|---|
| URL, host, platform, provider path, or mirror moves while the publisher artifact is proved unchanged | Keep the Legal Item, Official Version, and Legal Locations; record new aliases and snapshots | Reuse each exact six-field Search Record; a source move alone does not create replacement records |
| Publisher renames a continuing title | Keep the Legal Item when publisher evidence establishes continuity; update title aliases | Create a new Search Record only if a serving field changes; a traceability-only display change creates only a new Record Traceability Lookup revision |
| Publisher releases a new edition or a complete rolling update state | Keep the Legal Item and allocate a new Official Version | Reconcile the whole paragraph inventory; reuse only exact payloads with proved continuing support and create successor records for changed payloads |
| Publisher corrects a paragraph, note, citation, or other content | Keep the Legal Item and paragraph Legal Location when it remains the same maintained paragraph; allocate a new Official Version | Create a corrected Search Record when any serving field changes and preserve correction lineage |
| A paragraph is renumbered or moved within the same maintained title | Keep the Legal Location only when publisher mapping, stable publisher identity, or a reasoned Legal Desk decision under the source rulebook proves continuity; retain old and new locators as aliases | Reuse only an exact six-field payload; otherwise create a successor linked as moved or renumbered |
| A paragraph is moved to a different independently maintained title | Allocate a new Legal Location under the destination Legal Item and link it as transferred from the old location | Allocate new destination Search Records and preserve transfer lineage, even when the publisher text is unchanged |
| A publisher reuses an old paragraph number for a different subject | Allocate a new Legal Location; the visible number never transfers identity | Allocate new Search Records with no false continuity to the former topic |
| One paragraph is split into several maintained paragraphs | End the old location and allocate each successor location, linked as split from it | Allocate the required successor records and account for all predecessor content |
| Several paragraphs are merged into one maintained paragraph | End the old locations and allocate one new merged location linked to every predecessor | Allocate the merged record or deterministic serving parts and preserve many-to-one lineage |
| Authorities, notes, or currency information change | Keep the Legal Item and continuing paragraph location; allocate the applicable new Official Version | Create a new Search Record if any of the six serving fields changes, including `authority_note`; otherwise create only the required lookup revision |
| A cited case or item of legislation changes outside the Principles Title | Preserve the current identities and initiate review; the external change alone does not prove that the paragraph changed or is wrong | Continue, revise the authority note, withhold, or replace only under an evidence-backed Principles decision |
| Publisher withdraws or expressly supersedes a paragraph or title | Preserve all identities and record the publisher event | Retire the affected current records through the normal approved desired-state process unless the publisher supplies a supported replacement |
| The source is temporarily unavailable but no withdrawal is proved | Do not infer a publisher change | Apply the accepted unavailable-scope rules: explicit carry-forward, complete withholding, or no jurisdiction rebuild |
| A record is materially outdated and no supported publisher update is available | Preserve the entire source-faithful paragraph and its history | Withhold the complete affected record rather than rewriting part of the publisher's text; if it remains supportable with qualification, a controlled warning clause in `metadata.authority_note` may be used instead |
| Publisher versions, paragraph mapping, authenticity, or currency evidence conflicts | Make no new continuity assertion | Preserve the competing evidence and quarantine the event |

The exact six-field metadata payload is `text`, `country`, `jurisdiction`,
`type`, `source`, and `authority_note`; the serving envelope also carries the
top-level record ID. `authority_note` is always present and follows ADRs 0013
and 0050. An authority-note change
creates a new Search Record ID even when the source paragraph text is
unchanged.

## Licence-expiry freeze

Licence expiry is a technical freeze event for this design. It does not retire,
withhold, delete, or automatically change the authority note on the last approved records.

When a Principles source licence expires:

- the exact last approved Corpus Release remains eligible for selection;
- its Search Records remain in use and are copied into later replacement
  Pinecone Index Generations when that target is rebuilt;
- the same record IDs, six-field payloads, existing `authority_note` values, and exact
  cached embeddings are reused;
- the source scope is marked frozen in the Management Register;
- Watcher refresh, acquisition, corrections, new editions, new paragraphs,
  authority-note revisions, and every other content update for that source stop; and
- licence expiry alone creates no new Search Record, authority-note revision, lookup revision,
  withholding, or retirement.

If access is later renewed, the pipeline first captures and reconciles the
complete current publisher state against the frozen state. It then creates or
reuses identities under the ordinary continuity rules; it does not silently
assume that the missed interval contained no changes.

This technical design assumes the relevant use is legally compliant. The legal
team will decide source-specific rights, contractual controls, and compliance
requirements at a later stage. Those later decisions may amend this ADR through
a new explicit architecture decision; they are not inferred by the pipeline.

## Required evidence

Every Principles continuity decision records:

- publisher, collection, title, edition, release, and rolling-update identity;
- stable publisher paragraph identifiers and old and new visible locators;
- complete preserved before-and-after paragraph inventories and source text;
- publisher correction, replacement, renumbering, transfer, split, merge,
  supersession, withdrawal, and currency notices when applicable;
- exact source, serving-payload, lookup, and embedding fingerprints;
- cited-authority and currency evidence used for an authority-note or withholding
  decision;
- the responsible Legal Desk's rule and reasoned decision; and
- every created, reused, replaced, split, merged, transferred, authority-note-revised,
  withheld, retired, quarantined, frozen, or resumed identity.

Automated comparison may prove exact equality and propose mappings. It cannot
establish paragraph continuity merely from similar wording, the same visible
number, or nearby document position.

## Consequences

The Management Register needs Principles-title grouping, edition and rolling-
update evidence, paragraph inventories, alias history, typed Principles
lineage, and an explicit licence-expiry freeze state. Corpus construction must
support exact record and embedding reuse from a frozen release while blocking
all source-specific updates.

This decision settles the shared Principles identity and lifecycle model. ADR
0017 requires separate jurisdiction-qualified material families and rulebooks,
such as Australian Principles and Singapore Principles. Publisher-specific
source feeds, stable identifiers, update packaging, and currency evidence still
belong in each jurisdiction's Principles rulebook. The final Record
Traceability Lookup field encoding also remains open.
