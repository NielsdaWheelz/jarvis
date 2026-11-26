import { el, button, link } from "./home-dom.js";
import { draftPreview, openEditor } from "./mail-editor.js";
const $ = (id) => document.getElementById(id);
function creationPath(messageId, created) {
  const kind = created.editable === true ? "draft" : "revision";
  return "/mail/" + messageId + "/" + kind + "/" + created.create_action_id;
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
const todosCanvas = "todos";
let reloadReading = null;
let chatReturn = null;
const newDraft = () => ({ id: null, text: "", ref: null, files: [], uncertain: false });
let draft = JSON.parse(sessionStorage.getItem(draftKey) || "null") || newDraft();
let armed = null,
  pendingSend = false,
  checkingReceipt = false,
  receiptMissing = false,
  staging = 0,
  reselect = null,
  lastRead = null;
let current = null,
  displayed = "",
  routeVersion = 0,
  overviewPage = null,
  restoreOverview = false,
  revealTodo = null;
const todoRows = new Map();
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
function save() {
  const files = draft.files.map(({ name, size, sha256 }) => ({ name, size, sha256 }));
  sessionStorage.setItem(draftKey, JSON.stringify({ ...draft, files }));
}
const isDetail = (path) => path.startsWith("/m/");
const mailId = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const mailRoute = new RegExp("^/mail/(" + mailId + ")/(revision|draft)/(" + mailId + ")$");
let mailEditor = null;
let shownIndex = history.state?.entryIndex ?? 0;
let undoingTraversal = false;
function pushEntry(state, path) {
  history.pushState({ ...state, entryIndex: ++shownIndex }, "", path);
}
function mayLeaveEditor(canvas) {
  return !mailEditor?.dirty() || canvas === mailEditor.path ||
    window.confirm("leave this draft? changes that gmail has not confirmed may be lost.");
}

function replaceEntry(state, path) {
  history.replaceState({ ...state, entryIndex: shownIndex }, "", path);
}
function changeState(values, path = location.href) {
  replaceEntry({ ...history.state, ...values }, path);
}
function setPanel() {
  const open = Boolean(history.state?.panel);
  document.body.dataset.panel = open ? "open" : "closed";
  $("sidebar-open").setAttribute("aria-expanded", String(open));
  $("sidebar-close").hidden = !open || (!mobile.matches && !isDetail(location.pathname));
}
mobile.addEventListener("change", setPanel);
function openSidebar(origin) {
  armed = null;
  if (mobile.matches && !history.state?.panel) {
    rememberOverview(origin);
    changeState({ panelOpener: origin?.id || null, chatReturn: null });
    pushEntry({ ...history.state, panel: true, fromCanvas: true }, location.href);
  }
  setPanel();
}
function closeSidebar() {
  armed = null;
  if (history.state.fromCanvas) {
    history.back();
    return;
  }
  replaceEntry({ canvasSelection: history.state.canvasSelection }, "/");
  startRoute(shownIndex);
}
$("sidebar-open").onclick = () => {
  openSidebar($("sidebar-open"));
  $("sidebar-close").focus({ preventScroll: true });
};
$("sidebar-close").onclick = closeSidebar;

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  clearDrag();
  if (mobile.matches && history.state?.panel) closeSidebar();
});
function oldUpload() {
  return draft.uncertain && draft.files.some((entry) => !entry.sha256);
}
function canStage() {
  return !pendingSend && !checkingReceipt && (!draft.uncertain || (receiptMissing && !oldUpload()));
}
function updateComposer() {
  if ($("message").value !== draft.text) $("message").value = draft.text;
  const editable = !pendingSend && !draft.uncertain;
  $("message").readOnly = !editable;
  $("files").disabled = !canStage();
  $("context").hidden = !draft.ref;
  $("ref-label").textContent = draft.ref ? draft.refLabel || label(draft.ref) : "";
  $("remove-ref").disabled = !editable;
  for (const control of $("file-list").querySelectorAll("button")) {
    control.hidden = draft.uncertain;
    control.disabled = !editable || Boolean(staging);
  }
  const missing = draft.files.some((entry) => !entry.file);
  $("uncertain-help").hidden = !draft.uncertain || pendingSend || (!missing && !oldUpload());
  $("send").textContent = draft.uncertain ? "retry send" : "send";
  $("send").disabled =
    !canStage() || Boolean(staging) || missing || (!draft.text.trim() && !draft.files.length);
}
$("remove-ref").onclick = () => {
  draft.ref = null;
  delete draft.refLabel;
  save();
  updateComposer();
};
function showFiles() {
  const rows = draft.files.map((entry, index) => {
    const row = el("div", undefined, "draft-file");
    if (entry.preview) row.append(entry.preview);
    row.append(el("span", entry.name + (entry.file ? "" : " · needs original file")));
    if (!entry.file) {
      const choose = button("reselect", () => {
        reselect = entry;
        $("files").multiple = false;
        $("files").click();
      });
      choose.setAttribute("aria-label", "reselect " + entry.name);
      row.append(choose);
    }
    const remove = button("remove", () => {
      draft.files.splice(index, 1);
      $("file-problem").textContent = "";
      save();
      showFiles();
      const next = $("file-list").children[index] || $("file-list").lastChild;
      (next?.lastChild || $("files")).focus();
    });
    remove.setAttribute("aria-label", "remove " + entry.name);
    row.append(remove);
    return row;
  });
  $("file-list").replaceChildren(...rows);
  updateComposer();
}
const rasterType = /^image\/(png|jpeg|gif|webp|bmp|avif)$/i;
async function attachBytes(entry, file) {
  entry.file = file;
  if (!rasterType.test(file.type)) return;
  let bitmap;
  try {
    bitmap = await createImageBitmap(file);
    if (entry.file !== file || !draft.files.includes(entry)) return;
    const canvas = el("canvas");
    const scale = Math.min(1, 80 / Math.max(bitmap.width, bitmap.height));
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    canvas.setAttribute("aria-hidden", "true");
    entry.preview = canvas;
    $("file-list").children[draft.files.indexOf(entry)]?.prepend(canvas);
  } catch {
    // The filename remains usable when this browser cannot decode a thumbnail.
  } finally {
    bitmap?.close();
  }
}
function fileName(file) {
  if (file.name) return file.name;
  const image = rasterType.exec(file.type);
  return image ? "pasted image." + image[1].toLowerCase() : "pasted file";
}
async function digest(file) {
  try {
    const bytes = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
    return Array.from(new Uint8Array(bytes), (b) => b.toString(16).padStart(2, "0")).join("");
  } catch {
    throw new Error("couldn’t read " + fileName(file) + ". choose its original again.");
  }
}
async function restoreFiles(files, missing) {
  const matches = [];
  for (const file of files) {
    const candidates = missing.filter((entry) => entry.size === file.size);
    const hash = candidates.some((entry) => entry.sha256) ? await digest(file) : null;
    const match = candidates.find((entry) =>
      entry.sha256 ? entry.sha256 === hash : entry.name === fileName(file)
    );
    if (!match) throw new Error(fileName(file) + " does not match a missing original file.");
    missing.splice(missing.indexOf(match), 1);
    matches.push(match);
  }
  matches.forEach((entry, i) => attachBytes(entry, files[i]));
}
let additions = Promise.resolve();
function stage(files, target = null) {
  if (!files.length || !canStage()) return;
  staging++;
  updateComposer();
  // A later gesture must see the slots filled by an earlier digest check.
  additions = additions.then(async () => {
    try {
      $("file-problem").textContent = "";
      if (draft.uncertain || target) {
        await restoreFiles(files, target ? [target] : draft.files.filter((entry) => !entry.file));
      } else {
        if (draft.files.length + files.length > 10)
          throw new Error("a message can have at most 10 files.");
        const bytes = [...draft.files, ...files].reduce((total, file) => total + file.size, 0);
        if (bytes + new TextEncoder().encode(draft.text).length > 90 * 1024 * 1024)
          throw new Error("the message and files exceed 90 mib.");
        for (const file of files) {
          const entry = { name: fileName(file), size: file.size };
          draft.files.push(entry);
          attachBytes(entry, file);
        }
        save();
      }
      showFiles();
    } catch (error) {
      $("file-problem").textContent = error.message;
    } finally {
      staging--;
      updateComposer();
    }
  });
}
$("message").oninput = () => {
  draft.text = $("message").value;
  save();
  updateComposer();
};
function resetPicker() {
  reselect = null;
  $("files").value = "";
  $("files").multiple = true;
}
$("files").onchange = () => {
  stage(Array.from($("files").files), reselect);
  resetPicker();
};
$("files").oncancel = resetPicker;
function stageTransfer(e, data) {
  if (!data) return;
  const files = Array.from(data.files);
  if (!files.length) {
    for (const item of data.items || [])
      if (item.kind === "file") files.push(item.getAsFile());
  }
  if (!files.length && !data.types.includes("Files")) return;
  e.preventDefault();
  if (!files.length || files.includes(null)) {
    $("file-problem").textContent = "couldn’t read the files. choose them with attach.";
    return;
  }
  stage(files);
}
$("message").onpaste = (e) => stageTransfer(e, e.clipboardData);
let dragDepth = 0;
function clearDrag() {
  dragDepth = 0;
  $("composer").classList.remove("dragging");
}
function fileDrag(e) {
  return e.dataTransfer?.types.includes("Files");
}
$("composer").ondragenter = (e) => {
  if (!fileDrag(e)) return;
  e.preventDefault();
  dragDepth++;
  $("composer").classList.toggle("dragging", canStage());
};
$("composer").ondragover = (e) => {
  if (!fileDrag(e)) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = canStage() ? "copy" : "none";
};
$("composer").ondragleave = () => {
  if (--dragDepth <= 0) clearDrag();
};
$("composer").ondrop = (e) => {
  clearDrag();
  stageTransfer(e, e.dataTransfer);
};
window.addEventListener("dragend", clearDrag);
window.addEventListener("blur", clearDrag);
function discuss(ref, title, origin) {
  openSidebar(origin);
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
  $("file-problem").textContent = "";
  receiptMissing = false;
  save();
  resetPicker();
  showFiles();
  $("receipt").textContent = "received";
  present();
}
async function recover() {
  if (!draft.uncertain) return false;
  const id = draft.id;
  checkingReceipt = true;
  updateComposer();
  try {
    const receipt = await read("/api/submissions/" + id);
    if (!draft.uncertain || draft.id !== id) return true;
    if (receipt) accepted(receipt.id, id);
    else {
      receiptMissing = true;
      $("receipt").textContent = oldUpload()
        ? "delivery unconfirmed. this earlier upload has no file digest. checking for its receipt."
        : "delivery unconfirmed. retry the same message.";
    }
    return Boolean(receipt);
  } finally {
    checkingReceipt = false;
    updateComposer();
  }
}
$("composer").onsubmit = async (e) => {
  e.preventDefault();
  if ($("send").disabled) return;
  pendingSend = true;
  $("draft-choice").hidden = true;
  $("file-problem").textContent = "";
  updateComposer();
  const retry = draft.uncertain;
  if (!retry) draft.id = crypto.randomUUID();
  const id = draft.id;
  try {
    if (retry && (await recover())) return;
    if (new TextEncoder().encode(draft.text).length > 16 * 1024) {
      $("file-problem").textContent = "the caption exceeds 16 kib. shorten it to send.";
      return;
    }
    const message = JSON.stringify({ text: draft.text, ref: draft.ref });
    const options = { method: "PUT" };
    if (draft.files.length) {
      const form = new FormData();
      form.append("message", message);
      for (const entry of draft.files) {
        try {
          const hash = await digest(entry.file);
          if (retry && hash !== entry.sha256)
            throw new Error(entry.name + " has changed. choose its original again.");
          entry.sha256 = hash;
        } catch (error) {
          delete entry.file;
          delete entry.preview;
          $("file-problem").textContent = error.message;
          showFiles();
          return;
        }
        form.append("file", entry.file, entry.name);
      }
      options.body = form;
    } else {
      options.headers = { "Content-Type": "application/json" };
      options.body = message;
    }
    if (!retry) armed = { submission: id, request: null };
    receiptMissing = false;
    draft.uncertain = true;
    save();
    updateComposer();
    $("receipt").textContent = "sending…";
    const response = await request("/api/messages/" + id, options);
    if (response.ok) accepted((await response.json()).id, id);
    else if (response.status === 409) {
      $("receipt").textContent = "this submission was already used. review the conversation.";
      armed = null;
      draft.uncertain = false;
      draft.id = null;
      save();
    } else if ([400, 413, 422].includes(response.status)) {
      // A rejected retry says nothing about the first attempt.
      draft.uncertain = retry;
      save();
      if (!retry) armed = null;
      const problem = response.status === 400 ? "use the private home address to send."
        : response.status === 413 ? "message or files are too large."
        : "check the message, files and reference.";
      $("file-problem").textContent = problem;
      $("receipt").textContent = retry ? "checking whether the earlier message arrived…" : "";
    } else throw new Error("submission unavailable");
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
  if (e.key !== "Enter" || e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
  // Some IMEs report keyCode 229 even after isComposing clears.
  if (e.isComposing || e.keyCode === 229) return;
  e.preventDefault();
  if (!e.repeat) $("send").click();
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
function draftRevisionLink(messageId, actionId) {
  return link(
    "open draft revision",
    "/mail/" + messageId + "/revision/" + actionId,
    "result draft-revision-link",
  );
}
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
      proposal.draft_revision_id ? el("p", proposal.detail, "prose") : prose(proposal.detail),
      el("p", proposal.status_label || proposal.status.replaceAll("_", " "), "secondary"),
    );
    if (proposal.draft_revision_id) {
      const revision = draftRevisionLink(m.id, proposal.draft_revision_id);
      revision.setAttribute("aria-label", "open draft revision · " + proposal.title);
      group.append(revision);
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
  if (m.draft_revision_error === "integrity")
    node.append(el("p", "draft revision failed integrity checks.", "draft-evidence"));
  if (m.draft_revision_id && !m.drafts?.some(d => d.editable !== true && d.create_action_id === m.draft_revision_id)) {
    const revision = draftRevisionLink(m.id, m.draft_revision_id);
    revision.classList.add("draft-evidence");
    node.append(revision);
  }
  for (const [i, created] of (m.drafts || []).entries()) {
    const subject = created.subject || "(no subject)";
    const numbered = m.drafts.filter((other) => other.subject === created.subject).length > 1;
    const action = created.editable === true ? "open draft" : "open draft revision";
    const ordinal = m.drafts.slice(0, i + 1).filter(other => other.subject === created.subject).length;
    const name = action + " · " + subject + (numbered ? " · " + ordinal : "");
    node.append(link(name, creationPath(m.id, created), "result draft-revision-link"));
  }
  if (m.present && m.present.ref.kind !== "draft")
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
    if (m.present) {
      const {ref, request_id} = m.present;
      if (ref.kind === "draft") {
        const created = m.drafts?.find(d => d.request_id === request_id &&
          ref.request_id === request_id && d.create_action_id === ref.create_action_id);
        if (created) presentations.set(request_id, creationPath(m.id, created));
        else presentations.delete(request_id);
      } else presentations.set(request_id, objectPath(ref));
    }
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
  const returning = !isDetail(location.pathname) && chatReturn;
  if (
    returning && !$("msg-" + returning.messageId) &&
    !rows.some((row) => row.id === returning.messageId)
  ) {
    const origin = await read("/api/messages/" + returning.messageId);
    if (ver !== routeVersion) return;
    if (origin) rows.unshift(origin);
    else chatReturn = null;
  }
  merge(rows);
  if (rows.length) latest = rows.at(-1).id;
  $("older").hidden = !earliest;
  if (openingOffset !== null) {
    $("chat").scrollTop += selectedMessageOffset() - openingOffset;
    reloadReading = null;
  }
  if (!isDetail(location.pathname)) restoreChatReturn();
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
  if (!armed?.request || document.hidden) return;
  const path = presentations.get(armed.request);
  if (path) navigate(path);
}
function rememberReading() {
  if (selectedMessage && location.pathname === "/m/" + selectedMessage && $("chat").clientHeight)
    changeState({ reading: { id: selectedMessage, offset: selectedMessageOffset() } });
}
$("chat").addEventListener("scrollend", rememberReading);
function restoreChatReturn() {
  const returning = chatReturn;
  if (!returning) return;
  const article = $("msg-" + returning.messageId);
  const chat = $("chat");
  if (!article || !chat.clientHeight) return;
  chatReturn = null;
  if (document.activeElement !== document.body && document.activeElement !== returning.focus) return;
  const offset = article.getBoundingClientRect().top - chat.getBoundingClientRect().top;
  chat.scrollTop += offset - returning.offset;
  const matches = [...article.querySelectorAll("a")].filter((link) => link.href === returning.href);
  matches[returning.occurrence]?.focus({ preventScroll: true });
}

function navigate(path, { origin, canvasSelection = path } = {}) {
  armed = null;
  if (undoingTraversal || !mayLeaveEditor(canvasSelection)) return;
  if (
    canvasSelection === todosCanvas &&
    location.pathname === "/" &&
    history.state.canvasSelection === todosCanvas &&
    !history.state.panel
  )
    return;
  rememberOverview(origin);
  rememberReading();
  const revision = mailRoute.exec(path);
  const fromRevision = mailRoute.test(location.pathname);
  const fromRevisionMessage = Boolean(
    revision && origin?.classList.contains("draft-revision-link") && !fromRevision,
  );
  const article = origin?.closest("#messages article");
  if (article || history.state.chatReturn) {
    changeState({
      chatReturn: article && {
        fromEntry: shownIndex + 1,
        messageId: article.id.slice(4),
        href: origin.href,
        occurrence: [...article.querySelectorAll("a")].filter((link) => link.href === origin.href).indexOf(origin),
        offset: article.getBoundingClientRect().top - $("chat").getBoundingClientRect().top,
      },
    });
  }
  let state = { canvasSelection, ...(fromRevisionMessage ? { fromRevisionMessage } : {}) };
  if (path.startsWith("/t/")) {
    state = { ...todoEntry(path.slice(3)), hasOrigin: true };
  } else if (isDetail(path)) {
    state = {
      ...(fromRevision ? { canvasSelection: "/" } : history.state),
      panel: true,
      fromCanvas: true,
      reading: null,
      chatReturn: null,
    };
  }
  pushEntry(state, path);
  startRoute();
}
function todoEntry(id) {
  return { canvasSelection: todosCanvas, todoTarget: id, openTodos: { [id]: [] } };
}
$("todos-tab").onclick = () => navigate("/", { canvasSelection: todosCanvas });
$("todo-return").onclick = () => {
  if (history.state.hasOrigin) history.back();
  else {
    replaceEntry({ canvasSelection: "/" }, "/");
    startRoute();
  }
};
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
  if (
    a.origin === location.origin &&
    (/^\/(?:$|overview$|[mftv]\/)/.test(a.pathname) || mailRoute.test(a.pathname))
  ) {
    e.preventDefault();
    navigate(a.pathname + a.search, { origin: a });
  }
});
window.onpopstate = () => {
  const destination = history.state?.entryIndex ?? 0;
  if (undoingTraversal && destination === shownIndex) {
    undoingTraversal = false;
    return;
  }
  if (destination !== shownIndex &&
      !mayLeaveEditor(history.state?.canvasSelection ?? location.pathname)) {
    // The address already moved. Restore the same history entry without replacing its editor.
    undoingTraversal = true;
    history.go(shownIndex - destination);
    return;
  }
  undoingTraversal = false;
  const previousEntry = shownIndex;
  shownIndex = destination;
  armed = null;
  startRoute(previousEntry);
};

function empty(title) {
  const box = el("div", undefined, "empty");
  box.append(el("h1", title, "display"));
  return box;
}

function startRoute(previousEntry) {
  const leavingPanel = previousEntry !== undefined && document.body.dataset.panel === "open" && !history.state?.panel;
  if (mailEditor && mailEditor.path !== history.state?.canvasSelection) {
    mailEditor.close();
    mailEditor = null;
  }
  routeVersion++;
  failures.delete("canvas");
  failures.delete("detail");
  showConnection();
  reloadReading = history.state?.reading;
  const path = location.pathname + location.search;
  const detail = isDetail(path);
  if (location.pathname === "/overview") {
    replaceEntry({ canvasSelection: todosCanvas }, "/");
  } else if (path.startsWith("/t/") && history.state?.todoTarget !== path.slice(3)) {
    replaceEntry(todoEntry(path.slice(3)), path);
  } else if (!history.state?.canvasSelection) {
    changeState(
      detail ? { canvasSelection: "/", panel: true } : { canvasSelection: path },
    );
  }
  const saved = history.state.chatReturn;
  chatReturn = saved && saved.fromEntry === previousEntry
    ? { ...saved, focus: document.activeElement } : null;
  $("draft-choice").hidden = true;
  selectedMessage = null;
  document.querySelector(".selected")?.classList.remove("selected");
  if ((detail || path.startsWith("/t/")) && document.activeElement === $("message")) $("message").blur();
  if (mailRoute.test(displayed) && !mailRoute.test(location.pathname)) {
    $("object").replaceChildren();
    displayed = "";
  }
  restoreOverview = Boolean(history.state.position && !detail && !history.state.panel);
  revealTodo = path.startsWith("/t/") && !history.state.targetRevealed ? path.slice(3) : null;
  const sameCanvas = leavingPanel && displayed === history.state.canvasSelection;
  if (!restoreOverview && !detail && !history.state.panel && !sameCanvas) $("canvas").scrollTop = 0;
  $("todo-return").hidden = !path.startsWith("/t/");
  setPanel();
  if (leavingPanel && !(chatReturn && $("chat").clientHeight) && !revealTodo && !history.state.position?.focus) {
    const opener = $(history.state.panelOpener);
    const homeControl = mobile.matches ? $("sidebar-open") : document.querySelector(".wordmark");
    (opener?.getClientRects().length ? opener : homeControl).focus({ preventScroll: true });
  }
  if (!detail) restoreChatReturn();
  refresh();
}

async function mailRead(ver, path, messageId, kind, actionId) {
  const editing = kind === "draft";
  let sheet = $("draft-revision");
  if (displayed !== path) {
    current = null;
    displayed = path;
    $("location").textContent = editing ? "draft" : "draft revision";
    $("object-tools").hidden = true;
    const back = link("back to message", "/m/" + messageId);
    back.addEventListener("click", (event) => {
      if (
        history.state.fromRevisionMessage &&
        event.button === 0 && !event.metaKey && !event.ctrlKey && !event.altKey && !event.shiftKey
      ) {
        event.preventDefault();
        history.back();
      }
    });
    const title = el("h1", editing ? "draft" : "draft revision");
    title.tabIndex = -1;
    sheet = el("section");
    sheet.id = "draft-revision";
    const content = el("div");
    const loading = el("p", "loading draft revision…");
    loading.setAttribute("role", "status");
    content.append(loading);
    sheet.append(back, title, content);
    $("object").replaceChildren(sheet);
    $("canvas").scrollTop = 0;
    title.focus({ preventScroll: true });
  }
  if (sheet.dataset.loaded) return;
  const revision = await read("/api/mail/" + messageId + "/revision/" + actionId);
  if (ver !== routeVersion) return;
  const content = sheet.lastElementChild;
  content.replaceChildren(draftPreview(revision, editing));
  if (editing) {
    if (revision?.status === "complete" && revision.editable === true)
      mailEditor = openEditor(content, path, revision, digest);
    else content.append(el("p", "this saved revision is read-only."));
  }
  sheet.dataset.loaded = "true";
}

async function canvasRead(ver) {
  const same = () => ver === routeVersion;
  let path = history.state.canvasSelection;
  let ref;
  if (path === "/") {
    const home = await read("/api/home");
    if (!same()) return;
    ref = home.view;
    path = ref ? objectPath(ref) : todosCanvas;
    changeState({ canvasSelection: path });
  }
  const overview = path === todosCanvas;
  $("todos-tab").setAttribute("aria-pressed", String(overview));
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
    if (mobile.matches && history.state.panel) return;
    renderOverview();
    const page = await read("/api/todos?all=true");
    if (!same()) return;
    const active = new Set(page?.items?.map((item) => item.id));
    if (!page || page.offset !== 0 || page.items.length !== page.total || active.size !== page.total)
      throw new Error("incomplete todo list");
    overviewPage = page;
    const open = { ...history.state.openTodos };
    for (const id of Object.keys(open))
      if (id !== history.state.todoTarget && !active.has(id)) delete open[id];
    if (Object.keys(open).length !== Object.keys(history.state.openTodos || {}).length)
      changeState({ openTodos: open });
    $("todo-error").hidden = true;
    renderOverview();
    refreshTodoRows(false);
    return;
  }
  const url = new URL(path, location.origin);
  const revision = mailRoute.exec(url.pathname);
  if (revision) {
    await mailRead(ver, url.pathname, revision[1], revision[2], revision[3]);
    return;
  }
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
    if (!more) {
      const pinned = objectPath(ref);
      if (isDetail(location.pathname)) {
        changeState({ canvasSelection: pinned });
      } else {
        changeState({ canvasSelection: pinned }, pinned);
      }
    }
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
  const canonical = objectPath(ref);
  const title = name || label(ref);
  const locationLabel = $("location");
  if (ref.kind === "view" && location.pathname === "/") {
    if (locationLabel.firstElementChild?.getAttribute("href") !== canonical)
      locationLabel.replaceChildren(link(title, canonical));
  } else if (locationLabel.firstElementChild || locationLabel.textContent !== title) {
    locationLabel.textContent = title;
  }
  const identity = canonical + (fileState || "");
  if (displayed === identity) return;
  current = ref;
  displayed = identity;
  $("object").replaceChildren();
  $("object-tools").replaceChildren();
  if (ref.kind === "view" || type === "application/pdf") {
    const frame = el("iframe");
    frame.title = title;
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
  const discussObject = button("discuss this", (event) => discuss(current, undefined, event.currentTarget));
  discussObject.id = "discuss-object";
  $("object-tools").append(discussObject);
}

function civilDate(value) {
  return new Date(value + "T12:00:00Z")
    .toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    })
    .toLowerCase();
}

function overviewPosition(origin = document.activeElement) {
  const rows = [...$("todo-list").querySelectorAll(".todo-row")];
  const top = $("canvas").getBoundingClientRect().top;
  const first = rows.find((node) => node.getBoundingClientRect().bottom > top);
  const focused = origin?.closest?.(".todo-row");
  const results = first?.querySelector(".todo-body:not([hidden]) .linked-results");
  const result = results && results.getBoundingClientRect().top <= top
    ? [...results.querySelectorAll("li")].find((li) => li.getBoundingClientRect().bottom > top)
    : null;
  return {
    scroll: $("canvas").scrollTop,
    anchor: first?.dataset.id,
    result: result?.querySelector("a").getAttribute("href"),
    resultInset: result && result.getBoundingClientRect().top - top,
    inset: first ? first.getBoundingClientRect().top - top : 0,
    focus: focused?.dataset.id,
    control: focused && (origin.getAttribute("href") || origin.dataset.control),
    order: rows.map((node) => node.dataset.id),
  };
}
function readingTodos() {
  return history.state?.canvasSelection === todosCanvas && !isDetail(location.pathname) &&
    !(mobile.matches && history.state.panel) && displayed === todosCanvas;
}
function rememberOverview(origin) {
  if (readingTodos() && !restoreOverview)
    changeState({ position: overviewPosition(origin instanceof Element ? origin : document.activeElement) });
}
$("canvas").addEventListener("scrollend", rememberOverview);
$("todo-list").addEventListener("focusin", (event) => rememberOverview(event.target));
for (const type of ["pointerdown", "wheel", "keydown"])
  document.addEventListener(type, () => {
    restoreOverview = false;
    chatReturn = null;
  }, { passive: true });

function restorePosition(position) {
  const closest = (id) => {
    if (!id) return null;
    if (todoRows.has(id)) return todoRows.get(id);
    const i = position.order.indexOf(id);
    for (let n = 1; n < position.order.length; n++) {
      const neighbor = todoRows.get(position.order[i + n]) || todoRows.get(position.order[i - n]);
      if (neighbor) return neighbor;
    }
    return null;
  };
  const anchor = closest(position.anchor);
  if (anchor && (position.scroll > 0 || position.anchor === history.state.todoTarget)) {
    const result = position.result && anchor.id === position.anchor && !anchor.body.hidden
      ? [...anchor.body.querySelectorAll(".linked-results a")].find((a) => a.getAttribute("href") === position.result)
      : null;
    const element = result?.closest("li") || anchor.node;
    const inset = result ? position.resultInset : position.inset;
    $("canvas").scrollTop += element.getBoundingClientRect().top - $("canvas").getBoundingClientRect().top - inset;
  } else $("canvas").scrollTop = position.scroll;
  if (position.focus) {
    const row = closest(position.focus);
    let control = row ? (row.summary.hidden ? row.node : row.summary) : $("overview").querySelector("h1");
    if (row?.id === position.focus && position.control && !row.body.hidden)
      control = [...row.body.querySelectorAll("a,button")].find((element) =>
        element.getAttribute("href") === position.control || element.dataset.control === position.control
      ) || control;
    if (control !== document.activeElement) control.focus({ preventScroll: true });
  }
}

function makeTodoRow(id) {
  const node = el("div", undefined, "todo-row");
  node.dataset.id = node.dataset.key = id;
  node.tabIndex = -1;
  const body = el("div", undefined, "todo-body");
  body.id = "todo-body-" + id;
  const summary = button("", () => {
    const open = { ...history.state.openTodos };
    if (Object.hasOwn(open, id)) delete open[id];
    else open[id] = [];
    row.pending = {};
    changeState({ openTodos: open });
    summary.focus({ preventScroll: true });
    renderOverview();
    if (Object.hasOwn(open, id)) {
      readTodoPart(row, "record", true);
      readTodoPart(row, "results", true);
    }
    rememberOverview();
  });
  summary.className = "todo-summary";
  summary.setAttribute("aria-controls", body.id);
  summary.append(el("span"), el("small"));
  node.append(summary, body);
  const row = { id, node, summary, body, pending: {}, checked: {}, errors: {}, cursors: [] };
  return row;
}

function renderTodoBody(row, open) {
  row.body.hidden = !open && row.record !== null;
  if (row.body.hidden) return;
  const record = row.record;
  const item = record?.record;
  const timezone = record?.timezone || overviewPage?.timezone || "UTC";
  const wake = item?.wake_at && (
    (Date.parse(item.wake_at) <= Date.parse(record.as_of) ? "jarvis check was due " : "jarvis check scheduled for ") +
    time(item.wake_at, record.timezone).toLowerCase()
  );
  const version = JSON.stringify([record === null, item, wake, timezone, row.results, row.cursors, row.errors]);
  if (row.version === version) return;
  row.version = version;
  const body = row.body;
  body.replaceChildren();
  if (record === null) {
    body.append(prose("this todo is no longer available."));
  }
  if (item) {
    if (item.content) body.append(prose(item.content));
    if (wake) body.append(el("p", wake));
    const discussTodo = button("discuss", (event) =>
      discuss({ kind: "todo", id: row.id }, item.title, event.currentTarget));
    discussTodo.dataset.control = "discuss";
    body.append(discussTodo, link("link to this todo", "/t/" + row.id));
  }
  const results = row.results;
  if (record !== null && results && (results.items.length || row.cursors.length)) {
    const section = el("section", undefined, "linked-results");
    section.append(el("h3", "results"));
    const list = el("ul");
    for (const result of results.items) {
      const li = el("li");
      li.append(link(result.label || "answer", "/m/" + result.message_id),
        el("time", time(result.at, timezone)));
      list.append(li);
    }
    section.append(list);
    const pageButton = (label, next) => {
      const control = button(label, () => {
        changeState({ openTodos: { ...history.state.openTodos, [row.id]: next } });
        readTodoPart(row, "results", true);
      });
      control.dataset.control = label;
      section.append(control);
    };
    if (row.cursors.length) pageButton("newer results", row.cursors.slice(0, -1));
    if (results.next_before) pageButton("earlier results", [...row.cursors, results.next_before]);
    body.append(section);
  }
  for (const [part, problem] of Object.entries(row.errors)) {
    if (record === null && part === "results") continue;
    const login = problem === "login";
    const status = el("p");
    const retry = button(login ? "sign in" : "retry", login
      ? () => location.reload() : () => readTodoPart(row, part, true));
    retry.dataset.control = "retry-" + part;
    status.append(login ? "sign in to check this todo. " :
      part === "record" ? "couldn’t check this todo. " : "couldn’t check results. ", retry);
    body.append(status);
  }
  if (record === undefined && !row.errors.record) body.prepend(el("p", "loading todo…"));
}

function renderOverview() {
  const page = overviewPage;
  const target = history.state.todoTarget;
  const open = history.state.openTodos || {};
  const list = $("todo-list");
  const position = readingTodos() && (restoreOverview ? history.state.position : overviewPosition());
  const existing = new Map([...list.children].map((node) => [node.dataset.key, node]));
  const children = [];
  const ids = new Set();
  const addRow = (id, item, group) => {
    let row = todoRows.get(id);
    if (!row) todoRows.set(id, row = makeTodoRow(id));
    ids.add(id);
    children.push(row.node);
    const record = row.record?.record;
    const summary = item || record;
    const title = summary?.title || "todo";
    const caption = [];
    if (summary?.due_date) {
      const closed = summary.state === "done" || summary.state === "cancelled";
      const when = closed ? "due" : summary.due_date < page?.today ? "overdue" :
        summary.due_date === page?.today ? "due today" : "due";
      caption.push(when + " · " + civilDate(summary.due_date));
    }
    if (summary?.state && summary.state !== group) caption.push(summary.state.replaceAll("_", " "));
    if (row.summary.firstChild.textContent !== title) row.summary.firstChild.textContent = title;
    const text = caption.join(" · ");
    if (row.summary.lastChild.textContent !== text) row.summary.lastChild.textContent = text;
    row.summary.lastChild.hidden = !text;
    const expanded = Object.hasOwn(open, id);
    row.summary.hidden = row.record === null;
    row.summary.setAttribute("aria-expanded", String(expanded));
    renderTodoBody(row, expanded);
  };
  if (target && !page?.items.some((item) => item.id === target)) addRow(target);
  let group;
  for (const item of page?.items || []) {
    if (item.section !== group) {
      group = item.section;
      const heading = existing.get(group) || el("h2");
      heading.dataset.key = group;
      const headingText = group === "backlog"
        ? page.backlog_remaining === page.total ? page.total + " in backlog" : page.backlog_remaining + " remaining backlog"
        : group.replaceAll("_", " ");
      if (heading.textContent !== headingText) heading.textContent = headingText;
      children.push(heading);
    }
    addRow(item.id, item, group);
  }
  for (const id of todoRows.keys()) if (!ids.has(id)) todoRows.delete(id);
  for (let i = 0; i < children.length; i++)
    if (list.children[i] !== children[i]) list.insertBefore(children[i], list.children[i] || null);
  while (list.children.length > children.length) list.lastChild.remove();
  $("todo-empty").hidden = page?.total !== 0;
  $("checked").textContent = page ? "checked " + time(page.as_of, page.timezone).toLowerCase() : "";
  if (revealTodo && todoRows.has(revealTodo) && readingTodos()) {
    const row = todoRows.get(revealTodo);
    const title = row.summary.hidden ? row.node : row.summary;
    title.scrollIntoView({ block: "nearest" });
    title.focus({ preventScroll: true });
    changeState({ targetRevealed: true });
    revealTodo = null;
    rememberOverview();
  } else if (position && (page || todoRows.has(position.anchor))) {
    restorePosition(position);
    if (restoreOverview && page && Object.keys(open).every((id) => {
      const row = todoRows.get(id);
      return !row || ((row.record !== undefined || row.errors.record) &&
        (row.errors.results || (row.results !== undefined && row.cursors.at(-1) === open[id].at(-1))));
    })) {
      restoreOverview = false;
    }
  }
}

function refreshTodoRows(force) {
  const open = history.state.openTodos || {};
  for (const [id, row] of todoRows) {
    if (Object.hasOwn(open, id)) {
      readTodoPart(row, "record", force);
      readTodoPart(row, "results", force);
    } else if (id === history.state.todoTarget && !overviewPage?.items.some((item) => item.id === id)) {
      // The active index cannot refresh the summary of an addressed, inactive todo.
      readTodoPart(row, "record", force);
    }
  }
}

async function readTodoPart(row, part, force) {
  const ver = routeVersion;
  const cursors = history.state.openTodos?.[row.id] || [];
  const before = part === "results" ? cursors.at(-1) : null;
  const key = ver + ":" + (before || "");
  if (row.pending[part]?.key === key || (!force && row.checked[part] === key)) return;
  const request = { key };
  row.pending[part] = request;
  row.checked[part] = key;
  const current = () => ver === routeVersion && row.pending[part] === request && todoRows.get(row.id) === row;
  let path = "/api/todos/" + row.id;
  if (part === "results") path += "/results" + (before ? "?before=" + encodeURIComponent(before) : "");
  try {
    const data = await read(path);
    if (!current()) return;
    if (part === "results" && !data) throw new Error("results unavailable");
    row[part] = data;
    if (part === "results") row.cursors = cursors;
    delete row.errors[part];
  } catch (error) {
    if (!current()) return;
    row.errors[part] = error.login ? "login" : "failed";
  } finally {
    if (current()) {
      delete row.pending[part];
      renderOverview();
    }
  }
}

async function detailRead(ver) {
  const [, kind, id] = location.pathname.split("/");
  if (kind === "m") {
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
    restoreChatReturn();
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
    if (part === "canvas" && history.state.canvasSelection === todosCanvas) {
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
  if (document.hidden || undoingTraversal) return;
  poll("canvas", canvasRead);
  if (history.state?.canvasSelection === todosCanvas && !(mobile.matches && history.state.panel))
    refreshTodoRows(true);
  poll("detail", detailRead);
  poll("chat", messages);
  if (!$("chat").hidden && (!mobile.matches || history.state?.panel)) {
    poll("workspace approval", workspaceApproval);
  }
  if (!pendingSend && !staging && !checkingReceipt && draft.uncertain) poll("receipt", recover);
}

async function workspaceApproval(ver) {
  const [approval] = await read("/api/workspace/approvals");
  if (ver !== routeVersion) return;
  const node = $("workspace-approval");
  if (!approval) {
    node.replaceChildren();
    node.hidden = true;
    delete node.dataset.round;
    return;
  }
  if (node.dataset.round === approval.id) return;
  const status = el("p");
  status.setAttribute("role", "status");
  const answer = async (choice) => {
    const controls = [...node.querySelectorAll("button")];
    controls.forEach((control) => { control.disabled = true; });
    try {
      await request("/api/workspace/approvals/" + encodeURIComponent(approval.id), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ choice }),
      });
      status.textContent = "choice recorded.";
    } catch (error) {
      status.textContent = error.login ? "sign in to answer google." :
        "couldn’t record that choice. checking whether the request is still open.";
      controls.forEach((control) => { control.disabled = false; });
    }
    refresh();
  };
  const choices = approval.choices.map(({ value, label }) =>
    button(label, () => answer(value))
  );
  node.replaceChildren(
    el("p", approval.prompt),
    el("small", "google · expires " + time(approval.expires_at)),
    el("div"),
    status,
  );
  node.querySelector("div").append(...choices, button("cancel", () => answer(null)));
  node.dataset.round = approval.id;
  node.hidden = false;
}
showFiles();
startRoute();
window.addEventListener("pagehide", () => {
  rememberOverview();
  rememberReading();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) armed = null;
  else refresh();
});
window.addEventListener("online", refresh);
setInterval(refresh, 3000);
