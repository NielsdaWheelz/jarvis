# rehearsal checkouts held by virtualization

macos virtualization retained read-only descriptors on the initial worker setup
checkout at `rehearsal-kzlvsap_/checkout` after its container was removed. the
checkout is clean. the working probes, databases, containers, images and final
checkouts were removed. the hold leaves one disposable checkout on disk.

on 2026-11-20, the worker cleanup receipt in
`qualification/adr0094/worker/cleanup-final.json` recorded the open paths.
resolve when the descriptors close, the clean checkout is removed and the
receipt records its disposition. [adr 0094 qualification](../decisions/0094-worker-tools-and-native-context.md#qualification)

adr 0095 encountered the same hold on the macbook after initial isolated mail
and memory runs. the named scratch paths and observed vm users are retained
with those runs' cleanup evidence. the final rehearsals copied the postgres
init fixture before startup, which allowed their checkouts to be removed.
release the earlier clean checkouts after the verified descriptors close.
[adr 0095 qualification](../decisions/0095-context-cost.md#implementation-evidence)

adr 0097 encountered the same hold on november 23. the removed postgres fixture
had mounted `deploy/postgres-init.sql` from the intermediate `jarvis-0097`
checkout. virtualization still has read-only descriptors. the checkout is
clean on `review/adr0097-0018` at `b6bfa59`. the final candidate and its
verification checkout have their own dispositions in the 0097 cleanup receipt.
remove the intermediate checkout after the descriptors close.
