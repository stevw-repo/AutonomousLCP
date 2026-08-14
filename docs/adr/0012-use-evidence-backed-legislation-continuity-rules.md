---
status: accepted
date: 2026-08-11
amended_by:
  - 0013
  - 0019
  - "0079"
  - "0080"
---

# Use evidence-backed legislation identity-continuity rules

Legislation identity follows proved legal continuity. It is not inferred from
a matching URL, title, citation, provision number, wording, or position in a
document. The responsible Legal Desk applies the rules below to preserved
official evidence. If no rule is satisfied, the material is quarantined rather
than matched by guesswork.

This decision applies the identity layers accepted in ADR 0011:

- the **Legal Item** identifies the Act, regulation, rule, or other instrument;
- an **Official Version** identifies one official consolidation, compilation,
  correction, or other published version of that Legal Item;
- a **Legal Location** identifies a provision, Schedule item, or other tracked
  place inside the Legal Item; and
- a **Search Record** identifies one exact approved serving payload. ADR 0013
  as amended by ADR 0050 makes that payload the five original fields plus
  required `authority_note`.

A **Legal Status Event** is distinct from an Official Version. It records a
sourced change in legal effect or status, such as commencement, repeal, expiry,
or revival, when that event is not itself a newly published official version.
The pipeline must not invent an Official Version merely because legal status
changed.

## Continuity rules

| Observed event | Legal Item and Official Version | Legal Location | Search Record and lineage |
|---|---|---|---|
| The official page, URL, provider location, or mirror moves while the official artifact is proved unchanged | Keep the Legal Item and Official Version; record the new location as an alias and preserve the new Source Snapshot | Keep the Legal Location | Reuse the Search Record; no replacement is created solely for a source move |
| A new official consolidation or compilation is published, even if no legal text changed | Keep the Legal Item and allocate a new Official Version | Keep each location only after complete provision reconciliation proves continuity | Reuse an exact unchanged serving payload only when continuing legal support is also proved; otherwise allocate a new Search Record |
| An amendment changes the wording of a continuing provision | Keep the Legal Item and allocate a new Official Version when the changed official text is published | Keep the Legal Location when the evidence proves that the provision continues | Allocate new Search Records for changed payloads and link them to their predecessors; exact unaffected records may be reused |
| An official correction or erratum changes the official text | Keep the Legal Item and allocate a new Official Version | Keep the Legal Location unless the correction establishes a structurally different location | Allocate new Search Records for changed payloads and identify them as official corrections of their predecessors |
| The instrument is officially renamed or recited under a changed citation | Keep the Legal Item when official evidence says that it is the same instrument; allocate a new Official Version only when a new official version was published | Keep proved continuing locations | A changed serving payload gets a new Search Record; a traceability-only display-citation change gets a new Record Traceability Lookup revision instead |
| A provision is truly renumbered | Keep the Legal Item and use the applicable new Official Version or Legal Status Event | Keep the Legal Location only when an official conversion table, express mapping, or a Legal Desk decision under a written rulebook proves continuity; record the old and new locators as aliases | Allocate a new Search Record if any serving field changed and link it as renumbered from its predecessor |
| A provision is repealed without replacement | Keep the Legal Item; record the new Official Version if one was published, otherwise record the repeal as a Legal Status Event | Preserve the old Legal Location permanently and mark its legal effect as ended | Remove its records from the next approved current desired state; do not delete their identities or evidence |
| A provision is repealed and substituted, including at the same visible number | Keep the Legal Item and use the applicable new Official Version or Legal Status Event | End the old Legal Location and allocate a new one; reuse of the visible number does not reuse identity | Allocate new Search Records and link them as substitutions for the old records or location |
| One provision is split into several | Keep the Legal Item and use the applicable new Official Version | End the old location and allocate each successor a new Legal Location linked as split from it | Allocate the required new Search Records and account for all predecessor material; do not force a false one-to-one match |
| Several provisions are merged | Keep the Legal Item and use the applicable new Official Version | End the old locations and allocate a new merged Legal Location linked to every predecessor | Allocate new Search Records and preserve the many-to-one lineage |
| The entire instrument is repealed or expires without a successor | Preserve the Legal Item permanently and record a new Official Version only if one was published; otherwise append a Legal Status Event | Preserve its locations as historical and ended | Remove current records only through a complete approved desired-state change; this is retirement from current serving, not deletion |
| A repealed instrument is replaced or re-enacted as a newly enacted instrument | Allocate a new Legal Item, even if its title or wording is similar; link the instruments as replacement or re-enactment | Allocate new Legal Locations | Allocate new Search Records; similarity does not establish reuse |
| An instrument or provision is officially revived or reinstated | Keep or allocate the Legal Item and Legal Location identities according to the official continuity evidence; record a new Official Version when published, otherwise append a Legal Status Event | Reuse a location only when the evidence proves revival of that same legal location | Reuse an old Search Record only when all six metadata fields are exactly identical and the Legal Desk proves continuing legal support; otherwise allocate a new record linked as reinstated from its predecessor |
| The pipeline corrects its own processing error but the official source did not change | Keep the Legal Item, Official Version, and Legal Location | Keep the Legal Location | Allocate a corrected Search Record when the serving payload changes and link it as a processing correction; never describe it as an official correction |
| A duplicate capture of the same official artifact is discovered | Reuse the proved existing Legal Item and Official Version and attach the evidence or alias | Reuse proved existing locations | Do not create duplicate Search Records |
| Official sources conflict or continuity remains ambiguous | Make no new current identity assertion | Make no location-reuse decision | Preserve all competing snapshots, quarantine the event, and keep it outside promotion until the Legal Desk resolves it |

The rule for an amending instrument is separate from the rule for the amended
instrument. An amending Act is its own Legal Item. It may cause a later
Official Version of the principal Act only when the official source publishes
that version. If an amendment has commenced but an official consolidation is
not available, the existing Coverage Gap rules apply. ADR 0080 permits an
evidence-bound Reconstructed Consolidation Artifact without inventing an
Official Version. When exact reconstruction cannot pass, ADR 0079 requires a
warned analytical record for every affected location for which valid last-
verified official text is held; it creates no record where that text does not
exist.

## Minimum evidence

Every continuity decision records its rule, responsible Legal Desk, preserved
evidence, effective and observation dates, and the identities it kept, created,
ended, or related. Depending on the event, the evidence must include:

- official instrument identifiers, titles, citations, and status data;
- the official consolidation, compilation, correction, or publication identity
  and date;
- commencement, repeal, expiry, substitution, or revival evidence;
- complete preserved before-and-after text and provision inventories;
- official conversion, renumbering, or relationship tables when available;
- exact fingerprints of the source artifacts and derived records; and
- the Legal Desk's reasoned decision when the written source rulebook permits
  interpretation rather than an express official mapping.

Automated matching may propose candidate relationships and exact-text reuse.
It cannot decide legal continuity from similarity, numbering, or aliases. Each
jurisdiction-and-material source rulebook must still specify which official
documents and status fields satisfy these evidence categories.

## Consequences

The Management Register needs a separate Legal Status Event object, provision
inventories for version reconciliation, typed one-to-one and many-sided
lineage, alias history, and explicit ended-without-deletion status. Corpus
construction must distinguish a source move, new official version, legal-status
change, record replacement, traceability-only revision, and serving retirement.

These rules settle the general legislation identity-continuity model. They do
not settle jurisdiction-specific evidence sources, the scope of every class of
delegated legislation, the exact lineage-relation encoding, case-law or
Principles continuity, or the final Record Traceability Lookup field
encoding.
