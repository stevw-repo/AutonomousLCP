# HKeL Gazette register contract

Observed by Patchright discovery on 2026-08-19 against
`https://www.elegislation.gov.hk/gazette`, under the Department of Justice
clearance the project user reported the same day. This is the contract the
register recorded as `EXACT_GRID_PAGINATION_AND_ARTIFACT_LOCATOR_CONTRACT_REQUIRED`.

Discovery output is not evidence. Everything below describes how to *ask*; any
document fetched this way must still come through an admitted inert connector and
the ordinary manifest-last evidence flow, per ADR 0100.

## 1. The client-capability gate

`/gazette` does not serve directly. It bounces through a legacy capability check
and comes back with the answer in the query string:

```
GET  /gazette                                     302 →
GET  /checkconfig/checkClientConfig.jsp?applicationId=RA001
POST /checkconfig/submitClientConfig.do
GET  /checkconfig/warning.jsp
GET  /client-check?OS=Linux&OS_S=false&BR=Chrome&BR_S=true&BRV=151.0&BRV_S=true&JS_S=true&C_S=
GET  /gazette?OS=Linux&OS_S=false&BR=Chrome&BR_S=true&BRV=151.0&BRV_S=true&JS_S=true&C_S=true&…
```

The gate is satisfied by **query parameters**, not by an applet or a hidden
cookie. `JS_S` is JavaScript support and `C_S` is cookie support; `OS`, `BR`, and
`BRV` are the reported platform and browser.

**An honesty problem lives here.** A real browser reports `BR=Chrome` and
`JS_S=true` truthfully. The inert connector is neither Chrome nor
JavaScript-capable, and asserting those values would be a false statement to the
publisher. It is very likely harmless for a JSON endpoint that never renders, but
it is a statement about our client and the decision to make it belongs to the
project owner, not to an implementer. It is called out rather than buried.

## 2. The grid request

```
POST https://www.elegislation.gov.hk/grid
Content-Type: application/json
```

```json
{
  "gridId": "GAZETTE_REGISTER_LIST",
  "gsId": "GAZETTE_REGISTER_LIST",
  "gridIndex": "0",
  "functionId": "LRTS10",
  "queryId": "GAZETTE_REGISTER_QRY",
  "screenId": "ERTS0502",
  "gridBd": "hk.gov.doj.hkel.grid.lrt.LRTS1002GridBd",
  "namespace": "hk.gov.doj.hkel.bd.ert.ERTS0502Bd",
  "pkFields": "GAZETTE_ID",
  "pageNo": "1",
  "pageSize": "20",
  "queryParams": [
    "GAZETTE_NO=", "GAZETTE_NAME=",
    "GAZETTE_SUPPLEMENT_NO=1", "GAZETTE_SUPPLEMENT_NO=2", "GAZETTE_SUPPLEMENT_NO=3",
    "GAZETTE_DATE_FR=", "GAZETTE_DATE_TO=",
    "SER_FLD=E", "GN_TYP=N", "GN_PFX=-", "GN_SFX=", "GN_NO=", "GN_YR="
  ],
  "columns": [
    "GAZETTE_SUPPLEMENT_NO", "GAZETTE_DATE", "DISP_GAZETTE_NO",
    "GAZETTE_NAME", "ENG_PDF", "CHI_PDF", "BI_PDF"
  ],
  "controls": ["text","text","text","generateGazetteName","generatePdf","generatePdf","generatePdf"],
  "csrfToken": "<from the rendered gazette page>",
  "MODE": "1"
}
```

`queryParams` is a list of `KEY=VALUE` strings, not an object. Repeating a key
is how a multi-valued filter is expressed: the three `GAZETTE_SUPPLEMENT_NO`
entries select Legal Supplements 1, 2 and 3 — Ordinances, Regulations and Bills.
Empty values mean unfiltered.

`csrfToken` is issued by the rendered page. An inert client must first fetch
`/gazette` through the capability gate and read the token from that HTML; the
grid cannot be called cold.

## 3. Pagination

Request carries `pageNo` and `pageSize`. The response reports:

| field | observed | meaning |
|---|---|---|
| `firstPage` | `1` | first page number |
| `lastPage` | `1415` | last page number |
| `startPage` | `1` | first page of the current pager window |
| `nextPage` | `6` | next pager window, **not** the next page |
| `rowOffset` | `0` | zero-based offset of the first returned row |
| `totalRecords` | `100` | see the caution below |

**`totalRecords` does not mean what its name suggests.** It reported `100` while
`lastPage` was `1415` at `pageSize: 20`, which implies roughly 28,300 rows. Do not
use `totalRecords` as a completeness figure. Walk `pageNo` from `firstPage` to
`lastPage` and count what actually arrives; treat `lastPage × pageSize` as an
upper bound only. Pin the first reply's `lastPage` and re-read it on every page;
if it moves, the observation is incomplete because its membership boundary was
not stable. `GAZETTE_ID` is the publisher's declared primary key, so an empty or
duplicate ID also prevents a completeness result.

Twenty `pkValues` were returned for `pageSize: 20`, so the page size is honoured.

The implemented iterator accepts an operational `max_pages` safety cap, but the
cap is not a completeness boundary. If the publisher reports a later page beyond
that cap, enumeration fails explicitly before the first page's rows are yielded;
it never returns a short successful result. The acquisition activity materializes
the complete bounded listing before retaining any addressed PDF or writing the
canonical listing manifest.

## 4. The artifact locator

Row data is positional, described by the response's own `columns`:

```
["GAZETTE_ID","YEAR","GAZETTE_SUPPLEMENT_NO","DISP_GAZETTE_NO","GAZETTE_NO",
 "GAZETTE_NAME","GAZETTE_TITLE_ENG","GAZETTE_TITLE_CHI",
 "ENG_PDF","CHI_PDF","BI_PDF","GZ_NO","VIRTUAL_URL","GAZETTE_DATE"]
```

One observed row:

```
["30056","2026","Legal Supplement No. 1","1 of 2026","1 of 2026",null,
 "Appropriation Ordinance 2026","《2026年撥款條例》",
 "E","C",null,"1","hk/2026/1","08/05/2026"]
```

**`VIRTUAL_URL` is the locator**, given as a site-relative path without a leading
slash. `hk/2026/1` resolves to `https://www.elegislation.gov.hk/hk/2026/1`.

This is the same shape the register already carries as `{legal_item_locator}` for
`HK-LEG-HKEL-VERIFIED-COPIES` and `HK-LEG-HKEL-ASSISTED-COPIES`, so this contract
plausibly unblocks the locator half of those roles too. That has not been
verified and should not be assumed.

`ENG_PDF`, `CHI_PDF`, and `BI_PDF` are availability flags, not URLs: `"E"`, `"C"`,
or `null`.

**The PDF address is the locator, a `!`, and the language code.** Read from the
rendered grid on 2026-08-19:

```html
<td><a href="/hk/2026/1!en"><img src="/images/icon/pdf.gif" class="pdf-link"></a></td>
<td><a href="/hk/2026/1!zh-Hant-HK"><img src="/images/icon/pdf.gif"></a></td>
<td><div>-</div></td>
```

So `https://www.elegislation.gov.hk/hk/2026/1!en`. There is no server round-trip
and no separate identifier — `generatePdf` only composes this string. The two
published languages are `en` and `zh-Hant-HK`. A cell showing a bare `-` means
that language was never published, and the matching flag is absent; there is no
address to construct and none should be invented.

Note the marker class `pdf-link` sits on the `<img>`, not on the `<a>`. Two
discovery attempts filtered anchors by class and found nothing before the row
markup was dumped and read directly.

`GAZETTE_DATE` is `DD/MM/YYYY`. `GAZETTE_NAME` was `null` on every observed row
while `GAZETTE_TITLE_ENG` and `GAZETTE_TITLE_CHI` carried the titles, which is why
the grid's `controls` name a `generateGazetteName` function for that column.

### Artifact binding boundary

The grid's `VIRTUAL_URL` remains publisher data, not trusted URL syntax. The
worker accepts only the declared `hk/` shape and supplies the suffix after that
prefix to the endpoint's single `{gazette_artifact_locator}` placeholder. The
ordinary inert connector then uses the repository's shared bounded-locator
contract. It requires exactly one declared placeholder and one relative locator;
it rejects a missing/extra substitution, absolute or empty path, leading or
trailing slash, empty or traversal segment, query, fragment, backslash, braces,
credentials, and any scheme/host/port change. Percent escapes in publisher data
are encoded again so they remain data rather than downstream path syntax.

An out-of-shape publisher locator is durable `SOURCE_CONTRACT_CHANGED` and is
never fetched. This validation is part of artifact addressing; it does not turn
the grid response itself into evidence.

## 5. Completeness boundary

An unbounded walk is not reproducible because the register grows at the front.
The implemented completeness unit is one closed past-date window. Every page
from `firstPage` through the first reply's fixed `lastPage` must arrive within
the operational cap. A moving `lastPage`, empty intermediate page, duplicate or
empty `GAZETTE_ID`, transport failure, or cap exhaustion is not a complete
result.

Settled since this was written: the project owner decided on 2026-08-19 to assert
`JS_S=true` and `BR=Chrome`, recorded in `CAPABILITY_CLAIM` with its own note that
the values are asserted rather than measured. `POST` support went to a separate
`exchange` surface on the proxied transport rather than into
`OfficialHttpConnector`, which stays `GET`/`HEAD` so the inert evidence path is
unchanged.

The contract and date-window acquisition activity are implemented. The role
remains partial rather than complete because a closed window is the unit proved;
the repository does not yet have a whole-register coverage policy or scheduled
operational admission evidence.

Grid retry is bounded to three attempts. A dropped transport and explicit HTTP
429 response use deterministic 20-second then 40-second backoff and rebuild the
publisher session before retry; persistent refusal ends `SOURCE_UNAVAILABLE`.
Grid calls also keep the HKeL profile's one-second minimum interval. The retry
does not convert a failure into no-change or completeness.

## 6. Durable activity outcomes

The worker validates exact `DD/MM/YYYY` calendar dates, `date_from <= date_to`,
and the selected `en` or `zh-Hant-HK` language before constructing the publisher
client. Invalid activity input is a task error and has no publisher effect.

Register failures are closed as `SOURCE_UNAVAILABLE`,
`SOURCE_CONTRACT_CHANGED`, or `INCOMPLETE_OBSERVATION`; the register client also
has `INVALID_REQUEST`, which the validated worker treats as a task-contract
error. All three durable register-failure results have no listing manifest and
no artifacts because complete enumeration precedes retention.

For a completely enumerated listing, every row has one selected-language
artifact outcome:

| Outcome | Meaning |
|---|---|
| `RETAINED` | The admitted inert bytes were retained and read-back verified. |
| `NOT_PUBLISHED` | The grid's language flag says the publisher issued no artifact in that language. |
| `SOURCE_UNAVAILABLE` | The addressed source could not be reached within its bounded procedure. |
| `SOURCE_CONTRACT_CHANGED` | The locator, endpoint, response, or fetch result no longer matches the admitted contract. |
| `UNSAFE_RESPONSE` | Hostile or disallowed content classification rejected the response. |

The window is `COMPLETE` only when every listed row's selected-language artifact
is `RETAINED`. Any `NOT_PUBLISHED` or failed artifact makes the window
`PARTIAL_CAPTURE`, while the complete canonical listing manifest is still
retained for exact source accounting. Infrastructure/vault failures remain
fail-closed task failures rather than being mislabeled as publisher outcomes.

## 7. Coverage accounting and outage consequence

Every terminal window result now produces a canonical, fingerprinted source-
coverage report retained in the Primary evidence vault. The report binds the
source and source-policy version, exact endpoint set, date/language observation
key, cutoff, listing-manifest reference where enumeration completed, complete
row counts, normalized outcome, exact failure codes, and the source's registered
outage consequence. A partial window preserves the strongest consequence among
its artifact results: hostile response becomes `QUARANTINE`, contract drift
becomes `SOURCE_CONTRACT_REVIEW`, and unavailable, incomplete, or merely absent
selected-language material becomes a visible `COVERAGE_GAP`.

ADR 0032 makes the HKeL Gazette backcapture role `NONBLOCKING`. Its failed or
partial report therefore does **not** by itself block a fresh release, but the
gap remains explicit and cannot be converted to `COMPLETE` or no-change. The
same report machinery applies `RELEASE_BLOCKING` to GLD e-Gazette, which remains
the originating/current-publication Gazette role. An HKeL report never satisfies
or substitutes for the due GLD report.

The acquisition worker now assembles that report over every source due in one
accepted periodic cycle, reads each exact report version back, and writes the
cycle report last. Its exact Primary Vault binding enters the V1 Coverage Status
Manifest. Missing or failed `RELEASE_BLOCKING` roles, policy/version drift,
duplicate ambiguous accounting, or an incomplete binding prevent the V1-specific
Promotion Manifest freeze. Real candidate-flow integration remains later
HKV1-3/HKV1-8 work.
