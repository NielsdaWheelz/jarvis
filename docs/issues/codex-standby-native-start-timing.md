# three-host codex startup and stop timing

the shipped host units allow 20 seconds to start and 10 seconds to stop. the first concurrent start in the macbook x86_64 emulator hit both limits. later functional checks used guest-only limits of 120 and 45 seconds. those checks establish the unit dependencies and socket behavior. production timing remains unqualified.

closure requires measuring concurrent startup and clean stop on the selected deployment host, then observing the primary enablement pull up both standbys and jarvis during a real boot. record the margin against the shipped limits and the resulting application state. [adr 0108](../decisions/0108-codex-quota-standby.md)
