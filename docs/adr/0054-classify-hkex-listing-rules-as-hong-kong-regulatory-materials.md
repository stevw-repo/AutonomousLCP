---
status: accepted
date: 2026-08-12
amends:
  - 0050
refines:
  - 0003
  - 0005
  - 0008
  - 0011
  - 0018
depends_on:
  - 0050
refined_by:
  - "0069"
  - "0070"
  - "0071"
  - "0072"
  - "0073"
  - "0074"
---

# Classify HKEX listing rules as Hong Kong Regulatory Materials

## Decision and legal nature

Ask.Legal will add **Hong Kong Regulatory Materials** as a separate material
family and expose it through the user-facing category **Regulatory**. Search
Records in this family use the existing six-field metadata envelope with
`metadata.type` equal to `"regulatory"`. No field is added to the serving
contract.

The initial approved coverage is limited to the current effective:

- Rules Governing the Listing of Securities on The Stock Exchange of Hong Kong
  Limited, commonly called the **Main Board Listing Rules**; and
- Rules Governing the Listing of Securities on GEM of The Stock Exchange of
  Hong Kong Limited, commonly called the **GEM Listing Rules**.

This family is not named `Policy`. The Listing Rules prescribe formal listing
requirements and continuing obligations. HKEX states that the Exchange made
them under section 23 of the Securities and Futures Ordinance and that the SFC
approved them under section 24. The SFC remains the statutory regulator while
the Exchange administers the Listing Rules as the front-line listing regulator.
The SFC has separately described the Listing Rules as non-statutory and without
statutory effect. They are therefore neither Hong Kong Legislation nor
publisher-derived Principles, but they are materially more authoritative than
ordinary policy or guidance.

Sources supporting this classification include the current
[Main Board rule 2.01](https://en-rules.hkex.com.hk/rulebook/201-0), the
[SFC description of listing regulation](https://www.sfc.hk/en/Regulatory-functions/Corporates),
and the SFC and Exchange's
[listing-regulation consultation](https://apps.sfc.hk/edistributionWeb/api/consultation/openFile?lang=EN&refNo=16CP2).

This decision is jurisdiction-specific. It does not automatically classify
another jurisdiction's exchange rules, regulatory codes, circulars, or
guidance. Each later jurisdiction-and-material pair requires its own coverage
and Source Rulebook decision under ADR 0018.

## Coverage and ownership

The initial family has two non-overlapping Release Scopes:

| Release Scope | Ownership promise |
|---|---|
| `HK-REG-HKEX-MAIN-BOARD` | Complete current effective Main Board Listing Rules at one cutoff |
| `HK-REG-HKEX-GEM` | Complete current effective GEM Listing Rules at one cutoff |

The Main Board and GEM rulebooks are separate Legal Items because they govern
different markets and HKEX expressly says that each applies only to its own
market. A complete effective consolidated state is an Official Version for
pipeline identity purposes. Here, `Official Version` means an Exchange-issued
and SFC-approved rulebook state; it does not turn the rules into legislation.

Each Release Scope must account for every component that HKEX expressly makes
part of that rulebook, including applicable Chapters, notes, appendices,
Practice Notes, Regulatory Forms, Fees Rules, and any other expressly included
component. Navigation placement or a similar title is not enough. The source
inventory must preserve the exact rule or official statement that proves each
component's inclusion. HKEX currently identifies its Regulatory Forms as part
of the Listing Rules, while GEM rule 1.02 expressly includes its appendices,
Regulatory Forms, Fees Rules, Practice Notes, and specified notes. See the
[HKEX Regulatory Forms page](https://en-rules.hkex.com.hk/rulebook/regulatory-forms)
and [GEM rule 1.02](https://en-rules.hkex.com.hk/rulebook/102).

The initial searchable scope excludes:

- guidance letters and guidance materials that do not form part of the rules;
- frequently asked questions;
- listing decisions and Listing Review Committee decisions;
- circulars and general announcements;
- consultation papers, consultation conclusions, information papers, and
  policy-development material; and
- checklists, templates, and forms not expressly designated as part of the
  Listing Rules.

Those materials may be preserved as amendment, interpretation, provenance, or
review evidence when a rule decision requires them. They do not become
Search Records merely because the HKEX search interface displays them beside
the Listing Rules. HKEX states that its guidance does not form part of the
Listing Rules, does not amend or vary listing obligations, and yields to the
Listing Rules on discrepancy. See the current
[HKEX guidance disclaimer](https://www.hkex.com.hk/listing/rules-and-resources/guidance/listed-issuers/practices-and-procedures-for-handling-listing-related-matters?sc_lang=en).

A future searchable regulatory-guidance collection requires a separate
accepted scope, authority labelling, currency rules, evaluation, and source
precedence decision. This ADR does not authorize it.

## Fact-specific source hierarchy

The Hong Kong Regulatory Materials Source Rulebook must register sources by
the exact fact each may prove. The accepted policy-level hierarchy is:

1. **Current consolidated rule text.** The HKEX-maintained consolidated Main
   Board and GEM PDFs control the current consolidated wording. HKEX states
   that these PDFs prevail if they differ from the versions maintained by
   Thomson Reuters. See
   [HKEX consolidated PDFs](https://www.hkex.com.hk/listing/rules-and-resources/listing-rules/consolidated-pdfs?sc_lang=en).
2. **Amendment, commencement, and transition evidence.** Official HKEX
   amendment packages and subscriber update notices prove the changed words,
   stated coming-into-effect conditions, and transitional arrangements for
   their assigned facts. They do not make a future or conditional amendment
   current before its trigger is established.
3. **Approval evidence.** The applicable accepted SFC or Exchange evidence must
   support any result that depends on SFC approval rather than assuming
   approval from a draft, consultation, or proposed amendment.
4. **Online rulebook presentation.** The Thomson Reuters-maintained rulebook
   may support discovery, navigation, version comparison, and deterministic
   structure. It cannot override the HKEX-maintained consolidated PDFs on a
   discrepancy.
5. **Guidance and consultations.** These may explain background or open a
   review. They cannot silently rewrite rule text, prove present effect, or
   enter a rule Search Record as if they were part of the rulebook.

Every relied-on artifact, language version, update notice, amendment, approval
fact, and reconciliation report remains preserved in the Evidence Vault. A
Source Contract Review opens when HKEX changes the publication structure,
component classification, version semantics, language relationship, or
precedence statement.

## Effective state and transitional rules

`Current` means the exact rule text and applicability supported as effective at
one frozen observation cutoff. It does not mean the newest URL, highest update
number, latest consultation, or most recently posted file.

The Source Rulebook must distinguish:

- an amendment already in force;
- an amendment published with a future calendar effective date;
- an amendment whose operation depends on an external legal or system-launch
  event;
- a rule with cohort-specific, transaction-specific, or time-limited
  transitional arrangements;
- a repealed or withdrawn rule; and
- a proposed change with no operative effect.

Future and condition-dependent amendments remain in a regulatory Waiting Room
outside ordinary current search until exact evidence proves their trigger.
Consultation conclusions alone are not current rules. An official update may
contain several effective dates and transition conditions; the pipeline must
map each changed Legal Location separately rather than assigning one date to
the whole update. HKEX's 2026 updates demonstrate both split effective dates
and external-event triggers. See
[Update No. 153](https://en-rules.hkex.com.hk/rulebook/update-no-153) and
[Update No. 152](https://en-rules.hkex.com.hk/rulebook/update-no-152).

When old and new requirements concurrently apply to different cohorts, the
pipeline preserves the complete official transition and produces the minimum
self-contained records needed to state each current applicability branch
accurately. It does not flatten the branches into one universal rule. A
material applicability limitation belongs in source text and context where it
is part of the official rule package; a separate controlled authority note is
used only when the Source Rulebook requires an additional reliance warning.

The ordinary Ask.Legal target remains a current database, not an as-at-date
service. Superseded rule versions and expired transitions remain preserved and
traceable outside Pinecone.

## Identity, record unit, and continuity

Main Board and GEM rulebooks keep separate identities. Within each rulebook:

- the complete rulebook is the Legal Item;
- an effective consolidated state is an Official Version;
- a rule, subrule, incorporated note, appendix provision, Practice Note unit,
  form requirement, fee requirement, or other independently maintained
  rule-bearing unit is a Legal Location; and
- one independently understandable serving payload is a Search Record.

The default Search Record covers one complete rule or the smallest complete
official subrule that can stand independently with its necessary definitions,
headings, lead-ins, notes, transition text, and cross-reference context.
Separate rules are not combined merely to fill a token budget. The pipeline
does not generate unofficial summaries, explanations, or policy statements as
substitutes for rule text.

Overlong material splits only at complete official rule, paragraph, list,
table-row group, form Part, or other source-supported boundaries. Every part
retains the minimum dependency closure needed for independent meaning. No
sentence, character, token, or visual-page cut is permitted unless it is also
an official semantic boundary.

Register-issued identity and immutable serving-payload rules continue to
apply. A URL move or exact presentation-only change does not create a new
Legal Item. An effective amendment creates the applicable new Official Version
and successor Search Records for changed six-field payloads. Official
renumbering, split, merge, transfer, or repeal requires exact evidence and
typed lineage. Similar wording or a reused rule number never proves
continuity. Repealed and superseded material remains preserved but is not
selected for ordinary current search.

## Bilingual serving layout — superseded by ADR 0072

ADR 0072 replaces this section's full-bilingual serving and mandatory-Chinese
release gate with English-only `metadata.text`. The official Chinese
translation remains optional non-serving support. The text below preserves the
original decision for history and does not describe the current serving rule.

Each ordinary HKEX Listing Rule Search Record contains one English-first,
Traditional-Chinese-second `metadata.text` for the same board, Official
Version, Legal Location, effective state, and transition context. The blocks
are labelled differently because their authority is not equal:

```text
Context:
Material: HKEX Listing Rule — non-statutory exchange regulatory rule
Market: Main Board | GEM
Chapter and rule: <exact locator and heading>
Effective context: <only when required for current application>

English rule text — prevailing language:
<exact current English text>

Traditional Chinese rule text — official translation:
<exact matching Traditional Chinese text>
```

HKEX states that the rules are issued in English with a separate Chinese
translation and that English prevails on conflict. See
[Main Board rule 1.07](https://en-rules.hkex.com.hk/rulebook/107-0) and
[GEM rule 1.08](https://en-rules.hkex.com.hk/rulebook/108).

The pipeline creates no parallel English-only and Chinese-only vectors. Both
languages must map to the same exact rule location and current applicability
branch. A missing, stale, differently versioned, or structurally unalignable
required translation blocks or quarantines the affected bilingual candidate;
this ADR authorizes no silent monolingual fallback. A source conflict is not
resolved by translation similarity or an LLM. The English text controls the
legal meaning, while the mismatch still prevents the system from presenting
an unsafe bilingual pair.

`metadata.authority_note` remains `"None"` when the labelled rule text and
context fully state the record's authority and no specific reliance warning
applies. It may carry a controlled English warning for a material transitional,
scope, source, representation, or unresolved-reference limitation under the
Hong Kong Regulatory Materials Source Rulebook. A generic source description
is not repeated as an authority note merely because the material is
non-statutory.

## Serving-contract and quality consequences

The serving envelope remains top-level `id` plus the six required metadata
strings. This decision adds `"regulatory"` as a permitted `metadata.type`
value; it does not add a subtype, board, date, or language field. Exact board,
component class, version, effective facts, and evidence live in the Management
Register and Record Traceability Lookup, while the minimum meaning-bearing
context stays in `metadata.text`.

Before a Serving State containing Regulatory records can be approved, every
active Ask.Legal query path, filter, user-facing category selector, result
renderer, downstream prompt, audit path, schema, Desired-State Inventory,
promotion validator, and recovery check must prove that it accepts and
preserves `type: "regulatory"`. Unknown-type fallback is not proof of correct
behavior.

Evaluation must cover English, Traditional Chinese, and cross-language queries;
Main Board versus GEM disambiguation; rule-number searches; definitions and
cross-references; current versus future amendments; cohort-specific
transitions; forms, fees, tables, and Practice Notes; source attribution;
guidance-versus-rule confusion; and retrieval crowding against legislation,
cases, and Principles.

## Consequences and authorization

The next design artifacts are a complete source and component audit, the
Registered Source records, an `hk-regulatory` Source Rulebook, exact Main Board
and GEM inventories, effective-state and transition rules, bilingual
reconciliation contracts, record schemas, fixtures, coverage proofs, and
search-quality thresholds.

ADR 0069 later fixes the component-inventory and completeness contract. It
requires immutable cutoff-bound packages, exact observed-entry accounting,
separate membership, ownership, effective-state, disposition, and processing
results, per-scope completeness, and explicit treatment of shared artifacts and
excluded non-rule material. The actual changing component list remains a
versioned registry artifact rather than ADR content.

ADR 0070 later fixes the lean source contract: exactly five roles are ordinary
current-database dependencies, optional and item-specific evidence stays
outside the routine release path, and source material is not automatically
sent to the downstream legal-analysis LLM or indexed in Pinecone.

ADR 0071 later fixes applicability-branch effective-state and transition
decisions, derives the component inventory summary without flattening branches,
and fails closed on trigger, timing, transition, or current-product conflicts.

ADR 0072 later replaces the original full-bilingual record with complete
prevailing English text, keeps Chinese translations outside the serving and
ordinary release path, and requires Chinese-query evaluation before this
family can serve.

ADR 0073 later fixes the class-specific English record units, canonical
renderer, governing-context and cross-reference boundaries, official-structure
overlong partitioning, and exact English source-unit coverage proof.

ADR 0074 later fixes the two linked Regulatory conformance layers, strict
package and catalogue mechanics, frozen coverage matrix, high-risk pairs,
critical errors, reproducibility, and separate build-attestation boundary.

This decision authorizes documentation only. It does not authorize schema or
application implementation, source acquisition, corpus construction, provider
or embedding calls, release publication, Pinecone access or mutation,
promotion, deployment, commit, or push.
