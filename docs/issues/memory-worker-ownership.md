# memory worker ownership

problem: `service.py` contains rememberer and dreamer implementation alongside
discord coordination. cli maintenance and six qualification scripts import these
workers independently, coupling memory work to an unrelated service module.

evidence: `RemembererWorker`, `DreamerWorker`, their result types, and
`_recalled_id_sections` depend on memory/kernel ports, not `JarvisService`.

resolved when these cohesive workers have one memory-owned module, consumers
import it directly, and no compatibility re-exports remain. characterize real
memory commits, embedding failure, and cancellation during commit before moving
the code; preserve their ordering and exception behavior.
