# material window may skip large agent observations

problem: `CapturingReadDispatcher.take_material_sections` hands the rememberer
the most recent tool observations under a 180 000-byte window and skips any
single observation larger than the remaining room. after adr 0048 an `agent.list`
result may reach 1 mib and a control result 256 kib, so such an observation is
silently absent from memory formation material.

impact: the main model saw the result in its turn; only the rememberer's
material misses it. no action, evidence or answer is affected.

evidence: `src/jarvis/thread_runtime.py` (`_MAX_MATERIAL_CONTEXT_BYTES`,
`take_material_sections`), predating pr 3; the raised agent limits make it reachable.

resolved when the testing redesign or a later slice decides whether the
rememberer needs a bounded projection of oversized observations, and records the
choice in the spec. pr 3 changes no window without a requirement.
