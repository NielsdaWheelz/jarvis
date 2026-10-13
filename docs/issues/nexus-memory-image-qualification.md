# nexus memory image qualification

status: open, 2026-10-13. tracked in [the owning issue](https://github.com/NielsdaWheelz/nexus-web/issues/571).

compose configuration proves both build-secret grants and unset-key failure, but clean builds and key-leak inspection remain unrun. resolved when both disposable worker builds succeed with an authorized read-only key, a missing file fails, and produced layers/output/runtime config contain no key; start no installed service.

contract: [memory repairs](../memory-repairs.md). existing controlled evidence is
in [the memory integration record](../universal-memory.md#memory-repair-source-candidate).
