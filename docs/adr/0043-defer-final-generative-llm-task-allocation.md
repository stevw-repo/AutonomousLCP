---
status: accepted
date: 2026-08-12
amended_by:
  - 0053
  - "0065"
  - "0076"
refined_by:
  - "0080"
  - "0082"
amends:
  - 0031
  - 0039
refines:
  - 0001
  - 0018
  - 0042
depends_on:
  - 0013
  - 0016
---

# Defer final generative-LLM task allocation

The final allocation of legal-processing work between deterministic modules,
task-specific generative-LLM proposals, Legal Desk decisions, and human review
was deferred for one later cross-material design review. At the time, the
previously named case-proposition and later-treatment tasks were candidates
rather than a final implementation-ready task inventory. Hong Kong Gazette
event extraction and other Legal Desk support could also be considered during
that review. ADR 0053 later settles the high-level Hong Kong later-treatment
allocation only; the remaining allocation stays deferred here.

No listed candidate is enabled for implementation merely because it appears in
the design. A future accepted decision must approve the complete task inventory
and each exact task contract before a model provider may be called.

## Boundaries that remain settled

The deferral does not reopen these safety and authority decisions:

- the legal-processing worker's LLM task runner is the only internal component
  that may ever hold generative-LLM credentials or call a provider;
- Watchers first use source-specific checks and fingerprints, and complete
  supported no change stops all affected model work;
- every model call is a named task over exact preserved evidence under a
  versioned schema, prompt, model, settings, and output contract;
- model output is an evidence-bound proposal and must cite exact preserved
  support;
- deterministic validation checks evidence existence, hashes, identities,
  schema, permitted claims, and output completeness before a proposal can be
  considered;
- a generative LLM cannot establish source authenticity, Fact Authority,
  completeness, legal status, identity, continuity, authority note, disposition,
  release eligibility, Approval, retirement, or production action;
- the applicable Source Rulebook, responsible Legal Desk, deterministic
  contract checks, and required human review retain those authorities;
- embedding models remain a separate promotion capability; and
- Ask.Legal's answer LLM remains outside this pipeline.

Acquisition, immutable evidence capture, cryptographic hashing, contract and
schema validation, record identity enforcement, complete release accounting,
Approval validation, and promotion execution remain deterministic control
boundaries. Deferral of legal-analysis task allocation cannot move those
controls into an LLM.

## Candidate tasks at the time of this decision

The design may retain these candidates for the later review:

- `case-proposition-extraction`, later allocated for Hong Kong by ADR 0065;
- `later-treatment-proposal`, later allocated for Hong Kong only by ADR 0053;
  and
- `gazette-event-extraction`, which could propose instrument identity, event
  type, operative clauses, affected locations, dates or conditions, exact
  support, and unresolved facts from preserved Gazette material.

At the time of this decision, this list was illustrative and non-authorizing.
ADR 0053 subsequently allocates the Hong Kong later-treatment task family to a
staged hybrid architecture without enabling a provider call. The remaining
entries still neither require a generative LLM nor prevent a later review from
defining a different bounded task. A Legal Desk is an authority boundary rather
than a synonym for either a human or an LLM.

## Required later decision

The future allocation review must decide, for every proposed task:

- stable task ID and responsible jurisdiction-and-material Legal Desk;
- whether the task is deterministic, generative-LLM-assisted, human-only, or a
  defined combination;
- exact permitted evidence and forbidden inputs;
- claims it may propose and decisions it may never make;
- schema, prompt, model, settings, tools, and network boundary when applicable;
- deterministic preconditions and post-validation;
- exact evidence-citation and unresolved-fact requirements;
- evaluation corpus, thresholds, sampling, regression, and revalidation;
- human or Legal Desk review and automatic-acceptance conditions, if any;
- result reuse, invalidation, retention, security, cost, and failure behavior;
  and
- which Source Rulebook Package, conformance cases, and application build
  attest the task.

The review must update the canonical module map, relevant Source Rulebooks,
evaluation requirements, security boundaries, and handoff documentation
together. Until then, the exact task list and deterministic-versus-LLM split are
not implementation-ready.

ADR 0053 later settles one narrow exception: Hong Kong Cases later-treatment
screening uses staged whole-judgment LLM discovery, candidate-level LLM
analysis, deterministic validation, and Legal Desk decision. Its exact runtime
task contracts still require the task-enablement work listed there. The
allocation of Hong Kong Case Proposition extraction is later settled by ADR
0065 as two-pass staged hybrid analysis. ADR 0076 later settles the Hong Kong
Regulatory Materials high-level allocation through change-gated update-
analysis, update-challenge, record-analysis, and record-challenge proposal
tasks. Decision 7 of proposed ADR 0099 later selects Gazette-event and
Reconstruction Plan decision/challenge tasks and makes all other unallocated
tasks deterministic.

## Consequences

ADR 0039 remains authoritative for the sole LLM gateway, forbidden decisions,
and task-admission requirements. Decision 7 of proposed ADR 0099 supersedes its
proposal-only wording with bounded semantic-decision authority. Its two-task allocation
and its statement that Hong Kong Legislation has no generative task are amended
from final decisions to provisional candidates. ADR 0031's change gate remains
mandatory but authorizes no task by itself.

This decision authorizes documentation only. It does not authorize
implementation, source access, LLM or embedding-provider calls, release
publication, Pinecone mutation, promotion, or deployment.
