---
status: accepted
date: 2026-08-10
amended_by:
  - 0013
  - 0016
  - 0050
refined_by:
  - "0078"
---

# Adopt the five-field serving envelope and a separate traceability lookup

> **Amended on 2026-08-11 by ADR 0013 and renamed on 2026-08-12 by ADR 0050:**
> the target metadata contract has the original five fields plus one required
> `authority_note` string. Authority notes are
> delivered to the downstream LLM in metadata rather than solely through the
> former Adjacent Query Lookup.
>
> **Amended on 2026-08-11 by ADR 0016:** that object is renamed the Record
> Traceability Lookup and is not part of the live Ask.Legal query path. Its
> strict validation applies before promotion, not as a runtime join.

The greenfield pipeline adopts the existing standardized Pinecone base fields
and the ADR 0050 authority-note amendment as its target query contract. Every
record has a top-level `id` and an exact `metadata` object containing only:

- `text`;
- `country`;
- `jurisdiction`;
- `type`;
- `source`; and
- `authority_note`.

The contract forbids additional top-level and metadata fields. Registered
profiles may constrain the values differently and therefore retain their own
schema identities, versions, and locked fingerprints. A release, Desired-State
Inventory, Promotion Manifest, and Serving State identify the exact applicable
profile schemas rather than referring vaguely to one universal schema.

The legacy repository is evidence for this decision, not a production
dependency. When implementation is authorized, the adopted schemas and locks
must live under the greenfield versioned contract boundary. Code must not load
them at runtime from the legacy workspace.

The original five fields cannot carry all traceability information required by
the overall design. The system therefore uses a separate immutable,
fingerprinted Record Traceability Lookup keyed by the same Search Record ID. It
points to the record's stable legal identities, source evidence, provenance,
release ownership, structured authority-note evidence, and approved internal
grouping or citation identifiers. ADRs 0013 and 0050 make the approved
LLM-facing authority note a required serving-metadata field because the
downstream LLM receives only Pinecone metadata.

Every served Search Record has exactly one matching traceability entry and one
required metadata `authority_note` string. Duplicate, missing, orphaned,
mismatched, or differently fingerprinted entries block promotion. Authority-
note evidence must match the exact metadata authority note before promotion.
The metadata payload,
lookup identity, and content fingerprints are bound into the Desired-State
Inventory, Promotion Manifest, and Serving State.

Ask.Legal does not read or join this lookup during ordinary queries. Runtime
compatibility tests cover the Pinecone serving contract and authority-note delivery,
not a traceability lookup service. Temporary lookup unavailability after
activation does not stop ordinary search.

Serving State binds the query-contract and Record Traceability Lookup
identities, not one incidental application build. Exact app builds remain in
deployment and request logs. Every active query path must prove compatibility.
The current Python AI-Service is broadly compatible with the legacy five-field
envelope but has not proved the ADR 0050 authority-note-delivery contract. The current Node
Australian path still requires legacy `_node_content`. Whether to upgrade that
path or remove it from new-index queries remains a later decision; neither path
can consume a new serving state until its applicable compatibility tests pass.

## Considered options

- expand Pinecone metadata immediately — originally rejected, then superseded
  in part by ADRs 0013 and 0050 after the user established that the downstream
  LLM can receive authority instructions only through metadata;
- infer provenance or authority-note evidence from `text` or `source` — rejected
  because prose and filenames are not stable traceability contracts;
- bind every Serving State to one exact app build — rejected because unrelated
  application releases should not force a corpus rebuild; and
- assume a stable application is compatible — rejected because current local
  query paths already demonstrate different metadata expectations.

## Consequences

The contract package needs canonical profile-schema registration and lock
verification plus executable ADR 0050 six-field schemas and exact
pre-promotion matching rules. ADR 0078 later fixes the normative Serving Record
and sharded Record Traceability Lookup encodings and fingerprints; executable
schemas and validators must implement that decision. Corpus construction and
promotion must validate both artifacts together.

Ask.Legal must expose the Serving State ID in answer audit records but has no
runtime lookup dependency. The Node Australian consumer decision remains to be
settled before implementation.
