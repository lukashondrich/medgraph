# ADR 002: MCP Boundary

## Decision

Expose OpenFDA drug screening as a FastMCP server. Keep Qdrant retrieval,
routing, LangGraph state, and FHIR patient parsing as direct in-process calls.

## Context

MCP is useful when a tool wraps an external API or capability that other clients
could reuse, and when the implementation may need to be swapped without changing
the orchestrator. OpenFDA fits that boundary: it is an external API with rate
limits, caching, retry behavior, and a clean tool-shaped surface.

Qdrant retrieval is internal application infrastructure, and the routing graph is
core orchestration logic. Wrapping those in MCP would add ceremony without
improving reuse, deployability, or safety.

## Consequences

- The Drug Check Agent can call OpenFDA either directly or through the MCP server
  using `USE_MCP=true`.
- The MCP server uses Streamable HTTP at `/mcp/` plus a `/health` route for
  containerized network access.
- The OpenFDA client is a server-level singleton, so cache state survives across
  tool calls.
- Qdrant remains embedded for the validated path. A remote `QDRANT_URL` is a
  future deployment enhancement, not part of the validated demo path.
