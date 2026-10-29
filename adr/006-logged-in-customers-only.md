# ADR-006: Logged-in customers only, no anonymous identity merge

**Status:** Accepted (S1)

**Context:** The memory layer needs a stable identity to key memories to. Could support
anonymous browsing with later account linking (merge an anonymous session's history into a
real account on login), or require identity up front.

**Decision:** Every memory is keyed to a real `customer_id` from the start -- a simple
user-switcher UI (four seeded demo personas: Maya, Leo, Ana, Sam) stands in for real login.
Declining the consent prompt, or chatting with no `customer_id` at all, is a fully supported
anonymous path (same as S2's original no-memory chat) -- it just never writes or reads
memories (I6). There is no anonymous-session-to-account merge anywhere in the system.

**Consequences:** No identity-resolution/merge logic to build or get wrong (a notoriously
easy place to leak one person's data into another's history). Tradeoff: this demo's "login" is
four fixed personas, not a real signup/auth system -- fine for demonstrating the memory layer
itself, but a real product would need actual authentication and a way for a new real person to
get their own `customer_id`, which this project deliberately does not build (see
`SESSION_LOG.md`'s 2026-10-28 entry for the explicit scope conversation on this point).
