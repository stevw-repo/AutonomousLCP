# AskLegal Legal Database Pipeline

This repository is the greenfield modular monorepo for Ask.Legal's autonomous
legal-database pipeline.

The intended system checks official and approved publisher sources, preserves
exact evidence,
assesses supported legal status, prepares validated search records, obtains one
human approval for the complete frozen update, and keeps Ask.Legal's searchable
legal corpus aligned with that approval.

## Current status

**Design only. No application code or technical stack has been selected.**

The repository currently contains the initial overall design and durable
briefing files. Documentation does not authorize source access, AI or embedding
calls, corpus publication, Pinecone access, pruning, backup mutation,
deployment, routing changes, or any other remote action.

## Start here

1. [`AGENTS.md`](AGENTS.md) — mandatory operating instructions.
2. [`docs/agent/CONTEXT.md`](docs/agent/CONTEXT.md) — stable domain language.
3. [`docs/agent/DECISIONS.md`](docs/agent/DECISIONS.md) — settled decisions.
4. [`docs/agent/WORKING_STATE.md`](docs/agent/WORKING_STATE.md) — current
   objective and exact next step.
5. [`docs/adr/0001-use-a-modular-monorepo.md`](docs/adr/0001-use-a-modular-monorepo.md)
   — accepted repository architecture.
6. [`docs/adr/0002-use-replacement-pinecone-indexes.md`](docs/adr/0002-use-replacement-pinecone-indexes.md)
   — accepted serving-target and cutover architecture.
7. [`docs/adr/0003-make-corpus-releases-complete-scoped-snapshots.md`](docs/adr/0003-make-corpus-releases-complete-scoped-snapshots.md)
   — accepted Corpus Release boundary.
8. [`docs/adr/0004-make-desired-state-inventories-complete-and-flattened.md`](docs/adr/0004-make-desired-state-inventories-complete-and-flattened.md)
   — accepted Desired-State Inventory boundary.
9. [`docs/adr/0005-handle-unavailable-release-scopes-explicitly.md`](docs/adr/0005-handle-unavailable-release-scopes-explicitly.md)
   — accepted unavailable-scope behavior.
10. [`docs/adr/0006-make-the-promotion-manifest-the-sole-execution-envelope.md`](docs/adr/0006-make-the-promotion-manifest-the-sole-execution-envelope.md)
    — accepted approval and execution envelope.
11. [`docs/adr/0007-bind-approval-to-one-manifest-and-execution-lineage.md`](docs/adr/0007-bind-approval-to-one-manifest-and-execution-lineage.md)
    — accepted Approval contract.
12. [`docs/adr/0008-adopt-the-five-field-serving-envelope.md`](docs/adr/0008-adopt-the-five-field-serving-envelope.md)
    — accepted serving-record and separate internal traceability boundary.
13. [`docs/adr/0009-separate-serving-state-definition-from-lifecycle.md`](docs/adr/0009-separate-serving-state-definition-from-lifecycle.md)
    — accepted immutable Serving State and append-only lifecycle boundary.
14. [`docs/adr/0010-do-not-use-distillation-source-derived-identity.md`](docs/adr/0010-do-not-use-distillation-source-derived-identity.md)
    — excludes Distillation's source-derived hashes as greenfield identity.
15. [`docs/adr/0011-use-register-issued-layered-identity.md`](docs/adr/0011-use-register-issued-layered-identity.md)
    — accepted register-issued layered identity and immutable Search Records.
16. [`docs/adr/0012-use-evidence-backed-legislation-continuity-rules.md`](docs/adr/0012-use-evidence-backed-legislation-continuity-rules.md)
    — accepted evidence-backed legislation identity-continuity rules.
17. [`docs/adr/0013-deliver-warnings-in-required-serving-metadata.md`](docs/adr/0013-deliver-warnings-in-required-serving-metadata.md)
    — establishes the required LLM-facing metadata channel later standardized
    as `metadata.authority_note` by ADR 0050.
18. [`docs/adr/0014-use-proposition-scoped-case-law-continuity-and-retirement.md`](docs/adr/0014-use-proposition-scoped-case-law-continuity-and-retirement.md)
    — accepted case-law continuity, treatment, authority-note, and retirement rules.
19. [`docs/adr/0015-use-publisher-evidence-backed-reference-work-continuity.md`](docs/adr/0015-use-publisher-evidence-backed-reference-work-continuity.md)
    — accepted Principles continuity and licence-expiry freeze rules.
20. [`docs/adr/0016-keep-the-record-traceability-lookup-outside-the-query-path.md`](docs/adr/0016-keep-the-record-traceability-lookup-outside-the-query-path.md)
    — keeps the internal record-to-source traceability map outside Ask.Legal's
    live query path.
21. [`docs/adr/0017-use-jurisdiction-specific-principles-terminology.md`](docs/adr/0017-use-jurisdiction-specific-principles-terminology.md)
    — names Australian Principles, Singapore Principles, and other
    jurisdiction-specific Principles as separate material families.
22. [`docs/adr/0018-use-versioned-jurisdiction-and-material-source-rulebooks.md`](docs/adr/0018-use-versioned-jurisdiction-and-material-source-rulebooks.md)
    — standardizes the Source Rulebook Contract while keeping every
    jurisdiction-and-material rulebook separate.
23. [`docs/adr/0019-define-hong-kong-legislation-coverage-and-bilingual-records.md`](docs/adr/0019-define-hong-kong-legislation-coverage-and-bilingual-records.md)
    — defines complete Hong Kong legislation coverage and one English-and-
    Traditional-Chinese Search Record per searchable location.
24. [`docs/adr/0020-use-english-only-internal-warnings-for-hong-kong-records.md`](docs/adr/0020-use-english-only-internal-warnings-for-hong-kong-records.md)
    — keeps Hong Kong authority notes as English-only internal LLM instructions.
25. [`docs/adr/0021-use-canonical-bilingual-text-and-structure-aligned-splitting-for-hong-kong-legislation.md`](docs/adr/0021-use-canonical-bilingual-text-and-structure-aligned-splitting-for-hong-kong-legislation.md)
    — fixes Hong Kong legislation's bilingual text layout and legal-structure
    splitting rule.
26. [`docs/adr/0022-require-hkel-xml-and-matching-verified-pdfs-for-hong-kong-legislation.md`](docs/adr/0022-require-hkel-xml-and-matching-verified-pdfs-for-hong-kong-legislation.md)
    — records the original verified-copy gate; ADR 0081 later permits matching
    official HKeL assisted copies across covered scopes.
27. [`docs/adr/0023-defer-reconstructed-hong-kong-legislation-records.md`](docs/adr/0023-defer-reconstructed-hong-kong-legislation-records.md)
    — records the former reconstruction deferral, later superseded by ADR
    0080, while preserving its historical rationale.
28. [`docs/adr/0024-keep-hklii-non-controlling-and-defer-formal-registration.md`](docs/adr/0024-keep-hklii-non-controlling-and-defer-formal-registration.md)
    — establishes HKLII's non-controlling discovery and originating-source
    evidence boundary; ADR 0045 later registers the automated source role.
29. [`docs/adr/0025-use-fact-specific-gazette-event-evidence-for-hong-kong-legislation.md`](docs/adr/0025-use-fact-specific-gazette-event-evidence-for-hong-kong-legislation.md)
    — uses exact Gazette artifacts for specific legal events while keeping the
    applicable HKeL evidence as the consolidated-law boundary.
30. [`docs/adr/0026-use-hkel-past-data-for-history-and-editorial-records-for-official-editorial-events.md`](docs/adr/0026-use-hkel-past-data-for-history-and-editorial-records-for-official-editorial-events.md)
    — separates historical version reconciliation from official editorial-
    amendment evidence without bypassing applicable current HKeL evidence.
31. [`docs/adr/0027-exclude-legco-bills-and-proceedings-from-hong-kong-legislation.md`](docs/adr/0027-exclude-legco-bills-and-proceedings-from-hong-kong-legislation.md)
    — excludes LegCo Bills and proceedings from the automated current-law
    pipeline while allowing optional non-controlling human research.
32. [`docs/adr/0028-pin-hkel-publication-specifications-for-source-interpretation.md`](docs/adr/0028-pin-hkel-publication-specifications-for-source-interpretation.md)
    — pins the official HKeL specifications that define source interpretation
    without treating them as item-specific evidence or serving content.
33. [`docs/adr/0029-allow-official-hkel-assisted-copies-for-constitutional-instruments.md`](docs/adr/0029-allow-official-hkel-assisted-copies-for-constitutional-instruments.md)
    — records the original constitutional assisted-copy exception, later
    broadened across covered Hong Kong Legislation by ADR 0081.
34. [`docs/adr/0030-classify-hkel-instruments-by-legal-nature-and-explicit-disposition.md`](docs/adr/0030-classify-hkel-instruments-by-legal-nature-and-explicit-disposition.md)
    — routes HKeL A-series entries by actual legal nature and requires a
    complete versioned Instrument Disposition Registry.
35. [`docs/adr/0031-use-tiered-source-monitoring-and-change-triggered-ai.md`](docs/adr/0031-use-tiered-source-monitoring-and-change-triggered-ai.md)
    — uses scalable tiered source checks and gates model work behind a real
    deterministic change signal and an explicitly enabled task.
36. [`docs/adr/0032-register-fact-specific-hong-kong-legislation-sources.md`](docs/adr/0032-register-fact-specific-hong-kong-legislation-sources.md)
    — registers Hong Kong legislation sources by exact fact authority, outage
    impact, endpoint family, and monitoring tier while keeping historical
    material on demand.
37. [`docs/adr/0033-define-hong-kong-legislation-current-update-rules-and-conformance-cases.md`](docs/adr/0033-define-hong-kong-legislation-current-update-rules-and-conformance-cases.md)
    — defines stable Hong Kong current-update rules and matching pass, fail,
    boundary, conflict, and regression cases.
38. [`docs/adr/0034-establish-the-first-hong-kong-legislation-current-baseline-without-replaying-history.md`](docs/adr/0034-establish-the-first-hong-kong-legislation-current-baseline-without-replaying-history.md)
    — establishes the complete first Hong Kong current baseline from accepted
    present evidence while opening history only for named uncertainties.
39. [`docs/adr/0035-define-ordinary-provision-hkel-reconciliation-fixtures.md`](docs/adr/0035-define-ordinary-provision-hkel-reconciliation-fixtures.md)
    — fixes ordinary-provision XML/PDF, bilingual-pairing, source-review, and
    canonical-rendering examples with exact pass, block, or Quarantine results.
40. [`docs/adr/0036-define-schedule-table-and-form-hkel-reconciliation-fixtures.md`](docs/adr/0036-define-schedule-table-and-form-hkel-reconciliation-fixtures.md)
    — fixes Legal Location, rendering, bilingual-alignment, mismatch, and safe-
    splitting examples for Schedules, tables, and prescribed forms.
41. [`docs/adr/0037-define-note-image-and-cross-reference-hkel-reconciliation-fixtures.md`](docs/adr/0037-define-note-image-and-cross-reference-hkel-reconciliation-fixtures.md)
    — separates statutory and publisher notes, authority-note consequences, visual
    evidence, and exact source references from internal target resolution.
42. [`docs/adr/0038-define-partial-status-and-bilingual-structure-hkel-fixtures.md`](docs/adr/0038-define-partial-status-and-bilingual-structure-hkel-fixtures.md)
    — fixes partial-status coverage, authority-note placement, bilingual alignment,
    and smallest-safe-boundary outcomes.
43. [`docs/adr/0039-confine-generative-llm-use-to-explicit-legal-processing-tasks.md`](docs/adr/0039-confine-generative-llm-use-to-explicit-legal-processing-tasks.md)
    — confines any internal generative-LLM use to one proposal-only gateway
    and defines the task-admission and authority boundaries.
44. [`docs/adr/0040-define-recursive-overlong-hkel-record-partitioning.md`](docs/adr/0040-define-recursive-overlong-hkel-record-partitioning.md)
    — defines recursive official-structure partitioning, dependency closure,
    exact final-payload measurement, and source-unit coverage proof for
    overlong bilingual Hong Kong legislation records.
45. [`docs/adr/0041-use-strict-hashed-hkel-fixture-packages.md`](docs/adr/0041-use-strict-hashed-hkel-fixture-packages.md)
    — defines the frozen fixture catalogue, strict package manifest, hashed
    synthetic inputs, exact expected artifacts, and semantic validation rules.
46. [`docs/adr/0042-package-the-hong-kong-legislation-source-rulebook.md`](docs/adr/0042-package-the-hong-kong-legislation-source-rulebook.md)
    — packages Hong Kong Legislation policy, source roles, rules, codes,
    contracts, scope readiness, tests, activation, and build conformance.
47. [`docs/adr/0043-defer-final-generative-llm-task-allocation.md`](docs/adr/0043-defer-final-generative-llm-task-allocation.md)
    — defers the remaining deterministic-versus-generative-LLM task allocation
    while preserving the sole gateway and proposal-only safety boundary; ADR
    0053 later settles the Hong Kong treatment exception.
48. [`docs/adr/0044-normalize-hong-kong-current-update-results-and-complete-observation-failure-cases.md`](docs/adr/0044-normalize-hong-kong-current-update-results-and-complete-observation-failure-cases.md)
    — separates processing, disposition, coverage, review, and output results
    and adds the missing observation-failure conformance cases.
49. [`docs/adr/0045-register-hklii-as-a-non-controlling-automated-discovery-source.md`](docs/adr/0045-register-hklii-as-a-non-controlling-automated-discovery-source.md)
    — registers HKLII for automated Hong Kong Cases discovery while keeping
    judgment and treatment authority with accepted originating evidence.
50. [`docs/adr/0046-limit-ordinary-hong-kong-case-coverage-to-binding-courts.md`](docs/adr/0046-limit-ordinary-hong-kong-case-coverage-to-binding-courts.md)
    — limits ordinary Hong Kong Case coverage to binding courts and keeps
    lower-body judgments outside searchable serving.
51. [`docs/adr/0047-serve-hong-kong-case-propositions-in-original-language-by-default.md`](docs/adr/0047-serve-hong-kong-case-propositions-in-original-language-by-default.md)
    — serves Hong Kong Case Propositions in their original language and keeps
    Judiciary translations as linked evidence unless evaluation proves a
    later serving enrichment is needed.
52. [`docs/adr/0048-account-for-every-official-hong-kong-judgment-listing-entry.md`](docs/adr/0048-account-for-every-official-hong-kong-judgment-listing-entry.md)
    — separates official listings, judicial decisions, and judgment artifacts
    and requires explicit acquisition and completeness accounting.
53. [`docs/adr/0049-establish-the-first-hong-kong-cases-current-authority-baseline.md`](docs/adr/0049-establish-the-first-hong-kong-cases-current-authority-baseline.md)
    — establishes the first corpus-wide current-authority baseline without an
    arbitrary case-age cutoff.
54. [`docs/adr/0050-use-one-standardized-authority-note-metadata-field.md`](docs/adr/0050-use-one-standardized-authority-note-metadata-field.md)
    — standardizes one required `metadata.authority_note` field across all
    material families for controlled warnings and budget-based material
    support and neutral explanatory context.
55. [`docs/adr/0052-update-hong-kong-cases-through-bounded-impact-reconciliation.md`](docs/adr/0052-update-hong-kong-cases-through-bounded-impact-reconciliation.md)
    — updates Hong Kong Cases through bounded impact reconciliation and fixes
    HKLII's exact non-controlling discovery role.
56. [`docs/adr/0053-use-staged-hybrid-analysis-for-hong-kong-later-treatment.md`](docs/adr/0053-use-staged-hybrid-analysis-for-hong-kong-later-treatment.md)
    — uses whole-judgment LLM discovery and candidate-level LLM proposals
    between deterministic preparation, validation, and Legal Desk decisions.
57. [`docs/adr/0054-classify-hkex-listing-rules-as-hong-kong-regulatory-materials.md`](docs/adr/0054-classify-hkex-listing-rules-as-hong-kong-regulatory-materials.md)
    — adds the Regulatory category and `type: "regulatory"` for current HKEX
    Main Board and GEM Listing Rules while keeping guidance separate.
58. [`docs/adr/0055-use-immutable-selection-transitions-for-hong-kong-case-treatment.md`](docs/adr/0055-use-immutable-selection-transitions-for-hong-kong-case-treatment.md)
    — defines exact reuse, successor, reselection, retirement, partial
    retirement, uncertainty, and embedding-reuse behavior for Hong Kong case
    treatment without mutable records or cyclic lineage.
59. [`docs/adr/0056-separate-semantic-evaluations-from-deterministic-hong-kong-treatment-fixtures.md`](docs/adr/0056-separate-semantic-evaluations-from-deterministic-hong-kong-treatment-fixtures.md)
    — separates LLM semantic-understanding evaluations from byte-exact legal,
    record, release, and serving contract fixtures.
60. [`docs/adr/0057-use-strict-non-leaking-hong-kong-treatment-conformance-packages.md`](docs/adr/0057-use-strict-non-leaking-hong-kong-treatment-conformance-packages.md)
    — fixes permanent non-answer-bearing IDs, strict semantic and deterministic
    packages, expected-artifact states, catalogues, and coverage completeness.
61. [`docs/adr/0058-store-one-directional-case-treatment-relationship-with-two-internal-views.md`](docs/adr/0058-store-one-directional-case-treatment-relationship-with-two-internal-views.md)
    — stores each proposition-scoped treatment once, derives incoming and
    outgoing internal views, and keeps treatment-graph records out of Pinecone.
62. [`docs/adr/0059-freeze-the-initial-hong-kong-treatment-conformance-catalogue.md`](docs/adr/0059-freeze-the-initial-hong-kong-treatment-conformance-catalogue.md)
    — freezes the audited initial 155-case, 155-cell, and 21-pair Hong Kong
    treatment conformance universe.
63. [`docs/adr/0060-define-the-hong-kong-case-proposition-output-and-evidence-contract.md`](docs/adr/0060-define-the-hong-kong-case-proposition-output-and-evidence-contract.md)
    — defines one evidence-bearing proposition record, its labelled serving
    text, exact judgment support, one-record boundary, and zero-record or
    Quarantine behavior without choosing the extraction method.
64. [`docs/adr/0061-define-hong-kong-case-proposition-split-and-merge-rules.md`](docs/adr/0061-define-hong-kong-case-proposition-split-and-merge-rules.md)
    — splits and merges propositions by independent legal meaning, preserves
    opinion boundaries, quarantines indivisible overlong records, and defines
    correction lineage without token-based fragmentation.
65. [`docs/adr/0062-define-the-hong-kong-case-proposition-coverage-ledger.md`](docs/adr/0062-define-the-hong-kong-case-proposition-coverage-ledger.md)
    — requires an immutable complete source-unit, opinion, dependency,
    candidate, evidence-role, outcome, and zero-proposition accounting proof
    for every exact Hong Kong judgment version.
66. [`docs/adr/0063-separate-semantic-evaluation-from-deterministic-hong-kong-case-proposition-conformance.md`](docs/adr/0063-separate-semantic-evaluation-from-deterministic-hong-kong-case-proposition-conformance.md)
    — separates legal-understanding evaluation from exact mechanical
    conformance, uses adjudicated Reference Proposition Maps, and admits only
    one exact complete extraction workflow.
67. [`docs/adr/0064-freeze-the-initial-hong-kong-case-proposition-extraction-conformance-catalogue.md`](docs/adr/0064-freeze-the-initial-hong-kong-case-proposition-extraction-conformance-catalogue.md)
    — freezes the initial 132-case, 132-cell, and 31-pair Hong Kong Case
    Proposition extraction conformance universe.
68. [`docs/adr/0065-use-two-pass-hybrid-analysis-for-hong-kong-case-proposition-extraction.md`](docs/adr/0065-use-two-pass-hybrid-analysis-for-hong-kong-case-proposition-extraction.md)
    — allocates Hong Kong Case Proposition extraction across deterministic
    admission and validation, primary LLM analysis, independent LLM challenge,
    Legal Desk acceptance, narrow human review, and deterministic finalization.
69. [`docs/adr/0066-define-the-hong-kong-case-proposition-llm-task-contracts.md`](docs/adr/0066-define-the-hong-kong-case-proposition-llm-task-contracts.md)
    — fixes the two stable task families, closed request kinds, evidence-bound
    request and response contracts, long-judgment behavior, independent
    challenge, exact-range quotation boundary, and no-confidence rule.
70. [`docs/adr/0067-admit-and-monitor-complete-hong-kong-case-proposition-workflows.md`](docs/adr/0067-admit-and-monitor-complete-hong-kong-case-proposition-workflows.md)
    — admits only an exact complete Case Proposition workflow and fixes its
    evaluation repetitions, context reserve, retry, cost, monitoring,
    suspension, and revalidation policy.
71. [`docs/adr/0068-package-hong-kong-case-proposition-evaluations-and-admission-profiles.md`](docs/adr/0068-package-hong-kong-case-proposition-evaluations-and-admission-profiles.md)
    — defines the immutable evaluation suite, protected real-judgment and
    Reference Proposition Map views, evaluator results, pre-frozen admission
    profile, and non-circular admission evidence chain.
72. [`docs/adr/0069-account-for-every-hkex-listing-rule-component.md`](docs/adr/0069-account-for-every-hkex-listing-rule-component.md)
    — requires immutable complete Main Board and GEM rule-component inventory
    packages with separate membership, ownership, effective-state,
    disposition, processing, and readiness results.
73. [`docs/adr/0070-use-a-lean-hkex-regulatory-source-register.md`](docs/adr/0070-use-a-lean-hkex-regulatory-source-register.md)
    — registers five ordinary HKEX current-source roles, keeps optional and
    item-specific evidence outside routine release dependencies, and prevents
    source material from entering the downstream LLM automatically.
74. [`docs/adr/0071-decide-hkex-effective-state-per-applicability-branch.md`](docs/adr/0071-decide-hkex-effective-state-per-applicability-branch.md)
    — decides current effect per exact applicability branch, preserves
    concurrent transitions, fails closed on trigger or current-product
    conflicts, and separates legal state from serving disposition.
75. [`docs/adr/0072-serve-hkex-regulatory-materials-in-english-only.md`](docs/adr/0072-serve-hkex-regulatory-materials-in-english-only.md)
    — serves complete prevailing English HKEX rule text, keeps Chinese
    translations outside the ordinary release path, and requires evaluated
    Chinese-query retrieval without fabricating Chinese source text.
76. [`docs/adr/0073-construct-complete-source-faithful-english-hkex-records.md`](docs/adr/0073-construct-complete-source-faithful-english-hkex-records.md)
    — constructs class-specific complete English HKEX records with bounded
    governing context, non-recursive cross-references, official-structure
    overlong partitioning, and exhaustive source-unit coverage proof.
77. [`docs/adr/0074-use-two-linked-conformance-layers-for-hkex-regulatory-materials.md`](docs/adr/0074-use-two-linked-conformance-layers-for-hkex-regulatory-materials.md)
    — separates evidence-to-decision from exact decision-to-artifact
    Regulatory conformance and fixes strict catalogues, coverage-matrix,
    high-risk-pair, reproducibility, and build-attestation mechanics.
78. [`docs/adr/0075-freeze-the-initial-hkex-regulatory-conformance-catalogue.md`](docs/adr/0075-freeze-the-initial-hkex-regulatory-conformance-catalogue.md)
    — freezes the audited initial Regulatory conformance universe at 284
    direct cases, 284 matching primary cells, and 57 high-risk pairs.
79. [`docs/adr/0076-use-change-gated-two-pass-hybrid-analysis-for-hkex-regulatory-materials.md`](docs/adr/0076-use-change-gated-two-pass-hybrid-analysis-for-hkex-regulatory-materials.md)
    — uses deterministic fast paths around change-gated update and record
    analysis-and-challenge proposal tasks, with Legal Desk authority and
    deterministic finalization.
80. [`docs/adr/0077-admit-hkex-multilingual-retrieval-and-downstream-answer-behavior-separately.md`](docs/adr/0077-admit-hkex-multilingual-retrieval-and-downstream-answer-behavior-separately.md)
    — separately admits multilingual retrieval, frozen-context answer behavior,
    and the complete Ask.Legal query path for English-only Regulatory records.
81. [`docs/adr/0078-define-serving-record-and-record-traceability-lookup-encoding.md`](docs/adr/0078-define-serving-record-and-record-traceability-lookup-encoding.md)
    — fixes the strict six-field Serving Record, canonical payload and note
    fingerprints, and complete reusable Release-Scope-sharded traceability
    lookup encoding.
82. [`docs/adr/0079-keep-last-verified-legislation-searchable-during-known-consolidation-gaps.md`](docs/adr/0079-keep-last-verified-legislation-searchable-during-known-consolidation-gaps.md)
    — keeps the latest applicable official HKeL legislation held searchable
    with mandatory warnings as the fallback when an official change is known
    but neither an updated consolidation nor an eligible reconstruction is
    available; ADR 0081 permits verified or assisted supporting copies.
83. [`docs/adr/0080-allow-evidence-bound-searchable-hong-kong-legislation-reconstruction.md`](docs/adr/0080-allow-evidence-bound-searchable-hong-kong-legislation-reconstruction.md)
    — permits exact evidence-bound reconstructed Hong Kong consolidations in
    ordinary search with the approved mandatory warning and ADR 0079 fallback.
84. [`docs/adr/0081-allow-official-hkel-assisted-copies-for-current-and-reconstructed-text.md`](docs/adr/0081-allow-official-hkel-assisted-copies-for-current-and-reconstructed-text.md)
    — accepts the latest applicable official HKeL verified or assisted copies
    for ordinary current records and reconstruction bases.
85. [`docs/adr/0082-use-a-closed-deterministic-hong-kong-reconstruction-operation-registry.md`](docs/adr/0082-use-a-closed-deterministic-hong-kong-reconstruction-operation-registry.md)
    — fixes the closed deterministic amendment-operation allow-list, exact
    preconditions, atomicity, bilingual execution, fallback, and traceability
    rules for Hong Kong reconstruction.
86. [`docs/adr/0083-freeze-the-hong-kong-reconstruction-conformance-catalogue.md`](docs/adr/0083-freeze-the-hong-kong-reconstruction-conformance-catalogue.md)
    — freezes the initial 56 reconstruction cases, 56 primary cells, and 30
    pairs; ADRs 0086 and 0087 expand the current catalogue to 63, 63, and 35.
87. [`docs/adr/0084-define-the-hong-kong-reconstruction-plan-and-execution-report-contracts.md`](docs/adr/0084-define-the-hong-kong-reconstruction-plan-and-execution-report-contracts.md)
    — fixes strict immutable Plan and Execution Report identities, fields,
    operation bindings, atomic results, fingerprints, and traceability.
88. [`docs/adr/0085-define-the-reconstructed-consolidation-artifact-contract.md`](docs/adr/0085-define-the-reconstructed-consolidation-artifact-contract.md)
    — fixes the immutable bilingual reconstruction package, complete derivation
    map, coverage proofs, identity result, and ordinary-renderer boundary.
89. [`docs/adr/0086-reconcile-reconstructed-hong-kong-legislation-with-later-hkel.md`](docs/adr/0086-reconcile-reconstructed-hong-kong-legislation-with-later-hkel.md)
    — fixes scalable HKeL monitoring, common-basis comparison, mismatch
    attribution, bounded suspension, impact handling, and safe restart.
90. [`docs/adr/0087-require-attested-reconstruction-capability-before-processing-or-promotion.md`](docs/adr/0087-require-attested-reconstruction-capability-before-processing-or-promotion.md)
    — separates design, implementation, attestation, candidate-processing
    activation, and exact promotion authorization for reconstruction.
91. [`docs/design/HONG_KONG_RECONSTRUCTION_CONFORMANCE_CATALOGUE.md`](docs/design/HONG_KONG_RECONSTRUCTION_CONFORMANCE_CATALOGUE.md)
    — contains the exact accepted conceptual reconstruction case, cell, and
    controlled-pair catalogue.
92. [`docs/design/HONG_KONG_REGULATORY_CONFORMANCE_CATALOGUE.md`](docs/design/HONG_KONG_REGULATORY_CONFORMANCE_CATALOGUE.md)
    — contains the accepted exact 284-case HKEX Regulatory decision and
    deterministic coverage-cell catalogue and its 57 high-risk pairs.
93. [`docs/design/HONG_KONG_CASE_PROPOSITION_EXTRACTION_CONFORMANCE_CATALOGUE.md`](docs/design/HONG_KONG_CASE_PROPOSITION_EXTRACTION_CONFORMANCE_CATALOGUE.md)
    — contains the accepted exact synthetic semantic and deterministic Case
    Proposition extraction coverage-cell and case table.
94. [`docs/design/HONG_KONG_CASE_TREATMENT_CONFORMANCE_CATALOGUE.md`](docs/design/HONG_KONG_CASE_TREATMENT_CONFORMANCE_CATALOGUE.md)
    — contains the accepted exact initial synthetic semantic and deterministic
    Hong Kong treatment coverage-cell and case table.
95. [`docs/design/HONG_KONG_CASE_TREATMENT_DESIGN_AUDIT.md`](docs/design/HONG_KONG_CASE_TREATMENT_DESIGN_AUDIT.md)
    — records the final design-level treatment consistency audit, corrections,
    readiness boundary, and remaining decisions.
96. [`docs/design/HONG_KONG_LEGISLATION_DESIGN_AUDIT.md`](docs/design/HONG_KONG_LEGISLATION_DESIGN_AUDIT.md)
    — classifies the audited Hong Kong Legislation design as settled policy,
    implementation work, deferred decision, or cross-cutting dependency.
97. [`docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md`](docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md)
   — comprehensive initial design of the intended system.

## System shape

```mermaid
flowchart LR
    S["Official and approved publisher sources"]
    A["Acquire and preserve evidence"]
    D["Apply jurisdiction and material rules"]
    P["Prepare validated legal records"]
    C["Build the complete desired corpus"]
    R["Human reviews one frozen package"]
    V["Build and verify the approved serving state"]
    Q["Ask.Legal search"]

    S --> A --> D --> P --> C --> R --> V --> Q
```

## Planned monorepo shape

```text
AskLegal-LegalDBPipeline/
├── apps/
│   ├── control-plane/
│   ├── review-web/
│   ├── acquisition-worker/
│   ├── legal-processing-worker/
│   └── promotion-worker/
├── packages/
│   ├── domain/
│   ├── contracts/
│   ├── management-register/
│   ├── evidence-vault/
│   ├── source-connectors/
│   ├── legal-desks/
│   ├── processing/
│   ├── corpus/
│   ├── promotion/
│   ├── reporting/
│   └── observability/
├── tests/
│   ├── fixtures/
│   ├── unit/
│   ├── contract/
│   ├── integration/
│   ├── end-to-end/
│   └── legal-evaluations/
├── docs/
├── infra/
├── tools/
└── var/                 # ignored local runtime data only
```

The directories above describe the accepted target structure. They will be
created only when implementation is explicitly authorized.

## One repository, several security boundaries

The control plane, review application, acquisition worker, legal-processing
worker, and promotion worker are separate runnable applications. They may have
different identities, credentials, network access, scaling, and deployment
jobs even though their source code lives together.

In particular:

- acquisition cannot approve or deploy;
- legal processing cannot mutate production search;
- the review application cannot substitute different records;
- the control plane does not possess destructive production credentials; and
- only the promotion worker may apply the exact approved serving change.

## Information lives in three places

```text
Management register = what the system believes and is doing
Evidence vault      = what proves and can reproduce it
Pinecone            = what Ask.Legal currently searches
```

Git contains code, schemas, prompts, small fixtures, evaluation definitions,
infrastructure configuration, and documentation. Full legal corpora, source
snapshots, Corpus Releases, embedding caches, operational reports, backups,
credentials, and production state remain outside Git.

## Greenfield boundary

The older local Distillation, Release Store, Pinecone, and coordinator
repositories are reference material only. This repository does not inherit
their repository boundaries, internal contracts, schema, or implementation
automatically. A legacy idea may be reused only through an explicit current
decision and fresh validation.

## Design scope

The overall design describes the intended complete system and keeps unresolved
choices visible. It intentionally excludes pilot scope, staged product
versions, rollout planning, estimates, temporary operating arrangements, and
migration sequencing.
