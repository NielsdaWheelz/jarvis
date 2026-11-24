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
    case "proposal":
      return "/m/" + ref.message_id;
    case "todo":
      return "/t/" + ref.id;
  }
}
function label(ref) {
  return ref.kind === "view" ? ref.slug : ref.kind + (ref.page ? " · page " + ref.page : "");
}
const mobile = matchMedia("(max-width:720px)");
const draftKey = "jarvis.home.draft";
let reloadReading = null;
const newDraft = () => ({ id: null, text: "", ref: null, files: [], uncertain: false });
let draft = JSON.parse(sessionStorage.getItem(draftKey) || "null") || newDraft();
let armed = null,
  pendingSend = false,
  fileProblem = "",
  lastRead = null;
let current = null,
  displayed = "",
  routeVersion = 0,
  overviewPage = null,
  restoreOverview = false;
let latest = null,
  earliest = null,
  initialized = false,
  selectedMessage = null;
const inFlight = new Map();
const failures = new Map();
const presentations = new Map();
const time = (at, zone) =>
  new Date(at).toLocaleString([], {
    month: "short",
    day: "numeric",
    year: zone ? "numeric" : undefined,
    hour: "numeric",
    minute: "2-digit",
    timeZone: zone,
    timeZoneName: zone ? "short" : undefined,
  });
const save = () => sessionStorage.setItem(draftKey, JSON.stringify(draft));

function changeState(values, path = location.href) {
  history.replaceState({ ...history.state, ...values }, "", path);
}
function setPanel() {
  const open = Boolean(history.state?.panel);
  document.body.dataset.panel = open ? "open" : "closed";
  $("sidebar-open").setAttribute("aria-expanded", String(open));
  const todo = location.pathname.startsWith("/t/") && !history.state?.chat;
  $("chat").hidden = todo;
  $("records").hidden = !todo;
  $("chat-tab").setAttribute("aria-pressed", String(!todo));
}
function openSidebar() {
  armed = null;
  if (mobile.matches && !history.state?.panel) {
    rememberOverview();
    history.pushState({ ...history.state, panel: true, fromCanvas: true }, "", location.href);
  }
  changeState({ chat: true });
  setPanel();
}
function closeSidebar() {
  armed = null;
  if (history.state?.fromCanvas) history.back();
  else {
    changeState({ panel: false, chat: false }, history.state?.canvas || "/");
    startRoute();
  }
}
$("sidebar-open").onclick = () => {
  openSidebar();
  $("sidebar-close").focus();
};
$("sidebar-close").onclick = closeSidebar;
$("chat-tab").onclick = openSidebar;
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && mobile.matches && history.state?.panel) closeSidebar();
});
function updateComposer() {
  $("message").value = draft.text;
  $("message").readOnly = pendingSend || draft.uncertain;
  $("files").disabled = pendingSend;
  $("context").replaceChildren();
  $("context").hidden = !draft.ref;
  if (draft.ref) {
    const remove = button("remove reference", () => {
      draft.ref = null;
      delete draft.refLabel;
      save();
      updateComposer();
    });
    remove.disabled = pendingSend || draft.uncertain;
    $("context").append(draft.refLabel || label(draft.ref), remove);
  }
  $("file-list").textContent = [draft.files.map((f) => f.name).join(" · "), fileProblem]
    .filter(Boolean)
    .join(" · ");
  const oldUpload = draft.uncertain && draft.files.some((f) => !f.sha256);
  $("send").textContent = draft.uncertain ? "retry send" : "send";
  $("send").disabled = pendingSend || oldUpload || (!draft.text.trim() && !draft.files.length);
}
$("message").oninput = () => {
  draft.text = $("message").value;
  save();
  $("send").disabled = pendingSend || (!draft.text.trim() && !draft.files.length);
};
$("files").onchange = () => {
  fileProblem = "";
  if (!draft.uncertain) {
    draft.files = Array.from($("files").files, (f) => ({ name: f.name, size: f.size }));
    save();
  }
  updateComposer();
};
function discuss(ref, title) {
  openSidebar();
  const choice = $("draft-choice");
  choice.hidden = true;
  if (pendingSend || draft.uncertain) {
    $("receipt").textContent = "recover the previous submission first.";
    refresh();
    return;
  }
  const use = () => {
    draft.ref = ref;
    draft.refLabel = title || label(ref);
    save();
    updateComposer();
    choice.hidden = true;
    $("message").focus();
  };
  if (
    !draft.ref ||
    (objectPath(draft.ref) === objectPath(ref) && draft.ref.action_id === ref.action_id)
  )
    return use();
  const keep = button("keep draft", () => {
    choice.hidden = true;
    $("message").focus();
  });
  choice.replaceChildren(
    "change the reference to " + (title || label(ref)) + "? ",
    keep,
    button("use this item", use),
  );
  choice.hidden = false;
  keep.focus();
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
function failure(error, part = "chat") {
  failures.set(part, Boolean(error.login));
  showConnection();
}
function showConnection() {
  const node = $("connection");
  node.hidden = failures.size === 0;
  if (node.hidden) return;
  const login = Array.from(failures.values()).includes(true);
  const when = lastRead ? " last checked " + time(lastRead) + "." : "";
  const message = login ? "sign in to continue. " : "jarvis is offline. your draft is here." + when;
  if (node.firstChild?.textContent === message) return;
  node.replaceChildren(
    message,
    button(login ? "sign in" : "retry", login ? () => location.reload() : refresh),
  );
}
function accepted(id, submission) {
  if (draft.id !== submission) return;
  failures.delete("receipt");
  showConnection();
  if (armed?.submission === submission) armed.request = id;
  draft = newDraft();
  fileProblem = "";
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
  if (!draft.uncertain || draft.id !== id) return true;
  if (receipt) accepted(receipt.id, id);
  else
    $("receipt").textContent = draft.files.some((f) => !f.sha256)
      ? "delivery unconfirmed. this earlier upload has no file digest. checking for its receipt."
      : "delivery unconfirmed. retry the same message.";
  return Boolean(receipt);
}
$("composer").onsubmit = async (e) => {
  e.preventDefault();
  if (pendingSend) return;
  pendingSend = true;
  $("draft-choice").hidden = true;
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
      files.length !== draft.files.length ||
      files.some(
        (file, i) => file.name !== draft.files[i].name || file.size !== draft.files[i].size,
      )
    ) {
      fileProblem = "reselect the original files to retry.";
      return;
    }
    // Bound local hashing before allocating file buffers. The server also checks the encoded body.
    if (files.length > 10 || files.reduce((bytes, f) => bytes + f.size, 0) > 90 * 1024 * 1024) {
      fileProblem = "message or files are too large.";
      return;
    }
    if (!draft.uncertain) armed = { submission: id, request: null };
    for (const [i, file] of files.entries()) {
      let digest;
      try {
        digest = new Uint8Array(await crypto.subtle.digest("SHA-256", await file.arrayBuffer()));
      } catch {
        fileProblem = "couldn’t read the file. select it again.";
        return;
      }
      const sha256 = Array.from(digest, (b) => b.toString(16).padStart(2, "0")).join("");
      if (draft.uncertain && draft.files[i].sha256 !== sha256) {
        fileProblem = "the selected bytes differ. reselect the original files to retry.";
        return;
      }
      draft.files[i].sha256 = sha256;
    }
    fileProblem = "";
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
    failure(error, "receipt");
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
    /\[([^\]\n]+)\]\((?=https?:\/\/|\/[mftv]\/)|attachment:([0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12})|(?:https?:\/\/|\/[mftv]\/)[^\s<>]+/gi;
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
  if (m.ref) {
    const path = objectPath(m.ref);
    node.append(
      path
        ? link("discussed · " + label(m.ref), path, "result")
        : el("small", "discussed · " + label(m.ref)),
    );
  }
  for (const proposal of m.proposals || []) {
    const group = el("section", undefined, "proposal");
    group.append(
      el("strong", proposal.title),
      proposal.read_email ? el("p", proposal.detail, "prose") : prose(proposal.detail),
      el("p", proposal.status_label || proposal.status.replaceAll("_", " "), "secondary"),
    );
    if (proposal.read_email) {
      const disclosure = el("details");
      const body = el("p", "", "prose");
      let loading = false;
      let loaded = false;
      disclosure.append(el("summary", "read email"), body);
      disclosure.addEventListener("toggle", async () => {
        if (!disclosure.open || loading || loaded) return;
        loading = true;
        try {
          const entry = (await read("/api/messages/" + m.id + "?mail_body=true"))
            ?.proposals.find((item) => item.action_id === proposal.action_id);
          if (typeof entry?.mail_body !== "string") throw new Error("email body unavailable.");
          body.textContent = entry.mail_body || "empty email body";
          loaded = true;
        } catch (error) {
          body.textContent = error.message;
        } finally {
          loading = false;
        }
      });
      group.append(disclosure);
    }
    if (proposal.decision)
      group.append(
        link("owner reply · " + proposal.decision, "/m/" + proposal.owner_message_id, "result"),
      );
    const reply = button("reply", () =>
      discuss(
        { kind: "proposal", message_id: m.id, action_id: proposal.action_id },
        proposal.title,
      ),
    );
    reply.dataset.action = proposal.action_id;
    group.append(reply);
    node.append(group);
  }
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
    if (m.id === selectedMessage) node.classList.add("selected");
    const fraction = (m.at.match(/\.(\d+)/)?.[1] || "").padEnd(6, "0");
    // Date's millisecond precision alone loses the order of simultaneous writes.
    node.dataset.order = new Date(m.at).toISOString().slice(0, 19) + fraction + m.id;
    if (existing) {
      const focused = existing.contains(document.activeElement) ? document.activeElement : null;
      existing.replaceWith(node);
      if (focused?.dataset.action)
        node
          .querySelector('[data-action="' + focused.dataset.action + '"]')
          ?.focus({ preventScroll: true });
      else if (focused?.href)
        Array.from(node.querySelectorAll("a"))
          .find((a) => a.href === focused.href)
          ?.focus({ preventScroll: true });
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
async function messages(ver) {
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
  if (ver !== routeVersion) return;
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
function rememberReading() {
  if (selectedMessage && location.pathname === "/m/" + selectedMessage && $("chat").clientHeight)
    changeState({ reading: { id: selectedMessage, offset: selectedMessageOffset() } });
}
$("chat").addEventListener("scrollend", rememberReading);
function navigate(path, origin) {
  rememberOverview(origin);
  rememberReading();
  armed = null;
  const detail = /^\/[mt]\//.test(path);
  const fromCanvas = !history.state?.panel && !/^\/[mt]\//.test(location.pathname);
  const state = detail
    ? { ...history.state, panel: true, chat: false, fromCanvas, reading: null }
    : {};
  history.pushState(state, "", path);
  startRoute();
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
  if (a.origin === location.origin && /^\/(?:$|overview$|[mftv]\/)/.test(a.pathname)) {
    e.preventDefault();
    navigate(a.pathname + a.search, a);
  }
});
window.onpopstate = () => {
  armed = null;
  startRoute();
};

function empty(title) {
  const box = el("div", undefined, "empty");
  box.append(el("h1", title, "display"));
  return box;
}

function startRoute() {
  routeVersion++;
  failures.delete("canvas");
  failures.delete("detail");
  showConnection();
  reloadReading = history.state?.reading;
  const path = location.pathname + location.search;
  const detail = /^\/[mt]\//.test(path);
  if (detail && history.state?.panel === undefined) changeState({ panel: true });
  changeState({ canvas: detail ? history.state?.canvas || "/" : path });
  $("draft-choice").hidden = true;
  selectedMessage = null;
  document.querySelector(".selected")?.classList.remove("selected");
  if (detail && document.activeElement === $("message")) $("message").blur();
  if (location.pathname.startsWith("/t/") && $("records").dataset.item !== path) {
    $("records").replaceChildren();
    delete $("records").dataset.version;
    $("records").dataset.item = path;
  }
  restoreOverview = !detail && !history.state.panel;
  setPanel();
  refresh();
}

async function canvasRead(ver) {
  const same = () => ver === routeVersion;
  let path = history.state.canvas;
  let ref;
  if (path === "/") {
    const home = await read("/api/home");
    if (!same()) return;
    ref = home.view;
    path = ref ? objectPath(ref) : "/overview";
    changeState({ canvas: path }, location.pathname === "/" ? path : location.href);
  }
  const overview = path === "/overview";
  $("overview").hidden = !overview;
  $("object").hidden = overview;
  if (overview) {
    if (displayed !== path) {
      current = null;
      displayed = path;
      $("location").textContent = "";
      $("object").replaceChildren();
      $("object-tools").hidden = true;
    }
    const page = await read("/api/todos?offset=" + (history.state.offset || 0));
    if (!same()) return;
    renderOverview(page);
    return;
  }
  const url = new URL(path, location.origin);
  const [, kind, key, more] = url.pathname.split("/");
  if (kind === "v") {
    if (!ref)
      ref = await read(
        "/api/views/" + encodeURIComponent(key) + (more ? "/" + encodeURIComponent(more) : ""),
      );
    if (!same()) return;
    if (!ref) {
      current = null;
      if (displayed !== "withdrawn:" + path)
        $("object").replaceChildren(empty("this page is no longer available."));
      displayed = "withdrawn:" + path;
      $("location").textContent = "";
      $("object-tools").hidden = true;
      return;
    }
    if (!more)
      changeState(
        { canvas: objectPath(ref) },
        location.pathname === url.pathname ? objectPath(ref) : location.href,
      );
  } else {
    const n = Number(url.searchParams.get("page"));
    ref = { kind: "file", id: key, ...(Number.isSafeInteger(n) && n > 0 ? { page: n } : {}) };
    if (displayed === objectPath(ref) && !$("object-tools").hidden) return;
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
  $("object").replaceChildren();
  $("object-tools").replaceChildren();
  $("location").textContent = name || label(ref);
  if (ref.kind === "view" || type === "application/pdf") {
    const frame = el("iframe");
    frame.title = name || label(ref);
    if (ref.kind === "view") {
      frame.setAttribute("sandbox", "allow-scripts");
      frame.src = "/content/" + ref.slug + "/" + ref.rev;
    } else frame.src = fileUrl + (ref.page ? "#page=" + ref.page : "");
    $("object").append(frame);
  } else if (type?.startsWith("image/")) {
    const img = el("img");
    img.alt = name || "original image";
    img.src = fileUrl;
    $("object").append(img);
  } else $("object").append(empty(fileState || name || "original file"));
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

const disclosure = button("show more", () => {
  changeState({ expanded: !history.state.expanded });
  renderOverview(overviewPage);
});

function civilDate(value) {
  return new Date(value + "T12:00:00Z")
    .toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    })
    .toLowerCase();
}

function overviewPosition() {
  const links = [...$("todo-list").querySelectorAll("a")];
  const top = $("canvas").getBoundingClientRect().top;
  const first = links.find((a) => a.getBoundingClientRect().bottom > top);
  return {
    scroll: $("canvas").scrollTop,
    anchor: first?.dataset.id,
    inset: first ? first.getBoundingClientRect().top - top : 0,
    focus: document.activeElement.closest("#todo-list a")?.dataset.id,
    order: links.map((a) => a.dataset.id),
  };
}
function rememberOverview(origin) {
  if (
    !restoreOverview &&
    location.pathname === "/overview" &&
    !history.state?.panel &&
    displayed === "/overview"
  ) {
    const position = overviewPosition();
    if (origin?.matches?.("#todo-list a")) position.focus = origin.dataset.id;
    changeState({ position });
  }
}
$("canvas").addEventListener("scrollend", rememberOverview);
$("todo-list").addEventListener("focusin", rememberOverview);
function restorePosition(position, rows) {
  const closest = (id) => {
    if (!id) return null;
    if (rows.has(id)) return rows.get(id);
    const i = position.order.indexOf(id);
    for (let n = 1; n < position.order.length; n++) {
      const neighbor = rows.get(position.order[i + n]) || rows.get(position.order[i - n]);
      if (neighbor) return neighbor;
    }
    return null;
  };
  const anchor = closest(position.anchor);
  if (anchor && position.scroll > 0) {
    $("canvas").scrollTop +=
      anchor.getBoundingClientRect().top - $("canvas").getBoundingClientRect().top - position.inset;
  } else $("canvas").scrollTop = position.scroll;
  const focus = closest(position.focus);
  if (focus && document.activeElement !== focus) focus.focus({ preventScroll: true });
  else if (position.focus && !focus)
    $("overview").querySelector("h1").focus({ preventScroll: true });
}

function renderOverview(page) {
  const list = $("todo-list");
  const position = restoreOverview ? history.state.position : overviewPosition();
  overviewPage = page;
  if (history.state.offset !== page.offset) changeState({ offset: page.offset });
  $("todo-error").hidden = true;
  $("todo-empty").hidden = page.total !== 0;
  $("checked").textContent = "checked " + time(page.as_of, page.timezone).toLowerCase();
  $("todo-pages").hidden = page.total <= 50;
  $("page-number").textContent =
    page.offset + 1 + "–" + (page.offset + page.items.length) + " of " + page.total;
  $("previous-page").disabled = page.offset === 0;
  $("next-page").disabled = page.offset + page.items.length >= page.total;

  const backlog = page.items.filter((item) => item.section === "backlog");
  // A row moved into the collapsed tail still belongs to the active reader.
  if (!page.offset && backlog.slice(2).some((item) => item.id === position?.focus))
    changeState({ expanded: true });
  const expanded = Boolean(page.offset || history.state.expanded);
  const existing = new Map([...list.children].map((node) => [node.dataset.key, node]));
  const rows = new Map();
  const children = [];
  let group,
    backlogIndex = 0;
  for (const item of page.items) {
    if (item.section !== group) {
      group = item.section;
      const heading = existing.get(group) || el("h2");
      heading.dataset.key = group;
      heading.textContent =
        group === "backlog"
          ? page.backlog_remaining === page.total
            ? page.total + " in backlog"
            : page.backlog_remaining + " remaining backlog"
          : group.replaceAll("_", " ");
      children.push(heading);
    }
    if (group === "backlog") backlogIndex++;
    if (group === "backlog" && !page.offset && backlogIndex === 3) {
      disclosure.setAttribute("aria-expanded", String(expanded));
      disclosure.textContent = expanded ? "show less" : "show more";
      children.push(disclosure);
    }
    if (!expanded && backlogIndex > 2) continue;
    const a = existing.get(item.id) || link("", "/t/" + item.id, "todo-row");
    a.dataset.key = a.dataset.id = item.id;
    if (!a.children.length) a.append(el("span"), el("small"));
    a.classList.toggle("lead", item === page.items[0]);
    if (a.firstChild.textContent !== item.title) a.firstChild.textContent = item.title;
    const state = item.state.replaceAll("_", " ");
    let date = "";
    if (item.due_date) {
      const when =
        item.due_date < page.today ? "overdue" : item.due_date === page.today ? "due today" : "due";
      date = when + " · " + civilDate(item.due_date);
    }
    const caption = [date, group !== item.state ? state : ""].filter(Boolean).join(" · ");
    if (a.lastChild.textContent !== caption) a.lastChild.textContent = caption;
    a.lastChild.hidden = !caption;
    rows.set(item.id, a);
    children.push(a);
  }
  for (let i = 0; i < children.length; i++)
    if (list.children[i] !== children[i]) list.insertBefore(children[i], list.children[i] || null);
  while (list.children.length > children.length) list.lastChild.remove();
  if (!history.state.panel && location.pathname === "/overview") {
    if (position) restorePosition(position, rows);
    else if (restoreOverview) {
      $("canvas").scrollTop = 0;
      if ($("todo-pages").contains(document.activeElement))
        (rows.values().next().value || $("overview").querySelector("h1")).focus({
          preventScroll: true,
        });
    }
  }
  restoreOverview = false;
}
function changePage(offset) {
  changeState({ offset, expanded: false, position: null });
  restoreOverview = true;
  routeVersion++;
  refresh();
}
$("previous-page").onclick = () => changePage(Math.max(0, overviewPage.offset - 50));
$("next-page").onclick = () => changePage(overviewPage.offset + 50);

async function detailRead(ver) {
  const [, kind, id] = location.pathname.split("/");
  if (kind === "t" && !$("records").hidden) {
    const data = await read("/api/todos/" + id);
    if (ver !== routeVersion || $("records").hidden) return;
    const pane = $("records");
    const item = data?.record;
    const wake = item?.wake_at
      ? (Date.parse(item.wake_at) <= Date.parse(data.as_of)
          ? "jarvis check was due "
          : "jarvis check scheduled for ") + time(item.wake_at, data.timezone).toLowerCase()
      : "";
    const version = JSON.stringify([item, wake]);
    if (pane.dataset.version === version) return;
    const focus = pane.contains(document.activeElement),
      scroll = pane.scrollTop;
    pane.dataset.version = version;
    if (!item) {
      pane.replaceChildren(prose("this item is no longer available."));
      return;
    }
    const title = el("h2", item.title);
    title.tabIndex = -1;
    const reply = button("discuss", () => discuss({ kind: "todo", id: item.id }, item.title));
    const hadReply = pane.querySelector("button") === document.activeElement;
    pane.replaceChildren(
      title,
      el("small", item.state.replaceAll("_", " ")),
      prose(item.content || ""),
    );
    if (item.due_date) pane.append(el("p", "due · " + civilDate(item.due_date)));
    if (wake) pane.append(el("p", wake));
    pane.append(reply);
    pane.scrollTop = scroll;
    if (focus || (document.activeElement === document.body && history.state.panel))
      (hadReply ? reply : title).focus({ preventScroll: true });
  } else if (kind === "m") {
    const m = await read("/api/messages/" + id);
    if (ver !== routeVersion) return;
    if (!m) {
      $("receipt").textContent = "this message is no longer available.";
      return;
    }
    merge([m]);
    if (selectedMessage === id) return;
    selectedMessage = id;
    const node = $("msg-" + id);
    node.classList.add("selected");
    const restore = reloadReading?.id === id && reloadReading.appliedOffset === undefined;
    $("chat").scrollTop += selectedMessageOffset() - (restore ? reloadReading.offset : 0);
    if (restore && !initialized) reloadReading.appliedOffset = selectedMessageOffset();
    else reloadReading = null;
  }
}

async function poll(part, load) {
  const ver = routeVersion;
  if (inFlight.get(part) === ver) return;
  inFlight.set(part, ver);
  try {
    await load(ver);
    if (ver !== routeVersion) return;
    failures.delete(part);
    showConnection();
    if (part === "chat") {
      present();
      lastRead = Date.now();
    }
  } catch (error) {
    if (ver !== routeVersion) return;
    if (part === "canvas" && history.state.canvas === "/overview") {
      const node = $("todo-error");
      if (node.hidden || node.dataset.login !== String(Boolean(error.login))) {
        node.replaceChildren(
          error.login ? "sign in to check your todos. " : "couldn’t check your todos. ",
          button(
            error.login ? "sign in" : "retry",
            error.login ? () => location.reload() : refresh,
          ),
        );
        node.dataset.login = String(Boolean(error.login));
      }
      node.hidden = false;
    } else failure(error, part);
  } finally {
    if (inFlight.get(part) === ver) inFlight.delete(part);
  }
}
function refresh() {
  if (document.hidden) return;
  poll("canvas", canvasRead);
  poll("detail", detailRead);
  poll("chat", messages);
  if (!pendingSend && draft.uncertain) poll("receipt", recover);
}
updateComposer();
startRoute();
window.addEventListener("pagehide", () => {
  rememberOverview();
  rememberReading();
});
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) refresh();
});
window.addEventListener("online", refresh);
setInterval(refresh, 3000);
