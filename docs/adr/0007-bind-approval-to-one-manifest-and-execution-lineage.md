---
status: accepted
date: 2026-08-10
refined_by:
  - "0087"
  - "0096"
  - "0099"
---

# Bind Approval to one manifest and execution lineage

Decision 2 of the ADR 0099 closure review removes the independent Approval TTL,
separate human roles, action-specific step-up, and absence-cover construct from
this earlier design. The immutable manifest binding, revocation, current named-
human permission, predicate invalidation, and one-lineage consumption remain.

Approval is a separate immutable authenticated human decision bound to exactly
one Promotion Manifest identity and fingerprint and, once execution begins, one
execution lineage.

The decision record contains:

- its identity and schema version;
- the exact Promotion Manifest identity and fingerprint;
- approve or reject;
- the authenticated reviewer identity and evidence that the reviewer currently
  holds the required authority;
- decision time and reason or comment;
- valid-from time, with no independent Approval expiry;
- the expected base Serving State; and
- the objective conditions that must remain true before execution.

One authorized human approves or rejects the whole manifest. Service accounts
cannot approve, and the reviewer cannot alter the manifest while deciding.
Rejection is terminal for that manifest. Any correction creates a new manifest
and decision rather than changing the rejection or partly approving the
package.

Revocation, automatic invalidation, and consumption are separate
append-only lifecycle events. They preserve rather than rewrite the original
decision. Approval may be revoked before production execution begins. Once
execution starts, a named `PipelineAdministrator` may stop or recover the run
but cannot broaden or replace the Approval.

Execution consumes the Approval for one recorded lineage. A retry may resume
only in that lineage, from a manifest-permitted checkpoint, with identical
input fingerprints and while every validity condition remains true. Approval
cannot be reused for an unrelated run.

Immediately before the first production action, the promotion worker verifies:

- the manifest identity and fingerprint;
- current reviewer authority;
- current `PipelineAdministrator` permission and absence of rejection or revocation;
- the base Serving State and current target inventory;
- the Routing Configuration and non-secret settings;
- recovery readiness; and
- every other manifest invalidation predicate.

Any failed check makes the Approval unusable and records the reason. A changed
input, target, setting, step, retry basis, checkpoint, or rollback state needs a
new Promotion Manifest and Approval.

## Considered options

- store approval as a mutable flag on the manifest — rejected because later
  changes could obscure the original human decision and its history;
- use a reusable approval token — rejected because it could authorize a
  different package or execution;
- allow service-account approval — rejected because preparation or execution
  identity must not substitute for human authorization; and
- permit partial approval — rejected because the resulting Serving State would
  differ from the complete reviewed package.

## Consequences

The system needs authenticated named-human identities, the single
`PipelineAdministrator` role, canonical decision records, append-only lifecycle
events, one-lineage consumption, and an objective pre-execution validity
evaluator. Multiple named people may receive the same role. There is no
independent Approval validity duration or absence-cover mechanism.
