# Cross-cutting contract foundation

This package is the implementation-neutral machine contract for the legal-
database pipeline's shared domain. It does not select an application runtime,
database, cloud activation mechanism, model, source, legal coverage, reviewer
policy, threshold, retention period, or other deferred product value.

The package contains:

- strict JSON Schema Draft 2020-12 contracts;
- closed identity, reference, result, reason, lifecycle, failure, review, and
  capability and effect-type catalogues;
- closed-world state-transition definitions;
- a complete inventory of the accepted cross-cutting domain objects;
- synthetic positive and failure fixtures with exact expected results; and
- an exact file inventory in `package-manifest.json`.

Package version 1.2.0 adds the normative Command Envelope, Command Result,
Effect Intent, and Effect Receipt contracts. Replay and transport resolution
remain separate from immutable business results.

Package version 1.3.0 adds the normative M4 Connector Request, Watcher Result,
Scraper Result, Vault Object Receipt, Evidence Object, Evidence Package, and
Acquisition Outcome contracts. Only an exact complete primary-and-recovery
manifest can make a Source Snapshot eligible for legal processing.

Package version 1.4.0 adds the normative M5 executable Source Rulebook Package,
scope activation, Rule Execution Result, bounded Semantic Task Request and
Decision, and candidate-artifact contracts. Package conformance never activates
a scope, unknown or ambiguous rules fail closed, and model output remains
bounded evidence-derived judgment rather than source evidence or final text.

Package version 1.5.0 adds the normative M6 frozen Proposal Package Manifest
and exact Embedding Profile, Request, and Receipt. Proposal bytes are
manifest-last and immutable; embedding requests bind only `metadata.text` and
the complete exact profile; successful receipts expose hashes and accounting,
not raw vectors or provider authority.

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
