---
status: accepted
date: 2026-08-10
---

# Use replacement Pinecone Indexes and complete routing generations

Each jurisdiction's serving target will be one complete immutable Pinecone
Index. A promotion builds a fresh replacement index for every affected
jurisdiction while Ask.Legal continues using the previous verified indexes.
Unchanged jurisdictions carry their exact verified index references into the
next complete routing configuration.

Ask.Legal receives the active Pinecone Index names through Azure App Service
application settings. The application treats those names as one complete
versioned routing generation that also identifies the Serving State. The
promotion worker may activate the new
generation only after every replacement index and the complete target set pass
verification and the exact routing configuration remains covered by a valid
Approval. Each answer-producing request pins one routing generation throughout
its searches and records the matching Serving State and activation event; a
request already in flight may finish on the previous generation but cannot mix
generations.

The development environment has a dedicated App Service deployment slot. Its
index-name settings are slot-specific, its Pinecone access is restricted to
development targets, and it must never be used as the source of a production
cutover or as the destination of a production rollback. A production-candidate
slot, if used, is a separate boundary.

Pinecone Index names are date-led instead of purely sequential. They also need
a UTC time or another immutable package-bound suffix because a date alone can
collide during retries or multiple same-day runs. The exact provider-valid name
format remains to be specified. The working candidate is
`asklegal-<env>-<jurisdiction>-<YYYYMMDD>-<package8>`, capped at 40 characters.

The active configuration changes only if the approved base generation is still
active. Failure before activation leaves the previous state serving. A material
failure after activation invokes the approved rollback to the previous complete
routing generation. Previous indexes remain protected for the recovery window;
retirement is a separate exact controlled action and cannot occur while a
retained routing generation or recovery obligation references an index.

## Considered options

- mutate live Pinecone Indexes in place — rejected because a partially applied
  update could expose mixed old and new legal material;
- use one global replacement index — rejected as the default because a change
  in one jurisdiction would unnecessarily rebuild and enlarge the failure
  domain for all jurisdictions;
- use one index for every jurisdiction-and-material pair — rejected as the
  default because it fragments the complete jurisdiction state and increases
  routing and cutover complexity; and
- update several independent Azure index-name values without a routing
  generation boundary — rejected because partial updates or stale instances
  could expose inconsistent target sets.

## Consequences

Replacement builds require temporary duplicate capacity and may repeat
embedding work. The system must manage complete routing generations, request
pinning, conditional activation, post-cutover verification, rollback, and
eventual exact retirement. Azure App Service is the settled configuration
service. Whether production activation uses a separate production-candidate
slot or another complete-generation mechanism remains open and must be settled
before the cutover design is implementation-ready.

The user deferred the exact production-candidate slot, setting-swap,
activation, refresh, and provider-valid naming details on 2026-08-10. The
accepted replacement-index and complete-routing-generation architecture remains
in force. The deferred details must be resolved before implementation readiness.

ADR 0009 defines the immutable Serving State content and the append-only
activation ledger carried by these routing generations.

## Verified Azure platform facts

Azure App Service injects application settings as environment variables at
startup, and editing an application setting triggers an application restart.
An application setting marked as a deployment-slot setting stays with that
slot. During a slot swap, App Service applies the target slot's slot-specific
settings to the source, restarts and warms every source instance, and only then
switches the routing rules. These behaviors are documented in Microsoft's
[App Service configuration](https://learn.microsoft.com/en-za/azure/app-service/configure-common?tabs=portal)
and [deployment-slot](https://learn.microsoft.com/en-ie/azure/app-service/deploy-staging-slots)
documentation and must be reverified before implementation.

Pinecone currently requires index names to contain only lowercase Latin
letters, numbers, and dashes, to start and end with a letter or number, and to
remain within the API's 45-character limit. The naming contract will maintain
a stricter 40-character project limit. These constraints are documented in
Pinecone's [index-name restrictions](https://docs.pinecone.io/troubleshooting/restrictions-on-index-names)
and [create-index API](https://docs.pinecone.io/reference/api/2026-04/control-plane/create_index)
documentation and must also be reverified before implementation.
