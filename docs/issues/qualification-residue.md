# old qualification resources

problem: v1 qualification reports retain inventories of disposable databases and
private runtime directories awaiting cleanup. their current existence is unknown;
removing the reports does not establish that the resources were removed.

impact: obsolete probes may still occupy local/host storage and retain private
runtime state. no current leak or resource exhaustion is established.

evidence: the cleanup-obligation sections in the historical
[slice 4](https://github.com/NielsdaWheelz/jarvis/blob/42f1fa21c3d2f687a3f3fafc9366fea41023e0cb/docs/qualification/2026-09-05-slice-4.md#qualification-resource-cleanup-obligations),
[slice 5](https://github.com/NielsdaWheelz/jarvis/blob/42f1fa21c3d2f687a3f3fafc9366fea41023e0cb/docs/qualification/2026-09-06-slice-5.md#qualification-resource-cleanup-obligation)
and [slice 6](https://github.com/NielsdaWheelz/jarvis/blob/42f1fa21c3d2f687a3f3fafc9366fea41023e0cb/docs/qualification/2026-09-07-slice-6.md#qualification-resource-cleanup-obligation)
reports name the exact resources. later deployment housekeeping does not record
disposal of these inventories.

resolved when a read-only inventory establishes each named resource's current
status, any remaining disposable resources are removed through scoped operational
cleanup, and disposition is recorded. preserve canonical application state and
native histories. this documentation cleanup inspected or removed no resources.
