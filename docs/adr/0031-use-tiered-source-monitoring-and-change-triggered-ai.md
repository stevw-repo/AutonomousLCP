---
status: accepted
date: 2026-08-11
amended_by:
  - 0032
  - 0039
  - 0043
refined_by:
  - "0086"
amends:
  - 0019
  - 0025
  - 0026
  - 0028
depends_on:
  - 0005
  - 0018
  - 0023
  - 0029
---

# Use tiered source monitoring and change-triggered AI

Hong Kong Legislation uses source-specific monitoring tiers rather than
frequent uniform polling. Ordinary Watcher checks are lightweight and
deterministic. AI, embeddings, and full-artifact acquisition do not run merely
because a scheduled check occurred.

The official [HKeL current-data catalogue](https://data.gov.hk/en-data/dataset/hk-doj-hkel-legislation-current)
and [current-inventory catalogue](https://data.gov.hk/en-data/dataset/hk-doj-hkel-list-of-legislation-current)
state a weekly update frequency. The official [HKSAR Gazette Important Notices](https://egazette.gld.gov.hk/en/important-notices)
state that the ordinary Gazette is normally published on Friday and Gazette
Extraordinary is published as needed. The checking design follows those source
behaviors and the pipeline's weekly release cycle.

## Separate clocks

The Source Rulebook records four different time concepts:

1. **checking cadence** — how often the Watcher attempts a lightweight source
   check;
2. **publisher expectation** — the source's normal issue or refresh pattern;
3. **Observation freshness** — the time since the latest complete successful
   check; and
4. **publication-age expectation** — when missing an expected issue or refresh
   becomes suspicious.

A source may be freshly checked even when its content has not changed. A fresh
Observation does not manufacture a new Official Version. Conversely, a failed,
partial, blocked, or unreconciled check is not a no-change Observation.

## Monitoring tiers

The accepted ordinary tiers are:

| Tier | Source roles | Normal Watcher cadence | Weekly release requirement |
|---|---|---|---|
| **Daily current-law signals** | HKeL current lists and resource fingerprints; ordinary and Extraordinary Gazette inventories | Once per day; completely reconcile the expected ordinary-Gazette issue after its normal publication window | Latest complete successful Observation must be within 24 hours of the observation cutoff |
| **Weekly supporting sources** | HKeL Editorial-Record inventory; HKeL publication specifications and Important Notices | Once in each weekly pipeline cycle | Must have a successful current-cycle Observation whenever an affected release or processing decision relies on the source |
| **Monthly or event-triggered cross-checks** | Basic Law portal and other non-controlling constitutional or national-authority cross-checks | Complete monthly baseline check, plus an immediate affected check after a relevant controlling-source signal | Temporary absence does not invalidate otherwise complete controlling evidence; preserve and report the outage or discrepancy |
| **On-demand item and investigation evidence** | Matching verified or assisted PDFs, full current XML packages, HKeL past inventories and data, archival Gazette evidence, historical files, and other large artifacts | No periodic check or re-download merely to prove silence | Acquire only after a changed fingerprint, new item, missing preserved evidence, active review, historical investigation, recovery task, or release decision requires it |

ADR 0032 amends the earlier weekly assignment for HKeL past data. Historical
inventories, past XML, past verified PDFs, and official archival Gazette
material are now on-demand sources without an ordinary release freshness gate.
Their unavailability blocks only a task or decision that expressly requires
them. Editorial Records remain weekly because they may directly explain a new
current-text change.

The Source Register stores the tier and its concrete calendar in Hong Kong time.
Calendar handling accounts for the source's published schedule and accepted
holiday or official exceptions. An unexplained missing expected ordinary
Gazette issue, numbering gap, or missed HKeL publication expectation opens a
source-staleness investigation; it is not treated as proof that no legal change
occurred.

These cadences are the normal minimum checks for the Hong Kong Legislation
Source Rulebook. Bounded retries after failure and one release-preflight check
do not change a source's ordinary tier. Rate limits or provider instructions may
require a less frequent future rulebook version; the system does not silently
weaken the accepted cadence at runtime.

## Lightweight deterministic Watchers

An ordinary Watcher check compares only the minimum complete source signals,
such as inventory identities, timestamps, declared resource hashes, issue and
notice numbers, URLs, schemas, and specification fingerprints. It preserves
the Observation and comparison result.

The Watcher does not repeatedly acquire every large ZIP, XML document, PDF, or
historical artifact. A changed or missing deterministic signal creates bounded
work for the Scraper. The Scraper then acquires the exact complete affected
artifacts required by the Source Rulebook.

Reachability alone is not success. A successful no-change Observation requires
the complete expected inventory, language resources, issue sequence, and
fingerprints for that source role to reconcile. A partial response, missing
page, unexpected shrinkage, unexplained gap, or schema failure remains a source
failure or change signal.

## Generative-LLM and embedding gate

A generative LLM is not part of an ordinary scheduled Watcher check. The
processing sequence is:

1. perform the deterministic source check;
2. record a no-change Observation and stop when the complete fingerprinted
   state is unchanged;
3. deduplicate a real changed or missing signal;
4. acquire only the required affected artifacts;
5. run deterministic schema, hash, inventory, version, bilingual-pairing,
   known-rule, and prior-evidence checks; and
6. invoke a generative LLM only through a stable task expressly enabled by an
   accepted task contract and rulebook.

ADR 0039 originally named two case-law candidates,
`case-proposition-extraction` and `later-treatment-proposal`. ADR 0043 later
defers the final task inventory and deterministic-versus-LLM allocation,
including possible bounded Hong Kong Gazette support. ADR 0053 later accepts
Hong Kong later-treatment allocation and ADR 0065 later accepts Hong Kong Case
Proposition extraction allocation. This ADR's generic change gate is a
necessary condition for any later-approved model work, not authorization for
any task.

Changed work is batched within the weekly cycle where dependencies allow. An
earlier LLM or processing result may be reused only when every result-determining
input matches, including the complete evidence fingerprints, rulebook version
and fingerprint, task and prompt contract, model configuration, deterministic
processing version, and required output contract. Reuse is recorded; similarity
or unchanged source titles are insufficient.

Embedding calls occur only after a validated changed Search Record is selected
for a candidate release. A source change signal, scrape, or LLM result never
directly authorizes embedding or Pinecone access.

## Urgent checks

An official alert, controlling-source signal, or authorized human report may
open an urgent run between scheduled checks. Urgency changes when the work
starts; it does not bypass source capture, reconciliation, Legal Desk rules,
Quarantine, validation, human approval, recovery evidence, or promotion
controls.

The urgent run is bounded to the affected source and dependencies unless the
evidence requires wider reconciliation. Its result is included in the next
complete affected Corpus Release and Promotion Manifest rather than being
written directly to Pinecone.

## Staleness and failure behavior

At the observation cutoff, every blocking source role must have the fresh
successful Observation required by its tier. An expired, failed, partial, or
unreconciled required Observation makes that source unavailable. The system
cannot record no change or declare a fully fresh release.

After bounded retries, it preserves the outage evidence, reports a Coverage
Gap, and applies only the accepted carry-forward, Withholding Release, or no-
rebuild outcome under ADR 0005. Existing records are not silently deleted,
rewritten, or represented as newly verified.

Publisher delay and legal-text staleness remain separate. If Gazette evidence
proves a commenced change that HKeL current text does not yet contain, ADR 0023
and the withholding or no-rebuild rules apply to the affected records. If no
change is proved, a stale required source still prevents a fully fresh release
claim but does not prove that the existing law changed.

A non-controlling cross-check outage does not invalidate a complete controlling
evidence bundle under ADR 0029. The outage remains visible and any detected
conflict blocks the affected item until resolved.

## Consequences

The design scales by source role and change rate. Adding jurisdictions does not
create proportional LLM, embedding, or large-download activity when most source
checks are unchanged. Complete deterministic observations, not expensive
processing, provide routine assurance.

The exact clock times, retry counts, backoff values, concurrency limits, and
provider rate-limit settings remain bounded operational configuration inside
the accepted daily, weekly, monthly or event-triggered, and on-demand tiers.
They cannot weaken the release-freshness requirements.

This decision does not authorize implementation, source acquisition, AI or
embedding-provider calls, publication, Pinecone mutation, or deployment.
