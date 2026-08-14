---
status: accepted
date: 2026-08-12
refined_by:
  - "0080"
  - "0082"
  - "0083"
  - "0084"
  - "0085"
  - "0087"
refines:
  - 0018
  - 0021
  - 0022
  - 0028
  - 0033
  - 0034
  - 0035
  - 0036
  - 0037
  - 0038
  - 0040
depends_on:
  - 0011
  - 0013
  - 0016
---

# Use strict hashed HKeL fixture packages

Every executable HKeL reconciliation fixture is one immutable, self-contained,
synthetic package. A strict JSON manifest describes the scenario and points to
separately stored, hashed input and expected artifacts. A frozen catalogue
indexes every required package and proves that the complete accepted fixture
universe is present.

The manifest does not embed escaped XML, PDF bytes, or long bilingual expected
records. Those remain ordinary files so humans can inspect them, native format
validators can read them, and their exact bytes can be compared independently.

This contract is language-independent. A future implementation in Python,
TypeScript, or another language must consume and produce the same artifacts and
pass the same checks. It is a test contract, not a second Pinecone serving
schema and not a production source snapshot.

## Package shape

The logical package is:

```text
fixtures/
├── catalogue.json
└── <fixture-group>/
    └── <stable-fixture-id>/
        ├── fixture.json
        ├── input/
        │   └── <small synthetic evidence artifacts>
        └── expected/
            └── <exact expected artifacts>
```

The exact repository path may be selected with the implementation layout, but
the package boundary, filenames `catalogue.json` and `fixture.json`, input and
expected separation, and manifest semantics are fixed.

All paths inside a package are normalized relative POSIX paths. Absolute paths,
`..`, empty segments, platform-specific separators, URI retrieval, and
symlinks are forbidden. A fixture may read only its declared files and pinned
contracts. It may not reach the network, production stores, credentials, or an
undeclared local artifact.

Small synthetic XML, text, JSON, images, and PDFs required for tests may live
in Git under the repository's test-fixture rule. Real source snapshots and
full legal corpora remain outside Git.

## Frozen catalogue

`catalogue.json` is strict Draft 2020-12 JSON. It requires:

- its schema identity and fixture-contract version;
- `status: "frozen"`;
- the Hong Kong Legislation profile identity;
- the exact Source Rulebook, source-interpretation, renderer, serving-schema,
  identity, traceability, and other common contract identities and
  fingerprints required by the indexed packages;
- every required conceptual fixture group, its stable fixture-ID range, and
  expected count;
- one relative `fixture.json` path and SHA-256 hash for every fixture;
- a fingerprint of the complete normalized catalogue inventory; and
- no duplicate ID, path, package fingerprint, or unaccounted fixture.

The initial accepted catalogue contains all eighty-nine conceptual fixtures:

| Group | Stable IDs | Count |
|---|---|---:|
| Ordinary provisions | `HKLEG-RECON-ORD-FIX-001`–`012` | 12 |
| Schedules, tables, and forms | `HKLEG-RECON-STF-FIX-001`–`016` | 16 |
| Notes, images, and cross-references | `HKLEG-RECON-NIR-FIX-001`–`018` | 18 |
| Partial status and bilingual structure | `HKLEG-RECON-PSB-FIX-001`–`021` | 21 |
| Overlong-record partitioning | `HKLEG-RECON-ORP-FIX-001`–`022` | 22 |

An optional discovery tag may help select tests, but a broad label such as
`table` or `over-limit` never substitutes for an exact fixture ID, input,
expected artifact, or assertion.

## Strict fixture manifest

`fixture.json` is strict Draft 2020-12 JSON with
`additionalProperties: false`. It contains these required sections:

| Section | Required meaning |
|---|---|
| `$schema` | Exact fixture-manifest schema identity |
| `contract_version` | Version of this machine-readable package contract |
| `fixture_id` | One accepted stable fixture ID matching its catalogue entry and directory |
| `title` and `purpose` | Short human-readable description without changing normative assertions |
| `group` | One of the five accepted HKeL conceptual groups |
| `status` and `synthetic` | Exactly `"frozen"` and `true` |
| `profile` | Jurisdiction `HK`, material `legislation`, and HKeL source family |
| `contracts` | Exact IDs, versions, and fingerprints of every contract needed to interpret or execute the fixture |
| `observation_context` | Synthetic cutoff, Legal Item, Official Version, Legal Locations, and any prior approved state needed by the scenario |
| `inputs` | Declared evidence expectations and exact input artifacts |
| `assertion_scope` | Pipeline checkpoints whose behavior this fixture asserts |
| `expected` | Exact result classes and separately hashed expected artifacts |

Unknown manifest properties, enums, contract references, evidence roles,
languages, assertion scopes, and expected-artifact roles fail structural or
semantic validation. They are not ignored for forward compatibility.

## Inputs and deliberate absence

Each input artifact declaration contains:

- a package-local artifact ID;
- Registered Source ID and exact evidence role;
- language: `en`, `zh-Hant`, `bilingual`, or `not-applicable`;
- normalized relative path;
- media type;
- lowercase 64-character SHA-256; and
- the exact source-unit or scenario identities it supplies when applicable.

The manifest separately declares every evidence slot required by the scenario.
Each slot has exactly one expected state:

- `AVAILABLE` — named declared artifacts must exist and hash correctly;
- `INTENTIONALLY_ABSENT` — the missing-evidence condition is part of the test;
  or
- `UNREADABLE` — a named declared artifact supplies the exact corrupt or
  unreadable bytes expected by the test.

Conflicting, stale, differently versioned, or semantically incomplete evidence
uses available artifacts whose declared facts create that condition. It is not
represented by a vague `CONFLICTING` file state.

This separation distinguishes a fixture intentionally testing missing evidence
from an incomplete package in which a maintainer accidentally forgot a file.

## Assertion scopes and result classes

A fixture names every checkpoint it asserts, such as evidence completeness,
XML/PDF reconciliation, presentation projection, bilingual alignment, legal-
status mapping, record construction, overlong partitioning, traceability,
identity and lineage, or release consequence. An assertion outside the named
scope is not silently inferred.

The expected result keeps separate concepts in separate required fields:

- `processing_outcome`: `PASS`, `BLOCK`, or `QUARANTINE`;
- `legal_disposition`: one stable disposition permitted by the exact Source
  Rulebook version, or `NOT_APPLICABLE` at a checkpoint that does not decide
  disposition;
- `coverage_effect`: `NONE` or one or more exact Coverage Gap expectations;
- `source_contract_review_required`: boolean;
- `reason_codes`: an ordered nonempty list for every non-pass or special
  consequence;
- `rule_trace`: the exact ordered stable rule IDs expected to apply; and
- `record_output`: exactly `EXACT` or `NONE`.

`PASS` never means searchable current law by itself. `WAITING_ROOM` and
`HISTORICAL` are dispositions, not processing failures. `COVERAGE_GAP` is a
coverage statement, not a record or legal disposition. Source Contract Review
is a required follow-up state, not a guess at source meaning.

When `record_output` is `EXACT`, the manifest declares the expected record
artifact and count. When it is `NONE`, the result must contain an explicit
zero-count and no-record assertion. A missing or empty output file cannot
accidentally satisfy the test.

## Separately hashed expected artifacts

Every expected artifact declaration has a stable role, normalized relative
path, media type, and SHA-256. Depending on assertion scope, roles include:

- exact candidate or serving records in JSONL;
- reconciliation report;
- presentation-projection report;
- Bilingual Alignment Map;
- Status Coverage Map;
- Primary Source-Unit Coverage Proof;
- Record Traceability Lookup entries;
- identity and lineage result;
- Coverage Gap result;
- Source Contract Review result; and
- complete fixture execution report.

The fixture manifest does not duplicate the content of these artifacts. The
expected files are the normative byte-level answer. Structured expected files
also validate against their own pinned schemas and semantic rules.

Serving-record JSONL uses the separately pinned Serving Record Contract. The
fixture package does not redefine its fields. Test-only register state supplies
synthetic register-issued IDs where identity is in scope; source paths,
locators, fixture IDs, and split ordinals never become production identity.

## Structural and semantic validation

JSON Schema validates document shape. It cannot, by itself, prove the legal and
cross-file relationships required here. A fixture is valid only when the
semantic validator additionally proves all applicable conditions:

1. the catalogue contains the complete accepted ID ranges and exact counts;
2. the catalogue path and hash match each fixture manifest;
3. every declared file exists, is a regular file, remains inside its package,
   and matches its hash;
4. no undeclared file affects execution or expected comparison;
5. evidence slots, Registered Source roles, languages, versions, and required
   artifacts satisfy the scenario exactly;
6. all referenced contracts, rules, reason codes, Legal Locations, source
   units, and expected-artifact roles exist in their pinned versions;
7. every named assertion scope has the mandatory expected artifact or explicit
   no-output assertion;
8. actual processing outcome, disposition, Coverage Gap, Source Contract Review
   state, reason codes, and ordered Rule Trace equal the expected result;
9. actual structured artifacts validate and equal their expected artifacts;
10. permitted record bytes, `metadata.text`, `authority_note`, token measurement,
    metadata-byte measurement, identity, and lineage equal the expected values;
11. bilingual mapping, Legal Location ownership, dependency closure, and
    primary source-unit coverage are complete and exact; and
12. two isolated clean executions produce byte-identical artifacts, inventory,
    and execution reports.

A schema-valid fixture or byte-identical rebuild that fails one semantic check
does not pass. Reproducibility can reproduce a defect.

## Fingerprints and immutability

SHA-256 is calculated over each artifact's exact bytes. JSON, JSONL, text,
line-ending, Unicode, and serialization requirements belong to the pinned
artifact-specific contracts; the fixture runner cannot reformat an artifact
before hashing or comparison.

The frozen package fingerprint binds the exact `fixture.json` bytes and the
ordered `(relative path, SHA-256)` inventory of every declared input and
expected artifact. The catalogue fingerprint binds its exact manifest bytes,
ordered fixture IDs, package paths, and package fingerprints.

Changing any input, expected result, authority note, record, mapping, rule reference,
contract fingerprint, or assertion creates a new package fingerprint. A
changed normative outcome requires the applicable ADR or Source Rulebook
change; silently replacing expected output to make a failing implementation
pass is forbidden.

## Boundaries and remaining work

The fixture package references rather than duplicates:

- pinned HKeL schemas and publication-interpretation contracts;
- the Hong Kong Legislation Source Rulebook;
- reconciliation, renderer, serving-record, authority-note, identity, lineage,
  traceability, coverage, and report contracts; and
- for overlong fixtures, the embedding tokenizer and token ceiling plus the
  serving serialization and metadata-byte ceiling.

The exact executable JSON Schemas, synthetic HKeL-shaped XML and PDF bytes,
expected JSON and JSONL artifacts, and validator implementation are later
implementation artifacts. They must instantiate this accepted design and the
eighty-nine accepted outcomes without changing them.

This decision authorizes documentation only. It does not authorize source
access, implementation, dependency installation, AI or embedding calls,
release publication, Pinecone mutation, promotion, or deployment.
