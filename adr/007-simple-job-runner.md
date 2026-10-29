# ADR-007: Admin-triggered endpoint instead of a scheduler/job queue for decay

**Status:** Accepted (S6)

**Context:** The memory decay job (design brief §9: weight = importance x confidence x
half-life decay x reinforcement bonus; archive below a threshold, delete after 12 months
archived) needs to run periodically across every customer's memories. Could stand up a
scheduler (cron, Celery beat, Temporal) to run it automatically, or expose it as something
triggered on demand.

**Decision:** `POST /admin/decay` in `api/app/main.py` runs the full decay sweep synchronously
when called, using the admin DB role (it intentionally spans every customer, which
per-customer RLS, I1, would otherwise block). Nothing in this project calls it on a timer --
v1 is admin-triggered only, exactly as the design brief itself specifies ("v1 is an
admin-triggered endpoint, not a scheduler").

**Consequences:** No scheduler infrastructure, no extra always-running process, no new
dependency (Celery/Temporal/cron) for a solo-builder portfolio project to operate and debug.
Tradeoff: decay does not happen automatically -- someone (or an external cron hitting this one
endpoint) has to actually call it for memories to ever archive or delete. Acceptable for a
demo; a real deployment would want a scheduled trigger (even a simple hosted cron calling this
same endpoint) rather than a new job-queue system.
