# worker follow-up scope

[managed delegation](../decisions/0112-managed-agent-delegation.md) limits
`after` to a prior job in the current request's causal component. v13
`ActionStore.register_delegation` reads the named job in the same conversation
and takes its machine and worker. its lookup omits the prior origin's component
membership check. a follow-up can therefore address an unrelated request's
worker in the same chat. this is a source finding. no misdelivery was observed.

the [placement candidate](../decisions/0114-skid-worker-placement.md#candidate-evidence)
rejected that case before insertion with zero skid writes and accepted a related
job on the original machine handle. close this issue after the qualified binding
is selected in production.
