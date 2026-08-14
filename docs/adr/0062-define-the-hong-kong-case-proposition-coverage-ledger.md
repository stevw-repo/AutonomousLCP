---
status: accepted
date: 2026-08-13
refines:
  - 0049
  - 0060
  - 0061
depends_on:
  - 0016
  - 0043
  - 0048
refined_by: "0065"
---

# Define the Hong Kong Case Proposition Coverage Ledger

Every exact Hong Kong judgment Official Version receives one immutable
fingerprinted **Case Proposition Coverage Ledger**. The ledger proves that
every opinion and every part of the accepted original judgment was accounted
for and that every proposition result maps to exact source material.

It prevents silent truncation, skipped opinions, unaccounted footnotes, and a
bare “nothing found” result. It does not prove by arithmetic alone that every
semantic decision is correct. Extraction evaluation, conformance, runtime
uncertainty behavior, and correction monitoring remain necessary.

The ledger is internal. It creates no Pinecone vector or metadata field and is
not read by Ask.Legal during an ordinary query.

## Immutable ledger identity

One ledger result binds exactly:

- Judicial Decision and Official Version identities;
- accepted original judgment artifact fingerprints;
- complete opinion and judge-attribution inventory;
- parser and structural-normalization contract;
- Source Rulebook and observation cutoff;
- Case Proposition output, boundary, and renderer contracts;
- extraction task or decision contract, without assuming whether it is
  deterministic, LLM-assisted, Legal Desk, or human;
- processor build and any applicable model, prompt, and settings identities;
  and
- candidate, proposition, ledger, and output fingerprints.

A result-affecting source, parser, structure, extraction, model, prompt,
rulebook, or proposition-contract change creates a new ledger result or an
explicit impact decision. It never mutates an accepted earlier ledger.
Optional Judiciary translations remain auxiliary evidence and do not replace
or redefine original-language coverage.

## Exhaustive original-source inventory

Before semantic analysis, deterministic structure processing creates an
ordered exhaustive inventory of the accepted original artifact. It includes:

- every joint, majority, lead, adopted, concurring, dissenting, plurality,
  court, or other identified opinion;
- every numbered and unnumbered paragraph;
- opinion headings and subheadings;
- footnotes and endnotes;
- lists, tables, quoted blocks, orders, dispositions, schedules, and
  appendices; and
- cover, appearance, administrative, or other source material that may later
  be classified as non-propositional but cannot be silently omitted.

Each **Coverage Unit** records its register-owned Legal Location where
available, source locator or canonical fallback span, opinion ownership,
source order, original language, normalized-text fingerprint, and exact map
to the preserved artifact. Visible paragraph numbers and byte positions are
locators and evidence rather than permanent legal identity.

If the parser cannot enumerate or faithfully map the complete artifact, the
ledger is `BLOCKED`. It cannot proceed by covering only supported structures.

## Segmentation and dependency accounting

A judgment that fits one processing packet still receives the complete unit
inventory and ledger. Context-window fit is not coverage proof.

When segmentation is required:

- segments stay within one opinion for primary content;
- every Coverage Unit belongs to exactly one segment as primary content;
- the union of primary segment inventories equals the complete ordered unit
  inventory, with no omission, duplication, or reordering;
- a segment repeats a unit only as an explicit context dependency;
- each dependency points to its one primary unit and exact fingerprint and
  does not count as primary coverage again;
- cross-references, defined terms, earlier tests, qualifications, reasons, and
  dispositions needed to understand a segment become recorded dependencies;
  and
- no segment ends through silent truncation.

An adoption path across opinions is an explicit dependency supported by ADR
0061's exact adoption evidence. It does not merge primary opinion inventories
or infer agreement.

## Unit resolution and evidence roles

Every Coverage Unit has exactly one final resolution state:

- `RESOLVED` — the entire unit was accounted for;
- `QUARANTINED` — existing evidence or semantic interpretation remains
  materially conflicting or unsafe; or
- `BLOCKED` — required text, structure, dependency, or processing support is
  unavailable.

Every `RESOLVED` unit has exactly one primary use:

- `PROPOSITION_EVIDENCE` — supports one or more accepted Case Propositions;
- `CONTEXT_EVIDENCE` — supplies necessary facts, procedure, attribution, or
  result but is not itself a legal answer; or
- `NON_PROPOSITIONAL` — examined and supports no Case Proposition.

A proposition-evidence unit may link to several propositions and carry several
exact evidence roles: legal issue, derived answer, qualification, application,
result, authority attribution, selected exact quotation, or supplementary
supporting occurrence. Exact linked ranges expose mixed content. Repeated
support remains `PROPOSITION_EVIDENCE` with a supplementary role even when it
is omitted from minimum serving text.

Every `NON_PROPOSITIONAL` unit has a stable reason family. Required families
include source scaffolding, unused procedural or factual narrative, unadopted
party position, unadopted citation or quotation, outcome without a legal
answer, agreement-only opinion, non-material discussion, and treatment-only
reasoning. Exact machine codes remain later schema work.

`TREATMENT_ONLY` is not a discard result. It links to the separate citation
and treatment-screening inventory so a judgment with no proposition of its own
can still affect earlier authority.

## Candidate accounting

Every proposition candidate receives exactly one final outcome:

- accepted as one Case Proposition;
- rejected under ADR 0060 with an exact reason;
- merged into another identified candidate under ADR 0061;
- split into identified candidates under ADR 0061;
- quarantined; or
- blocked.

No candidate disappears between discovery and final output. Every accepted
proposition links to all required issue, answer, context, qualification,
application, result, attribution, and exact-quotation evidence roles. Every
serving record links to one accepted proposition and exact ledger fingerprint.
Orphan records, candidates, or renderer sections invalidate the result.

## Completeness arithmetic

A structurally valid ledger proves:

1. expected and covered opinion inventories are exact;
2. every expected Coverage Unit occurs exactly once in primary segment
   coverage and in original source order;
3. every dependency resolves to one covered primary unit and exact
   fingerprint;
4. every unit has exactly one resolution state;
5. every resolved unit has exactly one primary use;
6. every candidate has exactly one final outcome;
7. every accepted proposition has ADR 0060's complete evidence-role set;
8. every proposition and serving quotation maps to exact source ranges;
9. the accepted proposition inventory equals the accepted candidate
   inventory; and
10. no unaccounted, duplicate, orphaned, fingerprint-mismatched, blocked, or
    quarantined object is hidden inside a complete result.

The ledger declares exact inventories and reproducible totals for opinions,
units, primary segments, dependencies, candidates, accepted propositions,
each primary use, Quarantines, and blocked work. Free-form totals cannot prove
completeness.

## Final ledger results

One ledger has exactly one result:

- `COMPLETE_WITH_PROPOSITIONS` — every coverage and evidence check passes and
  at least one proposition is accepted;
- `COMPLETE_NO_PROPOSITION` — every check passes, no proposition is accepted,
  no candidate remains unresolved, and every unit has a resolved non-
  proposition result;
- `ACCOUNTED_WITH_QUARANTINE` — complete source structure is accounted for but
  at least one material unit, candidate, attribution, dependency, or
  proposition issue is quarantined;
- `BLOCKED` — complete examination cannot occur because required source text,
  structure, dependency, or processing support is unavailable; or
- `INVALID` — identity, fingerprint, inventory, arithmetic, schema, or
  contract validation failed. This is a processing defect, not a legal
  conclusion.

Clear independent candidate work may remain preserved beside a bounded
Quarantine, but the judgment ledger is not called complete and no release may
hide the unresolved boundary.

## Exact zero-proposition rule

`COMPLETE_NO_PROPOSITION` requires:

- the complete accepted original Official Version;
- every opinion and Coverage Unit present and resolved;
- every candidate accounted for with no accepted or unresolved proposition;
- no blocked or quarantined unit, candidate, dependency, opinion, or
  attribution issue;
- no `PROPOSITION_EVIDENCE` unit; and
- every citation-bearing or treatment-only unit handed to the separate
  treatment-screening inventory.

Three results remain distinct:

1. no proposition exists: `COMPLETE_NO_PROPOSITION`;
2. propositions exist but none currently serve: the ledger is
   `COMPLETE_WITH_PROPOSITIONS`, while later-treatment and selection rules
   produce zero selected Search Records; and
3. the system cannot decide safely: `ACCOUNTED_WITH_QUARANTINE` or `BLOCKED`,
   never a valid zero.

A release-level zero-record result still requires ADRs 0048 and 0049's
separate acquisition, treatment-screening, authority, and release accounting.
The proposition ledger alone cannot prove that the judgment does not affect
earlier authority.

## Traceability, correction, and allocation

The Evidence Vault preserves the ledger artifact. The Management Register
records its identity, status, relationships, and supersession. The Record
Traceability Lookup points each selected Case Proposition Search Record to the
exact ledger fingerprint without creating a query-time dependency.

An official corrected judgment receives a new Official Version and ledger. A
changed parser, structure, extraction, model, prompt, or proposition contract
requires a new result and impact declaration rather than mutation. Earlier
ledgers remain reproducible.

Structural enumeration, hashing, unit arithmetic, dependency integrity,
schema validation, and fingerprint validation are deterministic safety
controls. ADR 0043 initially deferred the semantic proposition, materiality,
unit-use, and candidate-decision allocation. ADR 0065 later assigns semantic
analysis and challenge to two bounded LLM passes while deterministic processing
owns complete ledger arithmetic and validation. The workflow must not store
private chain of thought; structured outcomes, evidence links, objections,
reasons, and uncertainty are sufficient.

## Consequences

The Hong Kong Cases Source Rulebook, extraction contracts, schemas,
evaluations, conformance catalogue, processing reports, correction logic,
Record Traceability Lookup, and release gates must agree with this ledger.
Exact executable schemas, codes, fixtures, thresholds, and runtime task-
admission values remain later work.

This decision authorizes documentation only. It does not authorize
implementation, source acquisition, model or embedding calls, release
publication, Pinecone or Azure access, promotion, deployment, commit, or any
remote action.
