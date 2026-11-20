const $ = (id) => document.getElementById(id);
const el = (tag, text, cls) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
};
function button(label, click) {
  const node = el("button", label);
  node.type = "button";
  node.addEventListener("click", click);
  return node;
}
function link(label, path, cls) {
  const node = el("a", label, cls);
  node.href = path;
  return node;
}
function objectPath(ref) {
  switch (ref.kind) {
    case "view":
      return "/v/" + ref.slug + "/" + ref.rev;
    case "file":
      return "/f/" + ref.id + (ref.page ? "?page=" + ref.page : "");
    case "decision":
      return "/d/" + ref.type + "/" + ref.id;
    case "todo":
      return "/t/" + ref.id;
  }
}
function label(ref) {
  return ref.kind === "view" ? ref.slug : ref.kind + (ref.page ? " · page " + ref.page : "");
}
const mobile = matchMedia("(max-width:720px)");
const draftKey = "jarvis.home.draft";
const readingKey = "jarvis.home.reading";
let reloadReading = null;
if (performance.getEntriesByType("navigation")[0]?.type === "reload")
  reloadReading = JSON.parse(sessionStorage.getItem(readingKey) || "null");
sessionStorage.removeItem(readingKey);
const newDraft = () => ({ id: null, text: "", ref: null, files: [], uncertain: false });
let draft = JSON.parse(sessionStorage.getItem(draftKey) || "null") || newDraft();
let tab = "chat",
  armed = null,
  pendingSend = false,
  lastRead = null;
let current = null,
  displayed = "",
  routeVersion = 0,
  sectionVersion = 0,
  polling = false;
let latest = null,
  earliest = null,
  initialized = false,
  selectedMessage = null;
let sectionPage = 1,
  sectionContent = "";
const presentations = new Map();
const time = (at) =>
  new Date(at).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
const save = () => sessionStorage.setItem(draftKey, JSON.stringify(draft));

function setPanel() {
  document.body.dataset.panel = history.state?.panel ? "open" : "closed";
}
function openSidebar() {
  if (mobile.matches && !history.state?.panel) {
    history.pushState({ panel: true, drawer: true }, "", location.href);
    setPanel();
    $("sidebar-close").focus();
  }
}
function closeSidebar() {
  if (history.state?.drawer) history.back();
  else {
    history.replaceState(null, "", location.href);
    setPanel();
    $("sidebar-open").focus();
  }
}
$("sidebar-open").onclick = openSidebar;
$("sidebar-close").onclick = closeSidebar;
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && mobile.matches && history.state?.panel) closeSidebar();
});
function chooseTab(name) {
  if (name !== tab) {
    sectionPage = 1;
    sectionContent = "";
    sectionVersion++;
  }
  tab = name;
  $("chat").hidden = tab !== "chat";
  $("records").hidden = tab === "chat";
  for (const control of document.querySelectorAll("[data-tab]"))
    control.setAttribute("aria-pressed", String(control.dataset.tab === name));
}
for (const control of document.querySelectorAll("[data-tab]"))
  control.onclick = () => {
    armed = null;
    chooseTab(control.dataset.tab);
    refresh();
  };

function updateComposer() {
  $("message").value = draft.text;
  $("message").readOnly = draft.uncertain;
  $("context").replaceChildren();
  $("context").hidden = !draft.ref;
  if (draft.ref) {
    const remove = button("remove reference", () => {
      draft.ref = null;
      save();
      updateComposer();
    });
    remove.disabled = draft.uncertain;
    $("context").append(label(draft.ref), remove);
  }
  $("file-list").textContent = draft.files.map((f) => f.name).join(" · ");
  $("send").textContent = draft.uncertain ? "retry send" : "send";
  $("send").disabled = pendingSend || (!draft.text.trim() && !draft.files.length);
}
$("message").oninput = () => {
  draft.text = $("message").value;
  save();
  $("send").disabled = pendingSend || (!draft.text.trim() && !draft.files.length);
};
$("files").onchange = () => {
  if (!draft.uncertain) {
    draft.files = Array.from($("files").files, (f) => ({ name: f.name, size: f.size }));
    save();
  }
  updateComposer();
};
function discuss(ref) {
  if (draft.uncertain) {
    $("receipt").textContent = "recover the previous submission first.";
  } else {
    draft.ref = ref;
    save();
    updateComposer();
  }
  armed = null;
  chooseTab("chat");
  openSidebar();
  $("message").focus();
}
async function request(path, options = {}) {
  const response = await fetch(path, { redirect: "manual", cache: "no-store", ...options });
  if (response.type === "opaqueredirect" || [401, 403].includes(response.status))
    throw Object.assign(new Error("sign in to continue."), { login: true });
  if (response.status >= 500) throw new Error("jarvis is offline.");
  return response;
}
async function read(path) {
  const response = await request(path);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("could not load this item.");
  return response.json();
}
function failure(error) {
  const node = $("connection");
  node.hidden = false;
  const when = lastRead ? " last checked " + time(lastRead) + "." : "";
  node.replaceChildren(
    error.login ? "sign in to continue. " : "jarvis is offline. your draft is here." + when,
  );
  node.append(
    button(error.login ? "sign in" : "retry", error.login ? () => location.reload() : refresh),
  );
}
function accepted(id, submission) {
  if (draft.id !== submission) return;
  if (armed?.submission === submission) armed.request = id;
  draft = newDraft();
  save();
  $("files").value = "";
  updateComposer();
  $("receipt").textContent = "received";
  present();
}
async function recover() {
  if (!draft.uncertain) return false;
  const id = draft.id;
  const receipt = await read("/api/submissions/" + id);
  if (receipt) accepted(receipt.id, id);
  else $("receipt").textContent = "delivery unconfirmed. retry the same message.";
  return Boolean(receipt);
}
$("composer").onsubmit = async (e) => {
  e.preventDefault();
  if (pendingSend) return;
  pendingSend = true;
  updateComposer();
  if (!draft.uncertain) {
    draft.id = crypto.randomUUID();
    save();
  }
  const id = draft.id;
  try {
    if (draft.uncertain && (await recover())) return;
    const files = Array.from($("files").files);
    if (
      JSON.stringify(files.map((f) => ({ name: f.name, size: f.size }))) !==
      JSON.stringify(draft.files)
    ) {
      $("receipt").textContent = "reselect the original files to retry.";
      return;
    }
    const message = JSON.stringify({ text: draft.text, ref: draft.ref });
    const options = { method: "PUT" };
    if (files.length) {
      const form = new FormData();
      form.append("message", message);
      for (const file of files) form.append("file", file);
      options.body = form;
    } else {
      options.headers = { "Content-Type": "application/json" };
      options.body = message;
    }
    if (!draft.uncertain) armed = { submission: id, request: null };
    draft.uncertain = true;
    save();
    updateComposer();
    $("receipt").textContent = "sending…";
    const response = await request("/api/messages/" + id, options);
    if (response.ok) accepted((await response.json()).id, id);
    else {
      if (response.status === 409) {
        $("receipt").textContent = "this submission was already used. review the conversation.";
        armed = null;
        draft.uncertain = false;
        draft.id = null;
        save();
      } else if ([400, 413, 422].includes(response.status)) {
        draft.uncertain = false;
        save();
        armed = null;
        $("receipt").textContent =
          response.status === 400
            ? "use the private home address to send."
            : response.status === 413
              ? "message or files are too large."
              : "check the message, files and reference.";
      } else throw new Error("submission unavailable");
    }
  } catch (error) {
    $("receipt").textContent = "checking whether your message arrived…";
    failure(error);
  } finally {
    pendingSend = false;
    updateComposer();
    refresh();
  }
};
$("message").onkeydown = (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !$("send").disabled)
    $("composer").requestSubmit();
};

function linkDestination(text, start) {
  let href = "";
  let depth = 0;
  for (let i = start; i < text.length; i++) {
    const c = text[i];
    if (/[\s<>]/.test(c)) break;
    if (c === ")" && depth === 0) return { href, end: i + 1 };
    if (c === "\\" && /[()\\]/.test(text[i + 1] || "")) {
      i++;
      href += text[i];
      continue;
    }
    if (c === "(") depth++;
    if (c === ")") depth--;
    href += c;
  }
  return null;
}

function prose(text) {
  const p = el("p", undefined, "prose");
  // Recognise links without interpreting the rest of a message as markup.
  const pattern =
    /\[([^\]\n]+)\]\((?=https?:\/\/|\/[mdftv]\/)|attachment:([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})|(?:https?:\/\/|\/[mdftv]\/)[^\s<>]+/gi;
  let end = 0;
  for (let match; (match = pattern.exec(text)); ) {
    const [token, label, attachment] = match;
    let tail = "";
    let href;
    if (label) {
      const destination = linkDestination(text, pattern.lastIndex);
      if (!destination) continue;
      href = destination.href;
      pattern.lastIndex = destination.end;
    } else if (attachment) {
      href = "/f/" + attachment;
    } else {
      href = token;
      tail = /[.,;:!?'"\]}]+$/.exec(href)?.[0] || "";
      href = href.slice(0, href.length - tail.length);
      if (href.endsWith(")") && href.split(")").length > href.split("(").length) {
        href = href.slice(0, -1);
        tail = ")" + tail;
      }
    }
    const a = link(label || (attachment ? "original file" : href), href);
    if (a.origin !== location.origin) {
      a.target = "_blank";
      a.rel = "noopener noreferrer";
    }
    p.append(text.slice(end, match.index), a, tail);
    end = pattern.lastIndex;
  }
  p.append(text.slice(end));
  return p;
}
const fileState = {
  pending: "saving original",
  ready: "open original",
  deleted: "original deleted",
  deleting: "deleting original",
  failed: "original unavailable",
};
function renderMessage(m) {
  const node = el("article");
  node.id = "msg-" + m.id;
  const stamp = el("div", undefined, "stamp");
  stamp.append(el("strong", m.role === "owner" ? "you" : "jarvis"), el("time", time(m.at)));
  node.append(stamp, prose(m.text));
  for (const f of m.files || [])
    node.append(
      link(
        (f.name || "unnamed file") +
          " · " +
          (f.unavailable ? "original unavailable" : fileState[f.state] || "unavailable"),
        "/f/" + f.id,
        "file",
      ),
    );
  if (m.ref) node.append(link("discussed · " + label(m.ref), objectPath(m.ref), "result"));
  if (m.present)
    node.append(link("open " + label(m.present.ref), objectPath(m.present.ref), "result"));
  node.dataset.version = JSON.stringify(m);
  return node;
}
function selectedMessageOffset() {
  const node = $("msg-" + selectedMessage);
  return node.getBoundingClientRect().top - $("chat").getBoundingClientRect().top;
}
function merge(items) {
  const chat = $("chat"),
    list = $("messages");
  const pinned = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 48;
  const top = chat.getBoundingClientRect().top;
  const anchor =
    !pinned && Array.from(list.children).find((node) => node.getBoundingClientRect().bottom > top);
  const previousTop = anchor ? anchor.getBoundingClientRect().top : null;
  for (const m of items) {
    const existing = $("msg-" + m.id);
    if (m.present) presentations.set(m.present.request_id, m.present.ref);
    if (existing?.dataset.version === JSON.stringify(m)) continue;
    const node = renderMessage(m);
    const fraction = (m.at.match(/\.(\d+)/)?.[1] || "").padEnd(6, "0");
    // Date's millisecond precision alone loses the order of simultaneous writes.
    node.dataset.order = new Date(m.at).toISOString().slice(0, 19) + fraction + m.id;
    if (existing) {
      existing.replaceWith(node);
      continue;
    }
    let lo = 0,
      hi = list.children.length;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2);
      if (list.children[mid].dataset.order < node.dataset.order) lo = mid + 1;
      else hi = mid;
    }
    list.insertBefore(node, list.children[lo] || null);
  }
  if (anchor && previousTop !== null) {
    const replacement = document.getElementById(anchor.id);
    if (replacement) chat.scrollTop += replacement.getBoundingClientRect().top - previousTop;
  } else if (pinned && !selectedMessage) chat.scrollTop = chat.scrollHeight;
}
async function messages() {
  let data = await read("/api/messages");
  const chunks = [data.items];
  while (
    latest &&
    data.items.length &&
    !data.items.some((m) => m.id === latest) &&
    data.next_before
  ) {
    data = await read("/api/messages?before=" + encodeURIComponent(data.next_before));
    chunks.push(data.items);
  }
  // The direct read may have a shorter scroll range until surrounding messages arrive.
  let openingOffset = null;
  if (!initialized) {
    if (selectedMessage) {
      openingOffset = selectedMessageOffset();
      if (reloadReading?.id === selectedMessage && reloadReading.appliedOffset === openingOffset)
        openingOffset = reloadReading.offset;
    }
    earliest = data.next_before;
    initialized = true;
  }
  const rows = chunks.reverse().flat();
  merge(rows);
  if (rows.length) latest = rows.at(-1).id;
  $("older").hidden = !earliest;
  if (openingOffset !== null) {
    $("chat").scrollTop += selectedMessageOffset() - openingOffset;
    reloadReading = null;
  }
}
$("older").onclick = async () => {
  const b = $("older");
  b.disabled = true;
  try {
    const data = await read("/api/messages?before=" + encodeURIComponent(earliest));
    earliest = data.next_before;
    merge(data.items);
    b.hidden = !earliest;
  } catch (error) {
    failure(error);
  } finally {
    b.disabled = false;
  }
};
function present() {
  if (!armed?.request) return;
  const ref = presentations.get(armed.request);
  if (ref) navigate(objectPath(ref));
}
function navigate(path, panel = false) {
  armed = null;
  history.pushState(panel ? { panel: true } : null, "", path);
  setPanel();
  renderRoute().catch(failure);
}
document.addEventListener("click", (e) => {
  const a = e.target.closest("a");
  if (
    !a ||
    a.target ||
    e.defaultPrevented ||
    e.metaKey ||
    e.ctrlKey ||
    e.shiftKey ||
    e.altKey ||
    e.button !== 0
  )
    return;
  if (a.origin === location.origin && /^\/(?:$|[dmftv]\/)/.test(a.pathname)) {
    e.preventDefault();
    navigate(a.pathname + a.search, /^\/[dmt]\//.test(a.pathname));
  }
});
window.onpopstate = () => {
  armed = null;
  setPanel();
  renderRoute().catch(failure);
};

function empty(title, action) {
  const box = el("div", undefined, "empty");
  box.append(el("h1", title, "display"));
  if (action) box.append(action);
  return box;
}
async function renderRoute({ refreshing = false } = {}) {
  const ver = ++routeVersion,
    [, kind, key, more] = location.pathname.split("/");
  const same = () => ver === routeVersion;
  const marker = location.pathname + location.search;
  if (kind === "m" && (!refreshing || selectedMessage !== key)) {
    chooseTab("chat");
    const m = await read("/api/messages/" + key);
    if (!same()) return;
    if (mobile.matches && !history.state?.drawer) history.replaceState({ panel: true }, "");
    setPanel();
    if (m) {
      selectedMessage = m.id;
      const old = $("msg-" + m.id);
      if (!old) merge([m]);
      document.querySelector(".selected")?.classList.remove("selected");
      const node = $("msg-" + m.id);
      node.classList.add("selected");
      const restore = reloadReading?.id === m.id && reloadReading.appliedOffset === undefined;
      $("chat").scrollTop += selectedMessageOffset() - (restore ? reloadReading.offset : 0);
      if (restore && !initialized) reloadReading.appliedOffset = selectedMessageOffset();
      else reloadReading = null;
    } else $("receipt").textContent = "this message is no longer available.";
  } else if (kind !== "m") selectedMessage = null;
  if (kind === "d" || kind === "t") {
    chooseTab(kind === "d" ? "decisions" : "todos");
    if (mobile.matches && !history.state?.drawer) history.replaceState({ panel: true }, "");
    setPanel();
    await records();
  }
  if (["d", "m", "t"].includes(kind) && current) return;
  let ref = null;
  if (kind === "v") {
    ref = await read(
      "/api/views/" + encodeURIComponent(key) + (more ? "/" + encodeURIComponent(more) : ""),
    );
    if (!same()) return;
  } else if (kind === "f") {
    const n = Number(new URLSearchParams(location.search).get("page"));
    ref = { kind: "file", id: key, ...(Number.isSafeInteger(n) && n > 0 ? { page: n } : {}) };
  } else {
    const home = await read("/api/home");
    if (!same()) return;
    ref = home.view;
  }
  if (ref && ((kind === "v" && !more) || !kind))
    history.replaceState(history.state, "", objectPath(ref));
  if (!ref) {
    displayed = marker;
    current = null;
    $("location").textContent = "";
    $("object-tools").hidden = true;
    $("canvas").replaceChildren(
      kind === "v"
        ? empty("this page is no longer available.")
        : empty(
            "nothing published yet",
            button("open chat", () => {
              chooseTab("chat");
              openSidebar();
              $("message").focus();
            }),
          ),
    );
    return;
  }
  let type = null,
    name = null,
    fileUrl = null,
    fileState = null;
  if (ref.kind === "file") {
    fileUrl = "/api/files/" + ref.id;
    const resp = await request(fileUrl, { method: "HEAD" });
    if (!same()) return;
    if (!resp.ok)
      fileState =
        resp.status === 410
          ? "original deleted"
          : resp.status === 409
            ? resp.headers.get("X-Jarvis-File-State") === "Pending"
              ? "saving original"
              : "original unavailable"
            : "original not found";
    type = resp.headers.get("content-type")?.split(";")[0];
    const disposition = resp.headers.get("content-disposition") || "";
    const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
    name = encoded ? decodeURIComponent(encoded[1]) : /filename="([^"]+)"/i.exec(disposition)?.[1];
    if (!disposition.startsWith("inline")) type = null;
  }
  const identity = objectPath(ref) + (fileState || "");
  if (displayed === identity) return;
  current = ref;
  displayed = identity;
  $("canvas").replaceChildren();
  $("object-tools").replaceChildren();
  $("location").textContent = name || label(ref);
  if (ref.kind === "view" || type === "application/pdf") {
    const frame = el("iframe");
    frame.title = name || label(ref);
    if (ref.kind === "view") {
      frame.setAttribute("sandbox", "allow-scripts");
      frame.src = "/content/" + ref.slug + "/" + ref.rev;
    } else frame.src = fileUrl + (ref.page ? "#page=" + ref.page : "");
    $("canvas").append(frame);
  } else if (type?.startsWith("image/")) {
    const img = el("img");
    img.alt = name || "original image";
    img.src = fileUrl;
    $("canvas").append(img);
  } else $("canvas").append(empty(fileState || name || "original file"));
  $("object-tools").hidden = Boolean(fileState);
  if (fileUrl && !fileState) {
    const open = link(
      type === "application/pdf" ? "open to print" : "open original",
      fileUrl + (ref.page ? "#page=" + ref.page : ""),
    );
    open.target = "_blank";
    open.rel = "noopener";
    $("object-tools").append(open);
    const download = link("download", fileUrl);
    download.download = name || "";
    $("object-tools").append(download);
  }
  if (type === "application/pdf") {
    const page = el("input");
    page.type = "number";
    page.min = "1";
    page.placeholder = "page";
    page.setAttribute("aria-label", "pdf page");
    page.value = ref.page || "";
    page.onchange = () => {
      if (page.value && page.validity.valid) navigate("/f/" + ref.id + "?page=" + page.value);
    };
    $("object-tools").append(page);
  }
  $("object-tools").append(button("discuss this", () => discuss(current)));
}

async function records() {
  if (tab === "chat") return;
  const ver = ++sectionVersion,
    name = tab,
    [, kind, key, more] = location.pathname.split("/");
  const detail = (name === "decisions" && kind === "d") || (name === "todos" && kind === "t");
  let items = [],
    item = null,
    next = null,
    asOf = null;
  if (detail) {
    const result = await read("/api/" + name + "/" + key + (more ? "/" + more : ""));
    item = name === "todos" ? result?.record : result;
    asOf = result?.as_of;
  } else {
    let path = "/api/" + name;
    for (let i = 0; i < sectionPage; i++) {
      const page = await read(path);
      items.push(...page.items);
      asOf = page.as_of;
      next =
        name === "todos"
          ? items.length < page.total
            ? "?offset=" + items.length
            : null
          : page.next_before
            ? "?before=" + encodeURIComponent(page.next_before)
            : null;
      if (!next) break;
      path = "/api/" + name + next;
    }
  }
  if (ver !== sectionVersion || tab !== name) return;
  const version = JSON.stringify([name, location.pathname, item, items, next]);
  if (version === sectionContent) {
    if (asOf && $("as-of")) $("as-of").textContent = "as of " + time(asOf);
    return;
  }
  sectionContent = version;
  const pane = $("records");
  pane.replaceChildren();
  if (asOf) {
    const stamp = el("small", "as of " + time(asOf), "secondary");
    stamp.id = "as-of";
    pane.append(stamp);
  }
  if (detail) {
    pane.append(
      button("all " + name, () => {
        history.pushState({ panel: true }, "", current ? objectPath(current) : "/");
        sectionContent = "";
        records().catch(failure);
      }),
    );
    if (!item) {
      pane.append(prose("this item is no longer available."));
      return;
    }
    const ref =
      name === "todos"
        ? { kind: "todo", id: item.id }
        : { kind: "decision", id: item.id, type: item.kind };
    pane.append(
      el("h2", item.title),
      el("small", (item.state || item.status).replaceAll("_", " ")),
      prose(item.content || item.detail || ""),
    );
    if (item.origin_message_id)
      pane.append(link("open conversation", "/m/" + item.origin_message_id, "result"));
    pane.append(button("discuss this", () => discuss(ref)));
    return;
  }
  for (const obj of items) {
    const a = link(
      obj.kind === "question" ? obj.detail : obj.title,
      name === "todos" ? "/t/" + obj.id : "/d/" + obj.kind + "/" + obj.id,
      "record",
    );
    a.append(el("small", (obj.state || obj.status).replaceAll("_", " ")));
    pane.append(a);
  }
  if (!items.length)
    pane.append(el("p", name === "todos" ? "no active todos." : "no open decisions.", "secondary"));
  if (next)
    pane.append(
      button("show more", () => {
        sectionPage++;
        records().catch(failure);
      }),
    );
}
async function refresh() {
  if (polling || document.hidden) return;
  polling = true;
  try {
    if (!pendingSend && draft.uncertain) await recover();
    await messages();
    await records();
    const path = location.pathname;
    if (
      path.startsWith("/v/") ||
      (path.startsWith("/f/") && $("object-tools").hidden) ||
      !displayed
    )
      await renderRoute({ refreshing: true });
    if (current?.kind === "view" && !path.startsWith("/v/")) {
      const pinned = current;
      const available = await read("/api/views/" + pinned.slug + "/" + pinned.rev);
      if (!available && current === pinned) {
        current = null;
        displayed = "withdrawn";
        $("location").textContent = "";
        $("object-tools").hidden = true;
        $("canvas").replaceChildren(empty("this page is no longer available."));
      }
    }
    present();
    lastRead = Date.now();
    $("connection").hidden = true;
  } catch (error) {
    failure(error);
  } finally {
    polling = false;
  }
}
updateComposer();
setPanel();
renderRoute().catch(failure).finally(refresh);
window.addEventListener("pagehide", () => {
  if (selectedMessage && location.pathname === "/m/" + selectedMessage && $("chat").clientHeight) {
    const offset = selectedMessageOffset();
    sessionStorage.setItem(readingKey, JSON.stringify({ id: selectedMessage, offset }));
  }
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
window.addEventListener("online", refresh);
setInterval(refresh, 3000);
