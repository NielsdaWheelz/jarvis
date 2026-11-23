# arch memory activation

arch was deferred while offline on 2026-11-15. it was reachable on 2026-11-20.
jarvis still had admission and connection disabled for all six arch codex and
claude profiles. the arch collector and host bundle were absent. capture begins
at each profile's new native boundary.

the 2026-11-18 workspace cleanup deleted the archived fleet credential store.
on 2026-11-20 two private inputs were recovered. the operator mac stores them
under `code/envs/projects/dev-server/secrets/memory/`, both mode `0600`.
the dev-server checkout's ignored `secrets/memory/` paths link to those files.

- `recovered-declaration.json` matches the original rollout checksum byte for byte.
- `recovered-active-credentials.json` contains the two installed collectors'
  credentials and all twelve connected profile credentials. all fourteen matched
  the live declaration after reopening the file. the registered arch collector
  upload key, `capture:arch`, is the single missing entry.

for the next jarvis deploy, use private working copies and recheck the fourteen
hashes against production. restore the arch key if a matching backup is found,
or explicitly rotate `capture:arch` with the operator's approval. enabling
the six new arch client connections creates their first credentials. verify
that the rendered declaration changes only arch. publish during stopped
maintenance and install the arch bundle through `./workstation apply` on arch.
[deployment checklist](https://github.com/NielsdaWheelz/jarvis/issues/86)

close after verifying long claude retention and all three codex daemons from a
fresh login after apply exits. record each profile's future-only boundary, a
new captured turn, and a memory read, save and exact reopen from a normal
session using that profile's credentials. record any pending profile by name.
