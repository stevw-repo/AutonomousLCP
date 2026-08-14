---
status: accepted
date: 2026-08-10
amended_by:
  - 0013
  - 0015
  - 0016
  - 0017
  - 0050
  - 0055
refined_by:
  - "0078"
  - "0079"
  - "0080"
  - "0084"
  - "0085"
---

# Use register-issued layered identity and immutable Search Records

The greenfield pipeline uses layered identities allocated and owned by the
Management Register. Identity is not calculated from a source URL, filename,
provider path, title, citation, provision number, paragraph number, current
wording, or output position. Those values are aliases, locators, display data,
and evidence.

The identity layers are:

1. **Legal Item ID** — the permanent identity of one legal authority, such as
   an Act, judgment, or publisher-maintained Principles Title;
2. **Official Version ID** — one immutable source-supported official version
   or correction belonging to a Legal Item;
3. **Legal Location ID** — one register-tracked place within a Legal Item, such
   as a provision, Schedule item, judgment location, or maintained Principles
   paragraph;
4. **Search Record ID** — one immutable exact record conforming to the accepted
   serving contract; and
5. **fingerprint** — a cryptographic proof of the exact canonical bytes of an
   object or referenced artifact, independent of its identity.

The register allocates an opaque ID once and never reassigns it. The exact ID
encoding remains a contract detail to settle later. A Search Record ID must
still conform to the accepted `rec_` plus 48-lowercase-hex schema shape, but the
value is issued under this greenfield identity contract rather than derived
from legacy source coordinates.

Legal Items survive ordinary changes to titles, citations, URLs, providers,
and official versions. Each new official consolidation or correction receives
a new Official Version ID. A Legal Location may survive a proved renumbering,
but a split, merge, repeal-and-substitution, or other legally distinct location
creates the new IDs required by the applicable material-specific rulebook.

Search Records are immutable. When the approved Pinecone payload changes—its
`text`, `country`, `jurisdiction`, `type`, `source`, or, under ADRs 0013 and
0050, `authority_note`—the Serving State must select a different exact Search
Record. The register creates a new Search Record ID with a forward predecessor
and change reason when that exact payload has never been issued. If a preserved
record already has the exact required payload and current legal support is
proved, ADR 0055 permits reselecting that record instead of minting a duplicate.
The old selected record remains preserved. Similarity is insufficient.

The internal Record Traceability Lookup is versioned separately. A citation or
provenance change that leaves the serving payload unchanged does not change the
Search Record ID or require a Pinecone rebuild. It creates a new immutable
lookup revision and fingerprint; a later Serving State may bind that revision
while reusing the existing verified indexes. Ask.Legal does not join the lookup
at runtime. ADR 0050 renames and broadens the original warning field:
`authority_note` is required serving metadata, so changing it selects a
different immutable Search Record; a new ID is required unless an exact
previously issued record is validly reselected under ADR 0055. Missing or
mismatched authority-note evidence blocks promotion.

Lineage is explicit and may be one-to-one, one-to-many, or many-to-one. Typed
relationships cover correction, replacement, renumbering, split, merge,
reinstatement, and other material-specific events. They record evidence,
reason, responsible Legal Desk, and effective and observation dates. Lineage
must be acyclic. Withholding and retirement remove selection from a serving
inventory but never erase or reuse identity.

Search Record lineage and Serving State selection history are separate. A
later Serving State may reselect an older exact supported Search Record, but it
records that choice through a new append-only selection or reinstatement event;
it never adds a backward Search Record lineage edge that would create a cycle.

When identity or continuity is ambiguous, the system preserves the competing
evidence and quarantines the decision. Text similarity, matching visible
numbers, or one matching alias cannot resolve it automatically. The responsible
Legal Desk decides legal continuity under its written rulebook. The promotion
worker may only execute the exact accepted IDs, fingerprints, relationships,
and dispositions already bound into the Promotion Manifest.

## Considered options

- derive identities from Distillation source paths and locators — rejected in
  ADR 0010 because those coordinates are mutable and do not prove legal
  continuity;
- use titles, citations, provision numbers, or URLs as IDs — rejected because
  they can change or be reused;
- mutate one Search Record under a stable ID — rejected because historical
  serving states could no longer prove the exact record they used;
- allocate a new Legal Item whenever an Official Version changes — rejected
  because a new consolidation or corrected judgment is normally a new version
  of the same authority; and
- encode traceability-only citation revisions as new Pinecone records — rejected
  because the serving payload has not changed and the separately fingerprinted
  lookup and Serving State already capture the revision. ADR 0013 later removed
  authority-note changes from this exception because the downstream LLM needs
  the exact note in serving metadata.

## Consequences

The Management Register needs immutable schemas for each identity layer,
aliases, evidence bindings, typed lineage relationships, and collision and
cycle validation. Corpus construction must compare exact payloads and legal
support before reusing a Search Record. Promotion reports and manifests must
show every created, reused, replaced, split, merged, withheld, retired, and
reinstated identity.

ADR 0078 later settles Search Record, Record Traceability Lookup revision and
shard ID shapes, serving-payload fingerprint meaning, canonical JSON and
SHA-256 encoding, and the final lookup entry and package fields. Other domain-
object ID encodings and executable schemas remain to be specified before
implementation. ADR
0012 supplies the accepted general legislation continuity rules, ADR 0014 the
accepted case-law rules, and ADRs 0015 and 0017 the accepted Principles rules;
source-specific rulebooks must still identify the exact official or publisher
evidence that satisfies them.
