---
status: accepted
date: 2026-08-10
amended_by: 0013
---

# Do not use Distillation's source-derived identity algorithm

The greenfield pipeline will not use Ask.Legal Distillation's source-derived
record-identity approach as its identity model. It will not make a raw
publication path, AustLII path, Title number, source paragraph number,
source-native locator, node identifier, or positional split-child index the
authoritative identity of a Legal Item, Official Version, Legal Location, or
Search Record.

Those values remain useful evidence and aliases, but they can change when a
source moves, renumbers material, changes provider, restructures a document, or
is segmented differently. A deterministic hash of mutable source coordinates
would reproduce the same technical ID only while those coordinates remained
stable; it would not by itself prove continuing legal identity.

Existing Distillation `rec_` values do not become authoritative greenfield
identities and are not automatically carried forward. They may be preserved as
non-authoritative legacy references when evidence or reconciliation requires
them, but no greenfield identity decision may be inferred from them.

This decision concerns identity semantics only. It did not reverse ADR 0008's
then-current five-field serving envelope. ADR 0013 later added required
metadata `authority_note`; the rejection of source-derived identity remains unchanged.
The greenfield system supplies conforming record IDs under its own identity
contract.

## Considered options

- copy Distillation's profile-specific structural hashes — rejected because
  their stability depends on source paths, locators, numbering, grouping, and
  split positions;
- adapt the hashes as the main logical Search Record IDs — rejected at the
  user's direction because this would retain the same source-derived identity
  premise; and
- preserve Distillation IDs automatically during greenfield registration —
  rejected because an old technical identifier is not evidence that two legal
  objects are the same.

## Consequences

The target identity contract must be designed independently around permanent
register-owned identities, immutable exact versions and records, explicit
evidence, and predecessor relationships. Source-system identifiers are aliases
and matching evidence only. ADR 0011 supplies the accepted layered identity and
Search Record revision model. Exact ID formats and material-specific continuity
rules remain open.
