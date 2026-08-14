---
status: accepted
date: 2026-08-14
refines:
  - "0054"
  - "0069"
depends_on:
  - "0018"
refined_by:
  - "0071"
  - "0072"
  - "0073"
  - "0074"
---

# Use a lean HKEX Regulatory Materials Source Register

The ordinary Hong Kong Regulatory Materials pipeline uses exactly five
Registered Source roles. They are the minimum sources needed to construct and
prove a complete current Main Board and GEM database under ADRs 0054 and 0069.
The pipeline does not turn every useful HKEX or SFC page into a monitored,
release-blocking source.

These are pipeline evidence sources, not inputs automatically delivered to the
downstream legal-analysis LLM. The downstream LLM receives only approved
Search Record metadata selected through Pinecone. Source inventories, update
packages, approval-framework material, monitoring reports, and investigation
evidence remain outside the serving payload unless exact source text is part of
the approved rule record itself.

## Ordinary current-source set

The Hong Kong Regulatory Materials Legal Desk owns these roles:

| Stable source ID | Fact Authority and forbidden use | Inventory responsibility | Outage impact | Monitoring tier |
|---|---|---|---|---|
| `HK-REG-HKEX-RULEBOOK-CATALOGUE` | Proves the top-level HKEX Listing Rules product families exposed for Main Board and GEM, their board association, and current product locators. It does not prove individual rule wording, effective state, or a complete component list by itself. | Bounds and reconciles the top-level families: consolidated rulebooks, Regulatory Forms, Fees Rules, and final rule updates. | A stale, failed, partial, or unreconciled catalogue blocks both scopes when the complete top-level universe cannot otherwise be bounded. | Daily lightweight deterministic check; complete successful Observation within 24 hours of the weekly cutoff. |
| `HK-REG-HKEX-CONSOLIDATED-RULEBOOKS` | Proves the prevailing current English wording and contained official structure of the Main Board and GEM consolidated rulebooks. Optional Chinese translations may support evaluation or investigation but are not current-rule wording authorities or release requirements under ADR 0072. The role does not prove separately published Forms or Fees Rules, why wording changed, or that an external condition occurred. | Completely enumerates and fingerprints every component contained in each required English consolidated rulebook, not merely its table of contents. | Missing or conflicting required English evidence blocks only the affected board when the boundary is proved board-specific; an unbounded shared failure blocks both. Optional Chinese unavailability has no release effect unless it exposes a possible English defect. | Daily deterministic English current-artifact signal; acquire and reconcile complete affected English artifacts after change or when unchanged bytes cannot otherwise be proved. |
| `HK-REG-HKEX-REGULATORY-FORMS` | Proves the separately published current English Main Board and GEM Regulatory Form inventories, express rulebook membership statements, and prevailing English form content. Optional Chinese translations are non-serving support. The role does not prove unrelated rules, fees, amendment cause, or effective external events. | Completely enumerates every separately published required English Regulatory Form and its board ownership. | Missing or conflicting required English evidence blocks the affected board or bounded form family; optional Chinese unavailability does not. An unbounded shared English inventory failure blocks both. | Daily lightweight English inventory and fingerprint check; acquire complete affected English artifacts on change. |
| `HK-REG-HKEX-FEES-RULES` | Proves the separately published current English Main Board and GEM Fees Rules, their express rulebook membership, and prevailing English content. Optional Chinese translations are non-serving support. The role does not prove other Listing Rules or amendment events. | Completely enumerates and fingerprints the separately published required English Fees Rules for each board. | Missing or conflicting required English evidence blocks the affected board or bounded fee component; optional Chinese unavailability does not. An unbounded shared English inventory failure blocks both. | Daily lightweight English inventory and fingerprint check; acquire complete affected English artifacts on change. |
| `HK-REG-HKEX-RULE-UPDATES` | Proves the complete final update inventory and the exact changed words, stated effective dates, stated conditions, transitions, mappings, withdrawals, or other update facts contained in an accepted final HKEX update notice or package. It does not prove occurrence of an external trigger, replace the current consolidated product, or turn a consultation or proposal into current rules. | Enumerates every final update entry due at the cutoff and every directly linked amendment artifact whose membership or effect must be classified. | Failure of the current update inventory blocks the affected board's fresh release. An older exact update artifact needed only for a bounded investigation blocks that work, not an otherwise supported release. | Daily lightweight update-inventory check; acquire new or changed packages on signal; older packages on demand. |

Languages, formats, URLs, update numbers, filenames, and dates are versioned
endpoint or artifact facts. They are not embedded in the stable source ID. A
URL move changes the endpoint record, not the Registered Source identity.

Current official product references include the [HKEX Listing Rules
catalogue](https://www.hkex.com.hk/Listing/Rules-and-Resources/Listing-Rules?sc_lang=en),
the [HKEX-maintained consolidated
rulebooks](https://www.hkex.com.hk/Listing/Rules-and-Resources/Listing-Rules/Consolidated-PDFs?sc_lang=en),
the separate [Regulatory
Forms](https://en-rules.hkex.com.hk/rulebook/regulatory-forms) and [Fees
Rules](https://en-rules.hkex.com.hk/rulebook/fees-rules), and the [Main Board
amendment index](https://en-rules.hkex.com.hk/rulebook/amendments-main-board-listing-rules)
and [GEM amendment
index](https://en-rules.hkex.com.hk/rulebook/amendments-gem-listing-rules).
The [SFC listing-regulation
page](https://www.sfc.hk/en/Regulatory-functions/Corporates) currently states
the standing approval framework. These links are initial endpoint evidence,
not permanent source identity.

## Complete inventory is the union, not one page

No one source proves the complete rule-component universe. At a frozen cutoff,
the declared universe is the reconciled union of:

1. every top-level product family in the complete catalogue Observation;
2. every component parsed from the complete Main Board and GEM consolidated
   rulebooks;
3. every separately published Regulatory Form;
4. every separately published Fees Rule; and
5. every due final update entry and directly linked artifact requiring
   classification.

This bounded union supplies ADR 0069's source-entry universe. A search-result
count, website navigation tree, PDF table of contents, or one successful source
cannot replace it. Before a scope is decision-ready, technical conformance must
prove that the connectors and parsers completely enumerate every assigned
product rather than silently omitting unsupported objects.

`SUPPORTED_NO_CHANGE` requires complete fresh Observations for all five due
roles and exact reconciliation with the accepted predecessor. A successful
reachability check, unchanged page title, or absence of an alert is
insufficient.

## Reference evidence is not an ordinary release dependency

The following material remains outside the five-role ordinary current-source
set:

- The Thomson Reuters-maintained online rulebook may open discovery,
  navigation, structure, or version-comparison work. It is an optional
  non-controlling cross-check, not a required release Observation and not a
  wording authority. A discovered discrepancy is preserved and assessed
  against the five accepted roles.
- Exact source-precedence, English-versus-Chinese, component-inclusion, and
  exclusion statements are pinned as fingerprinted Source Rulebook basis
  evidence from the relevant five source products. They are not duplicated as
  a separately polled publication-specifications source. A relevant change
  signal requires a new Source Contract Review and rulebook version.
- The SFC's standing approval framework supports the accepted architecture but
  is not a current-rule text feed or routine release gate. It is pinned as
  rulebook-basis evidence and rechecked after a relevant official signal or
  when a new rulebook version relies on a changed statement.
- Guidance, FAQs, listing decisions, consultations, conclusions, circulars,
  announcements, and general SFC or HKEX pages are not permanently registered
  or monitored merely because they may be useful. An exact official product or
  item is registered through a later rulebook version only when a real bounded
  decision needs its Fact Authority.

Unregistered material may trigger investigation but cannot prove a serving
change. Optional material never enters Pinecone merely because the pipeline
preserved or reviewed it.

## Approval evidence without an invented SFC feed

The public source structure does not expose one dependable separate SFC
approval notice for every HKEX rule update. The ordinary rulebook therefore
does not require an imaginary per-update approval feed.

For an ordinary final rule change, the combination of:

1. an accepted final HKEX update notice or package stating the final change;
2. the matching accepted current HKEX rulebook, Form, or Fees Rule product;
   and
3. the pinned standing framework that Listing Rule changes require SFC
   approval

may establish `APPROVAL_SATISFIED_BY_FINAL_PUBLICATION` under an exact Source
Rulebook rule. This is an explicit evidence-backed inference, not a claim that
the pipeline possesses a separate SFC approval receipt.

A consultation, proposal, draft, or publication stating that a change remains
subject to approval cannot satisfy the rule. If an item specifically requires
direct approval evidence, says approval is pending, or conflicts with the
standing framework, only that affected decision is blocked until exact
accepted SFC or Exchange evidence is registered and preserved.

## Conditional external events

There is no broad permanent source called external-trigger evidence. Every
`FUTURE_CONDITIONAL` update must declare:

- the exact fact that would activate the change;
- the exact official Registered Source role allowed to prove that fact;
- the affected board and components;
- the checking expectation while the condition remains live; and
- the result of missing, stale, negative, or conflicting evidence.

The role may already exist elsewhere, such as accepted Hong Kong legislation
commencement evidence, or may require a new item-specific official source
registration. Its heightened checking obligation exists only while a pending
condition requires it; its evidence and historical registration are not
deleted afterward.

Absence of positive evidence is not always proof that a condition remains
unmet. If the event might now have occurred but the required evidence is stale
or unavailable, the affected component becomes unresolved rather than silently
remaining future. That result may prevent the affected board from claiming
complete current serving readiness.

## Fact-specific conflict rules

There is no global newest-source-wins rule:

- the HKEX-maintained consolidated rulebook controls wording for components it
  contains;
- the separately published Regulatory Forms and Fees Rules control their own
  current components;
- a final update package proves its assigned amendment and stated timing facts
  but does not by itself prove an external event or replace current compiled
  text;
- English controls legal meaning and is the required serving text; optional
  Traditional-Chinese translations remain non-serving support under ADR 0072;
- an online-rulebook or guidance discrepancy cannot overwrite an accepted
  current product; and
- publication recency, filename, URL, or update number alone proves no current
  legal effect.

If a final update states that a change is already effective but the applicable
required English current product cannot be reconciled with it, the pipeline
does not reconstruct the current rule. The affected component becomes
`UNKNOWN` or enters Quarantine under the later effective-state rules, and the
affected board may remain not serving-ready. Missing, stale, or conflicting
optional Chinese material does not block a supported English candidate unless
it positively exposes a possible English identity, version, effective-state,
wording, or completeness defect.

## Deterministic monitoring and downstream boundary

Ordinary monitoring is deterministic. A daily check does not imply a daily
large download, LLM call, embedding call, or record rebuild. The Watcher checks
the minimum complete trustworthy inventory and fingerprint signals. Complete
artifacts are acquired only after a real signal or when the implementation
cannot prove unchanged bytes without acquisition.

If all five roles reconcile unchanged, processing stops after the immutable
Observation and supported-no-change result. No source artifact, approval
framework page, update package, guidance document, or monitoring report is
sent to the downstream LLM or added to Pinecone by this decision. Only later
validated changed Search Records may enter the ordinary corpus and promotion
flow.

## Consequences and authorization

ADR 0071 now uses these Fact Authorities to decide current,
transitional-current, future-fixed-date, future-conditional, superseded,
withdrawn, and unknown outcomes per applicability branch without reconstructing
missing current rules. ADR 0072 later makes prevailing English evidence the
required serving path and Chinese translations optional non-serving support.
ADR 0073 later fixes the English record-construction and source-unit coverage
contract. ADR 0074 later fixes the executable conformance-package architecture.
ADR 0075 later freezes the exact case table, ADR 0076 settles the high-level
semantic task allocation, and ADR 0077 settles multilingual retrieval and
answer admission architecture.

This ADR authorizes documentation only. It does not register live endpoints,
acquire source artifacts, implement connectors or schemas, call an LLM or
embedding provider, construct or publish a corpus, access Pinecone or Azure,
promote, deploy, commit, push, or perform any other production action.
