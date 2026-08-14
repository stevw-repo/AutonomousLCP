---
status: accepted
date: 2026-08-11
amended_by:
  - 0050
refined_by:
  - "0078"
  - "0087"
amends:
  - 0008
  - 0009
  - 0011
  - 0013
---

# Keep the Record Traceability Lookup outside the Ask.Legal query path

The object previously called the **Adjacent Query Lookup** is renamed the
**Record Traceability Lookup**. The new name describes its actual purpose: it
is an internal compact map from each Search Record ID back to the identities,
evidence, and release that produced it.

It is not a second search database. It does not contain the source files, and
Ask.Legal does not read or join it during an ordinary search. The downstream
LLM continues to receive only the six Pinecone metadata fields accepted in ADR
0013 as amended by ADR 0050. In particular, the LLM-facing authority note
remains in `metadata.authority_note`.

## Information boundary

The authoritative information remains in two places:

- the **Management Register** owns Legal Item, Official Version, Legal
  Location, Search Record, lineage, decision, release, and serving history; and
- the **Evidence Vault** stores the exact Source Snapshots and other preserved
  files that prove those facts.

The Record Traceability Lookup stores only compact identifiers and
fingerprints needed to follow that chain quickly. For each Search Record it
identifies at least:

- the Search Record ID and exact serving-payload fingerprint;
- its Legal Item, Official Version, and supporting Legal Location identities;
- its owning Release Scope and Corpus Release;
- the Source Snapshot or evidence references needed to locate the original
  material;
- its structured authority-note-evidence reference and the fingerprint of the
  exact rendered `metadata.authority_note`; and
- any approved grouping or display-citation identifiers useful for internal
  review and investigation.

Those are responsibilities, not the final JSON field names. The exact schema
encoding remains a contract detail.

## Validation and runtime behavior

Corpus construction produces an immutable fingerprinted lookup revision for
the candidate records. Before promotion, validation proves that:

- every Search Record in the Desired-State Inventory has exactly one matching
  lookup entry;
- no duplicate or orphaned lookup entry exists;
- record IDs, payload fingerprints, ownership, and evidence references agree
  with the Management Register and Corpus Releases; and
- the authority-note evidence and rendered-note fingerprint agree exactly with
  `metadata.authority_note`.

A missing, duplicate, orphaned, or mismatched entry blocks promotion. This is a
build-and-approval validation rule, not an Ask.Legal runtime join.

After activation:

- Ask.Legal retrieves the Pinecone record and passes its six metadata fields to
  the downstream LLM without consulting this lookup;
- temporary lookup unavailability does not stop an ordinary Ask.Legal search;
- the lookup remains available to reviewers, operators, investigations, and
  audits; and
- an answer's recorded Serving State ID identifies the exact lookup revision
  that was validated with that state.

The lookup remains sealed into the Desired-State Inventory, Promotion Manifest,
and Serving State Definition as traceability evidence, but it is not part of
the live Query Contract and no application query path must join it.

## Revisions

A citation, grouping, provenance, or evidence-reference correction that leaves
all six serving metadata fields unchanged does not create a new Search Record,
embedding, or Pinecone rebuild. It creates a new immutable Record Traceability
Lookup revision. A new Serving State Definition may bind that revision while
reusing the existing verified Pinecone indexes. The lookup already bound to an
older Serving State remains immutable so historical answers retain their exact
original audit context.

Changing `metadata.authority_note` is not a lookup-only correction. Under ADRs
0013 and 0050 it changes the serving payload and therefore creates a new Search
Record.

## Consequences

Ask.Legal requires no new runtime service or lookup integration for this
artifact. Runtime compatibility testing remains focused on the six-field
Pinecone metadata contract, especially delivery of `metadata.authority_note`.

ADR 0078 later fixes the normative versioned lookup entry, Release-Scope shard,
root-manifest, canonical fingerprint, and one-to-one promotion-validation
encoding. Executable schemas, fixtures, and validators must implement it. The
lookup must be recoverable with the Management Register and Evidence Vault, but
its temporary unavailability is an audit-system incident rather than a live
search outage.
