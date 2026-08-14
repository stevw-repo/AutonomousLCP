---
status: accepted
date: 2026-08-12
amended_by:
  - "0079"
  - "0080"
  - "0081"
amends:
  - 0033
refines:
  - 0041
  - 0042
depends_on:
  - 0005
---

# Normalize Hong Kong current-update results and complete observation-failure cases

Hong Kong Legislation current-update rules must not use one word such as
`outcome` to mean several different things. Every conformance result keeps the
dimensions fixed by ADR 0041 separate:

- **processing outcome** — `PASS`, `BLOCK`, or `QUARANTINE`;
- **legal disposition** — the legal object's serving state, or
  `NOT_APPLICABLE` before the disposition gate;
- **coverage effect** — whether an exact Coverage Gap must be published;
- **Source Contract Review** — whether unknown source meaning requires review;
- **record output** — exact candidate records or explicitly none; and
- **reason or workflow code** — the stable explanation or next-path result.

A rule may influence more than one dimension, but it cannot collapse them into
one overloaded enum. In particular, `COVERAGE_GAP` is not a legal disposition,
`WAITING_ROOM` is not a processing failure, and `SUPPORTED_NO_CHANGE` is a
workflow result rather than a sixth legal disposition.

## Normalized rule results

ADR 0033's named current-update results have these meanings:

| Rule situation | Processing | Legal disposition | Coverage | Record output | Stable explanation or next path |
|---|---|---|---|---|---|
| Complete supported no change | `PASS` | `NOT_APPLICABLE` | `NONE` | `NONE` | `SUPPORTED_NO_CHANGE`; reuse the prior accepted Corpus Release |
| A genuine affected signal | `PASS` | `NOT_APPLICABLE` | `NONE` | `NONE` at the observation gate | `AFFECTED_ACQUISITION_REQUIRED`; continue bounded affected work |
| Release-blocking Observation unavailable after retries | `BLOCK` | `NOT_APPLICABLE` | exact Coverage Gap | `NONE` | `RELEASE_BLOCKING_OBSERVATION_UNAVAILABLE`; apply ADR 0005 |
| Required affected evidence unavailable | `BLOCK` | `NOT_APPLICABLE` | exact gap only when current coverage or a release claim depends on it | `NONE` | `AFFECTED_EVIDENCE_UNAVAILABLE` |
| Evidence or cause conflict | `QUARANTINE` | `NOT_APPLICABLE` at that checkpoint | determined by later complete release accounting | `NONE` | the exact conflict reason |
| No accepted predecessor for an ordinary update | `BLOCK` | `NOT_APPLICABLE` | `NONE` | `NONE` | `INITIAL_BASELINE_REQUIRED`; open ADR 0034's baseline path |
| Operative event proved before matching consolidation | `PASS` | `NOT_APPLICABLE` for the unavailable new current version | exact Coverage Gap | eligible warned ADR 0080 reconstruction; otherwise warned `KNOWN_STALE_ANALYTICAL_CARRY_FORWARD` payload wherever valid latest applicable official HKeL text is held; otherwise `NONE` | `EVENT_PROVED_CONSOLIDATION_MISSING`; apply ADRs 0080, 0081, and 0079 |

The disposition gate later assigns exactly one of the five accepted legal
dispositions where a legal-object disposition is actually decided. A
quarantined processing result may therefore lead release accounting to record
the legal object as `QUARANTINE`; this does not make the two fields synonyms.

Exact code-catalog schemas remain an implementation artifact of the frozen
Source Rulebook Package. Their semantics must match this table.

## Missing conformance coverage

ADR 0033 originally defined `HKLEG-CURRENT-OBS-003` but did not include a
positive conformance case for either of its two branches. Add:

- `HKLEG-CURRENT-CASE-017` for an unavailable release-blocking current
  inventory or Gazette Observation; and
- `HKLEG-CURRENT-CASE-018` for an unavailable item-specific affected-work
  source while independent affected work remains complete.

The accepted Hong Kong Legislation conformance universe is therefore:

- 89 HKeL reconciliation fixtures;
- 18 ordinary current-update cases; and
- 14 first-baseline cases;

for **121 exact tests** in the initial frozen rulebook package.

## Consequences

Implementations and review displays must show the dimensions independently.
They must not infer searchability from `PASS`, treat a Coverage Gap as a legal
status, or turn an unavailable source into Quarantine when the correct result
is a processing block.

This decision corrects documentation and test coverage only. It authorizes no
implementation, source access, AI or embedding call, release publication,
Pinecone mutation, promotion, or deployment.
