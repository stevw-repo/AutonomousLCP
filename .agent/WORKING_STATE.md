# AskLegal Legal Database Pipeline — Working State

Updated: 2026-08-21 — docpro-MS-7D99 (Ubuntu 24.04.4 LTS, x86-64), branch `main`

**Starting a new session? Read `.agent/HANDOFF.md` first.** This file is now
2,500 lines of session diary and is the wrong place to start. The handoff is the
short orientation: where to stand, what was verified today, what the system
actually does, where these records had drifted, and the traps that have already
cost time.

## Latest session — V1 infrastructure push

The user asked to continue to V1 without stopping. This session found and fixed
a broken commit, then closed seven V1 blockers. Nothing was committed or pushed;
no external account, credential, model, Pinecone target, or production system was
touched. The only network use was read-only image resolution and pulling the
pinned base image plus the locked wheels.

**Repaired first.** Commit `b38c184` was broken. `ruff format` had rewritten an
`except (A, B, C):` into PEP 758's unparenthesised form, which is valid under the
pinned Python 3.14.7 but a syntax error under the host's system Python 3.12 that
the documented developer command uses. Every static V1 gate and the whole suite
failed to import; the commit was made without the suite passing. The construct is
gone and `tools/tests/test_system_python_entrypoints.py` now parses every static
entrypoint at Python 3.12 grammar so it cannot recur silently.

**Closed this session:**

- `HOST_PACKAGE_LOCKS` — nine host packages locked to their exact installed
  versions, read read-only from `dpkg-query`; the collector now reports installed
  versions and the checker requires them to equal the locks. The observed-network
  fact was added at the same time: the ten declared subnets must exist exactly and
  must not overlap any other host network.
- `PRIVATE_SUBNET_SELECTION` propagation — the unit graph now owns a third
  bootstrap one-shot, `asklegal-networks.service`, and ten internal networks whose
  subnets are checked against the host allocation rather than copied.
- `COLLISION_FREE_UID_GID_ALLOCATION` and `CONTAINER_UID_GID_MAPPING` — ten host
  accounts at 3000-3009, five container-only reservations at 3010-3014, SQL at its
  image-defined 10001, all verified free on this machine, plus a 16-entry container
  identity map that forbids root, shared, and split identities.
- `BASE_IMAGE_DIGEST` — `python@sha256:d6e0850f…` pinned, pulled, and verified as
  CPython 3.14.7 on Debian 13 trixie, x86-64, glibc 2.41.
- `THIRD_PARTY_WHEELHOUSE` — 59 linux/amd64 cp314 wheels for all five closures,
  downloaded inside the pinned base image with hash checking, recorded in
  `infrastructure/poc/application_wheelhouse.json`, and proved to install with
  `--network none`. This also clears the old `s3transfer 0.19.2` offline failure
  that had stopped the two-path package proof. The wheels stay in ignored `var/`.
- `LOGICAL_DESTINATION_RESOLUTION` — all 25 destinations bound to exact host,
  port, scheme, and shared network, derived from the topology by the checker.
- `RUNTIME_CONFIGURATION_ADAPTER`, `REAL_ADAPTER_COMPOSITION`, `RUNTIME_COMMANDS`,
  `BOUNDED_READINESS_PROBES` — all five applications now have a real continuous
  V1 entrypoint (`--serve`) that loads its own credentials, composes only its own
  adapters, proves every declared dependency through the bounded gate, serves or
  works, and shuts down cooperatively on `SIGTERM`. Missing credentials produce a
  closed `NOT_READY` exit, not a traceback.
- `OCI_BUILD_DEFINITION` — all five images build offline from pinned inputs and
  run as their allocated non-root UIDs.

**Readiness probes are honest about what they prove.** SQL uses the existing
non-mutating `SELECT 1`; each vault reads versioning and Object Lock. The
scheduler emulators, collector, and egress proxies get a bounded TCP connect,
because none of them publishes a non-mutating health operation and inventing one
would be a false signal. Review gets a verified TLS handshake. Every adapter
failure is normalised to one safe result carrying no provider detail.

**Two builds, byte-identical content.** Building twice from a cleared builder
cache produced identical installed trees for all five images. The Docker image
ids differ because Docker stamps a creation time into the image config; the
contract records `TWO_BUILDS_CONTENT_IDENTICAL` with `image_id_stability` set to
`NOT_CLAIMED`, and the checker rejects a stronger claim.

### Root provisioning scripts — generated 2026-08-18

`infrastructure/poc/provisioning/` holds seven generated scripts, rendered from
the contracts by `tools/v1_poc_render_provisioning.py`. They are never hand
edited: `tools/dev_test.py` re-renders and compares, so a manual change or an
unpropagated contract change fails the ordinary suite.

`provision.sh` runs steps 10-50. Every step honours `DRY_RUN=1`, uses
`set -euo pipefail`, is idempotent, and refuses to continue when an existing
account, group, or network does not match the contract exactly.

- **10-preflight** reads only. It was run for real on this host and passed:
  Ubuntu 24.04 x86-64, all nine locked packages at their exact versions, the
  4.0 TB disk present, TPM2 available, and all sixteen numeric identities free.
- **20-storage** moves the 4.0 TB disk from its desktop automount under `/media`
  to `/srv/asklegal` through `/etc/fstab` by UUID, backing up fstab first.
- **30-identities** creates the ten locked non-login accounts at their allocated
  numbers, the fourteen owned directories at `0750`, `/srv/asklegal/sql` owned by
  the image-defined `10001`, and root-owned `/etc/asklegal/tls`.
- **40-networks** creates the ten networks: seven internal, three routable.
- **50-journal-time** sets a persistent sealed journal and confirms time sync.
- **60-firewall** is deliberately **not** run by `provision.sh`. It adds one
  separate `inet asklegal` nftables table with an input default-deny policy,
  never touches the forward path (Docker owns that; overriding it would break
  every container network), requires `I_HAVE_CONSOLE_ACCESS=1`, and arms a
  dead-man revert that removes the rules unless confirmed.

**A topology bug was found and fixed while writing these.** The subnet work
earlier in the session had marked all ten networks `internal: true`. The accepted
topology marks the three egress networks routable, because the proxy on each one
has to reach its allowlisted destinations. Creating them internal would have
silently blocked all egress. The unit-input checker now derives isolation from
the topology instead of assuming it.

**A gap the scripts name rather than paper over.** The topology gives the three
workers outbound profiles of `OFFICIAL_SOURCE_ONLY`, `MODEL_PROVIDER_ONLY`, and
`PINECONE_AND_EMBEDDING_ONLY`. Docker cannot express that: on a routable network
every member can reach outside, not just the proxy. Closing it needs a decision —
fixed proxy addresses plus `DOCKER-USER` rules, or dual-homing each proxy so the
worker sits only on an internal network. Neither was applied.

### Certificates and the secret rule — 2026-08-19

The internal certificate authority is issued and verified. One authority signs
`sql-server`, `vault-primary`, `vault-recovery`, and `review-api`. Twelve checks
pass: each name completes a verified handshake, is rejected under a wrong
hostname, and is rejected when the authority is not trusted. SQL Server then
loaded its certificate and reported successful TLS initialisation with
`forceencryption = 1`. Private keys stay under the ignored `var/tls` tree and are
never printed; `tls_material.json` records only public facts and fingerprints.

Two real bugs were found and fixed on the way. The slim base image lacks the
Kerberos and `libltdl` libraries the bundled ODBC driver links against, so
`import mssql_python` succeeded while connecting failed — seven Debian packages
are now hash-pinned in `application_system_packages.json` and installed offline.
And a prepared `mssql.conf` must not be mounted read-only over
`/var/opt/mssql/mssql.conf`, because first-time setup writes its own
configuration there; TLS settings belong in a bootstrap step after the instance
exists.

**The 2026-08-18 SQL credential conclusion was wrong and is withdrawn.**
`MSSQL_SA_PASSWORD_FILE` does not set the SA password: two fresh instances of the
same image, same value, one by file and one by environment, gave a working login
only for the environment instance. The earlier proof inferred success from the
"ready for client connections" line and never authenticated.

**The user removed the file-only secret rule on 2026-08-19** and authorised
environment delivery for every credential the POC needs. The replacement rule
keeps encrypted-at-rest `systemd-creds` storage sealed to the TPM, still forbids
persistent plaintext files, and still forbids command arguments; only the last
hop changes. SQL is unblocked, the Versity exception is retired as no longer an
exception, and the exception mechanism stays implemented and tested against a
synthetic fixture. The five repository applications keep their working
file-based loader.

Residual risk, stated plainly: a service account can read its own credentials
from its process environment, and anything running as `docpro` can read every
container's environment through the Docker socket.

### Register slice — live 2026-08-19

SQL Server 2025 is running as a real service for the first time: network
`asklegal-register` as `sql-server`, uid 10001, data on the 4.0 TB disk at
`/srv/asklegal/sql`, internal certificate from `/etc/asklegal/tls/sql-server/`,
TLS 1.2 only, `forceencryption = 1`, password by environment from
`var/run/sa-password`.

Proved, not assumed: the application's own strict-TLS factory returns `SELECT 1`
with `encrypt_option = TRUE`; the same client without the internal CA is refused
for an unknown issuer; connecting by IP is refused for a hostname mismatch.

`HostNameInCertificate` turns out to be ignored under `Encrypt=Strict` —
validation is against the connection server name. The property holds, but the
factory's description of what enforces it needs correcting.

The certificates are installed at `/etc/asklegal/tls/`, root-owned, each key
`0640` to its own service group. The container is a plain `docker run`, not a
systemd unit, so it will not survive a reboot. Stop it with
`docker rm -f asklegal-sql-server`.

The slice is now complete. `AskLegalPocOperational` exists with snapshot
isolation on, both forward-only migration packages applied and re-applied with no
effect the second time, giving 17 tables and 10 procedures. All five application
principals exist, each a member of only its own role, and the set matches the
driver's allowed list exactly.

Least privilege is proved rather than assumed: as `asklegal_control_app`, a direct
`SELECT` on a register table fails with "invalid object name" and `CREATE TABLE`
fails with an explicit permission denial, while the login itself succeeds. All of
it over `Encrypt=Strict` through the internal CA.

Two traps found here. The migrations create their application users *without* a
login, so a deployment must drop and recreate each user `FOR LOGIN` and re-add its
role membership; `ALTER USER ... WITH LOGIN` cannot remap them. And the
application principal is `asklegal_legal_processing_app`, not
`asklegal_processing_app` — the driver, the migrations, and the runtime contract
all agree on the longer name, and a bootstrap script that guesses the short one
silently creates a stray principal.

Credentials currently live in `var/run/` as plain files: `sa-password` and
`app-password`. They are ignored by Git but are not yet encrypted at rest; that
arrives with the systemd units.

### Vault slice — live 2026-08-19

Both Versity gateways run as real services: `vault-primary` on
`asklegal-vault-primary` as uid 3008, `vault-recovery` on
`asklegal-vault-recovery` as uid 3009, each on HTTPS port 7070 with its own
certificate from `/etc/asklegal/tls/`, data on the 4.0 TB disk under
`/srv/asklegal/vault-*/{objects,versions,sidecar}`, root keys by environment.

Proved with the application's own locked Boto3 adapter, verifying TLS against the
internal CA, identically on both vaults:

- bucket created with Object Lock; versioning reports `Enabled`;
- an object written under `COMPLIANCE` retention with legal hold reports both
  back on read;
- deleting that locked object is refused with `AccessDenied`; and
- the bytes read back match what was written.

Evidence is confirmed on the SATA disk, not a container layer. Recovery remains
`LOGICALLY_SEPARATE_POC_RECOVERY`: both vaults share that one disk, so losing it
loses both, exactly as accepted.

Not yet done: manifest-last composition across the pair, primary-to-recovery
copying, corruption detection, and restart/recovery behaviour.

### Scheduler slice — live 2026-08-19

Both Durable Task Scheduler emulators run as real services: `dts-general` on
`asklegal-scheduler-general` as uid 3010 with task hubs `acquisition`, `control`,
and `legal-processing`; `dts-promotion` on `asklegal-scheduler-promotion` as uid
3011 with task hub `promotion`. Both listen on 8080 with no token and no TLS,
exactly as the accepted topology records: their authority rests entirely on
network isolation.

Proved with the application's own probe and settings factory: each application
reaches only its declared scheduler address, an unused port is refused, and the
settings resolve to the right service, the right single task hub, `MEMORY_ONLY`
persistence, and `REPLACEMENT_FROM_SAFE_CHECKPOINT`. Review is refused a
scheduler entirely, as it has no task hub.

Network isolation was checked rather than assumed. From the promotion network,
its own scheduler is reachable while the general scheduler, the register
database, and the primary vault are all unreachable. That is the least-privilege
boundary working at the network layer, not only in configuration.

Not yet done: orchestration through the hubs, duplicate and restart behaviour,
fencing, SQL reconciliation, and the replacement-from-checkpoint report after a
deliberate emulator loss.

### Telemetry, egress, and all five applications — live 2026-08-19

The whole V1 set now runs together: fourteen containers, the five supporting
services from earlier plus the collector, three egress proxies, and all five
applications, each proving its own dependencies before it serves.

**Telemetry.** The pinned collector runs as uid 3004 on `asklegal-telemetry`
with a read-only root filesystem and no capabilities. It is not only listening:
a real OTLP trace was exported over 4318 and travelled the whole pipeline, and
the collector reported one resource span and one span out of the debug exporter.
From the telemetry network the register, the vaults, and the schedulers are all
unreachable. Its configuration is `infrastructure/poc/config/otel-collector.yaml`
and its only exporter is `debug`, which writes to the journal; **no application
emits telemetry yet**, because `asklegal-observability` contains no OTLP export.
The TELEMETRY dependency is therefore a reachability requirement and nothing more.

**Egress.** Three pinned Squid instances run as uids 3012-3014. The source
profile permits exactly the nine official publishers bound in the Hong Kong
source register, over 443 only; a CONNECT to `example.com` or `pypi.org` is
refused with 403. The model and promotion profiles deny everything, because the
model provider, the Pinecone target, and the embedding provider are still the
user's decisions; the proxies run so the workers' declared dependency is
reachable while nothing can leave through them by accident.

**The proxy is a convention, not a boundary, and this was proved rather than
assumed.** From the source egress network a worker reached `example.com` and
`pypi.org` directly, ignoring the proxy entirely. The earlier note that Docker
cannot express `OFFICIAL_SOURCE_ONLY` on a routable network is confirmed live.
Closing it still needs host firewall rules or a dual-homed proxy.

**All five applications are ready against the real infrastructure.** Each loads
its own credentials, composes only its own adapters, and passes every declared
probe: Review on three, Control Plane on five including a verified TLS handshake
to Review, and the three workers on five or six each.

**Least privilege holds per dependency, with one measured exception.** From
inside each running application, every declared destination is reachable and
almost nothing else: no worker reaches another worker's scheduler, an undeclared
vault, or another profile's proxy. The exception is that all six members of
`asklegal-register` can reach each other, so every worker can also reach
`review-api:8001` and `control-plane:8000`, which none of them declares. A Docker
bridge with more than two members is a shared segment, not a point-to-point link;
the destination table is finer-grained than the network layer enforcing it.

### Three real defects found by running the applications

**Review served plain HTTP while Control Plane required TLS.** The topology puts
Review behind the internal authority and Control Plane proves it with
`TlsReachabilityProbe`, but `v1_service.py` never wired the issued certificate
into uvicorn. Control Plane could never have become ready. Review now serves its
own certificate: TLS 1.3, verified against the internal CA, refused without that
authority, and refused under a wrong hostname. Missing or unreadable server
material is a closed `NOT_READY` exit, not a traceback.

**A server that failed to start left the process running forever.** Both ASGI
applications created the serve task and then awaited only the shutdown event, so
a startup failure sat in the task while the event never fired: the container
reported healthy, the readiness line said READY, and nothing was listening. This
was observed, not theorised — a container ran forty seconds in exactly that
state. Both now wait on the server and the shutdown event together and exit
`FAILED` when the server stops first; the same deliberate failure now exits 2.

**The image build shipped stale code.** `v1_poc_build_images.py` assembled its
context from workspace wheels left on disk by an earlier session, so a source
change produced a new tag containing none of it. The change under test was simply
absent and the build reported success. It now rebuilds every workspace
distribution with the locked uv before assembling any context.

### Startup files — rendered 2026-08-19, not installed

`infrastructure/poc/units/` holds 33 generated files rendered from the contracts
by `tools/v1_poc_render_units.py`, on the same terms as the provisioning scripts:
`tools/dev_test.py` re-renders and compares, so a hand edit or an unpropagated
contract change fails the ordinary suite.

`infrastructure/poc/service_runtime_commands.json` supplies the value the unit
contract had left as `runtime_command_state: REQUIRED`. Every command in it was
executed on this host and reached its recorded state.

- Fourteen service units, one per proven service, plus `asklegal-networks.service`
  and an `asklegal.target` that starts or stops the whole POC together.
- Fourteen launchers. Each attaches every declared network **before** the process
  starts, because attaching after start races the readiness gate — that race was
  hit and is the reason the launcher exists at all.
- Hardening on every unit: `NoNewPrivileges`, `ProtectSystem=strict`,
  `ProtectHome`, `PrivateTmp`, an empty capability bounding set, and a container
  that drops all capabilities and runs as its allocated uid.
- `70-credentials.sh` seals every credential with `systemd-creds encrypt
  --with-key=host+tpm2`, so the sealed files are useless on any other machine.
- `80-install.sh` installs and deliberately does **not** enable.

Two credential shapes, both avoiding persistent plaintext and command arguments.
The five applications need a directory of 0400 files owned by their own runtime
uid, which `$CREDENTIALS_DIRECTORY` cannot be because systemd owns it as root, so
each launcher copies them onto `/run` with that exact ownership. The
infrastructure images take theirs from the environment: the launcher exports the
value and passes the bare variable name to `docker`, so no secret reaches argv.

`systemd-analyze verify` accepts the units, and all seventeen generated scripts
parse. **None of this has been installed or run as root**, so it is rendered and
tested, not proved on the host.

Prometheus and Grafana are pinned but were never run and have no configuration,
so no unit was rendered for them; `not_rendered` records that with its reason
rather than shipping a guess.

### What this session still does not cover

- No application emits telemetry, and the collector only writes to the journal.
- The credential values in `var/run/` are still plaintext on disk and unchanged
  since the register slice. Sealing them is `70-credentials.sh`, which needs root.
  **The SA and application passwords should be rotated when the units are
  installed**, because they have sat in plain files throughout.
- The five application images are local tags, not digests, so `ARTIFACT_PINS`
  stays open and the units name a tag.
- `pinecone-poc` and `embedding-provider` are staged as values that say
  `PLACEHOLDER-NOT-A-REAL-CREDENTIAL-DECISION-PENDING`. Nothing consumes them.
  The `review-api` and `review-client` credentials are read and then dropped:
  Review is served with no client authentication, and Control Plane holds a
  client credential it never presents.
- The vaults still share one root credential across every application, because
  no per-application vault identity has been created.
- No orchestration has run through either scheduler, no work has been claimed,
  and nothing has been written to the register or a vault by an application.

### Still open, and why

- `SQL_SERVER_CERTIFICATE_TRUST` / `VAULT_SERVER_CERTIFICATE_TRUST` — **closed.**
  The internal authority is issued, SQL and both vaults are verified against it,
  and Review now serves it too. What remains is renewal and rotation, which no
  proof covers.
- `SYSTEMD_CREDENTIAL_DELIVERY_PROOF`, `UBUNTU_SYSTEMD_PROOF`, `ARTIFACT_PINS`,
  `CONTAINER_CREDENTIAL_BRIDGE`, `PATH_OWNERSHIP_PROOF`, `UBUNTU_IDENTITY_PROOF`,
  `UBUNTU_RUNTIME_PROOF`, `UBUNTU_24_04_X86_64_OCI_PROOF` — these need host
  provisioning: `/srv/asklegal` and `/var/lib/asklegal` paths, the ten accounts,
  the ten networks, nftables, sealed journal, and system-level units. **The agent
  has no `sudo` on this host and did not attempt to acquire any.** These are the
  user's steps.
- `SYSTEM_UNIT_AND_ENCRYPTED_CREDENTIAL_REPROOF`, `HOST_AND_CONTAINER_UID_ALIGNMENT`,
  `MANIFEST_LAST_EVIDENCE_PACKAGE` — the credential proof ran under
  `systemd --user`; the encrypted variant needs the root-only host key.
- Pinecone plan, project, and key; model and embedding admission; real Hong Kong
  package adjudication — all need the user's decision or purchase.

Current composite verdict is unchanged: `V1_POC_NOT_ADMITTED`. Static contracts
passing is not readiness, and none of the above was marked done because a
contract validated.

## Current outcome

The user has instructed the agent to continue working toward the accepted
local V1 and stop only when a material user decision or new permission is
required. Safe repository-only implementation and validation should therefore
continue in dependency order without routine confirmation. Infrastructure
products are now selected, but exact external admission, credentials, messages,
commit/push, deployment, destructive work, and production effects remain
explicit stop gates.

The user authorized M7 with the instruction "M7." The complete offline local-
synthetic milestone is **COMPLETE** against
`docs/design/M7_END_TO_END_CONFORMANCE_PLAN.md`.

M1 through M7 now pass locally. The user subsequently authorized committing
and pushing the complete accumulated M2–M7 implementation to `main`. Git state
was re-verified on 2026-08-17: the M2–M7 implementation is commit `297afda`,
the earlier validated foundation is commit `88f8e92`, and the current clean
`main`/`origin/main` head is documentation commit `3726ee4`. Ignored local
runtime evidence under `var/` is excluded.

The accumulated Hong Kong readiness and disabled V1 POC checkpoint was
committed on 2026-08-17 as `6be9dd0` (`feat: add Hong Kong readiness and V1
POC contracts`), followed by continuity commit `5140578`. The user explicitly
confirmed the exact private destination and `main` branch; both commits were
pushed to `https://github.com/stevw-repo/AskLegal-LegalDBPipeline.git`, whose
`main` now resolves through `5140578`.

The user then authorized read-only official legal-source access and requested
that all 14 accepted Hong Kong Legislation source roles be completed together.
This means the 14 roles across the three frozen Hong Kong Legislation scopes;
it does not extend to Cases, HKEX Regulatory Materials, other jurisdictions,
models, Pinecone, deployment, publication, or production mutation. RSS is
permitted only as a discovery/change signal and never as controlling legal
evidence or proof of complete no-change.

Official-source verification started on 2026-08-17. On 2026-08-18 the user
reported that the AskLegal legal team confirmed all source rights and
permissions green for the fourteen frozen Hong Kong Legislation source roles.
The register preserves that conclusion as a separate legal-team attestation;
it does not rewrite the previously observed DATA.GOV.HK, HKeL, GLD, Basic Law,
archive, or NPC publisher notices. Legal admission is therefore clear while
technical admission remains fail-closed per source and endpoint.

The first operational source checkpoint is now implemented. The strict source
register at `packages/source-connectors/src/asklegal_source_connectors/
hk_legislation_source_register.json` binds all 14 source roles, 78 exact
endpoint contracts, seven rights-evidence entries, one legal-team attestation,
and fingerprint
`sha256:e792bc88bc3dca14dee4816927291429d002d73efef18a10b217bd640e0dfc58`.
Five source roles are configured, five are partially configured, and four are
technically blocked. The official HTTPS connector is credential-free, direct, TLS-
validating, bounded, no-redirect, proxy-free, cookie-free, content-admitting,
and fail-closed on contract drift. RSS results are discovery signals only.

A read-only live probe returned HTTP 200 with the expected media types for all
44 enabled exact endpoints. Bounded full GETs captured only the English and
Traditional Chinese current and past XML inventories plus DATA.GOV.HK's RSS
feed in memory. No ZIP corpus body was downloaded or saved. The four inventory
captures returned `CAPTURED`; RSS returned `DISCOVERY_SIGNAL_CAPTURED`. No
source artifact was written, published, or committed as legal evidence.

On 2026-08-18 the earlier build-first sequencing assumption was superseded by
the legal team's clearance. Repository-only work now includes a complete
14-role/77-endpoint engineering report, safe binding for all six declared item
URL templates, an atomic exact-member bilingual inventory connector, and a
rendered-session connector boundary. The report now identifies 62 endpoint
procedures with implemented handling and 16 endpoints requiring direct inert
evidence, catalogue, or physical procedures; five source roles are technically
complete and operationally callable.

The user selected Patchright for JavaScript-backed access. ADR 0100 pins
Patchright `1.62.1` to the acquisition worker and confines it to ephemeral,
credential-free, exact-host discovery. Browser output is reduced to a
sanitized request-map summary and can return only a discovery result; rendered
HTML cannot become legal evidence, prove completeness/no-change, or authorize
processing. Exact legal bytes still require inert direct capture and the
ordinary manifest-last evidence flow. No CAPTCHA or access-control bypass is
permitted.

The Mac now has Patchright's local Chrome for Testing and headless-shell
runtime `151.0.7922.34` (Playwright Chromium build `1234`). A bounded live NPC
run completed through the registered `/index` endpoint as
`DISCOVERY_SIGNAL_CAPTURED`, observing 17 same-host requests and producing a
3,367-byte sanitized summary. It exposed the official read-only `wjConfig` API;
the strict HTTP connector separately captured its 138-byte JSON response in
memory with fingerprint
`sha256:680b4065825b32fb4fc99ea872c824621416890e9714d53cecb99008b741a71c`.

Bounded HKeL Gazette discovery proved the exact same-host client-check paths
`/checkconfig/submitClientConfig.do`, `/client-check`, and `/grid`. The
rendered page returned 200 at `/gazette`, but the role remains technically
blocked until the grid request body, pagination/completeness proof, and exact
artifact locators are contracted. GLD e-Gazette redirected to its terms page
and requested a blocked Cloudflare Turnstile script; no terms acceptance or
challenge bypass occurred. The NPC/NPCSC official-materials site failed with
Chromium TLS cipher/version mismatch and remains blocked.

Inert inspection of the official NPC application identified its direct
read-only enumeration and aggregate metadata APIs. Both exact `GET` endpoints
are now registered. The enumeration endpoint passed the actual bounded
connector as `DISCOVERY_SIGNAL_CAPTURED`: HTTP 200, `application/json`, 7,936
bytes, fingerprint
`sha256:910dff8c504334db211dc53f527c1f4b9d39ea8233f0a4af087b6a1a6835719e`.
The aggregate endpoint separately returned HTTP 200 JSON, 3,228 bytes,
fingerprint
`sha256:c1148d4e638445cf9045dd6828ccc7df486bf84a4d4a8371ca13c31b7acb145c`,
with the publisher's aggregate classification and popularity fields. Both are
discovery metadata only and do not prove a complete law inventory or no
change. The accepted M4
method contract remains closed to `GET` and `HEAD`;
the internal NPC POST search call was not added without an exact protocol and
request-body contract.

HKeL's official verified-legislation coverage list was identified as a direct
PDF endpoint independent of its active item pages. The exact endpoint is now
enabled under the partially configured verified-copies role and passed the
actual connector as `CAPTURED`: 16,659,689 bytes, `application/pdf`, fingerprint
`sha256:098d592927bfbcb34ecdeae573077399c7429e83c2558eb516c91800143f9be5`.
The bytes remained in memory only. This proves the coverage inventory path,
not the still-disabled per-item verified-copy locator.

The official HKeL client-check page exposes a deterministic no-JavaScript
fallback, but live inspection proved that it redirects from HTTPS to HTTP and
then returns only a reduced `/no-js` page without the requested item or PDF
download metadata. The connector will not follow that downgrade or execute the
publisher's active JavaScript. Patchright now completes the isolated discovery
handshake, but this no-JavaScript path still cannot supply item/PDF locators and
is not mislabeled as source evidence.

Official fetch results now retain the exact inert transport envelope for
successful, unsafe, redirect/status-drift, and media-drift responses. A genuine
transport failure retains no invented response. This closes the evidence-loss
gap before official outcomes are composed into the acquisition worker's
manifest-last flow.

The user has now accepted a strictly internal single-Ubuntu-host V1 POC. The
user said on 2026-08-18 that they will probably do significant parts of
development on the Ubuntu machine from now on; the Mac is not retired and this
is not yet a settled change of development host. One Ubuntu
24.04 x86-64 PC with 64 GB RAM and local ext4 storage runs the five
applications, SQL Server 2025 Developer, separate general and promotion Durable
Task Scheduler emulators, separate Primary and Recovery Versity Gateway
instances, systemd credential delivery, and local telemetry. Hosted Pinecone
Cloud in a dedicated isolated POC project is the replaceable vector-serving
copy. Azure application hosting remains post-V1/deferred.

Both vaults currently share one filesystem and therefore provide only
`LOGICALLY_SEPARATE_POC_RECOVERY`. The earlier single-physical-disk premise was
a reporting mistake corrected on 2026-08-18; the host actually has three
physical disks. Vault placement was decided on 2026-08-18: both vaults and the SQL data path
sit together on the 4.0 TB SATA disk, because the disks are asymmetric and a
~458 GB Recovery volume could not honestly mirror a 4.0 TB Primary. The
recovery class therefore stays `LOGICALLY_SEPARATE_POC_RECOVERY`, and the host
thresholds were amended to match the real machine; see the dated entry in
`DECISIONS.md`. Scheduler state is memory-only; loss fences
the old execution and starts reconciled replacement work from the last safe SQL
checkpoint, never a claim that lost history resumed. Exact topology, image
pins/digests, incremental implementation, and verification planning are the
current infrastructure objective. No deployment or external effect is
authorized; explicit permission is required before the first real Pinecone
write.

No credential, Azure resource,
Azure OpenAI/model or embedding call, Pinecone target, provider backup,
Ask.Legal route/slot, deployment, corpus publication, or production effect was
accessed or changed. Read-only official Hong Kong source pages and catalogue
metadata were accessed only for source-contract and rights verification; no
legal corpus was bulk-downloaded, no source artifact was published, and no
external account or resource was changed. Ask.Legal admin-portal integration
remains deferred; M7 stabilizes the Review API boundary it will later consume.

The current authorized parallel workstream is local, network-disabled Hong
Kong Legislation package readiness with `HK-LEG-ORDINANCES` first. Its frozen
readiness inventory and complete 27-rule ordinary offline path are
implemented and validated, but all real scopes remain `NOT_READY` and cannot
activate or process real observations.

The accepted Ubuntu infrastructure products, complete service/network/storage/
systemd topology, and 12-step incremental verification plan are now recorded in
`docs/design/V1_POC_UBUNTU_TOPOLOGY.md`. Its first implementation slice is
complete: `infrastructure/poc/topology.json` is a secret-free, disabled-by-
default closed inventory and `tools/v1_poc_topology.py` plus 10 focused tests
fail closed on authority, isolation, secret, surface, recovery, scheduler, and
artifact drift. The ordinary developer entrypoint now executes this gate.
All 16 services remain disabled; 3 existing artifacts are digest-pinned and 13
remain `PIN_REQUIRED`. The read-only host-admission policy and synthetic facts
validator are also complete with 14 focused cases. They require exact Ubuntu
24.04 x86-64, memory/disk/ext4/path, credential protection, nftables, sealed
journal, time, and Docker isolation facts but always return `admitted=false`.
The three durable host blockers are `CREDENTIAL_INTERFACE_PROOF`,
`HOST_PACKAGE_LOCKS`, and `PRIVATE_SUBNET_SELECTION`. The secret-free artifact
registry is also complete: 12 unique artifact entries cover all 16 services,
the SQL and shared DTS candidates are digest-pinned but require Ubuntu reproof,
10 artifact selections/builds remain, and all 12 entries are
`admitted=false`. Build, registry pull/push, service enablement, actual host
collection, and provisioning remain permission gates. Read-only credential-
interface research and the local difference, cause, proved-event, disposition,
record, and release-accounting gates are complete. After the repository-only
runtime-input and credential-loader work below, the infrastructure critical
path needs the Ubuntu host and explicit image pull/run permission; real Hong
Kong package admission separately needs complete source evidence and package-
owner authority.

The next repository-only infrastructure checkpoint is also complete.
`infrastructure/poc/application_image_inputs.json` freezes all five repository
image inputs and their complete 19-distribution closures, health commands,
topology identities/listeners, exact locks, and hardening profile. Ten focused
tests enforce five explicit blockers and `tools/dev_test.py` now runs the gate.
No runtime command is declared: every current local-fake application
entrypoint remains `ADAPTER_REQUIRED`, so it cannot be mistaken for a V1
continuous service. `tools/v1_poc_collect_host_facts.py` adds the bounded
read-only Ubuntu collector with three focused tests. It refuses macOS, reads no
credential value, writes nothing, and emits only the exact fact schema already
consumed by host admission.

`infrastructure/poc/application_runtime_inputs.json` now freezes the exact
disabled per-process runtime inputs: five application/service identities, five
operational database roles, four scheduler/task hubs, permitted vaults, 25
logical destinations, exact topology networks/listeners/outbound profiles,
and 19 credential filenames. Thirteen focused tests enforce seven remaining
blockers, and `tools/dev_test.py` runs this gate too. The application-runtime
package now provides a locally tested process-side systemd credential loader
with absolute-directory, canonical-name, no-symlink, exact `0400`, bounded-
read, and redacted-error rules. This does not resolve real addresses, start a
service, prove container credential delivery, or settle the SQL/Versity vendor
credential-interface conflict.

The Management Register adapter now provides a V1-only SQL connection factory
that composes exact non-secret topology with a redacted password value. It
allows only `sql-server:1433`, `AskLegalPocOperational`, and the five application
principals; requires strict encryption, certificate hostname validation, and
no trust bypass; bounds login time; and emits only a closed failure code. The
16 focused cases also bind the pinned driver's password-log sanitizer. Trusted
certificate issuance and application-image trust-bundle delivery remain a new
explicit `SQL_SERVER_CERTIFICATE_TRUST` blocker; no certificate or trust root
was generated.

The locked Durable Task SDK now has an exact V1 settings/factory boundary with
seven focused cases. General and promotion emulator DNS names and task hubs are
closed, Review cannot acquire a scheduler, no token or TLS is added to the
private emulator networks, worker capacity must be explicit, and memory loss
remains replacement from a safe SQL checkpoint.

Locked Boto3 `1.43.49` now supplies the disabled V1 S3-compatible vault
boundary. It disables ambient credential lookup, uses only exact credential
files, SigV4 path-style HTTPS with vault-specific CA bundles, and the frozen
three-attempt/five-second-connect/30-second-read profile. Provider version IDs
round-trip losslessly. Conditional create, SHA-256 read-back, COMPLIANCE
retention, legal hold, replay adoption, collision/corruption handling,
manifest-last writes, and primary-to-recovery copying pass against deterministic
S3 fakes. No delete API exists. Seven application-composition cases prove that
all five applications construct only their own SQL, scheduler, and authorized
Primary/Recovery vault roles and load every declared provider credential file
without connecting, inventing an unselected provider format, or reading an
environment password. Provider material without an admitted adapter remains an
opaque redacted value.

The composition audit found and corrected one V1 topology omission. The
accepted M3 protocol requires read-only evidence for Control proposal
preparation and Review evidence streaming, so both applications now have
separate Primary Vault credential references and internal network membership.
The topology therefore has 25 credential references. No vault credential,
real endpoint, certificate, bucket policy, or permission was created; those
remain blocked. `VAULT_SERVER_CERTIFICATE_TRUST` is an explicit seventh runtime
blocker.

The framework-free application-runtime package now has the complete exact V1
readiness dependency inventory for all five applications and a bounded async
gate. It rejects missing, extra, duplicate, reordered, or unbounded probes;
runs the complete set with per-probe deadlines; normalizes failure and timeout
states; and becomes ready only when every dependency succeeds. The disabled
runtime policy carries the same dependency codes and cross-checks them against
the package. SQL now has a non-mutating exact `SELECT 1` readiness check with
resource cleanup, while each S3 vault verifies versioning and Object Lock
without writing. Official Microsoft guidance documents connectivity testing
to emulator gRPC port 8080 but no non-mutating SDK/task-hub health operation.
Scheduler, telemetry, Review/egress, and actual host probe behavior therefore
remain inside `BOUNDED_READINESS_PROBES`; no private SDK API or fake mutation
was substituted.

The accepted systemd graph is now machine checked rather than prose only.
`infrastructure/poc/systemd_unit_inputs.json` binds all 16 topology services,
two disabled privileged bootstrap one-shots, and five disabled timers whose
cadences remain package/admission inputs. It fixes unit dependencies, runtime
identities, exact credential files, write paths, root-owned management, restart
policy, `NoNewPrivileges`, strict protected system paths, private temporary
space, and an empty capability bounding set. Ten focused tests reject missing
units, identity/credential/dependency drift, weaker hardening, secret-bearing
configuration, timer defaults, bootstrap enablement, or authority expansion.
Six blockers keep runtime commands, unit installation, image pulls, credential
bridging, subnets, and Ubuntu proof unavailable; the checker never contacts or
modifies systemd.

The accepted host accounts are also now machine checked. The host-identity
contract binds the ten services that own persistent application/vault/telemetry
paths to distinct locked, non-login, group-isolated accounts and all 14 exact
write paths. Numeric UID/GID values stay null and every account stays
`created=false` until collision checks occur on Ubuntu. Nine focused tests
reject missing/shared/root identities, interactive shells, invented IDs,
ownership drift, embedded secrets, or host-mutation authority. Four blockers
retain numeric allocation, container UID/GID mapping, ownership read-back, and
real Ubuntu proof. SQL remains image-defined; pathless DTS and egress container
identities are not falsely declared as host accounts.

The executable credential-interface proof now has exact machine-checked inputs
instead of prose alone. `credential_interface_proof_inputs.json` binds SQL and
both Versity services to their current artifact selections, systemd credential
names, six proof steps, seven canary-inspection surfaces, 12 required evidence
classes, restart/rotation behavior, named cleanup, and the accepted fail-closed
decision gate. All three results remain `NOT_RUN`; image and host actions remain
unauthorized. Twelve focused mutation cases reject false execution, authority,
secret-rule weakening, evidence loss, artifact/systemd drift, or embedded
material.

The V1 admission result is now one fail-closed machine verdict rather than an
inference from separate static checks. `infrastructure/poc/v1_admission_gate.json`
binds 14 ordered components and all effect authority to false;
`tools/v1_poc_admission.py` re-runs the eight implemented static checkers and
returns exactly `V1_POC_NOT_ADMITTED`, with eight static contracts validated
and 14 blockers. It cannot admit V1, mutate the host, resolve or pull an image,
create a credential, contact a source/provider, or write Pinecone. Twelve
focused mutation cases protect the component order, evidence references,
states, blockers, authority, secret-free content, aggregate verdict, and
static-check propagation.

Read-only credential-interface research is now recorded in
`docs/design/V1_POC_CREDENTIAL_INTERFACE_SPIKE.md`. Official SQL material did
not reveal a supported password-file input, and Versity documents root
credentials only through arguments/environment while its internal IAM files
are persistent plaintext. No image pull or runtime test was authorized or
possible on the current Mac. The exact-image proof therefore remains gated on
an admitted Ubuntu test host, immutable pins, synthetic credentials, and
explicit pull/run permission; a failed proof will require a user choice rather
than a silent weakening of the accepted secret rule.
Current vendor interfaces expose one fail-closed admission risk: official SQL
Server container and Versity guidance uses environment variables or command
arguments for root credentials, which does not yet prove the accepted file-only
`systemd-creds` boundary. Credential-interface spikes must resolve this before
either service can be admitted; the rule is not silently relaxed.

## Completed M7 implementation

### Stable offline conformance interface

`asklegal-local` is exposed as a second console entry point of the existing
control-plane distribution and delegates to repository tooling in
`tools/local_conformance.py`. It is not a sixth deployed application, and the
closed 5-application/14-package architecture graph is unchanged.

The accepted interfaces are implemented:

```text
uv run --frozen --all-packages asklegal-local reset --exact-test-state
uv run --frozen --all-packages asklegal-local prove --scenario <E2E-001..E2E-032>
uv run --frozen --all-packages asklegal-local prove --all
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

## Hong Kong Legislation readiness checkpoint

The user accepted the recommendation to start one real-package workstream and
explicitly authorized local, network-disabled implementation. The first target
is `HK-LEG-ORDINANCES`; no source access, model call, cloud work, or production
action was authorized.

The new frozen package at
`packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package/` binds:

- all 14 accepted Hong Kong Legislation stable source roles without URLs,
  credentials, or acquired bytes;
- the three accepted non-overlapping Release Scopes, with Ordinances marked as
  the current implementation target;
- exact source, rights, bytes, incomplete rule/fixture-universe, evaluation,
  model-profile, owner, and attestation blockers; and
- a package inventory/fingerprint of
  `sha256:8176705e872a1751e280093435731b7302a123e9846a94e58058e919067541f5`.

The second checkpoint adds the offline `HKLEG-BASE-INV-001` vertical slice:

- one strict package-local Draft 2020-12 schema for the source/reason
  catalogues, rule, input, fixture catalogue, fixture, and decision;
- closed bindings from declared legal nature to the three accepted Release
  Scopes and one admitted current-inventory source role;
- four terminal branches—accounted, unaccounted, duplicate-owned, and
  misassigned—with no implicit success;
- four small synthetic fixture manifests and separately hashed exact expected
  decisions; and
- a deterministic conformance evaluator that validates all locks and emits no
  legal disposition or record.

The third checkpoint adds the preceding offline `HKLEG-BASE-OBS-001` slice:

- exact synthetic rulebook, Release Scope registry, and HKeL publication-
  specification locks at one cutoff;
- the release-blocking current-inventory and Gazette observation source set;
- five terminal branches for frozen success, missing/incomplete/stale required
  source, mixed cutoff, lock mismatch, and post-cutoff source change;
- five separately hashed fixtures and expected decisions; and
- an ordered proof that only the frozen-success branch advances through
  `HKLEG-BASE-OBS-001` → `HKLEG-BASE-INV-001`.

The fourth checkpoint adds the following offline `HKLEG-BASE-EVID-001` slice:

- matching English and Traditional Chinese current XML plus matching official
  HKeL copies for the exact synthetic version;
- both ADR 0081 copy classes, `VERIFIED` and `ASSISTED`, as permitted success
  paths without treating assisted copies as verified;
- five separately hashed fixtures and expected decisions covering both success
  modes, a missing Traditional Chinese current XML block, reconciliation
  conflict quarantine, and forbidden historical substitution; and
- an ordered proof through `HKLEG-BASE-OBS-001` → `HKLEG-BASE-INV-001` →
  `HKLEG-BASE-EVID-001`, with only an exact passing bundle advancing to
  `HKLEG-BASE-STATE-001`.

The fifth checkpoint adds `HKLEG-BASE-STATE-001`:

- exact predecessor binding to passing inventory and bilingual-evidence gates;
- one clear branch requiring complete current item, provision, structure,
  location mapping, version, operative-effect, no-conflict, and written-
  rulebook support facts;
- six fail-closed branches for missing required signals, partial or ambiguous
  mapping, accepted-source conflict, unknown source semantics, unproved
  operative effect, and missing rulebook support;
- seven separately hashed fixtures and expected decisions; and
- a composed ordered proof through `HKLEG-BASE-OBS-001` →
  `HKLEG-BASE-INV-001` → `HKLEG-BASE-EVID-001` →
  `HKLEG-BASE-STATE-001`.

The passing STATE result establishes only `OPERATIVE_CURRENT` at the frozen
cutoff. It keeps legal disposition `NOT_APPLICABLE`, emits no record, and uses
`historical_assertion_scope: PENDING_LIMIT_RULE`.

The sixth checkpoint adds `HKLEG-BASE-LIMIT-001`:

- an exact predecessor binding to the successful present-state result;
- one success branch that changes the assertion scope to
  `PRESENT_STATE_ONLY` without creating a historical claim;
- four blocked branches for unsupported historical events, effective dates,
  identity or continuity relationships, and complete event chains;
- five separately hashed fixtures and expected decisions; and
- a composed ordered proof through `OBS-001`, `INV-001`, `EVID-001`,
  `STATE-001`, and `LIMIT-001`, with only the exact present-state-only result
  allowed to advance to `HKLEG-BASE-ID-001`.

The seventh checkpoint adds `HKLEG-BASE-ID-001`:

- new opaque register-owned identity requests for all four ADR 0011 layers,
  without inventing their unresolved concrete encodings;
- source identifiers and legacy Distillation/Pinecone IDs preserved only as
  aliases or trace facts;
- blocked source/legacy authoritative identity reuse and unproved lineage;
- quarantined duplicate or continuity ambiguity even when similarity is
  claimed; and
- five exact fixtures with two passes, two blocks, and one quarantine, with
  only clean allocation requests advancing to `HKLEG-BASE-DISP-001`.

The eighth checkpoint adds `HKLEG-BASE-DISP-001`:

- one exact supported result for each of `SEARCHABLE_CURRENT`, `WAITING_ROOM`,
  `EVIDENCE_ONLY`, `HISTORICAL`, and `QUARANTINE`;
- a visible Coverage Gap when an operative event is proved without matching
  current consolidation evidence;
- rejection of publication or one status signal as a disposition shortcut;
- seven separately hashed fixtures and expected decisions; and
- only the exact searchable-current branch advancing to
  `HKLEG-BASE-REC-001`; every other branch emits no record.

The ninth checkpoint adds `HKLEG-BASE-REC-001`:

- exact ADR 0021 canonical bilingual rendering with English first and
  Traditional Chinese second, NFC, LF, and language-correct punctuation;
- the repository-wide six-field Serving Record shape and exact metadata-only
  fingerprint, excluding register-issued identity;
- one synthetic metadata profile that is conformance-only and not an admitted
  production profile;
- six fixtures covering exact candidate creation, non-searchable exclusion,
  legacy identity rejection, incomplete alignment, non-canonical rendering,
  and unapproved authority notes; and
- only the exact candidate branch advancing to `HKLEG-BASE-REL-001`.

The tenth checkpoint adds `HKLEG-BASE-REL-001`:

- complete accounting for objects, locations, dispositions, candidates,
  Coverage Gaps, Quarantines, investigations, and identity decisions;
- an explicit initial-baseline marker with no predecessor release;
- seven fixtures covering success, missing and duplicate inventory,
  inconsistent disposition output, false predecessor, missing references, and
  unresolved completeness;
- one fingerprint over the complete exact accounting input; and
- eligibility only to build a candidate Corpus Release, with no publication,
  Approval, promotion, or deployment authority.

The eleventh checkpoint adds `HKLEG-BASE-REVIEW-001`:

- one exact named question, affected-object set, registered-source request,
  permitted fact, stopping condition, and responsible Legal Desk;
- four permitted on-demand historical/discovery source roles;
- five fixtures covering one successful targeted review and blocks for no
  material uncertainty, whole-history acquisition, unregistered sources, and
  mismatched fact scope; and
- no source access or historical assertion; only an exact task may advance to
  `HKLEG-BASE-HIST-001`.

The twelfth checkpoint adds `HKLEG-BASE-HIST-001`:

- six fixtures prove one exact permitted fact and block current-evidence
  substitution, similarity-only proof, unavailable/insufficient evidence, and
  discovery-only proof;
- conflicting evidence quarantines the affected decision; and
- history neither reconstructs current text nor manufactures legal events.

The thirteenth checkpoint adds `HKLEG-BASE-CHANGE-001`:

- seven fixtures cover no post-cutoff change, both permitted later-change
  strategies, lost frozen-package evidence, a missing separate Observation,
  silent cutoff mixing, and an unsupported later-currency claim; and
- no branch mutates the original freeze or authorizes an ordinary update.

The fourteenth checkpoint adds ordinary `HKLEG-CURRENT-OBS-001` through
`HKLEG-CURRENT-OBS-003`:

- six fixtures distinguish supported silence, new and deduplicated bounded
  affected work, release-blocking unavailability, item-only unavailability,
  and an open urgent signal;
- only complete, fresh, reconciled silence reuses the existing Corpus Release;
  no zero-record release is created; and
- a change signal opens acquisition work but makes no legal conclusion.

The fifteenth checkpoint adds ordinary `HKLEG-CURRENT-EVID-001` through
`HKLEG-CURRENT-EVID-004`:

- nine fixtures prove verified and assisted success, newer-assisted selection,
  and same-version verified preference;
- unavailable evidence blocks with a Coverage Gap only when current-law
  coverage actually depends on it; and
- unofficial copies, bilingual/version/content mismatches, and unresolved
  structure or identity cannot pass or be overridden.

The sixteenth checkpoint adds ordinary `HKLEG-CURRENT-DIFF-001` and
`HKLEG-CURRENT-DIFF-002`:

- seven fixtures classify exact unchanged, payload, structure/location,
  evidence-bundle-only, object-addition, and missing-baseline cases;
- exact unchanged is reuse-eligible only with separately proved continuing
  support; and
- the gate emits no record and explicitly makes no legal-identity, legal-
  status, repeal, or continuity inference.

The seventeenth checkpoint adds ordinary `HKLEG-CURRENT-CAUSE-001` and
`HKLEG-CURRENT-CAUSE-002`:

- six fixtures prove accepted Gazette and Editorial Record causes, fully exact
  non-serving technical republication, unexplained and conflicting-change
  Quarantine, and bounded Source Contract Review;
- status signals, HKeL appearance, similarity, and AI output cannot replace
  exact assigned cause evidence; and
- the gate emits no record and makes no legal-identity or status inference.

The eighteenth checkpoint adds `HKLEG-CURRENT-EVENT-001`:

- eight fixtures prove exact routing to an eligible reconstruction plan,
  verified or assisted known-stale fallback, explicit no-record gap, ordinary
  current-bundle handling, and fail-closed incomplete/conflicting/unbounded
  inputs;
- successful missing-consolidation cases record a Legal Status Event and exact
  Coverage Gap but emit no Search Record; and
- a synthetic active reconstruction state proves only selection precedence and
  grants no real reconstruction or activation authority.

The nineteenth through twenty-first checkpoints add the complete ordinary
`HKLEG-CURRENT-DISP-001` → `HKLEG-CURRENT-REC-001` →
`HKLEG-CURRENT-REL-001` tail:

- seven disposition fixtures assign each accepted primary state or fail closed
  on upstream, coverage, or single-signal uncertainty;
- eight record fixtures enforce exact six-field reuse, new immutable identity
  on any serving change, no record for non-searchable states, and Quarantine on
  same-ID mutation; and
- seven release-accounting fixtures reconcile every object, location, event,
  selected and retired record, Coverage Gap, and Quarantine before candidate
  release construction.

The loader now represents the accepted `NOT_READY` lifecycle honestly: every
not-ready scope must name blockers, ready scopes cannot retain not-ready
blockers, decision-ready or later scopes require real fixture/evaluation
inventory, and attested or later scopes require attestations. The package now
contains 27 offline conformance rules and 127 fixtures, but zero activation-
executable terminal rules, semantic profiles, evaluation IDs, or attestation
IDs. All three real scopes remain `NOT_READY`.

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

Those M7 results are historical evidence for the committed M7 tree. Validation
of the current 2026-08-17 Hong Kong readiness checkpoint produced:

- focused Legal Desk loader/lifecycle and 27-rule package suite:
  **49 passed**;
- V1 POC topology, read-only host-admission/collector, artifact-inventory,
  application-image-input, application-runtime-input, and cross-application
  composition, systemd/identity/credential-proof-input, composite-admission,
  and V1 S3 adapter suites: **115 passed**;
  their CLIs
  report 16 disabled services,
  25 credential references, 12 non-admitted
  artifacts, five non-admitted repository images, five non-admitted application
  runtime profiles, 16 disabled service-unit inputs, two disabled bootstrap
  units, five disabled timers, ten uncreated host identities, seven runtime
  blockers, six systemd blockers, four identity blockers, and three explicit
  host blockers; the credential-interface CLI reports **three subjects, six
  steps, seven inspection surfaces, six blockers, executed=0**; the composite
  CLI reports **14 components, eight static contracts validated, 14 blockers,
  admitted=false**;
- V1 SQL file-credential, exact-topology, strict-TLS, readiness,
  driver-sanitizer, and secret-free-failure suite plus exact two-emulator
  scheduler and common bounded-readiness suites: **34 passed**;
- ordinary repository suite excluding its loopback-only durability file:
  **436 passed, 4 skipped**, with two durability
  tests initially denied IPv6 loopback binding by the sandbox; both passed when
  previously rerun with explicit loopback permission, for an effective
  **438 passed,
  4 skipped** across the updated test inventory;
- Ruff check and formatting for all touched Python files: PASS;
- repository-owned Python boundary checker: PASS across **129 files** with the
  same eight exact reviewed exceptions;
- architecture proof: PASS with 5 applications, 14 packages, 80 dependency
  edges, 31 capability ports, and policy fingerprint
  `sha256:7f1f055c93c44be1577588937bf92afbd0ae38315935a1e6879fa4074511b7b9`;
- JSON Schema validation of the frozen real-package manifest: PASS; and
- exact uv 0.12.5 offline wheel build: PASS in two distinct output roots with
  byte-identical SHA-256
  `734df40775d0c0f23028e6551dfa85eb759f2648ebc36d961d7890f2a7643177`;
  all current event/disposition/record/release artifacts are present; and
- deterministic package rebuild: PASS with package version `0.21.0`, package
  fingerprint `sha256:61d58fca4b695a466dbaaa73353c066614ba47df3be7cf5f3c89aa5389a1e978`,
  and `package.json` SHA-256
  `292bc2b72fcd641f3448528f949a1edc6d73243c80fe1515c209b509c2370a88`.

Validation of the official-source and Patchright checkpoint, including the
2026-08-18 build-first extension, produced:

- complete repository pytest inventory after legal clearance, NPC metadata,
  and Patchright integration: **485 passed, 4 skipped**;
- source-connectors package: **50 passed**, including strict register,
  build-accounting, locator-injection, exact bilingual-member, rendered-
  session, transport-drift, content-admission, and RSS signal cases;
- repository-wide Ruff lint: PASS;
- acquisition-worker plus source-connectors strict Pyright: **0 errors, 0
  warnings, 0 information messages**;
- Python boundary checker: PASS across **143 files** with the same eight exact
  reviewed exceptions; and
- architecture proof: PASS with five applications, fourteen packages, 80
  dependency edges, 31 capability ports, and policy fingerprint
  `sha256:e1055d5940e3b0387e482976b578bb44f990fe9b3bc93854e9c7c7987e9dbc50`;
- V1 application-image input gate: PASS while still `NOT_READY` with five
  images and five blockers; and
- V1 composite admission gate: PASS while still `NOT_ADMITTED` with fourteen
  components, eight validated static contracts, and fourteen blockers.

The complete network-disabled two-path package proof was attempted after the
Patchright lock update. It stopped during a clean acquisition-worker install
because the already locked `s3transfer 0.19.2` artifact was not available to
the offline uv cache. No network fallback occurred. This is an explicit
wheelhouse/cache blocker; it is not a Patchright runtime or source-connector
test failure.

The repository-wide `npm run typecheck` was also attempted after installing
the lock-pinned local Node dependencies. It reports 370 errors in preserved
unrelated V1 files and missing Boto stubs; the changed source-connectors package
itself passes strict Pyright. Node.js is still 24.15.0 rather than the required
24.19.0, so the complete exact developer gate remains unavailable on this Mac.

Repository-wide Ruff lint passes. Touched files pass Ruff formatting, while a
full-tree format check reports two preserved pre-existing formatting drifts in
`packages/domain/src/asklegal_domain/operations.py` and
`tools/build_synthetic_rulebook.py`. The Python boundary checker passes across
141 files with the same eight reviewed exceptions.

Repository-wide strict Pyright, the exact Node validator, and the complete
two-path package proof have not passed for this source checkpoint. The full M7 32-scenario proof
was rerun twice from clean path-distinct state and passed with current report
fingerprint
`sha256:24ba2d3ec5471276ec7c62263af3ae7662178014bf007245e4025c936fba8edb`.
Lock-pinned Node dependencies are now installed locally and ignored by Git.
Repository-wide `npm run typecheck` starts but retains the 370 unrelated
baseline errors described above. Node.js remains 24.15.0 rather than the
required 24.19.0. The user separately authorized the package-registry step that
locked Boto3 `1.43.49` and its transitive dependencies; no service or vault
endpoint was contacted.

Historical M7 reproducibility fingerprints include:

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

## Hong Kong readiness checkpoint files changed

- `packages/legal-desks/src/asklegal_legal_desks/loader.py`;
- `packages/legal-desks/src/asklegal_legal_desks/hk_legislation.py` and package
  exports;
- `packages/legal-desks/src/asklegal_legal_desks/_hk_legislation_package/`;
- `packages/legal-desks/tests/test_rulebook_package.py`;
- `tools/build_hk_legislation_rulebook.py`;
- `README.md`; and
- the four canonical continuity files under `.agent/`.

## Official-source checkpoint files changed

- `packages/source-connectors/src/asklegal_source_connectors/official.py`;
- `packages/source-connectors/src/asklegal_source_connectors/official_http.py`;
- `packages/source-connectors/src/asklegal_source_connectors/official_binding.py`;
- `packages/source-connectors/src/asklegal_source_connectors/official_inventory.py`;
- `packages/source-connectors/src/asklegal_source_connectors/official_planning.py`;
- `packages/source-connectors/src/asklegal_source_connectors/official_rendered.py`;
- `packages/source-connectors/src/asklegal_source_connectors/
  hk_legislation_source_register.json`;
- `apps/acquisition-worker/src/asklegal_acquisition_worker/
  patchright_discovery.py` and its focused tests;
- acquisition-worker dependency metadata, the exact uv lock, architecture
  policy/test, and V1 application-image input hashes;
- `docs/adr/0100-isolate-patchright-to-non-controlling-source-discovery.md` and
  the corresponding M4 protocol clarification;
- source-connectors admission, model, and public exports;
- six focused official-source test modules plus the Patchright test module; and
- all four canonical continuity files under `.agent/`.

## Latest V1 credential-proof checkpoint files changed

- `infrastructure/poc/credential_interface_proof_inputs.json`;
- `tools/v1_poc_credential_interface.py` and its focused tests;
- the composite gate and ordinary developer entrypoint;
- `README.md` and both V1 POC design documents; and
- `CONTEXT.md`, `ROADMAP.md`, and this working state. No new product decision
  was made, so `DECISIONS.md` was not changed by this checkpoint.

## Decisions and open questions

No new product or production architecture choice was required for M7. The
implementation follows the accepted 32-scenario plan and existing M3–M6
boundaries. The user subsequently selected `HK-LEG-ORDINANCES` as the first
real-package target and authorized local, network-disabled implementation.

There is no remaining M7 implementation blocker or decision. The Ordinances
package now has an exact blocker inventory and 27 fully covered offline rules,
but remains `NOT_READY`. Legal admission is clear for all 14 official-source
roles. Five roles are configured, five are partially configured, and four are
technically blocked. Adjudicated evaluation truth, semantic deployment
profiles, complete-universe acceptance, and conformance attestations remain
open evidence work, not defaults inferred from local success.

## Current host prerequisite

The active 2026-08-18 workspace is Ubuntu 24.04.4 LTS on x86-64
(`docpro-MS-7D99`), under `/home/docpro/Desktop/Ask.Legal Database/
AskLegal-LegalDBPipeline`. This is the machine intended as the V1 runtime host.
The repository requires exact Python 3.14.7, uv 0.12.5, and Node.js 24.19.0 for
its complete developer command. That toolchain was installed on this machine on
2026-08-18, without `sudo` and without modifying any shell startup file:

- uv and uvx 0.12.5 at `~/.local/bin/`, from the GitHub release tarball
  verified against its published SHA-256;
- managed CPython 3.14.7 via `uv python install`;
- Node.js 24.19.0 and npm 11.17.0 at
  `~/.local/opt/node-v24.19.0-linux-x64/`, from the nodejs.org tarball verified
  against the official `SHASUMS256.txt`; and
- the locked workspace (`uv sync --frozen --all-packages`, 87 packages) and
  locked npm devDependency Pyright 1.1.413 (`npm ci`).

Docker is deliberately not installed. It needs root, and adding the login user
to the `docker` group would violate the accepted
`docker_group_non_root_members_forbidden` host rule. The ordinary suite skips
every Docker-marked test, so it is not required for the developer command.

The complete developer command now runs on this machine for the first time; it
could not run on the Mac, whose Node.js was 24.15.0. System Python remains
3.12.3, which is what `tools.dev_test` is invoked with. The eight pure-Python
static gates still pass and the composite gate still returns
`V1_POC_NOT_ADMITTED`.

Validation on this machine after the install: the complete developer gate
`python3 -m tools.dev_test` passed with **485 passed, 4 skipped**; the Python
boundary checker passed across 143 files with the same eight reviewed
exceptions; the architecture proof reproduced policy fingerprint
`sha256:e1055d5940e3b0387e482976b578bb44f990fe9b3bc93854e9c7c7987e9dbc50`;
repository-wide Ruff passed; and `asklegal-local prove --scenario E2E-001`
returned `GOLDEN_FLOW_RECOVERED` with fingerprint
`sha256:a8cfe0c154ba9ded80fe6f37df79db289cafda4edc962b749375bef5e10d4558`,
byte-identical to the earlier macOS arm64 run. That is the first cross-machine,
cross-architecture reproduction of the local proof.

`npm run typecheck` still reports **370 errors, 0 warnings** from Pyright. The
count is identical to the figure recorded on the Mac, so it is a pre-existing
baseline rather than an install or toolchain artifact; the earlier note
attributing it partly to Node.js 24.15.0 was wrong. The errors concentrate in
`packages/legal-desks/.../hk_legislation.py` (51),
`packages/evidence-vault/.../s3.py` (26) and its tests (23), and the
`tools/v1_poc_*.py` family, and are mostly `reportUnknownVariableType`,
`reportUnknownArgumentType`, and `reportUnknownMemberType`. Because Pyright
fails first, `npm run typecheck` never reaches the boundary checker, which
passes when run directly. Clearing this baseline is open work.

## Credential-interface proof — partially executed 2026-08-18

Docker Engine 29.7.2 is installed on this host and the login account is in the
`docker` group, so container work is now possible. Both proof images were pulled
by digest and run with networking disabled and synthetic throwaway credentials.

Settled by execution: SQL Server 2025 satisfies the file-only secret rule through
`MSSQL_SA_PASSWORD_FILE`, leaking the value on none of the five inspected
surfaces; Versity Gateway `v1.7.0` has no file input and exposes its root keys on
four surfaces; and Versity's posix backend genuinely enforces Object Lock,
versioning, `COMPLIANCE` retention, and legal hold, refusing deletion of a locked
object with `AccessDenied`. The user accepted a bounded exception for the two
Versity root bootstrap credentials only. Details are in the dated `DECISIONS.md`
entry.

Both remaining steps have since been executed.
`DELIVER_SYSTEMD_CREDENTIAL_FILES` **passes**: `LoadCredential` delivers a `0400`
per-unit file, the container reads it through a bind mount, SQL Server starts,
the exact value authenticates and a wrong value is refused, and the value leaks
on none of five surfaces including the systemd unit and the journal.

`ROTATE_AND_REJECT_OLD_VALUE` **fails silently and is the most important finding
of the session.** Swapping the credential file and restarting does not rotate the
password: the new value was refused, the old value still authenticated, and the
service reported no error. Rotation must use in-database
`ALTER LOGIN sa WITH PASSWORD`, which was proved to work and to refuse the old
value afterwards. Any runbook that rotates by file swap would leave a supposedly
retired password live.

A delivery constraint also emerged: the credential file is owned by the systemd
service account at mode `0400`, so the container must run under the same numeric
UID. That is now a hard input to the still-open host-identity UID allocation and
container UID/GID mapping blockers, not a free choice.

The proof used a `systemd --user` unit, which exercises the same mechanism
without root. The encrypted `systemd-creds` variant, which needs the root-only
host key, and the real system-level units remain unproved.

**Contract gap now closed.** The proof record was redesigned from a
"nothing has run" guard into one that records executed results against evidence.
`credential_interface_proof_inputs.json` is schema 2 with status
`EXECUTED_PARTIAL`: real authority flags, six executed steps carrying evidence
references, per-subject results, one named accepted exception, two recorded
findings, and three replacement blockers
(`SYSTEM_UNIT_AND_ENCRYPTED_CREDENTIAL_REPROOF`,
`HOST_AND_CONTAINER_UID_ALIGNMENT`, `MANIFEST_LAST_EVIDENCE_PACKAGE`).

The checker enforces honesty rather than inactivity. An executed step or subject
must carry evidence drawn from the declared inventory; an unrun one must carry
none. `ready` is derived, not asserted: it may only be true when every step
passed and no blocker remains. An exception must name real subjects, give a
reason, a residual risk and a retirement path, forbid argument delivery, and may
never relax `arguments_forbidden`,
`credential_values_in_evidence_forbidden`, or `persisted_canary_forbidden`. A
subject claiming `EXCEPTION_ACCEPTED` must reference an exception that exists,
and a subject not claiming it may not carry one. The focused cases grew from
twelve to twenty-five, including seven that attack the exception mechanism
itself.

The Versity linux/amd64 digest is now pinned in `artifact_admission.json` and
both vault services in `topology.json`, raising pinned artifacts from two to
three and pinned topology artifacts from three to five.

The read-only host-facts collector was run here and aborted with
`read-only probe failed: findmnt`, consistent with an unprovisioned host: the
required `/srv/asklegal/...` paths do not exist. Two accepted policy thresholds
also do not match this machine as written; see the 2026-08-18 host-fact
correction in `DECISIONS.md`.

The earlier macOS workspace remains accurate history: Darwin 25.3.0 on arm64
under `/Users/admin/Desktop/AskLegal-LegalDBPipeline`, with uv and uvx 0.12.5
at `/Users/admin/.local/bin/`, managed Python 3.14.7, system Python 3.12.3,
Node.js 24.15.0, and no Docker. Exact Node.js 24.19.0 was, and remains, a
prerequisite for the locked complete developer command.

## Latest checkpoint verification

On 2026-08-17 the user successfully ran the local reset and `E2E-001` proof on
macOS after correcting the clean-workspace command to include
`--all-packages`; it returned `GOLDEN_FLOW_RECOVERED` with fingerprint
`sha256:a8cfe0c154ba9ded80fe6f37df79db289cafda4edc962b749375bef5e10d4558`.
The user then authorized the local Hong Kong Legislation readiness checkpoint
described above. Validation results are recorded in the current validation
section.

Credential-free official Hong Kong source pages, catalogue metadata, HEAD
responses, four XML inventories, two RSS feeds, publisher JavaScript bundles,
and the NPC enumeration metadata API were accessed read-only.
Captured response bodies were bounded and held in memory only; no legal corpus
or source evidence was saved or published. No model, embedding, Azure,
Pinecone, backup, routing, deployment, production system, account, or remote
mutable resource was accessed or changed. The source-connectors wheel build
was explicitly offline.

## Continuity file location change

On 2026-08-18 the four canonical continuity files moved from `docs/agent/` to
`.agent/` using `git mv`, preserving history as `R100` renames. Path references
were updated in `AGENTS.md`, `README.md`,
`packages/management-register-adapter/README.md`, and
`docs/design/V1_POC_UBUNTU_TOPOLOGY.md`. `.agent/` matches no `.gitignore` rule
and all four files remain tracked. The change is staged and not committed. See
the dated entry in `DECISIONS.md`.

## Authorization boundary and exact next step

M7 completion grants no M8 or external authority. M8 remains a later platform
milestone only if the user separately authorizes it. The stable first-baseline
rules run through `HKLEG-BASE-CHANGE-001`; the ordinary update path now runs
through complete `HKLEG-CURRENT-REL-001` accounting, with the separate
`HKLEG-CURRENT-EVENT-001` missing-consolidation router. Further real-package
admission needs adjudicated evaluations and complete-universe acceptance;
source rights are no longer the blocker. Bounded credential-free read access
is proved for the direct endpoints currently enabled, including the NPC
metadata API.

The next repository-only source steps are the exact HKeL `/grid` request,
pagination, completeness, and artifact-locator contracts; exact NPC direct
search/detail request bodies; catalogue and physical-holding procedures;
source-specific complete-capture composition; and integration with the
acquisition worker's manifest-last Primary/Recovery evidence flow. Patchright
may discover these contracts but cannot supply the controlling evidence. None
may bypass source or endpoint technical admission state.
The user has declined external publisher/archive enquiries for now. They are
not a V1 prerequisite and no message or request has been sent. Work continues
through independently verifiable official interfaces; sources without a
complete safe procedure remain visible as partial or blocked and cannot
contribute false completeness or no-change claims.

The static V1 POC topology, host-policy, artifact, application-image,
application-runtime-input, systemd-unit-input, host-identity-input, and exact
credential-interface-proof-input contracts are complete and disabled. The
composite gate records the complete
current result as `V1_POC_NOT_ADMITTED`; it does not turn those static passes
into readiness. Process-side
systemd credential-file loading, SQL/DTS/S3 factory composition, the complete
readiness gate, and concrete SQL/vault checks are locally proved, but
host/container delivery and the other concrete probes are not. The next
infrastructure proof cannot run honestly in the current environment. Its six
inputs are exact: access to the intended Ubuntu 24.04 x86-64 host, which is now
satisfied because the repository is checked out and running static gates on that
machine, leaving five outstanding; read-only image resolution authority; permission to pull and run only the
named SQL Server and Versity proof images; selection of an exact Versity
version/digest from that read-only resolution; permission to create synthetic
one-use credentials; and permission to create, inspect, then remove only the
named throwaway proof state after evidence capture. That host proof
is limited to credential-file behavior, SQL certificate trust and hostname
rejection, canary leak
inspection, rotation, restart, and named throwaway state. It authorizes no real
credential, source, Pinecone, model, deployment, or production effect. If the
Versity proof confirms its documented interface is incompatible, the user must
choose a native file-credential product, a maintained custom build, or an
explicit bounded relaxation; the recommendation is to preserve the rule and
prefer a native file interface.

The user explicitly confirmed that the private
`https://github.com/stevw-repo/AskLegal-LegalDBPipeline.git` remote is the
approved destination and authorized synchronizing the complete committed
M2–M7/V1 checkpoint from `main` to `origin/main`. Commits `6be9dd0` and
`5140578` were pushed successfully. The official-source and Patchright
implementation was subsequently committed as `8f2501d` and pushed by the user
manually outside an agent session; `main` and `origin/main` both resolve to
`8f2501d`. Other than read-only official-source access, no deployment,
external message, cloud mutation, or other remote-system action was performed.

### Suite state at the end of 2026-08-19

**727 tests pass and 4 skip, with nothing failing.** The user authorised
installing Node, so Node.js 24.19.0 was verified against the official
`SHASUMS256.txt` and unpacked into `~/.local/lib`, with `node` and `npm` linked
into `~/.local/bin`. Nothing was installed system-wide and no root was used. The
documented command now runs end to end on this host for the first time:

```sh
python3 -m tools.dev_test --uv ~/.local/bin/uv --node ~/.local/bin/node
```

All twelve static V1 contract gates pass inside it, including the new
rendered-unit drift check.

A hazard worth naming: `ruff format` has now twice rewritten parenthesised
`except (A, B):` into PEP 758's unparenthesised form, which is valid only under
the pinned Python 3.14. Eight library files currently carry it, so the tree
cannot be imported by the host's system Python 3.12. The existing guard covers
static entrypoints only. Nothing in this session was formatted with ruff for
exactly this reason.

### External providers smoke-tested — 2026-08-19

The user supplied a Pinecone key and one Azure OpenAI resource,
`asklegal-eastus-testing.openai.azure.com`, serving both an embedding deployment
(`text-embedding-3-small`) and an inference deployment (`gpt-5.4`). All three were
exercised for real, each through its own egress proxy, from inside the owning
worker's image and identity.

- **Embedding** — HTTP 200, model `text-embedding-3-small`, 1536 dimensions
  returned, 7 prompt tokens.
- **Inference** — HTTP 200, model `gpt-5.4-2026-03-05`, correct reply, finish
  reason `stop`, 18 total tokens.
- **Pinecone** — HTTP 200. One index visible, `testing-index-1`: dimension 1536,
  cosine, serverless on AWS `us-east-1`, state Ready, host
  `testing-index-1-t85jsjn.svc.aped-4627-b74a.pinecone.io`, and
  `describe_index_stats` reports 0 vectors in no namespaces. **The index dimension
  matches what the embedding deployment produces**, which a mismatch would
  otherwise have revealed only at first upsert.

Pinecone was read only: list and describe. Nothing was created, upserted, or
deleted, because the topology still records `real_write_authorized: false`.

**The allowlists are now exact.** The model profile permits only the one Azure
resource, and refuses a different `*.openai.azure.com` resource. The promotion
profile permits that resource plus exactly two Pinecone hosts, `api.pinecone.io`
and the assigned data-plane host; `docs.pinecone.io` and any other index host are
refused. **Recreating the Pinecone index changes its data-plane host and will
break the proxy with a 403 until `squid-promotion.conf` is updated.**

The real embedding and Pinecone credentials have replaced the placeholders in the
running promotion worker, which still reports READY on all six dependencies.

**The inference credential has nowhere to live.** The accepted topology gives
`legal-processing-worker` only `sql-processing`, `vault-primary-processing`, and
`model-egress-proxy`; there is no model-provider credential name, so the key that
was just proved to work cannot be loaded by the application that needs it. Adding
it means changing `topology.json`, `systemd_unit_inputs.json`, the worker's
`load_v1_infrastructure`, and the rendered units. It was not done unasked.

**Nothing consumes any of these credentials.** There is no Azure OpenAI adapter
and no Pinecone adapter in the workspace — no package, no client, no call site.
The smoke tests were standalone scripts, not application code paths. The two
admission blockers are unchanged: `MODEL_AND_EMBEDDING_ADMISSION` still needs a
deployment profile and evaluation, and `PINECONE_ADMISSION` still needs plan,
project, and write authority.

Credentials remain plaintext in ignored `var/run/staging/` and
`var/run/creds-*/`. Sealing them is `70-credentials.sh`, which needs root.

## Inference credential given a home — executed 2026-08-19

`legal-processing-worker` declared no model-provider credential, so the Azure
OpenAI inference key that was proved to work in the previous session could not
be loaded by the application that needs it. It can now.

The name `model-provider` was added to every contract that governs it:

- `infrastructure/poc/topology.json` — `credential_names`, provider before the
  egress proxy, mirroring how `promotion-worker` lists its two
- `infrastructure/poc/systemd_unit_inputs.json` — `credential_names`
- `infrastructure/poc/application_runtime_inputs.json` — `credential_filenames`
- `infrastructure/poc/service_runtime_commands.json` — `credential_names`, and
  the recorded image, which is now `asklegal/legal-processing-worker:model-cred`
- `apps/legal-processing-worker/src/.../v1_infrastructure.py` — a
  `model_provider_credential` field read in `load_v1_infrastructure`

The handoff had listed four places. There were more: two validators cross-check
these lists, `tools/v1_poc_application_runtime.py` and
`tools/v1_poc_systemd_units.py`, each requiring the sorted list to equal the
topology's, and two tests pin the credential totals, which moved from 25 to 26
distinct in the topology and 19 to 20 across the application runtime inputs.
`infrastructure/poc/credential_interface_proof_inputs.json` was not affected;
its subjects are only the three upstream images.

Re-rendering produced exactly three changed files: the sealing step now seals 25
credentials rather than 24, the unit gained its fourth `LoadCredentialEncrypted`
line, and the launcher installs the fourth file at 0400.

**This was executed, not only rendered.** `service_runtime_commands.json` carries
`RUNTIME_COMMANDS_PROVEN_LOCALLY` and a `proof_note` saying every command in it
ran on this host, so the entry was only added after the run:

1. All five images rebuilt from the current source as `:model-cred`. The new
   processing image was checked from the inside for the new source before it was
   used, because this build has shipped stale code before.
2. The credential volume was restaged with four files, each 0400 and owned by
   uid 3003.
3. The container was recreated on `:model-cred` and reached
   `LEGAL_PROCESSING_WORKER READY` on all five dependencies.

The other four applications still run `:tls-c` and their records still say
`:tls-c`, which is what actually ran. Only the processing worker was recreated.
The `:model-cred` images for the other four exist but were never started, so
nothing claims they were.

Full suite after the change: **727 passed, 4 skipped**, unchanged from before it.
All fourteen containers up; all five applications READY.

**What this does not do.** The credential can now be loaded. Nothing reads its
value and no call is made with it: there is still no Azure OpenAI adapter in this
workspace. `MODEL_AND_EMBEDDING_ADMISSION` is untouched and the composite verdict
stays `V1_POC_NOT_ADMITTED`. The local runtime still composes
`DisabledEffectPort("generative-model")`, which is the seam an adapter would fill.

## V1 completion push — provider adapters built and proved 2026-08-19

The user asked to finish V1 as fast as possible, authorised real Pinecone writes,
chose the five open Hong Kong sources, and allowed four security relaxations.

**The four external paths are real now, each proved from inside the owning
worker's image through its own egress proxy.**

| Path | Proof |
|---|---|
| Azure embeddings | 1536 dimensions, ~1.9 s, real token accounting, deterministic fingerprint across runs |
| Pinecone writes | three real vectors written to `testing-index-1`, enumerated back, retrieval gate passed |
| Azure inference `gpt-5.4` | real bounded decision returned; strictness guards refused a mismatched deployment and a wrong provider |
| Hong Kong sources | 1.9 MB of live HKeL current-inventory JSON (source-updated 2026-08-17) and the Basic Law portal, both admitted by the hostile-content classifier |

**New code.** `asklegal_promotion.remote` holds the Azure embedding adapter and
the Pinecone serving-target store. `asklegal_processing.remote` holds the Azure
semantic task runner. `ProxiedOfficialHttpTransport` lets the acquisition worker
reach official sources through its proxy.

All three speak REST directly with the standard library. Neither provider SDK is
in the pinned wheelhouse, and adding one would need network access and a
wheelhouse rebuild, so the SDK-free route was the fast route *and* the offline-safe
one. Every transport opens its connection to the proxy and tunnels with CONNECT,
matching the pattern the source connector already used.

**Fail-closed by construction.** Pinecone writes need `write_authorized`; deleting
an index needs a second, separate `destructive_authorized`, because that is not
recoverable. The semantic runner refuses an extra key, a missing key, an
unparseable body, an unknown challenge code, and any citation the evidence did not
supply — a legal component that repairs a malformed reply into a plausible
judgment is worse than one that refuses.

**Twenty new offline tests**, transports stubbed. Suite went 727 → 747 passed,
4 skipped.

**Two contract locks moved.** Adding a lint-ignore entry changed `pyproject.toml`,
which is a pinned image-build input, so its recorded fingerprint was re-locked.
All five images were rebuilt as `:v1`, all five containers recreated on `:v1` and
observed READY, and `service_runtime_commands.json` now records `:v1` for all
five — one tag everywhere, and every recorded image is one that actually ran.

**One root script.** `infrastructure/poc/ROOT_SETUP.sh` bundles every step needing
root, in order, idempotently. It found a real gap first: the sealing step wants all
25 credentials in one directory, but they were spread across three places and five
had different file names, so the user's run would have failed immediately.
`var/run/assemble_staging.sh` now builds a complete `var/run/staging-all`, verified
25 of 25. The script preflights the whole credential set, the rendered units, the
images, and the TPM device before it changes anything.

### What is still not done, plainly

- **The worker loops still do no domain work.** `run_once` is called with a
  no-op. The adapters exist and are proved, but nothing yet claims a task from a
  scheduler and drives acquire → process → promote. This is the largest remaining
  piece and it is the difference between "the parts work" and "the pipeline runs".
- **No application emits telemetry.** Unchanged.
- **Nothing has run under systemd.** `ROOT_SETUP.sh` is written and syntax-checked
  but has never been executed; it needs root, which this agent does not have.
- **Reboot survival is unproved**, and remains the point of the units.
- **Generative output is not reproducible.** The same prompt returned
  `INSUFFICIENT_EVIDENCE` on one run and `APPLIES_WITH_BASIC_LAW_QUALIFICATION` on
  the next. That is expected of the provider, but it means the challenge phase and
  evaluator are load-bearing, not decoration.

### Relaxations the user authorised, recorded so none of them hides

- egress firewall boundary not applied; workers keep unrestricted outbound access
- one shared vault root credential, no per-application vault identity
- Review API served with no client authentication
- images stay local tags, not digests, so `ARTIFACT_PINS` stays open

The composite verdict is unchanged: **`V1_POC_NOT_ADMITTED`**.

## First real systemd run — three bugs only a real run could find

The user ran `ROOT_SETUP.sh`. Install, sealing, and enable all succeeded: 25
credentials sealed to the host TPM, `asklegal.target` enabled. Then every one of
the fourteen units failed, and the failures were real defects in the rendered
units, not environment problems.

**1. No unit could start: `226/NAMESPACE`.** Every unit declares
`ReadWritePaths=/run/asklegal`, and `ProtectSystem=strict` refuses to build the
mount namespace when that path does not exist. Nothing created it. The template
now carries `RuntimeDirectory=asklegal` so systemd creates it, and
`RuntimeDirectoryPreserve=yes` so one unit stopping does not delete it from under
the others. After this, nine of fourteen units came up.

**2. SQL Server could not exec its own binary: `126`.** The recorded command was
`--cap-drop ALL` with no additions. `sqlservr` carries `cap_net_bind_service=ep`
as a file capability, and exec fails with `EPERM` when that capability is outside
the container bounding set. Reproduced outside systemd, so the recorded command
had never actually run despite the file's proof note. `capabilities_add` is now
part of the runtime-command contract, sql-server records `NET_BIND_SERVICE`, and
SQL Server was observed to start under it.

**3. The four applications could not place their credentials.** The launcher runs
as root and does `install -o <uid> -m 0400`, but the unit template rendered
`CapabilityBoundingSet=` empty, leaving root without `CAP_CHOWN`. The template now
grants exactly `CAP_CHOWN CAP_FOWNER CAP_DAC_OVERRIDE`.

**The proof note is corrected.** `service_runtime_commands.json` claimed every
command in it had been executed and reached its proven state. That was not true of
sql-server. Status is now `RUNTIME_COMMANDS_PARTIALLY_PROVEN` and the note says
which entries were not proven and why.

## Worker loops — the promotion worker now does real work

The loops were not merely missing a function call. `LocalTaskHub` is in-process
with a fixed queue and no way to enqueue from outside, so the workers had no work
source at all. The real one is the Durable Task hub, and `durabletask 1.9.0` with
`grpcio` is already in the pinned wheelhouse.

**A real orchestration ran end to end on the emulator** — scheduled, activity
executed, `COMPLETED` with the expected output. That is the first time anything
has gone through a task hub on this project.

`apps/promotion-worker/.../v1_pipeline.py` now holds a real orchestration and two
activities: embed through Azure OpenAI, then upsert to Pinecone and verify
retrieval. `v1_service` serves the real hub instead of looping on an empty local
one. The orchestrator holds no provider call and no clock, because the scheduler
replays it on every work item; every effect lives in an activity.

Writes require `PROMOTION_WRITE_AUTHORIZED=true`, now set for the promotion worker
because the user authorised real writes on 2026-08-19. Without it the worker still
runs the orchestration and fails closed at the upsert.

Applications may not import `durabletask` directly — `python_boundary_check`
enforces it. The context types are re-exported through `asklegal_durable_task`,
which is the one package allowed to see the library.

**Not done:** the other three workers still have no work source, and nothing yet
chains acquisition to processing to promotion. The promotion worker is the pattern,
not the whole pipeline.

## Fourth systemd bug, and the first real end-to-end run

**The launcher started every application twice.** Each image's entrypoint is
already `["/opt/asklegal/bin/asklegal-service", "--serve"]`, which calls exactly
the same `run()` as `python -m <app>.v1_service`. The runtime-command contract
also recorded that module invocation, and Docker appends a recorded command to the
entrypoint as *arguments*, so every application died on
`asklegal-service: error: unrecognized arguments: python -m ...`. All five were
affected; none had ever started under systemd. The five `command` entries are now
empty, and the image entrypoint runs as designed.

Note the shape of this one: the contract was internally consistent and every
static gate passed. Only running it showed that the recorded command and the image
entrypoint were two ways of saying the same thing, and that saying it twice breaks.

**Then the pipeline ran for real.** With the corrected configuration the promotion
worker reached READY on all six dependencies and served its hub. One orchestration
was scheduled against it and completed:

```
scheduled e2ba6cc76a9847c1aae7cc7dc5b40dd2
status: COMPLETED
output: {"written": 2, "verified": true, "index": "testing-index-1"}
```

The worker's own log shows `embedded 2 record(s)` then
`wrote and verified 2 record(s) in testing-index-1`, and the index went from three
vectors to five. Real scheduler, real Azure embeddings, real Pinecone writes, real
retrieval verification, driven by the deployed application rather than a probe
script.

That is the first time work has flowed through this system end to end. It covers
the promotion stage only: acquisition and processing still have no work source,
and nothing chains the three stages together.

## All three stages wired, and one document went the whole way

The acquisition and legal-processing workers now serve their own Durable Task
hubs, the same way the promotion worker does. Each has a `v1_pipeline.py` holding
its real activities, and its `v1_service` serves the hub instead of looping on an
empty in-process one.

**The full chain, executed:**

```
STAGE 1  acquisition: retained 1973663 bytes from HK-LEG-HKEL-CURRENT-INVENTORY
STAGE 2  processing:  decision INSUFFICIENT_EVIDENCE, 4 unresolved facts
STAGE 3  promotion:   {'written': 1, 'verified': True, 'index': 'testing-index-1'}
```

A real Hong Kong endpoint was fetched through the source proxy, retained in the
Primary vault under Object Lock with a verified read-back, read back out by the
processing worker at that exact version, analysed by the real `gpt-5.4`
deployment through the model proxy, and the resulting decision embedded and
written to the Pinecone serving target with retrieval verified. Six records now
sit in `testing-index-1`.

**The model behaved correctly on real input.** Given a legislation index rather
than legislative text, it returned `INSUFFICIENT_EVIDENCE` and said why — that
the evidence is a catalogue, that the task's decision vocabulary was not
supplied, and that no subject-specific facts were present. It did not
manufacture a judgment from a table of contents.

### Four more bugs, all found by running

- **Retention timestamps must end in `Z`.** `isoformat()` yields `+00:00` and the
  vault rejects it as `S3_RETENTION_INVALID`.
- **The vault could only verify objects that had a legal hold on.** `retention()`
  treated any error from `get_object_legal_hold` as a provider failure, but a
  gateway reports an object with no hold as `NoSuchObjectLockConfiguration`
  rather than `Status: OFF`. Every object written without a hold was therefore
  unverifiable, which is why the one historical proof that set a hold was the only
  one that ever passed. Narrowed to that exact error code; `COMPLIANCE` checking
  is unchanged.
- **A clock read inside an activity is not replay-safe.** Retention computed from
  `now()` differed on retry, and adoption of an already-written object compares
  the whole profile, so a retry collided with its own first attempt. The retention
  instant is now fixed.
- **Document bodies must not travel through the scheduler.** Fetch and store were
  two activities, which would have put a 1.9 MB body into orchestration history,
  because that is where activity results are persisted and replayed from. They are
  one activity now and only the reference travels. This one was a design error
  introduced in this session, not an inherited defect.

### Known scars and gaps

- One vault key, `poc/source/sep_…042/feac1a…`, is permanently stuck from a
  half-finished attempt: the bytes were written before verification failed, and
  Object Lock means it cannot be cleaned up. Harmless, but it is there.
- Two Basic Law endpoints return `HOSTILE_OR_INCOMPLETE_CONTENT`. That is the
  admission guard working, not a defect.
- **The units still run older images.** The chain above was driven against
  hand-started containers on the current build. `ROOT_SETUP.sh` has to be re-run
  for systemd to serve the pipelines.
- Nothing schedules this chain on its own. A driver script ran the three stages in
  order; no orchestration chains them, and the control plane does not yet start
  anything. That is the remaining piece between "it works" and "it runs itself".

## Automatic chaining, and the boundary that shapes it

**The architecture forbids the obvious approach.** Each application binds to
exactly one task hub: `_APPLICATION_SCHEDULERS` in the durable-task adapter,
`_TASK_HUBS` and `_expected_destinations` in the runtime validator, and the
container networks all say the same thing. The control plane is not on
`asklegal-scheduler-promotion` and cannot reach the promotion hub.

`dts-general` hosts three hubs — acquisition, control, and legal-processing — and
the control plane already declares `dts-general` as a destination and sits on that
network. So chaining acquisition to analysis needs no contract change at all, and
that is what `apps/control-plane/.../v1_pipeline.py` now does: an orchestration on
the control hub whose two activities schedule and await the other stages.

`asklegal-promotion-worker` remains unreachable from there. The options were
weighed with the user: amend the one-hub rule across the validator, four
contracts, and the tests, or hand off through the register. The register already
carries `effect_intent_fact`, `effect_claim_current`, `effect_attempt_fact`, and
`effect_receipt_fact` — precisely the "one component records an intended effect,
another claims and performs it" mechanism — so the register is the right path and
no rule needs amending. It is **not built**: `ManagementRegisterStore` exposes only
`consume_approval` and `resolve_command`, so the effect-intent tables have no
access code yet. The orchestration returns
`promotion: NOT_SCHEDULED_FROM_CONTROL_PLANE` rather than pretending otherwise.

Promotion's isolation looks deliberate: it is the one stage that changes what
users see. That is why it was not traded away for a shortcut.

## All open Hong Kong sources

Of the fourteen roles, **five are fully configured, five partly, and four
blocked**. The blockers are not code: a rendered session transport, an exact HKeL
grid pagination and artifact-locator contract, an NPC direct-search API contract,
a catalogue discovery procedure, and — for the Gazette archive — a *physical
holding* procedure. None can be invented here, and four roles have no enabled
endpoint at all.

What is open is **59 enabled endpoints across 10 roles**, and those were captured
through the real pipeline: each one fetched through the source proxy, classified,
and retained in the Primary vault under Object Lock with a verified read-back.

`acquire_endpoints` was added to the acquisition worker for batch capture, and it
is sequential on purpose: several endpoints carry ceilings in the hundreds of
megabytes and the connector holds a response in memory while classifying it, so a
fan-out would multiply peak memory for no gain. Individual failures are recorded
in the result rather than raised, because a source refusing admission is a finding
worth reporting.

The batch run had to be driven per endpoint instead, because the systemd-managed
worker still runs an older image, claimed the batch orchestration, and failed it
with `A 'acquire_endpoints' orchestrator was not registered`. Both workers know
`acquire_endpoint`, so the driver used that. Re-running `ROOT_SETUP.sh` puts
systemd on the current build and removes the need.

## The architecture forbids one application creating work for another

This was learned by executing, and it reframes "automatic chaining" entirely.

**The scheduler side.** Each application binds to exactly one task hub
(`_APPLICATION_SCHEDULERS`, `_TASK_HUBS`, `_expected_destinations`, and the
container networks). `dts-general` happens to host three hubs, so the control
plane can reach acquisition and legal-processing; `dts-promotion` it cannot.

**The register side, which was the surprise.** The obvious fallback was to record
a promotion intent in the register and let the promotion worker claim it. The
register refuses:

```
IF @caller_application IS NULL OR @caller_application <> @owning_application
    SET @result_code = 'REJECTED_UNAUTHORIZED';
```

`commit_command_v1` rejects any command whose `owning_application` is not the
caller. Both mechanisms enforce the same rule from opposite sides: **an
application may not create work for another application.** A push-based chain has
no legal form in this system.

The intended shape is therefore pull: each stage records what it did, and the next
stage notices and creates its own work. Making promotion notice requires a
readable signal that promotion owns, and no such signal exists yet. That is the
real remaining piece, and it is a design question rather than a coding one.

Four wrong turns preceded that finding, each caught by running:

- direct table DML — the register grants `EXECUTE` on procedures and `SELECT` on
  views, and explicitly `DENY`s INSERT/UPDATE/DELETE on the schema
- `DATEADD(...)` inside an `EXEC` parameter — EXEC parameters must be values
- `guard_result_code` outside the closed set, and an `APPLIED` command with no
  event: a command that applied must carry the event it produced
- not consuming the procedure's result row. `commit_command_v1` selects its result
  and only then commits, so closing without reading silently loses the command.
  This one reported success while persisting nothing, which is the worst kind.

### What is built and correct

`EffectHandoffStore` speaks the register's own procedures and view, and works —
for an application recording intents **it owns**. Its docstring now says so, so
the mistake is not repeated. The control-plane orchestration chains acquisition
and analysis and returns `promotion: REQUIRES_PULL_BY_PROMOTION_WORKER`, which
states the constraint rather than implying an unfinished switch.

## Open Hong Kong sources — capture in progress

Running through all 59 enabled endpoints. Roughly 3.3 GB retained by endpoint 34,
with individual archives up to 402 MB. The Hong Kong servers deliver at about
500 KB/s, so the largest `PAST-DATA` and `CURRENT-DATA` archives exceed the
600-second per-orchestration timeout and are recorded as failures rather than
retained. Raising that ceiling, or capturing those few overnight, is what remains.

The four blocked roles cannot be finished from this repository: they need a
rendered session transport, an exact HKeL grid pagination and artifact-locator
contract, an NPC direct-search API contract, a catalogue discovery procedure, and
a physical holding procedure for the Gazette archive.

## The one-hub rule was amended, and the chain now runs end to end

The user authorised changing the rule. The amendment is narrow and deliberate:
**the control plane alone may reach a second scheduler.** The four workers still
bind to one hub each and still cannot reach one another, so the isolation that
matters — a worker cannot start another worker's work — is intact. What changed is
that a sequencing component is now expressible at all; under the original rule it
was not.

Amended in seven places, all of which had to agree: the logical destination table
and readiness order in `application-runtime`, `_expected_destinations` and
`_READINESS_DEPENDENCIES` in the runtime validator, `_REQUIRES` in the systemd
validator, the topology's network membership, and the four `infrastructure/poc`
contracts. The destination count moved from 25 to 26.

**Executed, through one control-plane orchestration:**

```
STAGE 1 retained 141373 bytes from HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS
STAGE 2 decision INSUFFICIENT_EVIDENCE
STAGE 3 promotion {'written': 1, 'verified': True, 'index': 'testing-index-1'}
```

The control plane reports `TASK_SCHEDULER_PROMOTION=READY` alongside its own hub.

The register's `EffectHandoffStore` remains, correct and usable by an application
recording intents it owns. It is no longer on the critical path, and the pull
design it was built for is still the better long-term shape if the control plane
should ever stop being a single point of sequencing.

## The blocked Hong Kong endpoints, re-examined against reality

An earlier claim in this file — that five roles "need a real browser" — was wrong,
and fetching the disabled URLs directly proved it:

| URL | Result |
|---|---|
| `elegislation.gov.hk/importantnotices` | **200**, 59,600 bytes, no script shell |
| `grs.gov.hk/.../gazette.html` | **200**, 8,628 bytes |
| `search.grs.gov.hk/en/search.xhtml?q=gazette` | **200**, 56,167 bytes |
| `elegislation.gov.hk/copyright`, `/editorialrecord`, `/gazette` | **302** to `checkClientConfig.jsp` |
| `egazette.gld.gov.hk/en/list-of-gazette`, `/search-gazette` | **302** to `terms-acceptance` |
| `www.npc.gov.cn/` | TLS handshake failure |

So the real blockers are four different things, none of which is "needs a browser":

1. **The connector does not follow redirects**, by deliberate design. That alone
   accounts for five endpoints. Following one redirect within the same admitted
   host would unblock them.
2. **The GLD e-Gazette requires accepting terms of use.** That is a consent gate
   and belongs to the user, not to an agent.
3. **`www.npc.gov.cn` fails the TLS handshake** — an old or restricted cipher
   configuration, not a contract problem.
4. **Template URLs need a locator first** — `{legal_item_locator}`,
   `{verified_copy_locator}`, `{assisted_copy_locator}`,
   `{issued_artifact_locator}`, `{official_material_locator}`. These need the
   search or list step that produces the locator, which is the genuine
   rulebook-shaped gap.

Notably the **Gazette archive catalogue is online and fetchable** (56 KB of
results). The physical-holding procedure applies only to material that exists
solely on paper, not to the catalogue.

## Three roles retired, redirects loosened, and the e-Gazette answer

**NPC and the Gazette archive are out of scope for V1**, by the user's decision on
2026-08-19. `OfficialSourceState` gained `OUT_OF_SCOPE_V1`, because recording a
role we chose not to pursue as `BLOCKED` implies work is pending when none is.
Both NPC roles are mainland sources the database does not need; the Gazette
archive needs a physical holding procedure nobody will carry out. Their endpoints
are disabled and the register fingerprint is re-derived to
`sha256:9e2a083aa12f59cd2417da6906047913e4c738c3c35127919a6fff5a735fa58c`.
Blocked roles are now 2, enabled endpoints 55.

**The transport follows redirects**, same host only, at most three hops. The
strict transport refused all redirects, which made five reachable endpoints look
blocked. Narrow on purpose: a redirect can never move a fetch to a host the
register has not admitted.

It is a partial win and should not be reported as more. The three HKeL URLs now
return `200`, but all three return an identical 7,562 bytes — the
`checkClientConfig` page, not the documents. They need cookie support as well.
The loosening is correct and worth keeping; it did not by itself open those three.

**The e-Gazette terms were read rather than accepted, and that was the right
call.** The user asked for the checkbox to be clicked. Reading the page first
showed why it would not have helped:

> Any reproduction, adaptation, distribution, dissemination or making available of
> such copyright works to the public is strictly prohibited unless prior written
> authorization is obtained from the Government of the HKSAR.

That is exactly what this pipeline does — retain, embed, and serve. The page also
carries a Personal Data (Privacy) Ordinance (Cap. 486) notice about Gazette
notices containing personal data and DPP3 purpose limitation.

The register had already recorded this: `rte_...003` concludes
`PRIOR_WRITTEN_AUTHORIZATION_REQUIRED`. Clicking "I have read and accepted" grants
nothing; it affirms having read the prohibition. The blocker for GLD e-Gazette is
written authorization from the Government Logistics Department, and nothing an
agent clicks changes that.

The standing instruction on loosening rules is in `AGENTS.md`, with the list of
things that stay strict and the two that are never done on the user's behalf.
`.agent/HANDOFF.md` no longer exists; this file is the record.

## Cookies and redirects added; the three HKeL pages need more than both

The proxied transport now keeps a cookie jar for the duration of one fetch and
sends it across redirect hops. Cookies are discarded with the fetch, so nothing
carries identity from one capture to the next.

**It did not unblock `/copyright`, `/editorialrecord`, or `/gazette`.** Those sit
behind a legacy JSP client-capability gate. `checkClientConfig.jsp` sets its
cookie from JavaScript rather than a `Set-Cookie` header, and posts a form to
`submitClientConfig.do` reporting `jvmVendor`, `jvmVersion`, `appletLoadFailed`,
and IPv4/IPv6 verification — a Java-applet-era check. Completing the handshake by
hand got real session cookies (`CLIENT_CONFIG_ATTRIBUTE` among them) but the
submit redirected to `warning.jsp`, so the reported capabilities were rejected,
and the three URLs still bounce back to the gate.

Recommendation: leave them. All three are supplementary — a copyright notice, an
editorial-records index, a gazette back-capture index. None is legislation. The
legislation itself, roughly 9 GB, already arrives through the data.gov.hk mirrors,
which have no such gate. Chasing an applet-era capability check for three index
pages is poor value and brittle.

The cookie and redirect support is still correct and worth keeping; several other
government endpoints use ordinary same-host redirects.

## e-Gazette: legal cleared it, and the acceptance POST was blocked by the sandbox

The user reported on 2026-08-19 that their legal team green-lit GLD e-Gazette.
That is recorded here as **the user's report of legal clearance**, which is what
the register's `LEGAL_TEAM_CLEARED` state already means. It is not the same as
prior written authorization obtained from the Government Logistics Department,
and `rte_...003` still records `PRIOR_WRITTEN_AUTHORIZATION_REQUIRED` as the
publisher's stated condition. Both facts are true and should stay distinguishable.

The site is Laravel Livewire. The terms page yields `XSRF-TOKEN` and
`laravel_session` cookies and a `wire:snapshot`, and acceptance is a POST to
`/livewire/update` carrying the component snapshot with `acceptNotice` set.

That POST was **refused by the sandbox classifier**, which treats submitting an
acceptance to an external site as an action needing the user's own hand. It was
not worked around. The endpoints remain disabled.

If the user wants this completed, the options are: they accept the terms in a
browser themselves and the session is captured, or they grant the permission the
classifier is asking for. Either is their call, not an agent's.

## e-Gazette is closed by a CAPTCHA, and that ends the automation route

The user's legal team cleared GLD e-Gazette, the user granted permission, and the
plan was to build the terms acceptance into the connector as a product feature.
Reading the acceptance handler first showed why that cannot be done.

The form's submit handler branches on environment. In production it calls:

```js
const turnstileResponse = turnstile.getResponse();
```

**Cloudflare Turnstile.** The acceptance requires a CAPTCHA token. Completing or
bypassing bot-detection is prohibited outright, independently of who authorises
it, so the connector cannot satisfy this gate and no amount of permission changes
that. The earlier classifier refusals were correct for a reason neither side had
identified: the action really was in that category.

There is also a plain reading worth recording. The publisher put a CAPTCHA in
front of this content. Whatever the legal position on reproduction, the operator
is stating that automated access is not wanted here. Respecting that is the
correct engineering posture for a legal-data product.

**The four e-Gazette endpoints stay disabled.** The route to this source, if it is
still wanted, is an arrangement with the Government Logistics Department for an
API or bulk feed — the same route that would have been needed for the written
authorization their terms already required.

`.claude/settings.json` was added during this attempt with a broad
`Bash(sg docker -c *)` allow rule. It did not affect the outcome, because the
refusal came from the action classifier rather than command matching. It can be
removed.

### What did come out of the attempt

The transport gained same-host redirect following and a per-fetch cookie jar.
Both are correct, both are kept, and several government endpoints use ordinary
redirects. Neither opened the three HKeL config-gated pages, which need an
applet-era client check, and those are recommended as not worth pursuing: they are
index and notice pages, not legislation.

## The HKeL gazette rulebook was not built, and robots.txt is why

The user asked for the `/grid` contract behind `https://www.elegislation.gov.hk/gazette`.
Discovery was legitimate here — no CAPTCHA, and ADR 0100 permits Patchright for
exactly this kind of non-controlling contract discovery. Two things stopped it,
and only the second is decisive.

**Patchright cannot run in this image.** No Chromium binary; the build is offline
by design and installing a browser needs network plus root, which was refused.
That is a solvable packaging problem, not a blocker of principle.

**`robots.txt` is the blocker of principle.** HKeL publishes:

```
User-agent: *
Allow: /$
Allow: /sitemap
Disallow: /
```

Everything except the root page and `/sitemap` is disallowed for any agent that
is not separately named. The file then names `Googlebot` and `Bingbot` and grants
them broad access. Our acquisition worker is neither.

So `/gazette`, `/grid`, and every artifact locator behind them are paths the
operator has explicitly asked non-search-engine automation not to fetch. Building
the rulebook means building a crawler for exactly those paths. That is not a rule
of ours to loosen; it is the publisher's instruction, machine-readable and
unambiguous.

What was learned along the way, and is worth keeping:

- `/grid` exists as a top-level route and answers `405` to `GET`, so it is
  `POST`-only. The contract is discoverable in principle.
- `/sitemap.xml` is explicitly allowed and returns 2,914 entries. It contains
  exactly one gazette entry — `https://www.elegislation.gov.hk/gazette` itself —
  and no artifact locators, so the permitted route does not carry the data.
- The three config-gated pages sit behind the same `Disallow: /`.

**The pattern across both publishers is consistent.** GLD e-Gazette put Turnstile
in front of acceptance; HKeL disallows non-search-engine crawling. Both are saying
the same thing in different dialects: do not automate against the web front end.

**And both point at the same sanctioned channel.** The 9 GB already captured came
from `data.gov.hk` and `resource.data.one.gov.hk`, which are open-data
distribution points published for reuse and carry no such restriction. That is
the difference between what was collected and what was refused, and it is a real
distinction rather than a convenient one.

`data.gov.hk` was searched for gazette datasets: one result, unrelated (Treasury
quarterly accounts). The gazette artefacts are not currently published there.

**Recommendation unchanged and now better evidenced:** ship V1 on the consolidated
legislation, which is the operative law and is already in hand. If the gazette
artefacts are genuinely wanted, ask the Department of Justice to publish them
through data.gov.hk, which is the channel their own robots.txt and open-data
programme point to.

## The HKeL gazette contract is written down

Patchright discovery succeeded on 2026-08-19, run by the user on the host after
the DoJ cleared the access. The full contract is in
`docs/design/HKEL_GAZETTE_GRID_CONTRACT.md`. Summary of what was unknown and now
is not:

**The capability gate is query parameters, not an applet.** `/gazette` bounces
through `checkClientConfig.jsp`, `submitClientConfig.do`, and `warning.jsp`, then
`/client-check?…&JS_S=true&C_S=` returns and `/gazette?…` serves. Nothing hidden.

**The grid** is `POST /grid` with a JSON body naming
`gridId: GAZETTE_REGISTER_LIST`, `queryId: GAZETTE_REGISTER_QRY`, and
`screenId: ERTS0502`. `queryParams` is a list of `KEY=VALUE` strings where a
repeated key is a multi-valued filter; the three `GAZETTE_SUPPLEMENT_NO` entries
select Legal Supplements 1, 2 and 3 — Ordinances, Regulations, Bills.

**Pagination** is `pageNo`/`pageSize`, with `firstPage` and `lastPage` in the
response. `lastPage` was 1415 at `pageSize` 20.

**`totalRecords` is a trap.** It reported `100` against `lastPage: 1415`, so it is
not a row count and must never be used as a completeness figure. Walk the pages
and count what arrives.

**The artifact locator is `VIRTUAL_URL`**, a site-relative path without a leading
slash: `hk/2026/1` → `https://www.elegislation.gov.hk/hk/2026/1`. That is the same
shape the register already carries as `{legal_item_locator}` for the verified and
assisted copy roles, so this may unblock their locator half too — unverified.

Three things remain, and the role's blockers now say exactly these rather than the
old blanket `EXACT_GRID_PAGINATION_AND_ARTIFACT_LOCATOR_CONTRACT_REQUIRED`:

- `PDF_ARTIFACT_URL_CONSTRUCTION_NOT_OBSERVED` — `ENG_PDF`/`CHI_PDF`/`BI_PDF` are
  flags (`"E"`, `"C"`, `null`), not URLs, and the address is built client-side by
  a `generatePdf` control that was never exercised. One discovery run that clicks
  a PDF link settles it.
- `CONNECTOR_POST_SUPPORT_REQUIRED` — `OfficialHttpConnector` is `GET`/`HEAD` only,
  and the grid needs `POST` plus a `csrfToken` read from the rendered page.
- `CLIENT_CAPABILITY_ASSERTION_DECISION_REQUIRED` — the gate wants `BR=Chrome` and
  `JS_S=true`. The inert connector is neither. Asserting them is very likely
  harmless for a JSON endpoint that never renders, but it is a statement about our
  client to the publisher, and that decision belongs to the project owner.

### Two process notes from the discovery itself

The second discovery run returned an empty page — 39 chars, one request — and
**overwrote the first run's capture**, which was a real defect in the tool: a
discovery script must never clobber a previous result. Output is timestamped now,
a thin load retries once, and a thin result is reported as a failure rather than
written out as if it succeeded. The third run reproduced the first cleanly, so
the empty one was transient rather than a block.

The acquisition image cannot run Patchright: it carries the library but none of a
browser's shared objects, so a mounted Chromium fails on `libglib-2.0.so.0`. The
host has both, and the repo venv already has patchright 1.62.1, so discovery runs
there. Putting it in the worker means adding roughly thirty libraries through
`var/debs`, which is how the image already gets its Kerberos libraries.

## The gazette register client is built

`packages/source-connectors/src/asklegal_source_connectors/hkel_gazette.py`
implements the discovered contract. Nine offline tests, transport stubbed.

**It is not part of `OfficialHttpConnector`, on purpose.** That connector is the
inert acquisition boundary — GET and HEAD, no body, no redirects — and it stays
that way, because source bytes must never gain a route into it. The gazette
register is a publisher API: `POST`-only, gated, and it issues a CSRF token
through a rendered page. `ProxiedOfficialHttpTransport` gained a separate
`exchange(PublisherCall, cookies)` surface for that, documented as the
publisher-API path rather than the evidence path.

What the client does: passes the capability gate at `/client-check`, reads the
`csrfToken` from the returned `/gazette` page, then `POST`s `/grid` with the
supplement filters and walks pages by `lastPage`.

**`CAPABILITY_CLAIM` asserts `BR=Chrome` and `JS_S=true`, and says so.** The
project owner decided this on 2026-08-19. The client is neither Chrome nor
JavaScript-capable; the values are stated because the gate refuses service
without them. The constant carries its own docstring explaining that they are
asserted rather than measured, so the claim stays visible instead of being buried
at a call site. The grid returns JSON and is never rendered, so nothing about a
document's production or interpretation depends on them.

Three behaviours the tests pin, each because getting them wrong is silent:

- **`totalRecords` is never read.** It reported 100 against `lastPage` 1415 live.
  Paging follows `lastPage`, re-read every page, and stops early on an empty page.
- **`ENG_PDF`/`CHI_PDF`/`BI_PDF` are flags, not URLs** — `"E"`, `"C"`, or absent.
  Treating them as addresses would fetch nothing and look like a bad source.
- **A reply without its `columns` fails** rather than guessing. Row data is
  positional, so absent columns make every cell a guess.

Still outstanding, unchanged: the PDF address construction was never observed, so
`PDF_ARTIFACT_URL_CONSTRUCTION_NOT_OBSERVED` remains a blocker and the role stays
disabled. The client yields locators and item URLs, which is what the register
needed; turning a locator into a PDF address needs one more discovery run that
exercises a `generatePdf` control.

## The PDF address is settled; the gazette contract is complete

Read from the rendered grid markup on 2026-08-19:

```html
<td><a href="/hk/2026/1!en"><img src="/images/icon/pdf.gif" class="pdf-link"></a></td>
<td><a href="/hk/2026/1!zh-Hant-HK"><img src="/images/icon/pdf.gif"></a></td>
<td><div>-</div></td>
```

**The address is the locator, a `!`, and the language code** —
`https://www.elegislation.gov.hk/hk/2026/1!en`. No server round-trip;
`generatePdf` only composes the string. Two published languages, `en` and
`zh-Hant-HK`. A bare `-` means that language was never published, the matching
flag is absent, and `pdf_url()` returns `None` rather than inventing an address
that would fetch nothing and look like a broken source.

`GazetteEntry.pdf_url(language)` and `published_pdf_urls()` implement it, with
three more tests. Suite is 759.

**A lesson worth keeping: two runs were wasted guessing selectors.** The marker
class `pdf-link` sits on the `<img>`, not the `<a>`, so filtering anchors by class
matched nothing twice. Dumping the row markup and reading it answered the question
in one run. When a selector finds zero, print the DOM rather than guess again.

The role's blocker is now the single honest remainder,
`ACQUISITION_INTEGRATION_AND_COMPLETENESS_RULE_REQUIRED`:

- nothing yet enumerates the register and fetches the addressed PDFs through the
  inert connector; the client returns locators and addresses, and that is all
- completeness is undefined. `lastPage` was 1415 and can move while paging, so a
  reproducible run probably needs a date-bounded query rather than a full walk.
  This is a design decision, not a coding one.

Settled and recorded in the contract document: the capability assertion was the
owner's decision, and `POST` went to a separate `exchange` surface rather than
into `OfficialHttpConnector`, which stays `GET`/`HEAD` so the inert evidence path
is untouched.

### Tooling note

Discovery uses **patchright**, not playwright — `from patchright.sync_api import
sync_playwright`, which keeps the playwright API name. The browser binary is the
playwright-installed `chromium_headless_shell-1234` from the host cache, which
patchright reads from the same location.

## Gazette integration built; the completeness rule is a date window

Three pieces closed the remaining blocker.

**Completeness is a date window, and that is a decision, not a discovery.** An
unbounded walk of the register is not reproducible: it grows at the front, so page
one shifts as gazettes are published and two runs of the same query disagree.
`iter_entries(date_from=…, date_to=…)` sends `GAZETTE_DATE_FR` and
`GAZETTE_DATE_TO`, which the grid already accepted; a closed window over past
dates returns the same rows every time. A malformed date is refused before the
request rather than silently ignored, because an ignored filter would return the
whole register while looking bounded.

**Template resolution reached the inert connector.** `OfficialFetchRequest` gained
`substitutions`, and `_resolve_template` fills a registered template such as
`.../hk/{gazette_artifact_locator}`. The guard is the template's own fixed prefix:
the resolved URL must still start with the part before the first placeholder, so a
value carrying a scheme, a host, or a parent traversal cannot move the fetch. Four
tests cover the happy path and the three refusals. The register already supported
URL templates natively — `allow_template=True` — so the model had anticipated this.

**The two boundaries stay separate, which was the point.** The register grid is a
publisher API reached through the proxied transport and yields only locators. Each
addressed PDF is then fetched through the inert connector and retained the
ordinary way, so bytes that become evidence arrive on the evidence path.
`capture_gazette_window` in the acquisition worker does exactly that, with
`acquire_gazette_window` as its orchestration.

A new endpoint, `sep_…004f`, carries the artifact template as `DIRECT_HTTP` and is
enabled. `HK-LEG-HKEL-GAZETTE-BACKCAPTURE` moved from `BLOCKED` to
`PARTIALLY_CONFIGURED`, and its remaining blocker states the honest limitation:
`COMPLETE_INVENTORY_RULE_IS_DATE_WINDOWED_NOT_WHOLE_REGISTER`. A windowed capture
is reproducible; it is not a claim to hold the whole register, and the role should
not pretend otherwise.

Counts moved with it: 79 endpoints, 56 enabled, one blocked role, five partially
configured. Suite 765.

**Not yet executed against the live site.** Every part is proved offline with
stubbed transports, and the grid contract itself came from live discovery, but no
gazette PDF has been fetched and retained end to end. That run needs the rebuilt
acquisition image under systemd, and it is the next thing to do rather than
something already done.

## The live gazette capture is NOT proved, and here is exactly where it stopped

Three attempts, three distinct outcomes. None of them was a successful capture.

**1. A real defect the suite could not see.** `HkelGazetteRegisterClient` and
`PublisherCall` were listed in `__all__` without ever being imported into
`__init__.py`. Every test passed because they import the submodule directly, so
the gap only appeared when the built image started and the acquisition worker
died with `ImportError: cannot import name 'HkelGazetteRegisterClient'`.

Fixed, and `tests/test_package_exports.py` now asserts that every `__all__` name
is importable from the package root and that no public name is missing from it.
That class of bug cannot recur silently.

**2. The orchestration was claimed by the stale systemd worker**, which runs an
older image and does not know `acquire_gazette_window`. Same conflict as the batch
capture earlier. Re-running `ROOT_SETUP.sh` puts systemd on the current build.

**3. The capture itself failed on `gazette page issued no csrfToken`.** This is a
real unknown, not a passing error. The capability gate was satisfied — no
transport failure — but the inertly fetched page did not contain a token matching
`_CSRF_PATTERN`. The token seen during discovery came from the *rendered* page in
the grid request body. The plausible explanation is that the raw HTML carries it
in a different shape, or that JavaScript injects it, in which case an inert client
cannot obtain it at all and the design needs revisiting.

**That question is unanswered because the site stopped responding.** The
diagnostic probe failed with `SSLEOFError: UNEXPECTED_EOF_WHILE_READING`, which
after a day of discovery runs and a 9 GB capture reads as rate limiting. Hitting
it again would be both unproductive and rude. Wait, then run the probe in
`var/run/` that searches the inert page for the token.

**So the honest status of the gazette work:** contract observed and documented,
client implemented, template resolution built and guarded, activity wired,
767 tests green — and **no gazette PDF has been retained**. The role's
`PARTIALLY_CONFIGURED` state with an explicit blocker is correct and should not be
advanced until a real artifact lands in the vault.

If the token turns out to be JavaScript-injected, the options are: keep a
discovery step that reads the token and hands it to the inert fetch, or ask the
DoJ for a documented interface. That is a design decision and it should be made
knowingly rather than by patching a regex until something passes.

## The gazette capture works, end to end, against the live site

```
capturing {'date_from': '01/03/2026', 'date_to': '31/03/2026', 'language': 'en'}
listed 14, retained 14, skipped 0
   30023  2026/ln20!en    98303 B  created=True verified=True
   30026  2026/ln21!en   142342 B  created=True verified=True
   30032  2026/ln27!en   711094 B  created=True verified=True
```

Real Hong Kong gazette PDFs, addressed from the register grid, fetched through
the inert connector, retained under Object Lock with the read-back verified.

Two defects stood between the built code and a working capture, and both were
only findable by running it.

**The CSRF token is a hidden form input, not a JSON key.** The served page carries
`<input type="hidden" name="_CSRF_TOKEN" value="…">`. The lowercase `csrfToken`
key appears only in the request body the page's own JavaScript assembles, which is
where discovery had seen it. Worse, the diagnostic that should have caught this
searched for lowercase `csrf` against uppercase markup and reported zero matches,
which briefly suggested the token was JavaScript-injected and the design unworkable.
It was neither. The pattern is now anchored on the hidden input and case-insensitive,
and the test fixture is shaped like the real page instead of like the old guess.

**The PDFs sit behind the same capability gate as the register page.** Every fetch
returned `MEDIA_TYPE_DRIFT` because `/hk/2026/1!en` redirects to
`checkClientConfig.jsp` for a client with no session, and the inert connector
starts each fetch with an empty jar. `ProxiedOfficialHttpTransport` gained
`with_session(cookies)`, and the activity now fetches artifacts through a
connector carrying the session the grid client established.

That is a real widening and it is worth naming: the inert connector now carries a
session it did not create. It is still GET and HEAD only, still executes nothing,
still follows redirects only on the same host. What changed is that a legitimately
obtained address can now be fetched without being bounced to a gate. The
alternative was pulling the bytes down the publisher-API path, which would have
put evidence on the wrong side of the boundary — a worse trade.

Both fixes are the same lesson as the `pdf-link` selector: when something reports
nothing, check the assumption behind the question before concluding anything about
the answer.

Still true: `lastPage` was 1415, so the register is far larger than any window
captured here, and the role stays `PARTIALLY_CONFIGURED` with
`COMPLETE_INVENTORY_RULE_IS_DATE_WINDOWED_NOT_WHOLE_REGISTER`. A windowed capture
is reproducible and now demonstrably works; it is not a claim to hold the register.

## The gazette register is captured for 2000-2026

```
years 27   listed 7644   retained 7274   skipped 370   failed-years 0
retention 95.2%   vault 9.7 GB
```

Every year from 2000 to 2026 completed. The 2003 window needed all three attempts
before it went through.

**Why the range stops at 2000.** The PDFs were sampled before choosing it: 1960,
1985, 1990 and 1995 are scanned images with image objects and no fonts, while 2003
and 2005 carry 35 fonts and no images. The crossover sits between 1995 and 2003,
so everything earlier needs OCR before an embedding pipeline can read a word of
it. Capturing it would have cost most of a day and several gigabytes for material
the pipeline cannot use. `run_gazette_capture.sh 1955 1999` remains available if
OCR ever exists.

**The 370 skips are honest absences, not failures.** 2000 alone accounted for 193
of them, which looked like a defect until it was checked: those entries carry no
PDF flag in either language, so the publisher hosts no file for them. Real
ordinances are among them — the Electronic Transactions Ordinance, the Arbitration
(Amendment) Ordinance 2000 — and 2000 sits right at the digitisation boundary. By
contrast 2001 and 2005 are 100 per cent English. `pdf_url()` returned `None` and
the activity recorded `NOT_PUBLISHED` rather than constructing an address that
would have fetched nothing.

**A gap worth naming:** those 193 entries still have real metadata — title, date,
gazette number, supplement — and none of it is retained, because only PDFs are
captured. The register listing is itself a manifest of what exists, and keeping it
would record that a document was gazetted even where no artifact is published.
That is unbuilt.

### Two defects in the runner, both found by running it

**Failed years were recorded as done.** The first pass had eleven transport
failures, and the second run printed `already done: {'error': ...}` for every one
and skipped them. Recording an error as completion defeats the entire point of a
resumable runner: the failures would have needed the progress file deleted to
retry. A year with an error is now retried, and only successes are skipped.

**There was no retry within a run.** The failures cluster in consecutive years,
which reads as the publisher throttling under sustained load rather than as broken
years — the same eleven years all succeeded on the retry. Each year now gets three
attempts with escalating backoff and a rebuilt session, since an expired session
fails in exactly the same shape.

The progress file lives on a Docker volume rather than in `var/run`, because the
container runs as the service uid and `var/run` belongs to the host user; the
first version would have failed its first save, after a year of work.

## The register listing is retained as its own manifest

Closing the gap named above: the 193 entries in 2000 that the publisher hosts no
file for had real metadata and none of it was kept.

`_retain_gazette_listing` now writes one manifest per window under
`poc/source/gazette-listing/{window}/{fingerprint}`, holding every row including
those with no PDF in any language: gazette id, date, supplement, number, both
titles, locator, item URL, and the three availability flags.

**It is filed apart from the artifacts on purpose.** The rows come from the
publisher's grid API, which ADR 0100 treats as discovery rather than controlling
evidence, so the manifest carries its own `kind` and a `provenance` line saying so
and lives under a distinct key prefix. Nothing should mistake it for a source
artifact. What it answers is the question the PDFs cannot: which documents were
gazetted in this window, including the ones with nothing to download.

The bytes are canonical — rows sorted by gazette id, fixed separators, no capture
timestamp inside — so re-running a window produces the identical object and the
vault adopts it rather than writing a second copy.

**Written and unit-green, not yet verified live.** `var/run/run_gazette_verify.sh`
re-captures one year and reads the manifest back out of the vault to confirm the
no-PDF rows are in it. It is slow because it re-fetches that year's PDFs, so it is
the user's to run rather than something to poll from here.

## Retry belonged in the client, not in the batch runner

The verify script failed on page 9 with `SSLEOFError` inside
`BOUNDED_TRANSPORT_FAILURE` — the same throttling the whole-register run had hit.
It failed because retry had been built into `capture_gazette_all.py` and nowhere
else, so the batch runner survived the publisher's behaviour and every other
caller did not. That is the wrong layer: dropped connections under sustained
paging are a property of talking to this publisher, not of one job.

`HkelGazetteRegisterClient` now retries a dropped grid call itself — three
attempts by default with escalating backoff, rebuilding the session before each
retry because an expired token fails in exactly the same shape and the error alone
cannot tell them apart. Every caller inherits it: the batch runner, the verify
script, the acquisition activity, and anything written later.

Two tests cover it, using a transport that drops early grid calls the way the live
service does: one proves a page survives two drops and takes three grid calls, the
other proves retries stay bounded and the failure is reported rather than looped
on. Retrying forever against a publisher that is refusing us is not politeness.

Suite is 771. The batch runner keeps its own per-year retry, which now sits above
a client that already retries per page; the two compose rather than duplicate,
since a year can still fail for reasons a single page retry cannot fix.

## The listing manifest is proved live

```
listed 488  retained 295  skipped 193
manifest: 488 rows, 241029 B, created=True verified=True
  key poc/source/gazette-listing/01012000-31122000/6a67bf03e29da0…
read back: kind=HKEL_GAZETTE_REGISTER_LISTING  rows=488
  rows with no PDF in any language: 193
    05/05/2000  LS2  Interpretation and General Clauses Ordinance—Resolution
    12/05/2000  LS2  Security and Guarding Services (Fees) (Amendment) Regulation
```

Read back out of the vault, not merely written. The 193 entries the publisher
hosts no file for are now recorded with date, supplement, number, both titles, and
locator. They are real instruments — resolutions under the Interpretation and
General Clauses Ordinance, Security and Guarding Services regulations — so the gap
was worth closing: without the manifest their existence was invisible.

The same run confirmed the client-level retry works against the live service. The
previous attempt died on page 9; this one completed the same window.

## 2026-08-20 — Complete pre-V1 audit (session: Codex desktop on docpro-MS-7D99)

**Objective:** diagnose stale state, defects, security/operational hazards, and
remaining V1 gates. No implementation fix, deployment, destructive cleanup, or
external provider/source mutation was authorized or performed.

**Verified baseline:** `main` at `f4128dc` is one commit ahead of and not behind
`origin/main` after fetch. The pre-existing promotion six-field changes and new
test remain unstaged. Full developer suite and exact repeat both passed with 785
tests and four skips. The 19-package offline proof, contract validator, boundary
checker, Ruff lint, lock check, syntax/link checks, and Git object check passed.
OSV found no vulnerability in 69 locked Python packages and npm audit found none.

**Failed or incomplete gates:** strict Pyright reports 902 errors, including 715
in 52 tracked files; the developer suite does not run Pyright or Ruff and no CI
configuration exists. Ruff format check reports 17 drifted files, but automatic
formatting remains unsafe for system Python 3.12 launchers. A fresh
`asklegal-local prove --all` aborts on existing `run-a`; no destructive reset was
performed. The dedicated SQL, Durable Task emulator, and image-admission proofs
were not rerun.

**P0 correctness findings:** the live control chain sends every model result
straight to promotion without frozen release/desired state, Review, Approval,
coverage, backup, routing, or rollback gates; it has promoted an
`INSUFFICIENT_EVIDENCE` result. Its two-field payload is incompatible with the
active six-field fix. The promotion unit permanently authorizes writes. Pinecone
upsert acknowledgement is ignored and verification checks record IDs only, not
the vector or complete serving payload. The active reconstruction recomputes a
fingerprint from received fields instead of comparing an approved fingerprint.
Ambiguous provider failures are recorded `FAILED_FINAL` instead of outcome
unknown pending reconciliation.

**P1 operational findings:** all five systemd application containers are ready
but run image IDs older than current tags/source. `acq-batch` and `cp-test` are
long-running stale containers outside systemd on privileged pipeline networks.
No AskLegal timers are installed, application telemetry is absent, and only the
OTel collector—not Prometheus/Grafana—is deployed. Ignored `var/run/` retains
plaintext credential duplicates; values were not read. The tracked local Claude
permission file grants broad `Bash(sg docker *)` execution.

**Stale records reconciled here:** the official register has 79 endpoints, 56
enabled, with five configured roles, five partial, one blocked, and three outside
V1. `HANDOFF.md`, the relevant `CONTEXT.md` source-boundary facts, this roadmap's
current summary/queue, and this working state now carry the audit result. README,
the V1 topology design, and formal admission JSON still need deliberate
reconciliation after the release-safety decisions are implemented.

**Exact next steps:** freeze real promotion writes and investigate the two orphan
containers; make the release/review/approval/manifest/fingerprint/full-read-back
boundary executable; align control and promotion on one versioned six-field
contract; restore enforced Pyright/Ruff/CI gates; rotate staged credentials;
rebuild and reconcile host images; add timers and telemetry; then refresh formal
admission evidence and run acceptance/recovery/rollback before declaring V1.

## 2026-08-20 — Hong Kong source-connector audit follow-up

**Verified state:** the exact source register loads with fingerprint
`sha256:40e1918882a78a4ef29a095b426cdf20105f77968beee0f0c9ce49689daa0669`:
14 roles, 79 endpoints, 56 enabled; five roles configured, five partial, one
blocked, and three outside V1. The build report has 63 technically ready and 16
blocked endpoint procedures. All source-connector and acquisition-worker tests
pass: 89 passed in 1.46 seconds.

**Runtime boundary:** the V1 acquisition worker registers only direct endpoint,
multi-endpoint, and HKeL Gazette-window work. The generic rendered-session,
complete-inventory, and Patchright implementations exist and are tested but are
not schedulable service activities. Five configured roles are operationally
callable; the Gazette special path has live evidence but remains partial because
its completeness unit is one closed date window.

**Defects found by the audit and resolved on 2026-08-21:**
`capture_gazette_window` still has an operational `max_pages=50`, but
`iter_entries` now rejects a publisher-declared later page and an empty
intermediate page as explicit incomplete results. The worker completes the
bounded listing before retaining artifacts or its manifest. The publisher-API
`exchange` path now enforces `max_redirects` iteratively. A focused strict-
Pyright run over this area now fails with 40 errors after the second slice.

**Source work before V1:** wire or explicitly defer every required
rendered/inventory procedure; clear the 40 focused type errors; reconcile the stale
acquisition service description and deployed image; then capture admission
evidence for the exact V1 source subset without treating the three out-of-scope
roles as missing V1 coverage.

## 2026-08-21 — Disposable-branch review, GLD retained, and full HK V1 plan

**User correction and constraint:** `v1-poc-runtime-proven` was a disposable
visual demonstration, not an implementation source. No code may be imported;
all implementation is independently built on `main`. Informational discovery
facts may be considered only after current verification. The same treatment is
recorded for `demo/expo-source-transformation`.

**Branch evidence:** without switching branches, Git shows
`v1-poc-runtime-proven` at `3978674`, an ancestor of current `main` with no
unique commits and 28 `main` commits after it. Its old handoff is superseded.
Useful source discovery is already preserved in current history and design:
GLD acceptance is Cloudflare Turnstile-gated; the HKeL Gazette capability/CSRF
handshake, `/grid` request, page protocol, `VIRTUAL_URL`, language address
construction, date-window rule, retries, and live archive/manifest evidence are
on `main`. No branch code was copied, merged, or cherry-picked.

**Settled source decision, corrected later on 2026-08-21:** direct
`HK-LEG-GLD-EGAZETTE` remains inside V1 as the originating/current-publication
source and earliest official Gazette feed. GLD's official Important Notices
identify GLD as publisher of all Gazette parts and describe selected legal
supplements as *also* available on HKeL “for information”. HKeL Gazette remains
complementary backcapture, recovery, reconciliation, and gap-detection evidence,
not an upstream replacement. This supersedes the earlier same-day retirement
decision. GLD remains technically partial because the Cloudflare Turnstile gate
must not be bypassed; V1 needs a lawful repeatable or explicitly approved bounded
manual procedure with completeness/no-change proof. The current `main` register
is therefore already directionally correct and remains executable truth at 79
endpoints, 56 enabled, 5 configured, 5 partial, 1 blocked, and 3 outside V1.

**Full-jurisdiction interpretation:** the complete Hong Kong V1 uses the
accepted four-family scope—three Hong Kong Legislation scopes, proposition-level
binding-court Hong Kong Cases, HKEX Main/GEM Regulatory Materials, and selected
licensed Hong Kong Principles. Only Hong Kong Legislation has a real package
skeleton/checkpoints, and all its scopes remain `NOT_READY`. Cases, Regulatory
Materials, and Principles have no executable real package. If Principles is not
selected/licensed, the release must be named as complete primary-law,
binding-cases, and HKEX coverage rather than complete Hong Kong jurisdiction.

**Fresh validation:** current `main`/local `origin/main` ref is `c4b3ba2`; the
working tree was clean before continuity edits. The ordinary full suite now
passes with 845 tests and four skips after the fifth acquisition slice; the
exact developer bootstrap last passed before those fixes at 785 tests and four
skips. Strict Pyright still fails with 904 errors, including an unchanged 713
across 52 tracked files; the other 191 errors are in ignored local runtime files
under `var/`.
`asklegal.target` is enabled/active with no failed
unit and no AskLegal timer. All five running application image IDs differ from
the current tags; `acq-batch` and `cp-test` remain outside systemd.

**Durable plan:** `.agent/ROADMAP.md` now contains milestones HKV1-0 through
HKV1-10 with exact checkboxes and exit gates for scope/source authority,
engineering gates, acquisition, Legislation, Cases, HKEX Regulatory Materials,
Principles, model/embedding/target admission, real Review/promotion, local host
operation, and complete baseline/acceptance. The dependency-critical first work
is: admit the retained GLD current-publication path and complementary HKeL
backcapture/recovery path honestly; close
promotion trust-chain defects; restore shipping gates; then make source/package
families ready before attempting the complete baseline.

No implementation, source/provider request, credential access, Pinecone
mutation, container stop, deployment, commit, push, merge, or cherry-pick was
performed in this planning task.

### First HKV1-2 implementation slice

Implementation is now in progress on `main`, independently of both disposable
visual branches. The HKeL Gazette iterator no longer returns a short success
when the publisher reports more pages than the operational cap or when an empty
page appears before `lastPage`. The acquisition activity enumerates the complete
bounded window before retaining an addressed PDF or canonical listing manifest,
and it binds the artifact connector only after enumeration so a refreshed grid
session is carried forward. The publisher-API transport now follows redirects
iteratively and enforces the same configured limit as its inert fetch surface;
a same-host loop ends with `REDIRECT_LIMIT_EXCEEDED`.

Validation on 2026-08-21: 22 focused HKeL/transport tests and the ordinary full
suite passed, the latter with 789 tests and four skips. Focused Ruff lint, the
repository boundary checker, contract validator, and `git diff --check` passed.
Strict Pyright still reports the same 45 focused errors already recorded for
this area; this slice did not claim to clear them. Focused Ruff formatting still
reports the already-recorded drift in `v1_pipeline.py` and
`test_hkel_gazette_register.py`; it was not auto-formatted under the current
format-policy blocker.

No official source, credential, provider, Pinecone target, container, or other
external system was accessed or changed. No commit, push, merge, or cherry-pick
was performed.

### Second HKV1-2 implementation slice

All item-specific official endpoint fetches now delegate template resolution to
the shared exact bounded-locator contract. A templated endpoint cannot run with
a missing, extra, or wrong substitution; publisher locators cannot change the
authority, add query/fragment/template syntax, traverse, or exploit ambiguous
slashes/backslashes. Percent-encoded input is encoded as data. An HKeL grid row
outside the declared `hk/` locator shape becomes durable
`SOURCE_CONTRACT_CHANGED` rather than an index error or unintended fetch.

The Gazette register client now raises one of four closed codes:
`INVALID_REQUEST`, `SOURCE_UNAVAILABLE`, `SOURCE_CONTRACT_CHANGED`, or
`INCOMPLETE_OBSERVATION`. It checks both capability/page responses, converts
transport and malformed JSON/paging failures, and preserves the explicit
incomplete-window signal. The worker validates exact `DD/MM/YYYY` calendar
dates, ordering, and `en`/`zh-Hant-HK` before constructing the publisher client.
It checkpoints closed window outcomes and exact per-artifact outcomes for
retained, not published, unavailable, contract-drift, and hostile responses.
An absent or failed selected-language artifact produces `PARTIAL_CAPTURE`; an
incomplete register walk writes neither listing manifest nor artifact.

Validation on 2026-08-21: the connector/acquisition surface passed 113 tests;
the ordinary full suite passed with 809 tests and four skips. Focused Ruff lint
and the repository boundary checker passed. The exact focused strict-Pyright run
now reports 40 errors: 22 in `hkel_gazette.py`, 17 in `v1_pipeline.py`, one in
`v1_infrastructure.py`, and zero in `official_http.py`, down from 45. Contract
validation and final whitespace validation passed after this checkpoint.
The pre-existing focused Ruff formatting drift was not auto-formatted.

No official source, credential, provider, Pinecone target, container, or other
external system was accessed or changed. No commit, push, merge, or cherry-pick
was performed.

### Third HKV1-2 implementation slice

The official 14-role source profile now carries the exact ADR 0032 outage
consequence as executable policy. Register revision `2026-08-21.1` is effective
2026-08-21 with fingerprint
`sha256:93944064e78d314670476758ec4cde7cd042caca2f285858dc906bfb108794b4`.
GLD e-Gazette and the current HKeL inventory are `RELEASE_BLOCKING`; HKeL Gazette
backcapture is `NONBLOCKING`; the remaining roles preserve their accepted exact
consequences.

Because this is a material source-policy contract addition, the register schema
and all fourteen source-profile versions advanced from `1.0.0` to `1.1.0`.
The 79 transport endpoint versions remain `1.0.0`; their endpoint contracts did
not change in this slice.

The reporting boundary now freezes canonical per-source coverage reports and
complete due-source cycle reports. Source reports preserve exact counts,
observation-manifest reference, failure codes, source policy/version, cutoff,
deterministic
disposition, and release/affected-work blocking flags. Cycle reports reject
unexpected sources and source-policy drift, name every missing, duplicate, and
gap source, and release-block missing or failed `RELEASE_BLOCKING` roles plus
ambiguous duplicate accounting. A missing or failed `NONBLOCKING` discovery role
remains visible without gaining release authority.

The HKeL Gazette activity retains one such report for every terminal window.
Complete, partial, unavailable, contract-changed, incomplete, and unsafe paths
are covered; a partial artifact set preserves its strongest consequence in the
report. Every HKeL gap is visible but remains nonblocking and cannot satisfy or
replace the separately due GLD report. Full service assembly over every due V1
source and propagation into the final Coverage Status Manifest remain open.

During the slice, one test file was initially addressed to the misspelled empty
sibling `AskLegal-LgalDBPipeline`. The exact file was moved into this repository
with patches, and only the resulting empty directories were removed with
`rmdir`; no project or user data was deleted.

Validation on 2026-08-21: the ordinary suite passed with 820 tests and four
dedicated-environment skips; the combined acquisition/domain/reporting/source-
connector surface passed 169 tests. Repository-wide Ruff lint, the 168-file
Python boundary check with its 12 existing reviewed exceptions, contract
validation, lock validation, and whitespace validation passed. The new domain,
reporting, and source-profile files pass strict Pyright with zero errors. The
existing focused connector/acquisition debt remains exactly 40 errors, and the
tracked repository baseline remains 713 errors in 52 files. Full Ruff format
check still fails on 15 previously drifting files; the files materially edited
for this slice are formatted.

No official source, credential, provider, Pinecone target, container, or other
external system was accessed or changed. No commit, push, merge, or cherry-pick
was performed.

### Fourth HKV1-2 implementation slice

The existing complete-inventory connector is now a schedulable acquisition
activity and orchestration. Its input deliberately cannot select a member
subset: the scheduler supplies only a registered source, a canonical UTC
observation cutoff, and optional prior member fingerprints. The worker derives
the exact required endpoint/version set from the active register. For
`HK-LEG-HKEL-CURRENT-INVENTORY`, this is exactly the English and Traditional
Chinese XML inventory pair, and the source's `RELEASE_BLOCKING` policy applies.

Every admitted member is retained under its content fingerprint. A
response-bearing contract or hostile-content failure is retained in the
isolated response class; an unavailable response invents no bytes. Only after
all required members have a terminal outcome does the activity write a
canonical observation manifest. Complete and exact-prior no-change captures
record `complete=true` and an aggregate inventory fingerprint. Missing,
contract-changed, or unsafe required members record `complete=false`, carry no
aggregate fingerprint, and produce a release-blocking Coverage Gap, Source
Contract Review, or Quarantine result. No raw response body is returned through
the scheduler result.

The source-coverage report contract now names its generic
`observation_manifest_ref`, so the same fail-closed accounting applies to both
Gazette listings and complete inventories. Full due-source cycle assembly and
propagation into the Coverage Status Manifest remain open, as do the
rendered-session, catalogue, and Patchright schedulable procedures. This slice
is executable wiring and deterministic local proof; no current host timer or
deployment was changed and no official HKeL capture was performed.

Validation on 2026-08-21: 36 focused inventory/Gazette/reporting/connector tests
passed; the ordinary suite passed with 831 tests and four dedicated-environment
skips. Repository-wide Ruff lint, the 169-file Python boundary check with its 12
existing reviewed exceptions, contract validation, lock validation, and
whitespace validation passed. The new inventory proof, reporting, and service
registration surfaces pass strict Pyright with zero errors. Full Pyright remains
at 904 errors, including an unchanged 713 across 52 tracked files; the focused
source/acquisition debt remains 40. Ruff format drift decreased from 15 to 14
files because the materially edited acquisition service is now formatted.

No official source, credential, provider, Pinecone target, container, or other
external system was accessed or changed. No commit, push, merge, or cherry-pick
was performed.

### Fifth HKV1-2 implementation slice

ADR 0100's rendered browser discovery is now a schedulable acquisition activity
and orchestration, without upgrading browser output into source evidence. Its
closed instruction accepts only an endpoint ID, exact endpoint version, and
canonical UTC cutoff. It accepts no URL, locator, host, request, browser policy,
credential, or completeness claim. Before constructing a browser transport, the
activity requires an enabled, fixed, `BROWSER_SESSION`/`DISCOVERY_ONLY` endpoint
with an exact reviewed Patchright policy and a configured or partially configured
source.

The activity retains only the connector's sanitized request-map summary under a
report prefix, or response-bearing failure diagnostics under an isolation prefix,
then writes a canonical terminal attempt report last. Every scheduler result and
attempt report fixes `controlling_evidence`, `completeness_supported`,
`no_change_supported`, `coverage_satisfied`, and `processing_authorized` to
false. It emits no source-coverage report and returns no rendered HTML, cookie,
header, request body, or raw browser state. Exact replay adopts the existing
summary and report but still cannot claim no-change.

Two fail-closed defects in the existing Patchright adapter were repaired before
registration. Sanitization now strips URL user-info as well as query and fragment
data, including on denied requests. Exceeding the observed-request ceiling now
aborts excess requests and marks the discovery truncated, so content admission
returns `UNSAFE_RESPONSE` instead of a successful discovery signal. Sanitized
request rows are sorted before summary serialization for deterministic output.

This wiring does not make a real browser source callable. Both currently reviewed
policies target endpoints that remain disabled or outside V1: HKeL Gazette uses
its separate admitted date-window/grid workflow, and both NPC roles are outside
V1. The only `CATALOGUE_DISCOVERY` endpoint belongs to the out-of-scope official
Gazette archive. Required verified/assisted-copy, Editorial Record,
publication-specification, and GLD Gazette browser products are legal-source
evidence, not discovery signals; they still need inert source-evidence procedures
and Patchright cannot satisfy them. Chromium/runtime supply-chain and Ubuntu host
admission also remain open.

Validation on 2026-08-21: 55 focused rendered-discovery/Patchright/rendered-
connector/inventory/Gazette/reporting tests passed; the ordinary suite passed
with 845 tests and four dedicated-environment skips. Repository-wide Ruff lint,
the 170-file Python boundary check with its 12 existing reviewed exceptions,
contract validation, and lock validation passed. The new rendered-discovery
proof, Patchright adapter, and service registration surfaces pass strict Pyright
with zero errors. Existing repository type and format debt remains separately
tracked.

No official source, credential, browser, provider, Pinecone target, container,
host service, or other external system was accessed or changed. No commit, push,
merge, or cherry-pick was performed.

### Sixth HKV1-2 implementation slice

The acquisition worker now plans one exact periodic source cycle from the
active Hong Kong official-source register. The accepted daily, weekly,
monthly, and on-demand monitoring assignments are executable policy; an
`OUT_OF_SCOPE_V1` role cannot become due. The current full periodic cycle names
exactly Basic Law, direct GLD e-Gazette, the complete current HKeL inventory,
HKeL Editorial Records, and HKeL publication specifications.

Every due role receives a terminal, immutable source-coverage report. The
current HKeL inventory executes its admitted complete-inventory procedure. A
due role whose legal-source evidence procedure is not yet implemented records
an explicit `INCOMPLETE_OBSERVATION` with its exact blocker and outage
consequence; it is never represented as a source call, successful no-change, or
omitted work. Cycle assembly reads each report back from the Primary Vault by
exact version and fingerprint, reparses its canonical bytes, validates cutoff
and register policy, and writes the cycle report last. Missing, duplicate,
unexpected, or altered reports fail closed.

The corpus boundary now carries an exact `SourceCoverageCycleBinding` in the V1
Coverage Status Manifest. Incomplete accounting or any release-blocking source
gap forces every V1 scope to `NOT_READY`; the V1-specific promotion freeze gate
rejects the release before a Promotion Manifest can be frozen. The existing M6
synthetic route retains its legacy generic freeze function, so this addition
does not pretend the incomplete real Hong Kong package is already wired into a
candidate release. Full runtime candidate-flow integration remains HKV1-3 and
HKV1-8 work.

The HKeL Editorial Record evidence path remains an explicit source gap. Local
inspection and informational review of `v1-poc-runtime-proven` found no exact
request contract or connector to reuse; the rendered page still leads through
the publisher's legacy client-capability warning flow. No request contract was
guessed and no disposable-branch code was imported.

The previously recorded focused type debt is cleared: 22 HKeL Gazette errors,
17 acquisition-pipeline errors, and one readiness-infrastructure error are now
zero. The readiness protocol exposes probe metadata as read-only properties,
matching immutable concrete probes while retaining runtime structural
validation.

Validation on 2026-08-21: 109 focused tests passed; the complete local suite
passed with 856 tests and four dedicated-environment skips. All 30 changed
Python files pass Ruff lint and format checks. The exact focused Pyright run
passes with zero errors; the Python boundary checker passes for 173 files with
12 existing reviewed exceptions; contract validation, reproducible contract
package fingerprint
`sha256:7bd2858bd0099271bc5be1e8d5c380521d81fb15bee8a4110de8fe6629d3094e`,
lock validation, and whitespace validation pass. Repository-wide strict
Pyright remains a release blocker at 856 errors total: 665 in tracked Python
and 191 in ignored local `var/` scripts. Repository-wide Ruff format debt is
down from 14 to 13 files.

No official source, credential, browser, model/embedding provider, Pinecone
target, container, host service, or deployment was accessed or changed. The
user authorized committing and pushing this verified checkpoint to
`origin/main`. After that checkpoint, the exact next implementation work is the
remaining Gazette duplicate/moving-page/throttling/restart/manifest-adoption
proof set, followed by source-specific rate, retry, timeout, and outage
profiles.
