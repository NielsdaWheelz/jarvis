# unused google keyring

problem: google token construction requires a keyring that it parses and discards.
the extra configuration suggests encryption semantics the application does not use.

evidence: `GoogleTokenManager` uses `_parse_keyring` only to check active-version
membership. encryption uses `_handoff_key(single_secret)`, as spec 9.3 and adr 0027
require. temporary synthetic crypto, settings, and installer checks passed on
`d1295d6`, including reopening with changed unrelated keyring bytes.

resolved when the unused parser, setting, composition argument, secret-list entries,
example, and installer roster entry are removed together. preserve key-version
validation and the actual handoff secret, ciphertext format, and refresh behavior.
repeat the characterization across the cutover and independently review it.

deployment must remove `JARVIS_CONNECTOR_ENCRYPTION_KEYS` from the private source
and installed environment; the strict installer rejects stale source rosters.
retired keyring bytes cease participating in secret matching. no ciphertext
migration is needed. no private configuration was inspected or changed.
