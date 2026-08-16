# AskLegal Durable Task adapter

This narrow package is the local durability checkpoint for ADR 0093. It keeps
business authority in a fake Management Register while exercising Microsoft's
standalone Python Durable Task SDK against the disposable local Scheduler
emulator. All fixtures and effects are synthetic.

The emulator proof is opt-in and requires Docker. The ordinary unit suite uses
the SDK's replay executor and local fakes; neither path accesses Azure.

## Proved boundary

- Every instance carries an explicit numeric workflow version plus exact build,
  configuration, contract, input, and effect-command fingerprints.
- The orchestrator contains coordination only and places only opaque IDs,
  fingerprints, closed codes, bounded counters, and sanitized status under the
  64 KiB internal history ceiling.
- External events are only register references. The activity resolves the
  authoritative fact and rejects stale, duplicated, unknown, or wrong-lineage
  events.
- The effect activity rechecks current register lineage, capability, accepted
  event, command ID, and fingerprint. A simulated lost acknowledgement causes
  two SDK deliveries but one effect and one immutable receipt.
- A new worker can resume Scheduler-owned history against a fake register
  reconstructed from an exact snapshot.

The ordinary test uses Microsoft's in-memory SDK backend. The stronger opt-in
test uses the local Scheduler emulator pinned to:

```text
mcr.microsoft.com/dts/dts-emulator@sha256:1b49dcf1581168f5c620a4f32083e1291a7dddfa60434acb3eacd8b23355936a
```

Run that proof only in a fresh disposable container:

```bash
sudo docker run --name asklegal-dts-spike -d \
  -p 127.0.0.1:8080:8080 -p 127.0.0.1:8082:8082 \
  mcr.microsoft.com/dts/dts-emulator@sha256:1b49dcf1581168f5c620a4f32083e1291a7dddfa60434acb3eacd8b23355936a
ASKLEGAL_DURABLE_EMULATOR=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  .venv/bin/pytest -q \
  packages/durable-task-adapter/tests/test_durable_emulator_integration.py
sudo docker rm -f asklegal-dts-spike
```

The emulator is memory-only. This proves worker restart, not persistence across
emulator termination, managed identity, Azure networking, retention, capacity,
or regional recovery.
