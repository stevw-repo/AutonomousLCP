---
status: accepted
date: 2026-08-16
refines:
  - "0001"
  - "0006"
  - "0007"
  - "0009"
  - "0088"
  - "0091"
  - "0093"
  - "0094"
  - "0096"
---

# Close the M2–M7 implementation-facing design

The user explicitly accepted this reconciled ADR and its six protocols after
settling all seven material choices, including Decision 7's bounded semantic-
decision authority and deterministic/human evaluation boundary.

## Decision

Accept the six implementation-facing protocol specifications:

1. `M2_DOMAIN_AND_REGISTER_PROTOCOL.md`;
2. `M3_APPLICATION_INTERFACE_PROTOCOL.md`;
3. `M4_ACQUISITION_AND_EVIDENCE_PROTOCOL.md`;
4. `M5_EXECUTABLE_LEGAL_DESK_PACKAGE_PROTOCOL.md`;
5. `M6_REVIEW_AND_PROMOTION_PROTOCOL.md`; and
6. `M7_END_TO_END_CONFORMANCE_PLAN.md`.

Together they close the twelve gaps in the 2026-08-16 build-readiness audit.
They fix command/effect contracts, aggregate and run lifecycles, application
interfaces, manifest-preparation ownership, evidence and connector protocols,
executable rulebook packages, governance, provider-neutral execution,
promotion/routing/coverage behavior, and the local end-to-end acceptance plan.

The control plane prepares the complete effect-free proposal package through
pure corpus/promotion services. The Review API records one exact human
decision. The promotion worker consumes only the exact approved manifest and
owns every production embedding, backup, Pinecone, and routing effect.

## Human-governance decision

Decision 2 uses one `PipelineAdministrator` human role, assignable to multiple
named people, for Review and Control actions. A decision requires a delegated
named-human identity, current permission, non-empty reason, and immutable audit
evidence. Ordinary production MFA applies, but there is no separate step-up
freshness rule, independent Approval TTL, or absence-cover role. Approval is
single-use and remains subject to revocation, current permission, the bound
manifest's validity, and every exact invalidation predicate. Application and
workload identities remain separate.

## Quarantine and review-timing decision

Decision 3 uses severity, named administrator assignment, and immediate
notification for urgent release-blocking or potentially misleading current-law
issues. It defines no fixed one-, five-, or ten-business-day SLA. An
administrator may set an explicit due time when useful. Elapsed time never
releases or resolves material; the exact block, withholding, or evidence-backed
carry-forward remains until a recorded decision changes it.

## Provider, routing, naming, coverage, and model-allocation decisions

Azure OpenAI models sold by Azure through Microsoft Foundry are the production
service boundary for both generative proposals and embeddings. Only stateless
inference APIs are admitted. Exact model deployments, versions, dimensions,
prompts, thresholds, limits, and expiry remain immutable evaluation/admission
profile values; they are deliberately not floating architecture constants.
The user selected this provider family in decision 1 to match the existing
Ask.Legal Backend. That backend's Cloudflare gateway and API-key transport are
not part of the provider decision.

Decision 7 completes the allocation. In addition to the eight previously
accepted Case, later-treatment, and HKEX Regulatory semantic stages, it selects
change-gated evidence-bound analysis and challenge for Gazette-event extraction,
decision and challenge for structured Hong Kong Reconstruction Plans. An
admitted primary result that survives challenge and deterministic validation is
the ordinary decision for the exact semantic fields named by its task contract.
Offline evaluation instead uses deterministic checks and acceptance
calculations against human-adjudicated reference truth. All model stages remain
disabled pending executable contracts and admission.

Every other task without an accepted generative allocation defaults to
`NO_GENERATIVE_LLM` for now, including Principles transformations and work for
new jurisdictions or material families. A future generative allocation requires
a new ADR and complete task/evaluation/admission package.

Decision 7 gives admitted LLMs authority to decide bounded semantic fields and
ordinary results where deterministic rules perform poorly. Deterministic code
retains checks, tests, validation, evidence binding, completeness, identity,
final rendering/execution, Approval, and effect enforcement. Unresolved,
unsupported, out-of-contract, or exceptional results enter the exact Legal
Desk/human path. A model never defines reference truth or its own admission
gate.

Decision 5 fixes Pinecone index names as
`asklegal-<env3>-<jur3>-<YYYYMMDD>-<state12>`, remain at most 40 characters,
and must also satisfy Pinecone's combined index/project-ID DNS length.

Decision 4 selects a restricted Ask.Legal App Service `candidate` slot, distinct
from the existing development slot, and a complete
non-sticky routing-generation setting, manually authorized standard slot swap,
exact configuration preflight and platform warm-up,
generation pinning per request, post-cutover verification, and reverse-swap
rollback. Direct production setting edits, auto-swap, and mixed-generation
traffic are forbidden.

Decision 6 requires one complete immutable Coverage Status Manifest for every
routing generation. It accounts for every expected legal scope, status, last
verification time, known gaps or failures, and user-facing warning code. The
routing generation binds the exact SHA-256 fingerprint and a protected
immutable Azure download reference. Ask.Legal retrieves it through authenticated
protected storage, verifies the fingerprint, and caches the verified bytes by
routing generation. Activation blocks on a missing, incomplete, or mismatched
manifest. A temporary store failure may use only the exact verified cached copy;
without either valid source Ask.Legal shows a global `coverage status
unavailable` warning and records the failure. Decision 6 deliberately adds no
dedicated signing identity, signing keys, rotation, or signature-validation
lifecycle.

Coverage Status Manifest version 1.1.0 removes the former
`signature_policy_state` field and adds the selected per-scope verification,
gap, Quarantine, source-failure, and warning fields. Approval and its lifecycle
are likewise reconciled at version 1.1.0 with the accepted no-independent-TTL
decision.

The choices reflect current official documentation for
[Azure OpenAI embeddings](https://learn.microsoft.com/en-us/azure/foundry/openai/tutorials/embeddings),
[Azure OpenAI v1 and Entra authentication](https://learn.microsoft.com/en-us/azure/foundry/openai/api-version-lifecycle),
[Azure model data processing](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy),
[App Service slot behavior](https://learn.microsoft.com/en-us/azure/app-service/deploy-staging-slots),
and [Pinecone index-name constraints](https://docs.pinecone.io/troubleshooting/restrictions-on-index-names).

## Design closure versus admission evidence

With this ADR accepted after the user decisions, the implementation-facing
engineering design is complete even though production cannot yet be
admitted. Measured capacity, regions, redundancy exceptions, recovery and
retention values, WAF limits, service levels, budget thresholds, exact deployed
models, real source inventories, source rights, real fixtures, and adjudicated
evaluations are mandatory versioned profiles or evidence packages. Their
absence keeps the relevant capability disabled; it does not leave an
architectural behavior undefined or authorize an implicit default.

Real jurisdiction packages remain individually `NOT_READY` until their exact
evidence gates pass. M7 uses only the reserved local synthetic package and makes
no production or legal-readiness claim.

## Consequences

- M2–M7 implementation may proceed milestone by
  milestone under separate explicit authorization without another general
  architecture-design phase.
- The current architecture checkpoint must be revised and re-proved before M3
  runtime implementation to give proposal preparation to the control plane.
- Schema/code implementation will add versioned machine contracts for these
  protocols; documentation does not itself activate a capability.
- Evidence-derived or organization-owned values must be configured and proved
  before their capability is admitted; missing values always fail closed.
- Any later change to the five-application trust model, one-human Approval,
  provider service boundary, production routing method, or complete-coverage
  behavior requires a new ADR.

This ADR authorizes design only. It grants no implementation, source access,
provider call, Azure operation, Pinecone operation, deployment, or production
effect.
