# Hong Kong Case Treatment Conformance Catalogue

Status: **Accepted and frozen by ADR 0059**

Updated: 2026-08-13

> ADR 0058 is incorporated. The catalogue now directly covers optional
> treating-proposition linkage, one-edge/two-view projection, and correction-
> driven reverse impact without adding Pinecone treatment records.

The design-level completeness audit in
[`HONG_KONG_CASE_TREATMENT_DESIGN_AUDIT.md`](HONG_KONG_CASE_TREATMENT_DESIGN_AUDIT.md)
corrected omitted boundaries and non-exact result rows. This revised table is
the accepted post-audit catalogue.

This document is the accepted exact initial coverage-cell and case table for
Hong Kong later treatment under ADRs 0056 through 0059. It freezes legal and
technical scenarios, not executable JSON, judgment bytes, model settings,
numerical thresholds, prompts, provider choices, or production actions.

The table contains **155 direct cases and 155 matching primary coverage
cells**:

| Suite and checkpoint | Cases |
|---|---:|
| Semantic whole-judgment discovery | 13 |
| Semantic candidate analysis | 40 |
| Deterministic validation and package safety | 32 |
| Deterministic Legal Desk decision and routing | 22 |
| Deterministic authority-note rendering | 14 |
| Deterministic record, embedding, lineage, and selection | 12 |
| Deterministic release, update, and promotion boundary | 22 |
| **Total** | **155** |

The number is the result of direct branch coverage. It was not selected as a
target. Each row is one primary case and one matching primary coverage cell.
A later requirement adds a case and cell; unrelated rows are not merged merely
to preserve this count.

## Exact ID expansion

Within each table, the three-digit suffix expands to the full case and coverage
IDs shown in the heading. For example, semantic discovery row `008` means:

- case `HKCASE-TREAT-SEM-DIS-008`; and
- coverage cell `HKCASE-TREAT-COV-SDIS-008`.

The pair column uses `Pnnn +` for the `POSITIVE` member and `Pnnn -` for the
`NEAR_MISS` member. It expands to `HKCASE-TREAT-PAIR-NNN`. A blank pair cell
means direct ordinary coverage rather than a required high-risk pair.

Every row must eventually have one strict package and exact expected artifacts
under ADR 0057. The model never receives row IDs, descriptions, pair data, or
expected results.

## A. Semantic whole-judgment discovery

Case namespace: `HKCASE-TREAT-SEM-DIS-NNN`

Coverage namespace: `HKCASE-TREAT-COV-SDIS-NNN`

| Suffix | Pair | Synthetic evidence | Required structured discovery result |
|---:|---|---|---|
| 001 |  | Short operative judgment with no earlier-authority reference | Complete opinion and segment ledger; empty candidate inventory; no claim beyond supplied evidence |
| 002 |  | Several bare formal citations and no treatment-bearing reasoning | Inventory every citation lead with exact opinion and passages; discovery does not invent substantive treatment |
| 003 |  | One formal citation accompanied by express material treatment | One treatment candidate bound to the exact passage, cited decision lead, and operative opinion |
| 004 |  | Material treatment expressed through an unusual implicit reference without a conventional formal citation | Preserve a candidate and unresolved identity path; keyword or citation absence does not suppress it |
| 005 |  | Many cited decisions, only one materially treated | Account for every citation; distinguish the material candidate from bare-citation leads without dropping either |
| 006 |  | Majority and dissent separately discuss the same earlier authority | Produce separately attributed candidates; never merge the dissent into the operative majority |
| 007 |  | Judgment creates no proposition of its own but expressly affects an older proposition | Discover the outgoing treatment candidate despite zero new proposition output |
| 008 | P001 + | Long judgment split at opinion-aware boundaries; treatment meaning requires a cross-reference and context from another declared segment | Complete coverage ledger and one correctly contextualised candidate; no silent truncation |
| 009 | P001 - | Same shape as row 008 but one required segment is absent | Mark discovery incomplete; do not emit a supported no-treatment conclusion or silently accept the partial inventory |
| 010 |  | Citation words cannot be resolved to one registered judgment | Preserve one unmatched or ambiguous lead with exact words and passages; do not guess identity |
| 011 |  | Corrected reasons add, remove, and alter treatment-bearing passages relative to the accepted prior Official Version | Produce a complete added, removed, changed, and unchanged candidate-inventory comparison; decide no legal effect |
| 012 |  | Complete Traditional Chinese judgment expresses treatment in ordinary Chinese judicial language | Discover and locate the candidate without requiring an English translation or English magic phrase |
| 013 |  | Genuinely mixed-language opinion uses English citation material and Traditional Chinese reasoning | Preserve original language, opinion boundaries, context, and one correctly located candidate |

## B. Semantic candidate analysis

Case namespace: `HKCASE-TREAT-SEM-ANA-NNN`

Coverage namespace: `HKCASE-TREAT-COV-SANA-NNN`

| Suffix | Pair | Synthetic evidence | Required structured semantic proposal |
|---:|---|---|---|
| 001 | P002 - | Operative majority merely cites an earlier proposition | `CITED_ONLY`; no endorsement, material explanation, or authority-strength claim |
| 002 | P002 + | Operative majority expressly adopts and follows the exact earlier proposition | `FOLLOWED`, `EXPRESS`, exact whole-proposition mapping |
| 003 |  | Operative majority materially clarifies the meaning and limits of an earlier proposition without endorsing it | `EXPLAINED`, neutral material context, exact scope; not support |
| 004 |  | Court necessarily applies an earlier proposition to reach its result without an express treatment phrase | `APPLIED`, `NECESSARY_REASONING`, exact reasoning chain and proposition mapping |
| 005 |  | Operative majority expressly states that the earlier proposition is correct and approved | `APPROVED`, `EXPRESS`, exact proposition and passages |
| 006 | P003 - | Court distinguishes only the different facts and leaves the earlier proposition unchanged | `DISTINGUISHED`, fact-specific, non-limiting; no warning implication |
| 007 | P003 + | Court's distinction materially narrows when the earlier proposition may be relied upon | `LIMITED`, exact limitation and scope; do not leave the class as an implementation choice |
| 008 |  | Operative majority expressly doubts an exact proposition | `DOUBTED`, `EXPRESS`, exact affected proposition and scope |
| 009 | P004 + | Operative majority expressly criticises an exact proposition | `CRITICISED`, `EXPRESS`, operative-majority attribution |
| 010 | P004 - | Dissent uses the same criticism while the majority does not adopt it | `CRITICISED` with dissent attribution and non-operative status; never majority treatment |
| 011 |  | Operative majority expressly disapproves an exact proposition | `DISAPPROVED`, `EXPRESS`, exact scope and authority facts |
| 012 |  | Operative majority expressly refuses to follow an exact proposition | `REFUSED_TO_FOLLOW`, `EXPRESS`, exact scope and authority facts |
| 013 | P005 + | Authoritative operative majority expressly and conclusively overrules the whole exact proposition | `OVERRULED`, `EXPRESS`, whole scope, controlling opinion and court facts |
| 014 | P005 - | Lower court says binding superior authority is wrong and should not be followed | Preserve the adverse class and exact lower-court attribution, but never propose operative overruling power |
| 015 |  | Unadopted concurrence expressly criticises the proposition | Preserve concurrence attribution and non-operative status; never majority treatment |
| 016 |  | Plurality reasons contain adverse language but no controlling common position | Preserve plurality attribution and unresolved operative effect; never whole-court overruling |
| 017 |  | Foreign court expressly rejects the proposition | Preserve foreign jurisdiction and adverse treatment; never represent it as Hong Kong overruling |
| 018 | P006 + | Adoption follows necessarily from the complete reasoning but the judgment uses no express approval words | `FOLLOWED`, `NECESSARY_REASONING`; evidence chain must make adoption necessary |
| 019 | P006 - | Same necessary reasoning as row 018 is submitted as `APPROVED` | `FOLLOWED`, `NECESSARY_REASONING`; reject express-only `APPROVED` rather than returning an alternative set |
| 020 |  | Two materially plausible treatment readings remain after complete context | `UNRESOLVED`; record both bounded interpretations and uncertainty, not model-selected certainty |
| 021 | P007 + | Later court expressly overrules only one of three separately supported earlier propositions | Exact partial mapping to the one proposition; other propositions remain outside the treatment scope |
| 022 | P007 - | Adverse passage can be bounded to two possible propositions but cannot be mapped more exactly | `UNRESOLVED` bounded set containing exactly those propositions; no case-wide label |
| 023 |  | Adverse passage cannot be bounded across the required current proposition universe | `UNRESOLVED` unbounded scope and treatment-gap signal; no guessed target |
| 024 |  | Treatment applies only to a stated factual situation | Fact-specific scope with exact facts and proposition; do not generalise it |
| 025 |  | Treatment applies only to one identified legal issue within a broader proposition | Issue-specific scope and exact issue; preserve unaffected scope |
| 026 |  | Treatment concerns only procedure and not the substantive proposition | Procedural scope; do not alter substantive treatment |
| 027 |  | Case-level adverse discussion cannot be mapped to one proposition but the smallest affected set is known | Preserve that smallest bounded set and uncertainty; never spread treatment to every proposition in the case |
| 028 |  | Later appellate judgment affirms the earlier disposition without separately treating every proposition | `AFFIRMED` as appellate disposition; no automatic `APPROVED` or whole-case support label |
| 029 |  | Later appellate judgment varies part of the earlier order | `VARIED` as disposition with exact affected part; reopen proposition review without automatic treatment labels |
| 030 |  | Later appellate judgment reverses the result | `REVERSED` as disposition; identify propositions requiring review, not automatic whole-case retirement |
| 031 |  | Later appellate judgment sets aside the decision | `SET_ASIDE` as disposition; identify affected propositions and uncertainty separately |
| 032 |  | Later appellate judgment remits the matter | `REMITTED` as disposition; do not infer approval, rejection, or retirement |
| 033 |  | Traditional Chinese candidate packet expresses criticism and scope without English treatment terminology | Correct structured class, scope, passages, and original-language evidence |
| 034 |  | Mixed-language candidate packet contains English quotation and Chinese operative reasoning | Classify from the complete operative reasoning and preserve language and passage attribution |
| 035 |  | Untrusted summary says “overruled,” but the accepted judgment passages do not | Do not invent supporting passages or propose `OVERRULED`; use only accepted judgment evidence |
| 036 |  | Similar case names and citations point to two possible earlier identities | Preserve unresolved identity and do not map the proposal to the convenient record |
| 037 |  | Corrected reasons remove an earlier adverse passage but provide no affirmative reinstatement evidence | Propose a changed or removed relationship requiring new decision; never automatic reinstatement |
| 038 |  | Later judgment restates background without materially clarifying or endorsing the proposition | Preserve non-material explanation internally; materiality false and no LLM-facing context recommendation |
| 039 | P020 + | The operative majority itself expressly and conclusively overrules the exact earlier proposition | `OVERRULED`, `EXPRESS`, exact proposition, court, opinion, and passages |
| 040 | P020 - | The same adverse words appear only inside a quoted party submission or instruction-like source passage that the court does not adopt | Preserve the quoted reference with non-operative attribution; no `OVERRULED` judicial-treatment proposal and no obedience to source-text instructions |

## C. Deterministic validation and conformance-package safety

Case namespace: `HKCASE-TREAT-DET-VAL-NNN`

Coverage namespace: `HKCASE-TREAT-COV-DVAL-NNN`

| Suffix | Pair | Frozen input | Exact deterministic result |
|---:|---|---|---|
| 001 | P008 + | Schema-valid express-treatment proposal with exact accepted passages, identity, opinion, hierarchy, scope, and complete evidence | Validation pass; preserve proposal for Legal Desk decision; no legal or serving effect yet |
| 002 |  | Necessary-reasoning proposal uses an allowed class and supplies the complete reasoning chain | Validation pass with exact allowed expression-mode constraint |
| 003 | P008 - | Proposal cites a paragraph or words absent from the accepted artifact | Reject as fabricated evidence; critical error; no repair, decision, note, record, or release effect |
| 004 |  | Proposal maps to an identity inconsistent with supplied citation, aliases, and register facts | Reject wrong identity; preserve unresolved evidence; no convenient remapping |
| 005 |  | Proposal says a lower court overruled binding superior authority | Reject impossible hierarchy consequence while preserving the attributed adverse statement |
| 006 |  | Proposal attributes dissenting words to the operative majority | Reject opinion inversion as a critical error |
| 007 |  | Proposal uses `APPROVED`, `DOUBTED`, or another express-only class with necessary-reasoning mode | Reject the forbidden class/expression combination; do not silently relabel without a new proposal or rule |
| 008 |  | Proposal contains unknown field, enum, missing required field, or wrong schema version | Structural rejection; unknown content is never ignored for compatibility |
| 009 |  | Exact cited sentence exists, but required surrounding qualification and result context are absent | Reject with the exact incomplete-evidence result; no treatment decision or semantic conclusion from the isolated sentence |
| 010 |  | Whole-judgment discovery claims completion but the opinion-aware coverage ledger omits one supplied segment | Reject completeness claim; no supported no-treatment result |
| 011 |  | HKLII label and summary are supplied without the accepted originating judgment | Discovery work only; no legal-effect validation, note, retirement, or reinstatement |
| 012 |  | Treating judgment identity is known but accepted originating text is missing | Treatment Coverage Gap; no substantive validation |
| 013 |  | Earlier judgment or exact proposition evidence is missing | Preserve unresolved target and Coverage Gap; no treatment consequence |
| 014 |  | Strict synthetic package has exact schema, declared files, safe paths, matching hashes, and known contracts | Package validation pass; execution restricted to declared inputs and pinned contracts |
| 015 |  | Row 014 plus one unknown manifest property | Reject strict manifest; unknown property is not ignored |
| 016 |  | Declared artifact bytes do not match SHA-256 | Reject package before execution |
| 017 |  | Runner attempts to read an undeclared local file | Reject and record forbidden access; undeclared content cannot affect the result |
| 018 |  | Package declares absolute path, `..`, symlink, URI, or platform-specific escape | Reject unsafe path or retrieval declaration before execution |
| 019 | P009 + | Constructed semantic model packet contains only admitted evidence and task contract | Packet validation pass; no package, answer, score, or coverage metadata present |
| 020 | P009 - | Model packet includes case ID, title, pair, coverage label, expected result, score, or critical-error tag | Reject answer-leaking packet before provider admission |
| 021 | P010 + | Sealed external artifact identity and every declared fingerprint match | External evaluation artifact admission pass without copying protected bytes into Git |
| 022 | P010 - | Registered external artifact is missing, moved without proof, or hash-mismatched | Block evaluation case; never substitute another judgment or stale answer |
| 023 | P011 + | Fixture explicitly declares an applicable role as `NONE` with zero count and no-artifact assertion | Accept exact zero output after semantic validation of the role |
| 024 | P011 - | Expected file is absent but the manifest does not declare valid `NONE` | Fail fixture; missing output cannot masquerade as zero output |
| 025 | P012 + | Frozen catalogue explicitly lists every unique required case and matching package fingerprint | Catalogue completeness pass |
| 026 | P012 - | Catalogue has duplicate ID, missing required case, unaccounted package, range, glob, or dynamic discovery dependency | Catalogue completeness failure |
| 027 | P013 + | Coverage matrix gives every required cell a direct primary case and both members of every high-risk pair | Coverage completeness pass |
| 028 | P013 - | Required cell lacks a primary case, case has no primary cell, or high-risk pair has one member | Coverage completeness failure; aggregate score cannot cure it |
| 029 | P014 + | Two isolated clean deterministic executions produce identical declared artifacts and reports | Reproducibility pass after semantic and schema validation |
| 030 | P014 - | Clean executions differ in bytes, ordering, identity allocation, arithmetic, or report | Reproducibility failure; no attestation |
| 031 |  | Resolved relationship has complete treating decision, version, opinion, judges, passages, and one exact treated proposition, but the treating judgment validly produced no searchable proposition | Accept the relationship with no treating-proposition link; never invent a proposition merely to anchor treatment |
| 032 |  | Candidate attempts to store one resolved relationship with two distinct treated proposition IDs | Reject the multi-target resolved edge and create no relationship; any later separate proposals or unresolved lead require their own validated input |

## D. Deterministic Legal Desk decision and review routing

Case namespace: `HKCASE-TREAT-DET-DEC-NNN`

Coverage namespace: `HKCASE-TREAT-COV-DDEC-NNN`

| Suffix | Pair | Frozen validated treatment facts | Exact decision and route |
|---:|---|---|---|
| 001 |  | `CITED_ONLY`, operative majority, exact mapping | Internal relationship only; no authority-note clause or authority-strength inference |
| 002 |  | Material `EXPLAINED`, operative majority, exact mapping | Eligible neutral context; never support |
| 003 |  | Material `APPLIED`, permitted expression mode, exact mapping | Eligible support under rulebook materiality rule |
| 004 |  | Material `FOLLOWED`, permitted expression mode, exact mapping | Eligible support and ordinary automatic reporting |
| 005 |  | Express material `APPROVED`, exact mapping | Eligible support and ordinary automatic reporting |
| 006 |  | Pure factual `DISTINGUISHED` with no safe-use limitation | Internal relationship only; no warning |
| 007 |  | Material `LIMITED` treatment narrows safe reliance | Mandatory warning with exact affected scope |
| 008 |  | Express `DOUBTED`, sufficient operative authority | Mandatory warning; proposition remains potentially usable |
| 009 |  | Express `CRITICISED`, sufficient operative authority | Mandatory warning; proposition remains potentially usable |
| 010 |  | Express `DISAPPROVED`, evidence, authority, finality, and one concrete Source Rulebook consequence code all clear | Apply the fixture's single declared bounded consequence and exact expected artifact; alternative outcomes in one execution and invented retirement are forbidden |
| 011 |  | Express `REFUSED_TO_FOLLOW`, evidence, authority, finality, and one concrete Source Rulebook consequence code all clear | Apply the fixture's single declared bounded consequence and exact expected artifact; alternative outcomes and automatic overruling are forbidden |
| 012 | P015 + | Express conclusive whole `OVERRULED` by authoritative operative court | Exact proposition retirement; no warning-only successor |
| 013 |  | Required uncertainty review is complete and the treatment or mapping remains `UNRESOLVED` | Quarantine the smallest safe affected unit; no guessed serving change |
| 014 |  | Adverse treatment appears only in dissent | Preserve internal attributed relationship; no operative-majority consequence |
| 015 |  | Adverse treatment appears only in unadopted concurrence or non-controlling plurality | Preserve exact opinion relationship; no controlling-court consequence |
| 016 | P015 - | Lower court expressly rejects binding superior authority | Preserve attributed adverse relationship; cannot retire or represent overruling |
| 017 |  | Foreign court rejects Hong Kong proposition | Preserve foreign relationship; no Hong Kong retirement or controlling treatment claim |
| 018 | P021 + | Reversal evidence and the exact consequence rule conclusively establish that only one proposition's current authority was removed | Retire only that exact proposition; preserve unrelated propositions |
| 019 |  | Complete evidence and exact ordinary rule produce a clear bounded consequence | Automatic Legal Desk acceptance plus complete human report; no separate per-treatment approval |
| 020 |  | Competing classes, unsafe mapping, unclear authority, missing rule, or unresolved scope | `UNCERTAINTY_REVIEW`; no automatic acceptance |
| 021 | P016 + | Operative controlling decision changes binding-authority structure or meets every foundational cross-doctrinal high-impact trigger | `EXCEPTIONAL_CHANGE_REVIEW`; LLM does not decide trigger |
| 022 | P021 - | An appellate judgment reverses the result, but the evidence does not establish which earlier proposition, if any, lost current authority | `UNCERTAINTY_REVIEW`; reopen bounded proposition review and make no automatic retirement |

## E. Deterministic authority-note rendering

Case namespace: `HKCASE-TREAT-DET-NTE-NNN`

Coverage namespace: `HKCASE-TREAT-COV-DNTE-NNN`

| Suffix | Pair | Accepted current treatment graph | Exact rendering consequence |
|---:|---|---|---|
| 001 |  | No warning, selected material support, or selected material explanation | Exact case-sensitive `"None"` |
| 002 |  | One selected material explanation and no warning or support | One neutral `[CONTEXT: EXPLAINED]` clause; never support wording |
| 003 |  | One selected material `FOLLOWED` event and no warning | One controlled `[SUPPORT: FOLLOWED]` clause only |
| 004 |  | One current mandatory warning and no selected optional material | Controlled warning clause only |
| 005 |  | Current warning, support, and explanation all fit | Exact order: every warning first, support second, neutral context last |
| 006 |  | Several legally equivalent repetitive support or explanation events | Faithfully consolidate; preserve every event internally; no duplicate clause churn |
| 007 |  | Several legally distinct material events all fit | Include every distinct event; no fixed clause-number cap |
| 008 |  | Same treatment meaning but treating citation or passage reference in the rendered note changes | Exact note bytes and fingerprint change; no traceability-only exception |
| 009 | P017 + | Optional support or context exceeds the remaining budget after faithful consolidation | Apply pinned deterministic ranking and compression; omit only optional meaning and retain it internally |
| 010 |  | Several mandatory warnings are genuinely equivalent | Consolidate without losing any distinct reliance meaning |
| 011 | P017 - | Distinct mandatory warning meanings cannot all fit after faithful consolidation | Exact mandatory-warning-overflow failure; emit no incomplete note or eligible candidate record, leaving the separately tested ADR 0005 serving choice to its own checkpoint |
| 012 |  | Candidate renderer attempts citation count, numeric authority score, or “majority of cases” strength claim | Reject forbidden rendering; counts never substitute for authority analysis |
| 013 |  | Strong support and an existing warning both apply | Preserve warning first and undiminished; support cannot cancel, hide, or soften it |
| 014 |  | A Traditional Chinese Case Proposition requires one material Hong Kong treatment warning | Preserve original-language `metadata.text` and render the complete controlled `metadata.authority_note` in English only |

## F. Deterministic Search Record, embedding, lineage, and selection

Case namespace: `HKCASE-TREAT-DET-REC-NNN`

Coverage namespace: `HKCASE-TREAT-COV-DREC-NNN`

| Suffix | Pair | Accepted current result | Exact immutable transition |
|---:|---|---|---|
| 001 |  | Internal treatment changes but all six serving fields remain byte-exact | Reuse same Search Record and embedding; update internal and release accounting only |
| 002 |  | `authority_note` changes from `"None"` to a new support note; text and embedding contract exact | Allocate forward successor; reuse embedding; select successor |
| 003 |  | Existing warning text or rendered reference changes; proposition text exact | Allocate forward authority-note successor; reuse embedding |
| 004 |  | Proposition text changes under a supported correction | Allocate forward successor; generate embedding under pinned contract |
| 005 | P018 + | Former exact six-field record becomes legally supported again | Reselect the preserved record with one new append-only reinstatement event; no backward lineage |
| 006 | P018 - | Reinstated proposition now requires a support note that never existed in a former exact payload | Allocate forward successor; do not reselect the merely similar old record |
| 007 |  | Whole proposition conclusively overruled | Select no successor and omit vector from new target; preserve former record and history |
| 008 | P019 + | Combined record partly overruled; earlier judgment independently supports one unaffected standalone proposition and no exact narrower record already exists | End combined selection; create only the proved narrower record and generate its embedding |
| 009 | P019 - | Combined record partly overruled; no honest standalone unaffected proposition exists | End combined selection; create no invented narrower record |
| 010 |  | Only citation alias, evidence pointer, grouping, or traceability fact changes | Reuse Search Record and embedding; create only applicable register or lookup revision |
| 011 |  | Treatment effect or affected proposition remains uncertain | No guessed allocation, reselection, retirement, or embedding action; apply uncertainty rules |
| 012 |  | A legacy Distillation or Pinecone record appears textually identical to a new greenfield proposition | Allocate and select the register-owned greenfield identity; legacy identity is comparison evidence only and creates no predecessor lineage |

## G. Deterministic release, update, and promotion boundary

Case namespace: `HKCASE-TREAT-DET-REL-NNN`

Coverage namespace: `HKCASE-TREAT-COV-DREL-NNN`

| Suffix | Pair | Complete frozen update facts | Exact release and control result |
|---:|---|---|---|
| 001 |  | Every due official check, inventory comparison, artifact comparison, and treatment-coverage check proves exact reuse | `SUPPORTED_NO_CHANGE`; reuse records and releases; no embedding or new target |
| 002 |  | Evidence, alias, translation, zero-record, or traceability accounting changes while serving set stays exact | `ACCOUNTING_ONLY_CHANGE`; no serving-record or Pinecone change |
| 003 |  | At least one accepted note, proposition, selection, retirement, split, merge, or reinstatement changes serving | `SERVING_CHANGE`; rebuild only affected releases and compose complete target |
| 004 |  | Required release-blocking official observation remains unavailable or malformed | `BLOCKED` with the exact Coverage Gap; make no candidate-serving choice in this checkpoint and never report supported no change |
| 005 |  | Evidence conflict or unresolved treatment prevents exact affected decision | `QUARANTINED`; no guessed record effect; independent clean work remains separately accountable |
| 006 |  | Otherwise valid judgment or status event falls after frozen cutoff | Defer to next update; do not mutate candidate cutoff or convenient scopes |
| 007 |  | Candidate predecessor is no longer the accepted base | Reject stale candidate and rebuild; never silently rebase |
| 008 |  | Every required scope, record, fingerprint, recovery fact, compatibility check, and expected artifact is complete and exact | Candidate is Promotion Manifest-eligible only; no execution authority |
| 009 |  | One unclear item is quarantined and an accepted complete Withholding Release accounts for it while the remaining clean scopes are complete | Build one complete disclosed package from the exact withholding result; no partial approval of selected changes |
| 010 | P016 - | Legal treatment is clear and ordinary, but volume, cost, retirement count, or target diff crosses an operational limit | Separate operational pause; do not reclassify as `EXCEPTIONAL_CHANGE_REVIEW` |
| 011 |  | Required evidence gap is bounded and accepted prior state remains explicitly supportable under ADR 0005 | Exact carry-forward selection with reason, scope, cutoff, and disclosure |
| 012 |  | Affected record cannot be safely carried forward but unaffected target remains supportable | Exact withholding and inventory arithmetic; no silent deletion |
| 013 |  | Required current result cannot be supported or safely bounded into a complete candidate | No new target; preserve current serving state and explicit blocked gap |
| 014 |  | Candidate package is complete and Promotion Manifest-eligible but has no valid human Approval | No production execution, index build, or routing change |
| 015 |  | Fixture runner or pipeline component attempts direct live-record patch, source call, provider call, Azure or Pinecone access, credential use, routing, or undeclared external action | Hard failure with exact forbidden-side-effect report; no mutation |
| 016 |  | One accepted directional relationship is active at the cutoff | Derive exact incoming and outgoing projections carrying the same relationship ID and fingerprint; create no duplicate edge, Search Record, vector, metadata field, or whole-case summary |
| 017 |  | Corrected treating reasons add one, remove one, and alter one accepted relationship to earlier propositions | Preserve every former relationship; append the exact new and supersession facts; use the outgoing view to find every affected earlier proposition and recompute each incoming result exactly once |
| 018 |  | A bounded unresolved Treatment Lead identifies two possible earlier propositions but no exact treated target | Keep the lead in the outgoing investigative and affected-impact views only; create no settled incoming relationship, authority-note clause, relationship vector, or guessed edge |
| 019 |  | First current-authority baseline has no predecessor, complete required-scope and treatment screening, and one clear current proposition with no selected treatment note | Seal the no-predecessor baseline result with exact `authority_note: "None"`; never call it ordinary supported no change |
| 020 |  | A completely screened old superior-court proposition remains supported and has no accepted current-authority limitation | Keep it eligible for current serving; age and historical acquisition route create no retirement or warning |
| 021 |  | Official corrected reasons create a new Official Version and change treatment while the decision's original court and decision year remain exact | Keep the Judicial Decision and original court-year Release Scope; update only the affected relationships, propositions, records, and scopes |
| 022 |  | A previously accepted official listing disappears at the new cutoff without withdrawal or replacement evidence | Preserve prior evidence and selection, open bounded source reconciliation, and forbid automatic withdrawal, retirement, or supported no change |

## H. Required high-risk pairs

| Pair | Positive case | Near-miss case | Boundary proved |
|---|---|---|---|
| `HKCASE-TREAT-PAIR-001` | `SEM-DIS-008` | `SEM-DIS-009` | Complete segmented reading versus silent incompleteness |
| `HKCASE-TREAT-PAIR-002` | `SEM-ANA-002` | `SEM-ANA-001` | Express following versus bare citation |
| `HKCASE-TREAT-PAIR-003` | `SEM-ANA-007` | `SEM-ANA-006` | Material limitation versus factual distinction |
| `HKCASE-TREAT-PAIR-004` | `SEM-ANA-009` | `SEM-ANA-010` | Operative-majority criticism versus dissent |
| `HKCASE-TREAT-PAIR-005` | `SEM-ANA-013` | `SEM-ANA-014` | Authoritative overruling versus lower-court rejection |
| `HKCASE-TREAT-PAIR-006` | `SEM-ANA-018` | `SEM-ANA-019` | Permitted necessary-reasoning following versus express-only approval |
| `HKCASE-TREAT-PAIR-007` | `SEM-ANA-021` | `SEM-ANA-022` | Exact partial mapping versus bounded uncertainty |
| `HKCASE-TREAT-PAIR-008` | `DET-VAL-001` | `DET-VAL-003` | Exact evidence versus fabrication |
| `HKCASE-TREAT-PAIR-009` | `DET-VAL-019` | `DET-VAL-020` | Non-leaking model packet versus answer leakage |
| `HKCASE-TREAT-PAIR-010` | `DET-VAL-021` | `DET-VAL-022` | Matching sealed external evidence versus missing or mismatched evidence |
| `HKCASE-TREAT-PAIR-011` | `DET-VAL-023` | `DET-VAL-024` | Explicit zero output versus missing output |
| `HKCASE-TREAT-PAIR-012` | `DET-VAL-025` | `DET-VAL-026` | Explicit complete catalogue versus discovery or omission |
| `HKCASE-TREAT-PAIR-013` | `DET-VAL-027` | `DET-VAL-028` | Complete coverage matrix versus missing primary case or pair member |
| `HKCASE-TREAT-PAIR-014` | `DET-VAL-029` | `DET-VAL-030` | Deterministic reproducibility versus unstable output |
| `HKCASE-TREAT-PAIR-015` | `DET-DEC-012` | `DET-DEC-016` | Legal retirement versus lower-court adverse treatment |
| `HKCASE-TREAT-PAIR-016` | `DET-DEC-021` | `DET-REL-010` | Exceptional legal change versus operational anomaly pause |
| `HKCASE-TREAT-PAIR-017` | `DET-NTE-009` | `DET-NTE-011` | Permitted optional omission versus forbidden mandatory-warning omission |
| `HKCASE-TREAT-PAIR-018` | `DET-REC-005` | `DET-REC-006` | Exact former-record reselection versus new restored payload |
| `HKCASE-TREAT-PAIR-019` | `DET-REC-008` | `DET-REC-009` | Honest narrower proposition versus invented salvage |
| `HKCASE-TREAT-PAIR-020` | `SEM-ANA-039` | `SEM-ANA-040` | Operative judicial treatment versus quoted instruction-like source text |
| `HKCASE-TREAT-PAIR-021` | `DET-DEC-018` | `DET-DEC-022` | Exact proposition effect of reversal versus disposition-only uncertainty |

## I. Completeness and admission boundary

This accepted initial table directly covers:

- all accepted treatment classes, expression modes, scope results, opinion and
  authority boundaries, and appellate dispositions;
- one authoritative directional relationship, optional treating-proposition
  linkage, exact incoming and outgoing projections, and correction-driven
  reverse impact under ADR 0058;
- English, Traditional Chinese, and genuinely mixed-language semantic cases;
- complete and segmented reading, coverage ledgers, missing context, identity,
  evidence, and source boundaries;
- hostile or instruction-like source text, baseline no-predecessor behavior,
  old-authority retention, correction-scope continuity, legacy-ID isolation,
  unresolved-lead projection, and unsupported listing disappearance;
- all authority-note ordering, consolidation, budget, and prohibited-strength
  behavior;
- every immutable transition in ADR 0055;
- ordinary, uncertainty, exceptional, and operational routing; and
- every ordinary-update outcome and ADR 0005 serving choice used by Hong Kong
  later treatment.

It also directly tests ADR 0057's strict manifest, hashing, path, declaration,
answer-leakage, external-artifact, explicit-zero, catalogue, coverage, and
reproducibility rules.

The 53 semantic cases here are synthetic boundary cases. They are necessary but
not sufficient to admit a model task. Before provider enablement, a later exact
task-admission contract must add sealed representative real-judgment case IDs,
artifacts, human-adjudicated expected answers, class and boundary thresholds,
critical-error rules, repeated-run policy, model, prompt, settings, cost,
retention, and revalidation triggers. Those later cases extend the semantic
catalogue and coverage matrix; they do not replace these synthetic cases.

## J. Frozen consequence

ADR 0059 freezes:

- these 155 case IDs, 155 matching primary coverage cells, 21 pair IDs,
  scenarios, and required results as accepted design requirements;
- changing a normative row requires a new case and coverage ID, impact
  declaration, and preservation of the prior row;
- machine-readable catalogues, manifests, fixture bytes, schemas, exact reason
  and rule codes, canonical expected artifacts, and validators remain
  implementation artifacts; and
- no source acquisition, model call, embedding, release publication, Pinecone,
  Azure, promotion, deployment, or other operation becomes authorized.
