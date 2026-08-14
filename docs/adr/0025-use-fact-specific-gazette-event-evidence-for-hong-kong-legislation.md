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
  - 0005
  - 0012
  - 0022
  - 0023
depends_on:
  - 0018
---

# Use fact-specific Gazette event evidence for Hong Kong legislation

The Hong Kong Legislation Source Rulebook uses Gazette evidence to prove
specific legal events, not the resulting consolidated text. In simple terms:
the Gazette may prove **what happened and when**; matching HKeL XML and the
applicable verified or assisted official HKeL copy evidence support **the
current merged wording** that may become searchable.

Publication is not automatically commencement, and a status event is not an
Official Version. The pipeline records publication and effective dates
separately and maps partial events to exact Legal Locations. ADR 0080 permits
those facts to support a reconstructed consolidation only when every separate
reconstruction proof and deterministic-operation gate passes.

Relevant official references include the [HKSAR Gazette important
notices](https://egazette.gld.gov.hk/en/important-notices), the [Department of
Justice Gazette back-capture statement](https://www.doj.gov.hk/en/community_engagement/press/20220318_pr1.html),
and the [Legislative Council companion on commencement](https://www.legco.gov.hk/general/english/procedur/companion/chapter_11/chapter_11.html).

## Gazette source roles

The rulebook distinguishes three roles rather than treating every Gazette copy
as interchangeable:

1. **GLD e-Gazette artifact role** — the exact issued PDF or notice artifact is
   primary event evidence for available modern ordinary and Gazette
   Extraordinary issues. An HTML search result is only a locator.
2. **Printed Gazette or Government Records Service role** — historical or
   escalation evidence when an issue predates the online GLD collection, the
   online artifact is missing or ambiguous, or sources conflict.
3. **HKeL Gazette back-capture role** — discovery, source-note linking, and
   candidate-event identification only until the required Gazette evidence is
   obtained.

ADR 0032 assigns the stable IDs `HK-LEG-GLD-EGAZETTE`,
`HK-LEG-OFFICIAL-GAZETTE-ARCHIVE`, and
`HK-LEG-HKEL-GAZETTE-BACKCAPTURE`. Endpoint configuration, validity dates, and
retention settings remain concrete registry and implementation work.

## Gazette classifications

| Gazette material | Fact it may establish | What it cannot establish by itself |
|---|---|---|
| Legal Supplement No. 1 | Publication and as-enacted wording of an Ordinance; a commencement clause contained in that Ordinance | That every provision is operative, or that HKeL has published the current consolidation |
| Legal Supplement No. 2 | Publication of subsidiary legislation, commencement notices, revocation instruments, and other exact legal notices | The current consolidated wording of the principal legislation |
| Legal Supplement No. 3 | Minimum issue identity and excluded classification when needed for complete Gazette reconciliation | Bill processing, enactment, commencement, current law, or searchable wording |
| Main Gazette statutory notice | The exact event expressly given legal effect by its enabling provision | A general status change merely because a notice mentions an instrument |
| Gazette Extraordinary | The same fact as its applicable notice or supplement class | Automatic priority over another source controlling a different legal fact |
| Special or other supplement | Discovery unless an item-specific rule and enabling authority assign a legal role | Automatic inclusion in the current-law corpus |

Extraordinary publication changes when an artifact appears, not what that
artifact is legally capable of proving.

## Event rules

1. **Publication or enactment** — preserve the complete instrument, issue and
   supplement identity, notice or Ordinance number, publication date,
   authentic-language material, source metadata, and hash. Publication does
   not by itself make every provision searchable.
2. **Default commencement** — apply the accepted written Hong Kong default-
   commencement rule only when the exact instrument contains no different
   commencement provision.
3. **Fixed commencement** — when the instrument names a date, preserve that
   clause as event evidence. The affected material remains in the Waiting Room
   until the date arrives and matching current applicable HKeL text evidence is
   available.
4. **Appointed commencement** — require the exact commencement notice,
   ordinarily published as subsidiary legislation in Legal Supplement No. 2.
   A non-controlling research lead may locate it but cannot replace it.
5. **Partial commencement** — apply the event only to the exact sections,
   Schedules, or other Legal Locations named. Unnamed locations remain in
   their previous state.
6. **Amendment** — treat the amending instrument as its own Legal Item. After
   commencement is proved, prefer matching HKeL evidence under ADR 0022 or ADR
   0029; while it is unavailable, ADR 0080 may create amended principal text
   only through its complete evidence-bound reconstruction gates.
7. **Repeal, revocation, expiry, or revival** — require the exact operative
   provision, notice, later instrument, or express sunset clause and its
   effective date. Disappearance, an HKeL status label alone, or textual
   similarity is insufficient.
8. **Correction** — change legal text or status only under an express correcting
   instrument or another accepted correction rule. HKeL Editorial Records
   follow the separate rule accepted in ADR 0026.
9. **Amended or revoked event notice** — preserve both instruments and apply the
   later one only to the dates and Legal Locations it expressly changes. Never
   overwrite the earlier event history.
10. **Missing or conflicting evidence** — preserve all artifacts, make no new
    current-law assertion, and use Quarantine or ADR 0005's unavailable-scope
    process.

## Fact-specific priority and conflicts

No source wins globally merely because it is newer. Priority depends on the
fact being proved:

- the exact Gazette instrument or operative provision proves its legal event;
- matching HKeL XML and the applicable verified or assisted official HKeL copy
  evidence support the resulting current consolidated text;
- HKeL status data and enactment history corroborate and reconcile events but
  do not replace missing event evidence; and
- Department of Justice press releases, HTML search results, and HKeL Gazette
  back-captures are discovery or corroboration unless a later accepted rule
  gives an item a stronger role. LegCo Bills and proceedings are excluded from
  automated pipeline use under ADR 0027.

If the Gazette proves that an amendment commenced but matching applicable HKeL
text evidence is unavailable, record the event and exact affected locations
and report a Coverage Gap. Under ADR 0080, first attempt exact reconstruction;
if it cannot pass, apply ADR 0079's warned analytical fallback for every
affected location for which valid latest applicable official HKeL text is held. If HKeL appears to show an
operative change but no accepted event evidence can be found, quarantine the
change rather than treating its appearance as proof.

## Watcher and reconciliation rule

The Watcher accounts for ordinary Gazette publication and Gazette Extraordinary
between ordinary issues. Each observation cutoff reconciles the complete
expected issue-and-notice inventory; keyword alerts alone cannot support a no-
change decision. Missing sequences, replaced artifacts, late captures, and
unexpected notices require investigation.

ADR 0031 fixes the ordinary Watcher tier at one lightweight check per day and
requires a complete successful Gazette Observation within 24 hours of the
weekly release cutoff. The expected ordinary issue is completely reconciled
after its normal publication window; an urgent accepted signal may open an
earlier bounded run. Exact clock times and retry backoff remain operational
values and cannot weaken complete reconciliation.

ADR 0032 makes archival Gazette and HKeL back-capture acquisition on demand.
Their ordinary unavailability does not block a fresh release. Once a specific
historical or escalation decision requires official archival evidence, missing
evidence blocks only that decision. HKeL back-captures remain nonblocking
discovery material.

Legal Supplement No. 3 entries may be minimally identified and classified to
prove Gazette inventory completeness, but their Bill text is not acquired or
processed and no Bill workflow is created. ADR 0027 records this boundary.

## Consequences

The system can be current in its awareness of enactment, commencement, partial
commencement, repeal, and other events without pretending that every event is
an HKeL Official Version. ADR 0080 separately governs when proved events may
produce warned reconstructed wording. Every event remains evidence-backed,
location-specific, append-only, and reviewable. This decision does not
authorize source acquisition, implementation, publication, Pinecone mutation,
or deployment.
