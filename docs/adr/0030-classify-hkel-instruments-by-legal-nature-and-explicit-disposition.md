---
status: accepted
date: 2026-08-11
review_required: true
review_gate: before-hong-kong-instruments-rulebook-finalization
amends:
  - 0019
  - 0029
amended_by:
  - "0081"
depends_on:
  - 0011
  - 0013
  - 0018
  - 0020
  - 0022
  - 0029
---

# Classify HKeL instruments by legal nature and explicit disposition

> **Future review required:** This ADR is the accepted current baseline, but the
> user has expressly flagged HKeL's Instruments & Others treatment for later
> revision. It must be revisited before the Hong Kong Instruments disposition
> work is considered final or implementation-ready. A later accepted ADR may
> amend or supersede this decision.

Hong Kong e-Legislation's (HKeL) `Instrument` classification and A-number are
source publication and indexing facts. They do not by themselves determine an
item's legal nature, Release Scope owner, current legal effect, search
eligibility, identity, evidence path, or authority note.

The official [HKeL XML data dictionary](https://www.elegislation.gov.hk/datagovhk/hkel_data-dictionary_en.pdf)
describes the `instrument` document type as a constitutional or other
instrument. The official [legislation-list data dictionary](https://www.elegislation.gov.hk/datagovhk/hkel_list_xml-dictionary_en.pdf)
separately exposes Ordinance, Subsidiary Legislation, and Instrument source
types. HKeL's verified-legislation material nevertheless identifies A-series
entries such as A401 and A405 by their legal titles, the National Flag and
National Emblem Ordinance and the National Anthem Ordinance. The source filing
category therefore cannot replace legal-role classification.

## Instrument Disposition Registry

The Hong Kong Legislation Source Rulebook contains one immutable, versioned,
and fingerprinted **HKeL Instrument Disposition Registry**. It accounts for
every HKeL Instruments & Others entry observed at the applicable cutoff and
for every Legal Item or Legal Status Event represented or proved by that
entry.

One HKeL entry is not assumed to equal one Legal Item. A promulgation wrapper,
schedule, or bundled instrument may prove an application event and also contain
the text of one or more separately tracked authorities. The registry separates
the source artifact from the legal objects supported by it.

Each registry entry records at least:

- the register-owned identity and all observed HKeL A-numbers, URLs, titles,
  and other source aliases;
- the exact source entry and evidence fingerprints;
- the actual legal nature of each resulting Legal Item or Legal Status Event;
- the one owning Release Scope;
- the serving disposition and its exact Source Rulebook rule;
- zero or more additional evidence and relationship roles, such as
  `interprets`, `amends`, `approves`, `promulgates`, `implements`,
  `supersedes`, `ceased-to-apply`, or another controlled role;
- the current-effect, version, commencement, cessation, replacement, and
  conflict evidence on which the result depends;
- the applicable verified- or assisted-copy evidence path;
- the authority-note consequence for this and related Search Records; and
- the required behavior when the source entry is added, changed, removed,
  renumbered, repackaged, or reclassified.

Registry versions are part of the Source Rulebook fingerprint. Historical
releases and decisions remain bound to the exact registry version they used.

## Release Scope ownership

Ownership follows the item's actual legal nature, not its HKeL package:

- a Hong Kong Ordinance belongs to `HK-LEG-ORDINANCES`, including when HKeL
  gives it an A-number and stores it in Instruments & Others;
- subsidiary legislation belongs to `HK-LEG-SUBSIDIARY`, including when it is
  stored beside an A-series principal Ordinance; and
- the Basic Law, applicable Annex III national laws, central constitutional
  decisions and interpretations, and genuine residual constitutional or other
  instruments belong to `HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS`.

Examples of the first category include A305, A401, A405, A601, and A602, whose
legal titles identify them as Ordinances. Instruments made under the
Safeguarding National Security Ordinance, including the present A305A through
A305C family, are routed according to their subsidiary legal nature. These are
inventory examples, not permanent identity rules based on their current
A-numbers.

No Legal Item may be owned by two Release Scopes. Complete release validation
rejects duplicate ownership and any unaccounted covered item.

## Serving disposition and evidence roles

Serving disposition and evidence roles are separate dimensions. One authority
may be searchable current text and also interpret or implement another
authority. Conversely, an event instrument may be non-searchable while proving
why, when, or how a different authority applies.

Every supported legal object receives one primary serving disposition:

| Disposition | Meaning |
|---|---|
| `SEARCHABLE_CURRENT` | A presently operative authority that may be directly applied in current legal analysis and satisfies all text, status, bilingual, and conflict requirements |
| `WAITING_ROOM` | Validly made or adopted material that is not yet operative for ordinary current-law search |
| `EVIDENCE_ONLY` | An event, wrapper, amendment, approval, promulgation, or relationship artifact whose relevant present effect is represented by another current authority and which adds no separately searchable present rule |
| `HISTORICAL` | Ceased, superseded, spent, functionally exhausted, or other preserved material outside ordinary current-law Pinecone |
| `QUARANTINE` | Material whose identity, legal nature, current effect, evidence, bilingual alignment, ownership, replacement, or conflict cannot yet be resolved under the written rules |

The searchability test asks whether the item contains a presently operative
rule, power, duty, legal boundary, procedure, or authoritative interpretation
that legal analysis may directly apply. Search additionally requires the
settled bilingual evidence, a supported current status, one unambiguous owner,
and no unresolved replacement or source conflict.

Material is `EVIDENCE_ONLY` only when its relevant legal work is completely
represented by another tracked current authority and it adds no independently
applicable present rule. A promulgation artifact may therefore prove application
of a national law while that national law supplies the searchable provisions.
The system does not create duplicate Search Records merely because the same
wording appears in both a wrapper and the applied authority.

The HKeL `InEffect` value is a required signal but not a complete legal
conclusion. The Legal Desk records an item-specific reason for current search,
Waiting Room, evidence-only, historical, or Quarantine treatment. Express
source statuses such as A111 and A113 having ceased to apply are preserved and
normally place the affected text outside ordinary current search. A one-time or
older arrangement is not made current-searchable merely because HKeL continues
to list it as `InEffect`.

The Legislative Council Rules of Procedure are not excluded merely because
ADR 0027 excludes Bills and proceedings. The rules are evaluated as a possible
present procedural authority; a transcript, debate, vote, or other proceeding
remains excluded.

## Interpretations, relationships, and authority notes

A still-applicable NPCSC interpretation is represented as its own Legal Item
and may be `SEARCHABLE_CURRENT`. It also carries an evidence-backed
`interprets` relationship to the exact Basic Law provision or other authority
it interprets. The interpretation is not silently merged into or substituted
for the interpreted text.

The registry determines the authority-note consequence separately. When retrieval of
an interpreted provision without the applicable interpretation could cause
materially incomplete reliance, the affected provision's Search Record carries
a controlled English warning clause in `metadata.authority_note` instructing
the downstream LLM to read
the provision with the named interpretation. A relationship does not
automatically create an authority note when no substantive reliance
qualification is needed. Records without an approved substantive note retain the exact
string `"None"`.

Authority notes follow ADRs 0013, 0020, and 0050. They are delivered to the downstream LLM,
excluded from embeddings, supported by exact evidence, and cause a new Search
Record when the approved authority-note payload changes.

## Complete reconciliation and change behavior

Every observation cutoff reconciles the complete live HKeL Instruments &
Others inventory against the exact registry version. The reconciliation proves
that every observed entry and resulting legal object is accounted for once,
every expected entry has an explained presence or absence, and all ownership,
disposition, evidence, relationship, and authority-note requirements validate.

A previously unknown entry does not inherit treatment from a nearby A-number,
title pattern, subject group, or source status. It opens affected-item review
and remains out of search until a new fingerprinted registry version assigns an
evidence-backed result. An unexplained disappearance, new entry, duplicate
owner, unaccounted object, legal-nature change, or source conflict blocks the
affected item or scope under the accepted coverage rules.

An A-number remains an Identity Alias. Renumbering, repackaging, or a source
move cannot by itself keep, replace, split, or merge a Legal Item. Identity and
lineage continue to require the evidence-backed rules in ADRs 0011 and 0012.

## Consequences and remaining work

The three accepted Hong Kong Legislation Release Scopes remain unchanged, but
ADR 0019's reference to accepted HKeL Instruments & Others material is now
constrained by legal-nature routing and the Instrument Disposition Registry.
ADR 0081's verified- and assisted-copy rules apply only after the registry has
identified the actual legal nature and owning scope.

The registry contract and classification rules are settled. Populating and
legally reviewing the complete current row set remains concrete Hong Kong
Legislation Source Rulebook work. A dated source count is an observation, not a
permanent design constant; future source changes are handled through complete
reconciliation and a new registry version.

This decision does not authorize source acquisition, implementation,
publication, Pinecone mutation, or deployment. Source-specific legal
compliance remains deferred to the legal team under the project's accepted
assumption.
