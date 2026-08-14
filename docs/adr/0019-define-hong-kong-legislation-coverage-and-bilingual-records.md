---
status: accepted
date: 2026-08-11
amended_by:
  - 0020
  - 0021
  - 0022
  - 0023
  - 0025
  - 0026
  - 0027
  - 0028
  - 0029
  - 0030
  - 0031
  - 0032
  - "0080"
  - "0081"
depends_on:
  - 0003
  - 0005
  - 0012
  - 0013
  - 0018
---

# Define Hong Kong legislation coverage and bilingual records

The Hong Kong Legislation Source Rulebook accounts for the complete Hong Kong
legislation universe described below. Coverage is broader than Pinecone
selection: every covered item must receive a current-searchable or explicit
non-searchable disposition, while only supported operative current provisions
enter ordinary current-law search.

Hong Kong e-Legislation (HKeL) is the official consolidated-legislation
boundary. The Department of Justice states that HKeL is the only official
database of Hong Kong legislation and that verified HKeL copies have legal
status under the Legislation Publication Ordinance. HKeL provides current
legislation and past versions from 30 June 1997. Its official data model
classifies Ordinances, Subsidiary Legislation, and Instruments and publishes a
separate current “Instruments & Others” package.

Relevant official references are:

- [Department of Justice — published version of Hong Kong legislation](https://www.doj.gov.hk/en/about/orgchart_ldd_published_version.html);
- [HKeL — important notices and verified-copy status](https://www.elegislation.gov.hk/importantnotices);
- [Department of Justice — law in the HKSAR](https://www.doj.gov.hk/en/our_legal_system/law_in_the_hksar.html);
- [DATA.GOV.HK — current Hong Kong legislation dataset](https://data.gov.hk/en-data/dataset/hk-doj-hkel-legislation-current); and
- [HKSAR Gazette — publication structure](https://egazette.gld.gov.hk/en/important-notices).

## Release Scopes

The Hong Kong Legislation Legal Desk owns three non-overlapping Release Scopes:

1. **`HK-LEG-ORDINANCES`** — all Hong Kong Ordinances, including principal,
   amending, private, and other enacted Ordinances;
2. **`HK-LEG-SUBSIDIARY`** — all subsidiary legislation, including applicable
   regulations, rules, rules of court, orders, proclamations, resolutions,
   notices, bylaws, commencement instruments, and other instruments made under
   an Ordinance and having legislative effect; and
3. **`HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS`** — the Basic Law, national
   laws listed in Annex III and applied to Hong Kong, central constitutional
   decisions and interpretations, and genuine residual constitutional or
   other material accepted from HKeL's Instruments or Instruments & Others
   classification after exact inventory and legal-role reconciliation.

HKeL's `Instrument` classification is a source publication and indexing fact,
not a Release Scope. ADR 0030 requires a complete versioned Instrument
Disposition Registry and routes each legal object by its actual legal nature.
An A-series Hong Kong Ordinance belongs to `HK-LEG-ORDINANCES`; A-series
subsidiary legislation belongs to `HK-LEG-SUBSIDIARY`; only the genuine
residual constitutional and other material belongs to the third scope. The
A-number remains a source alias and cannot create duplicate ownership.

Schedules, annexes, appendices, forms, and tables that form part of an
instrument are Legal Locations within their parent Legal Item. They do not
become separate Release Scopes merely because HKeL publishes or updates them as
separate structural parts.

The Gazette is a Registered Source rather than a Release Scope. Its Ordinance,
Regulation, Bill, other supplement, and Gazette Extraordinary classifications
support discovery and event evidence, but the covered legal item remains owned
by one of the three scopes above.

## Complete accounting and search eligibility

Every Corpus Release for a Hong Kong Legislation scope accounts for:

- operative current material eligible for bilingual Search Records;
- enacted but uncommenced material preserved in the Waiting Room;
- amending, commencement, repeal, expiry, revival, correction, and editorial
  material used to establish identity, version, or legal status;
- repealed, expired, superseded, or past versions preserved outside ordinary
  current-law Pinecone serving; and
- uncertain or conflicting material preserved in Quarantine.

An amending Ordinance or subsidiary instrument is its own Legal Item. It changes
the Official Version of a principal instrument only when the controlling
official source publishes that supported version. A commenced amendment without
the required current official consolidation creates a Coverage Gap; the
pipeline does not splice amendment instructions into old text.

A commencement notice may establish different commencement dates for different
provisions. The rulebook therefore makes commencement decisions at the exact
affected Legal Location level where required. An enacted or gazetted item is
not searchable merely because it has been published.

Bills, drafts, and Legislative Council proceedings are excluded from this
pipeline under ADR 0027. They are not Registered Sources or routinely ingested
discovery evidence; a reviewer may consult them only as optional,
non-controlling human research. Judgments belong to Hong Kong Cases. Publisher-
derived material belongs to Hong Kong Principles. A treaty is outside this
rulebook unless its effect is implemented through a covered Hong Kong
Ordinance, subsidiary instrument, or constitutional or other applicable
instrument; any direct treaty corpus needs its own later coverage decision.

## One bilingual Search Record

Every searchable Hong Kong legislation record is one bilingual Search Record.
Its single `metadata.text` contains the corresponding English and Traditional
Chinese content for the same Legal Location, Official Version, and operative
state. The pipeline does not create separate English-only or Traditional-
Chinese-only Search Records.

This preserves the accepted six-field metadata contract:

- no `language` metadata field is added;
- both languages are passed together to the downstream LLM;
- both languages are included together in the embedding input because the
  embedding contract uses `metadata.text` only; and
- one retrieval result represents one legal location rather than two duplicate
  language results that Ask.Legal cannot join at query time.

The English and Traditional Chinese portions must be source-aligned. A missing,
stale, differently versioned, or structurally unmatched required language
blocks a new bilingual record and enters Quarantine or the accepted unavailable-
scope process. The pipeline never falls back to a monolingual serving record.

If a long bilingual provision is divided into deterministic serving parts,
each part contains the corresponding English and Traditional Chinese material.
No split may orphan one language or combine different legal locations merely
to reach a target length.

Changing either language changes `metadata.text` and therefore creates a new
Search Record ID under ADRs 0011 and 0013. Exact reuse requires equality of the
complete bilingual payload and continuing legal support. Simplified Chinese
may be retained as informational source evidence when useful, but it is not a
controlling text and does not replace Traditional Chinese in a serving record.

ADR 0021 settles the canonical labels, ordering, separators, normalization,
content exclusions, and structure-aligned bilingual split rule. ADR 0020
settles the separate authority-note-language rule: a real Hong Kong authority note
is an English-only internal instruction for the downstream LLM. ADR 0081
requires matching English and Traditional Chinese HKeL XML and matching
verified or assisted official HKeL copy evidence before an applicable
HKeL-derived current-law record can proceed; assisted status alone does not
create an authority note. ADR 0080
supersedes ADR 0023's reconstruction deferral and permits exact evidence-bound
reconstructed consolidations with the mandatory warning; ADR 0079 remains the
fallback when reconstruction cannot pass. ADR 0025 assigns fact-specific Gazette
roles and event rules without treating Gazette material as consolidated text.
ADR 0026 assigns historical-reconciliation and official editorial-amendment
roles to HKeL past data and Editorial Records respectively. ADR 0027 excludes
LegCo Bills and proceedings from source registration, ingestion, watching, and
serving while preserving optional non-controlling human research. ADR 0028
requires a pinned HKeL Publication Specification Bundle to interpret source
artifacts without treating general specifications as item-specific evidence.
ADR 0032 fixes the complete stable Hong Kong Registered Source inventory,
fact-specific authority, endpoint model, outage impact, and monitoring tier.

## Consequences and remaining rulebook work

Hong Kong legislation completeness is measured across all three Release
Scopes, including non-searchable dispositions. A current-law corpus containing
only chapter-numbered Ordinances is incomplete because subsidiary legislation
and the constitutional-and-other-instruments scope are also required.

The coverage promise, bilingual-record rule, tiered HKeL XML-to-PDF evidence
requirements, Registered Source roles, stable rules, conceptual fixtures,
strict fixture packages, and frozen Source Rulebook Package architecture are
settled through ADR 0042. Remaining work is deliberately separated below.

Implementation and operational specification still require:

- the machine-readable encoding, validity dates, connector mechanics, and
  health checks for ADR 0032's stable source IDs and endpoint records;
- concrete clock times, retry counts, backoff values, and provider limits within
  the accepted ADR 0031 monitoring tiers and freshness gates;
- the exact executable schemas, fixture bytes, validators, code catalogue, and
  English-only authority-note templates that conform to the accepted package; and
- the exact connector mechanics and endpoint-health implementation behind the
  stable source identities.

Two product decisions remain deliberately deferred rather than accidentally
unspecified: the complete populated and legally reviewed Instrument
Disposition Registry for HKeL Instruments & Others under ADR 0030, and the
final deterministic-versus-generative-LLM task allocation under ADR 0043.

Source-specific legal compliance controls remain deferred to the legal team
under the accepted assumption that the registered uses are legally compliant.
