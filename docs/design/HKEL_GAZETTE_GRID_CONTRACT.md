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
upper bound only, and re-read `lastPage` on every page because it can move while
paging.

Twenty `pkValues` were returned for `pageSize: 20`, so the page size is honoured.

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

## 5. What this does not settle

- whether `lastPage` is stable enough to define completeness, or whether a
  date-bounded query is needed to make a run reproducible

Settled since this was written: the project owner decided on 2026-08-19 to assert
`JS_S=true` and `BR=Chrome`, recorded in `CAPABILITY_CLAIM` with its own note that
the values are asserted rather than measured. `POST` support went to a separate
`exchange` surface on the proxied transport rather than into
`OfficialHttpConnector`, which stays `GET`/`HEAD` so the inert evidence path is
unchanged.

The contract is complete and implemented in
`asklegal_source_connectors.hkel_gazette`. What remains is integration: the
acquisition worker does not yet enumerate the register and fetch the addressed
PDFs through the inert connector, and the completeness question above is
unanswered, so the role stays disabled.
