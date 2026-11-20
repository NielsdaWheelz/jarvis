# adr 0094 setup checkout held by virtualization

macos virtualization retained read-only descriptors on the initial worker setup
checkout at `rehearsal-kzlvsap_/checkout` after its container was removed. the
checkout is clean. the working probes, databases, containers, images and final
checkouts were removed. the hold leaves one disposable checkout on disk.

on 2026-11-20, the worker cleanup receipt in
`qualification/adr0094/worker/cleanup-final.json` recorded the open paths.
resolve when the descriptors close, the clean checkout is removed and the
receipt records its disposition. [adr 0094 qualification](../decisions/0094-worker-tools-and-native-context.md#qualification)
