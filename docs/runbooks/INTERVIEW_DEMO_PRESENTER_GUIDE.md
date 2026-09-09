# AskLegal Offline Interview Demo — Presenter Guide

## What this demonstration proves

This is a **local synthetic offline proof of concept**. It demonstrates the
shape and controls of an autonomous legal-data pipeline without claiming that
the displayed case, ordinance, sources, or legal conclusions are real.

The prepared proof exercises a complete synthetic path: a scheduled source
change is detected, evidence is retained, legal records are constructed, a
frozen proposal is assembled for human review, a deterministic fake serving
target is activated, and the previous state is restored exactly after a
rollback. The browser adds a real, locally retained human APPROVE or REJECT
decision over the frozen proposal.

The browser decision and the completed pipeline proof are deliberately
adjacent but separate. The pipeline proof is prepared before the page opens so
the interview is reliable and fast. Clicking Approve records a real local
decision and queues the local-demo handoff; it does not pretend to rerun the
already completed proof or affect production.

No live Hong Kong publisher, cloud model, Pinecone index, deployment, or real
credential is contacted.

## Recommended two-minute walkthrough

1. Start with the banner: “This is deliberately a synthetic offline POC. I am
   demonstrating the workflow and control points, not claiming live legal-data
   coverage or production readiness.”
2. Point to **Pipeline status**. Explain that the first three stages are
   automated, human review is the governance boundary, and promotion cannot
   proceed without a decision.
3. Move to **Proposed legal changes**. Walk through the new Case B, its separate
   treatment update to Case A, and the legislation amendment. Emphasise the
   causal link between the first two cards and the effect of each on search.
4. Move to **Coverage checked**. Explain that the system reports both changed
   scopes and explicitly checked scopes with no change; silence is not treated
   as completeness.
5. Open **Evidence and complete change data** briefly. Explain that the readable
   cards are backed by record IDs and retained evidence references rather than
   presentation-only text.
6. Enter a decision note such as `Reviewed new Case B, its treatment of Case A,
   the amendment, effective date and scope coverage.` Then click **Approve all
   updates** or **Reject update**.
7. Point out that the decision applies to the exact frozen package. Any change
   to a record or its evidence requires a new review.

## Everything visible on the screen

### Header: “Review a proposed legal update”

This states the user task rather than the underlying technology. The reviewer
is not being asked to administer jobs or inspect infrastructure. They are being
asked to decide whether a prepared legal-data update may advance.

The subtitle reduces the review to four questions:

- What changed?
- Why does it matter to legal search?
- What evidence supports the proposed record?
- Should this exact frozen update be approved or rejected?

### “LOCAL SYNTHETIC OFFLINE POC” banner

This is the most important qualification on the page. It means:

- the cases, legislation, dates, and publisher labels are fictional fixtures;
- the application is running on localhost;
- no live Hong Kong source is queried;
- no model or embedding provider is called;
- no vector database is changed;
- no production AskLegal route or customer data is affected; and
- the interface proves mechanics and control boundaries, not legal accuracy,
  production scale, or jurisdictional completeness.

The fictional content is intentionally labelled inside each record as well as
in the page banner so it cannot easily be mistaken for a real legal update.

### Pipeline status

The five cards show the lifecycle of one proposed update.

1. **Change detected** — a scheduled synthetic source observation found data
   that differs from the previous accepted state.
2. **Evidence preserved** — the observed input was retained before downstream
   interpretation. This is the reproducibility boundary: later processing is
   tied to preserved input rather than a page that might change.
3. **Legal analysis** — the evidence was transformed into structured proposed
   search records and checked against the demo's legal-scope rules.
4. **Human review** — the proposal is frozen here. Automation prepares the
   recommendation, but a named decision remains mandatory.
5. **Local promotion** — before a decision this is blocked. Approval changes it
   to “Queued for local demo”; rejection stops it. This wording deliberately
   does not claim that production promotion occurred.

The key design point is that autonomy operates up to a visible governance
boundary. The pipeline can discover, preserve, analyse, compare, and propose;
it cannot silently turn a new interpretation into served legal data.

### Proposed legal changes: summary numbers

The page shows **3 proposed updates**: one addition and two replacements. Case B
is the addition. Case A's treatment note and the operative form of section 12
are replacements. That distinction matters:

- an addition introduces a new search record;
- a replacement supersedes the served form of a known record while preserving
  lineage to the prior form;
- a retirement removes a record from the proposed current serving set; and
- a withholding deliberately prevents uncertain material from entering the
  serving set.

This fixture has one addition, two replacements, and no retirements or
withholdings.

The second number shows **2 scopes checked — no change**. This is positive
coverage information. It tells the reviewer that those scopes were evaluated
and produced no proposed update; they were not silently skipped.

### New Case B card

The first legal card is the fictional new authority that caused the treatment
change. Demo Court of Appeal Case B becomes independently searchable. Its
fictional holding says that a public decision-maker must give intelligible
reasons that reveal its reasoning, while the content and timing of reasons for
urgent interim relief depend on context.

Case B has its own record ID, evidence reference, source, text, and authority
note. It is classified as **ADDED**, not hidden inside Case A's metadata. This
is the causal input that makes the next treatment update coherent.

Its search impact is twofold: researchers can find Case B directly, and the
system can use its observed relationship to update the authority context of
Case A. Case B's text describes its treatment of Case A; Case B's own authority
note correctly says that no later treatment of Case B exists in this fixture.

### Treatment of earlier Case A card

The next card propagates Case B's observed treatment back to the existing Case
A proposition. It says that the later Court of Appeal decision:

- **followed** an earlier case on the duty to give reasons; and
- **distinguished** that earlier case in the different context of urgent
  interim relief.

“Followed” means the later court applied or accepted the earlier proposition in
the relevant context. “Distinguished” means the court explained why a different
fact pattern or legal setting meant that the earlier result did not control
that part of the later dispute. One later judgment can do both for different
propositions or contexts.

This is a separate **UPDATED** record. The demo does **not** rewrite or erase the earlier judgment. The earlier
proposition remains searchable. The proposed replacement updates its authority
note so a researcher can see the later treatment. In a fuller system, treatment
is proposition-specific rather than a single crude label on an entire case.

The visible fields mean:

- **Updated search record** — Case A's authority-context record is a replacement in the desired serving
  state.
- **Narrative** — Case A's proposition plus a readable fictional explanation
  of Case B's followed and distinguished treatment.
- **Search impact** — the earlier proposition stays discoverable, with later
  treatment attached to its authority context.
- **Evidence basis** — a readable summary of why the record changes.
- **Source and scope** — the fictional Judiciary source family and the
  binding-court proposition scope.
- **Retained source reference** — the underlying synthetic evidence has a
  stable reference in the technical record. The compact card summarises it; it
  does not purport to quote a real judgment.

### Legislation amendment card

The fictional ordinance example shows a conventional current-law amendment:

- before amendment, section 12 required action within **14 days**;
- after amendment, it requires action within **21 days**; and
- the fictional effective date is **2026-08-01**, before the proposal's
  observation cutoff.

The effective date matters. An enacted but uncommenced amendment should not be
presented as ordinary current law. Here the fixture deliberately makes the
amendment operative before the cutoff, so current-law search should use the
21-day wording while the previous 14-day state remains in lineage/history.

The visible fields mean:

- **Updated search record** — the current served form changes; this is not a
  second duplicate section.
- **Narrative** — the before/after rule and fictional commencement date.
- **Search impact** — current-law search uses 21 days rather than 14 days.
- **Evidence basis** — the amendment relation and operative-date conclusion.
- **Source and scope** — the fictional e-Legislation source family and
  Ordinances scope.
- **Retained source reference** — the technical record identifies the
  synthetic source evidence behind the proposed replacement.

### Evidence and complete change data

This collapsed section exposes the canonical demo report rather than a second
presentation narrative. It contains the exact action classification, record
ID, material type, scope ID, source label, authority note, and evidence
reference for each change, along with the no-change scopes and counts.

It is useful when an interviewer asks how the attractive card maps back to
machine-readable state. The answer is: the card is rendered from the same
frozen change inventory and desired-state records; its counts and records are
not maintained separately by the UI.

The evidence basis on the card is a human-readable summary, not a quotation
from a real source. The full demo retains synthetic evidence references. A
production evidence viewer would additionally show the captured passage,
publisher metadata, capture time, and chain of custody subject to publisher
rights.

### Coverage and decision

The proposal heading identifies one frozen Hong Kong case-law-and-legislation
package and its observation cutoff. “Frozen” means that the decision is bound
to a specific immutable package. If records, evidence, settings, or the target
membership change, the old decision is not silently reused.

The two metrics mean:

- **Legal scopes checked** — how many declared scopes have an explicit
  disposition in this proposal.
- **Search records affected** — how many records are members of the proposed
  update: new Case B, updated Case A treatment, and updated section 12.

The coverage list currently shows:

- Binding-court case propositions — update included.
- Ordinances — update included.
- Constitutional and other instruments — checked, no change.
- Subsidiary legislation — checked, no change.

The distinction between “no change” and “not checked” is crucial. A trustworthy
pipeline must not make missing work look like a clean result.

### Evidence and technical package

This second collapsed section is the complete frozen proposal consumed by the
Review application. It contains audit-oriented fields that are hidden from the
main presentation: identifiers, fingerprints, exact member lists, scope
dispositions, evidence links, versions, and decision state.

The fingerprint is a content identity: change the package and its identity
changes. The Review API also supplies a version/ETag, and decision submission
uses that version. Together they prevent approving one screen while the server
quietly applies the decision to different bytes.

### Your decision

The decision note is required so the retained decision contains a short human
rationale rather than an unexplained button click.

- **Approve all updates** approves the complete frozen package, not individual
  cherry-picked fields.
- **Reject update** records rejection of that package and stops the local-demo
  promotion path.

The request carries an optimistic version and an idempotency key. In plain
language: it refuses a stale screen, and an accidental retry cannot create a
second different decision.

After submission the page reloads the authoritative retained decision. In demo
mode it reports, for example: “Approved locally by the demo reviewer. Reason:
… This does not affect production.” Internal actor, command, and approval IDs
remain available in technical state but are not shown in the presenter view.

The decision survives a page refresh and application restart because it is
stored in the local approval register. The buttons stay disabled once the
proposal is terminal.

## Likely interviewer questions

### Is this using real Hong Kong law?

No. The examples are intentionally fictional and visibly labelled. The demo
proves workflow, state transitions, evidence binding, and human governance.
Real-source legal accuracy and publisher rights require a separate admitted
run.

### Is AI deciding what the law is?

Not in this demonstration. The fixture is deterministic. The intended design
allows models only for bounded semantic tasks, requires strict structured
output tied to supplied evidence, rejects invented citations or malformed
responses, and still requires deterministic validation and human approval.

### Does “distinguished” mean the earlier case is no longer good law?

No. It means the later court treated the earlier authority as not controlling
in a particular context. The earlier proposition remains searchable, and the
treatment note supplies context. “Overruled,” “not followed,” and other
treatments would be separate evidence-bound propositions.

### Why not simply replace the text and forget the old version?

Legal research depends on time and provenance. The system proposes a new
current serving state while preserving the prior record, its evidence, and the
relationship between versions. That supports audit, rollback, and
point-in-time reasoning.

### How do you know the 21-day amendment is current?

The proposal evaluates both amendment content and operative date against its
observation cutoff. This synthetic amendment is effective before the cutoff.
An uncommenced amendment should be retained but excluded from ordinary
current-law search.

### What does “evidence preserved” really mean?

Downstream records refer to immutable captured evidence rather than only a live
URL. This POC uses synthetic local evidence. The production design adds source
metadata, integrity fingerprints, vault receipts, and access controls.

### Why retain “no change” scopes?

Because an empty output is ambiguous. It can mean no change, a source failure,
an unsupported scope, or skipped work. An explicit disposition prevents the
system from claiming complete coverage when work is missing.

### What happens if the evidence changes after approval?

The package identity changes and the approval no longer matches. A new frozen
proposal and a new human decision are required.

### Can the reviewer approve only one of the two updates?

Not in this POC. The approval is intentionally whole-package and exact. A
future product could support package splitting, but it must produce separately
frozen, independently auditable proposals rather than mutate an approved
package.

### What happens after approval here?

The decision is retained and the UI says the update is queued for the local
demo. Separately, the prepared E2E proof has already demonstrated deterministic
fake-target activation, rollback, and exact recovery. No production service is
changed.

### What happens after rejection?

The rejection and reason are retained, Review becomes terminal, and local
promotion is shown as stopped by the reviewer. A materially revised proposal
would require a new identity and review.

### Does the demo prove rollback?

Yes, within the offline synthetic boundary. E2E-001 reports
`GOLDEN_FLOW_RECOVERED`: the synthetic changed-source flow cut over to a fake
target, rolled back, and recovered the exact prior state. It does not prove a
live cloud or production rollback.

### Is Pinecone being called?

No. The POC uses deterministic local fakes and denies external network access.
Real Pinecone writes remain a separate explicitly authorized operation.

### Are credentials hidden behind the page?

The interview route uses a generated demo-only local token and connects
automatically. It is not a production credential. The generic Review
application still has its ordinary authentication surface.

### What would be needed for production?

At minimum: admitted publisher access and rights; real source observation;
measured model and retrieval evaluations; operational identities and secrets;
durable SQL, evidence, backup, and scheduler services; deployment and recovery
proof; monitoring; security review; and jurisdiction-specific legal quality
acceptance. None is implied by this POC.

### What is the strongest claim you can make?

“The repository contains an executable, deterministic, offline synthetic
pipeline that detects a prepared change, preserves evidence, constructs an
auditable legal-data proposal, requires a retained human decision, and proves
fake-target activation, rollback, and exact recovery.”

## Claims to avoid

Do not say that the demo:

- contains or updates real Hong Kong law;
- has validated legal accuracy;
- autonomously decides legal authority without review;
- called Azure OpenAI, Pinecone, or a live publisher;
- proves production security, scale, availability, or disaster recovery;
- obtained publisher permission; or
- deployed anything to AskLegal users.

## Running and resetting the demo

From the repository root:

```bash
./tools/run_interview_demo.sh
```

Open `http://127.0.0.1:8002/review`. Demo mode connects automatically. Press
Ctrl+C in the launcher terminal to stop it.

For a non-serving preparation check:

```bash
./tools/run_interview_demo.sh --prepare-only
```

The launcher resets only the marked demo directory under
`var/interview-demo`. It refuses to delete an unmarked directory.

The retained proof summary is in `var/interview-demo/demo-summary.json`; the
legal-change report is in `var/interview-demo/change-report.json`; and the
complete E2E result is in
`var/interview-demo/e2e-proof/E2E-001/result.json`. These are ignored local
runtime artifacts and must not be committed.
