# private file creation in the shared notes checkout

an ordinary git object or file created with mode `0666` inherits the shared access rules. a writer can deliberately create a regular notes file with mode `0600`, for example using `mkstemp` followed by rename. linux masks the inherited acl for that file. jarvis and the other contained accounts can then lose access to it. the stopped installer detects such files at its access scan.

closure requires identifying an actual supported writer that creates a private file in the shared checkout, fixing its publish mode at that writer, and demonstrating that peer accounts can edit the file while jarvis can only read it. keep private incoming mail outside the shared rule. [adr 0108](../decisions/0108-codex-quota-standby.md)
