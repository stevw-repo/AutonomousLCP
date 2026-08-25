# AskLegal Management Register adapter

This package is the narrow synchronous `mssql-python` adapter and exact,
forward-only migration runner selected by ADR 0091. Migration `000001` retains
the original synthetic Approval/Serving State proof. Migration `000002` adds
the complete common M2 register substrate: application-owned command results,
aggregate versions, events, effect intents, renewable claims, fencing,
attempts, terminal receipts, explicit policy state, projections, recovery
views, and five procedure-only application roles.

Migrations `000003` through `000009` add the V1 Review-ready proposal and
decision projection, exact single-use registered Approval consumption,
mutually exclusive revocation/invalidation, and the Promotion-only no-effect
execution-authorization transition. Migration `000008` then consumes the exact
authorized `exe_` lineage, approved first-action authority, and current
capability-evidence reference in one atomic `EXECUTION_RUNNING` transition plus
first Effect Intent. It registers no effect handler and performs no provider
effect. Migration `000009` lets an owning application read immutable intent
bytes only after proving its exact live claim and fencing token. The adapter
verifies the stored fingerprint and prior attempt count before returning the
claim, consumes every terminal-receipt result row, and exposes exact replay.

This is still a local implementation proof. It does not authorize Azure
access, legal data, deployment, or production use.

The ordinary repository suite skips the marked SQL Server test. The integration
suite requires the digest-pinned SQL Server Developer container documented in
`.agent/CONTEXT.md` and an ephemeral
`ASKLEGAL_SQL_CONNECTION_BASE` environment value. Keep its generated local
credential outside the repository and remove the disposable container and
credential file after the proof.

## Reproduce the real-engine proof

The host prerequisites are Docker and OpenSSL. Do not add the developer to the
Docker group. From the repository root:

```bash
umask 077
printf 'MSSQL_SA_PASSWORD=Aa1!%s\n' "$(openssl rand -hex 24)" \
  > /tmp/asklegal-management-register-m2.env
sudo docker run --name asklegal-management-register-m2 \
  --hostname asklegal-mr \
  --env-file /tmp/asklegal-management-register-m2.env \
  -e ACCEPT_EULA=Y -e MSSQL_PID=Developer \
  -p 127.0.0.1::1433 -d \
  mcr.microsoft.com/mssql/server@sha256:fa0dcf206087759fe6dad4cc02bfa88d97439085e548fbca9039330519c0cf1d
sudo docker port asklegal-management-register-m2 1433/tcp
```

After the logs say the server is ready, replace `<PORT>` with the printed host
port and run:

```bash
set -a
source /tmp/asklegal-management-register-m2.env
set +a
export ASKLEGAL_SQL_CONNECTION_BASE="Server=127.0.0.1,<PORT>;UID=sa;PWD={$MSSQL_SA_PASSWORD};Encrypt=yes;TrustServerCertificate=yes"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q -m sql_server \
  packages/management-register-adapter/tests/test_sql_server_integration.py
unset ASKLEGAL_SQL_CONNECTION_BASE MSSQL_SA_PASSWORD
sudo docker rm -f asklegal-management-register-m2
rm -f /tmp/asklegal-management-register-m2.env
```

The test recreates only its exact synthetic database inside the disposable
container. It performs no Azure, source, model, embedding, Pinecone, routing,
or production operation.
