# AskLegal Legal Database Pipeline — Decisions

Only settled decisions belong here. Recommendations and unresolved choices stay
in the design brief and `WORKING_STATE.md` until the user decides them.

## 2026-08-10 — Use this repository as the greenfield modular monorepo

`AskLegal-LegalDBPipeline` owns the complete rebuilt legal-database pipeline.
The code will live in one modular monorepo with separately runnable and
separately permissioned applications for control, human review, source
acquisition, legal processing, and production promotion. Repository colocation
does not merge their credentials, network access, approval powers, or
deployment identities. See
`docs/adr/0001-use-a-modular-monorepo.md`.

## 2026-08-10 — Existing repositories are reference material only

The older Distillation, Release Store, Pinecone, and coordinator implementations
do not define the target repository layout, schema, contracts, or internal
architecture. They may be inspected for lessons and verified behavior, but the
greenfield system does not depend on them automatically.

## 2026-08-10 — Keep substantial data and runtime state outside Git

Git contains code, schemas, prompts, small test fixtures, evaluation
definitions, infrastructure configuration, and documentation. Full legal
corpora, source snapshots, immutable releases, embedding caches, operational
reports, backups, credentials, and production state live in the appropriate
external stores. An ignored local `var/` tree may imitate those stores during
development.

## 2026-08-10 — The canonical brief is an initial overall-system design

`docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md` is the initial comprehensive
map of the intended complete system, not a final specification. It contains
settled decisions and unresolved system choices. Pilot scope, staged product
versions, rollout planning, migration sequence, estimates, and temporary
operating arrangements are excluded.

## 2026-08-07 — Watchers and scrapers are separate responsibilities

A Watcher performs lightweight scheduled checks and raises a possible-change
signal. A source-specific Scraper then captures the complete changed legal
content, required attachments, and metadata. The responsible Legal Desk decides
legal identity, status, and eligibility from that preserved evidence. A Watcher
alert alone can never become a Search Record.

## 2026-08-06 — Pinecone is a clean current serving copy

Pinecone serves the approved corpus used by Ask.Legal. It is not the permanent
archive and does not provide historical or “law as at date” search. Superseded
legislation and uncertain material remain recoverable outside Pinecone. A
negatively treated Case Proposition may remain searchable only with the
inseparable sourced treatment warning required by the case rules.

## 2026-08-06 — The human approves the complete frozen package

Every production addition, replacement, retirement, and exact-ID removal is
included in one complete frozen Promotion Manifest. The human approves or
rejects that package as a whole. Changing any included evidence, record, target,
configuration, recovery fact, or fingerprint requires a rebuilt package and
new Approval.

## 2026-08-06 — Prospective legislation stays outside search

Enacted or assented legislation that has not commenced is preserved in the
Waiting Room outside Pinecone. It enters a Promotion Manifest only after
official commencement is confirmed and an official updated consolidation is
available. The system does not splice amendment instructions into an old Act.
A commenced amendment without an updated official consolidation creates a
reported Coverage Gap.

## 2026-08-06 — Legislation is tracked from Act to Search Record

The Management Register tracks each Act, Official Version, Provision or stable
legal location, and derived Search Record. Every Search Record remains
traceable to that hierarchy.

## 2026-08-06 — Case search uses proposition records

Each distinct material Case Proposition becomes one self-contained
`type: "case"` Search Record containing the facts, issue, answer,
qualifications, application, result, opinion type, citation, and exact judgment
support needed to understand it. There is no duplicate case-overview vector and
no separate whole-case retrieval feature. A case with no material Case
Proposition creates no Pinecone record; uncertainty is quarantined.

## 2026-08-06 — Later case treatment is observed, not predicted

The system may identify later judgments and propose sourced treatment
classifications. It cannot predict that a Case Proposition will be overruled or
retire it because an AI model considers it weak. Treatment must identify exact
supporting passages, the affected proposition where possible, the court and
opinion relationship, and review state.

## 2026-08-06 — Case Propositions and Reference Principles stay separate

Case-derived propositions remain `case` Search Records. Halsbury and similar
reference-work paragraphs remain source-faithful `principle` Search Records.
The system does not blend or silently rewrite the two families.

## 2026-08-06 — Both provider-native and independent recovery are required

Pinecone-native backup and independent encrypted evidence and release backup
solve different failure modes. The intended system requires both, plus tested
restoration. A second folder on the same workstation is not an independent
backup.

## 2026-08-06 — Uncertainty is quarantined rather than guessed

Conflicting official evidence, incomplete source capture, unclear legal status,
and unsupported AI output are preserved in Quarantine. Unrelated clear work may
continue, but Quarantine remains visible in the report and coverage status.
