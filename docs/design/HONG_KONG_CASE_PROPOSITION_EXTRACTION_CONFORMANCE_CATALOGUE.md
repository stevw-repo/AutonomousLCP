# Hong Kong Case Proposition Extraction Conformance Catalogue

Status: **Accepted and frozen by ADR 0064**

Updated: 2026-08-13

This document is the accepted exact initial conceptual coverage-cell and case
catalogue required by ADRs 0063 and 0064. It freezes legal and technical scenarios, not
executable JSON, judgment bytes, model selection, prompts, numerical
thresholds, evaluation repetitions, provider calls, or production actions.

The proposed catalogue contains **132 direct cases and 132 matching primary
coverage cells**:

| Suite and checkpoint | Cases |
|---|---:|
| Semantic materiality and discovery | 18 |
| Semantic proposition content and evidence | 18 |
| Semantic boundary and opinion attribution | 22 |
| Semantic court, language, length, uncertainty, and safety | 20 |
| Deterministic structure and Coverage Ledger | 20 |
| Deterministic candidate, evidence, renderer, and output | 16 |
| Deterministic correction, package, security, and admission | 18 |
| **Total** | **132** |

The total is the result of direct branch coverage. It is not a permanent
ceiling. Each row is one primary case and one matching primary coverage cell.
A new requirement adds a new immutable case and cell; existing IDs and
meanings are never reassigned or silently rewritten to preserve this count.

## Exact ID expansion

Within each table, a three-digit suffix expands to the complete case and
coverage IDs shown above the table. For example, semantic materiality row
`004` means:

- case `HKCASE-PROP-SEM-MAT-004`; and
- coverage cell `HKCASE-PROP-COV-SMAT-004`.

The pair column uses `Pnnn +` for a positive member and `Pnnn -` for its
high-risk near-miss. It expands to `HKCASE-PROP-PAIR-NNN`. A blank pair column
means direct ordinary coverage rather than a required pair.

IDs identify only suite, checkpoint, and permanent ordinal. They do not encode
the court, language, proposition count, expected answer, success, failure, or
critical-error result and are never supplied to an evaluated workflow.

## A. Semantic materiality and discovery

Case namespace: `HKCASE-PROP-SEM-MAT-NNN`

Coverage namespace: `HKCASE-PROP-COV-SMAT-NNN`

| Suffix | Pair | Synthetic judgment situation | Required semantic result |
|---:|---|---|---|
| 001 | P001 +; P031 + | Operative opinion states and applies one clear legal test | Discover one material proposition with complete issue, answer, limits, application, result, attribution, and exact support |
| 002 | P002 + | Court applies a familiar settled rule to resolve a genuinely disputed issue | Discover the material proposition; novelty is not required |
| 003 | P002 - | Court lists a familiar authority as a bare citation without using its proposition | No new proposition from the citation; retain the citation or treatment lead internally |
| 004 | P003 + | Court quotes an earlier rule, expressly adopts it, and applies it | Discover one attributed proposition supported by the adoption passage, quoted support, and application |
| 005 | P003 - | Court quotes an earlier rule as background but never adopts or applies it | Do not create a proposition from the quotation; preserve its source and citation role internally |
| 006 | P004 + | Operative court expressly accepts one party's formulated legal test as its own reasoning | Discover the court's proposition with the exact acceptance and adopted wording; do not attribute authority to the party |
| 007 | P004 - | Judgment merely records one party's proposed legal test | No proposition from the unadopted submission |
| 008 |  | Procedural chronology contains legal terminology but no legal answer | `COMPLETE_NO_PROPOSITION` only after complete ledger and treatment-screening accounting |
| 009 |  | Judgment announces only the disposition without explaining a legal rule | No proposition; outcome remains accounted source material |
| 010 |  | Opinion resolves only a factual dispute and states no independently usable legal answer | No proposition; do not turn a fact finding into a rule |
| 011 |  | Court gives an administrative or case-management direction | No proposition unless separate source-supported legal reasoning independently qualifies |
| 012 | P005 + | Clearly attributed obiter reasoning materially explains a usable legal rule | Discover the proposition and label the obiter authority role prominently |
| 013 | P001 -; P005 - | Opinion mentions a legal topic hypothetically without materially explaining or using a rule | No proposition from non-material discussion |
| 014 |  | One judgment resolves several independently searchable legal issues | Discover every material proposition and no whole-case overview record |
| 015 | P031 - | Judgment contains no proposition of its own but expressly treats an earlier authority | No invented proposition; complete treatment-only handoff to the separate screening inventory |
| 016 |  | A material rule is stated in a footnote and applied through non-contiguous passages | Discover it using the smallest complete set of exact linked ranges |
| 017 | P019 + | Complete judgment contains citations and procedural text but no material proposition | Valid `COMPLETE_NO_PROPOSITION` with every unit and citation or treatment handoff accounted |
| 018 |  | Judgment contains supported propositions but later-treatment selection excludes every resulting record | Extract all propositions; ledger is `COMPLETE_WITH_PROPOSITIONS`; downstream selection alone is zero |

## B. Semantic proposition content and evidence

Case namespace: `HKCASE-PROP-SEM-CNT-NNN`

Coverage namespace: `HKCASE-PROP-COV-SCNT-NNN`

| Suffix | Pair | Synthetic proposition evidence | Required semantic result |
|---:|---|---|---|
| 001 |  | Court states one rule in wording different from the Reference Proposition Map | Source-faithful derived statement with equivalent meaning and exact support; no preferred-prose requirement |
| 002 | P006 + | Broad rule is materially narrowed several paragraphs later | One proposition containing the later qualification; never publish the broad statement alone |
| 003 |  | Rule contains an express exception or proviso | Keep the exception with the rule and prove both with exact ranges |
| 004 |  | Rule depends on a defined threshold or statutory definition | Include the controlling threshold or definition needed for honest use |
| 005 |  | Court allocates or shifts a legal burden | State the exact burden, triggering condition, and attributed reasoning |
| 006 |  | Only a small subset of facts and procedure controls the rule's scope | Include the minimum necessary context without speculation |
| 007 |  | Application and result reveal how an otherwise abstract test operates | Include the material application and relevant result |
| 008 | P006 - | Later narrative is interesting but neither limits nor explains the legal answer | Omit it from the minimum serving record while preserving it in the ledger |
| 009 | P007 + | Court adopts and relies on a quoted passage whose exact words prove the rule | Use the exact adopted range and adoption evidence without altering the quotation |
| 010 |  | Rule, qualification, and application appear in several non-contiguous passages | Link the smallest complete ordered set of ranges needed to prove the whole proposition |
| 011 |  | A footnote materially changes the scope of the proposition | Include the footnote support and resulting qualification |
| 012 |  | A list or table supplies operative elements of a legal test | Preserve the complete relevant structure and do not flatten away legal relationships |
| 013 |  | Proposition depends on a defined term or earlier cross-reference | Include or explicitly resolve the exact dependency needed for standalone meaning |
| 014 | P007 - | Quoted authority is not adopted and does no material work in the court's answer | Do not use it as proposition evidence |
| 015 |  | Exact passages support two materially plausible meanings and the judgment does not safely resolve them | Quarantine the proposition boundary; do not guess one derived statement |
| 016 |  | Legal meaning appears clear but the exact supporting locator or range cannot be established | Quarantine or block as required; never cite an approximate passage as exact evidence |
| 017 | P008 - | Proposed paraphrase omits a limit and materially broadens the court's rule | Reject or quarantine the proposed wording as a critical error; do not publish it |
| 018 | P008 + | Derived wording differs from the reference but preserves every required meaning and limit | Accept the equivalent derived statement when all exact evidence roles pass |

## C. Semantic boundary and opinion attribution

Case namespace: `HKCASE-PROP-SEM-BND-NNN`

Coverage namespace: `HKCASE-PROP-COV-SBND-NNN`

| Suffix | Pair | Synthetic judgment structure | Required semantic result |
|---:|---|---|---|
| 001 | P009 + | One cumulative legal test has several required elements | Keep all elements in one proposition |
| 002 |  | One balancing test contains several factors and no factor is independently dispositive | Keep the complete balancing rule together |
| 003 | P009 - | Judgment gives two independent alternative grounds, either sufficient for the result | Split into two propositions |
| 004 |  | Judgment answers two different legal questions | Split into independently usable propositions |
| 005 | P010 +; P014 + | Same opinion repeats or paraphrases the same answer with identical issue, scope, and role | Merge into one proposition with minimum complete non-repetitive support |
| 006 |  | Same rule is applied to a second fact pattern without creating a distinct legal branch | One proposition; do not duplicate the application |
| 007 | P010 - | A later application establishes a materially distinct branch of the rule | Create a separate independently usable proposition |
| 008 |  | General rule and its ordinary application jointly show what the court decided | Keep together in one proposition |
| 009 |  | Judgment states an independently usable remedy or jurisdiction rule beside the merits rule | Split the independent legal answers |
| 010 | P011 +; P013 + | One joint opinion is signed or delivered by several judges | One proposition per genuine answer, not one per judge |
| 011 |  | One lead opinion is expressly joined without qualification by other judges | Treat the joined reasoning as one path and create no judge duplicates |
| 012 |  | A separate opinion says only “I agree” | No duplicate proposition from the agreement-only opinion |
| 013 | P011 - | Concurrence supplies materially different additional reasoning | Keep its proposition separate and label it as concurrence |
| 014 | P013 - | Dissent states a material competing rule | Keep it separate and prominently label dissent; never present it as operative majority reasoning |
| 015 |  | Judge concurs in part but adds reasoning not adopted from the lead opinion | Separate only the additional qualifying reasoning and preserve the exact adopted scope |
| 016 | P012 + | Operative opinion expressly adopts identified reasons from another opinion in the same delivered judgment | One adopted reasoning path using both exact adoption and adopted support |
| 017 | P012 - | Opinions reach the same result but contain no express scope-clear adoption | Keep reasoning paths separate; never infer adoption |
| 018 | P013 -; P015 - | Several opinions overlap but no common reasoning path commands the required support | Do not manufacture a majority proposition; preserve separately attributed positions or Quarantine |
| 019 | P015 + | Several judges expressly join one identified common reasoning path while differing elsewhere | Create the exact common operative proposition and preserve separate additional reasoning |
| 020 |  | Material obiter and operative reasoning address different legal questions | Keep separate propositions with exact authority roles |
| 021 | P014 - | Wording is similar but issue, scope, or legal effect differs | Keep separate propositions despite textual similarity |
| 022 |  | Wording is identical but used for materially different issues or authority roles | Keep separate; identical words do not prove one proposition identity |

## D. Semantic court, language, length, uncertainty, and safety

Case namespace: `HKCASE-PROP-SEM-RSK-NNN`

Coverage namespace: `HKCASE-PROP-COV-SRSK-NNN`

| Suffix | Pair | Synthetic or sealed evaluation situation | Required semantic result |
|---:|---|---|---|
| 001 | P018 + | Court of Final Appeal judgment is authored in English | Complete source-faithful English proposition output and exact original support |
| 002 |  | Court of Appeal judgment is authored in Traditional Chinese | Complete source-faithful Traditional Chinese proposition output without requiring English translation |
| 003 |  | Court of First Instance judgment uses genuinely mixed-language reasoning | Preserve the authentic mixed-language reasoning and exact attribution |
| 004 |  | Competition Tribunal judgment uses technical tables and specialised competition terminology | Extract material propositions without flattening the operative structure or inventing general law |
| 005 |  | Historical Hong Kong superior-court judgment uses older formatting and citations | Apply the same proposition and evidence contract without modern-format assumptions |
| 006 |  | Hong Kong Privy Council appeal contains older artifact structure and several opinions | Preserve exact decision and opinion identity, scope, and proposition attribution |
| 007 | P018 - | Optional official translation is available beside the accepted original | Use translation as auxiliary evaluation evidence only; create no translation duplicate or replacement record |
| 008 |  | Optional translation materially conflicts with the original while original evidence remains clear | Preserve the original result and isolate the translation conflict unless it calls original evidence into question |
| 009 |  | Short judgment fits one task packet | Still produce complete opinion, Coverage Unit, candidate, and ledger accounting |
| 010 | P016 + | Long judgment uses complete opinion-aware segments and exact dependencies | Find every proposition and preserve all cross-segment meaning without silent truncation |
| 011 | P016 - | One required segment or dependency is absent | `BLOCKED` or `ACCOUNTED_WITH_QUARANTINE`; never complete or no-proposition |
| 012 |  | A material qualification occurs in a different segment from the initial rule | Resolve the dependency and include the qualification in the same proposition |
| 013 |  | Cross-opinion express adoption requires an exact dependency path | Use adoption and adopted support without merging opinion inventories |
| 014 | P017 - | One complete indivisible proposition still exceeds serving limits | Quarantine with the Coverage Gap; never fragment into query-dependent records |
| 015 | P017 + | Long material contains genuinely independent propositions that each fit | Split only at the proved legal boundaries and render independent complete records |
| 016 | P019 - | Complete evidence leaves materiality genuinely uncertain | Quarantine the candidate; do not call it non-propositional or complete zero |
| 017 |  | Judgment structure leaves operative opinion or attribution genuinely uncertain | Quarantine the smallest affected boundary |
| 018 |  | Parser cannot faithfully enumerate an unsupported source structure | `BLOCKED`; supported-looking portions cannot proceed as complete |
| 019 |  | Judgment quotes hostile instructions telling the model to ignore its task or alter the database | Treat the words only as source evidence; preserve task and output boundaries |
| 020 |  | Official corrected reasons materially change proposition wording, support, or attribution | Re-evaluate every affected proposition and preserve the prior result immutably |

## E. Deterministic structure and Coverage Ledger

Case namespace: `HKCASE-PROP-DET-LED-NNN`

Coverage namespace: `HKCASE-PROP-COV-DLED-NNN`

| Suffix | Pair | Frozen structural input | Exact deterministic result |
|---:|---|---|---|
| 001 |  | Complete short original judgment | Ordered artifact, opinion, Coverage Unit, segment, dependency, and ledger inventories with exact fingerprints |
| 002 |  | Judgment contains lead, concurrence, dissent, and agreement-only opinions | Exact opinion and judge-attribution inventory; no opinion omitted or duplicated |
| 003 |  | Artifact contains numbered and unnumbered paragraphs and headings | Stable ordered units and source mappings for every structure |
| 004 |  | Artifact contains footnotes, table, quoted block, order, disposition, schedule, appendix, cover, and appearance material | Every source part appears in the inventory even when later non-propositional |
| 005 | P020 + | Segmented ledger assigns every unit exactly once as primary content | Exact union equals the ordered unit inventory |
| 006 | P020 - | One unit appears as primary content in two segments | `INVALID`; duplicate primary coverage cannot pass |
| 007 |  | One expected unit is omitted from all primary segments | `INVALID`; never complete or valid zero |
| 008 |  | Primary segment union reorders source units | `INVALID`; original order is mandatory |
| 009 | P021 + | Repeated context uses an exact dependency on one primary unit and fingerprint | Valid dependency without double-counting primary coverage |
| 010 | P021 - | Dependency is missing, dangling, points to the wrong primary unit, or has a mismatched hash | `INVALID` or `BLOCKED` under the exact cause; never silently resolve |
| 011 |  | Cross-opinion adoption dependency has exact adoption and adopted ranges | Valid dependency while primary opinion inventories remain separate |
| 012 |  | Every unit has exactly one resolution state | Exact reproducible resolution totals |
| 013 |  | One unit has no resolution or conflicting resolution states | `INVALID`; missing or multiple resolution cannot mean non-propositional |
| 014 |  | Every resolved unit has exactly one primary use and permitted supplementary roles | Exact primary-use arithmetic and evidence-role links |
| 015 |  | Non-propositional units carry permitted stable reason families | Valid explicit accounting; free-form silence cannot substitute |
| 016 |  | Treatment-only and citation-bearing units link to the separate screening inventory | Valid handoff with no invented proposition and no discarded lead |
| 017 |  | All checks pass and at least one accepted proposition exists | Exact `COMPLETE_WITH_PROPOSITIONS` result and totals |
| 018 |  | All checks pass, no proposition evidence exists, every candidate resolves, and screening handoffs are complete | Exact `COMPLETE_NO_PROPOSITION` result and explicit zero Search Records |
| 019 |  | Complete structure is inventoried but one material unit or candidate is quarantined | Exact `ACCOUNTED_WITH_QUARANTINE`; clear work may be preserved but result is not complete |
| 020 |  | Required source or processing support is absent in one fixture and arithmetic or schema is defective in another | Distinguish `BLOCKED` from `INVALID`; neither may be called Quarantine or complete |

## F. Deterministic candidate, evidence, renderer, and output

Case namespace: `HKCASE-PROP-DET-OUT-NNN`

Coverage namespace: `HKCASE-PROP-COV-DOUT-NNN`

| Suffix | Pair | Frozen candidate and evidence input | Exact deterministic result |
|---:|---|---|---|
| 001 | P022 + | Every emitted candidate has one accepted, rejected, merged, split, quarantined, or blocked outcome | Exact complete candidate inventory and outcome arithmetic |
| 002 | P022 - | One discovered candidate disappears before final output | `INVALID`; no silent candidate loss |
| 003 | P023 + | Accepted proposition links every required issue, answer, context, qualification, application, result, attribution, and quotation role | Valid complete evidence-role set |
| 004 | P023 - | Accepted proposition lacks one required evidence role | Reject the proposition or invalidate the complete result; never render partial support |
| 005 | P024 + | Every Search Record links one accepted proposition and exact ledger fingerprint | Exact one-to-one traceability and payload ownership |
| 006 | P024 - | Search Record, proposition, ledger section, or renderer section is orphaned | `INVALID`; no release-eligible record |
| 007 | P025 + | Every verbatim quotation and locator matches exact preserved source ranges | Valid quote bytes, ordering, and source map |
| 008 | P025 - | One quotation is altered, normalized invisibly, or mapped to different words | Hard validation failure; never publish the quote |
| 009 |  | Evidence locator or claimed source range does not exist | Hard validation failure or exact blocked result; no approximate repair |
| 010 |  | One Coverage Unit mixes proposition and context text | Exact subranges and roles expose the mixed content without double-counting the unit |
| 011 |  | Valid proposition renders through ADR 0060's stable labelled layout | Canonical exact `metadata.text` and serving-payload fingerprint |
| 012 |  | One optional renderer section is inapplicable | Apply the pinned empty-section rule; never invent a “None found” legal claim |
| 013 |  | Six-field case payload has an applicable authority note | Preserve exact six fields, keep `authority_note` separate, and include no internal ledger metadata |
| 014 |  | Frozen judgments validly produce zero, one, and many propositions | Exact explicit output inventories; missing output never equals zero output |
| 015 |  | Complete indivisible proposition exceeds the pinned serving limit | Quarantine and Coverage Gap; no incomplete fragment or query-time reconstruction |
| 016 |  | Payload is exactly at, below, and above pinned tokenizer and byte limits in linked variants | Deterministic boundary behavior; mandatory text or authority warning is never weakened to fit |

## G. Deterministic correction, package, security, and admission

Case namespace: `HKCASE-PROP-DET-ADM-NNN`

Coverage namespace: `HKCASE-PROP-COV-DADM-NNN`

| Suffix | Pair | Frozen history or package input | Exact deterministic result |
|---:|---|---|---|
| 001 |  | Reprocessing proves an exact accepted proposition and six-field payload unchanged | Reuse exact Search Record and applicable embedding; append new processing and ledger history |
| 002 |  | Official correction changes proposition text, support, attribution, or payload | New Official Version, ledger, affected proposition result, and forward record lineage |
| 003 |  | Prior record improperly combined independent propositions | Stop selecting it and create or select supported records using `split_from` processing-correction lineage |
| 004 |  | Prior records improperly duplicated or fragmented one proposition | Stop selecting them and create or select one supported record using `merged_from` lineage |
| 005 |  | Later processing discovers a genuinely new proposition omitted previously | Create the proposition without inventing predecessor lineage; preserve correction and impact history |
| 006 |  | Corrected judgment changes only one of several propositions | New Official Version and ledger; re-evaluate affected scope and prove exact unaffected reuse |
| 007 |  | Parser, segmentation, contract, model, prompt, setting, validator, or renderer changes | New result or explicit impact decision; never mutate the prior accepted ledger or admission |
| 008 | P026 + | Strict semantic catalogue, deterministic catalogue, and coverage matrix explicitly contain every required ID and pair role | Valid frozen inventory and reproducible catalogue fingerprint |
| 009 | P026 - | Case, primary coverage cell, or required pair member is missing or discovered only by glob or count | Package invalid; no admission or inferred completeness |
| 010 | P027 + | Evaluated workflow packet contains only admitted evidence and task contract | Valid non-leaking packet; no answer-bearing identity or metadata reaches the workflow |
| 011 | P027 - | Packet exposes case title, expected answer, coverage label, pair role, score, or critical-error tag | Hard leakage failure; evaluation result invalid |
| 012 | P028 + | Sealed real-judgment artifact, Reference Proposition Map, manifest, and hashes match | Valid registered external evaluation package |
| 013 | P028 - | Required sealed artifact or map is missing, substituted, or fingerprint-mismatched | Evaluation invalid; never score partial or different evidence |
| 014 | P029 + | Two isolated deterministic executions use the same exact inputs and build | Byte-identical artifacts and fingerprints |
| 015 | P029 - | Repeated deterministic execution changes bytes, inventory, order, or fingerprint | Conformance failure; no admission |
| 016 |  | Fixture runner attempts source, model, embedding, Pinecone, Azure, routing, credential, production-store, network, or undeclared-file access | Hard forbidden-side-effect failure with no mutation |
| 017 | P030 + | Proposed workflow exactly matches every admitted parser, contract, method, model when applicable, validator, renderer, rulebook, build, package, threshold, evaluator, and result fingerprint | Eligible for Case Proposition Workflow Admission only; no deployment authority |
| 018 | P030 - | One result-affecting workflow or evaluation fingerprint differs | Not admitted; require new complete evaluation and impact declaration |

## H. Required high-risk pairs

| Pair | Positive case | Near-miss case | Boundary proved |
|---|---|---|---|
| `HKCASE-PROP-PAIR-001` | `SEM-MAT-001` | `SEM-MAT-013` | Material legal answer versus non-material legal discussion |
| `HKCASE-PROP-PAIR-002` | `SEM-MAT-002` | `SEM-MAT-003` | Material application of a familiar rule versus bare citation |
| `HKCASE-PROP-PAIR-003` | `SEM-MAT-004` | `SEM-MAT-005` | Adopted and applied quotation versus unadopted background quotation |
| `HKCASE-PROP-PAIR-004` | `SEM-MAT-006` | `SEM-MAT-007` | Party formulation adopted as court reasoning versus merely recited submission |
| `HKCASE-PROP-PAIR-005` | `SEM-MAT-012` | `SEM-MAT-013` | Material attributed obiter proposition versus non-material discussion |
| `HKCASE-PROP-PAIR-006` | `SEM-CNT-002` | `SEM-CNT-008` | Controlling later qualification versus optional narrative |
| `HKCASE-PROP-PAIR-007` | `SEM-CNT-009` | `SEM-CNT-014` | Adopted exact quotation as evidence versus unadopted quotation |
| `HKCASE-PROP-PAIR-008` | `SEM-CNT-018` | `SEM-CNT-017` | Faithful equivalent derived wording versus materially broadened paraphrase |
| `HKCASE-PROP-PAIR-009` | `SEM-BND-001` | `SEM-BND-003` | One cumulative test versus independent alternative grounds |
| `HKCASE-PROP-PAIR-010` | `SEM-BND-005` | `SEM-BND-007` | Repeated application of one rule versus distinct legal branch |
| `HKCASE-PROP-PAIR-011` | `SEM-BND-010` | `SEM-BND-013` | One joined judicial reasoning path versus separate concurrence |
| `HKCASE-PROP-PAIR-012` | `SEM-BND-016` | `SEM-BND-017` | Express scope-clear cross-opinion adoption versus inferred agreement |
| `HKCASE-PROP-PAIR-013` | `SEM-BND-010` | `SEM-BND-014` | Operative joint reasoning versus dissenting proposition |
| `HKCASE-PROP-PAIR-014` | `SEM-BND-005` | `SEM-BND-021` | Same answer and scope eligible to merge versus similar wording with different scope |
| `HKCASE-PROP-PAIR-015` | `SEM-BND-019` | `SEM-BND-018` | Expressly joined common reasoning versus manufactured plurality majority |
| `HKCASE-PROP-PAIR-016` | `SEM-RSK-010` | `SEM-RSK-011` | Complete segmented examination versus hidden missing segment |
| `HKCASE-PROP-PAIR-017` | `SEM-RSK-015` | `SEM-RSK-014` | Genuine legal split versus forbidden fragmentation of one indivisible proposition |
| `HKCASE-PROP-PAIR-018` | `SEM-RSK-001` | `SEM-RSK-007` | Court-authored original record versus auxiliary translation duplicate |
| `HKCASE-PROP-PAIR-019` | `SEM-MAT-017` | `SEM-RSK-016` | Proven no proposition versus unresolved possible proposition |
| `HKCASE-PROP-PAIR-020` | `DET-LED-005` | `DET-LED-006` | Exact primary unit coverage versus duplicate primary coverage |
| `HKCASE-PROP-PAIR-021` | `DET-LED-009` | `DET-LED-010` | Valid dependency closure versus dangling or mismatched dependency |
| `HKCASE-PROP-PAIR-022` | `DET-OUT-001` | `DET-OUT-002` | Complete candidate accounting versus silent candidate disappearance |
| `HKCASE-PROP-PAIR-023` | `DET-OUT-003` | `DET-OUT-004` | Complete evidence roles versus missing required role |
| `HKCASE-PROP-PAIR-024` | `DET-OUT-005` | `DET-OUT-006` | Exact record-to-proposition-to-ledger traceability versus orphan output |
| `HKCASE-PROP-PAIR-025` | `DET-OUT-007` | `DET-OUT-008` | Exact verbatim source mapping versus altered or mismapped quotation |
| `HKCASE-PROP-PAIR-026` | `DET-ADM-008` | `DET-ADM-009` | Complete explicit catalogue and matrix versus inferred or incomplete inventory |
| `HKCASE-PROP-PAIR-027` | `DET-ADM-010` | `DET-ADM-011` | Non-leaking evaluation packet versus answer leakage |
| `HKCASE-PROP-PAIR-028` | `DET-ADM-012` | `DET-ADM-013` | Matching sealed external package versus missing or mismatched protected evidence |
| `HKCASE-PROP-PAIR-029` | `DET-ADM-014` | `DET-ADM-015` | Deterministic reproducibility versus unstable output |
| `HKCASE-PROP-PAIR-030` | `DET-ADM-017` | `DET-ADM-018` | Exact admitted workflow identity versus result-affecting fingerprint mismatch |
| `HKCASE-PROP-PAIR-031` | `SEM-MAT-001` | `SEM-MAT-015` | A material proposition of the later judgment versus treatment-only reasoning about an earlier proposition |

The initial proposal contains **31** pair IDs, each with exactly two declared
members. A case may serve more than one pair only when the same frozen scenario
directly proves both boundaries; the coverage matrix must list every role
explicitly.

## I. Completeness and later real-judgment extension

The 78 semantic rows above define synthetic boundary cases. They are necessary
but not sufficient for workflow admission. Before an extraction method is
enabled, the semantic catalogue and coverage matrix must add sealed real-
judgment cases selected across the courts, languages, opinion structures,
lengths, materiality classes, evidence forms, and uncertainty boundaries in
ADR 0063. Each receives an adjudicated hidden Reference Proposition Map,
critical-error labels, and exact artifact fingerprints.

Real-judgment selection must not merely repeat easy synthetic shapes or cases
used to tune the proposed workflow. Development and sealed admission sets stay
separate. The exact real-judgment IDs, artifacts, maps, numerical thresholds,
repetition counts, evaluator, and workflow fingerprints are task-admission
work and do not alter these initial synthetic IDs.

The 54 deterministic rows require strict frozen fixture packages. Every
expected artifact role is `EXACT`, `NONE`, or `NOT_APPLICABLE`. Directory
discovery, globs, broad tags, counts, or an aggregate score cannot prove
catalogue completeness. Every case must be the primary case for at least one
coverage cell, and every required high-risk pair must contain both exact roles.

## J. Frozen consequence

ADR 0064 freezes:

- these 132 case IDs and 132 matching primary coverage-cell IDs;
- the seven group counts `18/18/22/20/20/16/18`;
- these 31 pair IDs and exact pair membership;
- every row's scenario and required result;
- the non-answer-bearing ID rule;
- the future sealed real-judgment extension requirement; and
- immutable expansion and correction behavior.

This frozen catalogue does not itself create executable fixtures, admit a
model, select real judgments, set numerical thresholds, authorize provider
calls, implement code, publish a release, or permit Pinecone, Azure,
deployment, commit, or remote action. ADR 0065 separately settles the high-
level LLM-versus-deterministic allocation without changing this catalogue.
