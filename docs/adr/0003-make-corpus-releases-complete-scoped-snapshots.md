---
status: accepted
date: 2026-08-10
---

# Make Corpus Releases complete scoped snapshots

A Corpus Release is a complete immutable snapshot of one explicitly declared
Release Scope at one observation cutoff. It is not a delta, change list, or
arbitrary processing batch.

A Release Scope is a stable, versioned, non-overlapping ownership boundary with
one responsible Legal Desk. The scope contract defines the jurisdiction,
material family and any narrower partition, required source coverage, and
completeness rules. Every Search Record belongs to exactly one Release Scope
within a serving target.

Each Corpus Release contains:

- its stable Release Scope identity and scope-contract version;
- its observation cutoff and source-coverage evidence;
- zero or more validated Search Records and their fingerprints;
- completeness, integrity, validation, and record-count evidence; and
- the predecessor release for the same scope, when one exists.

A zero-record release is valid only when the evidence proves that the complete
scope genuinely has no supported current Search Records or a complete
evidence-backed Withholding Release accounts for every non-searchable item and
disposition. A source failure, incomplete reconciliation, Quarantine, or
Coverage Gap without those dispositions cannot be represented as an empty
release. See ADR 0005.

If a Release Scope is unchanged, a later Desired-State Inventory references its
existing release rather than rebuilding or copying it. A later release declares
its predecessor but does not authorize or change production merely by existing.
It replaces the predecessor for serving only when selected by a complete
Desired-State Inventory and promoted under a valid Approval.

## Considered options

- delta releases containing only additions and changes — rejected because they
  cannot independently prove the complete owned state and make omission and
  retirement ambiguous;
- arbitrary processing batches — rejected because batch boundaries do not
  establish stable ownership or completeness;
- one global Corpus Release for the entire legal database — rejected because
  it would couple unrelated desks and jurisdictions and rebuild unchanged
  scopes unnecessarily; and
- prohibit empty releases — rejected because a valid complete scope can
  legitimately contain no current searchable records.

## Consequences

Changed releases logically repeat unchanged records within their scope, though
the Evidence Vault may deduplicate storage without changing artifact identity.
The system needs a versioned registry of required non-overlapping Release
Scopes, explicit completeness checks, stable predecessor links, and a clear
distinction between a proved empty scope and unavailable or uncertain work.

The Desired-State Inventory must next define how selected scoped releases
account for every required scope and compose into the complete expected content
of a Pinecone Index.
