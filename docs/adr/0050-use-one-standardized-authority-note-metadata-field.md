---
status: accepted
date: 2026-08-12
amended_by:
  - 0054
  - 0055
  - 0056
  - 0058
refined_by:
  - "0078"
  - "0079"
  - "0080"
  - "0081"
amends:
  - 0008
  - 0011
  - 0013
  - 0014
  - 0015
  - 0016
  - 0020
refines:
  - 0019
  - 0021
  - 0029
  - 0030
  - 0033
  - 0034
  - 0035
  - 0037
  - 0038
  - 0040
  - 0041
  - 0047
  - 0049
depends_on:
  - 0018
---

# Use one standardized authority-note metadata field

Every Search Record uses the same six required metadata strings across
Legislation, Cases, jurisdiction-specific Principles, and approved
jurisdiction-specific Regulatory Materials:

- `text`;
- `country`;
- `jurisdiction`;
- `type`;
- `source`; and
- `authority_note`.

This replaces the formerly required field name `warning`. It does not add a
case-only `treatment` field and does not increase the standardized field count.
The top-level Search Record ID remains separate.

`authority_note` is the complete controlled note delivered with one retrieved
record to help the downstream LLM assess how safely and strongly it may rely on
that record. It can carry mandatory reliance warnings and tightly selected
supportive or neutral explanatory authority context without mixing any of it
into source text.

## Values and common grammar

`authority_note` is always a string and always present. The exact case-sensitive
value `"None"` means no approved LLM-facing record-level authority note applies
at the Serving State's observation cutoff. It does not mean that no citation,
legal event, publisher event, source gap, or unobserved later treatment exists
beyond the accepted evidence and coverage cutoff.

Every real note uses one or more controlled clauses. Mandatory clauses appear
first and use a `[WARNING: ...]` prefix. Supportive clauses follow and use a
`[SUPPORT: ...]` prefix. Material neutral explanations come last and use
`[CONTEXT: EXPLAINED]`. The versioned renderer owns the permitted clause types,
ordering, punctuation, length, selection, and templates.

Example supportive case note:

```text
[SUPPORT: FOLLOWED] This proposition was followed in HKSAR v Example
[2026] HKCA 100 at [42]-[47].
```

Example mixed case note:

```text
[WARNING: CRITICISED] This proposition was criticised in Example v
Secretary [2026] HKCA 101 at [70]-[75]. Do not state it as settled without
this qualification. [SUPPORT: FOLLOWED] It was earlier followed in Earlier
Example [2024] HKCA 50 at [31]-[35].
```

Example positive and explanatory case note:

```text
[SUPPORT: APPROVED] This proposition was approved by the Court of Final Appeal
in Example [2026] HKCFA 10 at [40]-[44]. [SUPPORT: FOLLOWED] It was followed
by the Court of Appeal in Later Example [2027] HKCA 20 at [31]-[35].
[CONTEXT: EXPLAINED] Its scope was explained in Another Example [2028] HKCA 30
at [52]-[58].
```

Example legislation note:

```text
[WARNING: LIMITED OPERATIVE SCOPE] This record is current only for the
identified commenced provision; do not generalize it to uncommenced
locations.
```

Supportive information never cancels, hides, weakens, or follows an ordering
that could obscure a mandatory warning. Neutral context is not endorsement and
cannot be presented as support. If any mandatory clause applies, it is
rendered first and remains the controlling reliance instruction.

## Material-specific use

The field has one common meaning but material-specific approved evidence and
clause vocabularies:

- **Cases** may use proposition-specific positive, explanatory, limiting,
  mixed, or adverse later treatment. `APPROVED` and `FOLLOWED` are eligible
  support; `APPLIED` is eligible when materially useful to authority
  assessment. `EXPLAINED` is eligible only when it materially clarifies the
  exact proposition's meaning, scope, or use, and it is rendered as neutral
  context rather than support. Selection considers court hierarchy,
  jurisdiction, operative opinion status, exact treatment scope, continuing
  status, and supporting passages. `CITED_ONLY`, factual reference, and
  equivalent repetitive treatment that adds no distinct authority signal
  remain internal or are represented through the consolidated clause.
- **Legislation** may use operative-scope, status, constitutional-
  interpretation, source, representation, or other approved reliance warnings.
  A supportive clause is permitted only if it communicates a material source-
  supported authority fact rather than repeating ordinary current status.
- **Principles** may use publisher currency, withdrawal, qualification, source,
  or other approved reliance warnings. Source-faithful publisher text remains
  in `metadata.text`; authority notes do not rewrite that text.
- **Regulatory Materials** may use effective-date, transitional applicability,
  market scope, source, representation, or other approved reliance warnings.
  Formal rule text remains in `metadata.text`; an authority note does not turn
  guidance or a proposal into a current rule.

The exact value remains `"None"` when no approved warning, selected material
support, or selected material context applies. Licence expiry
alone continues to create no note under ADR 0015. An assisted-copy evidence
class alone continues to create no note under ADR 0029. Ordinary positive case
citations do not create notes merely because they exist.

## Case-treatment boundary

The complete structured treatment graph remains in the Management Register and
Evidence Vault. The Record Traceability Lookup points to the approved authority-
note evidence and fingerprint. `metadata.authority_note` is one concise
proposition-specific rendering, not a raw list of every citation or every
eligible treating case. Every accepted relationship remains internally
traceable even when it is not selected for rendering.

There is no fixed support- or explanation-clause count. The renderer includes
every current material non-repetitive support and explanation that fits the
pinned authority-note metadata and downstream-context budget. It consolidates
equivalent treatment while retaining separate signals for a different court-
authority level, proposition scope or issue, later confirmation after adverse
or limiting treatment, materially different reasoning, or another independent
authority fact.

Operative opinion status, Hong Kong court authority, treatment significance,
exact proposition scope, continuing status, and stable tie-breakers control
ordering and compression only when the budget is approached. They do not
create a fixed clause-number cap. The renderer must not compute or expose a
numerical authority-strength score, and citation counts must not substitute
for legal authority.

Every distinct current mandatory warning effect must be rendered before any
support or context. An approved template may consolidate genuinely equivalent
warnings but may not omit a material effect. If the complete mandatory warning
meaning cannot fit the pinned budget, the proposition cannot serve with an
incomplete note and follows the accepted Quarantine, withholding, or no-new-
target rules. If optional support and context exceed the remaining budget
after faithful consolidation, deterministic ranking keeps the most legally
informative rendering and every omitted relationship remains internal.

Unresolved proposals, raw model output, reviewer notes, confidence scores,
operational identifiers, source instructions, and long treatment histories do
not enter the field. Promotion validation proves that every rendered clause
agrees with the structured graph, court relationship, cutoff, approved Legal
Desk result, and exact source passages.

An expressly and conclusively overruled proposition remains outside ordinary
current Pinecone under ADR 0014. It is not retained merely to display an
authority note. Its complete treatment and retirement history remains
preserved outside Pinecone.

## Hong Kong language rule

Every real Hong Kong `metadata.authority_note` is English only. The note is an
internal downstream-LLM authority and reliance instruction, not authentic
Hong Kong legal text or a user-facing translation. It remains English even
when `metadata.text` contains Traditional Chinese or bilingual legislation.

Chinese-query end-to-end tests must prove that the exact English authority note
reaches the downstream LLM and affects its reliance behavior. If a future user
interface displays the field verbatim, its language and presentation require a
new explicit decision.

ADR 0080 adds one controlled exception for answer text, not interface display:
when a reconstructed consolidation supports an answer, the downstream model
reproduces the English reconstruction warning portion explicitly and does not
reproduce the internal `[INSTRUCTION: ...]` clause. The complete metadata field
still travels unchanged and remains English only.

## Query, embedding, and identity behavior

Every compatible Ask.Legal query path passes `metadata.authority_note`
unchanged with `metadata.text` to the downstream LLM. Stripping, renaming,
rewriting, or failing to transmit it makes that path incompatible with the
Serving State.

The embedding input remains `metadata.text` only. It excludes
`metadata.authority_note`, so treatment and warning vocabulary cannot distort
semantic retrieval. The exact serialized authority note still counts toward
the complete Pinecone metadata byte ceiling.

Changing `authority_note`, including between `"None"` and a real note, changes
the immutable six-field serving payload and therefore changes which exact
Search Record is selected. A previously unseen payload receives a new Search
Record ID with forward authority-note-revision lineage. Under ADR 0055, a
preserved exact record may instead be reselected when current legal support is
proved; that creates an append-only serving-selection or reinstatement event,
not backward Search Record lineage. When `metadata.text` and the pinned
embedding contract are exact, the cached embedding may be reused.

A new citation, source event, or publisher event does not automatically churn a
record. Neither does genuinely repetitive treatment that is consolidated
without changing the approved rendering. Only an approved material authority-
note change changes the serving payload. Citation, alias, grouping, or
evidence-reference corrections that change no serving field remain Record
Traceability Lookup revisions.

## Validation and migration

Promotion proves that:

- every record has exactly one `authority_note` string;
- only exact `"None"` or a schema-valid controlled rendering is used;
- every clause has approved structured evidence and a valid material-specific
  rule;
- warning clauses precede support clauses, context clauses come last, neutral
  explanation is not rendered as support, and neither support nor context
  contradicts or weakens a warning;
- every distinct mandatory warning meaning is present, no fixed support- or
  explanation-clause cap is imposed, and any budget-based omission follows the
  deterministic selection rule while remaining internally traceable;
- the rendered-note fingerprint agrees across the Search Record, Management
  Register, Corpus Release, Record Traceability Lookup, Desired-State
  Inventory, and Promotion Manifest; and
- every active Ask.Legal query path transmits the field unchanged.

The greenfield contract has not been implemented or promoted, so no live
record migration is authorized or required by this ADR. Legacy and earlier
design artifacts may retain `warning` as historical evidence, but they cannot
define the target contract. Future schemas, fixtures, validators, query-path
tests, and generated examples use `authority_note` only.

Under ADR 0056, semantic model evaluations do not prove this exact rendering
contract. Deterministic fixtures must separately compare canonical authority-
note bytes, fingerprint, evidence bindings, ordering, budget behavior, identity
and selection consequence, and forbidden side effects.

## Consequences

ADRs 0008, 0011, 0013, 0014, 0015, 0016, and 0020 remain historical sources of
the accepted placement, immutability, query-delivery, evidence, and language
rules but are amended wherever they name or restrict the field to `warning`.
The standardized current field is `authority_note`; supportive and neutral
explanatory clauses are permitted only under this ADR's evidence, selection,
and materiality controls.

This decision authorizes documentation only. It does not authorize schema or
application implementation, source acquisition, model or embedding calls,
release publication, Pinecone mutation, promotion, or deployment.
