---
status: accepted
date: 2026-08-11
amended_by:
  - 0029
  - 0031
  - 0032
  - "0079"
  - "0080"
  - "0081"
amends:
  - 0019
refines:
  - 0012
  - 0022
  - 0023
  - 0025
depends_on:
  - 0018
---

# Use HKeL past data for history and Editorial Records for official editorial events

HKeL past data and HKeL Editorial Records have separate source roles. Past data
supplies historical inventory and reconciliation evidence. An Editorial Record
proves the official editorial amendments it states and their effective dates.
Neither source by itself supplies current searchable consolidated text.

The Department of Justice publishes weekly past-version data dating back to 30
June 1997. It also states that electronic editorial amendments are made under
section 12 of the Legislation Publication Ordinance (Cap. 614) and Editorial
Records are published with legal status under section 15. The first electronic
Editorial Record with legal status was published on 10 April 2019.

Relevant official references are the [Department of Justice verification
completion paper](https://www.doj.gov.hk/en/legco/pdf/ajls20250331e3.pdf),
[HKeL important notices](https://www.elegislation.gov.hk/importantnotices),
[HKeL past-version data](https://data.gov.hk/en-data/dataset/hk-doj-hkel-legislation-past),
and the [HKeL past-version inventory](https://data.gov.hk/en-data/dataset/hk-doj-hkel-list-of-legislation-past).

## HKeL past-data role

The `HK-LEG-HKEL-PAST-DATA` semantic role is a historical inventory and
reconciliation source. It may:

- inventory earlier HKeL versions, version dates, status labels, locations,
  language resources, source URLs, and hashes;
- compare two specifically requested and verified historical versions;
- expose questions about Legal Item or Legal Location continuity, renumbering,
  split, merge, disappearance, or correction for investigation, without proving
  the answer by textual similarity;
- show that a previously captured version remains reproducibly available;
- support audit, recovery, regression fixtures, and ADR 0080 reconstruction
  back-testing; and
- preserve earlier versions outside current-law Pinecone.

Past XML is structured historical evidence, not verified legal-text proof by
itself. When the pipeline must rely on a past version's exact wording, it
reconciles the English and Traditional Chinese XML with corresponding past
verified PDFs using the deterministic legal-content boundary in ADR 0022.
Simplified Chinese remains informational.

A past-data status label, movement from a current package to a past package, or
disappearance cannot by itself prove commencement, repeal, expiry, or another
legal event. The exact Gazette, Editorial Record, or other accepted event source
must prove the cause.

Past-data failure does not automatically block an otherwise completely
supported current record. It creates a visible historical-coverage problem and
blocks only identity, lineage, audit, or other decisions that require the
missing evidence. It cannot support a silent no-change conclusion.

## HKeL Editorial-Record role

The `HK-LEG-HKEL-EDITORIAL-RECORDS` semantic role is official editorial-
amendment evidence. For each Editorial Record, the Evidence Vault preserves:

- year, number, every Part, and every effective date;
- complete English and Traditional Chinese authentic-language text;
- each affected Legal Item and exact Legal Location;
- the stated editorial operation and any explicit mapping;
- source metadata, publication evidence, and fingerprints; and
- its links to before-and-after HKeL versions.

The exact Editorial Record proves the editorial amendments it states and when
they took effect. It is not itself the resulting consolidated Official Version.
Normally the pipeline waits for matching current English and Traditional
Chinese HKeL XML and the applicable verified or assisted official HKeL copy
evidence, then proves that the resulting HKeL text reflects the Editorial
Record. ADR 0080 separately permits an Editorial Record to participate in a
reconstructed consolidation only through its complete evidence, operation,
bilingual, and reproducibility gates.

An editorial amendment may be limited in legal effect and still change wording,
punctuation, headings, numbering, structure, or another serving field. A change
to either authentic language changes the bilingual `metadata.text` and creates
a new Search Record ID. If a new verified Official Version leaves all six
serving fields exactly identical, the prior Search Record may be reused only
with proved continuing legal support. The new Official Version and Editorial
Record lineage are preserved either way.

## Priority and failures

Source priority is fact-specific:

- a Gazette or another accepted operative instrument proves its enacted or
  status event;
- an Editorial Record proves its official editorial amendment;
- past data supplies version history; and
- matching current XML and the applicable verified or assisted official HKeL
  copy evidence prove the searchable resulting text.

The failure rules are:

1. If an Editorial Record is published but matching updated applicable HKeL
   text evidence is unavailable, record the editorial event and affected
   locations, do not patch old text, and expose a Coverage Gap. Under ADR 0079,
   create a warned analytical record for each affected location for which valid
   latest applicable official HKeL text is held; otherwise create no record.
2. If current HKeL text changes but no accepted Gazette event, Editorial Record,
   or other approved cause explains it, preserve the before-and-after evidence
   and quarantine the change.
3. If past XML disagrees with its matching past verified PDF, the XML cannot
   establish exact wording. Quarantine the historical reconciliation without
   silently altering the current record.
4. If an Editorial Record and the resulting verified text appear inconsistent,
   preserve both, make no inferred repair, and quarantine the affected change.

## Acquisition and reconciliation — amended by ADR 0032

ADR 0032 separates `HK-LEG-HKEL-PAST-INVENTORY` from
`HK-LEG-HKEL-PAST-DATA` and makes both on-demand investigation and recovery
sources. Neither is checked in the ordinary weekly pipeline, neither has a
routine release freshness gate, and neither can block an otherwise fully
supported current-law release.

When a specific investigation, missing-baseline recovery, audit, or evaluation
task requests past evidence, the acquisition must capture and completely
reconcile the required inventory and package fingerprints rather than select a
convenient file. Missing or conflicting evidence blocks only that task or its
dependent identity or lineage decision.

The ordinary comparison uses the pipeline's preserved previous accepted
current bundle against the newly acquired current bundle, plus the accepted
event evidence explaining the change. Historical similarity or disappearance
may raise a continuity question but cannot prove renumbering, repeal,
commencement, or identity. Only accepted official mapping or other evidence
permitted by the rulebook may resolve that question; otherwise it is
quarantined.

`HK-LEG-HKEL-EDITORIAL-RECORDS` remains a weekly supporting source because a
new Editorial Record may directly explain a current-text change. Its Watcher
reconciles the complete numbered inventory, including every Part and effective
date. Revisions and later captures are preserved append-only.

## Consequences

Past data remains available for bounded history, recovery, audit, and
evaluation tasks without becoming a routine current-law dependency. Editorial
Records may support reconstruction only through ADR 0080, not as an informal
back door. The ordinary current HKeL XML-and-PDF rules remain unchanged, and
this decision does not authorize acquisition, implementation, publication,
Pinecone mutation, or deployment.
