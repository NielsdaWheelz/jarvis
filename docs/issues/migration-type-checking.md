# migration typing outside the configured gate

problem: an ad hoc `uv run pyright src migrations` reports four existing typing
errors outside the declared `src`/`scripts` gate: `migrations/env.py:29` passes an
`object` annotation where alembic expects a sqlalchemy connection; the missing
`pgvector.sqlalchemy` stub leaves two `0001` embedding columns partially unknown.

impact: migration modules do not have a clean standalone strict type check.
no runtime defect was found: the callback receives sqlalchemy's real synchronous
connection, and multiple fresh postgres chains through `0011` passed. the normal
project check remains unchanged and does not include historical migrations.

resolved when a deliberate migration typing scope and accurate connection/vector
types make that command pass without changing historical sql behavior.
