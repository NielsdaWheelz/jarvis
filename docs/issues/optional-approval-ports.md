# optional approval ports

problem: approval and recovery construction still supports missing dependencies
and an alternate ordinary delivery transport that production never selects.

evidence: the sole cli constructors supply schedule notifications and the approval
disabler; service completion always supplies cancellation. ordinary delivery uses
the same discord client. temporary real-postgres checks with synthetic external
adapters passed for claim-before-ack, cancellation, denial, exact attachments,
disable-before-recovery execution, incompatible approvals, and schedule notification.

resolved when those callback/disabler/cancellation inputs are required and the
unused `OrdinaryDelivery` override and unreachable missing-port branches are gone.
retain the real startup callback closures and all action/delivery ordering; repeat
the characterization and independently review. implicit tokens, no-op defaults,
and the unsupported alternate transport deliberately cease being accepted.
