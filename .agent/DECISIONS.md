# AskLegal Legal Database Pipeline — Decisions

Only settled decisions belong here. Recommendations and unresolved choices stay
in the design brief and `WORKING_STATE.md` until the user decides them.

## 2026-08-21 — Retain GLD e-Gazette as the V1 current-publication source

The direct `HK-LEG-GLD-EGAZETTE` role remains inside V1 and remains the
release-blocking source for the earliest official Hong Kong Gazette
publication. This supersedes the retirement decision immediately below. The
Government Logistics Department is the Gazette publisher and describes its
eGazette as the site carrying the Main Gazette, Legal Supplements, Special
Supplements, Supplement No. 6, and Gazette Extraordinary. Its official notice
also says the selected legal supplements are *also* available on HKeL “for
information”; HKeL is therefore not the upstream or earliest-publication source.
Verified official references on 2026-08-21:
`https://egazette.gld.gov.hk/en/important-notices` and
`https://egazette.gld.gov.hk/`.

HKeL Gazette remains in scope as independently captured backcapture, recovery,
reconciliation, and gap-detection evidence. It must not replace GLD merely
because it is easier to automate, and its narrower Gazette catalogue must not
be described as the complete current publication feed.

Scope does not waive the source's technical gate. The Cloudflare Turnstile
acceptance path must not be bypassed, and V1 is not source-ready until a lawful,
repeatable acquisition procedure or an explicitly approved bounded manual
procedure is admitted with completeness and no-change proofs. The existing
`main` register correctly keeps GLD visible as `PARTIALLY_CONFIGURED`; no code
from either disposable visual branch is authorized or needed for this decision.

## 2026-08-21 — Retire direct GLD e-Gazette access from V1 — SUPERSEDED

Superseded later on 2026-08-21 by the decision above after distinguishing the
originating/current-publication source from an archival mirror.

The direct `HK-LEG-GLD-EGAZETTE` connector is outside V1. Its Cloudflare
Turnstile-gated acceptance path will not be automated, bypassed, or treated as
a rendered-transport problem. The stable role remains in the source universe as
`OUT_OF_SCOPE_V1` so its identity and the reason for exclusion stay explicit;
its endpoints must be disabled in the current `main` implementation.

V1 will use exact Gazette artifacts hosted by HKeL instead of acquiring them
directly from GLD. This source choice does not by itself prove equivalent legal
fact authority or complete coverage. Before the HKeL artifacts can replace the
release-blocking event-evidence role assigned to GLD by ADRs 0025 and 0032, the
current branch must independently prove the exact artifact relationship and a
complete reproducible inventory for every Gazette class V1 relies on, including
ordinary and Extraordinary publications and any required Main Gazette notices.
The accepted Gazette ADRs and source rulebook must then be amended on `main`.
Until that proof passes, HKeL Gazette remains discovery/backcapture evidence and
the full Hong Kong Legislation package remains `NOT_READY`.

## 2026-08-21 — Disposable visual branches are informational only

`v1-poc-runtime-proven` was used only for visual demonstrations and is not an
implementation source. No code, patch, fixture, contract, or configuration may
be imported or cherry-picked from it. Independently useful discovery
observations may be considered only as non-authoritative information and must be
re-derived, implemented, and verified on `main`.

The same rule applies to the disposable `demo/expo-source-transformation`
detour. Its existing GLD-retirement diff is evidence of the intended decision,
now superseded by the retained-source decision above, and is not reusable
implementation. Verified on 2026-08-21: the local
`v1-poc-runtime-proven` ref is an ancestor of `main`, has no unique commits, and
is 28 commits behind; its durable useful findings are already preserved in
current history or continuity records.

## 2026-08-19 — Register slice is live; HostNameInCertificate is ignored under Encrypt=Strict

SQL Server 2025 now runs as a real service on this host: on the
`asklegal-register` network as `sql-server`, as uid 10001, with its data on the
4.0 TB disk at `/srv/asklegal/sql`, and using the internal certificate installed
at `/etc/asklegal/tls/sql-server/`. It reports TLS 1.2 only and
`forceencryption = 1`.

The application's own strict-TLS factory connects to it: `SELECT 1` returns 1 and
`sys.dm_exec_connections` reports `encrypt_option = TRUE`. Removing the internal
CA from the client refuses the connection with "unable to get local issuer
certificate", so validation is genuinely enforced rather than assumed.

**`HostNameInCertificate` is ignored when `Encrypt=Strict`.** Measured: a bogus
value is accepted, omitting it entirely is accepted, and connecting by IP is
refused with "subject name does not match host name". Hostname validation happens
against the server name used to connect, not against the override.

The security property holds, and holds slightly more strongly than intended,
because the override cannot be used to weaken validation. But
`V1MssqlConnectionFactory` treats `HostNameInCertificate` as the mechanism that
enforces the hostname, and that description is wrong. The parameter is harmless
and stays; the claim about what enforces validation must be corrected to name the
connection server name instead.

Two ordering facts that are easy to get wrong and cost time here. A prepared
`mssql.conf` cannot be mounted over `/var/opt/mssql/mssql.conf` before first
start, because setup writes its own configuration there; TLS settings must be
applied to the initialised instance and the service restarted. And the
certificate and key must be readable by the numeric identity the container runs
as, which is why they are installed under `/etc/asklegal/tls/<service>/` owned
`root:<service-gid>` with the key at `0640` rather than left in the repository
tree.

## 2026-08-19 — Remove the file-only secret rule; deliver credentials by environment

The user removed the accepted file-only secret rule and authorised environment
variables for every credential the POC needs. This supersedes
`SYSTEMD_CREDS_LOAD_CREDENTIAL_ENCRYPTED` as a delivery requirement.

The rule is replaced rather than deleted. `SYSTEMD_CREDS_AT_REST_ENVIRONMENT_DELIVERY`
keeps the parts the user did not ask to lose: credentials are still stored on the
host encrypted by `systemd-creds` and sealed to the TPM, still never written to a
persistent plaintext file, and still never passed as command arguments. What
changes is the last hop — the unit decrypts its credential and hands it to the
service as an environment variable. Arguments stay forbidden because they are
readable by any local user through `ps`, while the environment is readable only
by the same user and root; that distinction was measured earlier and still holds.

Two consequences follow immediately. SQL Server is unblocked: environment
delivery is the one method proved to actually set the SA password, so its subject
returns to `PASSED_WITH_FINDINGS` and `SQL_CREDENTIAL_DELIVERY_DECISION` is
closed. The Versity exception is retired, because environment delivery is no
longer an exception to anything; its bounded-exception record is removed while
the exception *mechanism* stays implemented and tested against a synthetic
fixture, so a future relaxation still has to be named, scoped, and justified.

The residual risk is now uniform and worth stating plainly: any process running
as a service account can read that service's credentials from its own process
environment, and any process running as `docpro` can read every container's
environment through the Docker socket. The vaults' immutability protections are
independent of key possession, so preserved evidence still cannot be silently
rewritten by someone holding the keys.

The five repository applications keep their existing file-based credential
loader. Nothing forces them to change, it already works and is proved, and
rewriting it would be churn without benefit. They can be moved to environment
delivery if uniformity is later preferred.

## 2026-08-19 — Correction: SQL Server does not honour MSSQL_SA_PASSWORD_FILE

The 2026-08-18 entry below records that "SQL Server **passes the accepted rule
unchanged**" because the pinned 2025 image "supports `MSSQL_SA_PASSWORD_FILE`".
**That conclusion is wrong and is withdrawn.**

Measured, same pinned image, two fresh instances, the identical password value
`Str0ng!Passw0rd#2026`, empty data directories, nothing else different:

- delivered as `MSSQL_SA_PASSWORD` — `SELECT 1` returns 1, login succeeds;
- delivered as `MSSQL_SA_PASSWORD_FILE` — `Login failed for user 'sa'`, from
  `sqlcmd` inside the container as well as from the application image.

Both instances start and log "SQL Server is now ready for client connections".
The earlier proof inferred success from that message and from surviving a
restart. Neither shows the SA password was taken from the file. It never
authenticated with the value, so it never tested the property it claimed.

This is the same failure shape as the rotation finding recorded below: the
service looks healthy while the security property does not hold. Two out of the
three executed SQL conclusions have now turned out to be reported rather than
measured, which is a reason to re-examine any remaining claim resting on a log
line instead of an observed effect.

The SQL subject moves from `PASSED_WITH_FINDINGS` to `FAILED`, and
`SQL_CREDENTIAL_DELIVERY_DECISION` is a new blocker. The accepted file-only rule
is **not** being silently relaxed. The choice is the user's, and the options are:

1. **In-database bootstrap.** Initialise with a throwaway value, then immediately
   set the real password from the systemd credential file with
   `ALTER LOGIN sa WITH PASSWORD`, which the rotation work already proved works.
   The throwaway still passes through the environment once, but the real
   credential never does. This is the recommendation.
2. **A bounded exception** for the SA bootstrap password only, matching the one
   already granted to the Versity root keys, delivered by environment and never
   as a command argument.
3. **Neither**, and SQL Server is reconsidered as the register product.

Nothing was decided here and no rule was changed.

## 2026-08-19 — Issue an internal certificate authority for the V1 POC host

One offline authority, valid on this host only, signs one server certificate
each for `sql-server`, `vault-primary`, `vault-recovery`, and `review-api`. The
authority is 4096-bit and valid five years with `pathLen:0`; the server keys are
2048-bit and valid 397 days, each carrying exactly one DNS name.

Verified rather than assumed. For all four names: a handshake against the
authority succeeds, a wrong hostname is rejected, and an unknown authority is
rejected — twelve checks, all passing. SQL Server then loaded its certificate
and reported "Successfully initialized the TLS configuration" with
`forceencryption = 1`.

Start times are backdated one day. The first issue failed every handshake with
"certificate is not yet valid": this host runs on Hong Kong time, so a
certificate starting at midnight UTC is not yet valid locally that morning.

Private keys live under the ignored `var/tls` tree, are never printed or logged,
and appear in no manifest. `infrastructure/poc/tls_material.json` records only
public facts and fingerprints.

Two mistakes worth keeping. Mounting a prepared `mssql.conf` read-only over
`/var/opt/mssql/mssql.conf` breaks first-time setup, because the server writes
its own configuration there during initialisation; TLS settings must be applied
after the instance exists. And the slim base image lacks the Kerberos and
`libltdl` libraries that the bundled ODBC driver links against — importing
`mssql_python` succeeds while opening a connection fails with "Failed to load
the driver". Seven Debian packages are now pinned by hash in
`application_system_packages.json` and installed offline during the build.

## 2026-08-18 — Keep the static gates parseable by the host's own python3

`ruff format` rewrote `except (A, B, C):` into PEP 758's unparenthesised
`except A, B, C:`. That is correct for the repository's declared
`target-version = "py314"` and runs fine under the pinned Python 3.14.7. It is a
**syntax error** under the Ubuntu host's system Python 3.12, which is the
interpreter the documented developer command `python3 -m tools.dev_test` uses.

Commit `b38c184` shipped exactly that in `tools/v1_poc_host_admission.py`. Every
static V1 gate and the whole developer suite failed to import. The commit was
made without the suite passing.

Two rules follow. First, `tools/` code that the host interpreter must import
avoids constructs newer than Python 3.12; where a multi-type `except` is wanted,
prefer the single common base class, which is both equivalent and immune to the
formatter. Second, `tools/tests/test_system_python_entrypoints.py` now parses
every `tools/v1_poc_*.py`, `tools/dev_test.py`, and `tools/python_boundary_check.py`
with `ast.parse(..., feature_version=(3, 12))`, so the next occurrence fails at
test time rather than at the next person's first command.

This is not a ruff defect and the formatter is not being switched off. It is a
real gap between the repository's target interpreter and its documented
entrypoint interpreter, and the guard names that gap instead of hiding it.

## 2026-08-18 — Allocate static UID/GIDs 3000-3014 and align every container to them

The credential proof established that `LoadCredential` writes a `0400` file owned
by the unit account, so a container under a different numeric UID cannot read its
own credential. Numeric identity is therefore a constraint, not a preference.

Ten host accounts take UID/GID 3000-3009, one number each, verified free on this
machine against `/etc/passwd` and `/etc/group`. Five pathless container services
— both scheduler emulators and the three egress proxies — take 3010-3014 as
**container-only reservations**: the numbers are held so nothing else can take
them, but no host account is created, because those services own no host path.
SQL Server keeps its image-defined `10001`, which is a measured fact read from
the pinned image, not a choice.

The range sits above the login user (1000) and Ubuntu's system range, below
`UID_MAX` (60000), and clear of Docker's subuid base (100000). The checker now
rejects a root runtime UID, a shared UID, a split UID/GID, a source that does not
match the service, and any widening of the range that could reach a real account.

Accounts remain uncreated; creation needs root and is the user's step.

## 2026-08-18 — Resolve the 25 logical destinations from the topology, not by hand

Each application's destinations are now bound to an exact host, port, scheme, and
shared network. The checker derives the expected value from `topology.json` and
compares, so changing a listener in the topology invalidates the resolution
rather than silently leaving a stale address behind.

Review is resolved as `HTTPS` rather than plain HTTP. Control carries a
`review-client` credential to it, and sending that over a plaintext link — even
on a private container network — is not defensible when an internal CA is being
created for SQL and both vaults anyway. The Durable Task emulators stay
`GRPC_PRIVATE_NO_TLS`, which the accepted topology already records: their
authority rests entirely on network isolation.

## 2026-08-18 — Prove image reproducibility by installed content, not image id

The five application images build offline from the digest-pinned base image, the
hash-locked wheelhouse, and the exact workspace wheels, with `--network none`.

Two builds from a cleared builder cache produce **byte-identical installed
trees** for all five images: the digest covers every file's path, mode, size, and
contents under `/opt/asklegal`. The Docker **image ids differ**, because Docker
embeds a creation timestamp in the image config.

The contract records exactly that: `reproducibility_state` is
`TWO_BUILDS_CONTENT_IDENTICAL` and `image_id_stability` is `NOT_CLAIMED`, with
the reason stored beside it. Claiming byte-identical images would be false, and
the checker now rejects that claim if someone writes it in.

## 2026-08-18 — Select the remaining upstream products and allocate the private subnets

The four unselected upstream products are chosen and pinned by linux/amd64
digest, resolved read-only from their official registries:

- OTel Collector Contrib `0.159.0`;
- Prometheus `v3.13.2`;
- Grafana OSS `13.0.2`, the newest published on that repository, not the
  `13.1.3` tag which exists only for the non-OSS build; and
- Squid `6.6-24.04_edge` from Canonical as the egress proxy.

Squid resolves the previously open "selected egress proxy" question. The
accepted topology already fixes port 3128 and allowlist-based outbound control
on all three egress services, which is Squid's native model, so this follows the
design rather than introducing a new one. Envoy would offer finer TLS control
and remains a later option if per-destination inspection is needed; nothing in
V1 requires it. Canonical's build is chosen for its Ubuntu 24.04 base, matching
the host.

Eleven of sixteen services are now digest-pinned. The five remaining are the
repository's own application images, which must be built rather than selected.

Ten collision-free private `/24` subnets are allocated from `10.90.0.0/16`, one
per declared network. That range avoids every network in use on this host: the
`192.168.8.0/22` LAN, the `10.2.0.0/16` VPN interface, and Docker's own
`172.17.0.0/16` bridge. It also sits outside Docker's default automatic
allocation pool of `172.16.0.0/12`, so Docker cannot later assign a colliding
subnet to an unrelated network.

The host checker now validates the allocation rather than accepting a declared
list: every declared network must appear exactly once, each value must parse as
a strict private `/24`, and no subnet may overlap another or any reserved host
network. Six focused cases cover a missing network, an overlap, a public range,
a wrong prefix length, a collision with the Docker bridge, and a malformed
value. `PRIVATE_SUBNET_SELECTION` is closed, leaving
`CREDENTIAL_INTERFACE_PROOF` and `HOST_PACKAGE_LOCKS` as host blockers.

No image was pulled, no network was created, and no service was enabled by this
decision.

## 2026-08-18 — Rotate SQL Server credentials in-database, never by swapping the credential file

The remaining two proof steps were executed. `systemd` credential delivery
**passes**: `LoadCredential` places the value in an ephemeral per-unit directory
as a `0400` file owned by the service user, that directory is bind-mounted into
the container, SQL Server starts from it, and the exact value authenticates
(`AUTH_OK`) while a wrong value is refused (`Login failed for user 'sa'`). The
value appeared on none of five surfaces: container environment, container
arguments, service logs, systemd unit properties, and the journal.

`ROTATE_AND_REJECT_OLD_VALUE` **fails, and fails silently.** Writing a new value
into the credential file and restarting the unit does not rotate the password.
Measured: the new value was refused and the old value still authenticated, while
the service started normally and reported no error. SQL Server consumes
`MSSQL_SA_PASSWORD_FILE` only when initializing an empty data directory; once the
database exists the stored password wins and the file is ignored.

The accepted rotation procedure is therefore an in-database
`ALTER LOGIN sa WITH PASSWORD = N'<new>'`, executed against the running instance.
That was proved end to end: the statement returned `ROTATED`, the new value then
authenticated, and the old value was refused. Operational runbooks must use this
path. A file swap must never be treated as a completed rotation, because the
service gives every outward appearance of success while still accepting the old
credential — the dangerous case is believing a compromised password has been
retired when it has not.

One integration constraint follows from delivery. The credential file is mode
`0400` owned by the systemd service account, so the container process must run
under the same numeric UID or it cannot read the file. This is the concrete
reason the host-identity contract leaves numeric UID allocation and container
UID/GID mapping open; those values must be aligned per service rather than
chosen freely. The proof ran the container under the invoking user's UID to
demonstrate the mechanism.

All proof state was removed and verified: no containers, no user units, no
scratch directories.

## 2026-08-18 — Keep file-only secrets for SQL Server; grant Versity root keys a bounded exception

The credential-interface question is answered by execution rather than vendor
documentation. Both images were pulled by digest on the Ubuntu host and run with
networking disabled and synthetic throwaway credentials.

SQL Server **passes the accepted rule unchanged**. The pinned 2025 image supports
`MSSQL_SA_PASSWORD_FILE`. Started from a read-only mounted file it reached "SQL
Server is now ready for client connections" and survived a restart without the
value being supplied again. The exact synthetic value did not appear in container
configuration, container arguments, process arguments, process environment, or
service logs. Only the file path is visible. No relaxation is needed or granted
for SQL Server, and the earlier expectation that it would fail was wrong.

Versity Gateway `v1.7.0` **cannot meet the rule**. Its complete option set exposes
root credentials only as `--access`/`--secret` arguments or the
`ROOT_ACCESS_KEY_ID`/`ROOT_SECRET_ACCESS_KEY` environment variables. There is no
file input. Measured exposure with both forms supplied: container environment,
container arguments, process arguments, and process environment all expose the
value; service logs do not, and the value is not persisted to the data,
versioning, or sidecar directories.

The user selected the bounded exception over a general relaxation. The exception
covers **only** the two Versity root bootstrap credentials on this internal
single-host POC. The accepted `SYSTEMD_CREDS_LOAD_CREDENTIAL_ENCRYPTED`
file-only rule continues to govern every other credential, including SQL Server's.
Implementations must supply the Versity root keys through the environment only,
never as command arguments, because arguments are readable by any local user
through `ps` while the environment is readable only by the same user and root.

Two facts bound the residual risk. Versity does not write the root secret to
disk, so exposure is runtime-only. More importantly, the vault enforces
immutability independently of who holds the keys: a bucket created with Object
Lock reported `ObjectLockEnabled: Enabled` and `Versioning: Enabled`, an object
written under `COMPLIANCE` retention with legal hold returned both values on
read-back, and deleting that locked object was refused with `AccessDenied`.
Possession of the root keys therefore does not permit silent rewriting of
preserved evidence, which is the property the design exists to protect.

The Versity linux/amd64 artifact is now resolved and pinned in this record as
`ghcr.io/versity/versitygw@sha256:ef1c6bf0180abd9583da8a0466b3cba1cfc1ed368afebdf7280c0774081d2c82`,
which closes the `VERSITY_VERSION_AND_DIGEST` blocker. Versity's admin account
mechanism is a later path to retiring the exception; it is not V1 work.

This is a partial proof and must not be recorded as a complete one. The
product-interface question, the leak-surface question, and the object-lock
question are settled. `DELIVER_SYSTEMD_CREDENTIAL_FILES` and
`ROTATE_AND_REJECT_OLD_VALUE` were **not** executed: the file was delivered by a
container bind mount rather than `systemd-creds`, no systemd unit exists to
inspect, and no rotation was attempted. All throwaway containers and state were
removed, verified by name.

## 2026-08-18 — Permit one named account in the host `docker` group

The user installed rootful Docker Engine 29.7.2 and explicitly authorized adding
their login account to the host `docker` group. The previously accepted rule
forbade any non-root member of that group, because membership grants
password-free root-equivalent control of the daemon.

The rule is amended rather than removed. `permitted_docker_group_members`
replaces `docker_group_non_root_members_forbidden`, and the host check now
requires the reported membership to equal that exact list. The accepted value is
`["docpro"]`. Any additional, renamed, or unexpected member still fails closed
with a `CONTAINER` finding, so the check keeps its detection value instead of
being switched off.

This is a deliberate, user-authorized reduction in host isolation for an
internal POC. It is not a finding that the original rule was wrong. The
residual risk is that any process running as `docpro` can control the Docker
daemon without a password, which includes reading and writing any container's
data. Rootless Docker remains the stronger option and was offered; the user
chose the group. Reversing this means removing the account from the group and
restoring the exact-empty membership rule.

The user must run the `usermod` step; the agent has no `sudo` authority on this
host and did not attempt to acquire any. This decision grants no image pull,
container run, credential, source, model, Pinecone, or deployment authority.

## 2026-08-18 — Place both vaults on the 4.0 TB disk and amend the host thresholds

The user chose to keep the Primary and Recovery Evidence Vaults, and the SQL
data path, together on the single 4.0 TB SATA disk. The alternative — splitting
Recovery onto a 500 GB NVMe for real single-disk-loss protection — was rejected
because the disks are asymmetric: a ~458 GB Recovery volume cannot mirror a
4.0 TB Primary, so the stronger class would become a false promise as soon as
the evidence corpus outgrew the smaller disk.

`recovery_class` therefore stays `LOGICALLY_SEPARATE_POC_RECOVERY`, and
`same_physical_disk_required` stays `true`. The POC still does not survive loss
of that disk or of the host, and nothing in this decision claims otherwise.

The accepted thresholds are amended to match the real machine:

- `host_admission_policy.json`: `physical_disk_count` 1 to 3,
  `minimum_disk_bytes` 5,000,000,000,000 to 3,900,000,000,000, and
  `minimum_memory_bytes` 68,719,476,736 to 64,424,509,440;
- `topology.json`: `minimum_ram_gib` 64 to 60, `physical_disk_count` 1 to 3,
  and `minimum_ext4_capacity_tb` 5 to 3.

The memory threshold moved because the old value was unsatisfiable by
construction, not merely too high. Host memory is measured as
`SC_PHYS_PAGES * SC_PAGE_SIZE`, which excludes firmware-reserved memory, so a
genuine 64 GB machine reports 67,252,903,936 bytes and could never meet a
literal 64 GiB minimum. The new value is 60 GiB, which this host clears while
still rejecting a 32 GB host.

`_validate_storage` also changed meaning, not just constants. It previously
required the host to report exactly one physical disk and compared every
required path against that sole disk. It now accepts the declared disk count,
requires all three required paths to share exactly one backing disk, and
applies `minimum_disk_bytes` to that backing disk. Fail-closed behavior is
preserved and extended: an unexpected disk count, a duplicate disk identity, an
unknown backing disk, a path split across disks, or an undersized backing disk
each produce a `STORAGE` finding. Two focused cases were added for the split
and undersized branches.

This changes no runtime authority. The host remains unprovisioned, the composite
gate still returns `V1_POC_NOT_ADMITTED` with 14 blockers, and the three durable
host blockers are unchanged.

## 2026-08-18 — Correct the V1 host storage and development-host facts

The user reported that the previously recorded V1 host description was their own
mistake. The accepted record said one Ubuntu PC with 64 GB RAM and 5 TB on one
physical disk. The actual machine, `docpro-MS-7D99`, has three physical disks: a
499 GB NVMe ext4 root, a second 500 GB NVMe ext4 volume, and a 4.0 TB SATA ext4
volume. Measured memory is 67,252,903,936 bytes.

The user also said they will probably do significant parts of development on
this Ubuntu machine from now on. That is recorded as a direction, not a settled
replacement of the Mac as development host.

Superseded later the same day by the vault-placement decision below, which
amends these values. Three accepted values did not match this machine and were
initially left unchanged pending a separate decision. `minimum_disk_bytes` is 5,000,000,000,000
against a largest single ext4 volume of 4,000,785,104,896.
`minimum_memory_bytes` is 68,719,476,736 against a measured 67,252,903,936.
`recovery_class` stays `LOGICALLY_SEPARATE_POC_RECOVERY`, because a stronger
class must be earned by proved separate-disk vault placement and never inferred
from the existence of more disks. `infrastructure/poc/topology.json`,
`infrastructure/poc/host_admission_policy.json`, their checkers in `tools/`, and
their focused tests are therefore not yet amended; correcting a fail-closed
admission threshold requires the capacity and vault-placement decisions first.

## 2026-08-18 — Move agent continuity files to `.agent/`

On 2026-08-18 the four canonical agent continuity files — `CONTEXT.md`,
`DECISIONS.md`, `ROADMAP.md`, and `WORKING_STATE.md` — moved from `docs/agent/`
to `.agent/`. The move used `git mv`, so file history is preserved.

The rationale is that continuity state is the agent's working material, not
documentation for people. Keeping it under `docs/` places it inside the
human-facing documentation tree and inside any future documentation build. The
new location keeps working state out of documentation builds and out of
human-facing docs.

This supersedes the previous `docs/agent/` location convention. The files stay
tracked in Git and continue to synchronize between machines through the remote;
`.agent/` matches no `.gitignore` rule. Path references in `AGENTS.md`,
`README.md`, `packages/management-register-adapter/README.md`, and
`docs/design/V1_POC_UBUNTU_TOPOLOGY.md` were updated to the new location.

## 2026-08-18 — Use Patchright only for isolated non-controlling discovery

The user selected Patchright for JavaScript-backed official-source access.
Patchright `1.62.1` runs only in the acquisition worker under exact endpoint
policies and an ephemeral, credential-free Chromium context. It may reveal
locators and request contracts, but its rendered output cannot become legal
evidence, prove completeness or no change, or authorize processing. The
connector returns only a sanitized request-map summary; legal source bytes
must be fetched again through an admitted inert connector.

This is the narrow ADR 0100 exception to M4's original active-content rule.
There is no CAPTCHA or access-control bypass, undeclared cross-host request,
persistent browser profile, retained cookie/header/body, authentication, or
automatic terms acceptance. Exact same-host POST paths may be allowed only as
reviewed browser-handshake steps. Patchright and its Chromium runtime require
separate supply-chain and Ubuntu admission before V1 deployment.

## 2026-08-18 — Defer publisher and archive enquiries for V1

The user does not want external technical enquiries sent to HKeL, the
Government Logistics Department, the Government Records Service, or another
publisher/archive at this stage. V1 work will continue using independently
verifiable official interfaces and already authorized read-only access.

External enquiries are not a V1 prerequisite. Sources whose complete technical
access procedure cannot be established independently remain explicitly
`PARTIALLY_CONFIGURED` or `BLOCKED`; they cannot be represented as complete,
silently omitted from coverage accounting, or used to infer no change. This
decision defers external messages but does not prevent further inert endpoint
research, implementation, synthetic evaluation, or work on the configured
source roles.

## 2026-08-18 — Record legal-team clearance for all Hong Kong Legislation sources

The user reported that the AskLegal legal team has confirmed that all source
rights and permissions are green. This clears the independent legal-admission
gate for all fourteen frozen Hong Kong Legislation source roles. The source
register records that conclusion as a separate, dated AskLegal legal-team
attestation reported by the project user; it does not alter or overwrite the
historical publisher notices observed on 2026-08-17.

Legal clearance does not imply technical completeness. Sources whose complete,
bounded acquisition procedure is not yet implemented remain `BLOCKED` or
`PARTIALLY_CONFIGURED`, and disabled endpoints still reject access before
transport. This decision authorizes continued credential-free read-only source
implementation within the prior access scope; it does not authorize corpus
publication, models, embeddings, Pinecone mutation, deployment, or production
routing.

## 2026-08-18 — Continue source engineering while legal review remains pending — superseded

The user directed the project to skip waiting for the legal team's source-
rights work and build the technical source capability first. Engineering may
therefore complete source contracts, safe locator binding, transport ports,
complete-inventory operations, hostile-content controls, deterministic tests,
and disabled runtime composition for all fourteen Hong Kong Legislation source
roles without pausing for the outstanding rights evidence.

This development-sequencing decision governed work while the review was
pending. It is superseded by the later 2026-08-18 legal-team clearance above.
The distinction it established between legal admission and technical readiness
remains in force.

## 2026-08-17 — Authorize bounded read-only Hong Kong Legislation source access

The user authorized credential-free, read-only access to the official sources
needed for all fourteen frozen Hong Kong Legislation source roles across the
three accepted release scopes. This authorization covers endpoint and format
verification, source-contract implementation, bounded capture, and local
validation. It does not extend to Hong Kong Cases, HKEX Regulatory Materials,
other jurisdictions, external messages, publication, deployment, or any remote
mutation.

Publisher terms remain an independent admission gate. User authorization does
not replace a publisher licence, required Government written permission, or a
named accountable owner's acceptance of applicable terms. A role therefore
remains fail-closed when its rights evidence or owner attestation is incomplete,
even if the endpoint is technically reachable.

RSS and similar feeds are discovery or change signals only. They may cause the
pipeline to inspect a complete official inventory, but absence from a feed is
never proof of completeness, legal status, currency, or no change. Release
accounting must continue to reconcile the applicable complete official
inventory and controlling evidence.

## 2026-08-17 — Continue autonomously toward the accepted local V1

The user instructed the agent to work toward V1 and stop only when user input
is genuinely required. This authorizes sustained, dependency-ordered,
repository-only implementation, tests, deterministic local artifacts, and
continuity maintenance within the already accepted local-V1 direction. The
agent should continue through safe reversible work without asking for routine
confirmation.

This instruction does not silently choose unresolved local infrastructure
products or authorize real-source/provider access, credentials, paid calls,
external messages, commits, pushes, deployments, destructive operations, or
production effects. The agent must stop when one of those choices or
permissions becomes materially necessary, or when competing accepted paths
cannot be resolved from repository evidence.

## 2026-08-17 — Use locked Boto3 for the V1 S3-compatible vault boundary

The V1 POC Primary and Recovery Versity gateways use the repository-owned
immutable-vault protocol through Boto3 `1.43.49`, locked in `uv.lock`. The
adapter uses only explicit per-application access pairs, SigV4, path-style
addressing, `us-east-1`, HTTPS with a vault-specific CA bundle, three total
attempts, a five-second connect timeout, and a 30-second read timeout. It does
not use the ambient AWS credential chain.

Provider version IDs are preserved losslessly in canonical URL-safe references.
Writes use conditional create, SHA-256, COMPLIANCE retention, optional legal
hold, exact-version read-back, and exact replay adoption. No delete API is
exposed. This decision selects the application client boundary only: it does
not prove the chosen Versity image, certificates, buckets, versioning/Object
Lock behavior, policies, credentials, restart behavior, or Ubuntu deployment,
and it authorizes no real vault access.

## 2026-08-17 — Route proved Hong Kong events before constructing records

`HKLEG-CURRENT-EVENT-001` records an accepted operative event and exact
Coverage Gap when matching current HKeL consolidation is unavailable. It then
selects exactly one downstream path in accepted order: an eligible
reconstruction plan only while reconstruction capability is explicitly
`ACTIVE_FOR_CANDIDATE_PROCESSING`; otherwise a warned known-stale candidate
when a valid latest applicable verified or assisted HKeL base is held;
otherwise an explicit no-record gap. Incomplete evidence blocks, conflicts and
unbounded affected sets quarantine, and an available current consolidation
returns to the ordinary evidence path.

This checkpoint cannot reconstruct text or emit a Search Record. Its synthetic
active-capability case proves routing logic only and does not activate the real
Hong Kong package or any real reconstruction capability.

## 2026-08-17 — Use the accepted single-Ubuntu-host V1 POC infrastructure

The V1 POC is strictly internal. Development remains on the user's Mac, but the
continuous runtime is one Ubuntu 24.04 x86-64 PC with 64 GB RAM and 5 TB on one
physical drive. Ubuntu is initially the only runtime host; the Mac is not a
runtime dependency.

The accepted POC products and boundaries are:

- **Management Register:** SQL Server 2025 Developer Edition in an exact-
  version, digest-pinned official Microsoft Linux container, private-only,
  with persistent ext4 storage and separate operational-POC and integration-
  test databases. Existing migrations, procedures, roles, concurrency, ledger,
  and recovery contracts remain authoritative. Developer Edition is limited to
  this internal development/test POC.
- **Durability:** the Microsoft Durable Task Scheduler emulator with the
  standalone Python SDK. One general scheduler instance owns control-plane,
  acquisition, and legal-processing hubs; a separate instance owns promotion.
  `systemd` timers create recurring triggers. The emulator is memory-only. On
  loss, the system fences the old execution, reconciles authoritative SQL state
  and effects, and starts replacement work from the last safe checkpoint; it
  never claims lost orchestration history resumed. A persistent supported
  scheduler is required before real production use.
- **Evidence:** separate Primary and Recovery Versity Gateway instances with
  distinct directories, identities, credentials, buckets, policies, and
  endpoints, Object Lock and versioning, application SHA-256 verification, and
  manifest-last writes. Suggested roots are `/srv/asklegal/vault-primary/` and
  `/srv/asklegal/vault-recovery/`. Because both use the same physical disk, the
  exact capability label is `LOGICALLY_SEPARATE_POC_RECOVERY`; it does not cover
  disk failure, theft, or host destruction.
- **Secrets:** Ubuntu `systemd-creds` with `LoadCredentialEncrypted=`. Setup
  detects TPM2, preferring TPM2 plus host-key protection and otherwise using
  host-key mode. Each service has separate credentials; plaintext appears only
  as read-only runtime credential files supplied to that service. Secrets never
  enter Git, images, Compose files, command arguments, plaintext `.env` files,
  or logs. Root compromise can expose them, and total host loss requires manual
  reprovisioning for this POC.
- **Vector serving:** a dedicated isolated Pinecone Cloud POC project. Serving
  uses immutable replacement indexes, verifies a new index before routing
  changes, and uploads only approved Serving Records and necessary metadata.
  SQL Server and the Evidence Vault remain authoritative. Credentials use
  `systemd-creds`; outbound access is restricted to required Pinecone
  endpoints. Pinecone Local or deterministic fakes remain test-only. Exact plan
  selection waits for measured corpus size and confirmed native backup/restore
  and RBAC requirements; Standard is required if those features are necessary
  to the V1 acceptance proof.
- **Operations:** OpenTelemetry Collector, Prometheus, Grafana OSS, and
  persistent forward-secure-sealed `systemd-journald`. SQL Server ledger records
  plus immutable Recovery Vault archives are authoritative audit evidence;
  telemetry, dashboards, and journals are operational aids. Loki is omitted
  initially. Monitoring shares the single host and is unavailable with it.

Every container must be pinned to an exact tested version and image digest.
Services are private by default and least-privileged. This decision supersedes
the earlier assumption that vector serving itself must be local and that
Pinecone is outside V1; Azure application hosting remains outside V1. It does
not authorize deployment, credential creation, real source/model calls, a real
Pinecone write, or any other external effect. Explicit authorization is
required immediately before the first real Pinecone mutation or other external
effect.

## 2026-08-17 — Operate V1 locally

The user set an overall product-direction constraint that V1 must run locally.
Azure implementation is therefore not assumed to be a V1 prerequisite or the
automatic next milestone. The accepted Azure architecture remains a possible
post-V1 deployment design unless a later decision supersedes it.

This earlier direction is superseded in part by the accepted single-Ubuntu-host
POC infrastructure decision above. It settled the operating profile before
products were selected; the newer decision now selects them and restores a
dedicated Pinecone Cloud POC project to V1 scope. The controlled-internet
profile remains:

- all pipeline applications, databases, durable runtime state, evidence and
  recovery storage, and scheduling infrastructure run on Ubuntu;
- controlled outbound access to admitted official legal-source endpoints is
  permitted;
- controlled outbound calls to separately admitted hosted model and embedding
  APIs are permitted; and
- Pinecone Cloud supplies the replaceable vector-serving copy, while Azure-
  hosted application infrastructure is not a V1 runtime dependency.

Exact source endpoints, provider deployments, Pinecone plan and endpoints,
credentials, network allowlists, evaluation profiles, and admission evidence
remain separately gated. This product-direction decision alone authorizes no
external call or implementation.

## 2026-08-17 — Start Hong Kong Legislation package readiness with Ordinances

The user accepted the recommendation to advance one real-package workstream in
parallel with the separately gated M8 platform and explicitly authorized local,
network-disabled implementation. `HK-LEG-ORDINANCES` is the first target because
its policy architecture is complete and it has no unresolved Hong Kong policy
choice; the package still includes and honestly reports all three accepted non-
overlapping Hong Kong Legislation scopes.

The first checkpoint is a frozen `NOT_READY` readiness package, not an
executable or admitted legal package. It must contain the accepted stable source
role universe, exact scope ownership, and named blocker codes without inventing
source bytes, rights, fixtures, adjudicated evaluations, model profiles, named
owner acceptance, or conformance attestations. A `NOT_READY` package may load
for inspection but cannot activate or execute. `HK-LEG-SUBSIDIARY` remains
outside the current implementation target, and
`HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS` retains its mandatory Instruments
& Others review and row-level disposition-registry blockers.

This authorization permits repository code, package artifacts, tests, and
continuity updates only. It does not authorize source access, source-rights
acceptance, model or embedding calls, Azure, Pinecone, backup or routing
mutation, deployment, production activation, commit, or push.

The user then instructed the agent to implement the recommended next slice.
`HKLEG-BASE-INV-001` is therefore the first offline executable conformance rule.
It accounts for each synthetic inventory legal object and resource, requires
exactly one Release Scope owner consistent with legal nature, and has four
closed results: accounted, unaccounted, duplicate-owned, or misassigned.
Passing this checkpoint does not decide legal disposition or produce a record.
The package stays `NOT_READY` because the complete rule/fixture universe and
all real-source, rights, evaluation, owner, and attestation evidence remain
missing. `HKLEG-BASE-OBS-001`, not `HKLEG-BASE-INV-001`, owns cutoff and source-
observation completeness.

The user next instructed the agent to implement that observation rule.
`HKLEG-BASE-OBS-001` now freezes one synthetic cutoff, the exact release-
blocking current-inventory and Gazette source set, and exact rulebook, Release
Scope registry, and publication-specification locks. Missing/incomplete/stale
required observations, mixed cutoffs, lock drift, or a post-cutoff source
change block progression. Only the one frozen-success branch may run
`HKLEG-BASE-INV-001`. This remains offline conformance, not evidence that any
real source observation or legal baseline has been accepted.

The user next instructed the agent to implement the bilingual current-evidence
gate. `HKLEG-BASE-EVID-001` now requires matching English and Traditional
Chinese current XML plus matching official HKeL copies for the exact version.
The copies may be `VERIFIED` or `ASSISTED` under ADR 0081. Missing current
evidence blocks the affected scope, a version or reconciliation conflict enters
Quarantine, and historical XML cannot substitute for a missing current
artifact. The rule emits neither legal disposition nor a Search Record; only a
passing synthetic evidence bundle may advance to `HKLEG-BASE-STATE-001`. This
adds no real-source, processing, activation, or production authority.

The user then authorized the recommended present-state slice.
`HKLEG-BASE-STATE-001` now establishes `OPERATIVE_CURRENT` only when the
inventory and evidence predecessors passed, the complete current item,
provision, structure, mapping, version, and operative-effect facts agree, no
accepted source conflicts, and the written rulebook supports ownership and the
proposed operative disposition. Missing required facts block; partial or
ambiguous location mapping and same-fact source disagreement quarantine;
unknown source semantics block and require Source Contract Review; and an
`InEffect`-style signal without operative-effect proof cannot pass. The rule
keeps legal disposition `NOT_APPLICABLE`, emits no record, and marks historical
assertion scope `PENDING_LIMIT_RULE`; only `HKLEG-BASE-LIMIT-001` may impose the
accepted present-state-only assertion boundary.

`HKLEG-BASE-LIMIT-001` now performs that boundary explicitly. A passing STATE
result may advance only with no proposed historical claim, after which LIMIT
sets `historical_assertion_scope: PRESENT_STATE_ONLY`. Unproved historical
legal events, effective dates, identity or continuity relationships, and
complete historical event chains each block with an exact reason. LIMIT keeps
legal disposition `NOT_APPLICABLE`, emits no record, and advances only its
clean success branch to `HKLEG-BASE-ID-001`.

The sustained V1 instruction next advanced `HKLEG-BASE-ID-001`. The rule emits
allocation requests rather than inventing the concrete opaque ID encodings that
ADR 0011 leaves unsettled. It preserves source and legacy values only as aliases,
blocks their use as authoritative identity, blocks unproved predecessor or
continuity relationships, and quarantines duplicate/continuity ambiguity even
when wording or legacy records appear to match. Only its clean branches may
advance to `HKLEG-BASE-DISP-001`.

The sustained V1 instruction next advanced `HKLEG-BASE-DISP-001`. It assigns
exactly one of the accepted five primary dispositions only from a complete
supported legal basis. An operative event with missing current consolidation
remains an explicit Coverage Gap, and publication or one HKeL signal alone is
blocked rather than treated as current law. Only `SEARCHABLE_CURRENT` advances
to `HKLEG-BASE-REC-001`; every other result remains accounted for without a
record.

The sustained V1 instruction next advanced `HKLEG-BASE-REC-001`. The rule uses
the accepted ADR 0021 canonical bilingual rendering and the repository-wide
six-field Serving Record contract. Its local metadata profile values are
explicitly synthetic conformance values, not an admitted production profile.
It rejects legacy identity carry-forward, incomplete bilingual alignment,
non-canonical rendering, and unapproved authority notes; only one exact
candidate advances to `HKLEG-BASE-REL-001`.

The sustained V1 instruction next advanced `HKLEG-BASE-REL-001`. It requires
complete initial-baseline accounting for every accepted dimension and records
that the first release has no predecessor. Missing or duplicate objects and
locations, inconsistent disposition outputs, missing gap/quarantine/
investigation references, and unresolved completeness gaps all block. A pass
only authorizes candidate Corpus Release construction; it does not publish,
approve, promote, or deploy anything.

The sustained V1 instruction next advanced `HKLEG-BASE-REVIEW-001`. It opens
only one bounded historical investigation for a named material uncertainty and
binds its question, affected objects, registered source roles, permitted fact,
stopping condition, and responsible Legal Desk. It blocks clear-item history,
whole-corpus requests, unregistered sources, and mismatched fact scope. This is
an offline task contract and performs no source access.

## 2026-08-16 — Authorize and complete the local/synthetic M7 milestone

The user's instruction "M7" authorizes the complete offline end-to-end
milestone defined by `docs/design/M7_END_TO_END_CONFORMANCE_PLAN.md`. It
authorizes repository tooling that composes the already authorized M3–M6 local
boundaries, the stable `asklegal-local` CLI, all 32 named deterministic
scenarios, ignored synthetic state, conformance tests, and continuity updates.
It does not authorize a real source/model/embedding/Pinecone/backup/routing
call, Azure or infrastructure work, deployment, corpus publication, production
effect, commit, or push.

The local conformance composition remains tooling exposed by an additional
control-plane console entry point; it is not a sixth deployable application.
The five applications still do not import one another, production capability
ownership and the 5-application/14-package architecture policy remain
unchanged, and every external boundary uses an in-process or filesystem fake.

Completion requires the accepted stable commands, exact marked-root reset,
`E2E-001` through `E2E-032`, an independently declared result/fact/effect
catalogue, network denial, and two clean path-distinct executions with a byte-
identical report. The report says only `local synthetic platform proved`.
The protocol's stale pre-M3 count of 18 workspace builds is reconciled to the
current closed 19-member workspace; no member or architecture boundary is
added by that correction.
This proves that the complete local pipeline works; it does not admit a real
jurisdiction package, provider, Azure platform, Pinecone target, Ask.Legal
route, deployment, or production operation. M8 remains separately gated and
admin-portal integration remains deferred.

## 2026-08-16 — Authorize and complete the local/synthetic M6 milestone

The user's instruction "M6" authorizes the complete locally provable Review,
Approval, corpus, and promotion milestone defined by
`docs/design/M6_REVIEW_AND_PROMOTION_PROTOCOL.md`. It authorizes immutable
local artifacts, real in-memory governance behavior, provider-neutral ports,
no-network deterministic fakes, the promotion orchestrator, conformance tests,
and continuity updates. It does not authorize a real embedding/model call,
Pinecone, provider-native backup, Ask.Legal routing or slot swap, Azure,
deployment, corpus publication, production effects, commit, or push.

Contract package 1.5.0 adds the frozen Proposal Package Manifest and exact
Embedding Profile, Request, and Receipt objects. The local profile is issued
only for the reserved `LOCAL_FAKE` provider with an exact `UTF8_BYTES`
token-count contract; this is test behavior and does not replace the accepted
Azure OpenAI/Foundry production boundary or choose a deployed model.

Review HTTP commands now reach the authoritative Approval behavior: one named
delegated `PipelineAdministrator` may comment, approve, reject, or revoke with
a reason. Consumption remains single-use. An exact retry of the same execution
lineage returns the consumed result, while a different lineage is rejected;
current role, manifest fingerprint, base state, validity window, and every
bound predicate are rechecked.

Replacement promotion verifies the exact target definition, IDs, serving
fingerprints, metadata text, vectors, deterministic retrieval, backup, routing
compare-and-set, and post-cutover generation before success. A lost
acknowledgement is reconciled against enumerated actual state. Provider-native
backup and the separately administered recovery copy return distinct verified
receipts. Rollback uses
only the exact retained predecessor. Retirement represents only one exact
manifest-declared inactive target name; no wildcard, prefix, metadata, or
delete-all operation exists.

## 2026-08-16 — Authorize and complete the local/synthetic M5 milestone

The user's instruction "M5" authorizes the complete locally provable Legal
Processing and executable Source Rulebook Package milestone defined by
`docs/design/M5_EXECUTABLE_LEGAL_DESK_PACKAGE_PROTOCOL.md`. The implementable
exit boundary is the cross-cutting engine plus one reserved test-only package;
the accepted protocol explicitly forbids fabricating real source rights,
inventories, bytes, named owners, adjudicated truth, or model admission to make
a Hong Kong package appear ready.

Contract package 1.4.0 therefore governs the executable package root, exact
scope activation, Rule Execution Result, bounded Semantic Task Request/Decision,
and candidate artifact. The implementation uses one canonical-layout
`ZZZ`/`LOCAL_SYNTHETIC`/`TEST_LEGAL_MATERIAL` package, a register-bound local
activation, closed deterministic rule execution, an always-disabled default
semantic runner, one exact no-network deterministic fake for primary/challenge
proof, and evidence-bound idempotent candidate/result recording.

The M5 runtime catalogue mirrors all twelve semantic stages already allocated
by accepted design: two Case Proposition stages, two later-treatment stages,
four HKEX Regulatory stages, two Gazette-event stages, and two Reconstruction
Plan stages. They form six exact primary/secondary pairs. A pair must use
distinct task profiles and prompt fingerprints while binding the same package,
subject, preserved evidence, and input. This closes a reconciliation defect in
which the first synthetic implementation reused one Gazette task/profile for
both passes; no new generative allocation was invented.

M5 completion means the local platform and its only enabled synthetic scope
pass. It does not mean Hong Kong Legislation, Cases, HKEX Regulatory Materials,
or Principles is ready. Those packages remain `NOT_READY` until their separate
real-source, owner, legal, fixture, evaluation, model, and attestation evidence
passes. No real source, Azure OpenAI/model, embedding, Pinecone, backup,
routing, deployment, corpus publication, production effect, commit, or push is
authorized by this instruction.

## 2026-08-16 — Authorize and complete the entire local M4 milestone

The user's instruction "M4" authorizes the complete local Evidence and
Acquisition milestone defined by
`docs/design/M4_ACQUISITION_AND_EVIDENCE_PROTOCOL.md`. It authorizes
deterministic synthetic connectors, local filesystem-backed primary/recovery
vault fakes, exact evidence/acquisition contracts, acquisition-worker
orchestration, Management Register acquisition outcomes, conformance tests,
and continuity updates. It does not authorize real source access, Azure Blob
or other remote storage, source credentials, M5–M7 implementation, model or
embedding calls, Pinecone, backup/routing mutation, deployment, production
effects, a commit, or a push.

Contract package 1.3.0 adds Connector Request, Watcher Result, Scraper Result,
Vault Object Receipt, Evidence Object, Evidence Package, and Acquisition
Outcome. Watchers and Scrapers have closed outcomes; source-contract drift,
unavailability/incompleteness, and hostile input enter Source Contract Review,
Coverage Gap, and Quarantine respectively. Only one exact stable complete
capture with a manifest-last package and verified primary/recovery receipts is
legal-processing eligible. Every other outcome grants no downstream work.

The acquisition worker retains only primary-vault authority. Recovery-copy
ownership remains exclusive to the promotion-worker boundary under ADR 0094
and the architecture policy. M4 therefore uses a two-phase protocol: the
acquisition worker commits the primary package, an independently invoked local
recovery copier produces exact verified receipts, and the acquisition worker
records `PRESERVED` only after validating that receipt against its pending
manifest. This implements M4 without silently widening acquisition
credentials. The local filesystem adapter proves behavior only; it makes no
Azure WORM, RBAC, network, regional, retention, or recovery claim.

## 2026-08-16 — Authorize and complete the entire local M3 milestone

The user's instruction "Do M3" authorizes the complete local implementation
and proof defined by `docs/design/M3_APPLICATION_INTERFACE_PROTOCOL.md`. It
does not authorize M4–M7 capability implementation, external source/model/
embedding/Pinecone/backup/routing/recovery calls, Azure changes, deployment,
production effects, a commit, or a push.

M3 uses exact locked FastAPI 0.141.1, Starlette 1.6.0, Pydantic 2.13.4,
Uvicorn 0.52.3, HTTPX 0.28.1, and AnyIO 4.14.2. FastAPI and Uvicorn remain
direct dependencies of only the control-plane and Review applications. A new
framework-free `asklegal-application-runtime` package prevents security-
boundary logic from being duplicated while keeping the workers free of HTTP
frameworks; it owns exact configuration, local identity/register/pagination/
projection/task adapters, leases, fencing, shutdown, and fail-closed effect
ports, but no application authority.

The control plane exclusively owns `proposal_package_prepare` and gains only
the accepted read-only corpus, promotion, and evidence dependencies. The
Review API retains Approval, rejection, and revocation. Production mutations
remain exclusive to the promotion worker. All five application boundaries
start independently with synthetic local configuration and adapters; every
source, vault, model, embedding, target, backup, routing, recovery, Azure, and
production effect remains disabled. The evolved architecture policy covers 5
applications, 14 packages, 80 internal edges, and 31 capability ports, and the
offline package proof covers 19 reproducible wheels.

## 2026-08-16 — Authorize and complete the entire local M2 milestone

The user replaced the earlier slice-by-slice M2 authorization with the direct
instruction to "just complete M2." This authorizes the remaining local M2
domain, typed Management Register port, deterministic fake, forward-only SQL
migration/procedure, conformance-test, real local SQL Server proof, and
continuity work. It does not authorize M3 runtime implementation, external
source/model/embedding/Pinecone calls, Azure changes, deployment, production
effects, a commit, or a push.

M2 is complete against `M2_DOMAIN_AND_REGISTER_PROTOCOL.md`. The accepted
command/result/effect objects and five lifecycle machines are joined by an
explicit quarantine-to-new-Work-Item re-entry rule; the typed store and fake
prove replay, collisions, durable rejections, monotonic versions, concurrent
winners, atomic failure, effect ownership, renewable leases, fencing,
attempts, cancel-before-effect, one terminal receipt, projections, explicit
policy state, and digest-verified recovery. Migration `000002` is a
fingerprinted nine-batch expand package over the retained `000001` proof and
adds the common SQL register substrate and procedure-only identities for all
five applications. A fresh digest-pinned SQL Server proved the complete exact
migration prefix, replay/stale behavior, event/intent atomicity, effect
claims/receipts, projections, recovery rows, ledger verification, and direct
DML denial. Production settings and operational admission remain later gates.

## 2026-08-16 — Implement the bounded M2 command and effect contracts

The user explicitly authorized the next bounded M2 implementation slice:
normative Command Envelope, Command Result, Effect Intent, and Effect Receipt
contracts plus pure immutable Python domain objects, conformance/failure tests,
and continuity updates. It authorizes no Management Register expansion,
application runtime, effect adapter, external call, Azure operation,
deployment, production action, commit, or push.

Contract package 1.2.0 now contains those four objects, eight independent
positive/negative fixtures, exact reference and identity additions, and the
closed effect-type catalogue. Command payloads bind one exact command-specific
contract and immutable payload-object reference. Effect type, exclusive owner,
capability, and sanitized destination class are one closed binding; destination
coordinates and secrets are never contract fields.

The implementation resolves one objective representational contradiction in
the accepted protocol without changing product behavior. `EXACT_REPLAY` cannot
be a newly persisted result while also returning the original result
byte-for-byte, and `INDETERMINATE` is a transport state rather than a business
fact. Durable `CommandResult` therefore contains only `APPLIED` or a closed
rejection. Submission resolution separately reports `RESULT_RECORDED`,
`EXACT_REPLAY`, `COMMAND_ID_CONFLICT`, or `INDETERMINATE`; conflict and
indeterminate resolution create no second business result.

## 2026-08-16 — Complete and publish the bounded design reconciliation

The user explicitly authorized completing the bounded accepted-design cleanup,
then committing and pushing the reviewed accumulated repository checkpoint.
The cleanup keeps the accepted architecture unchanged and reconciles M2
lifecycle prose, M3's human authority table, M6 review timing, ADR 0099 status
wording, and the canonical design.

The version 1.1.0 contract amendment removes `approval_decision.valid_until`
and the obsolete `APPROVAL_EXPIRED` state; invalid manifest evidence or a
failed bound predicate instead creates `APPROVAL_INVALIDATED`. Coverage Status
Manifest version 1.1.0 removes `signature_policy_state` and requires per-scope
verification time, exact gap/Quarantine/source-failure references, and a closed
warning code matching the scope status. Positive and negative fixtures bind
both amendments. This supersedes only the implementation-pending clauses in
the earlier Decision 2 and Decision 6 records; their product decisions remain
unchanged.

Commit and push authority covers this reviewed repository checkpoint only. It
does not authorize a pull request, deployment, Azure operation, source access,
model/provider call, Pinecone operation, publication, or production effect.

## 2026-08-16 — Count retries only after processing starts

For the final ordered lifecycle-correction ambiguity, decision 6, the user
approved the simple rule that a retry counts only after processing actually
starts. Before start, delivery retries keep the item `WORK_DISPATCHED`, reuse
the stable dispatch identity, and consume no work-attempt allowance. After a
`WORK_RUNNING` attempt reports a retryable failure, the item may enter
`WORK_RETRY_WAIT`. A permanent delivery problem becomes `WORK_BLOCKED` or
`WORK_FAILED_FINAL` under the already approved classification.

## 2026-08-16 — Use one recurrence and supersession rule

For ordered lifecycle-correction decision 5, the user approved one common rule
for Source Contract Reviews, Coverage Gaps, and Quarantines. Terminal records
never reopen or change. A non-terminal record becomes `SUPERSEDED` only when its
subject, scope, or underlying definition materially changes and one new linked
`OPEN` record identifies the replacement. A recurrence after terminal closure
creates a new linked `OPEN` record without mutating the predecessor. Mitigated
Coverage Gaps remain non-terminal and may therefore be superseded under this
rule.

## 2026-08-16 — Allow an unresolved Coverage Gap to change mitigation

For ordered lifecycle-correction decision 4, the user approved direct guarded
transitions between `MITIGATED_CARRY_FORWARD` and `MITIGATED_WITHHOLDING` when
the underlying gap identity and affected scope are unchanged. Each switch
requires a new authenticated administrator decision and exact evidence while
the gap remains visible and unresolved. `SUPERSEDED` is reserved for a changed
scope or underlying cause requiring a new linked gap. Only
`RESOLVED_COMPLETE` closes the gap.

## 2026-08-16 — Use four operator-facing Work Item classifications

For ordered lifecycle-correction decision 3, the user approved a simplified
operator-facing classification while retaining the detailed machine states for
automation and audit: Completed is `WORK_SUCCEEDED` or `WORK_NO_CHANGE`; Needs
follow-up is `WORK_BLOCKED` or `WORK_QUARANTINED`; Stopped is `WORK_CANCELLED`
or `WORK_FAILED_FINAL`; and Retrying is the non-terminal `WORK_RETRY_WAIT`.

Every terminal Work Item remains closed and later continuation creates a new
linked work item. Only `WORK_RETRY_WAIT` retains the same work identity and
immutable inputs for another attempt. Cancellation must derive from an
authorized parent-run cancellation or exact system stop command before an
irreversible checkpoint. Quarantine is reserved for evidence, legal, or
semantic uncertainty with a linked Quarantine record.

## 2026-08-16 — Classify pre-promotion Pipeline Run terminal outcomes

For ordered lifecycle-correction decision 2, the user approved retaining
`RUN_BLOCKED`, `RUN_CANCELLED`, and `RUN_FAILED` as possible terminal outcomes
from every applicable pre-promotion state. `RUN_BLOCKED` means a potentially
correctable condition prevents safe continuation, but the current run is
terminal and any continuation uses a new linked or rebased run. `RUN_CANCELLED`
requires authenticated action by a named `PipelineAdministrator` before any
irreversible effect checkpoint. `RUN_FAILED` requires a proved non-retryable
failure or exhaustion of permitted attempts. `RUN_REJECTED` is reserved only
for an authenticated human rejection of the frozen proposal.

## 2026-08-16 — Authorize the ordered lifecycle correctness correction

The user explicitly authorized the five corrective steps in this exact order:
add five normative versioned machine contracts; present ambiguous transition
and guard decisions one at a time; enforce runtime-exact primitive types; prove
Python-to-contract equivalence; and restore one reproducible ordinary developer
test command.

This authorization covers local contract, domain, test, development-bootstrap,
and continuity changes needed for those five steps. It does not authorize the
later Command/Result or Effect Intent/Receipt feature slice, application
runtime, external calls, Azure, deployment, production action, or a commit.

## 2026-08-16 — Keep reconciliation inside `RUN_PROMOTING`

For ordered lifecycle-correction decision 1, the user approved removing
`RUN_PROMOTING → RUN_BLOCKED`. Once promotion starts, ordinary cancellation and
terminal blocking are forbidden. An unknown or unresolved effect outcome keeps
the run in `RUN_PROMOTING`, with dependent work fenced while exact
reconciliation occurs. The run may then become `RUN_SUCCEEDED` after verified
success, `RUN_ROLLED_BACK` after verified approved recovery, or `RUN_FAILED`
only after a terminal failure is proved and no approved rollback or
reconciliation action remains.

## 2026-08-16 — Authorize the first bounded M2 domain-kernel checkpoint

The user separately authorized implementation of the first bounded M2
checkpoint after accepting ADR 0099. Its scope is the framework-free immutable
lifecycle kernel for Pipeline Runs, Work Items, Source Contract Reviews,
Coverage Gaps, and Quarantines, including closed transition catalogues,
optimistic-version rejection, recurrence identities, and exhaustive pure tests.

This authorization excludes Management Register ports or migrations, command
and effect contracts, application runtime, external sources, models,
embeddings, Azure, Pinecone, deployment, and production operations. Completion
of this checkpoint does not authorize the next M2 slice.

## 2026-08-16 — Accept ADR 0099 and the complete M2–M7 closure package

After deciding all seven material choices individually, the user explicitly
accepted reconciled ADR 0099 and its six implementation-facing protocols:
Domain/Register, Application Interfaces, Acquisition/Evidence, executable
Legal Desk Packages, Review/Promotion, and End-to-End Conformance.

The architecture and implementation-facing design baseline is therefore
accepted through ADR 0099. This closes the design prerequisite for M2–M7 but
does not authorize implementation, external source access, model or embedding
calls, Azure changes, publication, Pinecone mutation, deployment, routing, or
production operations. Each remains separately authorized and admitted.

## 2026-08-16 — Give admitted LLMs bounded semantic-decision responsibility

The user superseded decision 7's proposal-only characterization. For admitted
tasks where variable legal language is not handled well by deterministic code,
the LLM is to decide bounded semantic fields and ordinary results rather than
provide advice that a deterministic rule must independently recreate.

Deterministic code retains source/evidence checks, contract and schema checks,
coverage and completeness arithmetic, identity and exact-byte validation,
tests, admission gates, effect authorization, and execution. Independent model
challenge and deterministic validation may constrain a semantic decision; an
unresolved, unsupported, out-of-contract, or exceptional result goes to the
Legal Desk/human path. Approval and production effects remain outside model
authority.

This boundary is approved for every admitted task. The task contract must name
the exact semantic fields the model may decide. A conforming primary result
that survives independent model challenge and deterministic validation becomes
the ordinary semantic decision; deterministic code does not have to recreate
the same judgment. The earlier model-assisted evaluator selection is replaced
by deterministic checks and human-adjudicated reference truth. This decision
grants no provider call, implementation, or production authority.

## 2026-08-16 — Use LLM assistance for the remaining named semantic tasks and a deterministic default

For decision 7 of the ADR 0099 closure review, the user selected generative-LLM
assistance for two previously open processing areas and a deterministic/human
evaluation boundary:

1. Gazette-event extraction uses a change-gated evidence-bound analysis and
   challenge workflow. Within its admitted contract, the model decides
   instrument/event identity, operative clauses, affected locations, dates or
   conditions, support, and uncertainty. A conforming unchallenged result is
   the ordinary semantic decision; unresolved or exceptional cases go to the
   Hong Kong Legislation Legal Desk/human path.
2. Hong Kong Reconstruction Plan preparation uses evidence-bound decision and
   challenge stages. Within the admitted contract, the model decides the
   semantic mapping into the closed operation registry. Only registered
   operations may survive deterministic validation; deterministic execution
   applies authentic source-supplied text and produces the final bilingual
   bytes.
3. Offline semantic evaluation is not a generative-LLM task. Deterministic
   checks enforce contracts, exact support, invariants, and scored acceptance
   rules against human-adjudicated reference truth. Humans own disputed truth;
   a model may not grade itself or define the final admission gate.

Every other task without an accepted generative allocation defaults to
`NO_GENERATIVE_LLM` for now, including Principles transformations and tasks for
new jurisdictions or material families. A later generative allocation requires
a new accepted ADR and complete task, evidence, evaluation, admission, and
activation package.

This makes Hong Kong Legislation hybrid rather than purely deterministic:
models assist variable semantic interpretation, while source authentication,
XML/PDF reconciliation, event acceptance, status, reconstruction operation
validation/execution, authentic bilingual text, identity, rendering, release,
Approval, and production effects remain deterministic or Legal Desk/human
boundaries.

The HKEX/HKeL split is task-based, not a claim that one material family is safe
for AI and the other is not. HKeL supplies structured bilingual XML plus
matching official PDFs and a closed exact reconstruction-operation registry,
so deterministic code can prove more of its ordinary structure and final text.
HKEX contains varied English update, transition, table, fee, Form, and
dependency relationships whose semantic boundaries are less completely
machine-expressed, so its accepted model tasks cover those relationships. In
both families, an explicit deterministic fast path avoids model work and an LLM
is used only for a variable semantic proposal/challenge stage.

This settles decision 7 only. It enables no provider call, evaluator run,
source access, implementation, or production action.

## 2026-08-16 — Use a fingerprint-bound, cached Coverage Status Manifest

For decision 6 of the ADR 0099 closure review, the user approved a simplified
coverage-status delivery mechanism and rejected a dedicated signing identity,
signature keys, rotation, and signature-validation lifecycle.

Each routing generation references one complete immutable Coverage Status
Manifest covering every expected legal scope, status, last verification time,
known gaps/failures, and user-facing warning code. The routing generation binds
the manifest's exact SHA-256 fingerprint and protected immutable Azure download
reference. Ask.Legal retrieves it through authenticated protected storage,
verifies the bytes against the fingerprint, and caches the verified copy by
routing generation.

Candidate activation blocks if the manifest is missing, incomplete, or has the
wrong fingerprint. After activation, a temporary store failure may use only the
matching verified cached copy. If neither a valid stored nor cached copy exists,
Ask.Legal displays a global `coverage status unavailable` warning and records
the failure; it never treats a missing search result as proof that no law or
coverage gap exists.

At the time of this decision, the normative Coverage Status Manifest schema
required `signature_policy_state` and lacked selected delivery fields. The
later 1.1.0 amendment recorded above completed that implementation dependency.

This settles decision 6 only. It grants no storage, routing, deployment, or
production authority.

## 2026-08-16 — Use environment/jurisdiction/date/state Pinecone index names

For decision 5 of the ADR 0099 closure review, the user approved the exact
Pinecone index-name format:

`asklegal-<env3>-<jur3>-<YYYYMMDD>-<state12>`

`env3` is `dev`, `stg`, or `prd`; `jur3` is a registered lowercase three-
character jurisdiction code; the date is the UTC Serving State freeze date;
and `state12` is the first twelve hexadecimal characters of the immutable
Serving State Definition SHA-256 after collision checking. The normal form is
38 characters and the repository enforces an internal 40-character maximum.

Names use only lowercase ASCII letters, digits, and dashes and must start and
end with an alphanumeric character. Creation also validates the current
Pinecone 45-character API limit and the actual combined index-name/project-ID
hostname constraint. A shortened-token collision with a different full
fingerprint is a hard failure requiring a new registered disambiguation; it
never overwrites or reuses an index. Mutable aliases such as `latest`, sequence-
only names, and date-only names are forbidden. The complete fingerprint and
verified inventory, not the readable name, remain authoritative.

This settles decision 5 only. It grants no Pinecone or production authority.

## 2026-08-16 — Use a separate production-candidate App Service slot

For decision 4 of the ADR 0099 closure review, the user approved a separate
restricted Ask.Legal App Service `candidate` slot for production routing
activation. The existing development slot remains development-only and never
becomes a production cutover source or rollback destination.

The candidate slot receives one complete frozen routing generation and the
exact production-compatible application build. It is warmed and validated
before a `PipelineAdministrator` manually authorizes a standard swap with the
production slot. Each answer-producing request remains pinned to the routing
generation it started with. Post-swap checks verify production; failure invokes
the manifest-declared reverse swap and verifies the restored predecessor.
Direct production routing-setting edits, auto-swap, percentage traffic mixing,
and development-to-production swaps are forbidden.

Current Microsoft documentation confirms that deployment slots are live apps,
support standard and reverse swaps, and have no separate slot charge, while
each App Service plan tier limits the number of slots and all slots use the
plan's capacity. Production admission must therefore prove that the current
plan supports the extra slot and adequate shared capacity.

This settles decision 4 only. It grants no Azure, deployment, routing, or
production authority.

## 2026-08-16 — Use severity and optional due dates instead of fixed review SLAs

For decision 3 of the ADR 0099 closure review, the user approved the simpler
Quarantine/review policy and rejected fixed one-, five-, and ten-business-day
deadlines and their calendar-driven escalation machinery.

Every Quarantine, Coverage Gap, and Source Contract Review records its severity
and one or more assigned named `PipelineAdministrator` users. Urgent release-
blocking or potentially misleading current-law issues notify the assigned
administrators immediately. An administrator may set or change an explicit due
time when useful; no default due time, business-day calendar, half-interval
notification, deadline notification, or daily-overdue loop is required.

Elapsed time never releases, approves, suppresses, or resolves material.
Unresolved work remains blocked, safely withheld, or explicitly carried forward
under the applicable evidence rule until a recorded decision resolves it.
Permanent exclusion and re-entry retain their exact evidence, accounting, and
new-linked-work requirements.

This settles decision 3 only and grants no implementation or operational
authority.

## 2026-08-16 — Use one human pipeline-administrator role and no Approval TTL

For decision 2 of the ADR 0099 closure review, the user rejected separate
reader, commenter, approver, revoker, pipeline-operator, recovery-operator, and
absence-cover roles as unnecessary. The user also rejected recent step-up
authentication and an independent four-hour Approval expiry.

The human authorization model therefore has one `PipelineAdministrator` role.
Multiple named people may receive that same role. It permits inspection,
comments, approval, rejection, revocation, pipeline operation, and recovery
through the separately secured application interfaces. There is no separate
absence-cover construct and no shared account.

Approval, rejection, and revocation still require a delegated named-human
identity, current `PipelineAdministrator` permission, an immutable non-empty
reason, and complete audit evidence. Ordinary Entra sign-in and the production
MFA baseline remain, but there is no separate recent-authentication or step-up
freshness test for the decision.

An Approval has no independent time-to-live. It may be consumed exactly once
and is rejected after consumption, explicit revocation, removal of the actor's
current permission, invalidation of the bound Promotion Manifest, or failure of
any bound evidence, base-state, configuration, target, or recovery predicate.
The Promotion Manifest may still become invalid under its own evidence-
freshness and validity rules; that is not a separate Approval-age mechanism.

This simplifies human permissions only. Application identities, database
roles, deployment identities, and effect ownership remain separated. At the
time of this decision, the normative Approval schema still required
`valid_until`. The later 1.1.0 amendment recorded above completed that
implementation dependency.

This decision supersedes ADR 0096's earlier multi-role and action-specific
step-up requirement. It settles decision 2 only and grants no implementation
or operational authority.

## 2026-08-16 — Match Ask.Legal Backend's Azure OpenAI provider family

For decision 1 of the ADR 0099 closure review, the user directed the pipeline
to use whatever the existing Ask.Legal Backend uses. Read-only inspection of
`Ask.Legal Core/AskLegal-Backend/src/services/legalQuestionService.js` verified
that it uses Azure OpenAI deployments for both chat/generative requests and
embedding creation, with Pinecone as the separate vector-serving system.

The pipeline therefore selects **Azure OpenAI models made available through
Microsoft Foundry for both stateless generative proposals and embeddings**.
Exact deployments, versions, prompts, dimensions, token limits, thresholds,
budgets, and evaluation results remain immutable admission-profile evidence.

The existing backend currently routes those calls through a Cloudflare AI
endpoint and authenticates to Azure OpenAI with an API key. This provider
decision does not copy that transport or reusable credential into the
greenfield pipeline. They are implementation details, and the accepted
least-privilege Azure baseline continues to prefer private Azure connectivity
and Entra workload identity. Any proposed deviation must be separately
justified and decided.

This settles decision 1 only. It does not accept ADR 0099 as a whole or grant
implementation, provider-call, or production authority.

## 2026-08-16 — Superseded: ADR 0099 closure package was proposed, not accepted

The user corrected the record: the instruction to complete and close the
design meant that the assistant should prepare the design and then ask for the
material decisions. It did not authorize the assistant to decide product,
risk, cost, or operating-policy tradeoffs on the user's behalf.

ADR 0099 and D1–D6 therefore remain a complete **proposed** closure package.
They must not be treated as accepted, design-complete, or implementation-ready
until the user has decided the material choices and explicitly accepts the
resulting package. This correction supersedes the acceptance claim immediately
below; it does not discard the drafted recommendations.

Decisions 1 through 7 were subsequently settled and the reconciled ADR 0099 and
D1–D6 package was explicitly accepted by the later entry above.

No implementation or operational authority is implied while this review is
in progress.

## 2026-08-16 — Superseded: closure package incorrectly recorded as accepted

This entry is retained for audit history but its acceptance claim is
superseded by the correction above.

The assistant incorrectly interpreted the user's direction to complete and
close the design as approval. This superseded record stated that ADR 0099
accepted six protocol specifications closing all twelve findings in
the build-readiness audit: Domain/Register, Application interfaces,
Acquisition/Evidence, executable Legal Desk packages, Review/Promotion, and
end-to-end conformance.

The control plane prepares the complete effect-free proposal package. The
Review API records one exact human decision. The promotion worker consumes
only the approved manifest. M7 uses the reserved local-only synthetic Legal
Desk package and makes no real-jurisdiction readiness claim.

Azure OpenAI models sold by Azure through Microsoft Foundry are selected for
stateless generative proposals and embeddings. Exact model deployment/version,
prompts, dimensions, limits, thresholds, and evaluation results live in
immutable admission profiles and remain disabled until proved. Stateful model
features, hosted files, autonomous tools, browsing, and code execution are not
part of the pipeline.

Pinecone names use
`asklegal-<env3>-<jur3>-<YYYYMMDD>-<state12>`. Ask.Legal activation uses a
restricted `candidate` App Service slot, a complete swappable routing
generation, a validated manually authorized standard slot swap, per-request generation pinning,
post-cutover verification, and reverse-swap rollback. Every Serving State has
one complete immutable, fingerprint-bound Coverage Status Manifest retrieved
from protected storage and cached by routing generation after verification.

This superseded closure record originally claimed exact Entra roles, 15-minute
step-up, and four-hour Approval validity. Decision 2 above replaces those
claims with one `PipelineAdministrator` role, no action-specific step-up, no
independent Approval TTL, and single consumption. Decision 3 later removes
fixed review deadlines in favor of severity, immediate urgent notification,
and optional administrator-set due times.

Regions, capacity, retention, recovery objectives, service levels, budgets,
source inventories/rights, exact deployed models, and real evaluations remain
mandatory implementation or admission evidence. Their absence disables the
relevant capability and supplies no default; it does not leave the engineering
design open.

Design closure grants no implementation or operational authority.

## 2026-08-16 — Accept the M2–M7 build-readiness audit boundary

The full design audit confirms that the accepted five-application, immutable-
evidence, Legal Desk, Approval, replacement-target, local-first, Python, and
Azure architecture is coherent and does not need to be reopened. It is not yet
ready for continuous M2–M7 implementation: six implementation-facing design
packets remain, starting with the Domain and Register protocol before the next
M2 code slice. See
`docs/design/M2_M7_BUILD_READINESS_DESIGN_AUDIT.md`.

Complete effect-free proposal-package preparation belongs to the control-plane
coordination boundary through pure corpus and promotion services. The Review
application records the human decision without altering the proposal. The
promotion worker consumes only an exact approved manifest and cannot create,
broaden, or replace it. The current architecture spike remains valid evidence
of the checkpoint it proved, but its control-plane dependency and capability
declaration must be revised and re-proved before M3 runtime implementation.

M7 proves platform behavior with one closed test-only synthetic Legal Desk
package. That package cannot enter a production Release Scope Registry, grant
any external capability, or satisfy a Hong Kong legal, source, evaluation, or
production-readiness gate. Exact model/provider choices, Azure routing and
index values, production governance values, measured operational settings,
and Ask.Legal admin-portal integration remain deferred through M7.

This decision records design boundaries only. It grants no implementation or
operational authority.

## 2026-08-16 — Prove the complete local application/package architecture boundary

The user explicitly authorized the architecture spike. The workspace now has
minimum declarative, installable skeletons for the five separately permissioned
applications and 13 canonical shared packages. A closed manifest records every
member's exact identity, allowed direct internal and external dependencies,
role, and application capability ports. It also assigns every sensitive
exclusive capability to one application boundary.

The repository checker discovers future members and fails closed on coverage,
metadata, dependency, uv workspace-source, internal-import, package-to-app,
cycle, declaration, or exclusive-capability drift. The settled graph contains
5 applications, 13 packages, 70 permitted direct internal edges, and 30
declared capability ports. The expanded 18-member graph must also continue to
pass the offline reproducible-package and clean-install proof.

These skeletons declare intended authority but implement none: there are no
routes, entry points, worker loops, external calls, provider clients,
credentials, Azure resources, deployments, or production effects. Further M2
domain-kernel work and M3 runtime scaffolding each require separate
authorization.

## 2026-08-16 — Prove synthetic OCI admission locally before Azure

The user explicitly authorized the local image-admission spike. Its closed
manifest pins the synthetic image inputs; Buildx 0.36.1; BuildKit v0.26.2;
Docker 29.1.3; Syft 1.51.0; Grype 0.117.0 and one exact fresh v6.1.9 database;
ORAS 1.3.3; Notation 1.3.2; OpenSSL 3.0.13; release URLs; and verified binary,
release-asset, database, and BusyBox hashes. The policy is deliberately Linux
amd64 and synthetic-only.

Two clean network-disabled builds must produce the same exact OCI image graph,
normalized result-determining BuildKit provenance, normalized SPDX SBOM, and
unsigned candidate evidence graph. Grype output is complete, offline, bound to
the exact selected database, and normalized only for observation time and host
paths. KEV and Critical findings, fixed High findings, unfixed High findings
without an exact acceptance, unknown severity, stale/future database state,
and incomplete scanner output block. Denied, review-required, unknown, or
unfulfilled licences block under the closed test catalogue.

ORAS must copy the exact subject and all required referrers without rebuilding
and restore the complete signed graph byte-for-byte. Deployment references
must name `release/<application>@sha256:<digest>` and identities must have the
exact narrow action set. Notation generates a fresh local test certificate and
key for each proof; OpenSSL signs and verifies the canonical payload with that
key and certificate. That ephemeral root is marked `LOCAL_TEST_ONLY` and cannot establish
production trust, so signed-graph hashes intentionally differ between complete
runs while each run's recovery graph must equal its signed release graph.

This decision authorizes only the local synthetic proof. It does not admit the
downloaded upstream tools as production artifacts because their upstream
signatures/attestations were not verified. It does not prove Azure Artifact
Signing, ACR ABAC/private networking/locks, Container Apps policy, managed
identity, Azure recovery, deployment, or any production operation.

## 2026-08-16 — Prove offline isolated and reproducible Python packages

The user explicitly authorized the local package spike. Its closed manifest
covers all current workspace members and pins Python 3.14.7, uv 0.12.5, a
fixed build epoch, allowed workspace dependency closures, forbidden
development distributions, and exact container metadata inputs. Discovery of
an undeclared future package or application fails rather than silently
escaping the proof.

Two path-distinct offline builds must produce byte-identical wheels whose safe
paths and complete RECORD hashes and sizes verify. Each member must install
non-editably into a separate clean environment from the unchanged exact lock
with uv network access and Python downloads disabled; isolated imports may see
only that member and its declared workspace closure, with no development-tool
leakage. Two wheel-plus-lock USTAR container-input bundles must also be
byte-identical. This proves reproducible package and container inputs, not an
OCI image or admission chain. It authorizes no application scaffolding,
network access, Azure resource, deployment, or production effect.

## 2026-08-16 — Prove durability with the selected SDK and local emulator

The user explicitly authorized the local synthetic durability spike. It uses
the selected standalone Microsoft runtime rather than a repository-invented
replay simulator: `durabletask==1.9.0`,
`durabletask-azuremanaged==1.7.0`, Microsoft's always-on in-memory test backend,
and the Docker Scheduler emulator pinned to MCR digest
`sha256:1b49dcf1581168f5c620a4f32083e1291a7dddfa60434acb3eacd8b23355936a`.

Scheduler history owns deterministic replay, waiting, buffered event delivery,
activity dispatch, and retry only. A recoverable fake Management Register owns
current execution lineage, event facts, accepted approval event, capability,
idempotency keys, and immutable effect receipts. External events carry only an
opaque ID and exact fingerprint. Activities re-resolve those facts and recheck
authority immediately before a synthetic effect. The initial internal
Scheduler payload ceiling remains 64 KiB.

The adversarial proof stops the first worker at its human wait, queues a stale
event, its exact duplicate, and a valid current event, reconstructs the fake
register from an exact snapshot, and starts a fresh worker. A controlled lost
acknowledgement causes two SDK activity attempts but exactly one effect and one
receipt. Workflow versions use the emulator-enforced numeric form; this spike
uses `1.0.0`. The emulator container was removed and its image may remain
cached. This decision authorizes no Azure resource, application scaffolding,
external data, provider call, deployment, or production effect.

## 2026-08-16 — Prove the Management Register with Docker and real SQL Server

The user explicitly authorized the local Management Register spike and chose
Docker. Ubuntu `docker.io` 29.1.3 is installed with its privileged daemon, but
the user was not added to the root-equivalent Docker group. The proof pins SQL
Server 2025 CU7 Developer to MCR digest
`sha256:fa0dcf206087759fe6dad4cc02bfa88d97439085e548fbca9039330519c0cf1d`
and Microsoft's first-party `mssql-python==1.12.0` in the exact uv lock.

The repository-owned runner accepts only explicitly supplied forward-only
migration directories with closed manifests, ordered exact UTF-8/LF batch
bytes, SHA-256 lengths and hashes, one JCS package fingerprint, no `GO`, no
templates, and no implicit execution discovery. SQL Server owns short command
transactions, finite transaction application locks, single-winner Approval
consumption and Serving State activation, atomic inbox/event/outbox/projection/
result updates, and immutable lost-ack resolution. Application roles receive
only exact procedure/view permissions and cannot mutate tables directly.

The synthetic real-engine test proves migration replay, JCS-byte fingerprints,
idempotency, concurrent single-winner consumption, atomicity, activation,
ambiguous-commit recovery, direct-DML denial, and SQL ledger-digest
verification. Focused fakes prove bounded deadlock-victim retry. The disposable
container and credential were removed after validation; the pinned image may
remain cached locally. This decision authorizes no Azure access, application
scaffolding, legal data, external effect, deployment, or production operation.

## 2026-08-16 — Enforce the Python type boundary with two independent gates

The user explicitly authorized the local type-boundary spike. Official Pyright
1.1.413 remains the sole static type checker and now covers the complete
repository in strict Python 3.14 mode. A repository-owned AST and token checker
adds stable fail-closed rules for explicit `Any`, bare collection annotations,
casts, error suppressions, protected infrastructure imports, and framework
leakage that Pyright alone does not express as repository architecture policy.

The checker discovers every present and future `packages/*` and `apps/*`
source and test tree rather than trusting a manual package list. Five necessary
runtime-narrowing casts and one dependency-owned jsonschema diagnostic are
registered by exact path, line, code, and reason; a stale or unused exception
is itself a failure. Synthetic fixtures prove every violation class and future-
tree discovery. This decision implements the ADR 0089–0090 strict-profile
requirement without authorizing the later full application/package capability-
direction architecture spike or any external effect.

## 2026-08-16 — Pin the initial local Python contract toolchain

The user explicitly authorized the first local contract spike. It pins Python
3.14.7 and one uv workspace lock, plus official Pyright 1.1.413 in the separate
npm development-tool lock. The locked contract implementation uses
jsonschema 4.26.0, Pydantic 2.13.4, referencing 0.37.0, rfc8785 0.1.4, pytest
9.1.1, Hypothesis 6.165.9, and Ruff 0.16.3.

This is the exact initial implementation proof of ADRs 0088–0090, not a new
contract authority. The repository-root schemas and fixtures remain normative,
the dependency-free Node validator remains the independent oracle, and the
Python package contains no application, database, cloud, provider, source, or
production capability. A dependency or Python patch change must update the
locks and repeat the complete local proof.

## 2026-08-16 — Use Azure Monitor and immutable operational audit archives

ADR 0098 selects direct Azure Monitor OpenTelemetry instrumentation with one
workspace-based Application Insights resource per application, one shared
application-operations workspace, and one separately restricted security-and-
audit workspace. The five Application Insights resources preserve application
attribution and resource-context access; the two workspaces and one Azure
Monitor Private Link Scope are accepted shared observability blast radii.

Azure Monitor is a detection and query plane, not the authority for business or
legal facts, Approval, deployment, promotion, Serving State, or effect receipts.
Required operational audit records also flow to a dedicated immutable primary
Operational Audit Archive. A protected sealer creates exact interval packages,
and only the promotion worker's separately invoked recovery-copy capability may
copy those packages into a separately administered Recovery Audit Archive using
conditional create, exact versions, hashes, complete manifests, and read-back.

Production telemetry follows a closed allow-list and excludes legal text,
evidence payloads, prompts, model data, secrets, tokens, request bodies, and raw
exceptions. Privileged, security, failure, Approval, promotion, recovery,
deployment, migration, signing, and deletion-attempt events cannot be sampled
away. Ordinary work may continue for a bounded interval during telemetry loss
only while authoritative writes remain healthy; new privileged effects stop
when required monitoring and audit coverage cannot be proved.

Azure DevOps audit export must pass a separate production proof. The selected
baseline is a protected scheduled exporter using a short-lived Entra-backed
identity rather than a native stream that stores a reusable destination key.
Failure of that proof requires a new architecture decision. This decision
authorizes documentation only and creates no telemetry, archive, pipeline, or
Azure capability.

## 2026-08-16 — Use Bicep and Azure Pipelines for infrastructure delivery

ADR 0097 selects repository-owned Bicep as the infrastructure source and Azure
Pipelines as the operational deployment control plane while GitHub remains the
reviewed source repository. Every Azure service connection uses Entra workload
identity federation; reusable client secrets, certificates, publish profiles,
and deployment tokens are not the production delivery baseline.

Fresh Microsoft-hosted agents handle offline checks and Azure control-plane
work that needs no private data path. Separate zero-standby, stateless Managed
DevOps Pools in separately delegated subnets handle the private ACR software-
supply-chain path and private Azure SQL migration path. The pools provide
network placement, not ambient authority; every privileged stage consumes its
own protected workload-federated service connection.

Infrastructure apply, role assignment, policy and locks, migration, image
admission, each application deployment, evidence writing, exact retirement,
and break-glass use separate identities and gates. One immutable Deployment
Change Package binds exact source and compiled bytes, tools, target, identity,
complete what-if output, cost inputs, rollback basis, evidence destination, and
Operational Deployment Approval. Operational approval cannot create or replace
a legal Promotion Manifest or ADR 0007 Approval.

Apply uses a fresh full-provider plan and incremental deployment. Unknown or
ignored what-if output fails closed. Omission from Bicep is not deletion
authority, drift is not auto-remediated, and resource retirement requires a
separate exact package and maintenance identity.

The selected control plane deliberately differs from Ask.Legal Core's visible
GitHub Actions standard. The user explicitly accepted that deviation after
considering GitHub Enterprise managed private runners and a lower-plan GitHub
Actions design with project-operated ephemeral runners. Azure Pipelines was
selected to keep the private-runner and approval path Azure-managed and simple.
This decision authorizes documentation only; it does not authorize pipeline,
identity, runner, network, infrastructure, deployment, or cloud creation.

## 2026-08-15 — Use Application Gateway for a split public and private API edge

ADR 0096 selects one regional Azure Application Gateway WAF_v2 in a dedicated
hub edge subnet. Its public HTTPS frontend routes only the Review Application
API. Its separate private-IP frontend and private DNS route only the control
plane through an approved private operator-network path. The listeners have
separate hostnames, certificates, backend pools, probes, routing rules, and WAF
policies. There is no public control route, public fallback, worker route,
wildcard listener, or direct public Container Apps origin.

Both API origins remain internal Container Apps environments with private
virtual IPs and public network access disabled. Their app ingress is enabled
at the VNet scope so the hub gateway can reach it. Private DNS, exact backend
FQDN and SNI, end-to-end TLS, subnet restrictions, and trusted-proxy rules
prevent origin and forwarded-header bypass.

Application Gateway owns TLS, WAF, coarse rate limits, routing, and origin
isolation; it does not own identity or business authorization. Control and
Review use separate single-tenant Entra resource applications, audiences,
client allow-lists, scopes, app roles, and FastAPI authorization. Each API
validates signature, issuer, tenant, audience, lifetime, stable subject, actor
client, scope or expressly admitted application role, and current operation
permission.

The initial review browser uses authorization code with PKCE and its own Review
client registration. The later Ask.Legal admin portal is admitted as a
separate client of the same versioned Review API. Approval and revocation are
human-only delegated operations, reject app-only tokens, and bind the stable
Entra human identity. Decision 2 later fixes one `PipelineAdministrator` role
and removes action-specific step-up; Review and Control access still require
MFA before production admission.

Production uses a tested Azure Default Rule Set in WAF Prevention mode,
listener-specific exact exclusions and request limits, coarse anomaly rate
limits, and sensitive-data log scrubbing. Application policy still owns exact
identity-aware limits, raw-byte validation, idempotency, concurrency, and
Approval. One gateway is an accepted shared API-availability and configuration
blast radius. Exact region, capacity, private operator path, WAF values,
enhanced DDoS choice, cross-region recovery, retention, and complete cost
remain later decisions. This decision authorizes documentation only.

## 2026-08-15 — Use one private ACR with attested image admission

ADR 0095 selects one shared Azure Container Registry Premium registry for all
five production application images. Premium is required by the already
accepted private endpoint. The registry uses disabled public, anonymous, and
admin access plus `RBAC Registry + ABAC Repository Permissions` over separate
`base/`, `tool/`, `candidate/<application>`, and `release/<application>`
families. Per-application build, pull, verification, and deployment identities
receive conditioned repository access only; no runtime can read another
application's image or any candidate.

Builds push only candidates. One separately permissioned image-admission path
copies the exact manifest and referenced graph without rebuilding, and only a
passed release digest is signed and locked. Container Apps revisions name
`release/<application>@sha256:<digest>` only. The application-specific
deployment job repeats all verification immediately before deployment, while
a deny-mode Azure Policy rejects another registry, repository family, or tag-
only image reference.

Notation and one Azure Artifact Signing Private Trust certificate profile form
the central image-signing trust root. Strict verification binds signer and
timestamp trust, registry and repository scope, and exact digest. Container
Apps does not have the selected AKS-style in-platform signature admission, so
the deployment job and policy are explicit controls; tenant, Owner, policy-
exemption, and Container Apps control-plane compromise remain outside that
claim.

The ACR data path stays private. Artifact Signing is not claimed to support
Private Link: the isolated signer receives narrowly allowlisted outbound access
to the selected regional signing, Entra, and timestamp endpoints, with trust
roots admitted and pinned before release. Failure blocks new signing without
invalidating an already timestamped admitted release.

BuildKit produces in-toto/SLSA provenance. A pinned Syft build produces SPDX
JSON, pinned Grype scans with a fingerprinted database snapshot no more than
24 hours old, and a repository-owned evaluator applies a closed licence
catalogue. Unknown or incomplete coverage blocks. Critical and known-exploited
vulnerabilities block; fixed High vulnerabilities block; unfixed High findings
require an exact expiring acceptance. Denied licences block, and unknown or
review-required licences require an exact authorized decision. Production
remains disabled until that catalogue and exact admitted tool versions exist.

One ACR is simpler than five Premium registries while repository ABAC preserves
the current application data-plane boundaries. It is a shared registry and
signing control-plane blast radius, recorded rather than denied. Zone
redundancy and geo-replication protect availability, not deletion or backup.
Complete OCI image-layout packages, signatures, attestations, scanner inputs,
policy, and Image Admission Records are preserved in both ADR 0094 vaults.
Automatic ACR purge and retention are not authority; retirement names exact
digests and referrers. This decision authorizes documentation only.

## 2026-08-15 — Keep evidence and recovery storage Azure-only

ADR 0094 selects flat-namespace Azure Blob Storage GPv2 accounts with locked
version-level WORM as both the primary Evidence Vault and the separate
Recovery Vault. The Recovery Vault uses different accounts in a dedicated
Azure recovery subscription under the existing Microsoft Entra tenant and,
where data-location rules permit, a different Azure region pair. Primary and
recovery administration, policies, deployment identities, networks, and
runtime roles remain separate.

Only the promotion worker can create and verify recovery copies. One explicit
conditional-create, exact-version, read-back, SHA-256, and complete-manifest
protocol replaces the proposed cross-cloud copy and avoids adding Azure Blob
object replication as a second copy mechanism. No deletion propagates between
vaults, runtime identities cannot delete retained versions or change storage
policy, and retention expiry never becomes deletion authority.

Both vaults use Microsoft-managed encryption keys plus infrastructure
encryption. Azure SQL database-ledger digests go to a separate private Azure
Confidential Ledger, with verified digest checkpoints and receipts included in
Recovery Vault checkpoints. Azure SQL automated backups and Pinecone-native
backups remain separate mechanisms.

The user rejected the previously proposed second-cloud store because it is
unlikely to be available and directed that the design stay Azure-only and
simple. The accepted consequence is explicit: the Recovery Vault isolates
ordinary application, account, subscription, administrator, policy, and
regional failures, but it is not independent of Azure or the shared Entra
tenant. It does not protect against an Azure-wide failure or tenant-wide
compromise. Exact retention, regions, tiers, recovery objectives, destruction
authority, drill frequency, capacity, and cost remain open. This decision
authorizes documentation only.

## 2026-08-15 — Use managed Durable Task Scheduler for workflows

ADR 0093 selects the generally available standalone Python Durable Task SDK
with managed Azure Durable Task Scheduler. Durable applications remain
ordinary Python processes on Container Apps and do not acquire the Azure
Functions host.

Production begins with a general Scheduler containing separate control-plane,
acquisition, and legal-processing task hubs, plus a separate promotion
Scheduler containing only the promotion task hub. Each application uses a
distinct user-assigned identity with task-hub-scoped access. The Review API has
no Scheduler role, and no non-promotion identity or application network can
operate the promotion Scheduler. Private endpoints and private DNS carry the
data path; public network access is disabled after proof.

Cross-application handoff occurs through exact Management Register outbox
facts. Each receiving application schedules idempotent work only into its own
task hub. Scheduler history owns replay, timers, waits, retries, dispatch, and
external-event delivery; it never owns business or legal authority, Approval,
promotion admission, Serving State, immutable effect receipts, or audit.

Orchestration payloads contain only bounded references and sanitized closed
results under an initial 64 KiB ceiling. Legal content, evidence, prompts,
model and provider payloads, approvals, comments, secrets, and raw exceptions
stay outside Scheduler history. Explicit versioning, immutable old replay
branches, `continue-as-new`, idempotent activities, and register lineage checks
are mandatory.

Temporal remained the strongest alternative but its Azure Cloud offering is
currently invite-only pre-release; self-hosting would add substantial workflow
platform operations. Dapr adds sidecars, actor infrastructure, and a strongly
consistent state store, while Durable Functions adds an unneeded Functions
host. Queue-plus-custom-state-machine approaches would make this project own
replay and recovery correctness.

The local emulator remains the ordinary development path but stores state in
memory and cannot prove Azure identity, networking, persistent Scheduler
recovery, retention, capacity, or regional behavior. Managed Scheduler state
does not fail over across regions; regional replacement must fence the old
lineage, reconcile effects, and start a new exact recovery lineage from
authoritative register state. This decision authorizes documentation only.

## 2026-08-15 — Host the five pipeline applications on Azure Container Apps

ADR 0092 selects Azure Container Apps for the control plane, Review Application
API, acquisition worker, legal-processing worker, and promotion worker. Each
production boundary uses a separate workload-profiles environment and
delegated subnet, plus its own runtime managed identity, database role, secret
access, scaling and health policy, deployment identity, and deployment job.
Images are minimal per-application OCI images selected by immutable digest.

The two APIs are internal continuously available Container Apps behind a later
selected authenticated edge. The three workers are continuously running apps
with ingress disabled and durable worker connections. Production initially
maintains at least one replica for every boundary; scale to zero is not assumed
for a durable worker with no connected process to receive streamed tasks.
Exact Consumption or Dedicated workload profiles, sizes, replica limits,
region, zones, edge, hub, firewall, DNS, recovery, service levels, and cost
remain later measured decisions.

Container Apps was selected over App Service because it supplies one direct
container model for both FastAPI services and no-ingress continuous workers,
with per-app revisions and scaling. App Service remained technically capable
and operationally familiar, but preserving strict compute isolation would
require separate plans, while workers would use WebJobs or empty Always On web
apps. A hybrid API/worker split would add a second pipeline host without a
required capability.

One Container Apps environment per boundary is deliberate: environment-level
network policy is shared, while acquisition-source, legal-model, promotion,
review, and control egress risks differ. Application subnets route through
their own policy rules; private Azure dependencies use private endpoints and
private DNS where supported. Shared hub services do not merge identities,
database roles, task hubs, secrets, egress rules, or deployment authority.

The promotion worker is not a manually started Container Apps Job. The same
Job start action can override the execution image, command, arguments, and
environment, and the starter can access configured Job secrets. Promotion is
therefore a no-ingress continuous worker that accepts only durable
fingerprint-bound work and independently revalidates the exact Approval and
frozen manifest. ADR 0002's downstream Ask.Legal App Service routing-
configuration boundary remains unchanged.

This is a production-target decision, not an Azure-first development rule.
Ordinary development and tests continue locally without Azure credentials.
The decision authorizes documentation only; it does not authorize images,
infrastructure, Azure resources, deployments, identities, network changes, or
any operational capability.

## 2026-08-15 — Use Azure SQL for the Management Register

ADR 0091 selects one Azure SQL Database and Microsoft's first-party
`mssql-python` DB-API driver for the production Management Register. Azure SQL
was selected over Azure Database for PostgreSQL because both meet the core
relational, isolation, role, networking, and recovery requirements, while
Azure SQL additionally provides selective append-only ledger tables with
externally stored digests and aligns with Ask.Legal's existing SQL Server
operations. PostgreSQL's more mature driver, native async API, portability, and
concurrency strengths remain acknowledged tradeoffs rather than missing facts.

Authoritative writes use schema-qualified T-SQL command procedures behind
separate least-privilege application roles; no ORM owns the write path and
applications have no direct authoritative table DML or DDL. One short
transaction atomically binds a command's idempotency claim and fingerprint to
immutable events, outbox intents, rebuildable projections, and its exact
result. Critical single-winner transitions combine exact constraints and
compare-and-set with finite transaction-owned application locks and targeted
serializable isolation. External effects occur only after commit, and
ambiguous commit outcomes must be resolved by immutable command-result lookup
before retry.

Only selected immutable facts use append-only ledger tables; projections,
caches, and dispatch state remain rebuildable. Canonical JSON is stored as JCS
UTF-8 bytes plus its fingerprint and typed constraint columns. Migrations are
closed, ordered, fingerprinted, forward-only T-SQL batch packages applied by a
narrow repository-owned runner under one transaction and migration lock. The
exact driver version, Azure tier, capacity, availability, retention, digest
store, backup, and recovery settings remain later measured decisions.

This decision authorizes documentation only. It does not authorize code,
dependency or database installation, migration execution, Azure changes, or
any operational capability.

Azure SQL is the production target rather than the routine development
environment. Normal development must work locally without Azure credentials or
a shared cloud database, using synthetic fixtures, local fakes, and a supported
SQL Server Developer container created through exact migrations. Azure is used
later only for separately authorized proofs of Azure-specific identity,
network, failover, restore, digest, monitoring, and hosting behavior.

## 2026-08-15 — Use FastAPI and a strict Python boundary toolchain

ADR 0090 selects FastAPI with Pydantic v2 and Uvicorn for the control-plane and
Review Application HTTP APIs. FastAPI stays in application adapters; domain
and contract packages remain framework-free, workers do not use it as a
workflow mechanism, and generated OpenAPI supports HTTP documentation and
admin-portal clients without replacing repository-owned normative schemas.

The required development and contract toolchain is official Pyright strict,
Ruff, uv workspaces with one committed `uv.lock`, a repository-owned strict
raw-byte JSON parser, `jsonschema.Draft202012Validator` with a preloaded
network-disabled `referencing.Registry`, Trail of Bits `rfc8785` behind an
internal adapter, pytest, Hypothesis, HTTPX, and AnyIO. Normative JSON is parsed
and schema-validated before strict Pydantic binding. Exact versions remain
implementation-time lock decisions and every selected component must pass the
synthetic contract, type, package, architecture, and reproducibility proofs.

Flask was not selected: matching the typed OpenAPI and boundary-model outcome
would require additional wiring while retaining WSGI, and existing familiarity
does not justify weakening the greenfield boundary. This decision authorizes
documentation only and leaves all operational capabilities disabled.

## 2026-08-15 — Use Python for pipeline applications

ADR 0089 selects Python 3.14 for the control plane, Review Application API,
acquisition worker, legal-processing worker, promotion worker, and shared
production packages. The browser review client and later Ask.Legal admin portal
remain outside this language decision.

The choice follows a user-authorized read-only comparison with Ask.Legal Core:
the existing platform backend uses Node.js/JavaScript while the AI service
already operates Python 3.14 with the relevant AI, Pinecone, document, test,
and Azure experience. Microsoft's standalone Python Durable Task SDK is GA, so
C# would add a third backend ecosystem without an accepted requirement that
Python cannot meet.

Python must use a materially strict profile: complete annotations, failing
static checks, closed frozen domain types, strict external validation,
independent Draft 2020-12 and JCS/SHA conformance, deterministic orchestration,
bounded effect adapters, architecture tests, and reproducible locks. ADR 0090
later selects the application framework and boundary toolchain, ADR 0091 later
selects Azure SQL, ADR 0092 later selects the Container Apps host, and ADR 0093
later selects managed Durable Task Scheduler; provider, security, and
operational choices remain open. This decision authorizes documentation only;
every operational capability remains disabled.

## 2026-08-14 — Establish the implementation-neutral cross-cutting contract foundation

ADR 0088 accepts the repository-owned `contracts/` package. It inventories 54
shared objects, provides closed Draft 2020-12 schemas and eight code
catalogues, fixes six closed-world lifecycle machines, and binds fifteen
synthetic exact-result fixtures and every package file through one exact
manifest.

Shared JSON uses strict I-JSON, RFC 8785 JCS UTF-8, and lowercase
`sha256:<64-hex>` fingerprints. Shared register-issued IDs use a closed
three-character lowercase prefix plus 48 lowercase hexadecimal characters;
identity never derives from a hash or source coordinate. Immutable references
bind both ID and fingerprint.

Schemas require an explicit configured-or-undecided policy state and supply no
policy defaults. The immutable foundation checkpoint keeps the complete
production stack undecided, every operational capability disabled, and
external effects at `NONE`. ADRs 0089 through 0097 later select the backend
language, application boundary toolchain,
Management Register database boundary, application host, durable-workflow
service, evidence-and-recovery storage boundary, image-registry and software-
supply-chain boundary, API edge, and infrastructure-delivery boundary without
rewriting that historical fact.
The local dependency-free Node validator is conformance tooling only, not a
production-stack choice.
Jurisdiction-specific legal contracts and all runtime, source, model, release,
Pinecone, Azure, deployment, and other remote actions remain separately gated.

## 2026-08-14 — Require attested reconstruction capability before processing or promotion

ADR 0087 separates six reconstruction capability states from `DESIGN_ONLY`
through active, suspended, and revoked. Real reconstruction may begin only
under one exact immutable `rcp_` profile whose contracts, build, complete
ordinary and reconstruction suites, reproducibility, containment, architecture
boundaries, and accountable attestation are bound by a valid `rct_` artifact
and an active Management Register event.

Activation grants the legal-processing worker candidate-writing authority
only. Source access, model access, human Approval, embedding, backup, Pinecone,
Azure, deployment, and routing remain separate capabilities and gates. A
reconstructed record can reach production only in one exact frozen release and
Promotion Manifest with valid human Approval, executed by the promotion worker.
This repository remains `DESIGN_ONLY`.

ADR 0087 adds five readiness cases and three controlled pairs. The current
reconstruction catalogue therefore has 63 direct cases, 63 primary cells, and
35 pairs, making 184 direct cases with the ordinary baseline. The remaining
genuine product decision is ADR 0043's LLM-versus-deterministic allocation,
particularly model proposal or challenge of Reconstruction Plans and Gazette
event extraction. This decision authorizes documentation only.

## 2026-08-14 — Reconcile reconstruction with later HKeL and suspend defects narrowly

ADR 0086 keeps ordinary lightweight HKeL monitoring while a reconstruction is
active and performs bounded full acquisition only after a relevant change.
Valid applicable HKeL always replaces reconstructed serving through the normal
complete release, Approval, and promotion gates; comparison does not become a
new authority gate over HKeL.

Comparison requires the same Legal Item, locations, authentic languages, event
horizon, applicability branch, period, and dependency boundary. Additional
overlapping changes produce `COMPARISON_NOT_ISOLATABLE`; the system replaces
with HKeL but neither scores the reconstruction nor reverse-reconstructs a
synthetic comparison version. Invalid HKeL candidates neither replace nor
become comparison truth.

A material mismatch is attributed to the smallest proved evidence, mapping,
operation, applicability, bilingual, rendering, identity, or build component.
All active and pending work using that component is re-evaluated; eligible
latest-HKeL fallback replaces suspect reconstruction until corrected. Unbounded
causes suspend the complete affected rulebook/build profile. Restart requires a
new regression case, full affected suites, impact reconciliation, and a new
attestation.

ADR 0086 expanded the reconstruction catalogue to 58 cases, 58 primary cells,
and 32 pairs, making 179 direct cases with the ordinary baseline at that
checkpoint. ADR 0087 later expands it to 63, 63, and 35. This decision
authorizes documentation only.

## 2026-08-14 — Define the Reconstructed Consolidation Artifact contract

ADR 0085 fixes one strict immutable `rca_` package for every successful Plan.
The package contains the manifest, complete English and Traditional Chinese
trees and source units, reconstructed location units, Bilingual Alignment Map,
dependency and source-unit coverage proofs, derivation map, and identity-
lineage result. It references the Plan but not the Execution Report, preventing
a fingerprint cycle; the Report references the final artifact.

Every final source unit is either byte-identical unchanged base content or the
result of one exact admitted operation and official authentic-language
amendment evidence. There is no generated, inferred, translated, manual,
engine-corrected, or catch-all derivation. One unaccounted byte or structural
relationship invalidates the atomic artifact.

Reconstructed location units are ordinary renderer input, not Serving Records.
They contain no Pinecone metadata, warning, embedding, or final partition. The
ordinary legislation renderer later creates the strict six-field records and
ADR 0080 warning. The next topic is later-HKeL reconciliation and monitoring.
This decision authorizes documentation only.

## 2026-08-14 — Define strict Reconstruction Plan and Execution Report contracts

ADR 0084 fixes strict closed JCS JSON contracts for the immutable Reconstruction
Plan and Reconstruction Execution Report. Register-issued identities use
`rpl_`, `rop_`, `rex_`, and `rca_` plus 48 lowercase hexadecimal characters;
identity remains separate from the SHA-256 fingerprint of complete canonical
artifact bytes.

One Plan covers one Legal Item, latest applicable bilingual HKeL base, cutoff,
applicability branch, and dependency-closed result. It binds exact evidence,
events, effect decisions, contracts, locations, dependency proof, English and
Traditional Chinese streams, operation preconditions and expected results, and
the accepting Legal Desk decision. A proved one-language-only correction may
use an explicit unchanged stream; it cannot fabricate a no-op edit or
translation.

The Report accounts for every planned operation, including operations not run
after atomic failure, and fixes processing, review, reason, Rule Trace,
coverage, selection, and exact artifact consequences. Normative Reports omit
wall-clock and host noise so clean runs reproduce byte-for-byte. Neither Plan
nor Report enters Pinecone or embeddings. The next topic is the Reconstructed
Consolidation Artifact contract. This decision authorizes documentation only.

## 2026-08-14 — Freeze the Hong Kong reconstruction conformance catalogue

ADR 0083 freezes 56 direct reconstruction cases, 56 matching primary coverage
cells, and 30 controlled high-risk pairs. The count comes from direct coverage
of all eight operations and distinct chain, applicability, bilingual,
dependency, artifact, fallback, serving, security, reproducibility, and later-
HKeL branches rather than a chosen target.

The first 32 cases prove evidence-to-plan decisions. The remaining 24 prove
deterministic plan-to-artifact execution, serving, fallback, traceability, and
later-HKeL replacement. Every case, cell, and pair member must pass; no average
score or broad integration test compensates for a missing direct branch. The
existing 121 cases plus these 56 make 177 direct cases for a reconstruction-
enabled Hong Kong Legislation profile.

This suite does not call a model. Any future LLM plan-proposal workflow requires
separate semantic admission under ADR 0043, while this suite remains the exact
final-output contract. The next topic is the strict Reconstruction Plan and
Execution Report artifact contracts. This decision authorizes documentation
only. ADRs 0086 and 0087 later expand the catalogue to 63 cases, 63 cells, and
35 pairs for later-HKeL and readiness branches.

## 2026-08-14 — Use a closed deterministic Hong Kong reconstruction operation registry

ADR 0082 fixes eight exact source-backed amendment operation classes: exact
text substitution, closed-scope occurrence substitution, complete-node insert,
delete and replacement, exact renumbering or relabelling, explicit complete-
node movement, and closed structured-region replacement. There is no catch-all,
fuzzy match, translation, inferred cross-reference repair, model-authored final
wording, or human free-text override.

Every operation binds authentic-language evidence, legal effect, commencement,
applicability, the exact base and target, before and after states, match set,
order, dependency closure, and hashes. English and Traditional Chinese execute
separately and must reconcile. All changes for one dependency-closed serving
unit succeed atomically or that reconstruction does not exist; an independent
sibling may proceed only when complete evidence bounds the failure.

The engine validates an immutable Reconstruction Plan and emits an immutable
Reconstruction Execution Report. Unsupported or ambiguous work records its
exact reason and Coverage Gap, then uses the ADR 0079/0081 warned latest-HKeL
fallback where eligible. ADR 0043 still governs any future LLM proposal role;
deterministic rules always produce final bytes. The next topic is the exact
reconstruction conformance catalogue. This decision authorizes documentation
only.

## 2026-08-14 — Accept the latest applicable official HKeL copy

ADR 0081 permits matching official HKeL assisted copies for ordinary current
records, ADR 0080 reconstruction, and the ADR 0079 unchanged-text fallback
across every covered Hong Kong Legislation scope. A newer complete assisted
HKeL version is not held back merely because an older verified version exists.
Verified or assisted status remains preserved internally but creates no
separate serving treatment or authority note by itself.

The relaxation concerns HKeL's verification label, not record accuracy. Exact
official origin, matching bilingual XML and HKeL copies, version and identity
agreement, structure-sensitive reconciliation, evidence preservation, and
traceability remain mandatory. The active assisted-copy source role becomes
`HK-LEG-HKEL-ASSISTED-COPIES`; the fourteen-source Hong Kong inventory count is
unchanged.

The reconstruction warning now says `latest applicable HKeL copy` rather than
`latest verified HKeL copy`. This decision authorizes documentation only.

## 2026-08-14 — Allow evidence-bound searchable Hong Kong reconstruction

ADR 0080 supersedes ADR 0023's reconstruction deferral. When an operative Hong
Kong amendment is proved but HKeL has not published the matching consolidation,
the pipeline may select a warned `RECONSTRUCTED_CONSOLIDATION` record. It must
start from the latest applicable bilingual HKeL base supported by matching
verified or assisted official HKeL copies and have a
complete proved amendment and commencement chain, exact event ordering and
applicability, supported location operations, separately applied authentic
English and Traditional Chinese text, complete bilingual reconciliation, and
independently reproducible final bytes.

The register preserves the result as a Reconstructed Consolidation Artifact,
not an HKeL Official Version. Its Search Record otherwise uses the same
legislation type, Pinecone path, retrieval, ranking, source, citation,
quotation, bilingual rendering, release, promotion, rollback, and retirement
rules as official legislation. The sole special record-level treatment is the
approved mandatory English `metadata.authority_note` warning and its in-field
instruction to reproduce the warning when the record supports an answer.

Exactly one result serves per affected unit: eligible reconstruction first,
otherwise ADRs 0079 and 0081 warned latest applicable official HKeL text,
otherwise no record.
Unsupported, incomplete, conflicting, or ambiguous operations never create
reconstructed text. A generative model cannot author final text; any future
proposal role remains subject to ADR 0043. When matching HKeL consolidation
arrives, the official result replaces the reconstruction after ordinary gates,
and a material mismatch suspends the affected reconstruction rule or operation
class. This decision authorizes documentation only.

## 2026-08-14 — Fix the conditional reconstructed-consolidation authority note

Every searchable reconstructed Hong Kong Legislation record under ADR 0080
uses one stable English `metadata.authority_note` containing the
complete reconstruction warning followed by an explicit model instruction:

```text
[WARNING: RECONSTRUCTED CONSOLIDATION] As at [observation cutoff], HKeL had not yet published an updated consolidated copy incorporating the proved operative amendments affecting this provision. This record is a reconstructed consolidation using the latest applicable HKeL copy, version date [base version date], and the official amendment and commencement evidence identified in metadata.source, effective [effective date or exact applicability condition]. [INSTRUCTION: If you use this record to support any part of an answer, you must explicitly include the preceding warning in your response.]
```

The complete value is one metadata string. The warning is the text beginning
with `[WARNING: RECONSTRUCTED CONSOLIDATION]` and ending immediately before
`[INSTRUCTION: ...]`. If the model uses the record to support any part of an
answer, it must include that complete preceding warning explicitly in the
response. It does not reproduce the instruction itself. Mere retrieval does
not trigger the instruction. No separately reworded response-warning template
or downstream-model mechanism is decided at this stage.

ADR 0080 now incorporates this previously conditional warning into the accepted
reconstruction design. Neither decision authorizes implementation, model calls,
source access, publication, or Pinecone changes.

## 2026-08-14 — Keep the latest applicable HKeL text searchable during a known consolidation gap

ADR 0079 amends the earlier withhold-or-no-rebuild rule. When accepted official
evidence proves that a Hong Kong legislation change became operative but HKeL
has not yet supplied updated official consolidated text, valid latest
applicable official HKeL wording remains searchable for analysis as
`KNOWN_STALE_ANALYTICAL_CARRY_FORWARD`. It may replace a prior serving record
or be rendered into a warned record through the ordinary gates. A location
with no valid applicable official HKeL text has no record to retain. ADR 0081
allows verified or assisted supporting copies, so a newer eligible assisted
version is not displaced by an older verified one.

The retained `metadata.text` is byte-identical source wording from that latest
applicable official HKeL copy;
the pipeline does not apply amendment instructions or invent the unavailable
current wording. A controlled English `metadata.authority_note` says that the
change is known, the updated consolidation is missing, and the text must not be
described as current. Because this changes the six-field payload, the warned
record has a new Search Record ID while its unchanged text embedding may be
reused under the same admitted embedding contract.

The fingerprint-bound coverage channel independently supplies the warning to the user
interface and a deterministic six-field coverage context to the downstream
LLM. The complete candidate release accounts for the event, gap, warned
records, unaffected records, traceability, and replacement state. When the
updated official consolidation arrives and passes all gates, true current
records replace the warned analytical records. No arbitrary age cutoff removes
them while the consolidation gap remains unresolved. This decision authorizes
design documentation only.

## 2026-08-14 — Fix the Serving Record and traceability lookup encoding

ADR 0078 fixes one strict Serving Record with register-issued `rec_` identity
and exactly six metadata strings. Closed JSON Schema Draft 2020-12 profiles may
narrow values and exact limits but cannot add fields or change the outer shape.
Vectors, dates, schema identifiers, provenance, evidence, releases, grouping,
and citations remain outside the Pinecone record.

Contract JSON uses RFC 8785 JCS canonical UTF-8 bytes. Fingerprints use SHA-256
encoded as `sha256:` plus 64 lowercase hexadecimal characters. The Serving
Payload Fingerprint is the digest of canonical `metadata` only; the record ID
is excluded so identity and content proof remain separate. The authority-note
fingerprint is the digest of the exact UTF-8 note value.

The complete Record Traceability Lookup uses one canonical root manifest and
one exact NDJSON shard for every selected Release Scope. Each sorted entry
points from one Search Record to its profile, Legal Item, Official Versions,
Legal Locations, Release Scope, Corpus Release, evidence, and authority-note
decision. Empty scopes have explicit zero-byte shards. Unchanged shards may be
reused, while a lookup-only correction replaces the affected shard and root
revision without changing the Search Record or vectors.

Promotion requires a perfect one-to-one match between the flattened Desired-
State Inventory and the complete lookup. Missing, duplicate, orphaned,
mismatched, unsorted, undeclared, or non-reproducible content blocks the
candidate. Ask.Legal still performs no runtime lookup join. This decision fixes
normative design only; executable schemas, validators, data, Pinecone work, and
deployment remain unauthorized.

## 2026-08-14 — Separate HKEX multilingual retrieval and downstream-answer admission

The user authorized obviously dominant remaining Regulatory design choices to
be completed without routine approval. ADR 0077 therefore fixes three linked
but non-substitutable admission layers for English-only HKEX records:
multilingual ranked-ID retrieval, downstream-answer behavior over frozen exact
six-field contexts, and the complete pinned Ask.Legal query path. One layer's
score cannot compensate for another layer's failure.

The immutable profile binds exact English, Traditional-Chinese, and mixed-
language queries; relevance judgments and hard negatives; corpus and record
fingerprints; embedding and Pinecone-compatible retrieval settings; Ask.Legal
Query Contract and application build; downstream model and prompt; per-slice
gates; critical errors; and repeated-run, monitoring, and revalidation rules.
Every active path must pass all six metadata fields, including
`authority_note`, unchanged. Chinese explanations may paraphrase the
controlling English rule but may not claim official-translation status or
fabricate Chinese source quotations.

Exact queries, models, thresholds, repetitions, costs, profiles, and results
remain evidence-derived executable artifacts. If supported English-only
candidates later fail mandatory Chinese or mixed-language gates, records do not
serve and only then must the user choose between a compact official-Chinese
retrieval aid and full bilingual serving.

## 2026-08-14 — Allocate HKEX semantic work to change-gated two-pass proposals

ADR 0076 settles four named Regulatory generative-LLM proposal tasks: update
analysis and challenge, and record analysis and challenge. Complete supported
no change creates no model work. Deterministic admission and fast paths resolve
source-explicit facts first; a model is used only for changed, baseline, or
otherwise unresolved semantic mapping that the accepted evidence cannot reduce
to one exact deterministic branch.

Update tasks propose evidence-bound component mapping, dates, triggers,
cohorts, transitions, and lineage leads. Record tasks propose evidence-bound
semantic units, governing dependencies, references, and table, fee, and Form
relationships. Challenge tasks independently look for omissions, conflicts,
unsafe boundaries, and hidden uncertainty. Models never rewrite source text,
decide current state or identity, render records, or authorize serving.

The Regulatory Legal Desk remains the Source Rulebook executor and decision
authority. Complete ordinary work may be accepted automatically after both
passes and deterministic validation; humans handle only exact ambiguity,
conflict, novel structure, missing rule coverage, or another explicit review
trigger. Final state, rendering, partitioning, coverage, identity, release,
embedding, promotion, and operations remain deterministic or separately human-
approved. Exact task contracts and admission evidence remain unimplemented and
no model call is authorized.

## 2026-08-14 — Freeze the exact initial HKEX Regulatory conformance catalogue

ADR 0075 freezes the audited catalogue at 284 permanent direct cases, 284
matching primary coverage cells, and 57 complete high-risk pairs. The exact
checkpoint counts are `62/51/30/35/24/20/24/38`, comprising 143 evidence-to-
decision cases and 141 decision-to-artifact deterministic cases.

The user instructed the agent to complete obvious ADR-entailed work without
routine approvals. Coverage groups 3 through 6 and exact row expansion were
therefore derived from ADRs 0011, 0016, 0050, 0054, and 0069 through 0074 and
audited without inventing a product choice. The audit added direct cases for
each approved Regulatory authority-note meaning and package media-type or
permission failure before freeze.

Every row owns one matching primary cell; every pair has one positive and one
near-miss member; all accepted coverage and critical-error families have direct
primary coverage. The count follows the branches rather than a target or
Cartesian product. Existing IDs and meanings are immutable; later requirements
add IDs, while corrections require versioned supersession and impact evidence.
The freeze authorizes documentation only.

## 2026-08-14 — Escalate only genuine remaining HKEX design choices

For the seven remaining Hong Kong Regulatory Materials topics, the user
instructed the agent to decide and document any obviously optimal or already
entailed approach without requesting approval. Separate approval is unnecessary
for routine coverage expansion, exact case enumeration, pair and identifier
assignment, schema mechanics, audits, validation, documentation consistency,
or another choice with one clearly dominant answer under accepted ADRs.

The agent must ask the user only when a still-unresolved choice materially
changes legal meaning, product behavior, acceptable risk, cost, quality,
human-review burden, or another consequential outcome and no option clearly
dominates. Any escalation must state the actual tradeoff and recommendation,
not merely present implementation detail as a product decision.

This instruction changes the design collaboration workflow, not the system's
approval model. It does not authorize implementation, external access, model
or embedding calls, source acquisition, Pinecone or Azure changes, promotion,
deployment, commit, push, or any remote action.

## 2026-08-14 — Accept the second HKEX Regulatory conformance coverage group

The user approved applicability-branch effective-state and transition
requirements as coverage group 2 in the canonical working Regulatory
conformance catalogue. Direct cases must cover `CURRENT`,
`TRANSITIONAL_CURRENT`, `FUTURE_FIXED_DATE`, `FUTURE_CONDITIONAL`,
`SUPERSEDED`, `WITHDRAWN`, `UNKNOWN`, and `NOT_APPLICABLE`, their separate
ordinary dispositions, and the component summaries derived without flattening
the complete branch set.

The group requires exact fixed-date and cutoff boundaries, current-product
reconciliation, early-published future wording, ambiguous time, positive and
stale trigger evidence, all-of and any-of conditions, concurrent cohorts,
open-ended transitions, complete and partial replacement, exact withdrawal,
overlapping amendments, and conflicts or gaps. It separately tests ADR 0005's
carry-forward, withholding, and no-new-target consequences without treating a
technical source failure as a newly verified legal state.

Required high-risk pairs distinguish date reached with matching versus
conflicting wording, fresh non-occurrence versus stale trigger evidence, a
future amendment versus concurrent transitional branches, complete versus
partial replacement, official withdrawal versus disappearance, and complete
applicability context versus downstream inference. Serving future wording,
clock-only promotion, inferred trigger occurrence, reconstruction, transition
flattening, guessed cohort exhaustion, disappearance-based retirement, and
authority-note repair of `UNKNOWN` are critical errors.

This accepts coverage requirements, not unseen exact rows. Case and cell IDs,
pair membership, group counts, and the final count remain unfrozen until the
complete row-level catalogue is constructed and audited.

ADR 0075 later completes that audit and freezes the exact catalogue at 284
direct cases, 284 matching cells, and 57 pairs.

## 2026-08-14 — Accept the first HKEX Regulatory conformance coverage group

The user approved the source Fact Authority, corpus-membership, and board-
ownership requirements as the first group in the canonical working Regulatory
conformance catalogue. Every one of the five ordinary source roles requires a
direct permitted-use case and a controlled forbidden-overreach case. The group
also requires direct complete-union, freshness, supported-no-change,
incomplete-observation, board-bounded-failure, shared-gap, optional-source,
Source Contract Review, and approval-inference boundaries.

Every observed item receives exactly one `RULE_COMPONENT`, `EVIDENCE_ONLY`,
`EXCLUDED_NON_RULE`, or `UNRESOLVED_MEMBERSHIP` result. Included component
classes, excluded non-rule classes, distinct evidence-only uses, insufficient
proof, and conflict must receive direct coverage. Navigation, resemblance,
usefulness, publication, linking, or semantic similarity alone cannot prove
membership.

Every rule-component instance belongs to exactly one Main Board or GEM Release
Scope. A source artifact expressly supporting both rulebooks creates two
separate board-owned instances, not one cross-board component. Correct board
ownership, shared artifacts, multiple components in one artifact, conflicting
placement, missing ownership, duplicate, orphaned, double-owned, and wrong-
board results require direct coverage. Guidance entering the rule corpus,
wrong-board ownership, ambiguous double ownership, similarity-based serving,
one-source completeness, and concealment of a shared unbounded gap are
critical errors.

This accepts coverage requirements, not unseen exact case rows. Case and cell
IDs, pair membership, group counts, and the final count remain unfrozen until
the complete row-level catalogue is constructed and audited. The accepted
requirements are preserved in
`docs/design/HONG_KONG_REGULATORY_CONFORMANCE_CATALOGUE.md`.

## 2026-08-14 — Select HKEX Regulatory conformance cases by branches and targeted interactions

The user approved the scalable method for constructing ADR 0074's exact
coverage-cell and case table. The catalogue directly tests every stable legal
and technical result branch, tests both controlled sides of every designated
high-risk boundary, and directly tests every distinct mechanical failure or
result code. Selected combined cases prove interactions whose composition can
change the answer.

The catalogue does not attempt the Cartesian product of every independent
source, state, language, boundary, rendering, coverage, and identity fact.
That would grow without a corresponding completeness benefit. Combined and
end-to-end cases may add secondary proof, but they cannot replace a missing
direct primary case. The exact case count remains an output of the completed
audited table rather than a target, cap, round number, or aggregate score.

This approval settles the selection method only. The exact rows, IDs, pair
membership, group counts, and final case count remain to be constructed and
accepted. It authorizes documentation only.

ADR 0075 later constructs, audits, and freezes those rows and IDs.

## 2026-08-14 — Clarify the Legal Desk as a rule-bound logical authority

At the user's request, the existing ADR 0018 and ADR 0039 Legal Desk boundary
is now explicit. A Legal Desk is the named logical decision authority for one
jurisdiction-and-material pair, such as Hong Kong Regulatory Materials. It is
not synonymous with a human lawyer, an LLM, or a review queue. It may accept
fully resolved ordinary work automatically under an exact active Source
Rulebook, while an accountable Legal Desk Owner governs the rulebook and
handles only the human-review cases the rules require.

The Desk receives preserved evidence, structured source facts, prior register
state, and any permitted evidence-bound proposal. It applies stable rules,
records a complete Rule Trace, distinguishes established from unresolved facts,
and produces one immutable Legal Desk Decision containing the supported legal,
identity, disposition, coverage, record-eligibility, authority-note, and review
consequences. If no rule matches or evidence is insufficient or conflicting,
it blocks or quarantines under the rulebook rather than inventing an answer.

The Desk does not watch or scrape sources, change its rulebook during a
decision, treat model confidence as authority, render final bytes, issue IDs,
construct releases, approve promotion, deploy, or access LLM-provider,
Pinecone, Azure, backup, routing, or production credentials. Deterministic
rendering and corpus construction consume its accepted facts downstream, and
an authenticated human separately approves only the complete frozen Promotion
Manifest. This clarification adds no new operational authority.

## 2026-08-14 — Use two linked HKEX Regulatory conformance layers

The user approved ADR 0074. One immutable `hk-regulatory` conformance suite
contains a hidden-reference evidence-to-decision catalogue, an exact
decision-to-artifact deterministic catalogue, and one frozen coverage matrix.
The first proves that synthetic source-shaped evidence produces the correct
structured Legal Desk result. The second starts from accepted facts and proves
exact canonical records, authority notes, measurements, partitions,
source-unit coverage, traceability, identity consequences, readiness, failure,
and no-side-effect artifacts. Retrieval remains a later separate gate.

The package uses strict frozen root manifests, explicit case catalogues,
permanent non-answer-bearing IDs, package-local declared paths, exact artifact
roles, SHA-256 fingerprints, and no globs, mutable aliases, undeclared files,
network access, or answer leakage. Deliberately absent and unreadable inputs
remain different from accidentally incomplete packages; expected artifact
roles are exactly `EXACT`, `NONE`, or `NOT_APPLICABLE`.

The frozen coverage matrix, not an arbitrary case count, proves completeness.
Every required cell has a direct primary case, every executable case owns at
least one cell, every high-risk positive/near-miss pair has both members, and
every applicable stable rule and result branch has direct coverage. Critical
errors such as guidance entering the rule corpus, wrong-board ownership,
future wording served as current, reconstruction, omitted transition, Chinese
substitution, invented text, arbitrary splitting, incomplete source-unit
coverage, warning-based repair of unknown state, or external mutation cannot
be offset by an aggregate score.

Two isolated clean deterministic runs must be byte-identical. A separate
Regulatory Rulebook Conformance Attestation binds one exact suite, rulebook,
processing build, dependency lock, runner, and complete successful results.
The suite architecture itself does not select task allocation, prove real-
source currency, test retrieval, or authorize implementation or production.
ADR 0075 later freezes the exact row-by-row matrix, ADR 0076 settles the high-
level task allocation, and ADR 0077 settles retrieval and downstream-answer
admission architecture.

## 2026-08-14 — Construct complete source-faithful English HKEX records

The user approved ADR 0073. Every searchable current or transitional-current
HKEX applicability branch now uses the smallest complete official English
rule-bearing unit that is independently usable with its required governing
context. Complete means the selected semantic unit is uncut and retains its
qualifications; it does not require every subrule under one visible rule number
to enter every record. Separate rules are never packed merely to fill a token
budget.

Ordinary rules, definition entries, lists, notes, appendices, Practice Notes,
tables, Fees Rules, and Regulatory Forms use class-specific official
boundaries. Definitions normally produce one record per term. Cumulative or
otherwise inseparable conditions remain together. Tables retain headings,
units, row ownership, calculations, and notes; Forms use meaningful Parts,
instructions, declarations, or field groups rather than one record per blank.

Each record repeats only the minimum exact governing context needed for
correct independent use. Global definitions remain separate. Cross-references
retain their exact referring words, target locators, and eligible official
headings without recursively copying target rule text. A child that cannot
stand safely under that boundary stays with a larger official parent or is
quarantined if no faithful unit can fit.

The canonical English renderer uses stable material, market, component,
location, optional official-heading, material effective-context, and
serving-part labels, followed by optional required-governing-context and
referenced-location blocks and the complete prevailing English source block.
It includes no generated summary, Chinese text, URL, operational timestamp,
internal ID, reviewer prose, or model output. Tables and Forms use closed
versioned source-faithful presentation projections.

Overlong processing first measures the complete final `metadata.text` and
six-field metadata payload against exact pinned token and byte ceilings. It
recursively descends only through official English semantic structure and
chooses the fewest valid consecutive parts, filling each earlier part as fully
as possible. Arbitrary page, sentence, punctuation, character, token-position,
visual, and sliding-window cuts are forbidden. An indivisible oversized branch
is quarantined with a Coverage Gap rather than truncated.

Every result carries one immutable HKEX English Source-Unit Coverage Proof.
Every meaning-bearing current unit has one primary owner or an explicit blocked
or quarantined outcome; repeated context is labelled and points to that owner;
and future, historical, excluded, context-only, and presentation-only units are
explicitly accounted. Complete accounting does not claim serving readiness
when a current unit remains blocked or quarantined.

ADR 0073 authorizes documentation only. Executable schemas, conformance
packages, numerical limits, models, retrieval gates, implementation, sources,
Pinecone, Azure, promotion, and deployment remain separately gated.

## 2026-08-14 — Serve HKEX Regulatory Materials in English only

The user approved ADR 0072 after reconsidering ADR 0054's full-bilingual HKEX
record. Every Regulatory Search Record now contains the complete prevailing
English HKEX rule text and English applicability context only. It contains no
official or generated Chinese source block, Chinese-only duplicate, or
parallel Chinese vector. This amendment is specific to Hong Kong Regulatory
Materials and does not change bilingual Hong Kong Legislation.

Required English consolidated rulebooks, Regulatory Forms, Fees Rules, and
final update evidence govern current wording, structure, inventory, and
effective state. Missing, stale, conflicting, or incomplete required English
evidence still blocks or quarantines the affected boundary. An available
Chinese translation cannot substitute for English, and no warning or LLM
translation can repair the controlling source.

Official Chinese translations may be preserved outside Pinecone as optional
evidence for terminology, evaluation, investigation, audit, and possible
future design. They are not ordinary release dependencies, require no complete
cutoff freshness, and do not create a new Search Record merely by changing. A
Chinese discrepancy affects current processing only when it exposes a possible
English identity, version, effective-state, wording, or completeness defect.

English-only serving requires a pinned multilingual retrieval workflow to pass
complete Traditional-Chinese and mixed-language query evaluation. The
downstream LLM may explain the controlling English rule in Chinese but must not
claim that explanation is HKEX's official translation or fabricate a Chinese
source quotation. Failure of the Chinese-query gates blocks serving and
returns the design for an explicit official-Chinese retrieval-aid or bilingual
decision; it does not authorize silent extra fields, duplicates, or vectors.

ADR 0073 later settles exact conceptual record construction. Executable
schemas, models, evaluations, thresholds, and implementation remain open, and
no source, provider, Pinecone, Azure, promotion, or deployment action is
authorized.

## 2026-08-14 — Decide HKEX effective state per applicability branch

The user approved ADR 0071. Hong Kong Regulatory Materials effective state is
decided for one exact applicability branch at one frozen cutoff rather than
for a whole update, publication, Chapter, or rule from its update number or
publication date. A branch binds exact wording to the supported cohort,
transaction, reporting period, time window, external event, or other
limitation governing when it applies.

Each branch is current, transitional-current, future-fixed-date,
future-conditional, superseded, withdrawn, unknown, or not applicable. ADR
0069's one component state remains a derived inventory summary; it cannot
flatten complete branch decisions. A still-current ordinary predecessor does
not become transitional merely because a future amendment exists, while
concurrently current materially limited branches produce a transitional-current
summary.

Fixed-date and conditional changes remain in the Waiting Room before effect.
Reaching a date or proving a trigger does not cause clock-only promotion: the
resulting wording must reconcile with the controlling current English product.
Conflicting, lagging, stale, ambiguous, or missing evidence that could change
the current result produces unknown and Quarantine; the pipeline does not
reconstruct the rule. Optional Chinese evidence matters only when it exposes a
possible controlling English defect. Conditional changes require positive
fresh evidence from the exact official trigger source, with explicit all-of
and any-of behavior.

Every concurrently live transition branch remains explicit. Different
operative wording or obligations produce separate minimum self-contained
Search Records. The same wording with one simple limitation may remain one
record only when `metadata.text` communicates the complete condition. An old
branch becomes superseded only when a supported successor covers every former
application, or withdrawn only when exact evidence ends it without such a
successor. Disappearance and update number prove neither.

State remains separate from serving. Current branches require every other gate;
future branches stay in the Waiting Room; superseded and withdrawn branches
remain historical; and unknown branches enter Quarantine. ADR 0005 separately
governs explicit last-approved carry-forward, withholding, and no-rebuild
choices during technical source failure. The detailed deterministic,
LLM-assisted, and human allocation remains deferred. ADR 0071 authorizes
documentation only and no external or production action.

## 2026-08-14 — Use a lean HKEX Regulatory Materials Source Register

The user approved ADR 0070 after rejecting the implication that every useful
HKEX or SFC page is necessary for a legal-analysis AI. The ordinary Hong Kong
Regulatory Materials pipeline has exactly five Registered Source roles:
rulebook catalogue, consolidated rulebooks, Regulatory Forms, Fees Rules, and
final rule updates. Their reconciled union bounds and constructs the complete
current Main Board and GEM source-entry universe; no one role proves it alone.

The catalogue proves top-level product families, consolidated rulebooks prove
the current wording and contained structure, separately published Forms and
Fees Rules prove their own inventories and text, and final update packages
prove their assigned amendment, date, condition, transition, and mapping facts.
ADR 0072 later makes prevailing English evidence the required serving path and
Chinese translations optional non-serving support. Rule updates do not prove
that an external condition occurred and cannot replace the applicable current
compiled product.

Daily checks are lightweight and deterministic. Required roles must have a
complete successful Observation within 24 hours of the weekly cutoff, but
large artifacts are acquired only after a trustworthy change signal or when
unchanged bytes cannot otherwise be proved. Supported no change creates no
LLM, embedding, record rebuild, or Pinecone work.

The online Thomson Reuters rulebook is optional non-controlling discovery and
cross-check material. Source-precedence, language, component-inclusion,
exclusion, and the standing SFC approval framework are pinned as Source
Rulebook basis evidence rather than duplicated as routinely monitored feeds.
Guidance, consultations, FAQs, decisions, circulars, and general pages are
registered only when an exact bounded decision later needs their Fact
Authority.

There is no generic trigger source. Each conditional amendment names an exact
official source and receives heightened targeted checking only while pending.
If the event may have occurred but accepted evidence is stale or unavailable,
the component becomes unresolved rather than silently remaining future. For
ordinary final changes, a final HKEX update, matching current product, and the
pinned standing SFC framework may support the explicit inference
`APPROVAL_SATISFIED_BY_FINAL_PUBLICATION`; proposals or pending approvals may
not.

Registered source material is pipeline evidence, not downstream LLM context.
Only approved Search Record metadata is selected through Pinecone. ADR 0070
authorizes documentation only and no implementation, source acquisition,
provider, Pinecone, Azure, promotion, or deployment action.

## 2026-08-14 — Account for every HKEX Listing Rule component

The user approved ADR 0069's component-inventory and completeness contract.
Every frozen Hong Kong Regulatory Materials cutoff uses one immutable HKEX Rule
Component Inventory Package that accounts separately for the Main Board and GEM
Release Scopes. The stable ADR defines the package and accounting rules; the
changing live list of Chapters, rules, notes, appendices, Practice Notes,
Regulatory Forms, Fees Rules, and other components remains a versioned registry
artifact rather than mutable ADR content.

The declared inventory universe is bounded by exact registered rulebook
inventory and reconciliation source roles, not an unbounded website crawl.
Every observed entry receives one membership result: rule component,
evidence-only, excluded non-rule material, or unresolved membership. Every rule
component belongs to exactly one Main Board or GEM component instance. One
source artifact may support both rulebooks, but each board retains its own Legal
Location and context rather than sharing one ambiguous regulatory record.

Membership and ownership remain separate from effective state, material
disposition, and processing outcome. Current, transitional-current,
future-fixed-date, future-conditional, superseded, withdrawn, and unknown rule
states remain distinct. `PASS` does not mean searchable: excluded guidance may
pass its accounting result, while a known current component with unavailable
evidence is blocked. Proposed non-rule material receives no rule-component
effective state.

Each package separately reports source-entry accounting, component ownership
and structure, current-state accounting, and serving readiness. Complete
accounting may expose a blocked or quarantined component and does not make a
scope ready to serve. Missing, duplicate, unowned, double-owned, orphaned,
silently skipped, or fingerprint-mismatched objects invalidate the applicable
proof. A bounded Main Board failure need not invalidate GEM, but scope
isolation cannot hide a shared unbounded gap.

Package versions are immutable and predecessor-bound. A moved, renamed,
renumbered, split, merged, transferred, withdrawn, disappeared, or reappearing
entry creates an explicit new observation and comparison; disappearance alone
does not prove withdrawal. Supported no change requires every due inventory
role and every entry and component to reconcile exactly. Inventory processing
creates no Search Record and authorizes no source access, implementation, LLM,
embedding, Pinecone, Azure, or production action. The next design decision is
the exact Hong Kong Regulatory Materials Registered Source and Fact Authority
contract, which ADR 0070 later settles through the lean five-role design; ADR
0071 subsequently settles branch-level effective state and transitions.

## 2026-08-14 — Package Hong Kong Case Proposition evaluations and admission profiles

The user approved ADR 0068's future executable evaluation-package and profile
contract. Hong Kong Case Proposition admission now binds four separate
immutable objects in one non-circular order: the Evaluation Suite Package
defines cases, protected truth, evaluator, fixed gates, and completeness; the
Workflow Admission Profile freezes one exact candidate and all evidence-derived
values before sealed scoring; the Evaluation Run Set preserves the complete
case-by-repetition execution and result; and the final Workflow Admission binds
those objects plus separate Hong Kong Cases Legal Desk and system-owner
attestations.

The Evaluation Suite Package uses canonical declared artifacts and one root
fingerprint rather than directory discovery, mutable aliases, or aggregate
counts. Each semantic case separates the model-facing runtime-equivalent input,
the evaluator-only Reference Proposition Map, and the protected adjudication
record. The task receives ordinary legal identity and source evidence required
by ADR 0066 but never receives the evaluation case ID, human test label,
selection cell, pair role, expected answer, critical label, or score. Complete
real judgments, sealed membership, maps, adjudications, raw outputs, and
case-level operational results remain protected outside Git.

Sealed real judgments are chosen before candidate sealed results are inspected
through an exact branch-driven matrix spanning every required court family,
original language, opinion structure, length and segmentation shape,
proposition-result class, evidence form, materiality, boundary, and uncertainty
role. Development cases cannot count for admission. “Sealed” means that set
membership, evaluator truth, adjudication, and case-level results are hidden;
it does not claim that a public judgment was absent from provider training.
Exposure removes pristine admission and canary eligibility, triggers impact
review and replacement, and may convert the case into a regression case.

Reference Proposition Maps are frozen before candidate outputs are reviewed.
High-risk, critical, contestable, plurality, uncertain-attribution, and
alternate-boundary maps require independent second legal review. A previously
unlisted but potentially valid semantic equivalent cannot receive an ad hoc
pass: blinded adjudication either rejects it or creates a new map and suite
version followed by equal re-evaluation of every affected candidate.

The evaluator preserves explicit proposition matching, per-dimension and
per-slice numerators and denominators, critical and high-risk results, exact
deterministic artifacts, repetition completeness, and operational evidence.
Required executions end `PASS`, `FAIL`, `INVALID_RUN`, `EVALUATOR_BLOCKED`, or
`NOT_RUN`; only `PASS` satisfies a required repetition. The final run set may
be `ELIGIBLE` or `NOT_ELIGIBLE`, but eligibility grants only access to the dual
admission attestations and never production authority.

Fixed ADR 0067 gates cannot be weakened by a profile. Every evidence-derived
threshold, token, timeout, cost, concurrency, provider, retention, or drift
value must state its provenance, unit, method, sample, uncertainty or margin,
owner, and rationale and must be frozen before sealed admission scoring. Small
slices use exact per-case or per-distinction gates instead of misleading
percentages. A failed result may motivate a new immutable candidate, but no
threshold is lowered after viewing the result merely to make that candidate
pass.

ADR 0068 defines the package contract and selection method, not their actual
contents. Executable schemas, fixtures, selected real judgments and maps,
prompts, providers, models, numerical values, evaluator code, runs, and
attestations remain uncreated and unauthorized. The active design-level Hong
Kong Case Proposition package architecture is complete; the next recommended
greenfield design area is the detailed Hong Kong Regulatory Materials source
and `hk-regulatory` Source Rulebook audit.

## 2026-08-14 — Admit and monitor only complete Hong Kong Case Proposition workflows

The user approved ADR 0067. Hong Kong Case Proposition LLM use is admitted as
one exact complete fingerprinted workflow, never as a model name or aggregate
benchmark. The immutable admission package binds the source and parser
contracts, Coverage Ledger, packet builder, both ADR 0066 tasks, exact provider
and model, prompts and schemas, settings, validators, reconciliation, Legal
Desk rules, renderer, processing build, evaluations, thresholds, and all
operational profiles. Its lifecycle states are `CANDIDATE`, `EVALUATING`,
`ADMITTED`, `SUSPENDED`, `REVOKED`, and `SUPERSEDED`; only `ADMITTED` may
process ordinary new judgments.

The task runner reserves at least 20% of the admitted context window after
counting the prompt, schema, evidence, prior-stage data, and maximum response.
Material that cannot fit is deterministically repacketed without silent
truncation or cutting a Coverage Unit merely for size. An unfit complete packet
blocks or quarantines work.

Admission runs all 132 frozen synthetic cases and the registered sealed real-
judgment extension. Every deterministic case must pass in two clean byte-
identical runs. Ordinary semantic cases and real judgments run three times;
high-risk or critical cases run five times. Every high-risk distinction must
pass every repetition, no critical error may occur, and each separately pinned
semantic dimension and required slice must meet its own threshold. Equivalent
source-faithful wording and expressly allowed boundaries need not be byte-
identical. One blended average cannot hide a critical or weak slice.

Attempts are bounded: one initial provider attempt plus no more than two
transient retries; one representation-only schema repair; and one targeted
semantic re-analysis followed by one final targeted challenge. There is no
retry merely to sample until a convenient answer appears. The complete possible
per-judgment budget is reserved before starting. At 80% of a budget the system
reports and reduces non-urgent concurrency, at 90% it starts no new ordinary
judgments while reserved work finishes, and at 100% it makes no new provider
call.

The provider arrangement must prohibit training on task data and pin retention,
logging, region, encryption, abuse-monitoring exceptions, and deletion
behavior. Runtime retains full validation, Coverage Ledger, challenge,
reconciliation, and Legal Desk acceptance. Sealed canaries covering every
critical-error family and high-risk slice run weekly; the complete suite runs
at least every 90 days; and result-affecting changes or critical incidents cause
immediate applicable revalidation. Critical failures, fingerprint mismatch,
deterministic or evidence-boundary failure, unknown material provider behavior,
threshold breaches, or security incidents automatically suspend new calls.
Restart requires recorded resolution, impact analysis, revalidation, and a new
admission event.

This policy does not select a provider or model. ADR 0068 later separates the
sealed real-judgment inventory, maps, and evaluator into the candidate-
independent Evaluation Suite Package and places the exact candidate schemas,
prompts, provider and model, numerical thresholds, token, timeout, concurrency,
currency, retention, and drift values in a pre-frozen Workflow Admission
Profile. Their actual evidence-derived contents remain uncreated. No
implementation or provider call is authorized. See ADR 0067.

## 2026-08-14 — Define exact Hong Kong Case Proposition LLM task contracts

The user approved ADR 0066. The two semantic task families are fixed as
`hk-case-proposition-analysis/v1` and
`hk-case-proposition-challenge/v1`. The former proposes material Case
Propositions and complete evidence-linked unit uses; the latter independently
identifies supported objections to a deterministically validated proposal.

One semantic pass is one complete workflow over one exact judgment, not
necessarily one provider call. A short judgment may use one call in each pass.
A long judgment uses complete opinion-aware packet calls and a required
judgment-level integration or result-challenge call. Every primary Coverage
Unit remains accounted for, and context limits never redefine legal coverage.

Every task request binds exact contract, workflow, legal-source, complete-
coverage, supplied-evidence, task-constraint, and permitted prior-stage
material. Original court-authored text controls. Judiciary translations and
predecessor extractions are excluded by default to avoid translation dependence
and anchoring; later inclusion requires an explicitly admitted non-controlling
request kind, exact alignment, purpose, and separate fidelity and no-bias
evaluation.

The analysis contract permits only `FULL_JUDGMENT`, `EVIDENCE_PACKET`,
`JUDGMENT_INTEGRATION`, and `TARGETED_REANALYSIS`. Its response accounts for
every assigned primary unit and returns evidence-bound candidate propositions,
unit uses, materiality, attribution, required content, relationships,
handoffs, uncertainty, and a scope-limited conclusion. A partial packet cannot
declare a judgment-wide no-proposition result.

The challenge contract permits only `FULL_JUDGMENT_CHALLENGE`,
`COVERAGE_PACKET_CHALLENGE`, `JUDGMENT_RESULT_CHALLENGE`, and
`FINAL_TARGETED_CHALLENGE`. Its response accounts for every assigned unit,
candidate, relationship, and proposed judgment state and emits exact evidence-
linked objections. The challenger cannot edit or accept the proposal, choose a
reconciliation result, route directly to human review, or determine current
authority. An empty objection list means only that no supported objection was
found under complete challenge coverage.

Models select immutable Evidence Range IDs rather than supplying authoritative
copies of judgment quotations. Deterministic processing copies exact preserved
text into the renderer after acceptance. Neither task returns numeric model
confidence; evidence-bound semantic states, deterministic validation,
independent challenge, Coverage Ledger completeness, admitted evaluation
performance, Source Rulebook rules, and Legal Desk acceptance control the
result.

Responses use strict versioned JSON. One schema-repair request may fix
representation only and cannot change the semantic result. Semantic changes
must re-enter validation and challenge. Exhaustion blocks or quarantines work,
never creates a valid zero or accepts the latest result. ADR 0067 later fixes
the admission, repetition, context-reserve, bounded-attempt, budget,
monitoring, suspension, and revalidation policy. Exact models, prompts,
executable schemas, evidence-derived settings and budget values, ordinary
thresholds, provider values, and the separately protected sealed real-judgment
inventory remain future ADR 0068 suite-and-profile contents. No implementation
or provider call is authorized. See ADR 0066.

## 2026-08-13 — Use two-pass hybrid Hong Kong Case Proposition extraction

The user approved ADR 0065. Hong Kong Case Proposition extraction uses a
staged hybrid rather than pure deterministic extraction or a one-shot LLM
distillation call.

Deterministic Stage 1 proves source identity, artifact integrity, source-
supported court and opinion facts, complete Coverage Unit structure, exact
ranges, segmentation and dependencies, and task-admission preconditions. An
incompletely mapped judgment is blocked rather than partially submitted and
called complete.

The Stage 2 **Case Proposition Analysis Task** is the primary semantic pass. It
proposes material legal answers, evidence and context uses, qualifications,
applications, results, proposition boundaries, attribution, original-language
derived wording, handoffs, and uncertainty using only supplied exact evidence.
Stage 3 deterministic validation rejects mechanically impossible, mismapped,
incomplete, contract-breaking, or unsafe proposals. Schema validity does not
prove legal correctness.

Every judgment then receives a separate Stage 4 **Case Proposition Challenge
Task**. It looks for missed propositions, unsupported breadth, missing limits,
wrong opinion roles, bad split or merge boundaries, dependency gaps, and an
unsafe zero or complete result. It emits exact evidence-linked objections; it
does not vote with, edit, accept, or reject the first pass. Stage 5
deterministically reconciles every objection as already accounted for, invalid,
reopened, quarantined, blocked, or human review. One changed re-analysis gets
one final bounded challenge; infinite semantic cycling is forbidden.

At Stage 6 the Hong Kong Cases Legal Desk automatically accepts and reports an
ordinary result only when the exact admitted workflow applies, every
deterministic check passes, every unit, candidate, dependency, evidence role,
handoff, and objection is resolved, and the Coverage Ledger validly completes.
Human review is reserved for exact unresolved semantic ambiguity, uncertain
operative-opinion or adoption scope, an unresolved possible proposition, an
indivisible overlong serving decision, novel unsupported source structure,
repeated critical failure, or another versioned rulebook trigger. Length,
importance, Court of Final Appeal origin, Traditional Chinese, many
propositions, a new legal test, a valid zero, or one resolved re-analysis do
not alone trigger review.

Stage 7 deterministically finalizes the ledger and Rule Trace, identities,
canonical six-field payload, exact quotations and limits, traceability, and
correction or reuse effects before handing candidate records to corpus
construction. Later treatment separately determines current authority and
`metadata.authority_note`; embedding, Pinecone, approval, promotion, and
routing remain outside extraction.

At this decision, exact task IDs, schemas, prompts, models, settings, packet
limits, retry ceiling, evaluations, thresholds, costs, concurrency, timeouts,
retention, sampling, monitoring, and revalidation remained task-enablement
work. ADR 0066 later fixes the task-family IDs and conceptual contracts; ADR
0067 later fixes the runtime admission and monitoring policy. The executable
packages and evidence-derived immutable profile values remain open. No provider
call or implementation is authorized. See ADR 0065.

## 2026-08-13 — Freeze the 132-case Case Proposition extraction catalogue

The user approved ADR 0064 and the exact initial Hong Kong Case Proposition
extraction catalogue. It freezes 132 permanent direct case IDs, 132 matching
primary coverage-cell IDs, and 31 permanent high-risk pair IDs. The seven
checkpoint counts are `18/18/22/20/20/16/18`: four semantic groups containing
78 cases and three deterministic groups containing 54 cases.

The semantic catalogue covers materiality, proposition meaning and evidence,
split and merge boundaries, opinion attribution, every accepted Hong Kong
court family, original English and Traditional Chinese and mixed-language
reasoning, long segmented judgments, uncertainty, corrections, overlong
propositions, and hostile source text. The deterministic catalogue covers
source and Coverage Ledger arithmetic, candidates, evidence, quotation bytes,
rendering, limits, traceability, corrections, strict packages, answer leakage,
reproducibility, forbidden side effects, and full-workflow identity.

All 31 high-risk pairs have an exact positive and near-miss member. IDs never
encode answers and cannot be reassigned. Exact catalogues and coverage matrices
must list every primary case, cell, and pair role; discovery, globs, ranges,
broad tags, secondary coverage, counts, and aggregate scores cannot hide an
omission.

The 78 semantic rows are synthetic boundary cases, not a sufficient model-
admission corpus. ADR 0067's later task-admission policy requires sealed real Hong
Kong judgments and hidden independently adjudicated Reference Proposition Maps
across the same dimensions. Development and admission sets remain separate,
and real cases extend rather than replace the frozen synthetic IDs.

New requirements add permanent cases and cells. Correcting a frozen row
requires a new catalogue version, explicit mapping, preserved history, impact
declaration, and affected re-evaluation. Approval does not create fixtures,
admit a model, or set ordinary thresholds. ADR 0065 later settles the high-
level LLM-versus-deterministic allocation and ADR 0067 fixes the admission
policy without changing this catalogue. See ADR 0064.

## 2026-08-13 — Separate proposition semantics from deterministic extraction conformance

The user approved ADR 0063. Hong Kong Case Proposition extraction has two
separate linked suites. Semantic evaluation tests whether the workflow finds
the required legal propositions, avoids unsupported ones, preserves every
material qualification, attributes opinions correctly, uses correct boundaries
and exact evidence, respects original language, and distinguishes valid zero,
Quarantine, blocked work, and unselected propositions. Deterministic
conformance tests exact source and ledger accounting, candidate outcomes,
evidence mapping and quotation bytes, rendering, identities, limits,
traceability, reproducibility, and forbidden side effects. One blended score
cannot substitute for either proof.

Each semantic judgment has a hidden Legal Desk-adjudicated Reference
Proposition Map. It records required and forbidden meanings, exact support,
acceptable equivalent wording or boundaries, uncertainty results, and hidden
evaluation labels rather than prescribing one summary string. High-risk or
contestable maps require independent second review. Different extraction
methods may discover different intermediate candidates, but must account for
every candidate emitted and produce the same safe final legal content.

Coverage is branch-driven rather than count-driven and combines small
synthetic boundary cases with sealed real Hong Kong judgments. It directly
covers courts, original languages, opinion roles, zero/one/many results,
materiality and authority roles, split and merge boundaries, evidence forms,
long segmented judgments, corrections, hostile source text, and failures.
High-risk distinctions use positive and near-miss pairs. Answer-bearing IDs,
expected maps, complete real judgments, protected outputs, and operational
results remain hidden and outside Git as applicable.

Admission binds the complete extraction workflow—parser, contracts,
segmentation, method, any model and prompt, validators, renderer, Source
Rulebook, build, catalogues, thresholds, and evaluator—not a model name. Every
deterministic case must pass exactly, designated critical errors have zero
tolerance in the frozen semantic admission set, every semantic dimension and
high-risk slice must pass its own threshold, and repeated runs must satisfy a
pinned stability rule without averaging away critical failure.

Critical errors include fabricated propositions or evidence, false complete-
no-proposition results, materially broadened rules caused by omitted limits,
operative-opinion inversion, synthetic majority reasoning, confident treatment
of required uncertainty or incomplete coverage, and source-content escape from
the task boundary. This finite-set gate does not claim universal runtime
perfection; the Coverage Ledger, validation, Quarantine, monitoring, sampling,
and regression expansion remain mandatory. Retrieval and downstream-answer
quality remain a separate later gate. Exact catalogue rows, schemas, fixtures,
threshold numbers, repetition counts, corpus size, and extraction-task
allocation were still open at this decision; ADRs 0064 and 0065 later settle
the catalogue and high-level allocation, and ADR 0067 fixes the repetition and
runtime admission policy. ADR 0068 later assigns the protected sealed real-
judgment inventory to the Evaluation Suite Package and the evidence-derived
ordinary thresholds to the frozen candidate profile. See ADR 0063.

## 2026-08-13 — Require a complete Hong Kong Case Proposition Coverage Ledger

The user approved ADR 0062. Every exact Hong Kong judgment Official Version
receives one immutable fingerprinted Case Proposition Coverage Ledger. Before
semantic extraction, deterministic structure processing inventories every
opinion and every ordered Coverage Unit, including paragraphs, headings,
footnotes, tables, quoted blocks, orders, dispositions, schedules, appendices,
and source scaffolding. If the complete original artifact cannot be enumerated
and mapped faithfully, processing is blocked rather than silently partial.

Every unit ends resolved, quarantined, or blocked. A resolved unit is used as
proposition evidence, necessary context, or examined non-propositional
material with a stable reason family. Treatment-only material is handed to the
separate treatment-screening inventory. Segmentation never changes coverage:
each unit occurs once as primary content, repeated context uses exact
dependency links, and all adoption across opinions requires express evidence.

Every discovered proposition candidate ends accepted, rejected with a reason,
merged, split, quarantined, or blocked. Every accepted proposition has the
complete ADR 0060 evidence roles, every serving record maps to that proposition
and ledger fingerprint, and exact arithmetic rejects omissions, duplicates,
orphans, unresolved dependencies, or fingerprint mismatches.

The final result is `COMPLETE_WITH_PROPOSITIONS`,
`COMPLETE_NO_PROPOSITION`, `ACCOUNTED_WITH_QUARANTINE`, `BLOCKED`, or
`INVALID`. A valid no-proposition result requires complete original-version,
opinion, unit, candidate, and treatment-screening accounting. It remains
different from a judgment that contains propositions but currently serves
none, and from a judgment the system cannot safely decide.

The ledger is internal and creates no Pinecone vector, metadata field, or
query-time join. It proves complete accounting and exact traceability, not
semantic correctness by arithmetic alone. ADR 0043 initially deferred who or
what makes semantic extraction decisions; ADR 0065 later settles the high-
level allocation and requires that workflow to emit this ledger. See ADR 0062.

## 2026-08-13 — Split and merge Hong Kong Case Propositions by legal meaning

The user approved ADR 0061. Proposition boundaries are decided before record
size is measured. Split when legal answers can be searched, stated, or applied
independently. Keep together every element, threshold, definition, exception,
qualification, application, and exact passage needed to prevent the rule from
becoming incomplete or misleading.

Repeated or fragmented statements in one opinion merge only when their legal
answer, issue, scope, opinion, and authority role are the same. One joint or
lead opinion joined by several judges does not create duplicates. Concurrences,
dissents, separate opinions, and unresolved plurality positions remain
separately and prominently attributed. Reasons from another opinion in the
same delivered judgment enter one record only through express, scope-clear
adoption. Inferred agreement and shared outcomes cannot manufacture a majority
proposition.

Independent and alternative legal grounds split. Shared context is repeated
only to the minimum needed for each record to stand alone; there is no context-
only or whole-case companion vector. A separately delivered judgment that only
adopts, follows, or approves earlier reasoning creates Later Treatment instead
of a duplicate proposition unless it independently states and applies a
complete proposition.

Overlong records may remove only optional repetition, use the smallest complete
exact support, and shorten the derived statement without changing meaning.
They split only at genuine independent-proposition boundaries. An indivisible
complete proposition that still cannot fit enters Quarantine with the
applicable Coverage Gap; it is never divided into fragments that require a
query-time join.

Correct initial records need no artificial split lineage. Later correction of
an improperly combined record uses `split_from`; correction of improperly
fragmented or duplicate records uses `merged_from`. Prior records and history
remain preserved, and these events are processing corrections rather than
judicial treatment. ADR 0043 initially deferred the extraction-method
allocation; ADR 0065 later settles the high-level two-pass hybrid allocation.
See ADR 0061.

## 2026-08-13 — Define one evidence-bearing Hong Kong Case Proposition record

The user approved ADR 0060's output-and-evidence contract. One searchable Hong
Kong Case Proposition record represents one material legal answer from one
attributed judicial reasoning path. It is neither a sentence chunk nor a whole-
case summary. One judgment may validly produce zero, one, or many records.

A proposition qualifies only when its legal issue and answer are identifiable,
its exact opinion and authority role are established, exact source passages
support the proposition and every material qualification, the necessary facts,
procedural posture, application, and result can be stated without speculation,
and the result forms one honest searchable unit without blending distinct
opinions or rules. Materiality does not require novelty. Bare citations,
unadopted submissions or quotations, issue-free facts, outcome-only statements,
procedural chronology, and administrative directions do not qualify alone.

Each `metadata.text` uses a stable labelled layout containing the case,
citation, court, date, opinion and authority role, legal issue, clearly marked
derived proposition statement, necessary context, qualifications, application
and relevant result, and the smallest complete set of exact original-language
judgment passages and locators that proves the record. Both the derived
statement and exact support reach the downstream LLM because Ask.Legal has no
ordinary query-time join to internal traceability. The complete judgment and
evidential dossier remain outside Pinecone.

Multi-element tests stay together when they operate as one rule. Independently
applicable legal answers split. Qualifications stay with the rule they limit,
and different opinions never blend. Complete judgment and opinion coverage is
mandatory; silent truncation is forbidden. A valid zero-record result requires
complete review, while an unresolved possible proposition enters Quarantine.

The six serving fields, original-language rule, and separate
`metadata.authority_note` remain unchanged. This decision defines the required
result but did not itself allocate extraction between deterministic code, a
generative LLM, the Legal Desk, or human review. ADR 0065 later settles that
high-level allocation. See ADR 0060.

## 2026-08-13 — Freeze the audited 155-case Hong Kong treatment catalogue

The user approved ADR 0059 and the audited exact initial treatment conformance
catalogue. The frozen universe contains 155 permanent case IDs and 155 matching
primary coverage-cell IDs across 13 discovery, 40 semantic-analysis, 32
validation, 22 Legal Desk decision, 14 authority-note, 12 immutable-record, and
22 release or promotion cases. It also freezes 21 high-risk pairs, each with
exactly one positive and one near-miss member.

The table freezes normative scenarios and required results, not an arbitrary
target count. Future requirements may add cases, but existing IDs and meanings
are never reassigned or silently rewritten. A correction requires new versioned
identity, an impact declaration, preservation of prior packages and results,
and revalidation.

This approval does not admit a model or authorize implementation. Exact
schemas, fixture bytes, rule and reason codes, validators, real-judgment
evaluation artifacts, Source Rulebook values, Case Proposition extraction,
runtime task settings, Query Contract integration, and build attestation remain
later work. See ADR 0059.

## 2026-08-13 — Derive incoming and outgoing treatment views from one internal relationship

The user approved recording both how an earlier proposition has been treated
and how a later judgment treats earlier propositions. The system stores one
authoritative directional Later Treatment relationship from the later
decision, version, opinion, and exact passages to one exact earlier Case
Proposition. It deterministically derives an Incoming Treatment View keyed by
the earlier proposition and an Outgoing Treatment View keyed by the later
judgment and, when available, its treating proposition. The projections carry
the same relationship ID and fingerprint and do not duplicate the legal fact.

A treating Case Proposition link is optional. A no-proposition judgment may
still treat or overrule an older proposition, so the pipeline never invents a
proposition merely to anchor an edge. An unresolved target remains a Treatment
Lead rather than a settled incoming relationship. Corrections, withdrawal,
reversal, and supersession never overwrite an accepted edge: they append the
required successor or supersession facts, use the outgoing view to identify
every affected earlier proposition, and recompute current incoming results.

Pinecone does not receive treatment-relationship records, graph vectors,
exhaustive outgoing lists, a new metadata field, or a whole-case treatment
summary. The earlier proposition may expose selected incoming treatment through
`metadata.authority_note`. The later judgment exposes treatment reasoning only
when it belongs in a genuine material Case Proposition's `metadata.text`; its
own `authority_note` continues to describe subsequent treatment of that later
proposition. Bare citations remain internal. Pinecone alone therefore does not
promise exhaustive citator-style enumeration; that would require a separately
approved graph query path. See ADR 0058.

## 2026-08-13 — Use strict non-leaking Hong Kong treatment conformance packages

The user approved ADR 0057's stable namespaces and package contract. Semantic
IDs distinguish whole-judgment discovery from candidate analysis. Deterministic
IDs distinguish validation, Legal Desk decision, authority-note rendering,
record and embedding transitions, and release or promotion consequences. IDs
are opaque within those checkpoints: they never reveal court, treatment,
expected success, real case, locator, or answer, and are never reassigned.

Semantic and deterministic cases use separate frozen catalogues and strict
manifests. One frozen coverage matrix—not file discovery, globs, broad tags, or
counts—proves completeness. Every case is explicitly listed and is the primary
case for at least one required coverage cell. Every high-risk cell has a linked
positive and near-miss pair. Secondary coverage cannot hide a missing direct
case.

The model receives only the admitted evidence and task contract. It never sees
the case ID, title, purpose, coverage labels, pair relationship, expected
answer, adjudication, score, or critical-error tags. Small synthetic packages
may live in Git; protected real-judgment artifacts, answers, model outputs, and
operational results stay in registered external storage.

Every deterministic artifact role is explicitly `EXACT`, `NONE`, or
`NOT_APPLICABLE`. Missing output cannot pass as zero output. Applicable
artifacts validate and match canonical bytes, two clean runs must be identical,
and each fixture proves no network, source, provider, Azure, Pinecone, routing,
credential, production-store, or undeclared-file access. See ADR 0057.

## 2026-08-13 — Separate semantic treatment evaluations from exact contract fixtures

Hong Kong later-treatment conformance uses two linked suites. Semantic model
evaluations test whether the LLM identifies the correct evidence, proposition,
treatment class, expression mode, scope, materiality, opinion status, and
uncertainty in varied judgment language. They use schema-bound expected answers
and may permit explicitly approved immaterial variants; they do not grade
preferred explanatory prose.

Deterministic contract fixtures start from a frozen proposal or Legal Desk
decision and require exact validation, Rule Trace, treatment graph, authority-
note bytes and fingerprint, record identity and selection, forward lineage,
embedding action, release and inventory arithmetic, update outcome, review
route, Promotion Manifest eligibility, and forbidden-side-effect results. A
semantic score cannot prove these outputs, and exact fixtures cannot prove that
an LLM understands real judicial language.

The catalogue is coverage-driven, not assigned an arbitrary total. Every
treatment, authority and opinion boundary, expression and scope branch,
renderer-budget result, immutable transition, uncertainty path, correction and
later-status change, update outcome, model safety failure, and review route
needs direct coverage. High-risk boundaries require paired near-misses.

Every deterministic fixture must pass exactly. Model admission uses separately
pinned aggregate and boundary thresholds and zero tolerance for designated
critical errors in the frozen evaluation set, including fabricated evidence,
false conclusive overruling, operative-opinion inversion, and confident
resolution of required uncertainty. This is an admission rule, not a claim that
a probabilistic model can never err on unseen judgments; runtime validation,
Quarantine, review, monitoring, and revalidation remain mandatory. See ADR
0056.

## 2026-08-13 — Use immutable selection transitions for Hong Kong case treatment

The user approved the exact record-transition map for later treatment. Search
Records remain immutable, and the live Pinecone Index is never edited in place.
For each affected Case Proposition, the next complete Desired-State Inventory
either reuses the selected exact record, selects a different exact record, or
selects no record when the proposition is no longer current authority.

Internal treatment that leaves the exact six-field payload unchanged reuses the
same Search Record even when treatment and release accounting changes. A new
authority-note rendering selects a different record. If that exact payload has
never existed, the register creates a forward successor; if a preserved exact
record becomes legally supported again, the later Serving State reselects it
through a new append-only selection or reinstatement event. It does not create
a duplicate record or a backward lineage edge. Search Record lineage remains
acyclic.

An authority-note-only successor may reuse the cached embedding when
`metadata.text` and the embedding contract are exact. Full conclusive
overruling creates no warning-only successor: the exact proposition is omitted
from the next current inventory while its records, evidence, and history remain
preserved. Partial overruling ends selection of the combined record and permits
only narrower propositions independently supported by the earlier judgment.
The system never rewrites an earlier court merely to retain a vector.

Uncertain treatment creates no guessed replacement, retirement, or
reinstatement. It follows the accepted Quarantine, carry-forward, withholding,
or no-new-target rules. Every serving transition still requires a complete
frozen release, Promotion Manifest, human Approval, replacement Pinecone Index,
verification, and routing switch. See ADR 0055.

## 2026-08-13 — Expose selected meaningful case treatment, not bare citations

Every accepted Hong Kong case-treatment relationship remains in the internal
treatment graph, but `metadata.authority_note` gives the downstream LLM a
compact current authority summary rather than only adverse warnings. The
renderer may use three ordered clause families: mandatory `[WARNING: ...]`
clauses first, selected `[SUPPORT: ...]` clauses second, and selected neutral
`[CONTEXT: EXPLAINED]` clauses last.

`APPROVED` and `FOLLOWED` are eligible supportive authority. `APPLIED` is
included when the application is materially useful to proposition-level
authority assessment. `EXPLAINED` is included only when the later judgment
materially clarifies the meaning, scope, or use of the exact proposition; it
is neutral context and must not be rendered as endorsement. `CITED_ONLY`
never creates an LLM-facing note because citation alone proves no support,
adoption, or authority strength.

There is no fixed support- or explanation-clause count. The renderer includes
every current material non-repetitive support or explanation that fits the
pinned authority-note metadata and downstream-context budget. Equivalent
treatments are consolidated. Treatments remain distinct when they add a
different court-authority level, proposition scope or issue, later confirmation
after adverse or limiting treatment, a materially different reason, or another
independent authority signal.

Operative opinion status, Hong Kong court authority, treatment significance,
exact proposition scope, continuing status, and later tie-breaking facts
control ordering and compression when the budget is approached; they do not
create an arbitrary clause-number cap. Citation counts and numerical
authority-strength scores are forbidden: many weak citations cannot be
represented as outweighing one controlling treatment decision.

The exact value remains `"None"` when no warning, selected material support,
or selected material explanation applies. Every omitted relationship remains
internally traceable. A change to the selected rendering selects a different
exact Search Record and may reuse the unchanged text embedding. A previously
unseen payload receives a new ID; an exact former payload may be reselected
under ADR 0055. A new bare citation or consolidated repetitive treatment
creates no serving-record churn.

Every distinct current mandatory warning must be represented before support or
context. Faithful templates may consolidate genuinely equivalent warnings but
must not discard a material effect. If the complete mandatory warning meaning
cannot fit the pinned budget, the proposition cannot serve with an incomplete
note and follows the accepted Quarantine, withholding, or no-new-target rules.
When optional support and context exceed the remaining budget after faithful
consolidation, the deterministic ranking keeps the most legally informative
rendering and preserves every omitted relationship internally.

## 2026-08-13 — Automate normal treatment and review only uncertainty or exceptional change

Normal and common Hong Kong later-treatment decisions do not require separate
human treatment review. After the approved LLM semantic analysis, complete
evidence contract, deterministic validation, and exact Source Rulebook rule
pass, the Legal Desk may automatically accept the ordinary internal or serving
consequence. This includes routine support-note and warning-note changes. Each
result, Rule Trace, and exact record or release diff is reported to the human.

Human treatment review is reserved for uncertainty or ambiguity and for an
objectively exceptional change to the current authority structure. Unresolved
language, competing plausible classes, unsafe proposition mapping, unclear
opinion authority, material hierarchy or finality uncertainty, conflicts, or
the absence of an accepted rule cannot be auto-accepted.

The exceptional-change bar is intentionally high. Importance, novelty, a
Court of Final Appeal judgment, express overruling, reinstatement, a new legal
test, or a large but uniform routine batch does not qualify by itself. Clear
express overruling of one or a bounded set of propositions, clear reversal or
setting aside, evidence-backed reinstatement, and a new or changed test whose
affected universe is safely bounded remain ordinary automated decisions and
are reported.

`EXCEPTIONAL_CHANGE_REVIEW` has only two legal triggers:

1. an operative controlling decision changes the structure of precedent or
   hierarchy itself, including which bodies or classes of decision bind which
   Hong Kong courts, or invalidates an entire authority class rather than
   identified propositions; or
2. an operative controlling decision expressly replaces a foundational
   constitutional or jurisdiction-wide doctrine, its impact crosses multiple
   independent doctrinal lines rather than one citation chain, and it exceeds
   both high absolute and proportional impact thresholds pinned by the Source
   Rulebook.

An LLM cannot call a change exceptional. Unbounded impact, a missing accepted
rule, or uncertainty about a trigger routes to `UNCERTAINTY_REVIEW`. Separate
operational controls may pause unusual volume, cost, retirement count, or
target diffs without turning the underlying legal decision into exceptional
human treatment review.

This decision concerns per-treatment review. It does not remove the separately
settled human Approval for the complete frozen Promotion Manifest. Routine
treatment decisions are reported rather than individually approved, but every
result that enters a candidate Serving State remains visible in that complete
package.

This is the accepted current policy, not an invisible permanent constant. Its
future evaluation must report automated and human-routed outcomes, structured
corrections or reversals, sampled misses, and exact serving effects. Threshold
or routing changes require a new versioned rulebook or ADR with an impact
declaration; they must not be silently tuned to make the reported results look
better. Sampling is a non-blocking quality audit, not routine per-treatment
approval.

## 2026-08-13 — Use LLM semantic analysis with exact treatment evidence thresholds

The LLM is the primary semantic analyser for Hong Kong judgment treatment
because courts express the same legal relationship through varied wording and
context. Deterministic processing may identify formal citations and obvious
leads, but it must not treat keyword lists, fixed phrase rules, or the absence
of a recognized phrase as a reliable substantive treatment decision.

Deterministic controls instead validate the accepted source and complete
opinion structure, exact passages, identities, aliases, court and jurisdiction
facts, hierarchy constraints, schema, scope fields, coverage ledger, and that
every proposed claim stays inside supplied evidence. They may reject an
impossible or unsupported proposal, but they do not establish semantic
correctness merely from matching words. The LLM proposes semantic treatment,
expression mode, proposition mapping, scope, and materiality; the Legal Desk
accepts, corrects, rejects, or quarantines the legal effect.

Every substantive relationship requires the complete accepted treating and
earlier judgments, exact context and opinion attribution, exact or explicitly
unresolved identity and proposition mapping, authority and finality facts,
later-status checks, deterministic validation, and an accepted Rule Trace.
Model confidence, multiple-model agreement, HKLII labels or summaries,
headnotes, citation counts, similarity, or keywords are not legal evidence.

Direct semantic meaning, rather than a magic treatment word, satisfies
`EXPRESS`. `APPROVED`, `DOUBTED`, `CRITICISED`, `DISAPPROVED`,
`REFUSED_TO_FOLLOW`, and `OVERRULED` require express meaning.
`NECESSARY_REASONING` may support only `APPLIED`, `FOLLOWED`,
`DISTINGUISHED`, or `LIMITED` when the complete reasoning chain makes the
conclusion necessary and the Legal Desk accepts it. Ambiguity produces
`UNRESOLVED`, not a substantive label or automatic serving change.

## 2026-08-13 — Separate Hong Kong judicial treatment from database consequence

Hong Kong later treatment uses a five-axis decision model rather than one flat
label. It separately records: what the later judgment did with the earlier
proposition; whether that treatment was express, followed by necessary
reasoning, or ambiguous; the exact affected proposition and scope; the later
court's jurisdiction, hierarchy, opinion status, finality, and any separate
appellate disposition; and the resulting serving consequence.

Authority facts are a gate, not an automatic database instruction. The same
criticism may therefore be internal only, justify an authority-note warning,
or require Quarantine depending on who said it and in what opinion. A lower
court, dissent, concurrence not adopted by the operative majority, plurality
without a controlling common position, foreign court, or non-operative
discussion cannot be represented as overruling by the operative Hong Kong
court merely because its language is adverse.

`AFFIRMED`, `VARIED`, `REVERSED`, `SET_ASIDE`, and `REMITTED` remain separate
appellate dispositions. They trigger proposition review but do not
automatically classify or retire every proposition in the earlier decision.
Only express and conclusive overruling, mapped to the exact proposition and
supported by sufficient Hong Kong court and opinion authority, may support
retirement. Every support note, warning, Quarantine, withholding, retirement,
or reinstatement still requires an accepted Legal Desk Rule Trace.

## 2026-08-13 — Keep greenfield and legacy project memory separate

This repository records only greenfield instructions, decisions, approvals,
priorities, status, and next steps. Context from the legacy Distillation,
Release Store, Pinecone, or parent Dataprep workspaces is not imported and
cannot reorder or block greenfield work. Merely exposing both workspaces to an
agent creates no shared authority.

A legacy repository may be inspected only when the user explicitly requests a
named comparison or reference check. Such inspection does not change either
project and does not make a legacy decision a greenfield decision. Any
explicit cross-project task keeps separate continuity, authorization, and
handoff records for each project.

## 2026-08-12 — Classify HKEX Listing Rules as Hong Kong Regulatory Materials

The Hong Kong database will include the current effective Main Board and GEM
Listing Rules in a separate **Hong Kong Regulatory Materials** family. The
user-facing category is **Regulatory**, and each Search Record uses the existing
six-field envelope with `metadata.type: "regulatory"`. The family is not named
`Policy`: the Listing Rules are formal non-statutory exchange regulatory rules
made under section 23 of the Securities and Futures Ordinance and approved by
the SFC under section 24, not legislation, publisher commentary, or ordinary
guidance.

Main Board and GEM are separate Legal Items and Release Scopes. Each scope
completely accounts for the rulebook components that HKEX expressly makes part
of it. Guidance letters, FAQs, listing decisions, circulars, consultations,
and other non-rule materials remain outside the initial searchable scope and
may enter only through a later separately approved regulatory-guidance design.

HKEX-maintained consolidated PDFs control current wording over the
Thomson Reuters-maintained online presentation. Official amendment packages
and update notices supply fact-specific change, effective-date, condition, and
transition evidence. Future, conditional, and proposed changes stay outside
ordinary current search until their exact trigger is proved; cohort-specific
transitions remain explicit rather than being flattened into a universal rule.

ADR 0072 later supersedes this decision's original full-bilingual serving
paragraph. Each ordinary record now contains complete prevailing English rule
text and English applicability context only. Chinese translations are optional
non-serving evidence, while complete Chinese-query evaluation remains a
serving gate.

Every active query path and promotion contract must explicitly accept the new
`regulatory` type before these records can serve. See
`docs/adr/0054-classify-hkex-listing-rules-as-hong-kong-regulatory-materials.md`.
This is design authorization only and does not authorize implementation,
source acquisition, release publication, provider calls, Pinecone access,
promotion, or deployment.

## 2026-08-12 — Use staged hybrid analysis for Hong Kong later treatment

Hong Kong Cases later-treatment screening combines deterministic processing,
bounded LLM proposals, and Legal Desk decisions. Deterministic code validates
and structures the accepted judgment, extracts formal citations, resolves
identities and court relationships, prepares context, and maintains the
coverage ledger. An LLM may inspect the whole judgment for discovery and
orientation, but that pass cannot directly establish treatment or update a
record.

Each discovered candidate receives a separate exact evidence packet. The LLM
may propose the affected Case Proposition, treatment class, scope,
materiality, uncertainty, and exact supporting passages. Deterministic
validators reject unsupported or structurally impossible output. The Hong
Kong Cases Legal Desk alone accepts the legal effect that may revise
`metadata.authority_note`, withhold, retire, or reinstate a proposition.

A one-shot “read the judgment and update the database” task is forbidden. Long
judgments use opinion-aware, structure-preserving segments and an explicit
coverage ledger rather than silent truncation. The architecture is accepted,
but provider calls remain disabled until exact task schemas, prompts, models,
evaluations, thresholds, review rules, costs, and failure behavior are pinned.
ADR 0065 later settles the separate Hong Kong Case Proposition extraction
allocation. Gazette-event extraction and other unallocated candidate tasks
remain deferred under ADR 0043. See
`docs/adr/0053-use-staged-hybrid-analysis-for-hong-kong-later-treatment.md`.

## 2026-08-12 — Update Hong Kong Cases through bounded impact reconciliation

Each ordinary Hong Kong Cases update compares one frozen cutoff with one exact
accepted predecessor. Required official inventories determine supported no
change. Genuine signals open bounded acquisition and a transitive impact graph
covering the changed judgment, its propositions, material treatment, every
affected earlier proposition, and every affected court-year Release Scope.
Exact unaffected records and releases are reused.

Changed proposition text or `authority_note` selects a different exact Search
Record; a previously unseen payload receives a new ID, while ADR 0055 permits
proved reselection of a preserved exact record. An authority-note-only change
may reuse the exact text embedding. The update
keeps supported no change, accounting-only change, serving change, blocked,
and quarantined outcomes distinct. Missing judgment text may create an unknown
treatment gap that no generic authority note can cure.

HKLII remains `HK-CASE-HKLII-DISCOVERY`. It can find candidate judgments,
inventory differences, aliases, citations, historical leads, and possible
later treatment. Each result creates only a lead. An accepted originating
judgment and exact passages must prove any proposition, treatment,
authority-note, or retirement decision. HKLII cannot prove no change or cure
an official enumeration gap; its outage is nonblocking. An affirmative HKLII
difference is reconciled, evidentially dismissed, or left as explicit affected
work rather than silently ignored. See
`docs/adr/0052-update-hong-kong-cases-through-bounded-impact-reconciliation.md`.

## 2026-08-12 — Use one standardized authority-note metadata field

Every Legislation, Case, jurisdiction-specific Principles, and approved
Regulatory Materials Search Record uses the same six required metadata strings:
`text`, `country`, `jurisdiction`, `type`, `source`, and `authority_note`. This
renames and broadens the former `warning` field; it does not add a case-only
`treatment` field. The exact value `"None"` remains mandatory when no approved
LLM-facing note applies.

A real authority note uses controlled clauses. Mandatory `[WARNING: ...]`
clauses come first. Selected material `[SUPPORT: ...]` clauses may follow, and
selected neutral `[CONTEXT: EXPLAINED]` clauses come last. Positive case
treatment and material explanatory context enter only under the Cases Source
Rulebook's proposition-level selection rules; ordinary citations do not create
record churn. Support or context never cancels or weakens a warning.
Conclusively overruled propositions remain retired from ordinary current
Pinecone rather than being retained to display a note.

The complete treatment graph and other structured evidence remain internal.
Every active query path passes `metadata.authority_note` unchanged to the
downstream LLM; only `metadata.text` is embedded. A changed authority note
selects a different exact Search Record. A new payload receives a new ID; an
exact former supported payload may be reselected under ADR 0055. An unchanged
text and embedding contract may reuse the cached embedding. Real Hong Kong
authority notes remain English only. See
`docs/adr/0050-use-one-standardized-authority-note-metadata-field.md`.

## 2026-08-12 — Establish the first Hong Kong Cases current-authority baseline

The first Hong Kong Cases baseline freezes one cutoff and establishes the
complete supported current-authority result across every required binding-case
scope. It separately accounts for judgment acquisition, opinions and passages,
Case Propositions, material later treatment, authority notes, non-searchable results,
zero-record decisions, Quarantines, and Coverage Gaps. It imports no legacy
identity and is not a judgment-file dump.

Release Scopes are owned by issuing-court family and original decision year.
Corrections and later treatment do not move an earlier decision to another
scope. The scopes bound rebuilds and failures while all required scopes still
compose into one target and later-treatment reconciliation remains corpus-wide.

There is no arbitrary age cutoff. An old proposition remains eligible while
accepted evidence supports its current use. The initial historical boundary is
the earliest period whose official inventory can prove the exact coverage
promise; an unverified period remains visibly not ready or gapped. Pinecone
growth is controlled through material propositions only, zero-vector no-
proposition decisions, no whole-case or translation duplicates, current-
authority retirement, external judgment evidence storage, and reuse of exact
records and embeddings.

Every later in-scope judgment through the cutoff is screened for material
treatment of earlier propositions. A decision with no proposition of its own
still participates because it may affect an earlier case. Missing judgment
text creates both an acquisition gap and possible treatment gap; a generic
authority note cannot cure it. The initial baseline has no carry-forward predecessor.

Cutoff, acquisition, hashing, identity, scope, authority-note, and release
arithmetic remain deterministic. Proposition extraction follows ADR 0065's
two-pass staged hybrid flow, and Hong Kong later-treatment analysis follows ADR
0053's staged hybrid flow. No proposal may decide authority, authority note,
retirement, Quarantine, release, or production. See
`docs/adr/0049-establish-the-first-hong-kong-cases-current-authority-baseline.md`.

## 2026-08-12 — Account for every official Hong Kong judgment listing entry

Hong Kong Cases acquisition separately tracks an Official Judgment Listing
Entry, one separately delivered Judicial Decision, and every Official Judgment
Artifact that publishes its Official Version. One listing is not automatically
one decision or Search Record; multiple proceeding numbers, formats, aliases,
and optional translations do not create duplicate authority.

Every listing observed at a fixed cutoff receives exactly one outcome:
`ACQUIRED`, `DUPLICATE_OR_ALIAS`, `TRANSLATION_ARTIFACT`, `OUT_OF_SCOPE`,
`BLOCKED_UNAVAILABLE`, or `QUARANTINED`. Every acquired in-scope decision then
receives a separate processing and release-accounting result, including the
valid possibility of no material Case Proposition. A missing file can never be
reported as a valid zero-proposition decision.

Coverage proofs report inventory accounting, originating-evidence coverage,
and search-record output separately. Complete accounting may expose a Coverage
Gap but does not cure it or make a release eligible. Supported no change
requires every due official inventory check and reconciliation to succeed.

One accepted complete official original format may support a decision; there
is no legislation-style mandatory two-format pair. Every relied-on official
variant is preserved and material unexplained differences are quarantined. A
changed artifact at a stable URL is a new Source Snapshot and becomes a new
Official Version only with official correction, revision, reissue, or
replacement evidence.

Daily lightweight recent checks, partitioned metadata reconciliation,
change-triggered artifact acquisition, and bounded historical acquisition keep
monitoring scalable. Before a baseline or no-change claim relies on the LRS,
technical conformance must prove complete enumeration of the promised scope.
HKLII cannot cure an enumeration gap. See
`docs/adr/0048-account-for-every-official-hong-kong-judgment-listing-entry.md`.

## 2026-08-12 — Serve Hong Kong Case Propositions in original language by default

Each Hong Kong Case Proposition uses the language actually authored by the
court in its supporting opinion or passages. One proposition creates one
original-language serving record, including exact mixed-language source text;
the pipeline does not create separate English and Chinese records.

An official Judiciary translation is a linked Judiciary Translation Artifact,
not another judgment, Official Version, opinion, authority, or default part of
`metadata.text`. It is preserved for alignment, review, terminology,
proposition and answer evaluation, and paired cross-language retrieval tests.
Missing translation does not block the original record or create a Coverage
Gap. Translation problems are isolated unless they also undermine original
judgment evidence.

Before embedding-model and downstream-LLM acceptance, the pipeline must test
English and Traditional Chinese queries against original judgments in both
languages. If original-only serving fails materially, the next design choice
is a short labelled translation retrieval aid for affected records. Full
bilingual duplication is the last fallback. Any serving enrichment requires a
later explicit decision and may never remove controlling original text or
create duplicate language records. See
`docs/adr/0047-serve-hong-kong-case-propositions-in-original-language-by-default.md`.

## 2026-08-12 — Limit ordinary Hong Kong Case coverage to binding courts

Ordinary searchable Hong Kong Case coverage includes publicly released written
decisions and reasons from the Court of Final Appeal, Court of Appeal, Court of
First Instance, and Competition Tribunal. A covered court qualifies when its
ratio can bind at least one lower Hong Kong court. Corresponding pre-1997 Hong
Kong superior courts and pre-1997 Privy Council appeals from Hong Kong receive
separately accountable historical coverage.

Standalone decisions from the District and Family Courts, Magistrates' Courts,
Juvenile Court, Lands Tribunal, Labour Tribunal, Small Claims Tribunal, Obscene
Articles Tribunal, Coroner's Court, and comparable lower bodies do not create
ordinary searchable Case Propositions. Included appellate decisions remain
covered according to the court that issued them. Every in-scope official
decision is accounted for even when it creates no Pinecone record.

Technical extractability does not expand legal-authority scope. The Lands
Tribunal remains only a possible future, separately approved
`specialist-persuasive` source with retrieval isolation and an LLM-facing
authority-note warning clause. Family Court and Labour Tribunal inclusion would also
require separate later decisions; Labour Tribunal additionally requires a
materially better originating-source inventory. See
`docs/adr/0046-limit-ordinary-hong-kong-case-coverage-to-binding-courts.md`.

## 2026-08-12 — Register HKLII as a non-controlling automated discovery source

The Hong Kong Cases Source Rulebook registers
`HK-CASE-HKLII-DISCOVERY` for automated candidate-judgment discovery, aliases,
inventory cross-checking, historical and citation leads, and possible later-
treatment relationships. Its outage is nonblocking and cannot support a
no-change conclusion.

HKLII remains non-controlling for technical data-quality reasons. Every
judgment, Case Proposition, treatment, authority-note, or retirement decision still
requires matching evidence from an accepted originating source. HKLII content
alone creates no serving record or adverse-treatment result.

At the user's direction, legal and policy review is deferred to the legal team
and is not a prerequisite to design or later implementation. The intended use
is assumed compliant. This removes a compliance gate without expanding
HKLII's Fact Authority. See
`docs/adr/0045-register-hklii-as-a-non-controlling-automated-discovery-source.md`.

## 2026-08-12 — Normalize Hong Kong current-update results and complete observation-failure coverage

Hong Kong Legislation conformance results keep processing outcome, legal
disposition, coverage effect, Source Contract Review state, record output, and
workflow or reason code in separate fields. `PASS` does not mean searchable
law; a Coverage Gap is not a legal disposition; and
`SUPPORTED_NO_CHANGE` is a workflow result rather than a sixth disposition.

Two cases now exercise the previously uncovered branches of
`HKLEG-CURRENT-OBS-003`: release-blocking Observation failure and an
item-specific affected-source failure that must not stop complete independent
work. The frozen pre-reconstruction Hong Kong universe is 89 HKeL reconciliation fixtures, 18
ordinary-current cases, and 14 first-baseline cases: 121 exact tests. See
`docs/adr/0044-normalize-hong-kong-current-update-results-and-complete-observation-failure-cases.md`.

## 2026-08-12 — Defer final generative-LLM task allocation — amended by ADRs 0053 and 0065

The legal-processing worker's LLM task runner remains the sole internal
generative-model gateway, and any model output remains an evidence-bound
proposal with no source, legal-status, identity, authority-note, release, approval,
or production authority. Deterministic controls and the responsible Legal Desk
retain those authorities.

The final deterministic-versus-generative-LLM allocation was deferred for
`case-proposition-extraction`, `later-treatment-proposal`, and
`gazette-event-extraction`. ADR 0053 later accepts the high-level staged hybrid
allocation for Hong Kong later-treatment screening, and ADR 0065 accepts the
two-pass staged hybrid allocation for Hong Kong Case Proposition extraction.
Their exact runtime contracts remain disabled pending admission. Gazette-event
extraction and every other unallocated candidate task remain deferred. See ADRs
0043, 0053, and 0065.

## 2026-08-12 — Package the Hong Kong Legislation Source Rulebook

The Hong Kong Legislation Source Rulebook is one strict immutable policy
package for `hk-legislation`, not one package per Release Scope and not
executable code. Its date-led version, effective boundary, coverage, per-scope
readiness, stable source-role Fact Authorities, result-determining source-check
policy, HKeL interpretation lock, declarative rules, stable codes, contract
locks, test locks, and impact declaration are separately inspectable and bound
by an exact package fingerprint.

Mutable URLs, current source health, credentials, source evidence, runtime
decisions, implementation code, LLM prompts, and promotion authority remain
outside the package. An endpoint move does not create a new legal policy
version unless Fact Authority or another result-determining rule changes.

The three Release Scopes carry separate `DECISION_READY` or `NOT_READY` states.
The constitutional-and-other-instruments scope remains not ready until the
user's mandatory future Instruments & Others review and row-level legal-effect
work. That gate cannot be hidden as complete and does not automatically make
the separate Ordinances or subsidiary-legislation scopes invalid.

As amended by ADR 0044, the initial pre-reconstruction conformance universe binds all 89 HKeL
reconciliation fixtures, 18 ordinary-current cases, and 14 first-baseline
cases: 121 exact fixtures and cases. Every rule and permitted branch requires
coverage before its scope can be decision-ready. A separate Rulebook
Conformance Attestation binds the exact package to the exact processing build
that passes them.

Only validated frozen packages have decision authority. Registration,
activation, supersession, and revocation are append-only Management Register
events. One Observation cutoff uses exactly one package fingerprint. Every new
package carries an impact declaration; historical decisions are never silently
reinterpreted. See
`docs/adr/0042-package-the-hong-kong-legislation-source-rulebook.md`.

## 2026-08-12 — Use strict hashed HKeL fixture packages

Each of the eighty-nine accepted HKeL reconciliation fixtures becomes one
immutable synthetic package with a strict Draft 2020-12 `fixture.json`, small
separately stored inputs, and separately stored exact expected artifacts. Every
file is declared by role, language where applicable, relative path, media type,
and SHA-256. Large escaped XML, PDF bytes, and bilingual record text do not sit
inside the manifest.

A frozen `catalogue.json` binds all five conceptual groups, the complete stable
ID ranges and counts, every package path and fingerprint, and the exact common
contract versions. Broad feature tags may help discovery but cannot substitute
for an exact fixture assertion.

The manifest explicitly distinguishes available, intentionally absent, and
unreadable evidence. It separately records processing outcome, legal
disposition, coverage effect, Source Contract Review requirement, reason codes,
ordered Rule Trace, and exact-record or no-record expectation. `PASS` does not
mean searchable law; Waiting Room and historical states are dispositions;
Coverage Gap is a coverage fact.

JSON Schema validates structure. Semantic validation additionally proves file
hashes and containment, evidence roles, pinned references, exact outputs or
explicit zero output, bilingual mapping, Legal Location ownership, dependency
closure, source-unit coverage, authority-note, traceability, identity, lineage, and
two clean byte-identical executions. A reproducible defect cannot pass merely
because its JSON is valid.

The executable schemas, synthetic source-shaped bytes, expected artifacts, and
validator are later implementation artifacts. They must instantiate this
contract without changing the accepted fixture outcomes. See
`docs/adr/0041-use-strict-hashed-hkel-fixture-packages.md`.

## 2026-08-12 — Define recursive overlong HKeL record partitioning

The final conceptual HKeL reconciliation group contains twenty-two stable
`HKLEG-RECON-ORP-FIX-*` examples. One complete normal Legal Location remains
one bilingual Search Record whenever its exact final payload fits. Separate
locations are never merged because they are short, and records split only when
the final `metadata.text` token ceiling or complete metadata byte ceiling is
actually exceeded.

An oversized branch recursively descends through complete official aligned
units until it reaches the largest individually safe partition frontier. It
does not stop at the first usable structural level. The canonical grouping
uses the fewest valid parts and, among ties, fills each earlier part with the
greatest possible number of consecutive frontier units. All parts are rendered
again with their actual part numbers, total, dependencies, and authority note before
both ceilings are checked.

Every part carries dependency closure: the minimum bilingual governing context
needed for independent meaning. Required context is labelled as repeated and
counted; it is never discarded to make a part fit. Sentence, punctuation,
whitespace, token, and character fallbacks are forbidden unless the exact
boundary is itself an official legal unit. A smallest indivisible dependent
branch that cannot fit is quarantined with a Coverage Gap.

An internal Primary Source-Unit Coverage Proof establishes exact bilingual
primary coverage and order while distinguishing labelled repeated context.
Incorrect location ownership, dropped, duplicated, or reordered primary text,
and failure to produce the canonical partition are deterministic processing
defects. Unknown source semantics open Source Contract Review.

Every changed partition, dependency closure, final label, authentic text, or
authority note creates new register-issued Search Records with explicit lineage. The
exact embedding model, tokenizer, token and byte ceilings, serialization, and
executable source-schema bytes remain later pinned technical-contract values;
they cannot weaken the accepted legal partition rules. See
`docs/adr/0040-define-recursive-overlong-hkel-record-partitioning.md`.

## 2026-08-12 — Confine generative-LLM use to one governed gateway — amended by ADRs 0043, 0053, and 0065

No application or worker is generally “AI-powered.” The sole internal gateway
for any future generative-LLM provider call is the legal-processing worker's
LLM task runner. The originally named task candidates were:

- `case-proposition-extraction` proposes self-contained Case Propositions and
  exact supporting judgment passages; and
- `later-treatment-proposal` detects candidate citations and proposes how a
  later judgment treats an exact earlier Case Proposition, with exact support.

Both outputs are schema-bound evidence proposals. They cannot decide source
authenticity, legal status, identity continuity, court authority, overruling,
authority notes, retirement, release eligibility, Approval, or Pinecone mutation.
Deterministic validation and the applicable Legal Desk retain those decisions.

ADR 0043 later made this inventory provisional and deferred the exact
deterministic-versus-LLM split, including possible Gazette support. ADR 0053
then accepts the staged hybrid allocation for Hong Kong later treatment. ADR
0065 accepts separate semantic analysis and challenge LLM passes inside the
staged Hong Kong Case Proposition extraction workflow. All provider stages
still require complete admitted runtime contracts. The promotion worker's
embedding adapter remains a separate non-generative model capability, and
Ask.Legal's downstream answer LLM remains outside this pipeline. See ADRs 0039,
0043, 0053, and 0065.

## 2026-08-12 — Define partial-status and bilingual-structure HKeL fixtures

The fourth accepted HKeL fixture group contains twenty-one stable
`HKLEG-RECON-PSB-FIX-*` examples. Every relevant location in a partially
operative item receives exactly one disposition in an internal Status Coverage
Map. Parent status is inherited only when a pinned rule and exact evidence
prove the inheritance, and every child exception remains explicit.

A controlled English warning clause is added only at the smallest mixed-status
boundary where an otherwise current standalone record could materially
overstate its operative scope. Unrelated clear current records keep
`metadata.authority_note` equal to `"None"`. An authority note never makes noncurrent text
searchable.

English and Traditional Chinese structures align through official identifiers
and pinned mappings. One-to-one, one-to-many, many-to-one, and many-to-many
Bilingual Alignment Groups are allowed, but each source unit appears exactly
once and keeps its authentic order. Translation similarity, equal counts, and
LLM inference cannot establish or repair a mapping.

A mismatch affects the smallest complete legal branch that can safely be
separated. Independent siblings may continue; governing or unbounded conflicts
broaden Quarantine to the dependent subtree or item. Unknown source semantics
block and open Source Contract Review. For an ordinary update of previously
served material, ADR 0005 still controls carry-forward, withholding, or no-
rebuild; this fixture group does not silently retire or publish records. See
`docs/adr/0038-define-partial-status-and-bilingual-structure-hkel-fixtures.md`.

## 2026-08-12 — Define note, image, and cross-reference HKeL reconciliation fixtures

The third accepted HKeL fixture group contains eighteen stable
`HKLEG-RECON-NIR-FIX-*` examples. It separates exact legislation in
`metadata.text`, controlled English reliance instructions in
`metadata.authority_note`, non-legislative publisher context, visual evidence, and
internal cross-reference relationships.

A note is statutory text only when the pinned HKeL specification and Source
Rulebook classify it that way. Its exact marker, body, order, attachment, and
bilingual relationship remain in `metadata.text` and cannot be separated by a
serving split. A non-legislative HKeL publisher note remains in evidence and
internal traceability. If it materially limits safe reliance, source
reconciliation may pass but the record remains ineligible until the Legal Desk
approves a controlled English authority-note warning clause or withholds it. Unknown note status
blocks Source Contract Review. HKeL Editorial Records remain separate official
event evidence and never become serving text.

Decorative images are excluded and reported; official captions and legends are
preserved exactly. A meaningful image contributes serving text only when HKeL
supplies a complete official structured textual equivalent explicitly mapped
by the pinned rules. OCR, AI-generated descriptions, and reviewer summaries
cannot replace it. A missing required image blocks. Complete meaningful image
evidence without a faithful official textual equivalent enters Quarantine.

Cross-references keep their exact official words in `metadata.text`. Official
identifiers resolve the target as an internal relationship without copying the
target's wording into the record. Conflicting source or authentic-language
targets enter Quarantine. A reconciled reference whose target cannot be
resolved may pass reconciliation with `UNRESOLVED_REFERENCE`; a separate
materiality decision blocks record eligibility only when safe use needs an
approved authority note or withholding. Known out-of-scope targets may pass with no
coverage claim. Renderer expansion, modernization, rewriting, or silent
correction is a blocked processing defect.

The fixtures cover matching, conflicting, missing, material, unknown, and
split statutory or publisher notes; decorative, captioned, missing,
officially-equivalent, unrepresentable, and conflicting images; and resolved,
conflicting, unresolved, out-of-scope, or improperly rewritten references. See
`docs/adr/0037-define-note-image-and-cross-reference-hkel-reconciliation-fixtures.md`.

## 2026-08-12 — Define Schedule, table, and form HKeL reconciliation fixtures

The second accepted HKeL fixture group contains sixteen stable
`HKLEG-RECON-STF-FIX-*` examples for Schedules, tables, and prescribed forms.
The design preserves legal relationships in deterministic plain text rather
than imitating PDF page layout.

Every Schedule is a Legal Location under its parent instrument. Officially
identified Schedule Parts, paragraphs, items, tables, forms, form Parts, and
independently referenced groups may be child Legal Locations. Ordinary cells,
blank fields, visual rows, page coordinates, and serving parts do not receive
permanent identity merely from layout.

Tables render as labelled rows. Every value carries its complete official
header path, including merged outer headings, joined by the fixed ` > `
separator. Table identity, title, lead-in, units, qualifications, header scope,
row and column order, item numbers, values, blank states, symbols, and dependent
row groups are preserved. Blank, omitted, dash, zero, `N/A`, ditto, checkbox,
and other values are not interchangeable.

Forms preserve identity, instructions, Parts, fields, control types, choice
groups, options, dependencies, declarations, certifications, signature and date
fields, prescribed wording, and source order. Renderer scaffolding describes
the official blank control; it never invents an answer or selected option.

Bilingual structures align through official identifiers and roles. Visual
width, wrapping, page count, and placement may differ when each authentic
language matches its own PDF and official table or form structure aligns.
Unalignable header, row, cell, form-group, control, dependency, or order
relationships enter Quarantine; translation similarity and a generative LLM
cannot repair them.

Overlong structures split only at corresponding complete Schedule units,
table rows or inseparable row groups, and form Parts or complete field groups.
Every part repeats necessary bilingual headings, units, instructions,
dependencies, and parent context. A cell, dependent group, field, choice group,
declaration, signature statement, or governing instruction is never cut. If no
faithful representation or safe smallest unit exists, the candidate is
quarantined. An implementation that ignores an available safe split instead
produces a blocked processing defect rather than converting consistent source
evidence into a conflict.

The fixtures cover exact and page-repeated Schedules, Schedule mismatch,
rectangular and merged-header tables, presentation differences, table
relationship and blank-value conflicts, bilingual visual differences and
structural conflicts, matching and mismatching forms, unknown constructs,
unrepresentable legal layout, and safe splitting. See
`docs/adr/0036-define-schedule-table-and-form-hkel-reconciliation-fixtures.md`.

## 2026-08-12 — Define ordinary-provision HKeL reconciliation fixtures

The first accepted HKeL reconciliation fixture group covers ordinary titles,
identifiers, sections, subsections, paragraphs, headings, and text. Twelve
stable `HKLEG-RECON-ORD-FIX-*` examples bind small synthetic bilingual XML and
applicable PDF evidence to exact `PASS`, `BLOCK`, or `QUARANTINE` results.
Future executable fixtures must follow the pinned real HKeL schema, but their
representation cannot change the accepted purpose or outcome.

`PASS` means only that evidence completeness and deterministic reconciliation
succeeded; legal status, identity, disposition, record, release, approval, and
promotion gates still apply. `BLOCK` means that required evidence is missing,
unknown source semantics require Source Contract Review, or deterministic
candidate construction violates its contract without a source conflict.
`QUARANTINE` means
that existing evidence conflicts, describes different legal material, or
cannot be reconciled faithfully.

The PDF comparison may remove only enumerated presentation elements defined by
the pinned rulebook, such as known headers, footers, page numbers, page breaks,
line wrapping, and pagination. Every ignored occurrence is reported. Words,
numbers, dates, capitalization, quotation marks, hyphens, punctuation,
numbering, order, headings, cross-references, token boundaries, and legally
meaningful whitespace are not generally normalized. A line-end hyphen is not
automatically inserted or removed.

English and Traditional Chinese pair through official item, version,
provision, and structural identifiers rather than translation similarity or a
generative LLM. Each language must match its own applicable PDF and the official structures
must align. A missing artifact or authentic language blocks under
`HKLEG-CURRENT-EVID-003`; a legal-content, heading, numbering, order, version,
location, or bilingual-identity conflict is quarantined under
`HKLEG-CURRENT-EVID-004`.

An element explicitly classified as non-legal metadata by the pinned
specification mapping is excluded and reported. An unknown element, enum,
namespace, status, or meaning is not guessed: affected processing blocks and
Source Contract Review opens under ADR 0028. Passing inputs must render exactly
in the accepted English-first, Traditional-Chinese-second `metadata.text`, with
the authority note and operational traceability kept outside the text.

ADRs 0036 and 0037 settle Schedules, tables, forms, notes, images, and
cross-references. ADR 0038 settles partial status and general bilingual
structural mismatch. ADR 0040 subsequently settles recursive general overlong
partitioning. See
`docs/adr/0035-define-ordinary-provision-hkel-reconciliation-fixtures.md`.

## 2026-08-12 — Establish the first Hong Kong current baseline without replaying history

The first trusted Hong Kong Legislation baseline establishes the complete
supported present state at one fixed observation cutoff. It does not replay
every historical amendment, commencement, renumbering, repeal, or
consolidation. For a clear item, complete current HKeL inventory accounting,
the applicable reconciled bilingual XML-and-PDF evidence, unambiguous current
item and provision signals, no conflicting accepted signal, and a supported
rulebook disposition are sufficient to establish present operative state.

That conclusion is deliberately limited to present state. It cannot invent a
historical effective date or event, claim a complete event chain, infer
continuity from matching text, or construct missing current text from old
versions. HKeL `InEffect`, a list entry, version date, or status code remains
insufficient on its own.

Historical HKeL and archival Gazette evidence is acquired only after a named
material uncertainty opens a bounded investigation. Examples include duplicate
identity, unclear or partial present status, replacement, cessation,
renumbering, split, merge, ownership, continuity, and same-fact source
conflicts. The investigation records its exact question, sources, permitted
facts, and stopping condition. Unavailable or inconclusive history blocks only
the affected decision unless complete Release Scope accounting becomes
impossible. Historical similarity never proves identity or legal status and
cannot replace missing current evidence or authorize reconstruction.

The Management Register allocates new greenfield Legal Item, Official Version,
Legal Location, and Search Record IDs after evidence passes. HKeL and legacy
IDs remain aliases or trace facts; the baseline asserts no unsupported
predecessor lineage. Every item receives one existing supported current,
Waiting Room, evidence-only, historical, or Quarantine disposition. The first
Corpus Release identifies itself as an initial baseline with no accepted
predecessor and seals only after complete scope accounting.

The baseline freezes one cutoff and never mixes later source changes into that
package. A later signal requires a new cutoff or an ordinary update against the
accepted baseline before later currency may be claimed. Fourteen conformance
cases fix the clear, missing, conflicting, partial, historical, legacy-ID,
Instruments & Others, and post-cutoff-change boundaries. The user-flagged
Instruments & Others review still prevents the constitutional-and-other-
instruments scope from being called final; the other non-overlapping scopes
are not automatically blocked. See
`docs/adr/0034-establish-the-first-hong-kong-legislation-current-baseline-without-replaying-history.md`.

## 2026-08-12 — Define Hong Kong legislation current-update rules and cases

The ordinary Hong Kong Legislation update path now uses stable rule IDs shared
by the written rulebook, future executable rules, automated fixtures, Legal
Desk decisions, and review display. Every decision preserves an ordered Rule
Trace containing the applied IDs, exact evidence, established and unresolved
facts, identity effects, disposition, responsible desk, review state, and
reason. A later rule cannot cure failure at an earlier evidence gate.

`HKLEG-CURRENT-OBS-*` rules distinguish complete supported no change, bounded
affected work, and unavailable observations. A no-change result requires all
due observations and inventories to reconcile with no open affected signal;
it reuses the existing Corpus Release and triggers no acquisition, AI,
embedding, or record work. A changed inventory or event is only a signal. A
stale or incomplete blocking observation can never become no change.

`HKLEG-CURRENT-EVID-*` rules require matching bilingual current XML and the
applicable bilingual verified PDFs. The assisted-copy path remains confined to
eligible constitutional or other items without verified copies. Missing
required evidence blocks the affected work; conflicting, differently
versioned, monolingual, or unreconcilable evidence enters Quarantine. AI,
translation, similarity, or artifact recency cannot cure a mismatch.

`HKLEG-CURRENT-DIFF-*` compares the new current bundle with the pipeline's
preserved previous accepted current bundle rather than routinely acquiring
historical data. `HKLEG-CURRENT-CAUSE-*` requires accepted official evidence
for every material text, structure, identity, or status difference. An
unexplained or conflicting change is quarantined. If an operative event is
proved before matching HKeL consolidation exists,
`HKLEG-CURRENT-EVENT-001` records the event and Coverage Gap and creates no
reconstructed current text. ADR 0079 later amends its serving result: every
affected location for which valid latest applicable official HKeL text is held receives
a warned analytical record, while a location without that text emits no record.

`HKLEG-CURRENT-DISP-001` assigns exactly one supported current, Waiting Room,
evidence-only, historical, or Quarantine disposition. Publication, HKeL status,
disappearance, category, and A-number are never automatic search decisions.
`HKLEG-CURRENT-REC-001` reuses a record only when all six metadata fields and
continuing legal support are exact; otherwise it creates immutable successor
identity. `HKLEG-CURRENT-REL-001` requires complete scope accounting before a
release can be sealed.

Eighteen accepted conformance cases cover no change, ordinary changed text,
missing and conflicting evidence, bilingual mismatch, HKeL lag after a proved
event, unexplained change, Waiting Room treatment, exact record reuse,
unsupported disappearance, assisted-copy boundaries, missing predecessor,
irrelevant historical-source outage, partial commencement, and Editorial
Records, plus release-blocking and item-specific Observation failures. ADR 0044
keeps processing, disposition, coverage, review, output, and reason dimensions
separate. A first-ever baseline remains a separate path and cannot be
represented as ordinary no change; ADR 0034 now defines that path. See
ADRs 0033 and 0044.

## 2026-08-12 — Defer query-facing date metadata and recency search

The serving contract remains top-level `id` plus the six required metadata
fields `text`, `country`, `jurisdiction`, `type`, `source`, and
`authority_note`.
Commencement, effective, publication, compilation, observation, approval, and
cutover dates remain structured internal facts in the Management Register and
Evidence Vault; no date field is added to Pinecone metadata now.

Ask.Legal therefore does not add date filtering, recency boosting, or temporal
intent detection in the present design. This is a deferral, not a permanent
rejection. A future explicit decision may introduce a new versioned query
contract after it defines the legally meaningful record-level date for each
material family, handles unknown and mixed dates, updates every live query
path, and proves that recency does not displace older controlling authority.

## 2026-08-12 — Register fact-specific Hong Kong legislation sources

The Hong Kong Legislation Source Register uses fourteen stable source IDs for
official publisher products and accepted evidence roles. A source ID does not
contain a URL, language, format, date, version, or resource filename. Mutable
URLs, generated download routes, languages, formats, and physical holdings are
versioned Source Endpoint records. A URL move therefore does not create a new
source identity.

Every registration separately records the exact fact the source may prove,
its outage impact, and its monitoring tier. The system does not use one global
`controlling` flag: Gazette evidence may prove an event without proving HKeL's
resulting consolidated wording. Outages are `RELEASE_BLOCKING`,
`AFFECTED_WORK_BLOCKING`, or `NONBLOCKING`.

Only `HK-LEG-HKEL-CURRENT-INVENTORY` and `HK-LEG-GLD-EGAZETTE` are ordinary
release-wide blockers. They receive daily lightweight checks and require a
complete successful Observation within 24 hours of the weekly cutoff. The
current inventory is separated from `HK-LEG-HKEL-CURRENT-DATA`, so routine
checks remain small and full XML is acquired only for affected work. Verified
and assisted copies are likewise on demand; ADR 0081 broadens the assisted role
across covered scopes.

`HK-LEG-HKEL-EDITORIAL-RECORDS` and
`HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS` remain weekly supporting sources.
`HK-LEG-BASIC-LAW-PORTAL`, `HK-LEG-NPC-NATIONAL-LAWS-DATABASE`, and
`HK-LEG-NPC-NPCSC-OFFICIAL-MATERIALS` receive monthly and event-triggered
cross-checks, with affected-work blocking only when an item-specific decision
actually requires their fact.

`HK-LEG-HKEL-PAST-INVENTORY`, `HK-LEG-HKEL-PAST-DATA`,
`HK-LEG-OFFICIAL-GAZETTE-ARCHIVE`, and
`HK-LEG-HKEL-GAZETTE-BACKCAPTURE` are on-demand investigation or recovery
sources. They receive no ordinary weekly check and create no ordinary release
freshness gate. Missing historical evidence blocks only the investigation or
decision that requested it; the HKeL back-capture remains nonblocking
discovery material.

Normal change comparison uses the preserved previous accepted current bundle,
the new current bundle, and accepted event evidence explaining the change.
Historical text may expose a possible renumbering, disappearance, split, or
merge, but similarity never proves continuity or legal status. Without
accepted official mapping or other permitted evidence, the question is
quarantined. This amends ADR 0031's former weekly past-data assignment while
preserving ADR 0026's narrow historical evidence role. See
`docs/adr/0032-register-fact-specific-hong-kong-legislation-sources.md`.

## 2026-08-11 — Use tiered source monitoring and change-triggered AI — amended by ADRs 0032, 0039, and 0043

Hong Kong Legislation uses scalable source-specific monitoring tiers. HKeL
current lists and fingerprints and the ordinary and Extraordinary Gazette
inventories receive daily lightweight checks and must have a complete
successful Observation within 24 hours of the weekly release cutoff. Editorial
Records, publication specifications, and Important Notices are checked once
per weekly cycle and must be fresh whenever an affected decision relies on
them. ADR 0032 moves HKeL past inventories and data to on-demand investigation
and recovery use with no ordinary release freshness gate.

The Basic Law portal and other non-controlling constitutional or national-
authority cross-checks receive a monthly baseline check plus an immediate
affected check after a relevant controlling-source signal. Their temporary
absence does not invalidate otherwise complete controlling evidence. Full XML
packages, PDFs, historical files, and other large item evidence are acquired on
demand after a changed fingerprint, new item, missing evidence, active review,
or release dependency requires them.

Ordinary Watcher checks are deterministic and do not invoke a generative LLM,
embeddings, or
repeat large downloads. Unchanged complete fingerprints create no-change
Observations and stop. Real signals are deduplicated, acquired, and subjected
to schema, hash, inventory, version, bilingual, known-rule, and prior-evidence
checks before any later-approved evidence-bound LLM task may run. ADR 0043
defers unallocated tasks, while ADR 0053 accepts the Hong Kong treatment
architecture and ADR 0065 accepts the Hong Kong Case Proposition architecture
without yet enabling either set of provider contracts. The change gate does
not itself authorize a model call. Reuse requires every result-determining input to match.
Embeddings begin only for validated changed Search Records selected for a
candidate release.

An urgent official, controlling-source, or authorized human signal may start a
bounded run between scheduled checks but bypasses no evidence, Legal Desk,
review, approval, or promotion control. A stale or failed blocking source can
never become “no change”; after bounded retries it produces a Coverage Gap and
only the accepted ordinary carry-forward, ADR 0079 known-stale analytical
carry-forward, withholding, or no-rebuild outcome. See
`docs/adr/0031-use-tiered-source-monitoring-and-change-triggered-ai.md`.

## 2026-08-11 — Classify HKeL instruments by legal nature and explicit disposition

The Hong Kong Legislation Source Rulebook contains one immutable, versioned,
and fingerprinted HKeL Instrument Disposition Registry. It accounts for every
HKeL Instruments & Others entry and every Legal Item or Legal Status Event the
entry represents or proves. HKeL's `Instrument` label and A-number remain
source publication and indexing facts; they do not determine legal nature,
identity, Release Scope, search eligibility, evidence path, or authority note.

This is the accepted current baseline, not a permanently closed decision. The
user has explicitly required a later review and expects to revise the HKeL
Instruments & Others treatment. That review is a gate before the Hong Kong
Instruments disposition work may be called final or implementation-ready; a
later accepted decision may amend or supersede ADR 0030.

Actual legal nature determines the one non-overlapping owner. A-series Hong
Kong Ordinances route to `HK-LEG-ORDINANCES`; A-series subsidiary legislation
routes to `HK-LEG-SUBSIDIARY`; and the Basic Law, applicable national laws,
central constitutional decisions and interpretations, and genuine residual
instruments route to `HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS`. An A-number
is an Identity Alias and cannot decide continuity.

Each supported legal object receives one primary disposition of searchable
current, Waiting Room, evidence-only, historical, or Quarantine. Evidence and
relationship roles such as interpretation, promulgation, approval,
implementation, and supersession are recorded separately. `InEffect` is a
required HKeL signal but not an automatic searchability decision. Unknown,
missing, changed, reclassified, unaccounted, or duplicate-owned entries block
the affected item or scope until a new registry version resolves them.

A still-applicable NPCSC interpretation may be separately searchable and linked
to the exact provision interpreted. When provision-only retrieval could cause
materially incomplete reliance, the affected record carries an evidence-backed
English warning clause naming the interpretation; otherwise
`metadata.authority_note`
remains `"None"`. The registry contract is settled, while complete population
and legal-effect review of the current rows remains the next concrete rulebook
task. See
`docs/adr/0030-classify-hkel-instruments-by-legal-nature-and-explicit-disposition.md`.

## 2026-08-11 — Allow HKeL assisted copies for constitutional instruments

Eligible items in `HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS` may use
matching official HKeL English and Traditional Chinese assisted copies when
HKeL does not supply verified copies for that item and version. This is an
accepted Ask.Legal product-evidence threshold for legal analysis, not a claim
that an assisted copy has the statutory status of a verified copy.

Matching bilingual HKeL XML remains the construction input. The assisted
copies are captured, classified accurately, and deterministically reconciled
with the XML. Missing languages, mismatched versions, unexplained wording
differences, or source conflicts block or quarantine the affected item. This
does not create a PDF-only or monolingual serving path.

The exception does not relax ADR 0022 for Ordinances, subsidiary legislation,
or a constitutional item for which HKeL supplies verified copies. The Basic Law
portal is registered for discovery, scope inventory, links, and cross-checks,
not serving-text construction. Detected conflicts with portal or national-
authority material require affected-item review; temporary cross-check-source
absence does not invalidate a complete HKeL assisted-copy bundle.

Assisted-copy status alone does not create an Authority Note. The record uses
`metadata.authority_note: "None"` unless a separate substantive authority note
applies. The
source class and evidence stay in the register, Evidence Vault, and Record
Traceability Lookup. Item-by-item Instruments & Others disposition remains
Source Rulebook work. See
`docs/adr/0029-allow-official-hkel-assisted-copies-for-constitutional-instruments.md`.

## 2026-08-11 — Pin HKeL publication specifications for interpretation

`HK-LEG-HKEL-PUBLICATION-SPECIFICATIONS` is a mandatory source-interpretation
role. Each Hong Kong Legislation Source Rulebook version pins the exact relied-
on HKeL XSD, XML data dictionaries, Important Notices, applicable dataset
catalogue descriptions, fingerprints, and explicit interpretation mapping.
Only specifications actually used by the connector, parser, or verifier belong
in the bundle.

The bundle defines source formats, structural elements, legal-content and
metadata distinctions, version and language fields, status values, resource
hashes, and verified-copy marks. It cannot prove an item-specific legal event
or wording. Status fields remain routing and reconciliation signals; accepted
Gazette, Editorial Record, applicable HKeL verified or assisted text evidence,
or other assigned evidence must prove the relied-on fact. Specifications never enter serving metadata,
embeddings, Pinecone, or the downstream LLM request.

The specification Watcher preserves fingerprinted changes append-only. A
changed, stale, conflicting, unknown, or non-validating specification opens
Source Contract Review and pauses only affected new processing. Review may
produce a new rulebook version, parser and test changes, an impact declaration,
and bounded re-evaluation. A specification change alone never changes an
existing record.

A temporary documentation outage does not block processing while the accepted
bundle is preserved, live artifacts still validate, no relevant change is
observed, and the checking freshness limit remains satisfied. Exact artifact
inventory, intervals, freshness, ID encoding, and interpretation-map schema
remain rulebook work. See
`docs/adr/0028-pin-hkel-publication-specifications-for-source-interpretation.md`.

## 2026-08-11 — Exclude LegCo Bills and proceedings from Hong Kong legislation

The Hong Kong Legislation pipeline does not register, ingest, or continuously
watch the Legislative Council Bills Database, Bills, or LegCo proceedings.
They do not produce or validate current-law Search Records and therefore create
no connector, inventory, workflow, Source Snapshot, authority note, Coverage Gap,
release dependency, embedding, or Pinecone entry.

The Gazette and other accepted event sources prove their assigned legal events;
matching HKeL XML and the applicable verified or assisted official HKeL copy
evidence support current searchable wording. A Bill, reading, debate, vote,
committee document, or explanatory memorandum cannot replace that evidence and
has no current-law pipeline outcome. This source-evidence wording is amended by
ADR 0029 without changing the LegCo exclusion.

The Gazette Watcher may observe the minimum identity of a Legal Supplement No.
3 entry when proving complete Gazette reconciliation, but it does not acquire
or process the Bill text or follow its LegCo history. Human reviewers may
consult LegCo material as optional, unregistered, non-controlling research.

A future legislative-history or proposed-law product requires a separate
explicit material-scope and serving decision. See
`docs/adr/0027-exclude-legco-bills-and-proceedings-from-hong-kong-legislation.md`.

## 2026-08-11 — Separate HKeL past data from Editorial Records — amended by ADR 0032

HKeL past data is a historical inventory and reconciliation source. It supports
version comparison, identity and location continuity, investigation, audit,
recovery, and possible future reconstruction evaluation, while all historical
text stays outside current-law Pinecone. Past XML does not prove exact wording
without matching past verified PDFs and cannot establish current law or the
cause of a legal change.

HKeL Editorial Records are official editorial-amendment evidence. The pipeline
preserves each record's number, Parts, effective dates, authentic-language text,
affected legislation and locations, operations, metadata, and fingerprints.
The Editorial Record proves its stated editorial amendments but is not the
resulting consolidated Official Version and does not supply `metadata.text`.
Matching current HKeL XML and the applicable verified or constitutional-
assisted-copy evidence remain mandatory under ADR 0029's amendment.

An unexplained current-text change, a disagreement between past XML and its
verified PDF, or a conflict between an Editorial Record and resulting verified
text is quarantined. An Editorial Record without matching updated verified text
creates a Coverage Gap rather than reconstructed text. ADR 0079 later requires
warned analytical records wherever valid latest applicable official HKeL wording is
held. Past-data failure blocks only decisions that require the
missing history unless the current record is otherwise unsupported.

Past inventory and data are acquired only when a specific baseline,
investigation, recovery, audit, or evaluation task requires them; there is no
ordinary weekly past-data Watcher or release freshness gate. The Editorial-
Record Watcher continues to reconcile the complete numbered inventory, Parts,
and effective dates every weekly cycle because a new Editorial Record may
directly explain a current-text change. See
`docs/adr/0026-use-hkel-past-data-for-history-and-editorial-records-for-official-editorial-events.md`.

## 2026-08-11 — Use fact-specific Gazette event evidence

The Hong Kong Gazette proves specific legal events; matching HKeL XML and the
applicable verified or assisted official HKeL copy evidence support the
resulting consolidated wording. Publication and effective dates remain
separate, partial commencement applies only to the exact named Legal Locations,
and a Gazette event never creates a reconstructed consolidation. This source-
evidence wording is amended by ADR 0029 without changing the Gazette role.

The source rulebook distinguishes the exact GLD e-Gazette artifact for modern
event evidence, printed Gazette or Government Records Service material for
historical and escalation evidence, and HKeL Gazette back-captures for discovery
only. Legal Supplement No. 1 proves Ordinance publication and its written
commencement clause; No. 2 proves subsidiary legislation and exact notices. A
Legal Supplement No. 3 entry may be minimally identified for complete Gazette
reconciliation but its Bill is excluded from processing under ADR 0027. Main
Gazette, Extraordinary, and other supplements prove only the facts assigned to
their actual instrument class and enabling authority.

Commencement, amendment, repeal, revocation, expiry, revival, correction, and
changed event notices require their exact operative evidence and dates. Missing
or conflicting evidence enters Quarantine or the unavailable-scope process. A
Gazette-proved change without matching applicable HKeL text evidence creates a
Coverage Gap and, under ADR 0079, warned analytical records for affected
locations wherever valid latest applicable official HKeL wording is held rather than a silent or
reconstructed search update. An unexplained HKeL status appearance is not
accepted as event proof.

The Watcher covers ordinary and Extraordinary Gazette publication and
reconciles complete issue-and-notice inventories rather than relying on keyword
alerts. Exact polling intervals and final source-ID encoding remain operational
details. See
`docs/adr/0025-use-fact-specific-gazette-event-evidence-for-hong-kong-legislation.md`.

## 2026-08-11 — Keep HKLII non-controlling — registration deferral superseded by ADR 0045

HKLII is useful principally for finding and cross-checking Hong Kong cases, but
it is not a controlling source for legal text, version, status, treatment, or
authority notes. ADR 0045 later registers it as the automated non-controlling
discovery source `HK-CASE-HKLII-DISCOVERY` while preserving this evidence
boundary.

An HKLII case can identify a candidate judgment, historical authority, alias,
inventory gap, or later-treatment lead. Before processing proceeds, the
pipeline must obtain the matching Judiciary, court-registry, BAILII, or other
rulebook-approved originating artifact. An unmatched HKLII item remains a
discovery lead or enters Quarantine; it cannot create a Pinecone record.

HKLII is not a Hong Kong Legislation construction or verification source. HKeL
XML and the applicable verified or assisted official HKeL copy evidence remain
mandatory, and an HKLII difference may only trigger investigation. HKLII AI
summaries, tags, case-information boxes, and similar-case results are
suggestions for triage or evaluation, not evidence.
Its other collections require their own future material-scope decisions.

Automation remains non-critical and follows the Hong Kong Cases Source
Rulebook. Legal-policy review is deferred under the user's compliance
assumption; technical connector reliability and originating-source proof remain
mandatory. See ADRs 0024 and 0045.

## 2026-08-11 — Defer reconstructed Hong Kong legislation records

The current pipeline will not construct consolidated Hong Kong legislative
text by applying Gazette amendments or Legal Status Events to an older HKeL
version. This excludes both internal shadow reconstructions and searchable
reconstructed records. New or changed consolidated text waits for matching
English and Traditional Chinese HKeL XML and verified PDFs under ADR 0022.

The pipeline may still preserve Gazette evidence, record the event and its
effective date, and map the exact affected Legal Locations. Those facts make
the system current in its awareness of change without claiming to know the
resulting consolidated wording. If a commenced event proves that searchable
text changed before HKeL catches up, the affected stale records cannot be
ordinary carry-forwards. ADR 0079 later requires warned known-stale analytical
records wherever valid latest applicable official HKeL wording is held while the
Coverage Gap stays visible.

The reconstruction option remains open. Searchable reconstructed Pinecone
records may be introduced only through a later explicit accepted decision that
settles derived-source labelling, isolation from applicable HKeL text, the six-
field downstream contract, authority-note and review rules, deterministic bilingual
operations, historical back-testing, and release and approval controls. The
present design does not authorize that future behavior. See
`docs/adr/0023-defer-reconstructed-hong-kong-legislation-records.md`.

## 2026-08-11 — Require HKeL XML and matching verified PDFs — later amended by ADR 0081

Under ADR 0022's verified-copy path, every new or changed current-law Search
Record requires matching English and Traditional Chinese XML plus the
corresponding English and Traditional Chinese verified PDFs. XML is the
deterministic operational input for inventory, bilingual structure, change
detection, canonical `metadata.text`, and legal-boundary splitting. The
verified PDFs are the legal-text and version evidence. Neither representation
is sufficient by itself.

The system builds the candidate from XML, then deterministically reconciles
each language with its verified PDF and confirms that both languages describe
the same instrument, Official Version, Legal Location, and operative state.
Only enumerated PDF presentation differences such as page headers, footers,
line wrapping, and pagination may be ignored. Fuzzy similarity, translation
inference, and AI judgment cannot establish equality. Missing, older,
unverified, differently versioned, or structurally uncheckable material blocks
or quarantines the candidate; there is no monolingual fallback.

The Evidence Vault keeps the XML, PDFs, source metadata, hashes, mappings, and
comparison report. The Record Traceability Lookup points to that bundle. Only
the reconciled XML-built canonical bilingual text may enter `metadata.text`,
embeddings, Pinecone, and the downstream LLM request; PDF and comparison
material stays outside the serving record.

ADR 0081 supersedes the verified-only gate by accepting matching official HKeL
assisted copies across the covered scopes, including Ordinances, and for ADR
0080 reconstruction bases. Later decisions settle the Gazette event-evidence
role in ADR 0025 and the separate past-data and Editorial-Record roles in ADR
0026. ADR 0027 excludes the Legislative Council Bills Database, Bills, and
proceedings. The item-by-item Instruments & Others disposition inventory
remains open. See
`docs/adr/0022-require-hkel-xml-and-matching-verified-pdfs-for-hong-kong-legislation.md`.

## 2026-08-11 — Fix Hong Kong's bilingual text layout and legal-boundary splitting

Every Hong Kong legislation Search Record uses one canonical `metadata.text`:
an English authentic-text block first and the corresponding Traditional
Chinese authentic-text block second. English-first is only a stable formatting
choice; it does not give English greater authority. Each block contains the
official instrument title and identifier, exact locator, optional official
heading, and official legal text.

Operational traceability, source URLs, internal IDs, authority notes, reviewer notes,
AI explanations, unofficial summaries, and Simplified Chinese stay out of
`metadata.text`. UTF-8, Unicode NFC, LF line endings, fixed labels, controlled
whitespace, and a versioned deterministic renderer make identical inputs
produce identical text. Observation or source-version dates used only for
traceability do not cause record churn.

The complete bilingual record is measured with the exact tokenizer pinned by
the embedding contract. If it is too long, it splits only at corresponding
official legal boundaries, keeps both languages together, repeats complete
instrument and provision context, and labels internal pieces as “Serving
part”. Only legally necessary parent lead-in text is repeated, in both
languages and with an explicit parent-context label; sliding-window overlap and
arbitrary token or character cuts are forbidden. Unalignable bilingual
structures and indivisible official units that remain too long are
quarantined.

The eventual embedding model must prove multilingual English, Traditional
Chinese, cross-language, long-record, and split-record retrieval quality. The
exact model, tokenizer limit, and complex-structure conformance fixtures remain
to be selected. See
`docs/adr/0021-use-canonical-bilingual-text-and-structure-aligned-splitting-for-hong-kong-legislation.md`.

## 2026-08-11 — Use English-only internal authority notes for Hong Kong records

Every real `metadata.authority_note` on a Hong Kong Legislation, Hong Kong
Cases, or Hong Kong Principles Search Record is written in English only. The
exact no-note sentinel remains `"None"`. Ask.Legal passes a real authority note unchanged to
the downstream LLM and does not append or generate a Traditional Chinese
translation.

The language difference is intentional. Bilingual Hong Kong legislation
`metadata.text` contains equally authentic English and Traditional Chinese
legal text and also supports accurate retrieval and answer grounding for
Chinese queries. The authority note is not legal source text or a user-facing
translation; it is an internal instruction controlling how the model may rely
on the record. The model must apply it regardless of query language and may
express the resulting qualification in the answer language.

Authority notes remain excluded from embeddings. Chinese-query end-to-end tests
must prove that the bilingual text and exact English authority note both reach
the model and that any warning clause affects the answer. If a future interface
displays the raw note to users, its language rule must be explicitly
reconsidered. See
`docs/adr/0020-use-english-only-internal-warnings-for-hong-kong-records.md`.

## 2026-08-11 — Define Hong Kong legislation coverage and bilingual records

Hong Kong Legislation has three complete, non-overlapping Release Scopes:
`HK-LEG-ORDINANCES`, `HK-LEG-SUBSIDIARY`, and
`HK-LEG-CONSTITUTIONAL-AND-OTHER-INSTRUMENTS`. Together they account for
Ordinances; subsidiary legislation such as regulations, rules of court, orders,
notices, bylaws, resolutions, proclamations, and commencement instruments with
legislative effect; the Basic Law; Annex III national laws applied to Hong
Kong; and the accepted HKeL Instruments & Others inventory.

Coverage includes searchable current material, enacted but uncommenced material
in the Waiting Room, status and amendment evidence, preserved repealed or past
versions, and Quarantine. Only supported operative current provisions enter
ordinary Pinecone search. Schedules, annexes, forms, and other structural parts
remain Legal Locations under their parent Legal Item. The Gazette is a source,
not a Release Scope. ADR 0027 later excludes LegCo Bills, drafts, the Bills
Database, and proceedings from automated use while allowing optional non-
controlling human research. Judgments and Principles remain separate; treaties
are outside this rulebook unless implemented through covered Hong Kong
legislation.

Every searchable Hong Kong legislation location produces one bilingual Search
Record. Its single `metadata.text` contains the corresponding English and
Traditional Chinese content. The system creates no English-only or Traditional-
Chinese-only serving records and adds no language metadata field. Both
languages are embedded together and passed together to the downstream LLM.
Missing, stale, differently versioned, or structurally unmatched required
language content blocks the record rather than causing monolingual fallback.
Changing either language changes the Search Record ID.

The exact Hong Kong Registered Sources, Instruments & Others inventory, event
evidence, and checking rules remain open. See
`docs/adr/0019-define-hong-kong-legislation-coverage-and-bilingual-records.md`.

## 2026-08-11 — Use a common contract and separate source rulebooks

Every jurisdiction-and-material pair has its own immutable, versioned, and
fingerprinted Source Rulebook. Australian Legislation, Australian Cases,
Australian Principles, Singapore Legislation, Singapore Cases, Singapore
Principles, and equivalent pairs use one common Source Rulebook Contract but do
not share one source-completeness or legal-status decision manual. There is no
cross-jurisdiction Principles rulebook.

The Source Register records approved sources, roles, ownership, checking
expectations, and technical configuration. Source connectors capture facts.
The source rulebook references stable Registered Source IDs and tells the Legal
Desk what preserved evidence may prove and which outcomes are permitted. It
does not contain credentials, retrieve sources, approve a manifest, or
authorize production.

Every concrete rulebook states its identity and ownership, exact coverage,
source roles, checking and full-reconciliation rules, required Source
Snapshots, recognized events, source priority and conflicts, identity-
continuity evidence, permitted serving outcomes, failure behavior, and
examples or tests. Every rule has a stable rule ID, and every decision records
the rulebook version and fingerprint, exact rule, evidence, facts, outcome, and
responsible desk.

Missing evidence, failed reconciliation, unmatched events, and unresolved
conflicts cannot become silent no-change decisions. They enter Quarantine or
the accepted unavailable-scope process. Used rulebook versions are immutable;
a new version has an explicit effective observation cutoff and declares
whether existing material requires re-evaluation. See
`docs/adr/0018-use-versioned-jurisdiction-and-material-source-rulebooks.md`.

## 2026-08-11 — Use jurisdiction-specific Principles material families

Publisher-derived secondary legal material is called **Principles**, always
qualified by jurisdiction for scopes, profiles, desks, rulebooks, releases,
reports, and configuration. The design therefore uses Australian Principles,
Singapore Principles, United Kingdom Principles, Hong Kong Principles, and
equivalent jurisdiction-qualified names rather than one general Reference
Works family.

Each jurisdiction's Principles has its own Registered Sources, coverage,
source rulebook, Legal Desk, Release Scopes, Corpus Releases, and evidence. A
Principle remains a source-faithful `type: "principle"` Search Record. A
publisher-maintained Principles Title is a Legal Item; editions or complete
rolling update states are Official Versions, and publisher paragraphs are
Legal Locations.

The shared publisher-continuity rules in ADR 0015 still apply, but each
jurisdiction supplies its own publisher identifiers, update evidence, currency
signals, and checking rules. Licence expiry creates a Frozen Principles Scope
only for the affected jurisdiction and source. See
`docs/adr/0017-use-jurisdiction-specific-principles-terminology.md`.

## 2026-08-11 — Keep record traceability outside the Ask.Legal query path

The former Adjacent Query Lookup is renamed the Record Traceability Lookup. It
is a compact internal map from every Search Record ID to its Legal Item,
Official Version, supporting Legal Locations, source-evidence references,
Release Scope, Corpus Release, authority-note evidence, and useful internal grouping
or citation identifiers. It stores pointers and fingerprints, not the original
source files; the Management Register and Evidence Vault remain authoritative.

Corpus construction and promotion require exactly one matching lookup entry
for every selected Search Record. Missing, duplicate, orphaned, fingerprint-
mismatched, or authority-note-mismatched entries block promotion. Once the Serving
State is active, however, Ask.Legal does not read or join the lookup. Temporary
lookup unavailability does not stop ordinary searches.

The downstream LLM receives only the six Pinecone metadata fields. Its
record-level authority instruction comes from `metadata.authority_note`.
Traceability-only corrections create
a new immutable lookup revision without changing the Search Record or rebuilding
Pinecone; a later Serving State may bind that revision while reusing the same
verified indexes. See
`docs/adr/0016-keep-the-record-traceability-lookup-outside-the-query-path.md`.

## 2026-08-11 — Use publisher-backed Principles continuity and freeze on licence expiry

Within each jurisdiction's Principles, one independently publisher-maintained
Principles Title is a Legal Item. A publisher-authorized edition or complete
rolling update state is an Official Version, and each publisher paragraph is a
Legal Location. Search Records remain source-faithful `type: "principle"`
records; the system does not rewrite publisher paragraphs into its own legal
rules.

Source moves and title renames preserve proved identities. New editions,
rolling update states, corrections, paragraph moves, renumbering, splits,
merges, transfers, withdrawals, and currency changes follow explicit publisher-
evidence-backed continuity rules. Changed six-field payloads receive new Search
Record IDs; exact unchanged records may be reused only with proved continuing
support. A materially outdated paragraph is withheld as a whole unless it
remains supportable with a controlled authority note. Conflicting or unproved
continuity is quarantined.

Licence expiry is the exception: it freezes the exact last approved source
scope but does not stop its use. The same records, metadata, existing authority-note
values, and reusable embeddings remain selected and may be copied into later
replacement Pinecone indexes. Watchers, acquisition, corrections, new material,
authority-note revisions, and all other updates for that source stop. Expiry
alone does not change the note, withhold, retire, or delete anything. If access resumes, the
complete publisher state is reconciled before updates restart.

The technical design assumes this use is legally compliant. Source-specific
rights, contract controls, and other compliance details are deferred to the
legal team and are not treated as unresolved technical identity rules. ADR
0017 requires this policy to be applied through separate jurisdiction-specific
Principles families and rulebooks. See
`docs/adr/0015-use-publisher-evidence-backed-reference-work-continuity.md`.

## 2026-08-11 — Use proposition-scoped case-law continuity and retirement

One separately delivered judicial decision is one Legal Item. A Case Dossier
groups related trial, appeal, supplementary, costs, remedy, and procedural
decisions but is not itself legal authority. Official corrections or revised
reasons are new Official Versions of the same decision when the issuing court
expressly presents them that way. Opinions and exact passages are hierarchical
Legal Locations; every Search Record remains one self-contained, opinion-
attributed Case Proposition.

Source moves and duplicates do not create new legal identity. Separately
delivered decisions normally receive new Legal Items. Corrections,
rediscovered propositions, unsupported output, and proposition splits or
merges create the exact new records, lineage, and retirements required without
changing the judgment's identity or pretending that processing error is legal
treatment.

Later treatment belongs to a later judgment and the exact affected
proposition; it does not revise the earlier Official Version. Approved and
followed propositions, and materially useful applications, may receive a
selected controlled support clause under ADR 0050. A material explanation may
receive a neutral context clause; bare citation remains internal. A
distinction does not automatically require a warning clause, but a material
limitation may. Doubted or criticised
propositions remain searchable only with an approved warning clause in
`metadata.authority_note`.
Clear disapproval or refusal to follow follows the automated-and-reported rule
accepted on 2026-08-13; uncertainty or a missing consequence rule requires
review. An exact
proposition expressly and conclusively overruled by an authoritative court is
retired from ordinary current-law Pinecone serving and permanently preserved
with its evidence, history, and `overruled_by` lineage. Partial overruling or
reversal affects only the propositions whose authority was actually removed;
uncertain scope is quarantined. See
`docs/adr/0014-use-proposition-scoped-case-law-continuity-and-retirement.md`.

## 2026-08-11 — Deliver one required authority-note string in every record's metadata

The downstream LLM can receive legal-record information only from Pinecone
metadata. Every target Search Record therefore has six required metadata
fields: `text`, `country`, `jurisdiction`, `type`, `source`, and
`authority_note`. `authority_note` is always a string. The exact case-sensitive
value `"None"` means no approved record-level authority note applies at the Serving State's
observation cutoff; omission, null, empty strings, whitespace, and alternative
sentinels are invalid.

A real authority note is a concise controlled, evidence-backed, Legal
Desk-approved authority instruction passed unchanged with `metadata.text` to
the downstream LLM. Mandatory warning clauses come before selected material
support and neutral context clauses under ADR 0050. The embedding input remains
`metadata.text` only.
Adding, changing, or removing a real authority note selects a different exact
Search Record, although the exact cached embedding may be reused when the text
and embedding contract are unchanged. ADR 0055 later permits reselection of a
preserved exact record instead of minting a duplicate. The register and
evidence vault retain the full structured treatment evidence; the Record
Traceability Lookup is not the delivery channel. This decision supersedes the
five-field-only lookup exceptions in ADRs 0008 and 0011 and is amended by ADRs
0050 and 0055. See
`docs/adr/0013-deliver-warnings-in-required-serving-metadata.md`.

## 2026-08-11 — Use evidence-backed legislation continuity rules

Legislation identity follows proved legal continuity rather than matching
URLs, titles, citations, provision numbers, wording, or document positions. A
source move with a proved unchanged official artifact preserves its identities.
A newly published official consolidation or correction creates a new Official
Version. An amendment may preserve a continuing Legal Location, but changed
serving payloads receive new Search Record IDs.

True renumbering preserves a Legal Location only under an official mapping or
a reasoned Legal Desk decision permitted by its written rulebook. Repeal leaves
historical identity and evidence intact while removing current serving
selection. Repeal-and-substitution, splits, merges, and re-enactment create the
new Legal Item or Legal Location identities required by their legal meaning,
even when a number, title, or wording is reused. Reinstatement reuses an old
Search Record only when the serving payload is exactly identical and
continuing legal support is proved.

A Legal Status Event is distinct from an Official Version: commencement,
repeal, expiry, or revival does not cause the pipeline to invent official text.
An amending Act is its own Legal Item, and a commenced amendment without an
official consolidation produces a Coverage Gap rather than reconstructed law.
ADR 0079 later requires warned analytical records for affected locations
wherever valid latest applicable official HKeL wording is held during that gap.
Conflicts and ambiguous continuity are quarantined. Jurisdiction-specific
rulebooks must still identify which official evidence satisfies these general
rules. See
`docs/adr/0012-use-evidence-backed-legislation-continuity-rules.md`.

## 2026-08-10 — Use register-issued layered identity and immutable records

The Management Register allocates permanent opaque Legal Item IDs, immutable
Official Version IDs, Legal Location IDs, and immutable Search Record IDs.
URLs, filenames, provider paths, titles, citations, visible locators, wording,
and output positions are aliases, display data, or evidence rather than
identity inputs. An ID is allocated once and never reassigned.

A changed approved Pinecone payload selects a different exact Search Record. A
previously unseen payload receives a new ID and explicit forward predecessor
relationship; ADR 0055 later permits a preserved exact supported record to be
reselected without a backward lineage edge. The old selected record remains
preserved. An unchanged record may be reused for a later Official Version only
when exact payload equality and continuing legal support are proved. Traceability-only
citation or provenance changes create a new Record Traceability Lookup revision
without changing the Search Record ID or rebuilding Pinecone. ADRs 0013 and
0050 supersede the earlier exception: changing required metadata
`authority_note` changes the selected Search Record.

Corrections, replacements, renumbering, splits, and merges use typed
evidence-backed lineage and never erase or reassign identity. Selection,
reselection, withholding, retirement, and reinstatement also use separate
append-only lifecycle facts under ADR 0055. Ambiguous continuity is quarantined
for the responsible Legal Desk. The exact ID encoding remains to be specified;
ADR 0012 supplies
the legislation rules, ADR 0014 the case-law rules, and ADRs 0015 and 0017 the
Principles rules. See
`docs/adr/0011-use-register-issued-layered-identity.md`.

## 2026-08-10 — Do not use Distillation's source-derived identity approach

The greenfield identity model will not derive authoritative Legal Item,
Official Version, Legal Location, or Search Record identity from Distillation's
raw paths, AustLII paths, Title or paragraph numbers, source locators, node
identifiers, or positional split-child indexes. Existing Distillation `rec_`
values may be preserved as non-authoritative legacy references when needed,
but they are not automatically adopted or carried forward.

This does not reverse the serving-envelope decision or its later authority-note
amendment. Greenfield Search Records provide a conforming top-level `id`, but
its meaning and allocation come from the independently designed greenfield
identity contract. See
`docs/adr/0010-do-not-use-distillation-source-derived-identity.md`.

## 2026-08-10 — Separate immutable Serving State from lifecycle events

A Serving State Definition is sealed and fingerprinted before Approval. It
binds the environment, predecessor and rollback state, complete Routing
Configuration, every Pinecone Index Generation and Desired-State Inventory,
serving contracts and Record Traceability Lookup contents, query and embedding
settings, coverage manifest, required verification definitions, recovery
references, and all result-affecting non-secret settings.

Approval, execution receipts, activation time, mutable status, monitoring
observations, secrets, and incidental application builds are not part of that
fingerprint. The Promotion Manifest binds the candidate definition; the
definition does not refer back to the manifest. Successful build and
verification evidence makes the exact definition eligible to serve.

Verification, activation, failure, rollback activation, recovery protection,
and retirement are separate immutable append-only lifecycle events. Only an
activation event changes the active state, using an atomic comparison against
the approved base state. Exactly one Serving State is active per environment.
Rollback appends a new activation event for the retained predecessor instead of
mutating or cloning it.

The complete Azure routing generation includes the Serving State ID alongside
the jurisdiction-to-index mapping. Each answer-producing request pins one
Serving State and activation event, and its audit record records both. See
`docs/adr/0009-separate-serving-state-definition-from-lifecycle.md`.

## 2026-08-10 — Adopt the standardized base serving fields and internal traceability lookup

_Amended by the required-authority-note and internal-traceability decisions
above._

The greenfield query contract adopted the existing standardized base record
fields: top-level `id` plus `metadata.text`, `country`, `jurisdiction`, `type`,
and `source`. Each registered profile keeps its own schema identity and locked
fingerprint. ADR 0013 added a required metadata channel and ADR 0050
standardized it as `authority_note`, so the target contract is not
byte-compatible with the locked legacy schemas. The greenfield
contract package owns the new contracts; the legacy workspace is reference
evidence and does not become a runtime dependency.

Stable parent Legal Item identity, internal grouping and citation data,
provenance, release references, and structured authority-note evidence live in the
separate immutable Record Traceability Lookup keyed by Search Record ID. It is
used for validation, investigation, and audit rather than Ask.Legal queries.
The approved LLM-facing authority note lives in required serving metadata.

Every served record must have exactly one matching entry. Missing, duplicate,
or mismatched entries block promotion. A required authority note that is absent,
differs from its approved traceability evidence, or is not transmitted to the
downstream LLM fails promotion. The serving and traceability contracts and
content are bound into the Desired-State Inventory, Promotion Manifest, and
Serving State. Ask.Legal has no live lookup dependency.

Every active Ask.Legal query path must pass compatibility tests. The existing
Node Australian path cannot consume the new serving state while it still
requires `_node_content`; upgrading it or removing it from the new-index query
path remains a later decision. See
`docs/adr/0008-adopt-the-five-field-serving-envelope.md`.

## 2026-08-10 — Bind Serving State to the query contract, not an exact app build

The Serving State records the exact query-contract identity and fingerprint
that its search records obey. Promotion must prove that every active Ask.Legal
query path supports that contract. It does not bind the Serving State to one
exact application build merely because that build happened to be deployed at
cutover; application build identity belongs in operational deployment and
request logs.

An Ask.Legal change requires a new Serving State only when it changes how legal
records are retrieved, filtered, grouped, cited, warned about, or otherwise
interpreted under the query contract. An application release that leaves those
behaviours and the supported contract unchanged does not require a corpus
rebuild or new Serving State.

## 2026-08-10 — Approval is one immutable decision for one execution lineage

Approval is a separate immutable authenticated human decision bound to exactly
one Promotion Manifest identifier and fingerprint and, once execution begins,
one execution lineage. It records the reviewer identity and authority evidence,
decision, time, reason or comment, expected base Serving State, and conditions
that must remain true. Decision 2 later removes an independent Approval TTL and
uses one `PipelineAdministrator` role assignable to multiple named people.
Rejection requires a rebuilt manifest; there is no partial approval.

Revocation, automatic invalidation, and consumption are append-only
lifecycle events that preserve the original decision. Service accounts cannot
approve, the reviewer cannot alter the manifest while deciding, and Approval
cannot be reused for an unrelated run. A retry may continue only within the
same recorded execution lineage, at an allowed checkpoint, with identical
manifest inputs. Immediately before execution, the promotion worker must prove
that the manifest remains valid, current administrator authority, base and
target state, configuration, recovery readiness, and revocation state still
pass. Any failed check makes the Approval unusable. See
`docs/adr/0007-bind-approval-to-one-manifest-and-execution-lineage.md`.

## 2026-08-10 — The Promotion Manifest is the sole approval and execution envelope

The Promotion Manifest is one sealed immutable machine-readable package. It is
the only object a human approves and the only production plan the promotion
worker may execute. It binds by exact identifier and fingerprint the base
Serving State, candidate Serving State Definition and Desired-State
Inventories, old and proposed Pinecone Indexes, complete routing change, code
and contract versions, search and embedding settings, additions, replacements,
withholdings, retirements, recovery evidence, validations, cost limits, ordered
actions, verification checkpoints, rollback action, validity window, and
invalidation conditions.

The manifest references immutable evidence and payload artifacts instead of
duplicating the full corpus. It contains no credentials, private keys, or
secret values. Approval and execution results are separate append-only records
that reference its fingerprint; they never mutate it. The promotion worker may
not select a different target, setting, record, input, retry basis, or step. Any
material change invalidates the package and requires a rebuilt manifest and new
Approval. See
`docs/adr/0006-make-the-promotion-manifest-the-sole-execution-envelope.md`.

## 2026-08-10 — Unavailable scopes require an explicit serving decision

When a required Release Scope cannot produce a fully current release because of
source failure or Quarantine, the responsible Legal Desk must support one of
four explicit outcomes:

1. carry forward the last approved Corpus Release only when the desk supports
   continued serving with a visible Coverage Gap and last-verified date;
2. when an official legislation change is proved but updated official
   consolidated text is unavailable, select warned known-stale analytical
   records under ADRs 0079 and 0081 wherever valid latest applicable official HKeL text is held;
3. create a complete evidence-backed Withholding Release when existing records
   may be materially misleading, account for every withheld item, and require
   Approval for the exact serving removals; or
4. if neither outcome is supportable, produce no new Desired-State Inventory or
   Pinecone target for that jurisdiction, keep its previous target and publish
   the Coverage Gap, while other jurisdictions may proceed.

A source failure is never silently treated as no change, a proved-empty scope,
or automatic retirement. Carried-forward material is not described as verified
current. Withholding removes a Search Record from serving but does not declare
that its Legal Item ceased to exist. See
`docs/adr/0005-handle-unavailable-release-scopes-explicitly.md`.

## 2026-08-10 — Desired-State Inventories contain scoped and flattened views

Each Desired-State Inventory is one sealed immutable complete composition for
one logical Pinecone target. It identifies the versioned registry of required
Release Scopes, selects exactly one Corpus Release for every required scope,
and persists the matching flattened list of every expected Search Record ID,
content fingerprint, owning scope, and owning release. The two views must agree
exactly.

An unchanged scope references its existing Corpus Release. A proved-empty
release is selected normally and contributes zero records. Missing or duplicate
scope selections, overlapping ownership, duplicate record IDs, mismatched
fingerprints, records absent from the flattened list, flattened records absent
from the selected releases invalidate the inventory. An unexplained production
record blocks promotion against that target until its ownership and disposition
are resolved. The inventory proves desired state but does not authorize
production. See
`docs/adr/0004-make-desired-state-inventories-complete-and-flattened.md`.

## 2026-08-10 — Corpus Releases are complete scoped snapshots

A Corpus Release is the complete immutable snapshot of one explicitly declared
Release Scope at one observation cutoff, not a delta or arbitrary bundle. A
Release Scope is a stable, versioned, non-overlapping ownership boundary with
one responsible desk. A release contains zero or more validated Search Records,
its completeness proof, non-searchable item dispositions, and its predecessor
identity. A zero-record release is valid only when evidence proves that the
complete scope genuinely has no supported current Search Records or an
evidence-backed Withholding Release explicitly accounts for every
non-searchable item. Failed, incomplete, or quarantined work without those
dispositions must not be represented as an empty release.

When a scope is unchanged, later Desired-State Inventories reference the
existing release instead of copying or rebuilding it. A later release for the
same scope declares its predecessor but replaces it in serving only when a
complete Desired-State Inventory selects it and the exact Promotion Manifest is
approved and promoted. See
`docs/adr/0003-make-corpus-releases-complete-scoped-snapshots.md`.

## 2026-08-10 — Promote through replacement Pinecone Indexes and one routing generation

Each jurisdiction's serving target is a complete immutable Pinecone Index.
Every affected jurisdiction receives a fresh replacement index; unaffected
jurisdictions retain their exact verified index references. The promotion
worker builds and verifies every replacement before Ask.Legal activates the
complete new routing configuration through Azure-held application
configuration. One answer-producing request remains pinned to one routing
generation, so it cannot mix old and new jurisdiction targets. The previous
verified routing generation and indexes remain available for recovery, and old
index retirement is a later exact controlled action. See
`docs/adr/0002-use-replacement-pinecone-indexes.md`.

Pinecone Index names are date-led rather than purely sequential. A date alone
is insufficient because retries and urgent same-day builds can collide, so the
final naming contract must also include a UTC time or another immutable unique
suffix. At this decision's date, the exact name format and the Azure mechanism
for activating all index names as one production routing generation were open;
Azure App Service itself was the settled configuration boundary.

The current application configuration boundary is Azure App Service. The
development environment has its own deployment slot. Its index-name settings
remain specific to that slot, and the development slot is not a production
promotion or rollback slot. Production cutover therefore requires a distinct
production-candidate slot or another complete-generation activation mechanism.

Decision 5 now fixes names as
`asklegal-<env3>-<jur3>-<YYYYMMDD>-<state12>`. Decision 4 selects activation
through a restricted production `candidate`
slot distinct from development, one complete non-sticky routing generation,
validated manual slot swap, exact verification, and reverse-swap rollback.

## 2026-08-10 — Use this repository as the greenfield modular monorepo

`AskLegal-LegalDBPipeline` owns the complete rebuilt legal-database pipeline.
The code will live in one modular monorepo with separately runnable and
separately permissioned applications for control, human review, source
acquisition, legal processing, and production promotion. Repository colocation
does not merge their credentials, network access, approval powers, or
deployment identities. See
`docs/adr/0001-use-a-modular-monorepo.md`.

## 2026-08-10 — Existing repositories are reference material only

The older Distillation, Release Store, Pinecone, and coordinator implementations
do not define the target repository layout, schema, contracts, or internal
architecture. They may be inspected for lessons and verified behavior, but the
greenfield system does not depend on them automatically.

## 2026-08-10 — Keep substantial data and runtime state outside Git

Git contains code, schemas, prompts, small test fixtures, evaluation
definitions, infrastructure configuration, and documentation. Full legal
corpora, source snapshots, immutable releases, embedding caches, operational
reports, backups, credentials, and production state live in the appropriate
external stores. An ignored local `var/` tree may imitate those stores during
development.

## 2026-08-10 — The canonical brief is an initial overall-system design

`docs/design/INITIAL_OVERALL_PIPELINE_DESIGN.md` is the initial comprehensive
map of the intended complete system, not a final specification. It contains
settled decisions and unresolved system choices. Pilot scope, staged product
versions, rollout planning, migration sequence, estimates, and temporary
operating arrangements are excluded.

## 2026-08-07 — Watchers and scrapers are separate responsibilities

A Watcher performs lightweight scheduled checks and raises a possible-change
signal. A source-specific Scraper then captures the complete changed legal
content, required attachments, and metadata. The responsible Legal Desk decides
legal identity, status, and eligibility from that preserved evidence. A Watcher
alert alone can never become a Search Record.

## 2026-08-06 — Pinecone is a clean current serving copy

Pinecone serves the approved corpus used by Ask.Legal. It is not the permanent
archive and does not provide historical or “law as at date” search. Superseded
legislation and uncertain material remain recoverable outside Pinecone. A
negatively treated Case Proposition remains searchable only when the case rules
still support current use and any mandatory sourced authority note is present. An
exact proposition conclusively overruled by an authoritative court is retired
from current Pinecone and preserved outside it under ADR 0014.

ADR 0079 later adds one narrow, explicit analytical exception: valid last-
verified legislation remains searchable with mandatory warnings when an
official change is known but its updated official consolidation is not yet
available. The exception is neither historical search nor a current-text claim.

## 2026-08-06 — The human approves the complete frozen package

Every production addition, replacement, retirement, and exact-ID removal is
included in one complete frozen Promotion Manifest. The human approves or
rejects that package as a whole. Changing any included evidence, record, target,
configuration, recovery fact, or fingerprint requires a rebuilt package and
new Approval.

## 2026-08-06 — Prospective legislation stays outside search

Enacted or assented legislation that has not commenced is preserved in the
Waiting Room outside Pinecone. It enters a Promotion Manifest only after
official commencement is confirmed and an official updated consolidation is
available. The system does not splice amendment instructions into an old Act.
A commenced amendment without an updated official consolidation creates a
reported Coverage Gap. ADR 0079 later requires warned analytical records for
affected locations wherever valid latest applicable official HKeL wording is held until
the updated official consolidation is available.

## 2026-08-06 — Legislation is tracked from Act to Search Record

The Management Register tracks each Act, Official Version, Provision or stable
legal location, and derived Search Record. Every Search Record remains
traceable to that hierarchy.

## 2026-08-06 — Case search uses proposition records

Each distinct material Case Proposition becomes one self-contained
`type: "case"` Search Record containing the facts, issue, answer,
qualifications, application, result, opinion type, citation, and exact judgment
support needed to understand it. There is no duplicate case-overview vector and
no separate whole-case retrieval feature. A case with no material Case
Proposition creates no Pinecone record; uncertainty is quarantined.

## 2026-08-06 — Later case treatment is observed, not predicted

The system may identify later judgments and propose sourced treatment
classifications. It cannot predict that a Case Proposition will be overruled or
retire it because an AI model considers it weak. Treatment must identify exact
supporting passages, the affected proposition where possible, the court and
opinion relationship, and review state.

## 2026-08-06 — Case Propositions and Principles stay separate

Case-derived propositions remain `case` Search Records. Jurisdiction-specific
Principles remain source-faithful `principle` Search Records derived from their
approved publisher sources.
The system does not blend or silently rewrite the two families.

## 2026-08-06 — Both provider-native and separately administered recovery are required

Pinecone-native backup and separately administered encrypted evidence and release backup
solve different failure modes. The intended system requires both, plus tested
restoration. A second folder on the same workstation is not a separate
backup.

ADR 0094 later defines “independent” here as independent of Pinecone, the
workstation, ordinary applications, the primary Blob account and subscription,
and their day-to-day administrators. The accepted Azure-only design does not
claim independence from Azure or the shared Microsoft Entra tenant.

## 2026-08-06 — Uncertainty is quarantined rather than guessed

Conflicting official evidence, incomplete source capture, unclear legal status,
and unsupported AI output are preserved in Quarantine. Unrelated clear work may
continue, but Quarantine remains visible in the report and coverage status.
