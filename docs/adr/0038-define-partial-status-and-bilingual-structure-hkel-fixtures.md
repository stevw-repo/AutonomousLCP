---
status: accepted
date: 2026-08-12
amended_by:
  - "0079"
  - "0080"
  - "0081"
refines:
  - 0005
  - 0012
  - 0013
  - 0019
  - 0020
  - 0021
  - 0022
  - 0025
  - 0028
  - 0033
  - 0034
depends_on:
  - 0035
  - 0036
  - 0037
---

# Define partial-status and bilingual-structure HKeL fixtures

The fourth HKeL fixture group covers two related problems:

- one instrument or provision may contain current, uncommenced, ended, or
  uncertain locations at the same time; and
- authentic English and Traditional Chinese may divide the same legal location
  into different numbers of source units.

The system does not give a mixed instrument one convenient status and does not
require superficial one-to-one language symmetry. It builds complete internal
status and bilingual-alignment maps first, then creates Search Records only for
the exact locations proved suitable for current-law search.

This group preserves the distinction between three decisions:

1. whether required source representations reconcile;
2. what legal disposition each location receives; and
3. whether a complete Corpus Release can select, withhold, or carry forward
   records under the already accepted release rules.

A reconciliation `PASS` does not itself select a record for Pinecone.

## Status Coverage Map

For every covered Legal Item at one observation cutoff, the Management Register
holds an immutable **Status Coverage Map**. In simple terms, it is a complete
table saying what status every relevant Legal Location has, why, and which
evidence supports that conclusion.

The map records, for every location:

- the Legal Item, Official Version, Legal Location, and parent relationship;
- the exact source-status signals and accepted event evidence;
- the legal and observation dates that the evidence actually supports;
- whether a status came from an exact location-specific rule or from an
  expressly applicable parent rule;
- the resolved primary disposition under `HKLEG-CURRENT-DISP-001`;
- any unresolved facts, authority-note consequence, and evidence fingerprints; and
- the ordered Rule Trace and responsible Legal Desk decision.

Every relevant location appears exactly once. Missing locations, overlapping
assignments, or two primary dispositions for one location make the map
incomplete. The map is internal evidence and workflow state. It is not a new
Pinecone metadata field and is not inserted into `metadata.text`.

The map uses the already accepted dispositions:

- `SEARCHABLE_CURRENT` for supported presently operative text;
- `WAITING_ROOM` for validly made material not yet proved operative;
- `EVIDENCE_ONLY` for material whose relevant present effect is completely
  represented by another tracked authority;
- `HISTORICAL` for material proved ended, repealed, expired, superseded, or
  otherwise no longer current; and
- `QUARANTINE` for unresolved identity, status, evidence, alignment, or
  conflict.

An item-level `InEffect`, partial-status, current-version, or similar HKeL field
is a routing and reconciliation signal. It does not by itself prove
commencement, repeal, expiry, or the status of every child location.

## Parent and child status

A parent status applies to its descendants only when the accepted legal event
and written rule expressly cover the complete branch. An exact child-specific
event or exception may override that inherited status when accepted evidence
expressly identifies the child.

The pipeline never:

- copies status from a sibling;
- assumes every descendant shares an item-level status;
- lets a general parent signal erase an exact child exception; or
- invents inheritance behavior for an unknown status construct.

When the status of a governing lead-in, definition, qualification, table
heading, or other dependency is unresolved, every dependent location remains
inside the affected boundary. A clear child cannot be separated from context
whose legal effect is itself uncertain.

## Serving and authority-note boundary

Only `SEARCHABLE_CURRENT` locations may create ordinary Hong Kong legislation
Search Records. `WAITING_ROOM`, `EVIDENCE_ONLY`, `HISTORICAL`, and
`QUARANTINE` locations remain fully preserved and accounted for outside
current-law Pinecone.

A warning cannot make uncommenced, ended, or uncertain text searchable.
Partial status does not automatically warn every record in the instrument.
Instead, an approved English warning clause in `metadata.authority_note` is
required only when an exact
current record could materially cause the downstream LLM to overstate the
operative scope of its smallest mixed-status parent or another necessary
dependency. Unrelated current locations continue to use the exact string
`"None"`.

For example, a current record for section 4(1) may need a warning that only that
subsection is supported as operative when the rest of section 4 is not. A
record for an independent section 20 does not receive that warning merely
because section 4 has mixed status.

HKeL status labels, Status Coverage Maps, event dates used only for internal
decisions, and review explanations do not enter `metadata.text`. Exact official
words that form part of the legislation remain source text under the existing
renderer rules.

## Bilingual Alignment Groups

Authentic English and Traditional Chinese need not use the same number of
paragraphs or internal markers. The pipeline creates an immutable **Bilingual
Alignment Group** containing one or more consecutive English source units and
one or more consecutive Traditional Chinese source units that official
identifiers and the pinned Source Rulebook establish as the same:

- Legal Item;
- Official Version;
- Legal Location or complete official sub-location;
- operative state; and
- legal relationship to its parent and neighboring groups.

An alignment group may be one-to-one, one-to-many, many-to-one, or many-to-
many. Every authentic-language source unit must appear in exactly one group.
No unit may be orphaned, duplicated, or paired by wording similarity.

The renderer preserves each language's exact wording, markers, nesting, and
source order. It does not reorder Chinese to imitate English or English to
imitate Chinese. Differences in grammar or internal segmentation pass only
when an official structural mapping deterministically proves the common legal
scope. Matching translation, equal word counts, proximity, or a generative LLM
cannot create the mapping.

If complete known evidence contains legal material in one authentic language
that has no corresponding supported material in the other, the result is a
source conflict and enters Quarantine. If the observed construct's published
meaning is unknown, processing blocks and opens Source Contract Review instead.

## Smallest safe affected boundary

A status or bilingual problem affects the smallest complete legal branch that
can safely be separated from the rest. The boundary includes every governing
parent, child, note, heading, definition, lead-in, table relationship, or other
dependency needed to interpret the material.

An independent clear sibling may continue when exact official structure proves
that it does not depend on the conflicted location. If the conflict affects a
governing parent or cannot be contained deterministically, the whole dependent
subtree or item enters Quarantine.

For a first baseline, clear locations may proceed while every quarantined
location remains explicitly accounted for. For an ordinary update, Quarantine
of a previously served record does not automatically authorize either reuse or
removal. The Legal Desk applies ADR 0005's exact carry-forward, Withholding
Release, or no-jurisdiction-rebuild decision. A reconciliation fixture never
silently retires or carries forward production records.

## Accepted partial-status and bilingual-structure fixtures

### `HKLEG-RECON-PSB-FIX-001` — exact partial commencement map

Accepted event evidence names the exact locations that commenced. Matching
current bilingual HKeL bundles exist, the named and unnamed locations are
complete, and the status relationships agree across the accepted sources.

Expected result: reconciliation and status mapping `PASS`. Named operative
locations may receive `SEARCHABLE_CURRENT`; validly made unnamed locations
remain in `WAITING_ROOM` unless another exact event supports a different state.

### `HKLEG-RECON-PSB-FIX-002` — one instrument has several exact dispositions

Complete evidence proves that one instrument contains separately identified
current, uncommenced, repealed or expired, and uncertain locations.

Expected result: status partition `PASS`. Assign `SEARCHABLE_CURRENT`,
`WAITING_ROOM`, `HISTORICAL`, and `QUARANTINE` only to their exact locations.
Do not create one instrument-wide status or a record combining them.

### `HKLEG-RECON-PSB-FIX-003` — fixed future commencement date has not arrived

A validly made location has a proved fixed commencement date after the
observation cutoff and no accepted evidence gives it earlier effect.

Expected result: `WAITING_ROOM`; preserve and monitor it, but create no current
Search Record.

### `HKLEG-RECON-PSB-FIX-004` — commencement date arrived with matching current text

The exact commencement evidence is operative at the cutoff and matching
current bilingual HKeL XML and applicable PDF evidence reconcile for the
affected location.

Expected result: the status gate `PASS` and the location becomes eligible for
`SEARCHABLE_CURRENT` after all remaining record and release gates pass.

### `HKLEG-RECON-PSB-FIX-005` — operative event precedes HKeL consolidation

Accepted evidence proves that a change affecting served wording became
operative, but matching current HKeL XML and applicable PDF evidence are not
yet available.

Expected result: apply `HKLEG-CURRENT-EVENT-001`; record the event and exact
locations and report a `COVERAGE_GAP`. Under ADR 0080, select an eligible
warned `RECONSTRUCTED_CONSOLIDATION` for each affected serving unit. If exact
reconstruction cannot pass, select ADR 0079's warned
`KNOWN_STALE_ANALYTICAL_CARRY_FORWARD` wherever valid latest applicable official HKeL
text is held; otherwise emit no record for that location.

### `HKLEG-RECON-PSB-FIX-006` — `InEffect` signal without commencement proof

A validly made new item has complete source text and an HKeL `InEffect` or
similar current signal, but the evidence required to prove commencement is
absent and no conflicting event is established.

Expected result: `WAITING_ROOM`; the source signal opens investigation but
does not create a current Search Record.

### `HKLEG-RECON-PSB-FIX-007` — unexplained status signal affects a prior current record

A previously served current location receives a new ceased, partial, missing,
or other material status signal, but no accepted event evidence proves the
change.

Expected result: `QUARANTINE` the affected status decision under
`HKLEG-CURRENT-CAUSE-002`. Do not automatically retire, continue, warn, or
carry forward the prior record; ADR 0005 governs the release consequence.

### `HKLEG-RECON-PSB-FIX-008` — partial status has no exact location mapping

The source reports partial or mixed status, but accepted evidence does not
identify the exact provisions, Schedules, paragraphs, or other locations to
which it applies.

Expected result: `QUARANTINE` the smallest complete branch whose status cannot
be separated safely and open targeted status investigation. Do not select a
convenient subset.

### `HKLEG-RECON-PSB-FIX-009` — accepted sources disagree on operative state

HKeL status or structure evidence and accepted Gazette, Editorial Record, or
other fact-specific evidence assign different operative states to the same
location at the same cutoff.

Expected result: `QUARANTINE`. Preserve both facts and do not prefer the newer
artifact, the HKeL label, or the apparently more plausible result.

### `HKLEG-RECON-PSB-FIX-010` — known parent rule and exact child exception

Accepted evidence expressly applies one status to a complete parent branch and
separately identifies an exact child exception. The pinned rulebook defines
the inheritance and override relationship.

Expected result: status mapping `PASS`. Apply the parent state to covered
descendants and the child-specific state only to the exact exception. Record
both evidence paths.

### `HKLEG-RECON-PSB-FIX-011` — unknown status or inheritance semantics

A status value, partial-status construct, hierarchy rule, or parent-to-child
meaning is not defined by the pinned HKeL specification and Source Rulebook.

Expected result: `BLOCK` with `SOURCE_CONTRACT_REVIEW_REQUIRED` under ADR
0028. Preserve the input and do not infer the relationship from neighboring
items, wording, or a generative LLM.

### `HKLEG-RECON-PSB-FIX-012` — warning at the smallest mixed-status parent

An exact current child is independently searchable, but relying on its record
alone could materially imply that a broader mixed-status parent is entirely
operative. Other locations in the instrument are independent of that parent.

Expected result: the current child may proceed only with the Legal Desk-
approved controlled English warning required for that smallest mixed-status
boundary. Independent current locations retain
`metadata.authority_note: "None"`.
The warning does not make any non-current child searchable.

### `HKLEG-RECON-PSB-FIX-013` — officially mapped non-one-to-one language structure

Official identifiers and the pinned mapping establish that one or more
consecutive English units correspond to a different number of consecutive
Traditional Chinese units for the same location, version, state, and role.

Expected result: `PASS`. Create one complete Bilingual Alignment Group and
preserve every authentic unit exactly once.

### `HKLEG-RECON-PSB-FIX-014` — language-specific internal segmentation

The authentic languages use different internal markers, sentence grouping, or
grammatical order inside an officially mapped alignment group, while the
complete legal scope, parent relationship, and group order agree.

Expected result: `PASS`. Preserve each language's own wording, markers,
nesting, and order; do not force visual or one-to-one symmetry.

### `HKLEG-RECON-PSB-FIX-015` — extra or missing authentic-language legal unit

Complete known evidence contains an official legal unit in one authentic
language with no corresponding supported unit in the other language.

Expected result: `QUARANTINE` under `HKLEG-CURRENT-EVID-004`. Do not drop the
unit, translate it, duplicate a neighbor, or create a monolingual record.

### `HKLEG-RECON-PSB-FIX-016` — language structures identify different locations or states

English and Traditional Chinese structures point to different Legal Locations,
parent relationships, Official Versions, or operative states despite similar
wording or nearby positions.

Expected result: `QUARANTINE`. Official identity and status conflict cannot be
repaired by translation similarity.

### `HKLEG-RECON-PSB-FIX-017` — known structures have no deterministic alignment

Both language constructs are understood, but the accepted official identifiers
and mappings cannot assign every unit exactly once to complete corresponding
groups.

Expected result: `QUARANTINE`. Preserve the competing mapping evidence; a
generative LLM, word counts, semantic similarity, and reviewer convenience
cannot create the relationship.

### `HKLEG-RECON-PSB-FIX-018` — unknown bilingual structural construct

One language contains an element, relationship, or identifier whose published
meaning is unknown under the pinned specification bundle.

Expected result: `BLOCK` with `SOURCE_CONTRACT_REVIEW_REQUIRED`. Do not
prematurely label an unknown source contract as a legal conflict.

### `HKLEG-RECON-PSB-FIX-019` — mismatch confined to an independent child

Complete official structure proves that a bilingual or status mismatch is
confined to one child location and that independently supported siblings do not
depend on it or on uncertain governing context.

Expected result: quarantine the affected child only. Siblings may proceed when
their own gates pass, while the Corpus Release accounts for the child,
Quarantine, prior record, and any ADR 0005 consequence exactly.

### `HKLEG-RECON-PSB-FIX-020` — mismatch affects governing or unbounded context

A conflict affects a parent lead-in, definition, qualification, heading, table
relationship, or other context governing several children, or its exact
boundary cannot be determined.

Expected result: `QUARANTINE` the complete smallest dependent subtree, or the
Legal Item when no smaller safe boundary exists. Do not release apparently
clear fragments without their reliable context.

### `HKLEG-RECON-PSB-FIX-021` — renderer invents bilingual alignment

Source evidence and accepted alignment groups are valid, but candidate
construction pairs units by translation similarity, changes source order,
drops or duplicates a unit, translates missing content, or produces a
monolingual part.

Expected result: `BLOCK` as a deterministic processing defect. Correct the
renderer without altering the preserved source evidence or treating the defect
as a source conflict.

## Consequences and remaining catalogue group

Partial legal status and general bilingual structure now have complete status-
coverage, alignment, authority-note, affected-boundary, and release-consequence
examples. The pipeline may keep independently supported current law searchable
without hiding uncertainty, but it cannot use a warning or a small split to
convert unsupported law into current law.

ADR 0040 subsequently settles general overlong-record partitioning and
completes the conceptual HKeL reconciliation catalogue. ADR 0041 settles the
common machine-readable package and catalogue contract. Exact executable
pinned-schema bytes remain later implementation work and cannot change these
accepted IDs or outcomes.

This decision authorizes documentation only. It does not authorize source
access, implementation, AI or embedding calls, release publication, Pinecone
mutation, promotion, or deployment.
