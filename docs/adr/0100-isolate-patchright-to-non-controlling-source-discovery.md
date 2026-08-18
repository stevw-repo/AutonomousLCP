# ADR 0100: Isolate Patchright to non-controlling source discovery

- Status: Accepted
- Date: 2026-08-18

## Context

Several official Hong Kong source products expose stable legal documents or
catalogue APIs only after a JavaScript client has completed a browser handshake.
The original M4 rule prohibited executing active source content because source
bytes must never gain authority over the acquisition worker, evidence vault,
legal interpretation, or approval state.

Direct inert HTTP remains the safest acquisition path. It cannot, by itself,
discover every locator and request contract used by these browser products.
The user therefore selected Patchright for browser-backed source discovery.

## Decision

Patchright `1.62.1` is an exact dependency of the acquisition worker, the only
application that owns external-source reads. It may execute official publisher
JavaScript only in an ephemeral, credential-free discovery session governed by
an exact endpoint policy.

This is a narrow exception to the original M4 active-content rule. Patchright
output is never controlling source evidence and can return only
`DISCOVERY_SIGNAL_CAPTURED`. It cannot prove source completeness, legal text,
legal status, no change, or eligibility for processing. Any discovered legal
document or API response must be fetched again through an admitted inert
connector and preserved through the ordinary manifest-last evidence flow.

Each Patchright policy requires:

- one exact registered HTTPS endpoint host, with certificate validation and no
  cross-host expansion;
- an ephemeral headless Chromium context with no persistent profile, ambient
  credential, accepted download, or service worker;
- `GET` and `HEAD` by default, with any `POST` limited to an exact reviewed
  same-host path;
- bounded time, rendered bytes, and observed-request count;
- no WebSocket or EventSource request;
- no retained headers, cookies, request bodies, query strings, or fragments;
  and
- a sanitized deterministic request-map summary instead of executable rendered
  HTML as the connector result.

Patchright must not solve or evade a CAPTCHA, defeat an access control, accept
publisher terms without an authorized source-specific contract, authenticate,
or create a durable publisher-side session. A challenge, unsupported TLS
configuration, unexpected redirect, or undeclared request remains a visible
technical blocker.

The first reviewed policies cover the NPC National Laws Database application
and HKeL Gazette discovery handshake. The NPC application is operationally
enabled at its observed stable `/index` route. HKeL Gazette remains blocked
until the `/grid` request, pagination, completeness, and artifact-locator
contracts are exact.

## Consequences

M4 evidence capture still never executes active source content. The acquisition
worker now has a separate untrusted discovery compartment that does. Tests must
prove host and method denial, exact optional POST paths, ephemeral cleanup,
sanitization, size bounds, and the inability to convert browser output into
source evidence.

This decision adds a large browser dependency and a separately installed
Chromium runtime. Both must be pinned, supply-chain checked, included in image
inputs, and re-proved on the Ubuntu V1 host before deployment admission.
