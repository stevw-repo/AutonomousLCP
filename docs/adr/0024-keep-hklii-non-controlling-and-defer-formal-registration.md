---
status: accepted
date: 2026-08-11
amended_by:
  - 0029
  - 0045
  - "0081"
refines:
  - 0014
  - 0018
  - 0019
---

# Keep HKLII non-controlling and defer formal registration

The Hong Kong Legal Information Institute (HKLII) is useful to the pipeline as
a research and discovery service, especially for Hong Kong Cases, but it is not
a controlling source for legal text, version, legal status, or later treatment.

## Accepted boundary

For Hong Kong Legislation, HKLII does not construct, verify, update, or
reconstruct a Search Record. HKeL XML and the applicable matching verified or
assisted official HKeL copy evidence remain the mandatory current-text path
under ADR 0081, and accepted Gazette evidence has its separate Legal Status
Event role. A difference found in HKLII may trigger an investigation but cannot
decide its result.

For Hong Kong Cases, HKLII may help a human or a later non-controlling discovery
process find:

- candidate judgments and historical authorities;
- neutral citations, action numbers, court labels, party names, and aliases;
- possible duplicates or gaps in the originating-source inventory; and
- candidate citing judgments or other possible later-treatment leads.

Before a Case Proposition, Official Version, treatment classification, authority note,
or retirement decision proceeds, the pipeline must obtain and preserve the
matching artifact from the Judiciary, court registry, BAILII, or another source
accepted by the future Hong Kong Cases Source Rulebook. An unmatched HKLII item
remains a discovery lead or enters Quarantine. HKLII content alone does not
enter Pinecone.

HKLII-generated case summaries, case-information boxes, tags, similar-case
results, and other AI features are suggestions only. They may support human
triage or evaluation but cannot supply a Case Proposition or prove legal status
or treatment. The preserved originating judgment remains the evidence.

Treaties, practice directions, law-reform documents, regulator decisions, and
other HKLII collections do not enter the current corpus merely because HKLII
indexes them. A later material-scope decision must establish their coverage and
controlling sources.

## Formal registration is deferred

HKLII remains an unregistered human research tool for now. Whether it becomes a
Registered Source, its exact discovery-only source ID, and whether a connector
is justified will be decided with the Hong Kong Cases Source Rulebook. Before
automation, the project must verify a stable permitted machine interface and
complete operational rules.

HKLII is never a critical dependency. Its downtime, redesign, incomplete
coverage, or delayed update cannot block originating-source acquisition or
support a no-change decision. If it is registered later, it remains a non-
controlling discovery and completeness-cross-check source unless another
explicit accepted decision changes this boundary.

## Consequences

The system benefits from HKLII's broad research interface without weakening the
evidence standard or duplicating HKeL as a legislation source. No HKLII-specific
connector or release work is authorized by this design decision. The future
Hong Kong Cases Source Rulebook must still define its complete authoritative
source inventory, checking rules, and exact evidence requirements.

ADR 0045 later registers HKLII as the non-controlling automated discovery role
`HK-CASE-HKLII-DISCOVERY` and removes legal-policy review as a prerequisite to
technical design or later implementation. This ADR's originating-source,
nonblocking-outage, and no-HKLII-only-serving boundaries remain accepted.
