# V1 POC credential-interface spike

Status: fail-closed research result, 2026-08-17

This spike evaluates whether the accepted SQL Server and Versity Gateway
products can consume root/bootstrap credentials under the accepted V1 POC
rule. It is read-only research. No image was pulled, no service was started,
no credential was created, and no external system was changed.

## Fixed acceptance rule

- Encrypted blobs are root-owned and stored outside images and Git.
- `systemd` decrypts only the credentials named by one unit through
  `LoadCredentialEncrypted=`.
- Plaintext may exist only as a read-only file in that unit's
  `$CREDENTIALS_DIRECTORY`.
- A credential value must not appear in a command argument, process/container
  environment, Compose or `.env` file, image metadata, container inspection,
  persistent service file, or log.

Reading a credential file and exporting its contents into an environment
variable does not satisfy the rule. A Docker or Compose secret is only a file
delivery mechanism; it is insufficient if an entrypoint copies the value into
an argument or environment variable.

## Research result

| Product | Documented bootstrap interface | File-only result |
|---|---|---|
| SQL Server 2025 Linux container | Microsoft startup examples and the official container repository require `MSSQL_SA_PASSWORD` in the container environment. The repository has an open enhancement discussion whose workaround also copies a secret file into that environment. | **NOT PROVED**. No Microsoft-supported `MSSQL_SA_PASSWORD_FILE` interface was found. The exact pinned image still needs a bounded black-box inspection because documentation absence is not proof of binary absence. |
| Versity Gateway | The current global options accept root access/secret values through `--access`/`--secret` or `ROOT_ACCESS_KEY*`/`ROOT_SECRET_KEY*`. The Docker guide uses environment variables. | **INCOMPATIBLE IN THE DOCUMENTED INTERFACE**. No root-credential file option is documented. |
| Versity internal IAM | `--iam-dir` stores tenant account data in files. | **REJECTED**. Versity explicitly describes these as plaintext JSON protected only by file permissions; they are persistent plaintext credentials. |

Evidence:

- [Microsoft SQL Server Linux container quickstart](https://learn.microsoft.com/en-us/sql/linux/install-upgrade/quickstart-install-docker?view=sql-server-ver17)
- [Microsoft SQL Server container repository](https://github.com/microsoft/mssql-docker)
- [Microsoft container credential-file enhancement discussion](https://github.com/Microsoft/mssql-docker/issues/77)
- [Versity global options](https://github.com/versity/versitygw/wiki/Global-Options)
- [Versity Docker guidance](https://github.com/versity/versitygw/wiki/Docker)
- [Versity multi-tenant/IAM file warning](https://github.com/versity/versitygw/wiki/Multi-Tenant)

## Rejected shortcuts

- shell command substitution into `docker run -e`;
- `EnvironmentFile=`, Compose `environment`, or a plaintext `.env` file;
- a wrapper that reads `$CREDENTIALS_DIRECTORY` and exports the value;
- passing the value as a SQL/Versity command argument;
- storing Versity IAM JSON under its persistent data directory;
- recording synthetic-but-reusable credentials in tests, unit files, or logs;
- treating Docker inspection restrictions as removal of the plaintext process
  environment; and
- adding another credential store whose own bootstrap violates the same rule.

## Smallest executable proof still allowed later

The proof requires an admitted Ubuntu test host, exact image digests, synthetic
one-use credentials, and explicit permission to pull/run the images. It must:

1. mount only a systemd credential file into a throwaway unit/container;
2. initialize the product without copying the value to arguments,
   environments, logs, image metadata, or persistent files;
3. inspect unit/container configuration, process arguments and environments,
   logs, filesystem layers, and persistent volumes for seeded canary values;
4. rotate the credential and prove old-value rejection;
5. restart from persistent service state without reintroducing a bootstrap
   secret; and
6. destroy only the named throwaway state after evidence capture.

The current Mac has no Docker executable, and the accepted artifact policy
does not authorize image pulls or builds. Therefore no honest executable proof
can run in the current repository-only boundary.

The exact disabled proof inputs are now frozen at
`infrastructure/poc/credential_interface_proof_inputs.json` and checked by
`tools/v1_poc_credential_interface.py`. They bind the three affected services
to the artifact and systemd inventories, six proof steps, seven canary-
inspection surfaces, 12 evidence classes, rotation/restart behavior, and
named evidence-then-cleanup. Every result is `NOT_RUN`, all host/image/
credential authority is false, and no canary or credential value is stored.

## Decision gate if exact-image proof fails

Do not silently weaken the accepted rule. A user decision will be required
among materially different choices:

1. choose products with native file-based credential inputs;
2. accept and maintain a narrowly reviewed custom product build that adds a
   file interface; or
3. explicitly relax the secret rule for a documented, bounded bootstrap path.

The current recommendation is to preserve the secret rule and prefer a product
with a native file interface over a long-lived fork. SQL may warrant a separate
one-time bootstrap assessment because its persistent master database changes
subsequent startup behavior; Versity's documented ordinary runtime interface
is already incompatible.
