# ADR 003: Embedded Qdrant for the Validated Path

## Decision

Keep the existing embedded Qdrant store as the validated retrieval path. Document
external Qdrant as a deployment extension rather than adding a container that the
application does not yet wire up.

## Context

The project already ships a pre-indexed clinical guideline store. Moving it into
a separate container would require a restore or seed step, runtime configuration
for a remote Qdrant URL, and additional validation. That work is valuable for a
larger deployment, but it is not required to demonstrate local inference, MCP
integration, model routing, or OpenShift-compatible manifests.

Adding an unused Qdrant container would make the architecture look broader while
reducing honesty and reproducibility.

## Consequences

- Local dev and the validated demo use the embedded Qdrant store in
  `src/knowledge_pipeline/qdrant_store`.
- Docker Compose runs the orchestrator and MCP server, while retrieval remains
  embedded.
- Helm can include future Qdrant scaffolding, but the README and runbook must
  state that embedded retrieval is the validated path today.
- A production follow-up can add `QDRANT_URL`, seeding, readiness checks, and
  backup/restore handling.
