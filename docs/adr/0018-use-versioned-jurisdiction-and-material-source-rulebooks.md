---
status: accepted
date: 2026-08-11
refined_by:
  - "0087"
depends_on:
  - 0005
  - 0011
  - 0012
  - 0014
  - 0015
  - 0017
---

# Use versioned jurisdiction-and-material source rulebooks

The pipeline uses one common **Source Rulebook Contract** but a separate
versioned source rulebook for every jurisdiction-and-material pair. Examples
include Australian Legislation, Australian Cases, Australian Principles,
Singapore Legislation, Singapore Cases, and Singapore Principles. There is no
single rulebook that can establish source completeness or legal status across
jurisdictions, and there is no cross-jurisdiction Principles rulebook.

A source rulebook is the written decision manual that tells a responsible Legal
Desk what preserved source evidence means and which outcomes are permitted. It
does not contain credentials, perform source retrieval, approve a Promotion
Manifest, or authorize a production change.

The boundaries are:

- the **Source Register** records the approved source, its stable source ID,
  intended uses, owner, freshness and checking expectations, and technical
  locator or connector configuration;
- the **source connector** checks and captures source facts without deciding
  their legal meaning; and
- the **source rulebook** references stable Registered Source IDs and states
  the evidence and decision rules that the Legal Desk applies.

An unregistered discovery source may trigger investigation, but it cannot by
itself support a serving change.

## Common Source Rulebook Contract

Every jurisdiction-and-material rulebook must contain:

1. **identity and ownership** — jurisdiction, material family, responsible
   Legal Desk, owned Release Scopes, rulebook ID, version, fingerprint, and
   effective observation cutoff;
2. **coverage promise** — the exact legal materials, authorities, titles,
   courts, instruments, status events, exclusions, and time boundaries for
   which the desk claims complete accounting;
3. **Registered Sources and roles** — the stable source IDs allowed to prove
   identity, text, legal status, corrections, replacements, later treatment,
   publisher updates, currency, or discovery;
4. **checking and reconciliation** — Watcher checks, full-inventory
   reconciliation, freshness limits, bounded retries, disappearance checks,
   and the conditions required for a supported no-change result;
5. **required Source Snapshots** — the complete documents, inventories,
   attachments, schedules, notices, histories, metadata, and fingerprints that
   must be preserved before a decision;
6. **recognized events** — the source and legal events the rulebook can
   classify, using the applicable legislation, case-law, or Principles
   continuity policy;
7. **event evidence and source priority** — the evidence required for each
   event, which source controls each fact, explicit priority or replacement
   rules, and conflict handling;
8. **identity and continuity evidence** — what can prove that an observed
   object is the same, new, corrected, renumbered, replaced, split, merged,
   reinstated, transferred, withdrawn, or otherwise related to an existing
   identity;
9. **permitted outcomes** — the exact conditions for record creation, reuse,
   replacement, authority-note, carry-forward, withholding, retirement, Waiting Room,
   Frozen Principles Scope, Quarantine, or no jurisdiction rebuild;
10. **failure and uncertainty behavior** — the result of missing, stale,
    incomplete, conflicting, unmatched, or unsupported evidence; and
11. **examples and tests** — passing, failing, boundary, conflict, and
    regression examples that exercise the same stable rule IDs as the
    executable rules.

The common contract standardizes the questions each rulebook must answer. It
does not standardize the answers across jurisdictions. For example, Australian
and Singapore legislation rulebooks may both recognize commencement but rely
on different official sources and exact evidence. Australian Principles and
Singapore Principles may share the publisher-continuity model in ADR 0015 but
must separately establish their source coverage, paragraph identifiers,
publisher updates, currency signals, and completeness.

## Rule decisions and fail-closed behavior

Every material rule has a stable rule ID, plain-language explanation, required
inputs, accepted source roles, permitted outcome, review requirement, and
examples. Every Legal Desk decision records:

- the rulebook ID, version, and fingerprint;
- the exact rule ID;
- the Observation and Source Snapshot evidence used;
- the facts established and any unresolved facts;
- the identity and serving outcomes; and
- the responsible desk and any required human review.

If no rule matches, required evidence is missing, complete reconciliation
fails, or a source conflict remains unresolved, the pipeline cannot silently
record “no change” or invent an outcome. It preserves the evidence and uses
Quarantine or the accepted unavailable-scope process in ADR 0005. A missing
page is not proof of repeal or withdrawal.

The human-readable explanation, machine-readable rule, and automated examples
or tests use the same rule IDs. Software executes named rules; it does not
create new legal policy from source text, similarity, AI output, or convenient
defaults.

## Versioning and historical decisions

Rulebooks are immutable once used. A change creates a new version and
fingerprint with an explicit effective observation cutoff. Existing decisions
remain bound to the version that produced them and are never silently
reinterpreted.

Every new rulebook version includes an impact declaration stating whether
existing Legal Items, decisions, authority notes, quarantines, releases, or serving
records require re-evaluation. Required re-evaluation creates new evidence-
backed decisions and ordinary immutable lineage; it does not rewrite the old
decision or authorize production by itself.

## Consequences

The Management Register needs immutable rulebook versions, stable rule IDs,
source-role bindings, effective cutoffs, decision records, and impact
declarations. Contract validation must prove that every concrete rulebook
answers the common required sections and that every decision cites a valid rule
and sufficient evidence.

The shared template is now settled. The exact Registered Sources, coverage
promises, evidence rules, source priorities, checking frequencies, and event
rules must still be populated separately for each jurisdiction-and-material
pair before that scope is implementation-ready.

Source-specific rights and compliance controls remain deferred to the legal
team under the accepted assumption that every Registered Source and intended
use is legally compliant.
