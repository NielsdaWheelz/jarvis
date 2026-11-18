# pre-native action lineage bound rejects a steered write

on installed `844fe16`, native main attempt `0070f823-1255-4b4f-89c9-fb604f42301d`
accepted its fifth callback, `calendar.update_event`. its request and typed
arguments were valid. the host failed before inserting an action. the
unsealed native attempt was fenced and the original invocation retained.
the calendar, draft, send, worker and todo stayed on their original identities.

`_ExecutionEnvelope.input_message_ids` limits a durable action to 100 input ids.
the admitted invocation has 124. its exact retained shape validates with 100
ids and fails at 101 and 124 with `input_message_ids:too_long`. one running
turn can accept several bounded input batches. each action requires their
complete ordered provenance and its actual checkpoint.

resolve by qualifying normal action persistence and readback for complete
steered lineage with all identity and authority checks intact, then verify the
real continuation through an authorized update. retain the original callback
and fence. no effect was entered and no retry of a prior external write is due.

source fix `f8f7fc6` passed the independent actual postgres dispatcher proof.
runtime artifact `34d1620` passed local and hosted checks and is installed
inactive with its verified contained host. actual continuation requires new
owner timing steering because the earlier window expired. the original
unentered callback, pending send, work and exact worker target remain preserved.
