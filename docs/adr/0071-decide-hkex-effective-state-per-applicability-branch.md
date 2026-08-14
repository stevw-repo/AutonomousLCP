---
status: accepted
date: 2026-08-14
refines:
  - "0005"
  - "0054"
  - "0069"
  - "0070"
depends_on:
  - "0018"
refined_by:
  - "0072"
  - "0073"
  - "0074"
---

# Decide HKEX effective state per applicability branch

## Decision

Hong Kong Regulatory Materials effective state is decided for one exact
**applicability branch** at one frozen observation cutoff. It is not assigned
to a whole HKEX update notice, publication, PDF, Chapter, or rule merely from
its update number or publication date.

An applicability branch is one exact rule wording plus the supported cohort,
transaction, reporting period, time window, external condition, or other
limitation governing when that wording applies. One update may create several
branches, and one Legal Location may have more than one concurrently current
branch. Every branch remains owned by exactly one Main Board or GEM Rule
Component Instance.

The atomic Effective-State Decision binds at least the branch, component,
board, Legal Location, cutoff, relevant update part and source ranges,
controlling current-product evidence, applicable date or condition,
transition and cohort facts, predecessor and successor relationships, applied
Source Rulebook rule, result, reason, and evidence fingerprint. Exact schema
field names belong to the later executable contract.

## Branch state and component summary

Every branch receives exactly one state:

- `CURRENT` — effective at the cutoff for ordinary application, without a
  material special applicability limitation, and reconciled to the controlling
  current product;
- `TRANSITIONAL_CURRENT` — effective at the cutoff only for an exact supported
  cohort, transaction, reporting period, time window, or other material branch;
- `FUTURE_FIXED_DATE` — a final published branch whose exact fixed effective
  date is later than the cutoff;
- `FUTURE_CONDITIONAL` — a final published branch whose required external event
  or condition is not proved to have occurred;
- `SUPERSEDED` — a supported successor now governs every former current
  application of the branch;
- `WITHDRAWN` — official evidence removes or repeals the branch for every
  current application without a supported successor for that same obligation;
- `UNKNOWN` — the effective state cannot safely be established from the
  permitted fresh evidence; or
- `NOT_APPLICABLE` — permitted only for an observed entry that is not a Rule
  Component Instance.

ADR 0069's one state per component is an inventory-level summary derived from
the complete branch set; it does not replace or flatten branch decisions:

- exactly one ordinary current branch produces component summary `CURRENT`;
- one or more materially limited current branches, or concurrently current old
  and new branches, produce `TRANSITIONAL_CURRENT`;
- a pending future amendment does not make a still-effective ordinary
  predecessor component transitional merely because change is expected;
- `FUTURE_FIXED_DATE` or `FUTURE_CONDITIONAL` is a component summary only when
  no branch is currently effective and the complete potentially operative set
  supports that one future family;
- `SUPERSEDED` or `WITHDRAWN` requires every formerly current branch to satisfy
  that result; and
- any unresolved fact that could change what is current at the cutoff produces
  component summary `UNKNOWN`.

If mixed future branches cannot be faithfully represented by one component
summary, the summary is `UNKNOWN` unless another accepted rule establishes the
single present result. The complete branch decisions remain preserved and
must never be discarded merely to obtain one summary label.

## Evidence order

The Source Rulebook applies evidence in this order:

1. prove rule-component membership and exactly one board owner under ADR 0069;
2. map every changed range in every accepted final update to exact components
   and branches;
3. apply supported withdrawal, replacement, fixed-date, external-trigger, and
   transition facts to each branch;
4. reconcile the resulting current branch wording and structure with the
   controlling prevailing English product under ADRs 0070 and 0072; and
5. separately decide material disposition and the `PASS`, `BLOCK`, or
   `QUARANTINE` processing result.

A state label alone never authorizes a Search Record, Corpus Release, Pinecone
change, or promotion. A proposal, consultation, draft, expected change,
highest update number, newest URL, or publication date cannot make a branch
current.

All decisions use one immutable cutoff timestamp. Calendar dates are evaluated
in `Asia/Hong_Kong` unless the controlling source expressly supplies another
time zone. A change expressed as taking effect on a date is eligible for
current-state reconciliation when the cutoff reaches that Hong Kong calendar
date. An express time or different time zone controls. Ambiguous temporal
wording produces `UNKNOWN`; the pipeline does not invent precision.

## Fixed-date branches

Before its effective date, a final fixed-date branch is
`FUTURE_FIXED_DATE` and remains in the regulatory Waiting Room. Its currently
effective predecessor remains separately accountable.

Reaching the date does not cause clock-only promotion. At or after the
effective point, the changed wording must reconcile with the applicable
controlling current consolidated rulebook, Regulatory Form, or Fees Rule:

- a complete match may produce `CURRENT` or `TRANSITIONAL_CURRENT`;
- a controlling product that still shows incompatible old wording, omits the
  effective change, or otherwise conflicts produces `UNKNOWN` and Quarantine;
  and
- the pipeline does not reconstruct, splice, or infer the missing current rule.

If a publisher exposes future wording before its stated date, that wording
does not become current early. The future branch remains in the Waiting Room.
Any resulting inability to verify the presently operative predecessor is
handled through ADR 0005's explicit carry-forward, withholding, or no-rebuild
choice, not by treating the early product as current.

## Conditional branches

Every `FUTURE_CONDITIONAL` branch identifies the exact activating fact and the
official Registered Source allowed to prove it under ADR 0070. Positive,
fresh, preserved evidence is required to establish occurrence. The final HKEX
update proves the stated condition but not occurrence of an external event.

A branch may remain `FUTURE_CONDITIONAL` only while accepted evidence is fresh
enough to support non-occurrence. If the event could have happened and its
required source is stale, unavailable, incomplete, or conflicting, the branch
becomes `UNKNOWN`; absence of evidence is not treated as proof that nothing
happened.

For compound conditions:

- an all-of condition activates only after every required fact is proved;
- an any-of condition activates after any permitted fact is proved; and
- an any-of branch remains future only while every alternative is positively
  supported as not having occurred. Otherwise the result is `UNKNOWN`.

After a trigger is proved, the same current-product reconciliation required
for a fixed-date branch applies. Trigger evidence plus conflicting compiled
wording produces `UNKNOWN`, not reconstructed current text.

## Transitional branches

When old and new requirements concurrently apply to different cohorts,
transactions, reporting periods, or time windows, every legally live branch is
`TRANSITIONAL_CURRENT`. The old branch is not globally superseded merely
because a new branch exists.

Different current wording or materially different obligations produce
separate minimum self-contained Search Records. The same wording subject only
to one simple applicability limitation may remain one record when the complete
limitation is included in `metadata.text`. No record may require the downstream
LLM to infer which branch applies from text that was omitted.

An open-ended transition remains current until exact official evidence or
provable cohort exhaustion ends it. The pipeline does not guess that a cohort
is empty. When the last old branch is proved to have ended, it becomes
`SUPERSEDED` if a supported successor covers its former applications, or
`WITHDRAWN` if the obligation ended without such a successor.

Overlapping amendments affecting the same Legal Location form an ordered
branch timeline based on their supported effective facts, not their update
numbers. Simultaneous branches for different cohorts remain transitional. An
unresolved collision, gap, or precedence conflict produces `UNKNOWN`.

## Superseded, withdrawn, and unknown

`SUPERSEDED` requires a supported successor covering every former current
application of the branch. `WITHDRAWN` requires exact official withdrawal or
repeal evidence and no supported successor for the same obligation. A partial
replacement leaves the remaining old branch `TRANSITIONAL_CURRENT`.

Disappearance from a page, navigation tree, search result, filename, URL, PDF,
or table of contents proves neither result. Similar wording, a reused rule
number, and a higher update number also prove no continuity or retirement.

`UNKNOWN` is a legal-state uncertainty result, not a generic synonym for every
technical failure. It includes, for example:

- an effective update that conflicts with the controlling current product;
- a trigger that may have occurred while its official evidence is stale or
  unavailable;
- ambiguous mapping between an amendment and component;
- conflicting effective dates or transition scopes;
- optional Chinese evidence positively indicating an unresolved possible
  defect in the English identity, version, effective state, or completeness;
  or
- an unexplained current-product change that could affect meaning.

`UNKNOWN` enters Quarantine and prevents the affected component from being
claimed as freshly serving-ready. An authority note cannot turn an unknown
state into a current rule.

## Source failure and serving disposition

Technical unavailability without affirmative evidence of legal change does
not create a fictional new current decision. ADR 0005 governs the separate
serving choice:

- carry forward the last approved release only with its last-verified date,
  Coverage Gap, warning, review deadline, and Legal Desk support;
- withhold affected records when available evidence makes continued serving
  materially misleading; or
- build no new jurisdiction target when neither course is safely supported.

A carried-forward record remains last approved, not newly verified at the
current cutoff.

The state-to-disposition mapping is:

| Effective-state result | Ordinary material disposition |
|---|---|
| `CURRENT` | Searchable only after every other gate passes |
| `TRANSITIONAL_CURRENT` | Searchable branch record or records with complete applicability context, after every other gate passes |
| `FUTURE_FIXED_DATE` | Regulatory Waiting Room |
| `FUTURE_CONDITIONAL` | Regulatory Waiting Room with targeted live-trigger monitoring |
| `SUPERSEDED` | Historical and traceable outside Pinecone |
| `WITHDRAWN` | Historical and traceable outside Pinecone |
| `UNKNOWN` | Quarantine; no new current Search Record |
| `NOT_APPLICABLE` | No regulatory Search Record |

Material applicability context must appear in `metadata.text`, because the
downstream LLM receives only serving metadata. A controlled English
`metadata.authority_note` may additionally warn about a material transition,
scope, source, representation, or unresolved-reference limitation. It remains
`"None"` when the labelled text and context fully communicate the rule and no
specific reliance warning applies.

## Required examples and conformance

The executable Source Rulebook and conformance catalogue must cover at least:

- one update split across several fixed dates;
- one update containing both fixed-date and external-trigger branches;
- old and new rules concurrently current for different cohorts;
- a future product published early;
- a passed effective date with a lagging or conflicting current product;
- all-of and any-of external conditions;
- partial and complete supersession;
- withdrawal without replacement;
- disappearance without withdrawal evidence;
- overlapping amendments to one Legal Location;
- a stale trigger source when the event could have occurred;
- optional Chinese discrepancies that respectively do and do not expose a
  possible controlling English defect; and
- each ADR 0005 carry-forward, withholding, and no-rebuild outcome.

Official examples informing this rule set include [HKEX Update
153](https://en-rules.hkex.com.hk/rulebook/update-no-153), whose parts have
different fixed dates and transitional arrangements; [HKEX Update
152](https://en-rules.hkex.com.hk/rulebook/update-no-152), whose parts combine
external triggers with a fixed date; and [HKEX Update
150](https://en-rules.hkex.com.hk/rulebook/update-no-150), whose commencement
distinguished new applicants from existing issuers.

## Allocation and authorization boundary

This ADR defines the legal-state result and evidence contract. It does not
decide which future implementation steps are deterministic, LLM-assisted, or
human-reviewed. That allocation remains deliberately deferred. No model may
invent missing dates, conditions, cohorts, trigger occurrence, current wording,
or conflict resolution.

This ADR authorizes documentation only. It does not register live endpoints,
acquire source artifacts, implement connectors or schemas, call an LLM or
embedding provider, construct or publish a corpus, access Pinecone or Azure,
promote, deploy, commit, push, or perform any other production action.
