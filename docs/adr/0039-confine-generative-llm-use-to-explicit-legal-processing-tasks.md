---
status: accepted
date: 2026-08-12
amended_by:
  - 0043
  - 0053
  - "0065"
  - "0076"
refines:
  - 0001
  - 0014
  - 0018
  - 0031
depends_on:
  - 0013
  - 0016
---

# Confine generative LLM use to explicit legal-processing tasks

No application in the pipeline is generally “powered by AI”. Generative large
language model use is confined to an explicit task runner inside the legal-
processing worker. Every other application and every other part of legal
processing is non-LLM unless a later accepted decision names a new task.

This distinction matters because several different things are sometimes called
AI:

- a **generative LLM** reads preserved legal text and proposes structured legal
  analysis;
- an **embedding model** converts final validated `metadata.text` into vectors;
  it does not draft or decide legal content; and
- the **Ask.Legal downstream LLM** writes the user's answer after retrieval; it
  is outside this database-pipeline repository and receives only the six served
  metadata fields.

This decision governs only the first category while marking all three clearly
in the overall design.

## Exact LLM runtime boundary

The only pipeline component permitted to hold generative-LLM provider
credentials or make generative-LLM network calls is:

**Legal-processing worker → LLM task runner**

The task runner is an infrastructure boundary, not legal authority. It accepts
only a versioned task contract, the exact preserved evidence selected for that
task, and non-secret pinned settings. It returns a schema-valid proposal and
records the exact model, prompt, schema, settings, source fingerprints, and
result fingerprints.

At the time of this decision, the named target-design task candidates were:

1. **`case-proposition-extraction`** — proposes self-contained Case
   Propositions, material facts, issue, answer, qualifications, application,
   result, opinion attribution, and exact supporting judgment passages from one
   preserved official judgment; and
2. **`later-treatment-proposal`** — detects candidate citations and proposes
   how a later judgment may treat an exact earlier Case Proposition, together
   with exact supporting passages and scope.

At the time of this decision, no Hong Kong legislation task was named to call a generative LLM. HKeL parsing,
XML/PDF reconciliation, status mapping, bilingual alignment, rendering,
identity, disposition, record construction, authority-note selection, and release
accounting are deterministic or Legal Desk decisions under the accepted
rulebook and fixtures.

No Principles task currently calls a generative LLM. Publisher paragraphs
remain source-faithful and are parsed, versioned, compared, and validated under
their publisher-evidence rules. A future Principles LLM transformation would
require a separate accepted task and cannot be inferred from the word
“distillation”.

## Exact non-LLM boundaries

The following components make no generative-LLM calls:

| Component | Why it is non-LLM |
|---|---|
| Control plane | Scheduling, state transitions, source registry, coordination, completeness, and reports are deterministic workflow operations |
| Review application | It presents preserved evidence and proposals to authorized humans; it does not generate the approval decision |
| Acquisition worker | Watchers, scrapers, hashes, inventories, and immutable capture preserve source facts without legal generation |
| Source connectors | They retrieve and parse source-specific transport formats; source text cannot become a prompt instruction |
| Legal Desk rule modules | They apply versioned written rules and record responsible legal decisions; they may consume an LLM proposal but do not delegate authority to it |
| Deterministic legal-processing modules | Schema validation, parsing, normalization, XML/PDF reconciliation, bilingual alignment, status maps, renderers, identity checks, authority notes, and record validation use accepted contracts and fixtures |
| Corpus construction | Releases, desired-state composition, coverage accounting, lineage, and manifest inputs are exact artifact operations |
| Promotion worker except embeddings | Backup checks, target construction, verification, cutover, rollback, and exact retirement execute only an approved manifest |
| Reporting and observability | They render and monitor preserved facts rather than generating new legal conclusions |

The promotion worker's embedding adapter is explicitly marked **model-powered,
not generative-LLM-powered**. It receives only validated selected
`metadata.text` under a pinned embedding contract. An embedding result cannot
change a record, authority note, legal status, or approval.

The Ask.Legal downstream answer LLM is explicitly marked **external to this
pipeline**. The pipeline proves that every live query path passes
`metadata.text` and `metadata.authority_note` correctly, but it does not host or
control the answer-generation module here.

## LLM output is a proposal, not a decision

An enabled LLM task cannot establish or change:

- source authenticity, completeness, identity, version, or legal status;
- Legal Item, Official Version, Legal Location, or Search Record identity;
- court hierarchy, opinion identity, current authority, or whether treatment
  legally overrules a proposition;
- an authority-note clause, retirement, reinstatement, or release disposition;
- a Corpus Release, Desired-State Inventory, Promotion Manifest, Approval, or
  Serving State; or
- any Pinecone, backup, deployment, or routing action.

Those results require deterministic evidence checks, the applicable Source
Rulebook and Legal Desk decision, validation, and where required human review
and one frozen Approval.

Each LLM proposal must cite exact preserved passages. Missing support,
unsupported claims, mixed opinions, incomplete output, or failed evaluation
places the proposal in Quarantine. The pipeline does not ask another LLM call
to improvise an unsupported repair.

## Adding a future LLM task

A generic “evidence-bound AI” hook does not authorize a new task. A future LLM
task remains disabled until an accepted Source Rulebook or ADR defines:

- one stable task ID and owning jurisdiction-and-material Legal Desk;
- exact permitted evidence and forbidden inputs;
- schema, prompt contract, model settings, tools, and network boundary;
- the claims the output may propose and decisions it may never make;
- deterministic preconditions and post-validation;
- exact supporting-evidence requirements;
- evaluation corpus, acceptance thresholds, sampling, and revalidation;
- human or Legal Desk review requirements; and
- result reuse, invalidation, retention, cost, and failure behavior.

Only the LLM task runner may then execute the accepted contract. Other modules
cannot call a model provider directly.

## Consequences

The design now shows exact generative-LLM, embedding-model, deterministic, and
external-answer-model boundaries. “AI” is not used as an unexplained property
of the control plane, acquisition, Hong Kong legislation processing, corpus
construction, review, or promotion.

This decision authorizes documentation only. It does not authorize
implementation, source access, LLM or embedding-provider calls, release
publication, Pinecone mutation, promotion, or deployment.

ADR 0043 later deferred the final deterministic-versus-LLM allocation. The sole
gateway, proposal-only role, forbidden decisions, and task-admission contract
above remain accepted. It made the two named case tasks and the absence of a
Hong Kong Legislation task provisional rather than an implementation-ready
final inventory.

ADR 0053 later accepts the staged hybrid allocation for Hong Kong Cases later-
treatment screening. ADR 0065 later accepts separate proposition-analysis and
proposition-challenge model stages within the staged Hong Kong Case Proposition
extraction workflow. All model stages remain proposal-only and disabled until
their complete runtime task contracts pass the admission requirements above.
Gazette-event extraction and every other unallocated candidate remain deferred.

ADR 0076 later settles Hong Kong Regulatory Materials as four change-gated
two-pass proposal tasks: update analysis and challenge, and record analysis and
challenge. Exact source, validation, Legal Desk authority, rendering, coverage,
identity, release, and operational controls remain deterministic.
