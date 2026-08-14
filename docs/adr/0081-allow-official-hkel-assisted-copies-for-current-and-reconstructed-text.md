---
status: accepted
date: 2026-08-14
amends:
  - "0019"
  - "0022"
  - "0023"
  - "0024"
  - "0025"
  - "0026"
  - "0027"
  - "0029"
  - "0030"
  - "0032"
  - "0033"
  - "0034"
  - "0038"
  - "0042"
  - "0044"
  - "0079"
  - "0080"
refines:
  - "0013"
  - "0020"
  - "0021"
  - "0050"
  - "0078"
depends_on:
  - "0028"
  - "0032"
refined_by:
  - "0082"
  - "0086"
---

# Allow official HKeL assisted copies for current and reconstructed text

## Decision

Ask.Legal may use the latest applicable official HKeL copy whether HKeL labels
that copy **verified** or **assisted**. This applies to ordinary current Hong
Kong Legislation records, the base used by ADR 0080 reconstruction, and the
unchanged-text fallback used by ADR 0079 when reconstruction cannot pass.

The objective is to keep the searchable Ordinances and other covered Hong Kong
legislation as up to date as the accepted official HKeL material permits. The
pipeline does not hold back a newer complete assisted HKeL version merely
because an older verified version has the verification mark.

This amends ADR 0022's verified-copy requirement and broadens ADR 0029's former
constitutional-and-other-instruments-only assisted-copy exception. The
verification label remains preserved evidence, but it is no longer a general
record-eligibility or reconstruction-base gate.

## What counts as an assisted copy

This decision covers only a copy supplied by HKeL in its official product and
identified by HKeL as an assisted copy. It does not accept arbitrary web text,
search-result HTML, RTF, a third-party mirror, an unofficial scan, or a copy
whose source or version cannot be proved.

The ordinary evidence bundle still requires:

- complete matching English and Traditional Chinese HKeL XML;
- matching English and Traditional Chinese HKeL verified or assisted copies
  for the same item, version, locations, and cutoff;
- deterministic XML-to-copy reconciliation of all legal content and structure;
- complete status, identity, source-unit coverage, and bilingual alignment;
  and
- exact preserved source bytes, HKeL labels, metadata, fingerprints, and
  traceability.

The active Registered Source role is `HK-LEG-HKEL-ASSISTED-COPIES`. It replaces
the narrower pre-implementation design ID
`HK-LEG-HKEL-CONSTITUTIONAL-ASSISTED-COPIES`; the active Hong Kong source count
remains fourteen. Historical references to the old ID remain evidence of the
superseded boundary and cannot be emitted by the current rulebook package.

If a verified and an assisted copy represent the same exact version, the
verified copy is the stronger evidence and is retained. If the assisted copy
supports a newer applicable HKeL version, the newer complete version may
proceed after all ordinary gates. Verification status never cures a wording,
version, bilingual, structure, or identity mismatch.

Assisted-copy status alone creates no `metadata.authority_note`. The record
uses the same legislation type, source, citation, quotation, retrieval,
ranking, release, and downstream handling as another HKeL record. The evidence
class remains available internally through the Management Register, Evidence
Vault, and Record Traceability Lookup.

## Reconstruction amendment

ADR 0080 reconstruction may begin from the latest applicable bilingual HKeL
base supported by matching verified or assisted copies. Every other
reconstruction control remains unchanged: complete operative amendment and
commencement evidence, event-chain closure, supported deterministic operations,
separate authentic-language application, complete bilingual reconciliation,
reproducibility, mandatory warning, ADR 0079 fallback, and later comparison
with HKeL.

The exact reconstruction `metadata.authority_note` is amended only to remove
the inaccurate verified-only claim:

```text
[WARNING: RECONSTRUCTED CONSOLIDATION] As at [observation cutoff], HKeL had not yet published an updated consolidated copy incorporating the proved operative amendments affecting this provision. This record is a reconstructed consolidation using the latest applicable HKeL copy, version date [base version date], and the official amendment and commencement evidence identified in metadata.source, effective [effective date or exact applicability condition]. [INSTRUCTION: If you use this record to support any part of an answer, you must explicitly include the preceding warning in your response.]
```

The warning and instruction behavior otherwise remain exactly as accepted by
ADR 0080. If the model uses the record, it reproduces the warning portion and
does not reproduce the instruction portion.

## Known-stale fallback amendment

ADR 0079's fallback also starts from the latest applicable official HKeL text
validly held, whether its supporting copies are verified or assisted. A newer
eligible assisted HKeL version is not displaced by an older verified version.
The fallback remains unchanged source text with a mandatory stale warning; it
does not reconstruct or silently claim currency.

## Consequences

This decision increases currency by accepting HKeL's latest complete official
product without treating the verification mark as a universal freshness gate.
It accepts more source-representation risk than requiring verified copies for
every record. Exact official origin, bilingual XML-and-copy reconciliation,
version matching, preservation, and traceability remain mandatory controls.

This ADR authorizes design documentation only. It does not authorize source
access, implementation, model or embedding calls, release publication,
Pinecone mutation, promotion, Azure changes, deployment, commit, push, or
another remote action.
