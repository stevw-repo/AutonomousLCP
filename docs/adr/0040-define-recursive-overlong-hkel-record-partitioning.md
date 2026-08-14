---
status: accepted
date: 2026-08-12
refined_by:
  - "0080"
  - "0085"
amends:
  - 0021
refines:
  - 0011
  - 0013
  - 0018
  - 0019
  - 0036
  - 0037
  - 0038
depends_on:
  - 0020
  - 0022
---

# Define recursive overlong HKeL record partitioning

An ordinary Hong Kong legislation Legal Location produces one complete
English-and-Traditional-Chinese Search Record whenever its final serving
payload fits the pinned serving limits. Separate Legal Locations are never
combined merely because they are short, and a record is never split to reach a
preferred size. There is no target or minimum size.

If the complete payload is over a hard limit, the system partitions it only at
complete, officially supported, bilingual legal units. It descends recursively
through the source structure when a child is itself too large. It never falls
back to a sentence, punctuation mark, whitespace position, token position, or
character count unless that exact boundary is independently an official legal
unit under the pinned HKeL specification and Hong Kong Legislation Source
Rulebook.

This decision accepts the reusable contract discipline found in the legacy
Australian legislation pipeline while rejecting that implementation's unsafe
sentence, punctuation, and exact-character fallbacks.

## Exact payload and limits

The system constructs the complete final record before deciding whether it
fits. The measurement includes:

- the canonical English and Traditional Chinese authentic-text blocks;
- exact Legal Location and serving-part labels;
- every required repeated bilingual dependency;
- the final part number and total part count; and
- every other byte in the complete compact serving metadata, including the
  required `metadata.authority_note` string.

The embedding ceiling is measured over the exact final `metadata.text` with
the tokenizer pinned by the approved embedding contract. The separate serving-
metadata byte ceiling is measured over the exact compact serialized metadata
accepted by the serving contract. `metadata.authority_note` is excluded from the
embedding input under ADR 0013 but included in the metadata-byte measurement.

The exact embedding model, tokenizer, token ceiling, serialization, and byte
ceiling are later pinned technical-contract values. An implementation cannot
substitute a character estimate, another tokenizer, a target size, or a safety
margin for either exact check.

## Recursive legal-unit frontier

The reconciled bilingual source forms an ordered tree of official units and
accepted Bilingual Alignment Groups. The partitioner begins with the complete
children of the normal Legal Location.

For each child:

1. render the child with all context and dependencies it would require as a
   standalone serving part;
2. keep it whole when it fits;
3. if it does not fit and the pinned source structure supplies complete aligned
   children, replace it with those children and repeat the check; and
4. if it does not fit and no smaller complete supported unit exists, quarantine
   the smallest complete dependent branch and record a Coverage Gap.

This produces the **partition frontier**: the largest consecutive complete
bilingual source units that are individually safe to serve. Different parts of
one provision may reach different official depths. A complete subsection may
remain whole while an independently structured oversized sibling descends to
paragraphs or subparagraphs.

The following are indivisible unless the source and rulebook expressly provide
a smaller faithful bilingual structure:

- one Bilingual Alignment Group;
- a table row or legally inseparable row group;
- a prescribed-form field or group whose labels and values depend on one
  another;
- a statutory note and the unit to which its legal effect is attached; and
- a definition, qualification, exception, proviso, lead-in, or other governing
  text together with the smallest branch that depends on it.

Unknown source structure blocks with `SOURCE_CONTRACT_REVIEW_REQUIRED`; it is
not treated as an indivisible legal fact or repaired by an LLM.

## Dependency closure

Every final part must be independently understandable without retrieving a
neighboring part. It therefore carries **dependency closure**: the smallest
complete bilingual set of governing headings, lead-ins, column headers,
definition scope, qualifications, notes, and other context required to
interpret its primary content correctly.

Repeated governing text uses the bilingual repeated-parent-context labels from
ADR 0021. Repetition is not sliding-window overlap and cannot be added merely
to improve retrieval. If a required dependency plus the smallest dependent
unit cannot fit, the dependency is never discarded. The dependent branch is
quarantined and the release records the resulting Coverage Gap.

Cross-provision targets are not dependency text. ADR 0037 preserves the exact
referring words and an internal Cross-Reference Relationship instead of
copying target wording into the record.

## Deterministic grouping

Partition-frontier units remain in source order and cannot cross the normal
Legal Location boundary. Among all safe contiguous partitions after final
labels and dependencies are rendered, the canonical partition is:

1. the valid partition with the fewest serving parts; then
2. among ties, the partition that places the greatest possible number of
   consecutive frontier units in the earliest part, then in each later part.

This minimum-part, earliest-full rule is a precise form of greedy grouping. It
avoids circular estimates when the final `Serving part: X of N` and
`服務部分：第X部分，共N部分` labels themselves affect size. The chosen partition
is accepted only after every part is re-rendered with the actual final total
and passes both exact ceilings. Failure to reach the canonical result is a
deterministic processing defect, not a legal uncertainty.

## Source-unit accounting and identity

Every partition produces an internal **Primary Source-Unit Coverage Proof**.
It demonstrates that:

- every authentic English and Traditional Chinese source unit belongs to
  exactly one primary serving part;
- the primary parts preserve source order;
- every bilingual pairing comes from an accepted Bilingual Alignment Group;
- repeated context points to its original source unit and is labelled as
  repeated rather than counted as primary content; and
- nothing was dropped, duplicated, translated, summarized, paraphrased,
  modernized, silently corrected, or invented.

The proof and source mappings remain in the Management Register, Evidence
Vault, and Record Traceability Lookup; they do not add a Pinecone metadata
field or operational prose to `metadata.text`.

Each serving part receives its own register-issued immutable Search Record ID.
Source paths, visible locators, part numbers, and split ordinals do not define
identity. Any changed authentic text, authority note, dependency closure, canonical
label, or partition boundary produces new Search Records and explicit
replacement or split lineage under ADR 0011.

## Conformance fixtures

The accepted final conceptual HKeL reconciliation group is:

| Stable fixture ID | Condition | Required result |
|---|---|---|
| `HKLEG-RECON-ORP-FIX-001` | The complete final bilingual location fits both exact ceilings | `PASS`; create one unsplit record |
| `HKLEG-RECON-ORP-FIX-002` | Several separate short Legal Locations could fit together | `PASS`; keep one record per location and do not merge them |
| `HKLEG-RECON-ORP-FIX-003` | The complete record exceeds only the pinned `metadata.text` token ceiling | Apply the canonical recursive partition and revalidate every part |
| `HKLEG-RECON-ORP-FIX-004` | Token input fits but the complete compact metadata, including `authority_note`, exceeds the byte ceiling | Apply the same canonical partition; both ceilings are independent |
| `HKLEG-RECON-ORP-FIX-005` | Several consecutive complete frontier units can be grouped in more than one valid way | Choose the minimum-part, earliest-full canonical partition |
| `HKLEG-RECON-ORP-FIX-006` | One subsection is too large but its official aligned paragraphs can each be served safely | Descend recursively to paragraphs only for that oversized branch |
| `HKLEG-RECON-ORP-FIX-007` | A paragraph remains too large but complete official aligned subparagraphs fit | Descend again; do not stop at the first structural level |
| `HKLEG-RECON-ORP-FIX-008` | One officially established non-one-to-one Bilingual Alignment Group is encountered | Keep the complete group indivisible and preserve every authentic unit once |
| `HKLEG-RECON-ORP-FIX-009` | Child text depends on a parent lead-in, qualification, definition scope, or proviso | Repeat the minimum complete bilingual dependency in every affected part and count it before acceptance |
| `HKLEG-RECON-ORP-FIX-010` | Parent material is useful background but not required to interpret the child | Do not repeat it merely for retrieval enrichment |
| `HKLEG-RECON-ORP-FIX-011` | A split table or form part depends on column headers, field labels, or an inseparable row or field group | Repeat required bilingual headers or labels; never divide an inseparable group |
| `HKLEG-RECON-ORP-FIX-012` | A statutory note has legal effect attached to the affected unit | Keep the note with its dependency closure; do not strand it in another part |
| `HKLEG-RECON-ORP-FIX-013` | Final part totals or part-number labels change whether a tentative grouping fits | Select using the actual final labels and revalidate the complete canonical partition |
| `HKLEG-RECON-ORP-FIX-014` | Candidate parts fit but one authentic source unit is missing from primary coverage | `BLOCK` as a deterministic processing defect |
| `HKLEG-RECON-ORP-FIX-015` | Candidate parts fit but primary content is duplicated or reordered | `BLOCK` as a deterministic processing defect; labelled dependency repetition remains permitted |
| `HKLEG-RECON-ORP-FIX-016` | A sentence, punctuation, whitespace, token, or character cut would fit but is not an official legal boundary | Reject the cut; continue through supported structure or quarantine the dependent branch |
| `HKLEG-RECON-ORP-FIX-017` | The smallest complete bilingual legally indivisible unit plus required dependencies exceeds a ceiling | `QUARANTINE` the smallest complete dependent branch and record a `COVERAGE_GAP`; never truncate |
| `HKLEG-RECON-ORP-FIX-018` | A proposed boundary exists in one authentic language but no accepted alignment supports the corresponding other-language boundary | `QUARANTINE`; do not create monolingual or mismatched parts |
| `HKLEG-RECON-ORP-FIX-019` | Parsing assigns authentic text to the wrong Legal Location even though every record fits and all text is present | `BLOCK` as a deterministic source-location ownership defect |
| `HKLEG-RECON-ORP-FIX-020` | Two clean builds use identical evidence and pinned contracts | Both complete outputs, partition proofs, and reports must be byte-identical |
| `HKLEG-RECON-ORP-FIX-021` | A source element or dependency relationship has unknown published meaning | `BLOCK` with `SOURCE_CONTRACT_REVIEW_REQUIRED`; do not guess a split boundary |
| `HKLEG-RECON-ORP-FIX-022` | A new Official Version of previously served material cannot now be partitioned safely | Quarantine the affected branch; ADR 0005 requires an explicit carry-forward, Withholding Release, or no-rebuild decision, with no silent reuse or retirement |

Every fixture binds minimal HKeL-shaped XML and applicable PDF evidence,
source-unit identities, the pinned source interpretation, exact expected
canonical text or failure result, token and byte measurements, Rule Trace,
partition proof, and record-lineage consequence. Exact production ceiling
numbers and executable source-schema bytes are supplied by their later pinned
technical contracts and cannot weaken these outcomes. ADR 0041 defines the
common strict manifest, frozen catalogue, hashed-artifact, and semantic-
validation package that will encode these fixtures.

## Consequences

The final conceptual Hong Kong HKeL reconciliation catalogue is complete:
ordinary provisions; Schedules, tables, and forms; notes, images, and cross-
references; partial status and bilingual structure; and recursive overlong-
record partitioning.

Reproducibility is necessary but not sufficient. Tests must assert correct
Legal Location ownership, dependency closure, bilingual unit coverage, and
exact expected output or disposition, not merely that text survived and each
record fits.

This decision authorizes documentation only. It does not authorize source
access, implementation, AI or embedding calls, release publication, Pinecone
mutation, promotion, or deployment.
