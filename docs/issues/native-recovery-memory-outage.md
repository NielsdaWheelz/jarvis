# native turn retries stalled the memory endpoint

open, 2026-11-18. production release `05d1c33`, provider-runtime `0ebc1cb`,
kernel `3afc584`, stock codex `0.160.0`. times below are utc.

[adr 0086](../decisions/0086-native-recovery-and-memory-availability.md) owns
the accepted repair and its installed acceptance. this issue records the incident.

## incident

the macbook `codex-work2` client submitted a 928-byte note at 20:58:38.
its 300-second deadline expired at 21:03:38. a separate client initialization
also timed out. at 21:12 postgres held no committed `memory_log` row for
submission `fd0098ef-0dc3-42e7-abf8-8b50147f290b`. its original utf-8 sha256 is
`1ffb02e2abd6cab51f8c6621a45a7c4097cdabc62510f421970a43148e56f6d9`.
external tls and direct
loopback tcp both connected, but neither received an http response. seven
canonical requests were pending. on 2026-11-18 the owner’s read-only production
inventory identified pending mail owner request
`0d3bcc75-749d-4014-a0df-3cdf545366b3`, the request selected by the stopped
repair. attempt 19 is the first of the 108 already-fenced attempts. the
snapshot rechecks the original request and cohort under deployment ownership.

## cause

1. at 20:25:23, native attempt 19 submitted 2,326,106 characters in one text
   input. the pending owner request was linked to all 302 `gmail.read_message`
   and 37 `gmail.search` receipts in the opening. those receipts occupied
   2,222,880 bytes in their stored json representation. jarvis includes their
   full contents as required recovery context. the provider's
   `codex_native_request_fits` checks a 4 mib encoded transport envelope.
   stock rejected `turn/start` with json-rpc `-32602` and an input limit of
   1,048,576 characters. stock returns `code=-32602` and
   `data={input_error_code:"input_too_large",actual_chars:2326106,max_chars:1048576}`
   for that measured input. the retained jarvis evidence is the uncertain
   submission and provider error reason. the structured shape is verified at
   the deployed stock revision. [stock error constructor](https://github.com/openai/codex/blob/a956835d020762cb2b570053af06f643a11c0ecc/codex-rs/app-server/src/request_processors/turn_processor.rs#L502)
2. the provider recorded the reply as `AgentUncertain` because the writer had
   entered. the kernel fenced the attempt. `NativeRunner.run` returned
   `progressed`, so the service immediately tried again. attempts 19–126 all
   retained the same rejection. all 108 were already fenced, with zero native
   turn bindings, terminal seals or tool invocations.
3. before each turn, `recover_native_products` selects every column of every
   attempt with a null product outcome, materializes the rows and fences them
   again. at 20:49:03 it selected all 108. their request columns alone occupied
   393,996,644 stored bytes. the first and last request documents each expand to
   about 7.27 mb of json text. postgres finished the query at 20:49:12 and
   waited for the client. the recovery scan had zero rows needing a fence or
   terminal settlement. the query occupied the shared, serialized owner
   connection while its client consumed the rows.
4. the jarvis main thread was in kernel memory reclaim
   (`mem_cgroup_handle_over_high`). the process had 2.06 gib resident and
   2.94 gib swapped against a 2 gib cgroup high threshold, with zero oom kills.
   the worker and memory http server share an event loop. the last completed
   http request was logged at 20:49:02. by 21:12 the loopback listener had 97
   connections waiting to be accepted.

## production repair progress

the verified stopped cut restored memory on 0015 and the original client
received and reopened its note. attempt 127 used original mail receipts and
fresh observations. its partial response had 2,000 body characters and a
143-character limitation. the published field schema accepted both. their
rendered combination exceeded the single discord message bound. the failed
product parked 27 proven deliveries, including the original mail request.
two successful work actions retain their original receipts. preserve this
seal and resolve the schema mismatch before named operator release.
[production evidence](../decisions/0086-native-recovery-and-memory-availability.md#production-cutover-evidence)

## closure

close after installed proof of the four contracts in adr 0086. verify the old
mail request resumes with its recorded barriers and the original native client
receives one canonical receipt for the affected note. an expired deadline
alone establishes neither loss nor success.
