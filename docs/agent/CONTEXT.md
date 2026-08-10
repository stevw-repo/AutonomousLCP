# AskLegal Legal Database Pipeline — Domain Context

This glossary defines the stable language of the autonomous legal-database
pipeline. Architecture and policy decisions belong in `DECISIONS.md` and
`docs/adr/`; current work belongs in `WORKING_STATE.md`.

## Source and evidence

**Registered Source**: An approved official location whose intended coverage,
checking rules, and responsible legal desk are recorded.
_Avoid_: Website, data source

**Watcher**: A source-specific monitor that detects a possible addition,
change, disappearance, or legal-status event.
_Avoid_: Scraper, legal checker

**Scraper**: A source-specific retriever that captures the complete changed
content, required attachments, and source metadata.
_Avoid_: Watcher, desk

**Observation**: One recorded result of checking a Registered Source at a
specific time.
_Avoid_: Run, snapshot

**Source Snapshot**: An immutable preserved capture of the source evidence used
for a decision.
_Avoid_: Current page, working copy

**Evidence Vault**: The durable store of Source Snapshots, official-status
evidence, releases, approvals, reports, and recovery material.
_Avoid_: Pinecone, management register

## Legal material

**Legal Desk**: The jurisdiction-and-material authority that applies written
source rules to preserved evidence.
_Avoid_: Watcher, scraper, AI worker

**Legal Item**: A uniquely tracked legal authority such as an Act, judgment, or
reference-work paragraph.
_Avoid_: Search record, source file

**Official Version**: A source-supported version or status event belonging to a
Legal Item.
_Avoid_: Latest file, current record

**Provision**: A stable legal location within legislation from which one or
more search records may be derived.
_Avoid_: Chunk

**Case Proposition**: One material legal proposition derived from a judgment
and supported by exact passages and necessary context.
_Avoid_: Halsbury principle, sentence

**Reference Principle**: One source-faithful paragraph from Halsbury or another
approved secondary reference work.
_Avoid_: Case proposition

**Search Record**: One validated, independently searchable representation of
legal material.
_Avoid_: Vector, source snapshot

## Corpus and promotion

**Management Register**: The durable ledger of sources, observations, legal
items, states, decisions, work, approvals, and serving history.
_Avoid_: Evidence vault, report

**Corpus Release**: A sealed immutable set of validated Search Records and its
integrity evidence.
_Avoid_: Distillation output, latest dataset

**Desired-State Inventory**: The exact complete set of Search Records that
should exist in a particular serving target after promotion.
_Avoid_: One profile release, deletion list

**Promotion Manifest**: The frozen plan joining evidence, releases, desired
states, targets, recovery evidence, settings, additions, replacements, and
retirements under one approval.
_Avoid_: Report, deployment command

**Approval**: An authenticated human decision bound to one exact Promotion
Manifest and its fingerprints.
_Avoid_: Permission to improvise, general consent

**Serving State**: A completely verified search corpus and routing
configuration eligible to serve Ask.Legal.
_Avoid_: Partially updated index, latest index

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

**Waiting Room**: Preserved enacted or assented legislation that has not met
the commencement and official-consolidation requirements for search.
_Avoid_: Searchable prospective law

## Relationships

- A **Registered Source** produces many **Observations**.
- An **Observation** may trigger one **Scraper** capture and one or more
  **Source Snapshots**.
- A **Legal Desk** interprets **Source Snapshots** into supported
  **Official Versions**, **Quarantines**, or **Coverage Gaps**.
- A **Legal Item** has one or more **Official Versions**.
- An **Official Version** may produce zero or more **Search Records**.
- A **Corpus Release** contains one or more **Search Records**.
- A **Desired-State Inventory** composes all approved releases contributing to
  one serving target.
- A **Promotion Manifest** contains one or more Desired-State Inventories and
  receives at most one current **Approval**.
- A successful **Cutover** makes one verified **Serving State** active.
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
  cases; and the latest maintainable source-faithful paragraph for a reference
  work.
- **Principle** previously referred to both case-derived propositions and
  Halsbury paragraphs. The canonical terms are **Case Proposition** and
  **Reference Principle**.
- **Stage** previously implied a separate repository. In the greenfield system,
  acquisition, legal processing, release construction, approval, and promotion
  are capability boundaries inside one modular monorepo.
- **Release** does not mean authorization. A **Corpus Release** is an immutable
  artifact; production still requires a valid **Approval** for a complete
  **Promotion Manifest**.
