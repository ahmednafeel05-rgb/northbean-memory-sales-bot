# ADR-002: FastAPI + Next.js, one backend service

**Status:** Accepted (S1-S2)

**Context:** Need a Python backend (to share the LLM/memory pipeline code cleanly) and a
browser UI for the chat, memory panel, and ops dashboard, within a solo-builder portfolio
timeline.

**Decision:** One FastAPI service (`api/`) owns every route -- chat, memory CRUD/governance,
retrieval inspection, ops metrics, decay job -- backed by one Postgres database. One Next.js
15 App Router frontend (`web/`), plain JavaScript (no TypeScript, no UI framework), calls that
API directly over REST/JSON. No API gateway, no BFF layer, no separate microservices.

**Consequences:** Simplest possible deployment topology for this scope (two containers plus
Postgres, see `docker-compose.yml`) and no cross-service auth/versioning to manage. Tradeoff:
the one API service has every responsibility (sales agent, memory read/write path, admin
aggregation) -- fine at this traffic/team size, would need splitting before it became a real
multi-team production system.
