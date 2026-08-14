---
status: accepted
date: 2026-08-10
refined_by:
  - "0078"
---

# Make Desired-State Inventories complete and flattened

A Desired-State Inventory is one sealed immutable complete composition for one
logical Pinecone target. It records the desired state in two matching views.

The scope view identifies the versioned Release Scope registry and selects
exactly one Corpus Release for every required scope. An unchanged scope reuses
its existing release. A valid proved-empty release is selected normally and
contributes zero Search Records.

The flattened target view persists every expected Search Record ID, content
fingerprint, owning Release Scope, and owning Corpus Release. It is sorted and
fingerprinted deterministically. The full record content remains in the selected
Corpus Releases; the flattened view is the exact target-wide inventory and
integrity map rather than a second copy of the corpus.

The two views must agree exactly. Validation fails if:

- a required Release Scope is missing or selected more than once;
- Release Scopes overlap or claim the same Search Record;
- a Search Record ID appears more than once, even with identical content;
- a content fingerprint differs between the release and flattened views;
- either view contains a record absent from the other;
- the flattened inventory is not in its canonical order or its aggregate
  fingerprint is wrong.

When the valid inventory is compared with the current production target, an
existing record with no explained owner and disposition blocks promotion until
it is reconciled.

The Desired-State Inventory is sealed before approval and is included by exact
fingerprint in the Promotion Manifest. It proves what one complete target should
contain, but it is not Approval and does not authorize building, mutating, or
retiring anything in Pinecone.

## Considered options

- release references without a flattened record inventory — rejected because
  they do not independently expose target-wide collisions, omissions, or the
  exact inventory to verify after promotion;
- a flattened record list without release selections — rejected because it
  loses scope completeness, ownership, and release lineage;
- a delta containing only changed records — rejected because safe retirement
  and complete verification require the whole desired target; and
- recompute the flattened view during execution — rejected because a changed
  algorithm or release-selection result could alter the approved target.

## Consequences

The inventory duplicates a small amount of record identity and fingerprint
metadata but not the complete record payload. The system needs a canonical sort
and fingerprint contract, a versioned registry of required Release Scopes,
collision checks, and exact whole-target comparison before and after promotion.

ADR 0005 defines how the inventory accounts for a required scope affected by
source failure or Quarantine without silently retiring its records or
misrepresenting stale material as current.
