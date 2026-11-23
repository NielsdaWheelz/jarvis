# historical tool corpus

the owner selected future capture only for [adr 0098](../decisions/0098-conversation-capture.md) and reserved redesign of existing history for a separate pr. external tool-call/result records occupied roughly 81% of the first 77,150 admitted positions on november 23. the count includes tools that carried conversation. those records still cost storage and historical construction. source ids, frozen positions, citations, dream references and backups already refer to them.

a separate proposal must measure the recoverable cost, name the original evidence and references it would retain or retire, and prove its migration and restore on an isolated copy. resolve with an owner decision to keep history as-is or a separately authorized, verified change. the [parked compactor](compactor-native-event-buffer.md) has its own repair.
