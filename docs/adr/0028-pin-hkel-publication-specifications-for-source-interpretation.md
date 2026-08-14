---
status: accepted
date: 2026-08-11
amended_by:
  - 0031
  - 0032
amends:
  - 0019
refines:
  - 0022
depends_on:
  - 0018
---

# Pin HKeL publication specifications for source interpretation

The Hong Kong Legislation Source Rulebook registers
`HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS` as a mandatory source-interpretation
role. The specifications define how the pipeline reads HKeL artifacts. They do
not prove that a particular legal item changed or has a particular legal
status.

The word **specifications** is deliberate. HKeL publishes schemas, data
dictionaries, notices, and catalogue descriptions. The pipeline's Source
Rulebook owns the executable rules that apply those published meanings.

Relevant official references include the [HKeL XML data dictionary](https://www.elegislation.gov.hk/datagovhk/hkel_data-dictionary_en.pdf),
the [legislation-list XML data dictionary](https://www.elegislation.gov.hk/datagovhk/hkel_list_xml-dictionary_en.pdf),
the [HKeL Important Notices](https://www.elegislation.gov.hk/importantnotices),
and the [current HKeL dataset catalogue](https://data.gov.hk/en-data/dataset/hk-doj-hkel-legislation-current).

## Publication Specification Bundle

Each accepted Hong Kong Legislation Source Rulebook version pins a complete
**HKeL Publication Specification Bundle** containing only the official
artifacts on which its connector, parser, and verifier rely. The bundle may
include:

- the exact HKeL XML Schema Definition, currently referenced as `hklm.xsd`;
- the Hong Kong legislation XML data dictionary;
- the current-and-past legislation-list XML data dictionary;
- the exact HKeL Important Notices relied on for the official verification
  mark, verified-copy elements and dates, informational HTML and RTF formats,
  and informational Simplified Chinese status;
- applicable DATA.GOV.HK catalogue descriptions for resource grouping,
  language, format, update frequency, schema reference, and hashes; and
- another exact official specification only when the rulebook identifies the
  interpretation that depends on it.

The bundle records every source location, published version where available,
capture time, content fingerprint, relationship to other artifacts, and the
rulebook's explicit interpretation mapping. A JSON dictionary is included only
when an accepted connector uses JSON. Unused help pages are not captured merely
because they exist.

## Interpretation boundary

The bundle may define:

- document and legislation types;
- current and past version fields, version dates, language identifiers, and
  resource hashes;
- structure such as sections, Schedules, tables, forms, lead-ins, and
  continuations;
- the distinction between legal content, metadata, statutory notes, editorial
  notes, and other source material;
- status categories, status codes, partial-status values, and their published
  meanings; and
- the verification mark and relevant verified-copy cover and page elements.

These definitions tell the pipeline how to parse and classify an observed
artifact. They cannot prove an item-specific commencement, repeal, expiry,
amendment, or other legal event. A status code is a routing and reconciliation
signal; accepted Gazette, Editorial Record, HKeL verified text, or other
assigned evidence must still prove the relied-on fact.

Publication specifications, interpretation mappings, and review material never
enter `metadata.text`, `metadata.authority_note`, embeddings, Pinecone, or the
downstream LLM request.

## Pinning and change control

Processing uses the preserved bundle pinned by the exact Source Rulebook
version. It does not retrieve mutable documentation during each record
operation.

A specification Watcher periodically fingerprints every relied-on official
artifact. Captures are append-only. A changed XSD, dictionary, notice, enum,
field meaning, or verification rule opens a **Source Contract Review** rather
than a legal-text update.

Affected new processing pauses until the Legal Desk and technical owner:

1. compare the old and new bundles;
2. identify syntactic, semantic, verification, and serving impact;
3. update parsers, verifiers, interpretation mappings, and conformance fixtures
   where necessary;
4. issue a new immutable Source Rulebook version and impact declaration; and
5. re-evaluate only the Legal Items, decisions, releases, or Search Records that
   the impact declaration identifies.

A specification change alone does not create, change, warn, withhold, retire,
or reinstate a Search Record. Existing served records continue unless the
evidence-backed impact review establishes that they are affected and the
ordinary release and approval process replaces them.

## Availability, conflicts, and unknown input

A temporary documentation outage does not automatically stop processing when:

- the accepted bundle remains preserved and fingerprinted;
- live HKeL artifacts still validate against it;
- no schema, namespace, enum, or referenced-version change is observed; and
- the specification-checking freshness limit has not expired.

Affected new processing stops and Source Contract Review opens when a freshness
limit expires, a live artifact stops validating, an unknown element or value
appears, a referenced specification changes fingerprint, or the relied-on
official artifacts conflict.

Syntactic validity and semantic meaning are separate facts. An XSD does not
silently override a conflicting data dictionary or notice, and the newest page
does not automatically win. The Evidence Vault preserves every version and the
conflict blocks only the affected interpretation until it is resolved.

## Examples

1. The data dictionary states that the XML `meta` block is not part of the
   official law. The rulebook may explicitly exclude it from legal text rather
   than guessing from the tag name.
2. A list record contains status code `6`, published as “Not yet in
   operation”. The code routes the item for investigation or the Waiting Room;
   it does not replace the required event evidence.
3. `hklm.xsd` changes at the same URL. The fingerprint change pauses affected
   new processing and opens review; the parser does not silently accept new
   semantics and Pinecone does not change.
4. The Important Notices change the verification-mark rule. New affected PDF
   verification pauses until a reviewed mapping and tests are accepted.
   Existing serving records change only if the impact review proves they are
   affected and a later approved release replaces them.

## Remaining operational values

ADRs 0031 and 0032 assign the specification bundle and Important Notices to the weekly
supporting-source tier. They are fingerprint-checked once in every weekly cycle
and must have a successful current-cycle Observation whenever affected new
processing relies on them. The final artifact inventory, exact clock time,
endpoint records, and interpretation-mapping schema remain concrete Source
Rulebook work. The stable role ID is
`HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS`. These remaining details cannot weaken
the pinned-bundle, change-review, fail-closed, or serving-boundary requirements
accepted here.

This decision does not authorize source acquisition, implementation,
publication, Pinecone mutation, or deployment.
