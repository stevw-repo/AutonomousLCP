# Hong Kong Reconstruction Conformance Catalogue

Status: **Accepted by ADR 0083 and expanded by ADRs 0086 and 0087**

Updated: 2026-08-14

This is the canonical conceptual catalogue for Hong Kong publication-lag
reconstruction. It freezes 63 direct cases, 63 matching primary coverage cells,
and 35 controlled high-risk pairs. It defines required behavior but does not
contain executable fixture bytes, real legal source material, implementation,
or production authorization.

## Construction rule

The catalogue directly covers every ADR 0082 operation and every distinct
cross-cutting branch whose result changes. It does not target a round number or
multiply every independent fact into a Cartesian product.

Each case has one primary cell with the same ordinal:

- `HKLEG-RCN-DEC-001` maps to `HKLEG-RCN-CELL-001`, continuing through
  decision case and cell `032`; and
- `HKLEG-RCN-DET-033` maps to `HKLEG-RCN-CELL-033`, continuing through
  deterministic case and cell `063`.

The executable coverage matrix must list every mapping explicitly. Ranges in
this document describe the frozen catalogue but cannot replace enumeration in
the machine package.

## Result language

`PASS` means the asserted checkpoint produced the exact reference result. It
does not by itself mean that production serving is authorized. `BLOCK` means
the affected reconstruction cannot proceed from the supplied evidence.
`QUARANTINE` means preserved evidence conflicts or cannot safely be attributed.
`SOURCE_CONTRACT_REVIEW` means source semantics or the registry contract are
unknown. Each negative case also fixes the exact Coverage Gap, fallback, or
zero-record consequence.

## Frozen case catalogue

### A. Evidence-to-plan decision cases

| Case ID | Primary scenario | Required result |
|---|---|---|
| `HKLEG-RCN-DEC-001` | Exact source-backed text range and replacement content match once | Accept `HKRECON-OP-001` with exact before and after hashes |
| `HKLEG-RCN-DEC-002` | The stated old text does not match the selected base | `BLOCK`; `RECONSTRUCTION_BEFORE_STATE_MISMATCH`; no fuzzy search; eligible fallback |
| `HKLEG-RCN-DEC-003` | Official instruction replaces every exact occurrence inside one completely enumerated scope | Accept `HKRECON-OP-002`; record every match and scope boundary |
| `HKLEG-RCN-DEC-004` | Scope, exclusion, or occurrence set is open, ambiguous, zero, or unexpectedly different | `BLOCK`; `RECONSTRUCTION_TARGET_NOT_EXACT`; eligible fallback |
| `HKLEG-RCN-DEC-005` | Complete new authentic-language node and exact insertion position are supplied | Accept `HKRECON-OP-003` with exact parent and order |
| `HKLEG-RCN-DEC-006` | New node is complete but its parent or order position is not exact | `BLOCK`; `RECONSTRUCTION_TARGET_NOT_EXACT`; eligible fallback |
| `HKLEG-RCN-DEC-007` | One complete identified node is expressly repealed or omitted | Accept `HKRECON-OP-004` and its exact source-unit removal set |
| `HKLEG-RCN-DEC-008` | Proposed deletion would remove shared, governing, or incompletely bounded content | `BLOCK`; `RECONSTRUCTION_DEPENDENCY_CLOSURE_INCOMPLETE`; eligible fallback |
| `HKLEG-RCN-DEC-009` | One complete node and complete authentic replacement node are supplied | Accept `HKRECON-OP-005` with exact structure and content |
| `HKLEG-RCN-DEC-010` | Replacement omits a required heading, note, or table header from the bounded replacement node | `BLOCK`; `RECONSTRUCTION_STRUCTURE_UNSUPPORTED`; eligible fallback |
| `HKLEG-RCN-DEC-011` | Official evidence exactly renumbers or relabels one node | Accept `HKRECON-OP-006`; preserve identity and record the new locator |
| `HKLEG-RCN-DEC-012` | Renumbering would require an unstated cross-reference repair | `BLOCK`; do not infer the repair; eligible fallback |
| `HKLEG-RCN-DEC-013` | Official evidence supplies the exact moved node, new parent, order, and dependency effects | Accept `HKRECON-OP-007` |
| `HKLEG-RCN-DEC-014` | Move destination, source order, shared context, or dependency effect is unresolved | `BLOCK`; `RECONSTRUCTION_DEPENDENCY_CLOSURE_INCOMPLETE`; eligible fallback |
| `HKLEG-RCN-DEC-015` | Complete official table, Form, Schedule, formula, or diagram-backed replacement is supported by the canonical renderer | Accept `HKRECON-OP-008` with complete structured-region coverage |
| `HKLEG-RCN-DEC-016` | Structured replacement is incomplete or contains meaning the renderer cannot preserve | `BLOCK`; `RECONSTRUCTION_STRUCTURE_UNSUPPORTED`; eligible fallback |
| `HKLEG-RCN-DEC-017` | Latest applicable verified HKeL base and every operative amendment to cutoff are complete | Accept the closed plan from that exact base |
| `HKLEG-RCN-DEC-018` | A newer eligible assisted HKeL base exists beside an older verified base | Select the newer assisted base; preserve both evidence classes |
| `HKLEG-RCN-DEC-019` | Selected base version, language, location, or fingerprint does not match the plan | `BLOCK`; base or before-state mismatch; no operation execution |
| `HKLEG-RCN-DEC-020` | One operative amendment or Editorial Record between base and cutoff is missing | `BLOCK`; `RECONSTRUCTION_CHAIN_INCOMPLETE`; Coverage Gap and eligible fallback |
| `HKLEG-RCN-DEC-021` | Interacting amendments have a completely proved legal and source order | Accept one exact ordered chain |
| `HKLEG-RCN-DEC-022` | Interacting amendments share an effective time and their material order is unresolved | `BLOCK`; `RECONSTRUCTION_EVENT_ORDER_UNRESOLVED`; eligible fallback |
| `HKLEG-RCN-DEC-023` | Fixed, partial, cohort, transitional, retrospective, and conditional facts identify one exact operative branch; future operations are separately excluded | Accept only operations applicable to that branch and cutoff |
| `HKLEG-RCN-DEC-024` | Applicability remains unresolved and valid latest applicable HKeL fallback text is held | `BLOCK`; `RECONSTRUCTION_APPLICABILITY_UNRESOLVED`; exact Coverage Gap and warned fallback |
| `HKLEG-RCN-DEC-025` | Authentic languages require different operation sequences, including a proved one-language-only correction with an explicit unchanged stream, but establish one aligned legal result | Accept both streams and one complete Bilingual Alignment Map; never invent a no-op edit |
| `HKLEG-RCN-DEC-026` | One authentic-language amendment source or required output unit is missing | `BLOCK`; `RECONSTRUCTION_LANGUAGE_EVIDENCE_INCOMPLETE`; no monolingual result |
| `HKLEG-RCN-DEC-027` | One language is proposed by translating, paraphrasing, or copying the other | `BLOCK` as a prohibited operation; no generated authentic text |
| `HKLEG-RCN-DEC-028` | Both language streams execute but identify different legal effects, locations, or operative states | `QUARANTINE`; `RECONSTRUCTION_BILINGUAL_RESULT_MISMATCH`; no reconstruction |
| `HKLEG-RCN-DEC-029` | Amendment to a governing definition, heading, lead-in, or shared structure has a complete dependent-unit set | Accept the expanded dependency closure and all required operations |
| `HKLEG-RCN-DEC-030` | Proposed plan omits one dependent unit affected by changed governing context | `BLOCK`; `RECONSTRUCTION_DEPENDENCY_CLOSURE_INCOMPLETE`; no convenient child reconstruction |
| `HKLEG-RCN-DEC-031` | Official identifiers prove one-to-many, many-to-one, or many-to-many authentic-language alignment | Accept the non-symmetric but complete alignment |
| `HKLEG-RCN-DEC-032` | Complete units exist but the observed bilingual construct has no pinned interpretation rule | `BLOCK`; `SOURCE_CONTRACT_REVIEW`; no similarity pairing |

### B. Plan-to-artifact deterministic cases

| Case ID | Primary scenario | Required result |
|---|---|---|
| `HKLEG-RCN-DET-033` | Three dependent admitted operations all satisfy ordered preconditions | `PASS`; execute atomically and emit one exact result |
| `HKLEG-RCN-DET-034` | The middle operation fails its before-state precondition | Emit no partial reconstruction; exact failure report and eligible fallback |
| `HKLEG-RCN-DET-035` | One independent sibling succeeds while another bounded sibling fails | Emit the successful sibling only with complete separate accounting |
| `HKLEG-RCN-DET-036` | Failed operation affects a governing parent or unbounded shared dependency | Emit no dependent child reconstruction; block the complete unsafe closure |
| `HKLEG-RCN-DET-037` | Identical job retry sees an already issued exact result | Reselect the immutable result; do not apply any operation twice |
| `HKLEG-RCN-DET-038` | Two clean executions produce different plans, bytes, hashes, IDs, or reports | `BLOCK`; `RECONSTRUCTION_REPRODUCIBILITY_FAILURE`; build not attestable |
| `HKLEG-RCN-DET-039` | Strict plan package, operation IDs, parameters, files, hashes, and contracts are complete | `PASS`; exact immutable plan admitted for execution |
| `HKLEG-RCN-DET-040` | Plan contains an unknown operation, field, parameter, enum, selector, or contract version | Reject package; `SOURCE_CONTRACT_REVIEW` when semantics are genuinely new |
| `HKLEG-RCN-DET-041` | Execution reads undeclared evidence, a mutable alias, external path, URI, or local file | Reject as package and containment failure; no side effect |
| `HKLEG-RCN-DET-042` | Model or human supplies free-text final wording or an operation outside the registry | Reject the patch; no serving artifact and no registry bypass |
| `HKLEG-RCN-DET-043` | Execution report, artifacts, bilingual proof, lookup, lineage, Coverage Gap, and hashes are complete | `PASS`; every exact artifact equals its expected bytes |
| `HKLEG-RCN-DET-044` | Required report field, evidence binding, artifact, hash, lookup row, or coverage result is missing or forged | Reject result; no release eligibility |
| `HKLEG-RCN-DET-045` | Eligible reconstruction completes and ordinary record construction passes | Select one ordinary legislation record with the exact ADR 0080 authority note and complete traceability |
| `HKLEG-RCN-DET-046` | Reconstruction is unsupported and a newer eligible assisted fallback exists beside an older verified copy | Select only the newer assisted ADR 0079/0081 warned fallback |
| `HKLEG-RCN-DET-047` | Reconstruction is unsupported and no valid applicable HKeL fallback text exists | Select no record; publish the exact Coverage Gap |
| `HKLEG-RCN-DET-048` | Candidate inventory selects reconstruction and stale fallback for the same serving unit | Fail exclusivity and release completeness; select neither until corrected |
| `HKLEG-RCN-DET-049` | Reconstruction warning is absent, altered, split into another field, or has unsupported placeholder values | Reject Serving Record; no release eligibility |
| `HKLEG-RCN-DET-050` | Operation IDs, evidence class, plan, report, or internal reasoning enters `metadata.text` | Reject Serving Record as a serving-boundary defect |
| `HKLEG-RCN-DET-051` | Later applicable HKeL consolidation exactly matches reconstructed canonical legal content | Select the ordinary HKeL record, close the gap after complete reconciliation, preserve reconstruction evidence |
| `HKLEG-RCN-DET-052` | Later HKeL differs only by permitted PDF presentation projection while canonical legal content matches | Treat as an exact legal-content match and perform ordinary HKeL replacement |
| `HKLEG-RCN-DET-053` | Later HKeL materially disagrees with reconstructed wording or structure | Select valid HKeL result, preserve mismatch, suspend the attributable operation class or rule, and open bounded investigation |
| `HKLEG-RCN-DET-054` | Material mismatch is proved attributable to wrong source evidence, base identity, or event mapping rather than the operation implementation | Select valid HKeL result and suspend the affected evidence or mapping path; do not blame unrelated operation classes |
| `HKLEG-RCN-DET-055` | HKeL later consolidates only some independently separable affected units | Replace matched units only; retain eligible reconstruction and Coverage Gap for unresolved units |
| `HKLEG-RCN-DET-056` | No matching HKeL consolidation has yet arrived and reconstruction remains fully supported | Keep the warned reconstruction selected with active monitoring and Coverage Gap; no arbitrary retirement |
| `HKLEG-RCN-DET-057` | Valid later HKeL contains an additional overlapping change, so no exact common event horizon can be isolated | Replace serving with valid HKeL; record `COMPARISON_NOT_ISOLATABLE`; do not score or reverse-reconstruct the earlier artifact |
| `HKLEG-RCN-DET-058` | A changed later HKeL candidate fails ordinary bilingual evidence or reconciliation gates | Do not replace or compare; keep the eligible reconstruction and Coverage Gap while the HKeL evidence failure is resolved |
| `HKLEG-RCN-DET-059` | Exact reconstruction profile, attestation, build, activation, and operation class are current and active | Permit isolated candidate processing only; no source, provider, promotion, or production side effect |
| `HKLEG-RCN-DET-060` | Attestation or activation is missing, stale, expired, revoked, unverifiable, or fingerprint-mismatched | Block before execution; produce no real Plan or artifact |
| `HKLEG-RCN-DET-061` | One operation class is suspended while an independent operation class remains admitted | Referencing Plans use eligible fallback or no record; independent admitted work may continue |
| `HKLEG-RCN-DET-062` | Reconstructed release and manifest are complete but exact manifest-bound human Approval is absent | Promotion authorization fails; no Pinecone, backup, Azure, or routing effect |
| `HKLEG-RCN-DET-063` | Exact immutable promotion package and matching valid Approval are supplied to an isolated fake adapter | Authorization validation passes without contacting production; execution remains outside this suite |

## Frozen controlled pairs

Each pair fixes one high-risk distinction. “Reference” is the case that proves
the permitted or correctly bounded path; “near boundary” changes one material
fact and requires the different result.

| Pair ID | Reference | Near boundary | Controlled distinction |
|---|---|---|---|
| `HKLEG-RCN-PAIR-001` | `001` | `002` | Exact before-state versus mismatch |
| `HKLEG-RCN-PAIR-002` | `003` | `004` | Closed match set versus ambiguous scope or count |
| `HKLEG-RCN-PAIR-003` | `005` | `006` | Exact insertion point versus ambiguous position |
| `HKLEG-RCN-PAIR-004` | `007` | `008` | Complete-node deletion versus shared or incomplete boundary |
| `HKLEG-RCN-PAIR-005` | `009` | `010` | Complete replacement versus omitted legal content |
| `HKLEG-RCN-PAIR-006` | `011` | `012` | Express renumbering versus inferred cross-reference repair |
| `HKLEG-RCN-PAIR-007` | `013` | `014` | Explicit complete move versus unresolved destination or dependency |
| `HKLEG-RCN-PAIR-008` | `015` | `016` | Renderer-complete structure versus unrepresentable meaning |
| `HKLEG-RCN-PAIR-009` | `017` | `019` | Exact base versus wrong base identity or fingerprint |
| `HKLEG-RCN-PAIR-010` | `018` | `019` | Eligible newer assisted base versus mismatched base evidence |
| `HKLEG-RCN-PAIR-011` | `021` | `022` | Proved interacting order versus unresolved order |
| `HKLEG-RCN-PAIR-012` | `023` | `024` | Exact applicability branch versus unresolved effect |
| `HKLEG-RCN-PAIR-013` | `025` | `026` | Complete authentic streams versus missing language evidence |
| `HKLEG-RCN-PAIR-014` | `025` | `027` | Authentic separate streams versus generated translation |
| `HKLEG-RCN-PAIR-015` | `025` | `028` | Aligned effect versus bilingual legal mismatch |
| `HKLEG-RCN-PAIR-016` | `029` | `030` | Complete governing dependency closure versus omitted dependent unit |
| `HKLEG-RCN-PAIR-017` | `031` | `032` | Official non-symmetric alignment versus similarity-only mapping |
| `HKLEG-RCN-PAIR-018` | `033` | `034` | Complete atomic chain versus failed middle operation |
| `HKLEG-RCN-PAIR-019` | `035` | `036` | Bounded independent sibling versus shared governing failure |
| `HKLEG-RCN-PAIR-020` | `037` | `038` | Reproducible retry versus non-deterministic execution |
| `HKLEG-RCN-PAIR-021` | `039` | `040` | Known strict plan contract versus unknown operation semantics |
| `HKLEG-RCN-PAIR-022` | `039` | `041` | Declared contained inputs versus undeclared external input |
| `HKLEG-RCN-PAIR-023` | `039` | `042` | Registry plan versus free-text patch |
| `HKLEG-RCN-PAIR-024` | `043` | `044` | Complete report and lookup versus missing or forged proof |
| `HKLEG-RCN-PAIR-025` | `045` | `049` | Exact reconstruction warning versus missing or altered warning |
| `HKLEG-RCN-PAIR-026` | `045` | `050` | Ordinary serving text versus leaked internal operation data |
| `HKLEG-RCN-PAIR-027` | `046` | `047` | Eligible latest-HKeL fallback versus no valid fallback text |
| `HKLEG-RCN-PAIR-028` | `045` | `048` | Exactly one selected result versus reconstruction-plus-fallback duplication |
| `HKLEG-RCN-PAIR-029` | `051` | `053` | Later HKeL match versus material mismatch |
| `HKLEG-RCN-PAIR-030` | `053` | `054` | Operation-attributable mismatch versus evidence-or-mapping-attributable mismatch |
| `HKLEG-RCN-PAIR-031` | `051` | `057` | Comparable common event horizon versus overlapping additional change |
| `HKLEG-RCN-PAIR-032` | `051` | `058` | Valid comparable HKeL bundle versus invalid candidate bundle |
| `HKLEG-RCN-PAIR-033` | `059` | `060` | Exact active capability versus stale or mismatched capability |
| `HKLEG-RCN-PAIR-034` | `059` | `061` | Admitted operation class versus suspended affected class |
| `HKLEG-RCN-PAIR-035` | `063` | `062` | Exact manifest-bound Approval versus missing Approval |

The executable pair catalogue uses full case IDs and explicitly declares each
member's role. The abbreviated ordinals above remain unambiguous only inside
this frozen table and cannot be used as executable identities.

## Required suite-wide assertions

Every case additionally proves, where applicable:

- no network, source, model, embedding, Pinecone, Azure, backup, routing,
  promotion, deployment, credential, or production-store access;
- exact file containment, schema validation, hashes, contract locks, and
  declared inventory;
- exact processing, legal disposition, coverage, review, record-output, reason,
  and Rule Trace dimensions;
- immutable base evidence, plans, reports, artifacts, records, identities, and
  lineage;
- complete authentic-language and dependency coverage without generated text;
- exact warning and six-field Serving Record validation;
- exact reconstruction-versus-fallback exclusivity and complete release
  accounting; and
- two isolated clean executions with byte-identical results.

## Readiness boundary

The current reconstruction-enabled Hong Kong Legislation conformance universe
is the pre-reconstruction 121 direct cases plus these 63 direct cases, for 184
direct cases total. The 35 controlled pairs are additional relational
assertions and are not extra executable cases.

This document does not create the executable suite. Strict schemas, manifests,
fixture bytes, expected artifact bytes, validators, a successful run, and a
complete ADR 0087 Reconstruction Capability Attestation and activation remain
required before real candidate reconstruction can run. Human Approval and
promotion remain separate even after activation.
