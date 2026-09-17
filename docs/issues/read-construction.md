# read construction

problem: `build_read_catalog` and `build_slice3_catalog` duplicate google token,
google read, maps, brave, and web construction. the latter adds memory only.
policy or credential wiring changes must be repeated manually.

evidence: the two constructors in `src/jarvis/read_composition.py`.

resolved when shared read-family construction has one owner while exact catalog
order, client ownership, binding identities, and dispatched requests are preserved.
coordinate with direct role construction so this does not preserve an otherwise
obsolete catalog just to deduplicate it.
