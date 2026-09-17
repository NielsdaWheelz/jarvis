# connector keyring environment cutover

problem: the application no longer loads or uses the redundant connector
keyring setting, but the deployment's private environments have not been checked.
the strict private-state installer rejects a source environment containing
`JARVIS_CONNECTOR_ENCRYPTION_KEYS`.

impact: remove that entry from the private source and installed environment before
deploying this change. retain `JARVIS_CONNECTOR_ENCRYPTION_SECRET` and
`JARVIS_CONNECTOR_ENCRYPTION_KEY_VERSION` unchanged. retired keyring values no
longer participate in host secret matching. no ciphertext migration is needed.

evidence: synthetic token load, refresh, reopen, settings, and local installer
checks preserve the qualified single-secret encryption contract. no private
configuration was read or changed during cleanup.

resolved when the owner removes the retired entry from both private environments
and the private-state install accepts the source roster. do not print secret values.
