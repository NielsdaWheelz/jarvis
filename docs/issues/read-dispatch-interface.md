# read dispatch interface

problem: both read dispatchers carry a recorder type parameter solely for an
unused public recorder property. this exposes an implementation detail without
serving a consumer.

evidence: production consumers use dispatch and budget recovery; no source,
script, or deployment caller reads either property. a temporary real-postgres
characterization passed for memory dispatch and exact receipt replay with a fresh
recorder and budget, preserving one handler entry and restored evidence.

resolved when `ReadToolDispatcher` and `MemoryToolDispatcher` take `ReadRecorder`
directly, their unused properties and type parameters are removed, and the cli's
memory dispatcher annotation is updated. retain execution bodies and recorder
ownership, repeat the characterization, and independently review the cut.
