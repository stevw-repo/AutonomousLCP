# AskLegal Management Register boundary

This framework-free package is the completed M2 persistence boundary. It
contains the typed `ManagementRegisterStore` protocol, immutable register
operation and recovery value objects, explicit configured-or-undecided policy
state, and a deterministic thread-safe in-memory implementation.

The fake is a behavioral reference and test adapter. It proves command
identity and exact replay, optimistic versions, single-winner constraints,
atomic event and effect-intent append, effect leases and fencing, terminal
receipt selection, projection rebuild, and digest-verified recovery. It makes
no database, filesystem, network, provider, or production call.

The SQL Server implementation boundary and exact forward-only migrations live
in `packages/management-register-adapter/`.
