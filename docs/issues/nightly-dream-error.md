# nightly dream ended before seed progress

at 11:04:30 utc on 2026-11-20, installed release `e7f5916` ended its nightly
attempt after about 209 seconds. stock metadata showed five sol/xhigh turns.
the service logged `dream did not complete: type=MemoryError`. the claim
stood, with no committed notes or seed progress. the journal retained neither
the library error code nor a usable token total. `DreamerWorker.run_one`
logs the exception class for this path. the historical cause is unknown.

the [model candidate](../decisions/0093-subscription-model-refresh.md) must
complete its own grounded dream. record a bounded library reason on a
reproduced failure and fix its owning layer. close this incident on identified
cause, a representative corrective check and installed completion with
consistent notes, references and seed progress. retain the historical
uncertainty if reproduction cannot identify the cause.

the production archive contains six synthesis notes committed together on
november 21 at 11:05:08 utc. at the november 23 readback the nightly seed
cursor had reached 8,184, the full ready prefix. newer captured material was
still waiting on the [parked compactor](compactor-native-event-buffer.md).
the november 20 failure cause remains unknown.
