# ADR 0006: Do not use a workflow framework in v1

- Status: Accepted; persistence wording amended by ADR 0007; bounded
  agent-kernel distinction clarified by ADR 0017
- Date: 2026-09-01

## Context

Jarvis v1 has a small number of direct flows:

- Recall, converse, respond, remember.
- Periodically dream and rebuild summaries.
- Store an outward action awaiting approval, then approve or deny it.

Temporal, Restate, Celery, or another durable workflow system would add a new
programming model and a new operational surface before these flows have shown a
need for it. DBOS is a PostgreSQL-backed library rather than a service, so the
operational-surface argument does not apply to it; the rejection there rests on
the programming model alone, which is sufficient.

## Decision

Use ordinary Python control flow, PostgreSQL transactions, stable effect IDs,
and a systemd or small process timer.

Persist approvals in the ordinary unified `action` table. Do not keep a worker
blocked while waiting for the user.

Do not add a workflow framework in v1.

## Consequences

Positive:

- Fewer abstractions and dependencies.
- Failures can be understood from application code and database state.
- Memory and conversation work can evolve quickly.
- The operational deployment remains one application plus PostgreSQL.

Accepted costs:

- Retry and recovery behavior must be written explicitly. Every effectful
  application tool call has a persisted identity before dispatch. Canonical
  message and memory transactions are ordinary host bookkeeping and follow
  their own database invariants.
- Numerous future long-running flows could eventually strain this design.
- Migration to a workflow engine may require restructuring coordinator code.

## Reconsideration evidence

A workflow framework may be reconsidered only after actual implementation shows
one or more of:

- Many distinct multi-day workflows waiting on several external events.
- Repeated production bugs in retries, timers, compensation, or recovery.
- Multiple execution hosts requiring coordinated durable ownership.
- Workflow-version migration becoming a material engineering problem.

The existence of cron jobs, one approval wait, or background dreaming is not
sufficient evidence.
