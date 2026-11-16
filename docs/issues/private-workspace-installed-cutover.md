# private workspace production cutover

problem: slice 4's source and isolated candidate do not activate the private
workspace in production. the selected installed deployment still has schema-4
mapping and no `/var/lib/jarvis-notes` checkout. intermediate activation remains
deliberately refused.

impact: production main cannot use the new native workspace. source/candidate
qualification must not be reported as installed acceptance.

evidence: [slice 4](../private-notes-and-rolodex.md) owns source, upstream pins,
candidate journeys and cleanup. [the roadmap](../implementation-plan.md#v2-reviewable-pr-slices)
owns the remaining sequence; [operations](../operations.md#private-workspace-handoff)
owns bootstrap and host/application replacement. a concurrent production rollout
observed during qualification did not install this slice's schema or checkout.

resolved when: the final v2 cutover accounts for reminders and entered effects,
creates the selected private remote, bootstraps the ordinary checkout under the
actual native account environment, installs the same qualified release's schema-5
mapping and host/application units, and verifies an actual owner discord
file/helper/git journey plus restart with dirty-work and original-receipt
preservation. record physical delivery and installed authority separately from
the temporary controlled gateway/connector proof. no intermediate activation,
credential copy, automatic pull or native-command replay.
