---
status: accepted
date: 2026-08-13
amended_by:
  - 0056
  - 0058
amends:
  - 0011
  - 0013
  - 0014
  - 0020
  - 0050
  - 0052
depends_on:
  - 0003
  - 0004
  - 0006
  - 0007
  - 0053
---

# Use immutable selection transitions for Hong Kong case treatment

Later treatment changes either the information delivered with a still-current
Case Proposition or whether that proposition remains selected as current
authority. These are different consequences and must not both be described as
retirement.

Search Records remain immutable. The pipeline never edits a record in place and
never patches the live Pinecone Index. Each frozen Hong Kong Cases update
records the complete treatment decision and then makes one of three selection
choices for the next Desired-State Inventory:

1. reuse the currently selected exact Search Record;
2. select a different exact Search Record; or
3. select no record for a proposition that is no longer eligible for ordinary
   current-authority serving.

## Separate record lineage from selection history

Search Record lineage explains how newly issued immutable records relate to
earlier records. It is forward-only and acyclic. Serving selection history
records which existing Search Record each approved Serving State selected.

A later state may therefore reselect an older exact record. That choice creates
a new append-only serving-selection or reinstatement event referencing the new
cutoff, the previously selected record, the reselected record, evidence, Legal
Desk decision, and Rule Trace. It does not create a backward Search Record
lineage edge and does not mutate either record.

## Exact transition map

| Accepted current result | Search Record result | Embedding result | Serving result |
|---|---|---|---|
| Internal treatment changes but the exact six-field payload does not | Reuse the same Search Record ID | Reuse | Record set remains exact; affected treatment and release accounting may still change |
| `authority_note` changes to a payload never issued before | Create a successor Search Record with forward authority-note-revision lineage | Reuse the cached embedding when `metadata.text` and the embedding contract are exact; otherwise generate it under the approved contract | Select the successor in the next inventory |
| Equivalent treatment is consolidated and the rendered note remains byte-exact | Reuse the same Search Record ID | Reuse | No Pinecone record change; preserve every relationship internally |
| A former exact six-field payload becomes legally supported again | Reselect the preserved Search Record ID | Reuse the exact cached embedding when available under the approved cache policy and contract | Record a new selection or reinstatement event; create no backward lineage |
| The required restored payload has never existed | Create a forward successor from the currently selected record | Reuse or generate according to exact text equality and the embedding contract | Select the successor |
| Proposition is expressly and conclusively overruled in full | Create no successor merely to display a warning | Do not include a vector for it in the new target | Omit the proposition from the next current inventory; preserve prior records and history outside current Pinecone |
| A combined proposition is partly overruled | End selection of the combined record; create or reuse only independently supported narrower records | Generate embeddings for changed text; reuse only for exact text under the same contract | Select only proved unaffected propositions |
| Treatment effect or affected proposition remains uncertain | Make no guessed record transition | Make no treatment-driven embedding decision | Apply Quarantine, carry-forward, withholding, or no-new-target rules under ADR 0005 |

Exact equality means all six serialized serving fields are identical, not merely
semantically similar. A citation, alias, evidence pointer, or internal treatment
relationship that changes no serving field updates the Management Register,
Evidence Vault, Record Traceability Lookup, or Corpus Release as applicable but
does not create Pinecone record churn.

## Replacement, retirement, and Quarantine

**Payload replacement** means the proposition remains current but its exact
LLM-facing record changed. The next inventory selects another immutable record.
The prior record remains preserved.

**Legal retirement** means the proposition itself no longer qualifies as
current authority. The next inventory selects no successor for that exact
proposition. Retirement is exclusion, not deletion.

**Quarantine or withholding** means the system cannot yet support a current
selection decision. It does not itself prove that the proposition is wrong,
overruled, or reinstated. A generic authority note cannot cure unknown scope or
missing judgment evidence.

## Partial overruling

When one Search Record combines affected and unaffected propositions, the
combined record cannot remain in current serving. A narrower successor or
previous record may be selected only when the earlier judgment itself supports
that narrower proposition as a standalone proposition. The pipeline must not
rewrite the earlier court's reasoning merely to retain a vector. If no honest
standalone proposition exists, no narrower successor is created. Unclear scope
is quarantined.

## Promotion boundary

Every serving transition remains part of a complete frozen Corpus Release,
Desired-State Inventory, Promotion Manifest, human Approval, replacement
Pinecone Index build, verification, and routing switch. Automatic acceptance of
a clear ordinary Legal Desk treatment result under ADR 0053 does not bypass the
separate human Approval for the complete promotion package.

## Required conformance examples

ADR 0056 places these examples in the deterministic contract suite and requires
exact expected artifacts. Separate semantic evaluations test whether the LLM
finds the treatment; they do not prove the transition result.

- a bare citation adds internal evidence but reuses the same Search Record;
- a material following changes `"None"` to a support note, creates a successor,
  and reuses the text embedding;
- repetitive following leaves the consolidated note byte-exact and creates no
  Search Record churn;
- a changed warning reference creates a successor even when the proposition
  text is unchanged;
- a traceability-only evidence-pointer correction reuses the record;
- full overruling omits the exact proposition with no warning-only successor;
- partial overruling creates only earlier-judgment-supported narrower records;
- clear reinstatement reselects an exact prior record through a new selection
  event without cyclic lineage;
- reinstatement requiring a new support note creates a forward successor; and
- uncertain scope produces no guessed replacement, retirement, or
  reinstatement.

## Consequences

The Management Register needs separate append-only schemas for Search Record
lineage and Serving State selection or reinstatement events. Corpus construction
must detect exact previously issued payloads before allocating an ID. Reports
and Promotion Manifests must distinguish reused, newly issued, reselected,
replaced, withheld, retired, split, and reinstated records. Embedding reuse
remains conditional on exact text, the pinned embedding contract, and the
approved cache and retention policy; this ADR does not itself establish an
indefinite cache-retention promise.
