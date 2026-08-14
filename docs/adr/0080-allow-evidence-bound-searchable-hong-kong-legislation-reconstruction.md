---
status: accepted
date: 2026-08-14
amended_by:
  - "0081"
refined_by:
  - "0082"
  - "0083"
  - "0084"
  - "0085"
  - "0086"
  - "0087"
amends:
  - "0005"
  - "0012"
  - "0019"
  - "0022"
  - "0023"
  - "0025"
  - "0026"
  - "0033"
  - "0034"
  - "0038"
  - "0044"
  - "0079"
refines:
  - "0011"
  - "0013"
  - "0020"
  - "0021"
  - "0029"
  - "0035"
  - "0036"
  - "0037"
  - "0040"
  - "0041"
  - "0042"
  - "0043"
  - "0050"
  - "0078"
depends_on:
  - "0025"
  - "0038"
  - "0079"
---

# Allow evidence-bound searchable Hong Kong legislation reconstruction

## Decision

When accepted official evidence proves that a Hong Kong legislative amendment
affecting served wording is operative but HKeL has not yet published the
matching updated consolidation, Ask.Legal may construct and serve the resulting
consolidated text under the serving mode `RECONSTRUCTED_CONSOLIDATION`.

This decision supersedes ADR 0023's prohibition on internal and searchable
reconstruction. It also changes ADR 0079 from the normal result into the safe
fallback: when reconstruction cannot be completed exactly, valid latest
applicable official HKeL text remains searchable under ADR 0081 as
`KNOWN_STALE_ANALYTICAL_CARRY_FORWARD` with its own warning. If no valid base
text exists, no record is created.

Reconstruction is not estimation. The pipeline may perform only exact,
reproducible amendment operations whose complete evidence, legal effect,
location mapping, bilingual result, and ordering are proved. An unsupported,
incomplete, conflicting, or ambiguous operation never produces reconstructed
text.

## Eligibility

A reconstructed consolidation is eligible only when all of the following are
proved at one frozen observation cutoff:

1. the exact latest applicable HKeL English and Traditional Chinese base,
   supported by matching verified or assisted HKeL copies under ADR 0081, and
   its version date, identities, locations, structure, and preserved bytes are
   available;
2. complete official amendment text identifies every change affecting the
   relevant locations after that base version and through the cutoff;
3. accepted official commencement evidence proves the exact effective date or
   applicability condition for every applied amendment;
4. the event chain is complete and deterministically ordered, including
   interacting amendments, corrections, renumbering, repeals, substitutions,
   savings, transitions, and partial commencement that affect the result;
5. every amendment maps to exact base or intermediate locations using an
   operation expressly supported by the active Source Rulebook;
6. English and Traditional Chinese operations are applied separately to their
   authentic text and the resulting bilingual structure reconciles completely;
7. the reconstructed serving unit contains the same minimum governing context
   and passes the same source-unit coverage, partitioning, metadata, and payload
   gates as an ordinary Hong Kong Legislation record; and
8. the exact derivation, evidence, rulebook, engine build, outputs, and
   fingerprints reproduce independently.

ADR 0081 makes verified and assisted official HKeL copies equally eligible as
reconstruction bases after their applicable evidence gates pass. The exact
evidence label remains preserved internally, but the ordinary serving record
does not receive separate source treatment merely because its base was
assisted.

The reconstruction engine uses a closed, versioned supported-operation
registry. No catch-all operation, textual-similarity guess, silent repair,
unproved interpolation, or model-generated final wording is permitted. A
generative model may receive a proposal or challenge role only if a later task-
allocation decision under ADR 0043 admits it. Whether or not such a proposal
role is later used, deterministic rules apply the admitted operations and
produce the final bytes.

## Internal artifact and serving treatment

The register stores one immutable **Reconstructed Consolidation Artifact** for
each exact successful result. It is not an HKeL Official Version or verified
copy. That internal distinction exists for evidence, reproduction, replacement,
and audit; it does not create different ordinary serving behavior.

The selected Search Record follows the same rules as official Hong Kong
Legislation for:

- `metadata.type: "legislation"`;
- Pinecone index and namespace selection;
- semantic retrieval and ranking;
- bilingual `metadata.text` construction and splitting;
- `metadata.source`, citation, quotation, and source display;
- downstream context delivery; and
- release, Approval, promotion, rollback, and retirement.

There is no reconstructed material type, separate index, separate namespace,
lower ranking, separate query path, special citation restriction, or special
quotation restriction. The only special record-level treatment is the
mandatory `metadata.authority_note` warning.

The traceability lookup binds the reconstructed record to the base Official
Version, every amendment and commencement artifact, the complete ordered
operation list, exact affected locations, English and Traditional Chinese
coverage proofs, Source Rulebook and reconstruction-engine versions, Legal
Desk Decision, Corpus Release, and later official reconciliation.

## Exact authority note

Every reconstructed Search Record carries this one controlled English
`metadata.authority_note` string, with only evidence-backed placeholders
filled:

```text
[WARNING: RECONSTRUCTED CONSOLIDATION] As at [observation cutoff], HKeL had not yet published an updated consolidated copy incorporating the proved operative amendments affecting this provision. This record is a reconstructed consolidation using the latest applicable HKeL copy, version date [base version date], and the official amendment and commencement evidence identified in metadata.source, effective [effective date or exact applicability condition]. [INSTRUCTION: If you use this record to support any part of an answer, you must explicitly include the preceding warning in your response.]
```

The warning is the text beginning with `[WARNING: RECONSTRUCTED
CONSOLIDATION]` and ending immediately before `[INSTRUCTION: ...]`. If the
model uses the record to support any part of an answer, it includes that
complete preceding warning explicitly in the response. It does not reproduce
the instruction itself. Retrieval without use does not trigger the instruction.
No separately reworded response-warning template is introduced.

The renderer identifies different cutoffs, base versions, effective dates, or
applicability branches exactly rather than compressing them into a false single
date. It states only that HKeL had not published the matching consolidation at
the proved cutoff; it does not claim that HKeL is generally out of date.

Because reconstructed `metadata.text`, `metadata.source`, or
`metadata.authority_note` differs from the former six-field payload, the result
selects a new Search Record ID. An embedding may be reused only in the unusual
case where the exact `metadata.text` and admitted embedding contract are both
unchanged. All earlier records remain immutable.

## Selection, fallback, and review

For each affected serving unit, the candidate release selects exactly one
ordinary search result:

1. a fully eligible `RECONSTRUCTED_CONSOLIDATION` record;
2. otherwise, an ADR 0079 and ADR 0081 `KNOWN_STALE_ANALYTICAL_CARRY_FORWARD`
   record when valid latest applicable official HKeL text is held; or
3. otherwise, no Search Record and an exact Coverage Gap.

The old official and known-stale records remain preserved outside the active
selection. They do not compete with the reconstructed result in ordinary
semantic retrieval. Unaffected locations proceed normally, and one failed
operation does not block an independently complete sibling.

An ordinary successful supported operation is automatic after deterministic
validation and is reported to humans; it does not require item-by-item human
approval. An ordinary unsupported reconstruction falls back and is reported.
Human review is reserved for the already accepted exceptional triggers, such
as unresolved legal effect or identity, conflicting controlling evidence, a
new operation class or source meaning, an uncontainable cross-location effect,
or another genuinely exceptional change. Human review cannot waive a missing
eligibility proof or authorize guessed text.

The Coverage Gap remains open while HKeL lacks the matching consolidation even
when a reconstructed record serves. Coverage status exposes the same
reconstruction warning; it does not create a different material or source-
handling class.

## Official replacement and reconciliation

When HKeL later publishes the matching applicable consolidation, the pipeline
acquires and validates it through the ordinary bilingual XML-and-PDF gates,
compares it with the reconstructed result, and selects the official result for
the next approved release. The reconstructed record and derivation remain
preserved outside the active selection. The reconstruction warning disappears
only with that replacement, and the changed payload receives or reselects the
appropriate exact Search Record ID.

An exact match is positive reconstruction evaluation evidence. A material
wording, structure, location, effect, or bilingual mismatch is recorded as a
reconstruction failure and suspends the affected operation class or rulebook
rule until corrected and re-admitted. A valid new HKeL consolidation is not
withheld merely to preserve a matching reconstructed result; the official
record replaces it after the ordinary gates pass. If the new official evidence
is itself conflicting or invalid, the pre-existing Quarantine and release-
scope rules apply.

## Conformance amendments

`HKLEG-CURRENT-CASE-006`, `HKLEG-BASE-CASE-012`, and
`HKLEG-RECON-PSB-FIX-005` retain their permanent IDs. Their former no-
reconstruction result is superseded. They now require an eligible reconstructed
record when the exact reconstruction proofs are present, ADR 0079 fallback when
they are not, complete Coverage Gap accounting, and no silent omission.

The supported-operation registry, executable reconstruction cases, fixture
bytes, exact thresholds, and expected artifacts are the next specification
checkpoint. Until that package is frozen and passes the Source Rulebook
conformance gates, the accepted reconstruction capability exists in design but
cannot produce an implementation-ready or promotable record. The currently
frozen 121-case Hong Kong Legislation suite remains the pre-reconstruction
executable baseline and must not be misrepresented as proving this new
capability.

## Consequences

Ask.Legal can provide a more up-to-date searchable consolidation during an
official publication lag without pretending that HKeL published the text.
The value comes with higher correctness risk than serving only published
consolidations. Exact eligibility, deterministic final text, bilingual proof,
complete traceability, mandatory warning, safe fallback, and later comparison
with HKeL control that risk.

This ADR authorizes design documentation only. It does not authorize schema or
application implementation, source acquisition, model or embedding calls,
release publication, Pinecone mutation, promotion, Azure changes, deployment,
commit, push, or another remote action.
