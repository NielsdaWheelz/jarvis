# independent recovery of drive documents

deferred to a future decision and pr. [drive filing](../decisions/0120-drive-files.md) makes the owner’s google account the only permanent document store. losing the jarvis host leaves those files in drive. account loss or permanent deletion can still put the only copy out of reach. drive normally empties trash after 30 days. the existing postgres recovery job excludes document bytes. [google trash](https://support.google.com/drive/answer/2375102) · [database recovery scope](../decisions/0088-storage-and-memory-recovery.md)

if the owner chooses independent recovery, agree on coverage, frequency, key custody and retention. verify a separately controlled copy by reopening a byte-identical pdf and a usable editable native-doc export without google or jarvis. until then record the accepted single-provider exposure. this issue authorizes no export, credentials, job or backup implementation.
