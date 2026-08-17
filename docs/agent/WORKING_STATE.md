# AskLegal Legal Database Pipeline — Working State

Updated: 2026-08-16

## Current outcome

The user authorized M7 with the instruction "M7." The complete offline local-
synthetic milestone is **COMPLETE** against
`docs/design/M7_END_TO_END_CONFORMANCE_PLAN.md`.

M1 through M7 now pass locally. The user subsequently authorized committing
and pushing the complete accumulated M2–M7 implementation to `main`. The
commit scope is the full project change set above pushed commit `88f8e92`;
ignored local runtime evidence under `var/` is excluded.

M8 remains separately gated. No real source, credential, Azure resource,
Azure OpenAI/model or embedding call, Pinecone target, provider backup,
Ask.Legal route/slot, deployment, corpus publication, or production effect was
accessed or changed. Ask.Legal admin-portal integration remains deferred; M7
stabilizes the Review API boundary it will later consume.

## Completed M7 implementation

### Stable offline conformance interface

`asklegal-local` is exposed as a second console entry point of the existing
control-plane distribution and delegates to repository tooling in
`tools/local_conformance.py`. It is not a sixth deployed application, and the
closed 5-application/14-package architecture graph is unchanged.

The accepted interfaces are implemented:

```text
uv run --frozen asklegal-local reset --exact-test-state
uv run --frozen asklegal-local prove --scenario <E2E-001..E2E-032>
uv run --frozen asklegal-local prove --all
```

Reset validates the exact resolved ignored `var/local-conformance` path and its
marker before deletion. The runner denies DNS/socket access, binds exact locks,
contract/protocol/policy inputs, deterministic clocks/IDs/jitter, and one
independent expected result/fact/effect entry for every scenario.

### Complete flow and scenario matrix

`E2E-001` plans and schedules through the versioned Control API, then connects
the actual local acquisition service, primary/recovery vault fakes, ZZZ
activation/rule engine, candidate renderer, Corpus Release/DSI/
coverage/promotion builders, frozen proposal package, Review HTTP API and
loaded minimal browser client, named-human Approval, fake embedding/replacement
target/backup/routing, reverse-swap, and exact same-lineage recovery.

`E2E-002` through `E2E-032` prove supported no-change, watcher false positive,
duplicate/replay, restart, lost acknowledgement, command conflict, stale
version/fencing, overlap, cancellation before and after promotion, incomplete/
hostile/unknown source handling, non-total rules, carry-forward, withholding,
quarantine re-entry/recurrence, stale and app-token review rejection, revoked/
consumed Approval, vector/target/cost/recovery/base/coverage failures,
post-cutover rollback, digest-verified Management Register recovery, broad-
deletion denial, and ZZZ environment containment.

`prove --all` runs the complete catalogue twice under clean path-distinct roots
and compares both authoritative report bytes and every generated artifact's
relative path, byte size, and SHA-256 digest. The final report statement is
exactly `local synthetic platform proved`; its fingerprint is
`sha256:1371eca6e75e380f8a754e665850e3839aa7e2ff9de4b86e18c5061ae026d8ae`.

### Reporting and Review projection support

`asklegal_reporting` now owns strict immutable scenario and complete-report
values. An incomplete catalogue, duplicate identity, count/result drift, or
fingerprint drift fails closed. `LocalReviewProjectionStore` accepts explicit
frozen proposals and a snapshot for M7 composition while preserving its M3
defaults.

## Validation performed

All application bytes and effects were synthetic/local:

- stable exact uv CLI reset and all-scenario proof: **32/32 scenarios passed in
  both path-distinct runs**;
- focused M7/reporting suite: **7 passed**;
- exact developer command and complete ordinary suite: **239 passed, 4 skipped
  in 10.63 seconds**;
- repository-wide Ruff: PASS;
- strict Pyright: **0 errors, 0 warnings, 0 information messages**;
- Python boundary checker: PASS across **114 files** with the same eight exact
  reviewed exceptions and no M7 exception;
- architecture proof: PASS with 5 applications, 14 packages, 80 dependency
  edges, 31 capability ports, and unchanged fingerprint
  `sha256:5253bae3e841072f8f823a1298344404bbec569f7fa3fd7b87db8f18d5ca168c`;
- independent Node contract validator: PASS with unchanged package fingerprint
  `sha256:7bd2858bd0099271bc5be1e8d5c380521d81fb15bee8a4110de8fe6629d3094e`;
  and
- complete network-disabled package proof: two byte-identical builds and clean
  installs for all 19 wheels plus byte-identical container inputs.

Current reproducibility fingerprints include:

- unchanged uv lock:
  `cf0e9eb5f7c6aa14a7ee79dd55d1468a5a56cb95c5f1daf05a06b807e682ce92`;
- application-runtime wheel:
  `09d9dff744446b3ad1ee4b3253304dbd49c852ac0494d0e2637beb50ae4cd73e`;
- control-plane wheel:
  `8d6d0c0c2cec15ed4ca87a91dcbc0c43ba210da71b988fd9fcaebe28f0865b7f`;
- reporting wheel:
  `3e663f318e12c5986288a3b6b45d7cb836b04b972d8c8cabfb6eadcb33c127cb`;
  and
- package container-input archive:
  `a6ca61c29382a4b7fb8c1b2ccb327ad6dd0ad3b080e77b80db2bc5d10aa6119c`.

## M7 files changed

M7 changes are concentrated in:

- `tools/local_conformance.py` and `tools/tests/test_m7_end_to_end.py`;
- `packages/reporting/src/asklegal_reporting/local_conformance.py`, its export,
  and tests;
- `apps/control-plane/src/asklegal_control_plane/local_cli.py` and the
  `asklegal-local` entry point;
- explicit local Review projection injection support;
- root Ruff policy and README reproduction instructions; and
- `AGENTS.md` plus all canonical continuity files.

The ignored `var/local-conformance/` tree contains only disposable generated
synthetic proof state and is not a repository artifact.

## Decisions and open questions

No new product or production architecture choice was required for M7. The
implementation follows the accepted 32-scenario plan and existing M3–M6
boundaries.

There is no remaining M7 implementation blocker or decision. Real Hong Kong
packages and every exact external/platform admission value remain open evidence
work, not defaults inferred from local success.

## Current host prerequisite

The exact `uv 0.12.5` required by the repository is not installed on this
host's `PATH`. At the user's request, the verified temporary installation at
`/tmp/asklegal-m6-uv` was removed on 2026-08-16 and its absence was verified.
The recommended durable developer installation is the official versioned uv
0.12.5 standalone installer targeting the normal user executable directory,
with installer PATH mutation disabled. `/home/stevw-s14/.local/bin` already
exists and is already on this host's `PATH`, so no shell-startup edit is needed.
Until that durable installation is performed, repository commands requiring
uv cannot run from a fresh shell.

## Authorization boundary and exact next step

M7 completion grants no M8 or external authority. The next capability milestone
is M8, the Azure non-production platform, only if the user explicitly
authorizes it. Before creating cloud resources, M8 must settle and measure the
exact region, capacity, retention, recovery, security, identity, network,
observability, service-level, and cost profiles required by its accepted exit
gate.

The user explicitly confirmed that the private
`https://github.com/stevw-repo/AskLegal-LegalDBPipeline.git` remote is the
approved destination and authorized synchronizing the complete committed
M2–M7 change set from `main` to `origin/main`. That repository push is the only
authorized remote action. No deployment, external message, cloud mutation, or
other remote-system action was performed.
