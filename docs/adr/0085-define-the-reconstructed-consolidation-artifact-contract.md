---
status: accepted
date: 2026-08-14
refines:
  - "0011"
  - "0016"
  - "0021"
  - "0040"
  - "0041"
  - "0042"
  - "0078"
  - "0080"
  - "0082"
  - "0083"
  - "0084"
depends_on:
  - "0013"
  - "0021"
  - "0038"
  - "0040"
  - "0050"
  - "0078"
  - "0080"
  - "0081"
  - "0082"
  - "0084"
refined_by:
  - "0086"
  - "0087"
---

# Define the Reconstructed Consolidation Artifact contract

## Decision in simple language

A successful reconstruction produces one immutable **Reconstructed
Consolidation Artifact** before it produces any Search Record. The artifact is
the complete bilingual legal structure that the ordinary Hong Kong legislation
renderer consumes.

It contains no legal guess and no model-written wording. Every final English
and Traditional Chinese source unit must be traced either to unchanged bytes in
the selected HKeL base or to one exact admitted operation and its official
amendment evidence. If any final word, punctuation mark, number, heading,
structural relationship, table element, Form element, or asset relationship
cannot be accounted for, the artifact is invalid and no reconstructed record
may be rendered.

The artifact is not an HKeL Official Version. It is an immutable internal
derivation package used for evidence, deterministic rendering, traceability,
later comparison with HKeL, and audit. Its Search Records retain the ordinary
legislation serving path and the ADR 0080 warning.

## Identity and dependency direction

The Management Register issues one immutable artifact ID matching
`^rca_[0-9a-f]{48}$`. The ID is not calculated from the chapter number,
provision, base version, cutoff, Plan, output, or fingerprint.

The dependency direction is fixed and acyclic:

```text
accepted Reconstruction Plan
        ↓
deterministic execution
        ↓
Reconstructed Consolidation Artifact
        ↓
Reconstruction Execution Report references the artifact
        ↓
ordinary rendering, release, traceability, and serving gates
```

The artifact references the accepted Plan but not the Execution Report. The
Report references both the Plan and artifact. The Record Traceability Lookup
later references all three. This prevents Plan–Report–artifact fingerprint
cycles.

## Strict package boundary

One artifact is a declared strict package:

```text
reconstructed-consolidation-artifact/
├── manifest.json
├── trees/
│   ├── en.json
│   └── zh-Hant.json
├── source-units/
│   ├── en.jsonl
│   └── zh-Hant.jsonl
├── reconstructed-location-units.jsonl
├── bilingual-alignment-map.json
├── dependency-closure-proof.json
├── source-unit-coverage-proof.json
├── derivation-map.json
└── identity-lineage-result.json
```

All eleven roles are required. The future executable package may use a
different enclosing storage prefix, but these package-local paths, roles, and
input/output separation are fixed. The manifest enumerates every file and
SHA-256 hash. No directory discovery, optional undeclared file, symlink,
absolute path, parent traversal, URI retrieval, mutable alias, external read,
or host-specific path is permitted.

The package contains derived structured artifacts, not the original source
files. Original HKeL XML and copies, Gazette instruments, Editorial Records,
commencement evidence, and other source bytes remain immutable Evidence Vault
objects reached through typed references and fingerprints.

## Canonical encoding

JSON and JSONL use their strict registered schemas, I-JSON, RFC 8785 JCS rules,
UTF-8, and exact line and ordering contracts. Fingerprints use
`sha256:<64-lowercase-hex>`. Binary assets are not rewritten or embedded in
JSON; a structure that relies on an asset uses an immutable evidence reference
and exact binary fingerprint under the pinned ordinary HKeL renderer contract.

The complete artifact-package fingerprint hashes one canonical inventory of
every package path, role, media type, file size, and exact file hash. The root
fingerprint is stored outside `manifest.json` with the issued `rca_` ID,
avoiding a self-reference. Equal hashes never replace exact byte equality and
collision checking at registration.

## Manifest contract

`manifest.json` is a closed object requiring:

| Field | Exact meaning |
|---|---|
| `$schema` | Exact registered artifact-manifest schema identity |
| `contract_version` | Exact Reconstructed Consolidation Artifact contract version |
| `reconstructed_consolidation_artifact_id` | One register-issued `rca_` ID |
| `artifact_class` | Exact constant `RECONSTRUCTED_CONSOLIDATION` |
| `jurisdiction` | Exact constant `HK` |
| `material` | Exact constant `legislation` |
| `observation_cutoff` | Exact cutoff inherited from the Plan |
| `legal_item_ref` | Exact Legal Item reference inherited from the Plan |
| `reconstruction_plan_ref` | Exact `rpl_` ID and canonical Plan fingerprint |
| `base_official_version_ref` | Exact HKeL base Official Version reference |
| `base_evidence_class` | Exact `VERIFIED` or `ASSISTED` value from the Plan |
| `applicability_decision_ref` | Exact accepted branch decision |
| `coverage_gap_ref` | Exact active missing-consolidation Coverage Gap |
| `identity_lineage_decision_ref` | Accepted identity and continuity decision for all affected locations |
| `contracts` | Exact rulebook, registry, source-tree, renderer, alignment, identity, lineage, traceability, and artifact contracts |
| `files` | Complete sorted inventory of the ten non-manifest package files |
| `serving_requirements` | Exact closed object defined below |

The values inherited from the Plan must match byte-for-byte. The artifact
cannot substitute a newer cutoff, different branch, different base, different
evidence class, or wider location set after execution.

Each `files` entry contains exactly a registered role, normalized relative
path, media type, non-negative byte size, and SHA-256. Paths and roles are
unique, sorted by role then path, and match the fixed package boundary.

## Authentic-language trees and source units

`trees/en.json` and `trees/zh-Hant.json` contain the complete final canonical
source trees for the Plan's dependency closure. They preserve exact authentic
wording, punctuation, numbering, headings, nesting, order, tables, Forms,
Schedules, notes, cross-reference markers, and renderer-supported asset
relationships.

Each tree node has:

- one canonical tree-node ID unique inside the artifact;
- authentic language;
- registered Legal Item and Legal Location identity;
- structural type and parent ID;
- zero-based sibling order;
- owned source-unit IDs in exact order;
- child node IDs in exact order; and
- canonical node-content and subtree fingerprints.

Tree-node IDs are artifact-local structure identities, not Legal Location or
Search Record identities. The two language trees may have different shapes.
They must each cover their complete authentic-language source units exactly
once and connect through the Bilingual Alignment Map.

`source-units/en.jsonl` and `source-units/zh-Hant.jsonl` contain every final
authentic-language source unit exactly once in canonical tree order. Each row
binds its source-unit ID, tree node, Legal Location, exact unit kind, content or
asset reference, order, content fingerprint, and derivation-map entry.

No unit may contain generated translation, explanatory prose, warning text,
Plan instructions, engine diagnostics, or serving-only labels. Simplified
Chinese is not an authentic-language output.

## Reconstructed location units

`reconstructed-location-units.jsonl` is the sole final structured input to the
ordinary Hong Kong legislation renderer. It contains one row for each complete
Legal Location in the dependency closure, including governing context that the
renderer may need.

Every row binds:

- Legal Item and Legal Location references;
- applicability branch and operative-state decision;
- English and Traditional Chinese tree-node and source-unit IDs;
- Bilingual Alignment Group IDs;
- governing and dependent Legal Location references;
- source order and structural role;
- complete canonical location fingerprints for both languages; and
- whether the location is primary affected content, required governing
  context, dependent rebuilt content, or a proven independent boundary.

This file is not a Serving Record and contains no `metadata` object, Search
Record ID, embedding, source display, authority note, Pinecone field, or final
partition. The ordinary renderer and partitioner consume it under ADRs 0021,
0040, 0050, and 0078.

## Bilingual alignment and coverage proofs

`bilingual-alignment-map.json` uses the ordinary Hong Kong Bilingual Alignment
Map contract. Every final English and Traditional Chinese source unit belongs
to exactly one alignment group. One-to-one, one-to-many, many-to-one, and many-
to-many groups remain valid when official identities and structure prove them.
Translation similarity cannot create or repair a group.

`dependency-closure-proof.json` proves that every primary, governing,
dependent, and independent-boundary location equals the Plan closure and that
no affected dependency was omitted or double-owned.

`source-unit-coverage-proof.json` proves separately for each language that:

- the final source-unit inventory is complete and duplicate-free;
- every final unit occurs exactly once as primary tree content;
- repeated serving dependencies later point to their primary units;
- every Plan-declared unchanged base unit is preserved byte-exactly;
- every inserted or changed unit is owned by one admitted operation; and
- every deleted base unit is absent and accounted for in the Report.

A complete tree with an incomplete proof is invalid. Reproducibility can
reproduce an omission.

## Derivation map

`derivation-map.json` accounts for every final source unit using exactly one
primary derivation class:

| Derivation class | Required proof |
|---|---|
| `UNCHANGED_BASE_UNIT` | Exact base source-unit reference and byte-identical content fingerprint |
| `OPERATION_RESULT_UNIT` | Exact `rop_` operation instance, amendment source-unit references, before-state reference where applicable, and final content fingerprint |

Structural nodes, orders, labels, references, and asset relationships altered
by an operation also bind that operation. There is no `GENERATED`, `INFERRED`,
`CORRECTED_BY_ENGINE`, `TRANSLATED`, `MANUAL`, or catch-all derivation class.

One operation may produce several final units, and one final unit may cite
several exact amendment source units, but each final unit has one primary
derivation entry and no conflicting ownership. Unchanged content that moved or
was renumbered still binds the responsible operation for the structural change
while preserving its unchanged content source.

Every final content and structure fingerprint must be reachable through the
derivation map. An unaccounted byte or structural relation invalidates the
complete atomic artifact.

## Identity and lineage result

`identity-lineage-result.json` binds the accepted Legal Item, Legal Location,
and source-unit continuity consequences. It records:

- locations and source units that retain identity;
- new locations created by insertion, split, or replacement;
- ended locations removed by repeal, merge, or replacement;
- explicit renumber, move, split, merge, replacement, and predecessor links;
- the evidence and Legal Desk decision for every non-trivial continuity result;
- acyclic lineage validation; and
- complete reconciliation with the Plan's location inventory.

Visible numbering, identical text, or operation position cannot allocate or
merge identity. The Management Register issues all domain IDs under ADR 0011.
The artifact records the accepted result and never calculates identity from
content.

## Serving requirements

`serving_requirements` contains exactly:

- `serving_mode: "RECONSTRUCTED_CONSOLIDATION"`;
- the exact ADR 0080 authority-note template contract reference;
- `ordinary_legislation_renderer_required: true`;
- `ordinary_legislation_partitioning_required: true`;
- `separate_material_type_forbidden: true`;
- `separate_index_or_namespace_forbidden: true`; and
- `traceability_lookup_required: true`.

The artifact does not contain a rendered authority note because that note is a
Serving Record consequence filled from proved cutoff, base-version, source,
effect, and applicability facts. Record rendering must reproduce the accepted
template exactly; it cannot paraphrase the warning or add artifact internals.

## Validation and later HKeL reconciliation

The artifact passes only when:

1. the Plan reference and all inherited facts match exactly;
2. all declared files exist, validate, remain contained, and match hashes;
3. both trees and source-unit inventories are complete and internally exact;
4. the reconstructed location units equal the tree and Plan closure;
5. bilingual alignment, dependency closure, and source-unit coverage are
   complete;
6. every final byte and structural relation has one permitted derivation;
7. identity and lineage are accepted, complete, and acyclic;
8. the ordinary renderer can consume the package without source repair;
9. the Execution Report independently produces and references this exact
   package; and
10. two clean builds produce byte-identical package files, inventory, and root
    fingerprint.

When HKeL later publishes the applicable consolidation, comparison uses the
same canonical tree, legal-content, presentation-projection, location,
bilingual, and coverage contracts. Exact legal-content agreement supports
ordinary HKeL replacement. A material mismatch preserves this artifact and all
evidence, selects the valid HKeL result, and applies ADR 0083's attributed
monitoring and suspension result. The artifact is never mutated to resemble
later HKeL.

## Authorization and next topic

This contract completes the internal reconstruction artifact chain at the
design level. The next topic is later-HKeL reconciliation and reconstruction
monitoring: exact match classes, mismatch attribution, suspension scope, and
safe restart.

This ADR authorizes documentation only. It does not create schema or fixture
files, implement the package, access sources, call a model or embedding
provider, render records, publish a release, mutate Pinecone or Azure, promote,
deploy, commit, push, or perform another remote action.
