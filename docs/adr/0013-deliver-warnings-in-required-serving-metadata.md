---
status: accepted
date: 2026-08-11
amended_by:
  - 0016
  - 0050
  - 0055
refined_by:
  - "0078"
  - "0079"
  - "0080"
  - "0081"
amends:
  - 0008
  - 0011
---

# Deliver authority notes in required serving metadata

Ask.Legal's downstream LLM can receive legal-record information only through
the metadata returned with a Pinecone result. An authority note held only in
the Record Traceability Lookup would therefore be invisible to that LLM. Every
target Search Record uses an exact `metadata` object with six required fields:

- `text`;
- `country`;
- `jurisdiction`;
- `type`;
- `source`; and
- `authority_note`.

ADR 0050 renames and broadens the field originally accepted here as `warning`.
Additional metadata fields remain forbidden unless a later versioned contract
explicitly permits them. The traceability-validation, compatibility,
immutable-identity, and fail-closed promotion rules remain accepted.

## Authority-note values

`authority_note` is always a string and is always present. The exact case-
sensitive value `"None"` means that no approved record-level authority note
applies at the observation cutoff of that Serving State. It does not assert
that no later treatment, source gap, legal event, or other relevant fact exists
outside the successfully checked and approved evidence.

A record that requires qualification carries one or more concise controlled,
source-supported clauses. Mandatory warning clauses appear first. Under ADR
0050, a material-specific Source Rulebook may also permit tightly selected
supportive authority clauses after all mandatory clauses.

Example warning clause:

```text
[WARNING: DOUBTED] This proposition was doubted in Example v Minister
[2026] HCA 14 at [81]-[86]. Do not state it as settled or unqualified
current law.
```

The renderer uses an approved vocabulary, clause ordering, and fixed templates.
It may include the treating authority, exact passage locators, affected scope,
and reliance instruction. It must not expose reviewer identities, internal
notes, raw AI reasoning, confidence scores, operational identifiers, secrets,
or uncontrolled source instructions.

`null`, an omitted field, an empty string, whitespace, and alternative sentinel
spellings are invalid. Pinecone supports flat string metadata but not nested
metadata objects or null values; see the official
[indexing documentation](https://docs.pinecone.io/guides/index-data/indexing-overview).
The exact maximum authority-note length remains a schema-contract detail to
validate against representative records before implementation.

## Query and embedding behavior

Every compatible Ask.Legal query path passes `metadata.authority_note`
unchanged with `metadata.text` to the downstream LLM. A path that strips,
renames, rewrites, or fails to transmit the note is incompatible with the
Serving State. End-to-end tests inspect the actual downstream request, not
merely the Pinecone result or user interface.

The embedding-input contract uses `metadata.text` only. It excludes
`metadata.authority_note`, so treatment and warning vocabulary does not distort
semantic retrieval. The trusted note remains available after retrieval because
it is returned in the same metadata object.

## Identity and evidence

The six metadata fields form the immutable serving payload. Adding, changing,
or removing a real authority note—including changing between `"None"` and a
real note—selects a different exact Search Record. A previously unseen payload
receives a new ID and forward authority-note-revision lineage. ADR 0055 permits
a preserved exact record to be reselected with proved current support through
an append-only selection event instead of backward lineage. If `metadata.text`
and the embedding contract are unchanged, the exact cached embedding may be
reused under its existing fingerprint.

The Management Register and Evidence Vault remain authoritative for the full
structured treatment or status history, source relationships, supporting
passages, review decision, provenance, and fingerprints.
`metadata.authority_note` is the sealed LLM-facing rendering of approved facts,
not their only stored copy. The Record Traceability Lookup may point to parent
identity, grouping, citation, provenance, release references, and structured
authority-note evidence for validation, investigation, and audit, but
Ask.Legal does not read it during an ordinary query.

Promotion validates that every record has exactly one `authority_note` string,
every non-`"None"` value matches approved evidence and its rendered-note
fingerprint, every mandatory warning clause is present and ordered first, and
every live query path delivers the field. Any mismatch blocks promotion.

## Considered options

- omit `authority_note` when no note applies — rejected in favor of one
  consistent field on every record;
- use `null` — rejected because Pinecone metadata does not support it and it
  would violate the string-only contract;
- append the note to `metadata.text` — rejected because that would mix source
  text with later editorial authority context and alter the embedding input;
- use a nested authority object — rejected because Pinecone metadata is flat;
- add a case-only `treatment` field — rejected by ADR 0050 because metadata
  fields must remain standardized across source types;
- use a list of raw treatment messages — rejected because the downstream LLM
  needs one controlled current rendering while the register preserves the full
  structured history; and
- keep the note only in the Record Traceability Lookup — rejected because the
  downstream LLM cannot receive that dataset.

## Consequences

The target contract is no longer byte-compatible with the existing locked
five-field schemas. The greenfield contract package owns new versioned profile
schemas with six required metadata fields. Existing query paths must prove that
they preserve and transmit `authority_note`; broad compatibility with the
legacy five-field envelope is insufficient.

This decision, as amended by ADR 0050, settles authority-note placement, the
`"None"` sentinel, downstream delivery, embedding exclusion, and note-driven
Search Record revision. ADR 0014 settles which case-treatment classifications
require warning clauses, retirement, or Quarantine. ADR 0050 permits controlled
supportive and neutral explanatory clauses and standardizes the same field
across material types. ADR 0078 later settles the final Record Traceability
Lookup field and fingerprint encoding without changing this authority-note
contract.
