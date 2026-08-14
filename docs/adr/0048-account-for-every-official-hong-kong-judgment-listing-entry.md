---
status: accepted
date: 2026-08-12
refines:
  - 0046
depends_on:
  - 0005
  - 0014
  - 0018
  - 0045
  - 0047
---

# Account for every official Hong Kong judgment listing entry

Hong Kong Cases acquisition distinguishes an official source listing, one
separately delivered judicial decision, and the official artifacts that
publish that decision. Every official listing entry observed within one fixed
cutoff receives an explicit acquisition outcome. Pinecone record count is
never used as proof of source completeness.

## Three acquisition levels

The Source Rulebook and Management Register keep these objects separate:

1. an **Official Judgment Listing Entry** is one source result observed in a
   Judiciary inventory;
2. a **Judicial Decision** is one separately delivered judgment or set of
   reasons tracked as a Legal Item under ADR 0014; and
3. an **Official Judgment Artifact** is one exact source file or official
   rendered representation publishing one Official Version of that decision.

One listing is not automatically one decision or one Search Record. One
decision may have several proceeding numbers, listings, media formats, and an
optional translation. Duplicate listings or files may identify the same
decision. A valid acquired decision may produce zero Case Propositions.

## Source roles

The Judiciary Legal Reference System inventory is the primary current official
publication inventory for the courts and artifact classes accepted by ADR
0046. The originating Judiciary judgment file or official rendered judgment is
the primary wording evidence.

The relevant court registry is an item-specific official fallback when a known
artifact is unavailable or authenticity, correction, or version is unclear.
Judiciary Library and Privy Council collections support the separately
accountable historical baseline and bounded item investigations.

Judiciary Translation Artifacts remain optional linked evidence under ADR
0047. Their presence or absence does not define judgment coverage. Registered
Source `HK-CASE-HKLII-DISCOVERY` remains non-controlling and nonblocking under
ADR 0045.

The exact stable source IDs other than the already accepted HKLII role,
endpoint records, and connector profiles belong in the Hong Kong Cases Source
Register and Source Rulebook Package. Changing a URL or endpoint does not
change a source role.

## Exact listing-entry outcomes

Every observed official listing entry at the cutoff has exactly one of these
acquisition outcomes:

| Outcome | Meaning |
|---|---|
| `ACQUIRED` | Complete accepted originating judgment evidence is preserved. |
| `DUPLICATE_OR_ALIAS` | Evidence proves that the entry identifies an already acquired decision or artifact. |
| `TRANSLATION_ARTIFACT` | The entry is an optional official translation linked to the acquired original. |
| `OUT_OF_SCOPE` | The issuing court, artifact class, or publication is outside ADR 0046; the exact reason is recorded. |
| `BLOCKED_UNAVAILABLE` | An in-scope original is known but cannot currently be obtained or completely validated. |
| `QUARANTINED` | Decision, version, language, opinion, artifact identity, or source evidence conflicts or remains unresolved. |

An entry first observed after the cutoff belongs to a later Observation. It is
not forced into or hidden within the earlier accounting.

A successfully acquired decision separately receives one processing and
release-accounting outcome: one or more supported Case Propositions, validly no
material Case Proposition, processing Quarantine, or the applicable explicit
unavailable-scope outcome. A missing or unreadable judgment is never labelled
as a valid decision with no proposition.

## Three separate completeness results

Every coverage proof reports these facts separately:

1. **inventory accounting** — whether every observed listing entry has exactly
   one acquisition outcome;
2. **evidence coverage** — whether every in-scope decision has accepted
   originating evidence or an explicit unresolved Coverage Gap; and
3. **search output** — how many acquired decisions produced zero, one, or many
   Case Proposition Search Records.

Complete inventory accounting may honestly contain a Coverage Gap. It does not
make that gap safe, prove evidence coverage complete, or make a release
eligible. A supported no-change result requires every due official inventory
check to succeed, complete reconciliation with the preserved prior inventory,
an explicit outcome for every in-scope change, and no hidden blocking conflict.
Producing no new Search Record is not a no-change proof.

The design keeps excluded entries visible in accounting so connector
observation cannot silently expand the accepted court scope. It also accounts
for every valid in-scope decision that produces no searchable proposition.

## Acquisition evidence bundle

For every acquired artifact, the Evidence Vault and Management Register
preserve or reference:

- the exact source bytes or exact official rendered capture;
- source identity, URL, endpoint version, observation time, and cutoff;
- response, listing, and publication metadata;
- every source label for judgment, reasons, language, translation, correction,
  revision, or other displayed role;
- case name, issuing court, decision date, neutral and reported citations, and
  every proceeding number;
- original-or-translation role and language;
- media type, byte length, and cryptographic hash;
- parser, conversion, rendering, and validation versions and reports; and
- relationships to duplicate listings, formats, translations, corrections,
  replacements, and prior captures.

A generated working conversion never replaces the source artifact. Official
anonymisation and redaction are preserved exactly; acquisition and processing
must not attempt to restore concealed information.

## Format and version behavior

Hong Kong Cases do not inherit Hong Kong Legislation's mandatory XML-and-PDF
pair. One complete format may support acquisition when it is an accepted
official original and passes its pinned format profile.

When several official original-language representations are relied on, the
pipeline preserves them and deterministically reconciles their legal content
under enumerated presentation rules. A material unexplained difference enters
Quarantine. Fuzzy similarity or a generative LLM cannot declare conflicting
formats equal.

A stable URL whose bytes change is always a new Source Snapshot observation.
It creates a new Official Version only when official evidence supports a
correction, revision, reissue, or replacement under ADR 0014. An unexplained
silent change is preserved and quarantined rather than overwriting the prior
artifact or inventing legal continuity.

A disappeared listing or failed download is not proof that a judgment was
withdrawn. The pipeline retains the previous evidence, opens bounded source or
registry reconciliation, and uses ADR 0005 when the affected current scope
cannot otherwise be supported.

## Scalable monitoring

The acquisition design uses overlapping tiers:

- lightweight newly-added or RSS checks each working day;
- metadata-only reconciliation by court, publication product, and time
  partition at that partition's assigned freshness interval;
- complete artifact acquisition only for a new, changed, missing, conflicting,
  or specifically reviewed item; and
- historical-library acquisition for the initial historical baseline or one
  bounded investigation question.

Recent partitions are checked more often than old stable partitions. Every due
partition must nevertheless complete successfully before it can support the
applicable no-change claim. Existing hashes and preserved artifacts are reused
instead of repeatedly downloading unchanged judgment files.

The exact endpoints, partition sizes, parser profiles, retry counts, clock
times, and backoff settings are implementation contracts. Before a baseline or
no-change result relies on the LRS inventory, technical conformance must prove
that the accepted connector can enumerate the complete promised scope. If it
cannot, the system reports the unresolved limitation; HKLII discovery cannot
cure it.

Acquisition, hashing, inventory reconciliation, and coverage arithmetic use no
generative LLM. This ADR does not settle the separately deferred allocation for
Case Proposition or later-treatment analysis.

## Consequences

The Hong Kong Cases Source Rulebook needs the three acquisition objects,
listing outcomes, three-part completeness proof, source roles, format profiles,
freshness tiers, disappearance behavior, and conformance cases. The Management
Register needs immutable listing-to-decision-to-artifact relationships and
must preserve zero-proposition decisions as accounted outcomes.

This decision authorizes documentation only. It does not authorize connector
implementation, source acquisition, AI or embedding calls, release
publication, Pinecone mutation, promotion, or deployment.
