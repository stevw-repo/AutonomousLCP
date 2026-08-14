---
status: accepted
date: 2026-08-12
amended_by:
  - "0081"
refined_by:
  - "0086"
amends:
  - 0019
  - 0022
  - 0025
  - 0026
  - 0028
  - 0029
  - 0031
depends_on:
  - 0005
  - 0018
  - 0023
  - 0030
---

# Register fact-specific Hong Kong legislation sources

The Hong Kong Legislation Source Register uses stable source IDs for official
publisher products and accepted evidence roles. It does not use one global
`controlling` flag and it does not treat a URL as source identity.

Every source registration answers three separate questions:

1. **Fact authority** — exactly what fact may preserved evidence from this
   source prove?
2. **Outage impact** — does an unavailable source prevent the whole fresh Hong
   Kong release, only the affected work that requires it, or neither?
3. **Monitoring tier** — is it checked daily, weekly, monthly or after a
   relevant event, or acquired only when a specific task needs it?

This separation is necessary because authority is fact-specific. The Gazette
may prove publication or commencement, for example, but it does not prove the
resulting HKeL consolidated wording. HKeL current XML constructs searchable
text, but it does not by itself prove why that text changed.

## Stable source identity and changing endpoints

A stable source ID identifies the official publisher product and the role in
which the rulebook accepts it. The ID contains no URL, language, format, date,
version, or resource filename.

Each Registered Source has separately versioned **endpoint records**. An
endpoint record may contain:

- the live URL or physical holding;
- language and format;
- access method and expected media type;
- the dates for which the endpoint was active;
- predecessor and successor endpoints; and
- technical health and connector configuration.

A URL move changes the endpoint record, not the stable source ID. A materially
different publisher product or evidence role receives a new source ID.
English, Traditional Chinese, XML, JSON, ZIP, PDF, RSS, generated download
URLs, and physical archive locations are endpoint or artifact facts.

The Hong Kong Legislation Legal Desk owns all roles below. Source connectors
capture evidence; the Desk applies the fact-specific rules.

## Availability classes

The registry uses three outage-impact classes:

- **`RELEASE_BLOCKING`** — a new Hong Kong release cannot claim a fresh,
  complete current-law observation while the source is stale, failed, partial,
  or unreconciled;
- **`AFFECTED_WORK_BLOCKING`** — only the item, investigation, interpretation,
  or decision that actually requires the missing source is blocked; and
- **`NONBLOCKING`** — an outage is recorded but does not invalidate otherwise
  complete accepted evidence. A detected conflict may still block the affected
  item.

An `AFFECTED_WORK_BLOCKING` source that is not needed for the current release
creates no release-wide freshness requirement.

## Registered Source inventory

| Stable source ID | Fact authority and forbidden use | Outage impact | Monitoring tier |
|---|---|---|---|
| `HK-LEG-HKEL-CURRENT-INVENTORY` | Proves the complete current HKeL resource universe exposed by the publisher: item and resource identities, language resources, version and status signals, locators, and declared hashes. It does not prove exact legal wording or the cause of an event. | `RELEASE_BLOCKING` | Daily current-law signal; complete successful Observation within 24 hours of the weekly cutoff |
| `HK-LEG-HKEL-CURRENT-DATA` | Supplies current English and Traditional Chinese XML text and structure used to construct and compare a changed candidate. It does not by itself satisfy the accepted text-and-version evidence threshold or prove why the law changed. | `AFFECTED_WORK_BLOCKING` | On demand after a changed inventory signal, new item, missing evidence, or affected review |
| `HK-LEG-HKEL-VERIFIED-COPIES` | Proves the exact verified English and Traditional Chinese HKeL text and version for an item governed by ADR 0022. It does not replace XML construction or prove the cause of change. | `AFFECTED_WORK_BLOCKING` when the verified-copy path applies | On-demand item evidence |
| `HK-LEG-HKEL-ASSISTED-COPIES` | Supplies accepted official HKeL assisted English and Traditional Chinese text-and-version evidence for any covered Hong Kong Legislation item under ADR 0081. It does not claim statutory verification and may support a newer applicable version than an available verified copy. | `AFFECTED_WORK_BLOCKING` for an item using this path | On-demand item evidence |
| `HK-LEG-HKEL-PAST-INVENTORY` | Shows which earlier HKeL versions and resources the publisher retains, with dates, languages, locators, and hashes. It does not prove exact past wording, present law, continuity, or the cause of change. | `AFFECTED_WORK_BLOCKING` only for a specific historical investigation, missing-baseline recovery, audit, or evaluation task | On demand only; no ordinary weekly check or release freshness gate |
| `HK-LEG-HKEL-PAST-DATA` | Supplies earlier structured XML and legal structure. Exact past wording still requires matching past verified PDFs. It does not establish present law, a legal event, or identity continuity by similarity. | `AFFECTED_WORK_BLOCKING` only for the specific task that requires the artifact | On demand only |
| `HK-LEG-HKEL-EDITORIAL-RECORDS` | Proves the exact official editorial amendment, affected locations, Parts, and effective dates stated in an Editorial Record. It does not supply the resulting consolidated serving text. | `AFFECTED_WORK_BLOCKING` when a current change or decision requires the record | Weekly supporting source, plus affected acquisition after a signal |
| `HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS` | Defines the published meanings of HKeL schemas, fields, structures, status values, formats, and verified-copy marks. It proves no item-specific wording or event. | `AFFECTED_WORK_BLOCKING` when affected new processing relies on a stale, changed, conflicting, unknown, or non-validating interpretation; otherwise the preserved accepted bundle may continue under ADR 0028 | Weekly supporting source |
| `HK-LEG-GLD-EGAZETTE` | Supplies exact available modern ordinary and Extraordinary Gazette artifacts and proves only the publication, clause, notice, or legal event assigned to the artifact class and enabling authority. It does not prove resulting HKeL consolidation. | `RELEASE_BLOCKING` | Daily current-law signal; complete successful Observation within 24 hours of the weekly cutoff |
| `HK-LEG-OFFICIAL-GAZETTE-ARCHIVE` | Supplies exact printed Gazette, Government Records Service, or accepted official-holding evidence for a pre-online, missing, ambiguous, or conflicting event. It does not prove resulting consolidation. | `AFFECTED_WORK_BLOCKING` only for the historical or escalation decision that requires it | On demand only |
| `HK-LEG-HKEL-GAZETTE-BACKCAPTURE` | Supports candidate-event discovery, source-note linking, and location of older Gazette material. It proves no event until the required official Gazette evidence is obtained. | `NONBLOCKING` | On demand only |
| `HK-LEG-BASIC-LAW-PORTAL` | Supplies constitutional scope inventory, Annex III and instrument links, and discrepancy signals. Its page text does not prove serving wording or controlling legal status. | `NONBLOCKING`; a detected conflict blocks the affected item | Monthly baseline plus an affected check after a relevant controlling-source signal |
| `HK-LEG-NPC-NATIONAL-LAWS-DATABASE` | May prove originating national-law text, national promulgation material, and published national status when an item-specific rule assigns that exact fact. It does not prove the Hong Kong method or time of application or supply the required HKeL bilingual serving evidence. | `AFFECTED_WORK_BLOCKING` only when an item-specific decision requires the national-source fact; otherwise a cross-check outage is nonblocking | Monthly baseline, event-triggered cross-check, and on-demand affected acquisition |
| `HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS` | May prove an exact NPC or NPCSC decision or interpretation at its originating official source when an item-specific rule assigns that fact. It does not replace the HKeL evidence path or independently prove every Hong Kong application fact. | `AFFECTED_WORK_BLOCKING` only when the exact originating material is required; otherwise a cross-check outage is nonblocking | Monthly baseline, event-triggered cross-check, and on-demand affected acquisition |

## Endpoint families

The endpoint records begin with these official product families:

- `HK-LEG-HKEL-CURRENT-INVENTORY` — the DATA.GOV.HK **List of Hong Kong
  Legislation (Current version)** catalogue and enumerated English and
  Traditional Chinese XML resources. JSON is added only if an accepted
  connector uses it; Simplified Chinese remains informational.
- `HK-LEG-HKEL-CURRENT-DATA` — the DATA.GOV.HK **Hong Kong Legislation
  (Current Version)** catalogue and its enumerated current ZIP resources.
- `HK-LEG-HKEL-PAST-INVENTORY` and `HK-LEG-HKEL-PAST-DATA` — the separate
  official past-list and past-version DATA.GOV.HK catalogues and enumerated
  resources.
- verified and assisted copies — the exact HKeL Legal Item page, download
  metadata, and generated artifact locators. Generated `legoutput` URLs do not
  become source identity. The verified-copy role also uses the HKeL verified-
  list product when a rule relies on it.
- `HK-LEG-HKEL-EDITORIAL-RECORDS` — the official `/editorialrecord` product,
  its RSS change signal, and exact numbered record routes. RSS is a change
  signal; complete numbered-inventory reconciliation remains required.
- `HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS` — the exact relied-on `hklm.xsd`,
  HKeL data dictionaries, Important Notices, DATA.GOV.HK catalogue
  descriptions, and rulebook interpretation map.
- `HK-LEG-GLD-EGAZETTE` — the official GLD List of Gazette and Search Gazette
  Notice products and the exact issued artifacts to which they point. Search
  results and mutable search URLs are locators only.
- `HK-LEG-OFFICIAL-GAZETTE-ARCHIVE` — the exact printed Gazette, Government
  Records Service catalogue or holding, or other accepted official holding
  used for the decision.
- `HK-LEG-HKEL-GAZETTE-BACKCAPTURE` — HKeL's Gazette product, for discovery
  only.
- `HK-LEG-BASIC-LAW-PORTAL` — the official Basic Law text, Annex and
  Instrument, national-laws, and Important Notices pages.
- `HK-LEG-NPC-NATIONAL-LAWS-DATABASE` — the official National Laws and
  Regulations Database and its exact database and official-gazette artifact
  locators.
- `HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS` — exact official NPC and NPCSC
  decision and interpretation publications.

Relevant official product references include the [current HKeL inventory](https://data.gov.hk/en-data/dataset/hk-doj-hkel-list-of-legislation-current),
[current HKeL data](https://data.gov.hk/en-data/dataset/hk-doj-hkel-legislation-current),
[past HKeL inventory](https://data.gov.hk/en-data/dataset/hk-doj-hkel-list-of-legislation-past),
[past HKeL data](https://data.gov.hk/en-data/dataset/hk-doj-hkel-legislation-past),
[HKeL Editorial Records](https://www.elegislation.gov.hk/editorialrecord),
[HKeL Important Notices](https://www.elegislation.gov.hk/importantnotices),
[GLD e-Gazette Important Notices](https://egazette.gld.gov.hk/en/important-notices),
[Basic Law portal Important Notices](https://www.basiclaw.gov.hk/en/notices/index.html),
and the [National Laws and Regulations Database](https://flk.npc.gov.cn/).

Endpoint records are configuration and evidence, not promises that a current
route will never change. Connector implementation must verify the current
official route and source contract before use.

## Normal current-version comparison

The ordinary update path does not depend on the publisher's historical corpus.
It compares:

1. the pipeline's preserved previous accepted current HKeL evidence bundle;
2. the newly acquired current HKeL evidence bundle; and
3. the accepted Gazette, Editorial Record, or other event evidence that
   explains the change.

The comparison identifies observable differences such as changed wording,
renumbering, movement, disappearance, split, merge, or structure. A difference
opens a question; it does not answer the legal question.

For example, if old section 10 disappears and similar wording appears as new
section 11, similarity may propose possible renumbering. The pipeline preserves
the same Legal Location identity only when an official mapping or a reasoned
Legal Desk rule supported by accepted official evidence proves continuity.
Otherwise the question is quarantined. Historical text never proves repeal,
commencement, renumbering, or identity merely by matching or disappearing.

## Historical-source boundary

Historical HKeL inventories, past XML, past verified PDFs, and official
archival Gazette material are retained as available investigation and recovery
sources. They are useful only for a specific task such as:

- establishing the initial baseline when the pipeline has no preserved prior
  current bundle;
- recovering a missing earlier artifact;
- investigating a disputed historical disappearance, split, merge,
  renumbering, or correction;
- audit or recovery verification; or
- bounded historical evaluation if reconstructed serving is reconsidered.

They are not checked in the ordinary weekly pipeline, do not receive a routine
freshness gate, and cannot block an otherwise fully supported current-law
release. Once requested, missing or conflicting historical evidence blocks
only that investigation or dependent decision.

Editorial Records are different. A newly published Editorial Record may
directly explain a new current-text change, so its complete inventory remains a
weekly supporting-source check.

This historical-source demotion amends ADRs 0026 and 0031. It removes HKeL past
data from ordinary weekly monitoring while preserving its narrow evidence
roles and fail-closed behavior when a specific task actually relies on it.

## Exclusions

Department of Justice explanatory pages used only to justify the architecture
are not separately watched Registered Sources unless a concrete parser,
verifier, or rulebook rule later depends on a mutable statement on that page.
LegCo Bills and proceedings, HKLII, generic press releases, HTML search results,
and unofficial mirrors remain excluded or unregistered under the accepted
rules.

This source inventory does not reopen the user-flagged HKeL Instruments &
Others treatment. ADR 0030 and its mandatory future-review gate remain in
force, and row population remains deferred.

## Consequences

The Hong Kong Source Register now has complete stable role IDs, fact authority,
outage impact, monitoring tier, and official endpoint families. Exact clock
times, retry counts, backoff, provider limits, connector mechanics, endpoint
validity dates, and machine-readable registry encoding remain operational or
implementation decisions. They cannot weaken the accepted evidence and
freshness rules.

This decision does not authorize source acquisition, implementation,
publication, AI or embedding calls, Pinecone mutation, or deployment.
