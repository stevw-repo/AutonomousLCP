---
status: accepted
date: 2026-08-10
amended_by:
  - "0079"
  - "0080"
refined_by:
  - "0087"
---

# Handle unavailable Release Scopes explicitly

When source failure or Quarantine prevents a required Release Scope from
producing a fully current Corpus Release, the responsible Legal Desk must make
one of three explicit evidence-backed serving decisions.

## Carry forward

The Desired-State Inventory may select the last approved Corpus Release when
there is no affirmative evidence that its records changed and the Legal Desk
supports continued serving. The selection records the failed or quarantined
observation, the release's last-verified date, a visible Coverage Gap and
warning, and a review deadline. The records are identified as last-approved
and carried forward, not verified current at the new cutoff.

ADRs 0079 and 0080 define the separate result when official evidence proves
that legislation changed but updated official consolidated text is not yet
available. ADR 0080 first permits a fully proved `RECONSTRUCTED_CONSOLIDATION`.
If exact reconstruction is unavailable, every affected location for which
valid latest applicable official source text is held remains searchable as
`KNOWN_STALE_ANALYTICAL_CARRY_FORWARD` under ADR 0079. Both paths require their
mandatory warning, Coverage Gap, exact serving-payload identity, and complete
release accounting; neither may be silent.

## Withhold

When available evidence indicates that existing Search Records may now be
materially misleading and neither ADR 0080 reconstruction nor ADR 0079's exact
known-stale fallback applies, the Legal Desk creates a new complete Withholding Release. The
release omits the affected records from its searchable set but accounts for
every withheld Legal Item or prior Search Record, the reason, and the exact
supporting evidence. The corresponding serving removals require Approval in
the complete Promotion Manifest. Withholding does not declare that the Legal
Item ceased to exist and does not destroy its previous records.

A Withholding Release may contain zero Search Records only when its complete
accounting covers every item in the Release Scope. A bare empty release cannot
stand for a source failure, incomplete reconciliation, or unresolved
Quarantine.

## Do not rebuild the jurisdiction

If the Legal Desk cannot support either continued serving or withholding, the
coordinator produces no new Desired-State Inventory or Pinecone Index for that
jurisdiction. The routing configuration retains its previous verified target
and publishes the Coverage Gap. Other jurisdictions may proceed in the complete
routing generation, but otherwise-clear changes within the blocked jurisdiction
wait until a safe complete target can be built.

## Considered options

- silently reuse the last approved release — rejected because users and
  operators would mistake stale or unchecked material for verified current law;
- always retain the previous release — rejected because most affirmative
  evidence may make continued serving materially misleading; ADRs 0079 and
  0080 permit only their exact, explicitly warned legislation-consolidation
  paths;
- automatically remove uncertain records — rejected because uncertainty is not
  proof of legal retirement and removals require evidence and Approval; and
- block every jurisdiction whenever one scope fails — rejected because a
  jurisdiction with a valid complete target need not wait for an unrelated
  jurisdiction.

## Consequences

Every unavailable-scope decision needs a reason, evidence, author, timestamp,
last-verified date, Coverage Gap, review deadline, and audit history. Source and
material rulebooks must define when ordinary carry-forward, ADR 0079's known-
stale analytical carry-forward, withholding, or no rebuild applies. Coverage
status must remain visible until a later complete release resolves the gap.
