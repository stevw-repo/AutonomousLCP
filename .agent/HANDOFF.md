# Where the project stands — 2026-08-20

Read this first. It is short on purpose.

`WORKING_STATE.md` is the full record, but it is now 2,500 lines of session
diary. Do not start there. `CONTEXT.md` is the glossary, `DECISIONS.md` the
decision log, `ROADMAP.md` the plan — and see section 4, because the roadmap is
currently behind reality.

When this file stops matching the system, correct it or delete it. A handoff that
lies is worse than no handoff.

---

## 1. Where to stand

```
/home/docpro/Desktop/Ask.Legal Database/AskLegal-LegalDBPipeline
```

Host `docpro-MS-7D99`, Ubuntu 24.04.4 LTS, x86-64. Branch **`main`**.

Four facts that waste an hour if you do not know them:

- **Docker needs `sg docker -c '...'`.** The login session predates the group
  change, so a bare `docker` call fails on the socket.
- **`uv` and `node` live in `~/.local/bin`**, which is not on `PATH` by default.
- **The agent has no `sudo` here and has never taken any.** Anything needing root
  is the user's step.
- **`demo/expo-source-transformation` is a disposable presentation branch.** It
  is never merged. `v1-poc-runtime-proven` is old history, 26 commits behind.

---

## 2. What is true right now — all of this was run on 2026-08-20

```sh
export PATH="$HOME/.local/bin:$PATH"
python3 -m tools.dev_test --uv ~/.local/bin/uv --node ~/.local/bin/node
```

| Check | Result |
|---|---|
| Full developer suite | 771 passed, 4 skipped, 27.6s |
| `asklegal.target` | enabled and active |
| Units | 14 services running, plus `asklegal-networks` (exited, by design) |
| Composite admission gate | `V1_POC_NOT_ADMITTED` — 14 components, 8 static contracts valid, 14 blockers |
| Vault disk `/srv/asklegal` | 11 GB used of 3.6 TB |

```sh
systemctl list-units 'asklegal*' --all --no-pager
sg docker -c "docker ps --format '{{.Names}}\t{{.Status}}'" | sort
```

---

## 3. What the system actually does

- **It runs under systemd and survives a reboot.** Not hand-started containers
  any more. The first real root run found three defects — a missing runtime
  directory, SQL Server needing `NET_BIND_SERVICE` to exec its own binary, and
  root lacking `CAP_CHOWN` to place credentials. All fixed in the templates.
- **Three external providers work**, each proved from inside the owning worker
  through its own egress proxy: Azure embeddings, Azure `gpt-5.4` inference, and
  Pinecone writes to `testing-index-1`. All speak REST from the standard library;
  neither provider SDK is in the pinned wheelhouse.
- **One document went the whole way**: live Hong Kong endpoint → Primary vault
  under Object Lock with verified read-back → analysed by the real model →
  embedded → written to Pinecone with retrieval verified.
- **The model refused to guess.** Handed a legislation index instead of
  legislative text, it returned `INSUFFICIENT_EVIDENCE` and said why.
- **The gazette register is captured**: 7,274 PDFs for 2000–2026, 9.7 GB, 95.2%
  retention, plus a listing manifest recording the 370 entries the publisher
  hosts no file for.

The rule that shapes everything: **an application may not create work for another
application.** The register's `commit_command_v1` rejects it and the scheduler
bindings block it from the other side. One narrow exception was authorised — the
control plane alone may reach a second hub — and that is what makes the
three-stage chain expressible at all.

---

## 4. Where the records are wrong — fix these before trusting them

1. **`ROADMAP.md` is stale.** Byte-identical to its 2026-08-19 version. It still
   lists real model, embedding and Pinecone operation as `NOT STARTED`. That was
   true on the 19th. It is not true now. `CONTEXT.md` and `DECISIONS.md` are
   likewise untouched since then.
2. **The running images are older than the source.** The acquisition worker's
   `hkel_gazette.py` matches commit `e261621` — three behind `main`. The live-PDF
   session fix and the client retry are not deployed. Re-running
   `infrastructure/poc/ROOT_SETUP.sh` reconciles it. That needs root.
3. **`infrastructure/poc/v1_admission_gate.json` still declares
   `MODEL_AND_EMBEDDING_ADMISSION` and `PINECONE_ADMISSION` as `NOT_STARTED`.**
   Defensible — formal admission means a deployment profile and an evaluation,
   not one working call — but nobody has revisited it since those calls became
   real.
4. **Two containers run outside systemd**: `acq-batch` and `cp-test`. Leftovers.

---

## 5. Open work, in the order worth doing it

**A live correctness bug, first.** The Pinecone write sends two metadata keys,
`text` and `content_fingerprint`. ADR 0078 defines the payload as a closed object
of six. So `authority_note` never reaches the index: a reconstructed provision
comes back looking official, and a proposition the Court of Final Appeal refused
to follow comes back unqualified. The fields are dropped in two places — the
adapter in `packages/promotion/src/asklegal_promotion/remote.py` and the durable
task payload between embed and upsert. A fix exists on the demo branch; it is
re-derived on `main`, never merged across.

Then, roughly in order:

- **Token measurement** counts UTF-8 bytes against a ceiling the profile pins to
  a real tokenizer. Matters most for Traditional Chinese, at three bytes a
  character. Fixing it needs `tiktoken`, which is not in the offline wheelhouse.
- **The egress proxy is a convention, not a boundary.** From a worker on a
  routable egress network, the open internet was reached directly. Needs host
  firewall rules or a dual-homed proxy.
- **`asklegal-register` is a shared bridge.** Six containers on it can reach each
  other regardless of what they declare.
- **Hong Kong sources**: five roles configured, five partial, four blocked. The
  blockers are a locator-producing search step, `POST` support in the connector,
  a client-capability assertion that is the owner's decision, and NPC's failing
  TLS handshake.
- **Large archives time out.** The biggest `PAST-DATA` sets exceed the 600-second
  orchestration ceiling. Raise it or capture them overnight.
- **Rotate `sa-password` and `app-password`.** They have sat in plain files in
  `var/run/` across several sessions.

Nothing pre-2000 is captured, deliberately: those gazettes are scanned images
with no fonts and need OCR before the pipeline can read a word of them.

---

## 6. Traps that have already cost time

- **Do not run `ruff format` or `ruff check --fix`.** It rewrites `except (A, B):`
  into Python 3.14-only syntax, which the host's system Python 3.12 cannot parse.
  It has broken the tree twice. Fix lint findings by hand.
- **Generated files fail the suite if hand-edited.** `infrastructure/poc/units/`
  and `infrastructure/poc/provisioning/` are re-rendered and compared. Change the
  contract and re-render; never edit the output.
- **Credential files must be exactly mode 0400 owned by the runtime uid.**
  Anything else fails in a way that looks unrelated.
- **Recreating the Pinecone index breaks egress.** The proxy config pins the
  current data-plane host, which Pinecone assigns at creation. The symptom is a
  403 that reads like a provider outage.
- **`totalRecords` from the HKeL grid is a trap.** It reported 100 against 1,415
  pages. Walk the pages and count what arrives.

---

## 7. How to report

Plain words, short sentences, and keep the honesty. Say what was proved, say what
was not, and never let a contract validating stand in for a thing working.
Continue in dependency order without routine confirmation. Commit, push, deploy,
destructive work, production effects, and external account changes are stop gates.

`AGENTS.md` carries a standing instruction on loosening over-strict rules — read
it before deciding a rule is load-bearing. Four rules are named there that must
never be loosened, each because it already caught a real defect.
