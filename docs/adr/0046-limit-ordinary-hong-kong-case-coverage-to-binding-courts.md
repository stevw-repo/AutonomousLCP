---
status: accepted
date: 2026-08-12
depends_on:
  - 0014
  - 0018
  - 0024
  - 0045
---

# Limit ordinary Hong Kong case coverage to binding courts

## 2026-08-25 V1 amendment

For the approved live V1 only, the statement below that separately accountable
historical coverage includes pre-1997 superior-court and Privy Council material
is superseded. V1 begins inclusively on 1 July 1997 and excludes every earlier
Hong Kong Case; every official listing in the accepted binding-court families
from that date onward still requires one exact disposition. The historical
families remain part of this ADR's broader post-V1 design and have not been
deleted or reclassified.

The controlling V1 scope and exclusions are in the
[Hong Kong Live V1 Execution Specification](../design/HK_V1_LIVE_EXECUTION_SPEC.md).

Ordinary searchable Hong Kong Case coverage includes a court when the ratio of
one of its decisions can bind at least one lower Hong Kong court. “Binding”
does not mean that every proposition from that court binds every other Hong
Kong court.

## Included courts and decisions

The ordinary scope covers every publicly released written judicial decision or
written reason within the accepted artifact classes from:

- the Court of Final Appeal;
- the Court of Appeal;
- the Court of First Instance; and
- the Competition Tribunal.

Separately accountable historical coverage includes the corresponding pre-1997
Hong Kong superior courts and pre-1997 Privy Council appeals from Hong Kong.
Historical inclusion does not bypass proposition-level current-authority and
later-treatment rules under ADR 0014.

The originating court of the written decision controls coverage. A covered CFI,
CA, or CFA decision remains included when it concerns an appeal, review, or
other proceeding originating in an excluded lower body.

The coverage promise is limited to publicly released written judgments,
reasons for judgment, reasons for verdict, reasons for sentence, and applicable
miscellaneous written judicial decisions accepted by the Hong Kong Cases Source
Rulebook. It does not promise every hearing, oral ruling, order without reasons,
private or restricted proceeding, pleading, transcript, or court filing.

Every in-scope official decision must be accounted for even when it produces no
material Case Proposition and therefore no Pinecone record.

## Excluded lower bodies

The ordinary searchable scope excludes standalone decisions from:

- the District Court and Family Court;
- Magistrates' Courts and Juvenile Court;
- the Lands Tribunal;
- the Labour Tribunal;
- the Small Claims Tribunal;
- the Obscene Articles Tribunal;
- the Coroner's Court; and
- another lower or specialist body unless a later accepted decision expressly
  adds it.

Technical extractability does not change this authority boundary. An excluded
decision may remain an HKLII discovery lead, appear in the Case Dossier or
evidence for an included appellate decision, or support internal source
reconciliation. It does not create a standalone ordinary-search Case
Proposition or Pinecone record.

## Why the three reviewed bodies remain excluded

Published Family Court and Lands Tribunal judgments are technically tractable,
but their standalone propositions are not binding authorities within the
accepted ordinary scope. Family Court publication is also selective. Relevant
binding appellate decisions remain covered according to the court that issued
them.

Individual published Labour Tribunal reasons are parseable, but the observed
public inventory is too sparse to support a credible ordinary-coverage promise.
Relevant CFI and later appellate decisions remain covered.

Of the three, the Lands Tribunal is the strongest possible future source of
specialist but non-binding analysis. It is not activated by this decision. A
future `specialist-persuasive` product would require a separate accepted scope,
retrieval isolation from binding case law, an explicit LLM-facing authority
authority note, complete originating-source and coverage rules, and its own tests and
approval. Family Court reconsideration would require the same separate
decision and preservation of official anonymisation. Labour Tribunal
reconsideration additionally requires a materially better originating-source
inventory.

## Source boundary

The Judiciary Legal Reference System publication products are the primary
official online route for in-scope current decisions. The relevant court
registry is an item-specific official fallback when a known decision is not
online or authenticity, correction, or version is unclear. Judiciary Library
and Privy Council collections support separately accountable historical and
item-specific acquisition.

ADR 0045 continues to govern HKLII: it may automate discovery and cross-checking
but cannot by itself prove judgment wording, version, authority, proposition,
treatment, authority note, or retirement.

## Consequences

The Hong Kong Cases Source Rulebook must encode the exact included court and
artifact classes, historical boundary, excluded-body behavior, source roles,
complete in-scope decision accounting, and conformance cases. A source
connector may observe material outside coverage, but processing and corpus
construction must enforce the accepted scope before any serving record is
created.

This decision authorizes documentation only. It does not authorize connector
implementation, source acquisition, AI or embedding calls, release
publication, Pinecone mutation, promotion, or deployment.
