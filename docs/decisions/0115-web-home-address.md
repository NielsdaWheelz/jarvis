# adr 0115. keep the web home at the bare domain

**accepted and implemented in source.**

the previous shell rewrote `jarvis.nielseriknandal.com` to
`/overview` or to a published revision. the owner wants the bare domain to
mean “open jarvis.” a link to something specific still needs to work on
another device. the installed phone journey used both an alert for an exact
reply and a citation to page six of a pdf. this amends the home address rules
in [0087](0087-private-web-home.md#authored-canvas) and
[0097](0097-todo-home.md#c-shell). [phone evidence](0105-native-android.md#installed-phone-follow-up-on-november-24-utc)

## navigation contract

| owner action | address and result |
| --- | --- |
| open the bare domain in a fresh tab, or choose the jarvis wordmark | show `/`. read the selected home once. show its exact published revision, or todos if the service reports no selection. a failed read offers retry. |
| choose todos, including from a custom home | show the todo list at `/`. the header and sidebar both call it “todos.” an existing `/overview` link opens this same list after sign-in and replaces its own history entry with `/`. |
| open or close conversation over a canvas | keep the canvas address. preserve the existing phone back gesture, which closes the panel before leaving the canvas. |
| open a message, todo, file or published page | use `/m/{id}`, `/t/{id}`, `/f/{id}` with optional one-based `?page=N`, or `/v/{slug}/{rev}`. an explicit latest link at `/v/{slug}` still resolves once to its pinned url. the same rules apply when the requesting tab presents a result. |

each browser history entry remembers its canvas. opening a copied `/` in a
fresh tab shows the home selected at that time. reloading the original tab restores
its chosen todos or pinned publication. changing home or publishing a newer
revision leaves that reader in place. withdrawing the pinned page shows the
existing unavailable message there. when a publication is displayed at
`/`, make its displayed title a link to the exact revision so it can still
be opened or copied directly.

back and forward restore the entry even when adjacent entries both say `/`.
returning from a todo restores the list page, disclosure, scroll anchor and
focused row under 0097. opening chat keeps the tab's draft. a cold message
or todo link opens its target independently of the background home read.
closing a cold detail shows that home at `/`. closing a detail opened inside
jarvis restores the canvas and address it opened over, including todos at `/`
while a publication is home, or a file at its page-specific address.

## implementation boundary

the packaged [web shell](../../src/jarvis/static/home/home.js) owns this
change. reuse its history state to distinguish a revision displayed at home
from an explicit visit to the same revision. initialize from the url on fresh
entry and from saved state on reload or history traversal. use the resolved
canvas for todo refresh, errors and focus restoration. retain the navigation-version check
so a delayed home response cannot undo a later choice. wire both
[todos controls](../../src/jarvis/static/home/index.html) to the same
operation. keep the shell handler for inbound `/overview`. a server redirect
to `/` would lose the instruction to open todos.

delivery updates the packaged shell. existing tabs running the previous
shell adopt the change on reload. stored links, api paths, publication refs
and database records keep their formats. the installed android app continues
to handle the same app links, including `/overview` for todos and pinned
custom tabs for publications. [native navigation](0105-native-android.md#a-identity-and-navigation)

## browser acceptance

1. open `/` with no selected publication. on a phone-sized viewport open
   chat, type a draft and go back. open a todo from an expanded list, reload
   its detail, then use back and forward. check the addresses, draft, list
   position and focused row.
2. select publication a as home. open `/`, choose todos, then go back and
   forward through the two `/` entries. go back to a. republish a while its original
   revision is open. reload that tab and open the copied bare address in a
   fresh tab. the first shows the original revision, the second the new one.
   open the original tab's title link separately and verify its revision.
   withdraw a and check the unavailable message in both readers.
3. with a custom home selected, open a saved `/overview` link through sign-in.
   it lands on todos at `/`. back must not revisit `/overview` as an extra
   jarvis entry. open an old reply link and follow a page-six citation in a
   fresh tab. check the exact
   reply and page. delay the home read while choosing todos or opening a
   detail. the later choice wins.
