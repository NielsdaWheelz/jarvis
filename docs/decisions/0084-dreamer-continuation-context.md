# adr 0084: dreamer continuation context

status: accepted, 2026-11-17 owner-local date, by explicit owner choice: "raise
only dreamer context ceiling to 1 mib". supersedes only the 327,680-byte dreamer
context bound retained by adr 0083 and the consolidated memory contract.
source implementation and controlled qualification pass; actual installed stopped
quiet completion passes on `650eb7c` with three notes and consumed seeds
`[0,4127)`. the combined journey and final reset remain pending.

## evidence

actual installed `d34d30c` run `734fb92c-70a8-498b-9e21-bf34e71e58ca` passes
the former input guard with 421,532 input tokens over five provider turns, then
stops with `ContextLimitExceeded` at `continuation_context:184` / `_project:242`.
no notes or consumed progress commit. the earlier measured input diagnosis and
unknown earlier causes remain preserved in f2's evidence.

source audits find no duplicate bootstrap or read rendering. a valid maximal
64,000-byte seed and 8,000-byte older sample produce a 292,790-byte controlled
bootstrap; prior actual-postgresql proof measures 292,817 with different framing.
all nodes obey the 2,048-byte bound. the library's shared result-size primitive
already includes the actual observation frame and native/MCP encodings.
one supported near-limit read adds 65,533 bytes and reproduces the current
failure. independent source sizing covers ordinary and escaping-heavy pages.

## decision and trade-offs

raise only `DREAMER_KERNEL_LIMITS.max_new_context_bytes` to 1,048,576 and advance
dreamer v6 to v7. retain personal-subscription sol/xhigh, input 1,000,000, output
16,000, ten provider turns, two repairs, 300 cooperative seconds, eight tool calls,
all grants, ready seeds, full admitted reads, nightly priority and atomic
completion. no clipping, smaller source allocation, fallback, prescribed read
procedure or budget framework.

the existing eight bounded read slots plus maximal bootstrap require about
817,105 visible bytes. the controlled ordinary eight-read path measures 817,054
visible bytes and 825,582 canonical bytes before the final provider turn. its
conservative canonical total after that terminal is 825,809 bytes, leaving
222,767 bytes under 1 mib. 512 kib covers only three maximal read frames.
this sizes the existing envelope rather than one failing fixture.

the host cumulative context threshold rises 3.2 times. longer permitted history
can increase generation work and reach unchanged input/time/native limits
sooner. reported-input enforcement remains after generation and can overshoot.
this is neither a monetary bill nor a guarantee of every maximal repair/output
path, weekly availability or useful completion. strict overflow remains possible.

## qualification and migration

retain the real old-role one-read red and new composed-role eight-read green
through the actual kernel and controlled public provider/dispatch ports. compare
every other composition field exactly, run frozen required checks and independent
review, then delete only new probes after hash receipts. no schema migration or
canonical control change. actual stopped fixed-model quiet completion, the
genuine continuation journey and final reset remain required.
