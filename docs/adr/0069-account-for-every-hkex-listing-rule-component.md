---
status: accepted
date: 2026-08-14
refines:
  - "0054"
refined_by:
  - "0070"
  - "0071"
  - "0072"
  - "0073"
  - "0074"
depends_on:
  - "0011"
  - "0018"
---

# Account for every HKEX Listing Rule component

Every frozen Hong Kong Regulatory Materials cutoff uses one immutable HKEX
Rule Component Inventory Package. The package separately accounts for the Main
Board and GEM Release Scopes and proves which official publication entries are
rule components, which rulebook owns them, their effective state, and their
permitted disposition.

The package contract is stable architecture. The changing live list of
Chapters, rules, notes, appendices, Practice Notes, Regulatory Forms, Fees
Rules, and other components is a versioned registry artifact governed by the
contract; it is not frozen as a mutable list inside this ADR.

Inventory accounting does not itself prove that a rule is searchable, create a
Search Record, or authorize a release. A complete inventory may expose a
blocked or quarantined component and therefore prove that one Release Scope is
not serving-ready.

## Exact inventory universe

One inventory package binds one frozen observation cutoff, one `hk-regulatory`
Source Rulebook version, the registered component-discovery and reconciliation
source roles due at that cutoff, and their complete successful or failed
Observations.

The inventory universe consists of entries published through those registered
HKEX rulebook inventory products, consolidated rulebooks, component indexes,
and exact update manifests, together with directly linked material whose
membership must be classified. It is not an unbounded recursive crawl of every
HKEX, SFC, or Thomson Reuters page.

The future Source Register must state which products enumerate the promised
universe and which are only cross-checks. Until complete enumeration of an
accepted source role is technically proved, the affected Release Scope cannot
claim a complete current inventory. An online search result count, website
navigation tree, PDF table of contents, or one source in isolation cannot
silently define the universe unless the Source Rulebook expressly assigns that
fact authority.

## Source entries and owned component instances

The design distinguishes:

- an **observed source entry** — one item, link, heading, form, note, or other
  object presented by a registered publication product at the cutoff;
- a **source artifact** — one preserved PDF, page, update package, form, or
  other publication that may contain or support several entries; and
- a **board-owned rule component instance** — one register-owned Legal
  Location under either the Main Board or GEM Legal Item.

Source-entry IDs, URLs, titles, rule numbers, update numbers, page positions,
and filenames are evidence and aliases. They do not become Legal Location or
Search Record identity.

One artifact may support many components and may be evidence for both
rulebooks. That does not create one ambiguous cross-market component. If the
same official form, note, or wording is expressly part of both rulebooks, the
inventory creates or resolves one Main Board-owned component instance and one
GEM-owned component instance, each with its own rulebook context and identity,
while both may reference the same preserved artifact.

## Separate classification dimensions

Every observed source entry and every resulting component instance records
separate dimensions. One label never stands in for all of them.

### Membership and ownership

The membership result is exactly one of:

- `RULE_COMPONENT` — official evidence proves that the object forms part of
  one accepted Listing Rule rulebook;
- `EVIDENCE_ONLY` — the object may prove an amendment, approval, transition,
  interpretation, source relationship, or review fact but is not rule text;
- `EXCLUDED_NON_RULE` — the object is outside the accepted searchable family,
  such as unincorporated guidance, an FAQ, consultation, listing decision, or
  general announcement; or
- `UNRESOLVED_MEMBERSHIP` — available evidence does not safely establish one
  of the preceding results.

Every `RULE_COMPONENT` has exactly one Release Scope owner:
`HK-REG-HKEX-MAIN-BOARD` or `HK-REG-HKEX-GEM`. The same component instance
cannot be owned by both, omitted from both, or assigned through website
placement alone. Non-rule and unresolved entries have no rule-component owner,
although their evidence remains linked to the affected scopes.

### Effective state

Every `RULE_COMPONENT` records exactly one effective-state family at the
cutoff:

- `CURRENT` — effective without a material special transition branch;
- `TRANSITIONAL_CURRENT` — currently applicable only to an exact cohort,
  transaction, reporting period, or other supported branch;
- `FUTURE_FIXED_DATE` — published but subject to an unelapsed fixed date;
- `FUTURE_CONDITIONAL` — published but dependent on an unproved external
  event or condition;
- `SUPERSEDED` — replaced for all current applications;
- `WITHDRAWN` — officially withdrawn or repealed for all current
  applications;
- `UNKNOWN` — the effective state cannot safely be established; or
- `NOT_APPLICABLE` — permitted only for an entry that is not a rule component.

ADR 0071 later refines this as one derived inventory-level component summary
backed by the complete set of atomic applicability-branch decisions. The
summary preserves ADR 0069's exact component accounting but cannot flatten,
discard, or replace concurrently current, future, or historical branch facts.

The exact effective date, condition, cohort, transition text, source evidence,
and applied rule remain structured facts rather than being compressed into the
state name. `TRANSITIONAL_CURRENT` may produce several separately owned current
branches when old and new requirements concurrently apply.

### Material disposition and processing outcome

The material disposition remains separate from both membership and processing:

- searchable current rule component;
- regulatory Waiting Room;
- evidence-only;
- historical;
- Quarantine; or
- not applicable.

Processing separately ends `PASS`, `BLOCK`, or `QUARANTINE` with stable reason
and rule codes. `PASS` does not mean searchable. For example, a correctly
classified guidance document may pass with an excluded membership and no rule
disposition, while a known current rule whose required source artifact is
unavailable is blocked rather than misclassified as historical.

Exact machine enum names for material disposition and detailed reason codes
belong to the executable contract. They must preserve these separate meanings
and cannot collapse missing evidence, legal state, coverage effect, and serving
output into one status.

## Inclusion proof

`RULE_COMPONENT` requires exact preserved official evidence showing that the
object is part of the relevant rulebook. Permitted evidence may include a
rulebook definition, express incorporation provision, official component
statement, complete consolidated-rulebook structure, or update package whose
meaning is assigned by the Source Rulebook.

The following are insufficient by themselves:

- appearing in the same website navigation or search result;
- having a similar title, rule number, form number, or visual style;
- being useful to understand or comply with the rules;
- being published by HKEX or the SFC;
- being linked from a rule page; or
- being semantically similar to an included component.

Every accepted membership decision records the exact evidence ranges, source
roles, Source Rulebook rule IDs, responsible Hong Kong Regulatory Materials
Legal Desk, cutoff, and decision fingerprint. Unresolved membership enters the
smallest affected Quarantine and cannot become searchable through convenience,
similarity, or an authority note.

## Structure and component coverage

Every accepted component instance records its board, class, official parent,
visible locator, source aliases, structural order, exact inclusion evidence,
effective-state evidence, required English artifact relationships, any
preserved optional Traditional-Chinese relationship, and predecessor or
related component identities where applicable.

Parent and child structure follows official legal organization. A Chapter may
own rules; a rule may own subrules and incorporated notes; an appendix,
Practice Note, Regulatory Form, or Fees Rule may have its own supported
hierarchy. A website container, PDF page, table cell, blank form field, or
renderer-created serving part does not receive permanent component identity
merely from presentation.

The inventory proves structure without deciding final Search Record
partitioning. ADR 0072 later selects English-only serving, and ADR 0073 fixes
which complete official units can stand independently, how their context and
cross-references are rendered, and how overlong content is represented.

## Four separate completeness results

One package reports four separate results for each Release Scope:

1. **source-entry accounting** — every entry in the declared inventory
   universe has exactly one membership result;
2. **component ownership and structure** — every accepted rule component has
   exactly one board owner, one supported structural position, and no duplicate
   or orphan component instance;
3. **current-state accounting** — every component has one supported effective
   state and material disposition, or an explicit blocked or quarantined
   result; and
4. **serving readiness** — every required current component has the later
   English record, traceability, conformance, and release evidence needed
   to proceed.

A scope may have complete source-entry accounting while remaining not ready to
serve because one known component is blocked or quarantined. Record counts,
PDF page counts, website totals, or a successful parser cannot substitute for
these proofs.

The package is invalid when any declared entry or component is missing,
duplicated, unowned, double-owned, orphaned, silently skipped, discovered only
through an undeclared file, or inconsistent with its declared fingerprint and
totals. Each total must reproduce from the exact inventories.

An independently bounded Main Board failure does not automatically invalidate
the complete GEM result, and vice versa. A missing or conflicting shared source
role affects both only when the Source Rulebook proves that both scopes depend
on that fact. Scope isolation cannot be used to hide an unbounded shared gap.

## Immutable versions and ordinary updates

Every inventory package declares its package ID, cutoff, predecessor,
Source Rulebook and contract fingerprints, source and endpoint versions,
ordered observed-entry inventory, board-owned component inventories, evidence
references, totals, reconciliation results, per-scope readiness, impact
declaration, and canonical root fingerprint.

A new, moved, renamed, renumbered, split, merged, transferred, withdrawn,
disappeared, or reappearing entry creates a new observation and an explicit
comparison with the accepted predecessor. It does not silently mutate the old
package. Disappearance is not proof of withdrawal, supersession, or removal
from current search. Similar wording or a reused number does not prove
component continuity.

`SUPPORTED_NO_CHANGE` requires every due inventory role to complete, every
declared entry and component to reconcile with the accepted predecessor, and
no unresolved source, membership, ownership, structure, effective-state, or
contract signal. It reuses the accepted component inventory and creates no
rule processing, embedding, or Pinecone work merely to record silence.

## Conformance boundary

The future conformance catalogue must directly cover at least:

- a Chapter, rule, incorporated note, appendix, Practice Note, Regulatory
  Form, Fees Rule, and another expressly included component;
- nearby guidance, FAQ, consultation, decision, announcement, and template
  entries that must not become rules;
- one artifact containing many components and one artifact supporting both
  board-owned component instances;
- missing, duplicate, orphaned, double-owned, and wrong-board components;
- current, future-dated, conditional, transitional, superseded, withdrawn,
  and unknown effective states, plus proposed non-rule material that must not
  receive a rule-component state;
- a moved URL, renamed component, renumbering, split, merge, disappearance,
  and reappearance;
- complete accounting with zero Search Records and complete accounting that
  exposes a blocked or quarantined scope;
- one independently bounded board failure and one shared unbounded gap; and
- exact no-change versus an incomplete or stale inventory observation.

Deterministic processing owns source enumeration, hashing, declared-inventory
comparison, identity and structure arithmetic, schema validation, and
fingerprints. The Hong Kong Regulatory Materials Legal Desk owns accepted
membership, ownership, effective-state, and disposition decisions under the
Source Rulebook. This ADR does not allocate any ambiguous semantic proposal to
a generative LLM and authorizes no model call.

## Consequences and authorization

ADR 0070 later registers the exact lean five-role Hong Kong Regulatory
Materials source set and assigns Fact Authority, inventory responsibility,
outage effect, monitoring, optional-evidence, trigger, conflict, and downstream
boundaries. ADR 0071 later settles applicability-branch effective-state and
transition rules. ADR 0072 later settles English-only serving and makes Chinese
translation material optional non-serving support. ADR 0073 later settles
English record construction and exact source-unit coverage. The next decisions
settle executable conformance fixtures and retrieval gates. ADR 0074 later
fixes the two-layer conformance and coverage-matrix architecture without
creating the exact case table. ADR 0075 later freezes that table, ADR 0076
settles the high-level semantic task allocation, and ADR 0077 settles
multilingual retrieval and answer admission architecture.

This decision authorizes documentation only. It does not create the live
component inventory, register sources, acquire artifacts, implement schemas or
connectors, call an LLM or embedding provider, construct a corpus, access
Pinecone or Azure, promote, deploy, commit, push, or perform any remote action.
