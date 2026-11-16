# adr 0074: private native socket publication

status: accepted implementation correction under the owner's slice 4 authorization,
2026-11-15; candidate qualification pending. production remains unchanged.

this supersedes the affected socket publication of adrs 0065/0072 and SPEC 7.5
for [slice 4](../private-notes-and-rolodex.md). its native capabilities require
stock's supported execution boundary. it changes neither the configured endpoint
nor application/host identities, grants, callback protocol or effect recovery.

## evidence

the first real candidate main could not see native shell tools because the host
still set `CODEX_EXEC_SERVER_URL=none`. removing that legacy disabling setting
exposed shell, but stock then rejected the physical socket directory's `0710`
mode. no requested file or git effect ran; both turns retained honest canonical
configuration waits. an actual isolated compactor still passed after enabling
the host execution environment.

the next native probe exposed the host's `ProcSubset=pid` restriction: bubblewrap
could not read `/proc/sys/kernel/overflowuid`. installed bubblewrap reads that
and `overflowgid` before parsing even `--help`, so stock reported no usable
launcher despite the required executable and flags being present. the same
unprivileged no-new-privileges command passed outside the filtered host mount
namespace, with ordinary proc visibility; that control alone does not qualify
the corrected service namespace.

stock `rust-v0.160.0` requires its reserved `/tmp/codex-daemon-UID` directory to
remain owner-only `0700` on every preparation ([directory guard](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/uds/src/daemon_directory.rs)).
its linux sandbox masks that directory and aliases of its ancestors, and rejects
direct directory/socket bind aliases ([mount checks](https://github.com/openai/codex/blob/rust-v0.160.0/codex-rs/linux-sandbox/src/daemon_mounts.rs)).
the old direct bind and group-traversable physical directory cannot support
native execution. a public hardlink would bypass the mask and expose privileged
control to native commands; it is unsuitable even though linux can connect
through a socket hardlink.

## decision

keep the configured public endpoint at `/run/jarvis-contained/app-server.sock`.
its global path is an inert regular placeholder. the host owns a private `exec`
child of that runtime root, bound as the ancestor `/tmp` inside its namespace.
stock's reserved daemon child stays `0700`; the one selected socket is `0660`
for the existing client group. the host's private relative alias resolves to that
socket under `exec` in both the host and service-manager namespaces.

systemd binds only that socket onto the public placeholder inside the application
namespace. native commands see the placeholder and stock-masked private aliases.
the application gets the existing one-socket grant. the native host uses ordinary
proc visibility so its unprivileged sandbox can read live kernel metadata.
`ProtectKernelTunables=true` retains read-only kernel settings and
`ProtectProc=ptraceable` retains process hiding. the application keeps
`ProcSubset=pid`. retain account instruction
masks, root-only application secrets, distinct uids, non-dumpability, private
temporary files, no-new-privileges and empty capabilities. no proxy, copied
credential, public control hardlink, extra listener or privileged publisher.

the host owns its disposable runtime paths; cleanup never touches the persistent
checkout. application verification checks the socket's identity/modes and performs
the actual provider handshake. filesystem access alone does not prove attachment;
the temporary linux read-only socket bind allowed both a write-access check and
the real handshake while its global placeholder remained inert.

## lifecycle and cost

the file bind pins an inode. the application orders after and binds its lifetime
to the native host with systemd `After` and `BindsTo`. host loss stops application
admission through its existing graceful shutdown and entered-effect settlement.
after host repair/replacement, the operator starts the application with a fresh
namespace and socket bind. add no automatic application start or new supervisor.
stopped paired release replacement already owns this operation.

this adds a coordinated restart requirement and may leave jarvis unavailable
until repair. the trusted native domain can also read additional kernel/system
metadata; it gains no kernel-setting write grant. sessions remain disposable;
canonical requests, original callback
receipts and effect recovery survive. final v2 cutover must install the same
qualified host/application release and mapping together. candidate proof must
show application connection, native socket masking, real shell/git, isolated
containment, host-loss stop and fresh remount before production acceptance.
