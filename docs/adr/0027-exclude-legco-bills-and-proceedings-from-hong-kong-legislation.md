---
status: accepted
date: 2026-08-11
amended_by:
  - 0029
  - "0080"
  - "0081"
amends:
  - 0019
refines:
  - 0025
depends_on:
  - 0018
  - 0022
---

# Exclude LegCo Bills and proceedings from Hong Kong legislation

The Hong Kong Legislation pipeline does not register, ingest, or continuously
watch the Legislative Council Bills Database, Bills, or LegCo proceedings.
These materials may help legislative-history or future-law research, but they
do not produce or validate the supported current-law records that this pipeline
serves.

Relevant official references checked are the [LegCo Bills Database](https://www.legco.gov.hk/en/open-legco/open-data/bills-database.html),
its [published data specification](https://www.legco.gov.hk/datagovhk/data-dictionary-bills-db-en.pdf),
and the [LegCo website disclaimer](https://www.legco.gov.hk/en/general/disclaimer.html).

The accepted current-law chain is already complete without LegCo material:

- the Gazette proves the enacted instrument and the legal events assigned to
  exact Gazette evidence under ADR 0025;
- other accepted event sources prove only their assigned facts;
- HKeL current XML and the applicable matching verified or assisted official
  HKeL copy evidence prove the current searchable consolidated wording under
  ADR 0081; and
- HKeL past data preserves historical-version evidence under ADR 0026.

A proposed Bill, reading, debate, vote, explanatory memorandum, or committee
report cannot replace any part of that chain. ADR 0080 reconstruction relies
on proved official amendment and commencement evidence, not proposed Bill
wording. LegCo material therefore remains unnecessary to producing the
supported consolidation.

## Excluded operational capabilities

The Hong Kong Legislation pipeline creates no:

- `HK-LEG-LEGCO-BILLS` Registered Source;
- Bills Database, Bill, or LegCo-proceedings Watcher or connector;
- complete Bills Database inventory or reconciliation obligation;
- routine Bill, explanatory memorandum, debate, vote, committee-paper, or
  proceedings Source Snapshot;
- Bill workflow, Bill dossier, Bill identity, or Bill-to-Ordinance mapping
  requirement;
- Coverage Gap, Quarantine, release failure, or no-change failure caused by
  LegCo unavailability or change; or
- current-law Search Record, `metadata.text`, `metadata.authority_note`, embedding, or
  Pinecone entry derived from LegCo material.

A Bill's introduction, readings, passage, amendment, withdrawal, lapse, or
disappearance has no direct Hong Kong Legislation pipeline outcome. It cannot
create, change, warn, withhold, retire, or reinstate a current-law record.

## Gazette Legal Supplement No. 3 boundary

ADR 0025 requires complete Gazette issue-and-notice reconciliation. A Gazette
Watcher may therefore observe that a Legal Supplement No. 3 issue or Bill
entry exists while accounting for the Gazette inventory. That observation is
an excluded classification, not Bill processing.

The Watcher may preserve the minimum issue identity and classification needed
to prove complete Gazette reconciliation. It does not need to acquire or parse
the Bill text, create a Bill workflow, follow its LegCo progress, or treat the
Bill as legal-event evidence. Legal Supplement No. 3 cannot establish
enactment, commencement, current law, or searchable wording.

## Optional human research

A human reviewer may manually consult a Bill or LegCo proceeding when unusual
historical context is helpful. This is unregistered, optional, non-controlling
research. The material cannot satisfy a required rulebook input or decide a
pipeline outcome. The accepted Gazette, HKeL, or other assigned source evidence
must still prove every relied-on fact.

No automated process depends on this optional research. Its absence never
blocks a release, and a reviewer is not required to record a complete LegCo
research trail unless a later separate policy expressly requires one.

## Future reconsideration

If Ask.Legal later offers legislative-history search, proposed-law monitoring,
or future-law alerts, Bills and proceedings require a separate product and
material-scope decision. That decision must define coverage, source roles,
serving labels, downstream interpretation, authority notes, freshness, revisions,
withdrawal and lapse behavior, and isolation from current law. This ADR does
not authorize that future capability.

## Consequences

The current-law pipeline stays focused on evidence that can change or validate
current searchable law. It avoids a large procedural-history ingestion and
reconciliation subsystem with no current serving outcome. This decision does
not authorize source acquisition, implementation, publication, Pinecone
mutation, or deployment.
