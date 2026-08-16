# Cross-cutting contract foundation

This package is the implementation-neutral machine contract for the legal-
database pipeline's shared domain. It does not select an application runtime,
database, cloud activation mechanism, model, source, legal coverage, reviewer
policy, threshold, retention period, or other deferred product value.

The package contains:

- strict JSON Schema Draft 2020-12 contracts;
- closed identity, reference, result, reason, lifecycle, failure, review, and
  capability catalogues;
- closed-world state-transition definitions;
- a complete inventory of the accepted cross-cutting domain objects;
- synthetic positive and failure fixtures with exact expected results; and
- an exact file inventory in `package-manifest.json`.

`foundation-status.json` preserves the historical ADR 0088 foundation
boundary: at that checkpoint the production stack and listed product policies
were undecided, every operational capability was disabled, and external
effects were `NONE`. Later accepted ADRs and versioned contract amendments do
not rewrite that historical artifact.

All normative JSON is I-JSON. Canonical JSON uses RFC 8785 JCS and UTF-8.
Fingerprints are lowercase `sha256:<64-hex>`. Domain identity is always
register-issued and never derived from a fingerprint or source locator.

Run the offline validator from the repository root:

```sh
node tools/validate-contracts.mjs
```

Validation performs no network or provider access and no production action.
The local Node.js runtime is validation tooling only; it does not constrain the
future production stack.
