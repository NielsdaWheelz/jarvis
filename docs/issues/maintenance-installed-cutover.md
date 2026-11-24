# installed maintenance cutover

[adr 0104](../decisions/0104-maintenance-without-owner-pause.md) has source and isolated candidate evidence. the production release still selects the predecessor, so real maintenance still uses its operator procedure.

close this after a separately authorized named release adopts the custody guards and verifies the configured backup reader from its archive. capture the exact before and after release, service readiness, owner control, compatible pending work and next scheduled backup. use the existing owner state and original effect receipts. [operator procedure](../operations.md#named-production-maintenance)
