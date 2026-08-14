---
status: accepted
date: 2026-08-14
refines:
  - "0004"
  - "0008"
  - "0009"
  - "0011"
  - "0013"
  - "0016"
  - "0050"
depends_on:
  - "0003"
  - "0006"
refined_by:
  - "0079"
  - "0080"
  - "0081"
  - "0084"
  - "0085"
  - "0087"
---

# Define the Serving Record and Record Traceability Lookup encoding

## Decision

The shared serving boundary uses two separate immutable contracts:

1. one small **Serving Record** containing exactly the ID and six strings that
   Pinecone and Ask.Legal need; and
2. one complete **Record Traceability Lookup Revision** containing compact
   internal pointers from every selected Search Record to its legal identities,
   release ownership, decisions, and preserved evidence.

The Serving Record is query data. The lookup is validation and audit data. The
lookup never becomes a seventh metadata field or an ordinary query-time join.

This ADR fixes the normative encoding. Executable JSON Schema files, validators,
fixtures, storage adapters, and production data remain later implementation
artifacts.

## Serving Record JSON

One Serving Record has exactly this outer shape:

```json
{
  "id": "rec_0123456789abcdef0123456789abcdef0123456789abcdef",
  "metadata": {
    "text": "Complete independently usable legal content",
    "country": "Registered profile value",
    "jurisdiction": "Registered profile value",
    "type": "Registered profile value",
    "source": "Registered profile value",
    "authority_note": "None"
  }
}
```

The common contract requires:

| Field | Exact common rule |
|---|---|
| `id` | One register-issued string matching `^rec_[0-9a-f]{48}$` |
| `metadata` | One object containing exactly the six named properties below |
| `metadata.text` | Non-empty string produced by the admitted material-specific renderer |
| `metadata.country` | Non-empty string allowed by the exact registered profile |
| `metadata.jurisdiction` | Non-empty string allowed by the exact registered profile |
| `metadata.type` | Non-empty string allowed by the exact registered profile |
| `metadata.source` | Non-empty string allowed by the exact registered profile |
| `metadata.authority_note` | Exact `"None"` or one valid controlled rendering under ADR 0050 |

Every property is required. Additional top-level or metadata properties,
`null`, numbers, booleans, arrays, nested metadata, empty required strings,
invalid Unicode, and an omitted field are rejected. Material-specific profile
schemas may narrow values, templates, and byte limits but may not change the
outer shape or add fields.

The contract uses JSON Schema Draft 2020-12 with closed objects. Each immutable
registered profile binds its schema identity, version, canonical schema
fingerprint, permitted constants or enums, renderer contract, and exact
metadata-byte ceiling. The ceiling must be no greater than the provider limit
proved for the admitted Pinecone API and configuration; a current provider
limit is evidence for a profile, not a timeless substitute for this contract.

The Serving Record does not contain a vector, embedding fingerprint, schema
identifier, date, provenance, evidence, release, grouping, citation, or lookup
field. The promotion adapter attaches the separately approved vector and sends
the exact `id` and `metadata` to Pinecone. Embedding continues to use
`metadata.text` only.

## Canonical bytes and fingerprints

All contract JSON uses the JSON Canonicalization Scheme in RFC 8785:

- input must be valid I-JSON with unique property names and valid Unicode;
- object properties are recursively sorted under JCS rules;
- array order is preserved;
- no insignificant whitespace or byte-order mark is emitted;
- strings are not Unicode-normalized or otherwise rewritten after validation;
  and
- the canonical result is encoded as UTF-8.

The executable conformance suite must include the RFC 8785 vectors and verified
errata, including rejection of invalid Unicode and negative-zero input. The
current contracts use no floating-point legal facts; counts are non-negative
safe integers.

Fingerprints use SHA-256 and the exact lowercase representation
`sha256:<64-lowercase-hex>`.

The following meanings are fixed:

```text
serving_payload_fingerprint = SHA-256(JCS(metadata))
authority_note_fingerprint = SHA-256(UTF-8(metadata.authority_note))
json_artifact_fingerprint = SHA-256(exact canonical JSON artifact bytes)
binary_artifact_fingerprint = SHA-256(exact preserved artifact bytes)
```

The SHA-256 result is encoded with the `sha256:` prefix after hashing. The
Serving Record ID is deliberately excluded from `serving_payload_fingerprint`:
identity and content proof remain separate. In the Desired-State Inventory,
`content_fingerprint` means this exact `serving_payload_fingerprint` unless a
future versioned inventory contract names another fingerprint explicitly.

Equal fingerprints are never accepted as proof of equal content without exact
canonical-byte comparison at registration and collision checking. Different
bytes with one claimed digest are a critical integrity failure.

## Record Traceability Entry

Every selected Search Record has exactly one entry with the following closed
shape. Array fields are always present, even when their valid value is empty.

```json
{
  "search_record_id": "rec_0123456789abcdef0123456789abcdef0123456789abcdef",
  "serving_payload_fingerprint": "sha256:<64-lowercase-hex>",
  "serving_record_profile_id": "<immutable registered profile ID>",
  "legal_item_id": "<registered Legal Item ID>",
  "official_version_ids": ["<registered Official Version ID>"],
  "legal_location_ids": ["<registered Legal Location ID>"],
  "release_scope_id": "<registered Release Scope ID>",
  "corpus_release_id": "<immutable Corpus Release ID>",
  "evidence_refs": [
    {
      "ref_type": "<registered evidence-reference type>",
      "ref_id": "<immutable evidence object ID>",
      "fingerprint": "sha256:<64-lowercase-hex>"
    }
  ],
  "authority_note_evidence": {
    "rendered_value_fingerprint": "sha256:<64-lowercase-hex>",
    "decision_ref": {
      "ref_type": "<registered authority-note-decision reference type>",
      "ref_id": "<immutable decision ID>",
      "fingerprint": "sha256:<64-lowercase-hex>"
    },
    "supporting_evidence_refs": []
  },
  "grouping_ids": [],
  "display_citation_ids": []
}
```

`official_version_ids` and `legal_location_ids` are non-empty. They are arrays
because one record may have several exact supporting locations or preserved
version bindings without changing the six-field payload. `evidence_refs` is
non-empty and points to the minimum immutable objects needed to reach the
source material and accepted construction decision. Reference types come from
one closed versioned registry; an unknown type is invalid.

`authority_note_evidence` is required even when the rendered value is
`"None"`. In that case the decision still proves why no LLM-facing note was
selected, and `supporting_evidence_refs` may be empty. A real note requires all
structured supporting evidence selected by its material-specific renderer.
The lookup stores the note's fingerprint, not another mutable copy of the note.

`grouping_ids` and `display_citation_ids` hold only approved internal pointers.
They do not determine legal identity, record ownership, or query correctness.
A correction limited to those pointers or another lookup-only field creates a
new lookup revision but not a new Search Record.

Every array is duplicate-free and sorted by its complete canonical value.
Evidence-reference arrays sort by `ref_type`, then `ref_id`, then
`fingerprint`. Identity arrays sort by their ASCII identifiers. Array order
therefore carries no hidden meaning and repeated construction is byte-exact.

## Scalable complete lookup revision

A lookup revision is a strict package rather than one unbounded monolithic
map. It contains:

- one canonical `manifest.json`; and
- one or more explicitly declared Release-Scope shards under `entries/`.

The manifest has exactly these fields:

```json
{
  "schema_id": "asklegal.record-traceability-lookup-manifest",
  "schema_version": "1.0.0",
  "manifest_schema_fingerprint": "sha256:<64-lowercase-hex>",
  "lookup_revision_id": "rtl_0123456789abcdef0123456789abcdef0123456789abcdef",
  "entry_schema_id": "asklegal.record-traceability-entry",
  "entry_schema_version": "1.0.0",
  "entry_schema_fingerprint": "sha256:<64-lowercase-hex>",
  "total_entry_count": 0,
  "serving_record_profiles": [],
  "shards": []
}
```

`lookup_revision_id` is register-issued and matches
`^rtl_[0-9a-f]{48}$`. `serving_record_profiles` contains each exact profile ID,
schema version, and schema fingerprint used by any entry. It is sorted by
profile ID and contains no unused or duplicate profile.

Each `serving_record_profiles` member has exactly:

```json
{
  "serving_record_profile_id": "<immutable registered profile ID>",
  "schema_version": "<immutable schema version>",
  "schema_fingerprint": "sha256:<64-lowercase-hex>"
}
```

There is exactly one shard for every Release Scope selected into the target,
including a zero-entry shard for a proved-empty scope. A shard descriptor has:

```json
{
  "release_scope_id": "<registered Release Scope ID>",
  "corpus_release_id": "<selected Corpus Release ID>",
  "lookup_shard_id": "rts_0123456789abcdef0123456789abcdef0123456789abcdef",
  "path": "entries/rts_0123456789abcdef0123456789abcdef0123456789abcdef.ndjson",
  "media_type": "application/x-ndjson",
  "entry_count": 0,
  "artifact_fingerprint": "sha256:<64-lowercase-hex>"
}
```

Shard IDs match `^rts_[0-9a-f]{48}$`. Descriptors sort by
`release_scope_id`; every path is exact, relative, normalized, manifest-listed,
and derived only from its shard ID. Directory discovery, globs, ranges,
symlinks, aliases, absolute paths, and undeclared files are forbidden.

Each non-empty shard is newline-delimited canonical JSON: one JCS-canonical
Record Traceability Entry per line, sorted by `search_record_id`, with one LF
byte after every entry including the last. It has no blank line, carriage
return, byte-order mark, comment, header, or footer. The shard fingerprint is
SHA-256 over those exact bytes. A zero-entry shard is the zero-byte file and
uses the SHA-256 digest of zero bytes.

The manifest contains no fingerprint of itself. The externally recorded lookup
revision fingerprint is SHA-256 over the exact JCS-canonical `manifest.json`
bytes. Because the manifest binds every shard fingerprint, profile, schema,
scope, release, count, and path, that one root transitively binds the complete
lookup without a circular self-reference.

`manifest_schema_fingerprint` identifies the separate immutable JSON Schema
artifact; it is not the fingerprint of this manifest instance.
`total_entry_count` is a non-negative safe integer and must equal both the sum
of all shard counts and the flattened Desired-State Inventory record count.

Release-Scope sharding permits an unchanged shard to be reused in a later
lookup revision. A traceability-only change rebuilds only the affected shard
and root manifest. It does not mutate an old shard or lookup revision and does
not require new vectors when the six-field Serving Records remain exact.

## Complete validation

Before promotion, deterministic validation proves at least:

1. the manifest, entry schema, every profile schema, and every shard have their
   exact registered identities, versions, paths, media types, counts, and
   fingerprints;
2. every Desired-State Inventory Search Record has exactly one entry and every
   entry has exactly one matching desired record;
3. no Search Record ID is duplicated within or across shards;
4. entry scope, Corpus Release, profile, and serving-payload fingerprint agree
   exactly with the Corpus Release and flattened Desired-State Inventory;
5. every legal identity, decision, evidence reference, and fingerprint exists
   and agrees with the Management Register and Evidence Vault;
6. `rendered_value_fingerprint` equals SHA-256 over the exact selected
   `metadata.authority_note`, and the accepted decision and evidence prove that
   value under ADR 0050;
7. arrays, shards, profiles, and entries are complete, unique, and in canonical
   order; and
8. two isolated clean constructions from the same inputs produce identical
   records, shards, manifest, counts, and fingerprints.

Missing, duplicate, orphaned, mismatched, unsorted, undeclared, stale,
non-canonical, or unsupported content blocks the candidate. Aggregate counts
cannot compensate for one bad record. The promotion worker consumes only the
already frozen validated lookup revision and cannot repair or regenerate it.

## Runtime and revision behavior

Ask.Legal continues to receive only the record ID and six metadata strings.
Temporary lookup unavailability after activation does not stop ordinary search.
Reviewers and investigations resolve the Serving State ID to the exact lookup
revision and then to the applicable scope shard and entry.

A lookup-only correction creates a new immutable lookup revision and, when
needed, a new Serving State Definition binding it while reusing exact verified
indexes. A change to any of the six metadata strings changes the serving
payload and follows Search Record identity and lineage rules instead.

## Why this approach

- A flat Pinecone record keeps the live query path small and compatible.
- JCS removes programming-language property-order and whitespace differences.
- A named SHA-256 encoding prevents bare-digest ambiguity.
- Release-Scope shards avoid rebuilding one enormous lookup for an unrelated
  citation or provenance correction.
- The complete root manifest still proves that no record or scope disappeared.
- Keeping full evidence outside the lookup avoids creating another evidence
  store or leaking internal material into the downstream LLM.

## Consequences and authorization boundary

The open Serving Record and Record Traceability Lookup encoding decision is
settled. Exact executable schemas and fixtures must implement this ADR without
adding fields or weakening completeness. Provider-specific numerical limits
remain evidence-derived registered-profile values because they must be tested
with the selected Pinecone API, embedding workflow, and representative records.

This ADR authorizes documentation only. It does not authorize schema or
application implementation, source or corpus acquisition, embedding or model
calls, lookup publication, Pinecone mutation, promotion, Azure changes,
deployment, commit, push, or another remote action.

Primary references: [RFC 8785 JSON Canonicalization Scheme](https://www.rfc-editor.org/rfc/rfc8785.html),
[RFC 8785 verified errata](https://www.rfc-editor.org/errata/rfc8785),
[JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12), and
[Pinecone upsert limits](https://docs.pinecone.io/guides/index-data/upsert-data).
