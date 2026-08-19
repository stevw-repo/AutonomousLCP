# Handoff — 2026-08-19, after wiring the inference credential

Read this first, then `WORKING_STATE.md` for the full record. `CONTEXT.md` is the
glossary and `DECISIONS.md` the decision log; neither changed today.

This file describes one session's state. When it stops matching reality, trust
`WORKING_STATE.md` and delete this.

---

## 1. Where to stand up

```
/home/docpro/Desktop/Ask.Legal Database/AskLegal-LegalDBPipeline
```

Host `docpro-MS-7D99`, Ubuntu 24.04.4 LTS, x86-64. **This machine, not the Mac.**

Three environment facts that waste an hour if you do not know them:

- **Docker needs `sg docker -c '...'`.** `docpro` is in the `docker` group in
  `/etc/group`, but the login session predates that change, so a bare `docker`
  call fails with a socket permission error. `tools/v1_poc_build_images.py`
  already wraps itself this way.
- **`uv` and `node` are in `~/.local/bin`, which is not on `PATH` by default.**
- **The agent has no `sudo` here and has never taken any.** Anything needing root
  is the user's step. Do not try to acquire it.

Run the whole suite with the documented command:

```sh
export PATH="$HOME/.local/bin:$PATH"
python3 -m tools.dev_test --uv ~/.local/bin/uv --node ~/.local/bin/node
```

Current result: **727 passed, 4 skipped, 0 failed.**

---

## 2. What is running right now

Fourteen containers, started by hand, on `/srv/asklegal` (the 3.6 TB SATA disk).

| Group | Containers |
|---|---|
| Register | `sql-server` |
| Vaults | `vault-primary`, `vault-recovery` |
| Schedulers | `dts-general`, `dts-promotion` |
| Telemetry | `otel-collector` |
| Egress | `egress-source`, `egress-model`, `egress-promotion` |
| Applications | `review-api`, `control-plane`, and the three workers |

`legal-processing-worker` runs `asklegal/legal-processing-worker:model-cred`; the
other four run `:tls-c`. That is deliberate — only the processing worker needed
the rebuild, and the records name the image that actually ran.

All five applications report **READY** on every declared dependency.

**None of this survives a reboot.** They are plain `docker run` containers, not
units. If they are gone when you arrive, that is why — see section 4.

Check with:

```sh
sg docker -c "docker ps --format '{{.Names}}\t{{.Status}}'" | sort
```

Helper scripts in ignored `var/run/` recreate them:

- `run_app.sh <service> <uid> <image> <alias> <net1,net2,...> <python-module>` —
  creates the container, attaches **every** network with its alias, then starts.
  The two-step order matters: attaching a network after start races the readiness
  gate, and that race was hit.
- `stage_credentials.sh <service> <uid> <staging-dir>` (with `IMAGE=` set) — copies
  credentials into a named Docker volume owned by the runtime uid at mode 0400,
  which is what the application loader demands. The host staging directory cannot
  express that without root, so the copy runs as root *inside* Docker.

---

## 3. The user's decisions, and what is still open

The user supplied real credentials on 2026-08-19 and all three were smoke-tested
live, each through its own egress proxy, from inside the owning worker's image.

| Credential | State |
|---|---|
| Azure OpenAI embedding, `text-embedding-3-small` | Works. 1536 dimensions. Loaded into the running promotion worker. |
| Pinecone, index `testing-index-1` | Works. Dimension 1536, cosine, serverless AWS `us-east-1`, 0 vectors. Loaded. |
| Azure OpenAI inference, `gpt-5.4` | Works, **but has nowhere to live.** See below. |

Azure resource: `asklegal-eastus-testing.openai.azure.com`. Plaintext credentials
sit in ignored `var/run/staging/` and `var/run/creds-*/`.

Still the user's call: whether to authorise Pinecone writes
(`real_write_authorized` is still `false`, so today's proof was list-and-describe
only), the deployment profile and evaluation behind
`MODEL_AND_EMBEDDING_ADMISSION`, and legal sign-off on Hong Kong content.

---

## 4. The obvious next four things

### 4.1 ~~Give the inference credential a home~~ — done, and executed

`model-provider` is now declared in all four contracts and read by
`load_v1_infrastructure`. The processing image was rebuilt as `:model-cred`, the
credential volume restaged with four files, and the container recreated and
observed **READY**. `service_runtime_commands.json` was only updated after that
run, so its proof note stays true.

Note for the next change of this shape: the four places named below were not all
of them. Two validators cross-check the credential lists and two tests pin the
credential totals. `WORKING_STATE.md` has the full list.

**The credential can be loaded. Nothing calls with it** — that is 4.3.

### 4.2 Install the startup files — needs the user, not you

`infrastructure/poc/units/` holds 33 generated files. Nothing has been installed
or run as root, so they are rendered and tested, **not proved on the host**.

The user's sequence, in this order:

```sh
sudo ./infrastructure/poc/units/80-install.sh
sudo ./infrastructure/poc/units/70-credentials.sh var/run/staging
sudo systemctl enable --now asklegal.target
```

`80-install.sh` deliberately does not enable anything. `70-credentials.sh` seals
every credential with `systemd-creds encrypt --with-key=host+tpm2`.

**Tell the user to rotate the SQL passwords when they do this.** `sa-password`
and `app-password` have sat in plain files in `var/run/` since the register work
and have been read by more than one session.

**Expect the first boot to find problems.** The units are correct on paper —
`systemd-analyze verify` accepts them and every generated script parses — but no
unit has ever started a container. Treat the first `enable --now` as a test.

### 4.3 Build the provider adapters — the real work

There is **no Azure OpenAI adapter and no Pinecone adapter** in this workspace:
no package, no client, no call site. Today's smoke tests were standalone scripts,
not application code paths. `packages/` has `processing` and `promotion`, but
neither reaches a provider.

Until this exists, working credentials and a correct network path buy nothing.
This is the largest remaining piece of V1.

### 4.4 Exercise the schedulers

Nothing has run through either task hub: no orchestration, no claimed work, no
duplicate or restart behaviour, no fencing, no SQL reconciliation, and no
replacement-from-checkpoint report after a deliberate emulator loss. The
schedulers are proved reachable and correctly configured, and nothing more.

---

## 5. Two gaps that are proved, not theorised — do not paper over these

**The egress proxy is a convention, not a boundary.** From inside a worker on a
routable egress network, `example.com` and `pypi.org` were reached **directly**,
ignoring the proxy. Docker cannot express "only via the proxy" on a routable
network. Closing it needs host `DOCKER-USER` firewall rules or a dual-homed proxy
with the worker on an internal network. Neither is applied.

**`asklegal-register` is a shared segment, not a point-to-point link.** Six
containers sit on it, so every worker can also reach `review-api:8001` and
`control-plane:8000`, which none of them declares. Isolation is correct per
*dependency* — no worker reaches another's scheduler, an undeclared vault, or
another profile's proxy — but any Docker bridge with more than two members lets
all its members talk. The destination table is finer-grained than the network
layer enforcing it.

Smaller, but real:

- **No application emits telemetry.** `asklegal-observability` contains no OTLP
  export. The collector's only exporter is `debug`, to the journal. The TELEMETRY
  dependency is a reachability requirement and nothing else.
- **The `review-api` and `review-client` credentials are read and dropped.**
  Review is served with no client authentication; Control Plane holds a client
  credential it never presents.
- **Both vaults share one root credential** across every application. No
  per-application vault identity exists.
- **The five application images are local tags, not digests**, so `ARTIFACT_PINS`
  stays open and the rendered units name a tag.
- **Recreating the Pinecone index breaks egress.** Pinecone assigns the
  data-plane host at creation; `squid-promotion.conf` pins the exact current one.
  The symptom is a 403 from the proxy, which reads like a Pinecone outage.

---

## 6. Traps that have already cost time

- **`ruff format` writes Python 3.14-only syntax.** It has twice rewritten
  `except (A, B):` into PEP 758's unparenthesised form. Eight library files carry
  it, so the tree cannot be imported by the host's system Python 3.12. The
  existing guard, `tools/tests/test_system_python_entrypoints.py`, covers static
  entrypoints only. **Do not run `ruff format` or `ruff check --fix`** — fix lint
  findings by hand.
- **Generated files fail the suite if hand-edited.** `infrastructure/poc/units/`
  and `infrastructure/poc/provisioning/` are re-rendered and compared by
  `tools/dev_test.py`. Change the contract and re-render; never edit the output.
- **The image build used to ship stale code.** It assembled its context from
  wheels left on disk, so a source change produced a new tag containing none of
  it — and reported success. Fixed: it now rebuilds every workspace distribution
  with the locked uv first. If a change seems not to take effect, verify inside
  the image before doubting the source.
- **Credential files must be exactly mode 0400 owned by the runtime uid.**
  Anything else gives `CREDENTIAL_MODE_INVALID` or
  `CREDENTIAL_DIRECTORY_INVALID`, which look like unrelated failures.
- **A failure inside a serve task used to be invisible.** Both ASGI apps awaited
  only the shutdown event, so a server that failed to start left the process up
  and "READY" with nothing listening. Fixed in both; if you add a third ASGI
  service, copy the pattern.

---

## 7. Repository state

Everything is committed and pushed. `main` is level with `origin/main` at
`46af9da`, and the working tree is clean.

Recent commits: `46af9da` (the inference credential given a home, executed and
proved), `3978674` (previous session record and this handoff), `ef48338` (the V1
POC run and the rendered startup files).

Ignored runtime material under `var/` is excluded and nothing under it is
tracked. The plaintext credentials in `var/run/staging/` and `var/run/creds-*/`
have never been committed.

The composite verdict is unchanged and should stay that way:
**`V1_POC_NOT_ADMITTED`.** Static contracts passing is not readiness.

## 8. How the user wants to be talked to

Plain words, short sentences, no jargon — and keep the honesty. Say what was
proved, say what was not, and never let a contract validating stand in for a
thing working. Every claim in this file corresponds to something that was
executed and observed; if you cannot say that of your own work, say so instead.

The standing instruction is to continue in dependency order without routine
confirmation, and to stop only for a material user decision or a new permission.
Commit, push, deployment, destructive work, production effects, and external
account changes remain explicit stop gates.
