import { bindArtifacts } from "./artifacts.js";
import { el, button, link } from "./home-dom.js";
import { draftPreview, openEditor } from "./mail-editor.js";
import { bindFiles, drivePath, driveRoute, originStatus } from "./drive.js";
import { chatAttention, instant, tracked } from "./chat-attention.js";

import { address } from "./home-address.js";
import { linkedText, parseMessage, renderMarkdown, showTableControls, updateCitations } from "./chat-reader.js";
import { bindInspection } from "./inspection.js";
import { bindPresence } from "./presence.js";

const $ = (id) => document.getElementById(id);
function creationPath(messageId, created) {
  const kind = created.editable === true ? "draft" : "revision";
  return "/mail/" + messageId + "/" + kind + "/" + created.create_action_id;
}
function objectPath(ref) {
  switch (ref.kind) {
    case "view":
      return "/artifacts/" + ref.slug + "/" + ref.rev;
    case "file":
    case "drive_file":
      return drivePath(ref);
    case "proposal":
      return "/m/" + ref.message_id;
    case "todo":
      return "/t/" + ref.id;
  }
}
function label(ref) {
  if (ref.kind === "view") return ref.slug.replaceAll("-", " ") + " · " + ref.rev.slice(0, 12);
  const kind = ref.kind === "drive_file" ? "drive file" : ref.kind;
  return kind + (ref.page ? " · page " + ref.page : "");
}
const mobile = matchMedia("(max-width:720px)");
const presence = bindPresence({
  request,
  async openOwed(href, control) {
    if (href) {
      if (address(href)?.kind === "message") navigate(href);
      return;
    }
    openSidebar(control);
    if (mobile.matches) $("sidebar-close").focus({ preventScroll: true });
    const landing = document.activeElement;
    await poll("workspace approval", workspaceApproval);
    if (document.activeElement === landing && !$("workspace-approval").hidden)
      $("workspace-approval").querySelector("button")?.focus();
  },
  keepBottom(change) {
    const anchor = chatAnchor();
    const atEnd = pinned && !selectedMessage && !pendingOpening && !isDetail(location.pathname) &&
      chat.scrollHeight - chat.scrollTop - chat.clientHeight <= 2;
    attention.beforeLayoutChange();
    change();
    if (atEnd) scrollChat(chat.scrollHeight);
    else restoreChatAnchor(anchor);
    attention.update();
  },
});
const draftKey = "jarvis.home.draft";
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
let displayed = "",
  routeVersion = 0,
  overviewPage = null,
  restoreOverview = false,
  revealTodo = null;
const todoRows = new Map();
let latest = null,
  earliest = null,
  oldest = null,
  selectedMessage = null;
let lastArrivingTerminal = null, chatToken = null;
const knownTerminals = new Set();
const inFlight = new Map();
const failures = new Map();
let loginRequired = false;
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
const chat = $("chat");
const transcript = $("messages");
let pinned = true, scrollTarget = null, heldPosition = null, pendingOpening = null;
let sentPlacement = null;
let reread = true, visitOpening = true, placeVisit = true, earlierRead = null;
const attention = chatAttention({
  chat,
  list: transcript,
  ledge: $("chat-ledge"),
  sidebarOpen: $("sidebar-open"),
  icon: $("chat-icon"),
  live: $("chat-live"),
  formatTime: time,
  stopAttending() { placeVisit = pinned; },
  newVisit() {
    reread = visitOpening = true;
    refresh();
  },
  preservePosition(update) {
    const anchor = chatAnchor();
    update();
    restoreChatAnchor(anchor);
  },
  place(node) {
    pinned = false;
    scrollChat(insetPosition(node));
  },
  jump(id) { navigate("/m/" + id); },
  earlier: earlierMessages,
  request,
  recheck(older = false) {
    reread ||= older;
    if (!document.hidden && !loginRequired) refreshChat(routeVersion);
  },
  failure(error, part) {
    if (error) failure(error, part);
    else if (failures.delete(part)) showConnection();
  },
});

function save() {
  const files = draft.files.map(({ name, size, sha256 }) => ({ name, size, sha256 }));
  sessionStorage.setItem(draftKey, JSON.stringify({ ...draft, files }));
}
const isDetail = path => address(path)?.kind === "message";
let mailEditor = null;
let shownIndex = history.state?.entryIndex ?? 0;
let undoingTraversal = false;
function pushEntry(state, path) {
  // Chat history entries share the viewer visit they were opened over.
  if (state.panel) state.canvasEntry = history.state.canvasEntry ?? shownIndex;
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
  if (!open && mobile.matches && chat.clientHeight) heldPosition = chatAnchor();
  document.body.dataset.panel = open ? "open" : "closed";
  $("sidebar-open").setAttribute("aria-expanded", String(open));
  $("chat-bar").hidden = !open || (!mobile.matches && !isDetail(location.pathname));
  presence.place(open && mobile.matches);
  if (chat.clientHeight) {
    if (!applyOpening()) restoreChatAnchor(heldPosition);
    heldPosition = null;
  }
  attention.update();
}
mobile.addEventListener("change", setPanel);
function openSidebar(origin) {
  armed = null;
  if (mobile.matches && !history.state?.panel) {
    rememberOverview(origin);
    files.remember(origin);
    artifacts.remember(origin);
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
async function request(path, { allowServerError = false, ...options } = {}) {
  const headers = new Headers(options.headers);
  headers.set("X-Jarvis-Viewer-Contract", "shown-v1");
  const response = await fetch(path, { redirect: "manual", cache: "no-store", ...options, headers });
  if (response.type === "opaqueredirect" || [401, 403].includes(response.status)) {
    if (!loginRequired) {
      loginRequired = true;
      presence.unauthenticated();
      routeVersion++;
      document.body.classList.add("auth-required");
      armed = null;
      selectedMessage = null;
      presentations.clear();
      inspection.close();
      files.close();
      artifacts.leave();
      for (const id of ["object", "object-tools", "location", "todo-list", "messages", "workspace-approval"])
        $(id).replaceChildren();
      $("todo-empty").hidden = true;
      attention.clearProjection();
      knownTerminals.clear();
      failure({ login: true }, "sign in");
    }
    throw Object.assign(new Error("sign in to continue."), { login: true });
  }
  if (response.status === 426) {
    failure({ upgrade: true }, "upgrade");
    throw Object.assign(new Error("reload the jarvis viewer."), { upgrade: true });
  }
  if (!allowServerError && response.status >= 500) throw new Error("jarvis is offline.");
  return response;
}
async function read(path, options) {
  const response = await request(path, options);
  if (response.status === 404) return null;
  if (!response.ok) throw new Error("could not load this item.");
  return response.json();
}
function failure(error, part = "chat") {
  failures.set(part, error.login ? "login" : error.upgrade ? "upgrade" : "offline");
  showConnection();
}
function showConnection() {
  const node = $("connection");
  node.hidden = failures.size === 0;
  if (node.hidden) return;
  const login = loginRequired;
  const upgrade = Array.from(failures.values()).includes("upgrade");
  const when = lastRead ? " last checked " + time(lastRead) + "." : "";
  const message = login ? "sign in to continue. " : upgrade ? "reload the jarvis viewer. " :
    "jarvis is offline. your draft is here." + when;
  if (node.firstChild?.textContent === message) return;
  node.replaceChildren(
    message,
    button(login ? "sign in" : upgrade ? "reload" : "retry", login || upgrade ? () => location.reload() : refresh),
  );
}
function accepted(id, submission) {
  if (draft.id !== submission) return;
  failures.delete("receipt");
  showConnection();
  if (armed?.submission === submission) armed.request = id;
  if (sentPlacement?.submission === submission) {
    if ($("msg-" + id)) {
      scrollChat(chat.scrollHeight);
      sentPlacement = null;
    } else sentPlacement.request = id;
  }
  draft = newDraft();
  $("file-problem").textContent = "";
  receiptMissing = false;
  save();
  resetPicker();
  showFiles();
  $("receipt").textContent = "";
  presence.accepted();
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
  let sending;
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
    attention.sent();
    await attention.flush();
    if (loginRequired) return;
    if (!retry) armed = { submission: id, request: null };
    receiptMissing = false;
    draft.uncertain = true;
    save();
    updateComposer();
    $("receipt").textContent = "";
    sending = setTimeout(() => { $("receipt").textContent = "sending…"; }, 400);
    pendingOpening = null;
    pinned = true;
    sentPlacement = { submission:id, request:null };
    scrollChat(chat.scrollHeight);
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
    clearTimeout(sending);
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

function draftRevisionLink(messageId, actionId) {
  return link(
    "open draft revision",
    "/mail/" + messageId + "/revision/" + actionId,
    "result draft-revision-link",
  );
}
function renderMessage(m, existing) {
  const node = existing || el("article");
  node.id = "msg-" + m.id;
  if (!existing) {
    const stamp = el("div", undefined, "stamp");
    stamp.append(el("strong", m.role === "owner" ? "you" : "jarvis"), el("time", time(m.at)));
    node.append(stamp);
  }
  if (node.messageText !== m.text) {
    node.parsed = parseMessage(m.text);
    node.messageText = m.text;
    const reader = renderMarkdown(m, node.parsed);
    if (node.reader) node.reader.replaceWith(reader);
    else node.append(reader);
    node.reader = reader;
  } else updateCitations(node.reader, m);
  inspection.updateTable(m);
  const controls = el("div");
  for (const f of m.files || [])
    controls.append(
      link(
        (f.name || "unnamed file") +
          " · " +
          (f.unavailable ? "file unavailable" : originStatus(f.state, f.disposition)),
        "/f/" + f.id,
        "file",
      ),
    );
  if (m.ref) {
    const path = objectPath(m.ref);
    controls.append(
      path
        ? link("discussed · " + label(m.ref), path, "result")
        : el("small", "discussed · " + label(m.ref)),
    );
  }
  for (const proposal of m.proposals || []) {
    const group = el("section", undefined, "proposal");
    group.append(
      el("strong", proposal.title),
      proposal.draft_revision_id ? el("p", proposal.detail, "prose") : linkedText(proposal.detail),
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
    controls.append(group);
  }
  if (m.draft_revision_error === "integrity")
    controls.append(el("p", "draft revision failed integrity checks.", "draft-evidence"));
  if (m.draft_revision_id && !m.drafts?.some(d => d.editable !== true && d.create_action_id === m.draft_revision_id)) {
    const revision = draftRevisionLink(m.id, m.draft_revision_id);
    revision.classList.add("draft-evidence");
    controls.append(revision);
  }
  for (const [i, created] of (m.drafts || []).entries()) {
    const subject = created.subject || "(no subject)";
    const numbered = m.drafts.filter((other) => other.subject === created.subject).length > 1;
    const action = created.editable === true ? "open draft" : "open draft revision";
    const ordinal = m.drafts.slice(0, i + 1).filter(other => other.subject === created.subject).length;
    const name = action + " · " + subject + (numbered ? " · " + ordinal : "");
    controls.append(link(name, creationPath(m.id, created), "result draft-revision-link"));
  }
  const delivered = new Map((m.artifact_links || []).map(ref => [objectPath(ref), ref]));
  if (m.present && !["draft", "source"].includes(m.present.ref.kind))
    delivered.set(objectPath(m.present.ref), m.present.ref);
  const alreadyLinked = new Set([...node.reader.querySelectorAll("a[href]"), ...controls.querySelectorAll("a[href]")]
    .map(anchor => anchor.getAttribute("href")));
  for (const [path, ref] of delivered) {
    if (!path || alreadyLinked.has(path)) continue;
    const filename = ref.kind === "file" && m.files?.find(file => file.id === ref.id)?.name;
    const name = filename ? filename + (ref.page ? " · page " + ref.page : "") : label(ref);
    controls.append(link("open " + name, path, "result"));
  }
  if (node.controls) node.controls.replaceWith(controls);
  else node.append(controls);
  node.controls = controls;
  node.dataset.version = JSON.stringify(m);
  node.dataset.at = m.at;
  node.dataset.order = instant(m.at) + m.id;
  if (!existing) attention.render(node, m);
  return node;
}
function chatOffset(node) {
  return node.getBoundingClientRect().top - chat.getBoundingClientRect().top;
}
function insetPosition(node) {
  const preceding = node.previousElementSibling?.matches("article")
    ? node.previousElementSibling : node.previousElementSibling?.previousElementSibling;
  const line = parseFloat(getComputedStyle(preceding?.reader || node).lineHeight);
  return chat.scrollTop + chatOffset(node) - 4.5 * line;
}
function scrollChat(top) {
  if (!chat.clientHeight) return;
  const before = chat.scrollTop;
  chat.scrollTop = top;
  if (chat.scrollTop !== before) scrollTarget = chat.scrollTop;
}
function chatAnchor() {
  if (!chat.clientHeight) return null;
  const top = chat.getBoundingClientRect().top;
  const node = [...transcript.children].find((child) =>
    child.matches("article") && child.getBoundingClientRect().bottom > top);
  return node ? { id:node.id, offset:chatOffset(node) } : null;
}
function restoreChatAnchor(anchor) {
  const node = anchor && $(anchor.id);
  if (node) scrollChat(chat.scrollTop + chatOffset(node) - anchor.offset);
}
function applyOpening() {
  if (!pendingOpening || !chat.clientHeight) return;
  const { node, capped } = pendingOpening;
  pendingOpening = null;
  if (selectedMessage || isDetail(location.pathname) || chatReturn) return;
  scrollChat(capped ? 0 : node ? insetPosition(node) : chat.scrollHeight);
  return true;
}
chat.addEventListener("scroll", () => {
  const programmatic = chat.scrollTop === scrollTarget;
  scrollTarget = null;
  if (programmatic) return;
  sentPlacement = null;
  pendingOpening = null;
  pinned = chat.scrollHeight - chat.scrollTop - chat.clientHeight < 48;
}, { capture:true, passive:true });

function merge(items) {
  const anchor = chatAnchor();
  let mutated = false;
  // The visit separator shares the transcript but is not a message order key.
  const ordered = [...transcript.querySelectorAll(":scope > article")];
  for (const m of items) {
    const existing = $("msg-" + m.id);
    if (m.present) {
      const {ref, request_id} = m.present;
      if (ref.kind === "draft") {
        const created = m.drafts?.find(d => d.request_id === request_id &&
          ref.request_id === request_id && d.create_action_id === ref.create_action_id);
        if (created) presentations.set(request_id, creationPath(m.id, created));
        else presentations.delete(request_id);
      } else if (ref.kind === "source") {
        if (m.sources?.some(source => source.slot === ref.slot && source.state === "available"))
          presentations.set(request_id, "/m/" + m.id + "/source/" + ref.slot);
        else presentations.delete(request_id);
      } else presentations.set(request_id, objectPath(ref));
    }
    if (existing?.dataset.version === JSON.stringify(m)) continue;
    if (!mutated) attention.beforeLayoutChange();
    mutated = true;
    const focused = existing?.contains(document.activeElement) ? document.activeElement : null;
    const node = renderMessage(m, existing);
    if (m.id === selectedMessage) node.classList.add("selected");
    if (existing) {
      if (!focused || focused.isConnected) continue;
      let control;
      if (focused.dataset.readerAnchor)
        control = node.querySelector('[data-reader-anchor="' + focused.dataset.readerAnchor + '"]');
      else if (focused.dataset.action)
        control = node.querySelector('[data-action="' + focused.dataset.action + '"]');
      else if (focused.href)
        control = [...node.querySelectorAll("a")].find((a) => a.href === focused.href);
      attention.restoreFocus(control, focused);
      continue;
    }
    let lo = 0, hi = ordered.length;
    while (lo < hi) {
      const mid = Math.floor((lo + hi) / 2);
      if (ordered[mid].dataset.order < node.dataset.order) lo = mid + 1;
      else hi = mid;
    }
    transcript.insertBefore(node, ordered[lo] || null);
    ordered.splice(lo, 0, node);
  }
  attention.update();
  restoreChatAnchor(anchor);
}

async function messagePage(cursor) {
  const sequence = attention.reading();
  const data = await read("/api/messages" + (cursor ? "?before=" + encodeURIComponent(cursor) : ""),
    { signal: AbortSignal.timeout(6000) });
  if (!Array.isArray(data?.items) || !Array.isArray(data.new) ||
      !Array.isArray(data.owed) || data.owed.length !== data.owed_total ||
      !Number.isSafeInteger(data.new_total) || data.new.length > data.new_total)
    throw new Error("incomplete conversation state");
  return { ...data, sequence };
}

async function messages(ver, paired) {
  const initial = latest === null;
  const allPages = initial || reread;
  reread = false;
  const pages = [];
  let data, cursor = null, seenNew = 0, needContext = false;
  let foundLatest = !latest, foundOldest = !allPages || !oldest;
  let latestId;
  function keepReadState(error) {
    reread ||= allPages || !foundOldest;
    if (ver !== routeVersion || document.hidden || error.upgrade || !pages.length) return;
    for (const page of pages) attention.page(page, page.sequence, true);
    attention.update();
  }
  try {
    do {
      data = await messagePage(cursor);
      if (ver !== routeVersion || document.hidden) {
        reread ||= allPages;
        return;
      }
      const items = data.items;
      if (!pages.length) {
        latestId = items.at(-1)?.id;
        // A new head and a late insert can arrive between the same two reads.
        if (oldest && (attention.olderStale(data.new_total) || paired && paired.chat !== chatToken))
          foundOldest = false;
      }
      pages.push(data);
      foundLatest ||= items.some((m) => m.id === latest);
      foundOldest ||= items.some((m) => m.id === oldest);
      if (initial) {
        seenNew += data.new.length;
        needContext = Boolean(data.new.length && data.new[0] === items[0]?.id);
      }
      cursor = data.next_before;
    } while (cursor && (!foundLatest || !foundOldest ||
      initial && pages.length < 3 && (seenNew < data.new_total || needContext)));
  } catch (error) {
    keepReadState(error);
    throw error;
  }

  if (initial && !latestId) {
    visitOpening = false;
    attention.page(data, data.sequence);
    attention.update();
    presence.chatChecked(paired, null, false);
    return;
  }
  const rows = pages.toReversed().flatMap((page) => page.items);
  // A current page can straddle the previously loaded edge after new inserts.
  const edge = initial ? -1 : rows.findIndex((row) => row.id === oldest);
  if (edge > 0) rows.splice(0, edge);
  const terminals = rows.filter((row) => row.source === "native_final" || row.source === "native_failure");
  const arriving = (!initial || !visitOpening) && terminals.findLast((row) => !knownTerminals.has(row.id));
  const unpainted = arriving && !$("msg-" + arriving.id);
  const handoff = arriving?.id || lastArrivingTerminal;
  const returning = !isDetail(location.pathname) && chatReturn;
  if (returning && !returning.table && !$("msg-" + returning.messageId) &&
      !rows.some((row) => row.id === returning.messageId)) {
    let origin;
    try {
      origin = await read("/api/messages/" + returning.messageId, { signal: AbortSignal.timeout(6000) });
    } catch (error) {
      keepReadState(error);
      throw error;
    }
    if (ver !== routeVersion || document.hidden) {
      reread ||= allPages;
      return;
    }
    if (origin) {
      rows.unshift(origin);
      attention.remember(origin);
    } else chatReturn = null;
  }
  if (initial) {
    earliest = pages.at(-1).next_before;
    oldest = pages.at(-1).items[0]?.id;
  }
  const added = initial && visitOpening ? [] : rows.filter((m) =>
    tracked(m) && !$("msg-" + m.id) &&
    (initial || instant(m.at) + m.id > $("msg-" + latest)?.dataset.order)).map((m) => m.id);
  const before = chat.scrollTop;
  const follow = pinned && !selectedMessage && !isDetail(location.pathname) && !chatReturn;
  const anchor = chatAnchor();
  $("older").hidden = !earliest;
  for (const page of pages) attention.page(page, page.sequence);
  attention.announce(added);
  merge(rows);
  for (const terminal of terminals) knownTerminals.add(terminal.id);
  if (paired) {
    presence.chatChecked(paired, handoff ? $("msg-" + handoff) : null, Boolean(unpainted));
    chatToken = paired.chat;
    lastArrivingTerminal = paired.you ? arriving?.id || null : null;
  } else if (arriving) lastArrivingTerminal = arriving.id;
  restoreChatAnchor(anchor);
  latest = latestId ?? latest;
  if (initial || visitOpening) {
    const boundary = [...transcript.querySelectorAll("article")].find((node) =>
      attention.fresh(node.dataset.messageId));
    if (visitOpening) {
      const anchor = chatAnchor();
      attention.openBoundary(boundary);
      restoreChatAnchor(anchor);
    }
    if ((initial || placeVisit) && !returning && !isDetail(location.pathname))
      pendingOpening = { node:$("chat-boundary") || boundary, capped:initial && seenNew < data.new_total };
    visitOpening = false;
  }
  const sentArrived = sentPlacement?.request && $("msg-" + sentPlacement.request);
  if (sentArrived) sentPlacement = null;
  if (pendingOpening) applyOpening();
  else if ((follow || sentArrived) && added.length && !initial) {
    const arriving = $("msg-" + added[0]);
    if (!attention.attending()) pinned = false;
    else if (chat.clientHeight) {
      const viewport = chat.getBoundingClientRect();
      const first = [...transcript.querySelectorAll("article")].find((node) => {
        const box = node.getBoundingClientRect();
        return attention.fresh(node.dataset.messageId) && box.bottom > viewport.top &&
          (box.top < viewport.bottom || added.includes(node.dataset.messageId));
      }) || arriving;
      scrollChat(Math.max(before, insetPosition(first)));
    }
  } else if (sentArrived || follow && !initial && rows.length && chat.clientHeight &&
    chat.scrollHeight - before - chat.clientHeight < 48) scrollChat(chat.scrollHeight);
  if (!isDetail(location.pathname)) restoreChatReturn();
  if (arriving) refreshChat(ver, true);
}

async function earlierMessages() {
  if (!earliest || earlierRead) return false;
  const before = earliest, ver = routeVersion;
  $("older").disabled = earlierRead = true;
  try {
    const data = await messagePage(before);
    if (ver !== routeVersion || document.hidden) return false;
    earliest = data.next_before;
    oldest = data.items[0]?.id ?? oldest;
    const anchor = chatAnchor();
    $("older").hidden = !earliest;
    attention.page(data, data.sequence);
    for (const row of data.items)
      if (row.source === "native_final" || row.source === "native_failure") knownTerminals.add(row.id);
    merge(data.items);
    restoreChatAnchor(anchor);
    return data.items.length > 0;
  } catch (error) {
    failure(error);
    return false;
  } finally {
    $("older").disabled = false;
    earlierRead = null;
  }
}
$("older").onclick = earlierMessages;
function present() {
  if (!armed?.request || document.hidden) return;
  const path = presentations.get(armed.request);
  if (path) navigate(path);
}
function rememberReading() {
  if (selectedMessage && location.pathname === "/m/" + selectedMessage && $("chat").clientHeight)
    changeState({ reading: { id: selectedMessage, offset: chatOffset($("msg-" + selectedMessage)) } });
}
$("chat").addEventListener("scrollend", rememberReading);
function restoreChatReturn() {
  const returning = chatReturn;
  if (!returning) return;
  const root = returning.table ? $("inspection") : $("msg-" + returning.messageId);
  const pane = returning.table ? $("canvas") : $("chat");
  if (!root || !pane.clientHeight) return;
  let control, anchor = root;
  if (returning.anchor) {
    control = root.querySelector('[data-reader-anchor="' + returning.anchor + '"]');
    if (!control?.getClientRects().length) return;
    anchor = control;
  } else {
    const matches = [...root.querySelectorAll("a")].filter(link => link.href === returning.href);
    control = matches[returning.occurrence];
  }
  chatReturn = null;
  if (document.activeElement !== document.body && document.activeElement !== returning.focus) return;
  const scroll = control?.closest(".table-scroll");
  if (scroll && returning.left !== undefined) scroll.scrollLeft = returning.left;
  const position = pane.scrollTop + anchor.getBoundingClientRect().top -
    pane.getBoundingClientRect().top - returning.offset;
  if (pane === chat) {
    pendingOpening = null;
    pinned = false;
    scrollChat(position);
  } else pane.scrollTop = position;
  attention.restoreFocus(control);
}
function navigate(path, { origin, canvasSelection = path, filesSelector, replace = false } = {}) {
  armed = null;
  if (undoingTraversal || !mayLeaveEditor(canvasSelection)) return;
  if (replace) {
    if (isDetail(location.pathname)) changeState({ canvasSelection });
    else changeState({ canvasSelection }, path);
    startRoute();
    return;
  }
  if (
    !filesSelector && !history.state.filesSelector && path !== "/" &&
    path === location.pathname + location.search && !history.state.panel
  ) return;
  rememberOverview(origin);
  artifacts.remember(origin);
  files.remember(origin || document.activeElement);
  rememberReading();
  const destination = address(path);
  const fromRevision = address(location.href)?.kind === "mail";
  const fromRevisionMessage = Boolean(
    destination?.kind === "mail" && origin?.classList.contains("draft-revision-link") && !fromRevision,
  );
  const article = origin?.closest("#messages article");
  const readerAnchor = ["source", "table"].includes(destination?.kind) && origin?.dataset.readerAnchor;
  const table = readerAnchor && origin.closest("#inspection") ? history.state.canvasSelection : null;
  if (article || table) {
    const pane = table ? $("canvas") : $("chat");
    const anchor = readerAnchor ? origin : article;
    changeState({ chatReturn: {
      fromEntry: shownIndex + 1, messageId: table ? destination.message : article.id.slice(4),
      table, anchor: readerAnchor || null, left: origin.closest(".table-scroll")?.scrollLeft,
      href: origin.href,
      occurrence: article && [...article.querySelectorAll("a")].filter(link => link.href === origin.href).indexOf(origin),
      offset: anchor.getBoundingClientRect().top - pane.getBoundingClientRect().top,
    } });
  } else if (history.state.chatReturn) changeState({ chatReturn: null });
  let state = {
    canvasSelection,
    ...(fromRevisionMessage ? { fromRevisionMessage } : {}),
    ...(filesSelector ? { filesSelector } : {}),
    ...(readerAnchor ? { inspectionOrigin: { table } } : {}),
  };
  if (destination?.kind === "view") {
    state.artifactBack = true;
  } else if (destination?.kind === "todo") {
    state = { ...todoEntry(destination.id), hasOrigin: true };
  } else if (driveRoute(path)) {
    state.filesBack = Boolean(driveRoute(history.state.canvasSelection));
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
  return { canvasSelection: "/todos", todoTarget: id, openTodos: { [id]: [] } };
}
const inspection = bindInspection({ object: $("object"), request, time, restore: restoreChatReturn, restoring: () => Boolean(chatReturn), refresh });
const files = bindFiles({ $, navigate, changeState, request, time, attach: discuss });
const artifacts = bindArtifacts({ $, read, refresh, objectPath, changeState, empty, discuss });
$("files-return").onclick = () => history.back();
$("todo-return").onclick = () => {
  if (history.state.hasOrigin) history.back();
  else {
    replaceEntry({ canvasSelection: "/todos" }, "/todos");
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
  if (!address(a.getAttribute("href"))) return;
  e.preventDefault();
  if (a.id === "artifact-return" && history.state.artifactBack) history.back();
  else navigate(a.pathname + a.search, { origin: a, replace: a.hasAttribute("data-file-page") });
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
  inspection.close();
  routeVersion++;
  failures.delete("canvas");
  failures.delete("detail");
  showConnection();
  reloadReading = history.state?.reading;
  const path = location.pathname + location.search;
  const route = address(location.href);
  const detail = route?.kind === "message";
  const todo = route?.kind === "todo" ? route.id : null;
  if (todo && history.state?.todoTarget !== todo) {
    replaceEntry(todoEntry(todo), path);
  } else if (!history.state?.canvasSelection) {
    changeState(
      detail ? { canvasSelection: "/", panel: true } : { canvasSelection: path },
    );
  }
  const saved = history.state.chatReturn;
  chatReturn = saved && saved.fromEntry === previousEntry
    ? { ...saved, focus: document.activeElement } : null;
  $("draft-choice").hidden = true;
  $("message-unavailable").hidden = true;
  selectedMessage = null;
  document.querySelector(".selected")?.classList.remove("selected");
  if ((detail || todo) && document.activeElement === $("message")) $("message").blur();
  if (displayed !== history.state.canvasSelection && displayed !== "files") {
    artifacts.leave();
    $("object").replaceChildren();
    $("object-tools").hidden = true;
    $("location").replaceChildren();
    displayed = "";
  }
  restoreOverview = Boolean(history.state.position && !detail && !history.state.panel);
  revealTodo = history.state.targetRevealed ? null : todo;
  const sameFiles = files.showing(history.state.canvasSelection, history.state.canvasEntry ?? shownIndex);
  if (!sameFiles) files.close();
  const sameCanvas = leavingPanel && (displayed === history.state.canvasSelection || sameFiles);
  if (!restoreOverview && !detail && !history.state.panel && !sameCanvas) $("canvas").scrollTop = 0;
  $("todo-return").hidden = !todo;
  $("artifact-return").hidden = route?.kind !== "view";
  $("artifact-return").textContent = history.state.artifactBack ? "back" : "back to artifacts";
  $("files-return").hidden = !history.state.filesBack || !driveRoute(path);
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
  if (path === "/") {
    const home = await read("/api/home");
    if (!same()) return;
    path = home.view ? objectPath(home.view) : "/todos";
    changeState({ canvasSelection: path });
  }
  const route = address(path);
  const overview = route?.kind === "todos";
  const viewingShelf = route?.kind === "artifacts";
  const viewingFiles = ["files", "file", "drive_file"].includes(route?.kind);
  const homeVisit = location.pathname === "/";
  for (const [id, selected] of [
    ["todos-tab", overview && !homeVisit],
    ["artifacts-tab", (viewingShelf || route?.kind === "view") && !homeVisit],
    ["files-tab", viewingFiles],
  ]) {
    if (selected) $(id).setAttribute("aria-current", "page");
    else $(id).removeAttribute("aria-current");
  }
  $("todos").hidden = !overview;
  $("drive").hidden = !viewingFiles;
  $("artifacts").hidden = !viewingShelf;
  $("object").hidden = overview || viewingFiles || viewingShelf;
  if (viewingFiles) {
    if (displayed !== "files") {
      displayed = "files";
      $("location").textContent = "";
      $("object").replaceChildren();
      $("object-tools").hidden = true;
    }
    if (mobile.matches && history.state.panel) return;
    await files.show(path, history.state.canvasEntry ?? shownIndex);
    return;
  }
  if (viewingShelf) {
    displayed = path;
    if (!(mobile.matches && history.state.panel)) await artifacts.showShelf(same);
    return;
  }
  if (overview) {
    if (displayed !== path) {
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
  if (route?.kind === "source" || route?.kind === "table") {
    displayed = path;
    $("location").textContent = route.kind;
    $("object-tools").hidden = true;
    if (!mobile.matches || !history.state.panel) await inspection.show(path, route);
    else inspection.close();
    return;
  }
  if (route?.kind === "mail") {
    await mailRead(ver, path, route.message, route.mode, route.action);
    return;
  }
  if (route?.kind !== "view") return;
  const work = await read("/api/artifacts/" + route.slug);
  if (!same()) return;
  const rev = route.rev || work?.current;
  const edition = work?.editions.find(edition => edition.rev === rev);
  if (!edition) {
    if (displayed !== "unavailable:" + path) artifacts.unavailable();
    displayed = "unavailable:" + path;
    return;
  }
  const ref = { kind: "view", slug: route.slug, rev };
  const canonical = objectPath(ref);
  if (!route.rev) {
    if (isDetail(location.href)) changeState({ canvasSelection: canonical });
    else changeState({ canvasSelection: canonical }, canonical);
  }
  displayed = canonical;
  await artifacts.showEdition(work, edition, ref, same);
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
  return history.state?.canvasSelection === "/todos" && !isDetail(location.pathname) &&
    !(mobile.matches && history.state.panel) && displayed === "/todos";
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
    let control = row ? (row.summary.hidden ? row.node : row.summary) : $("todos").querySelector("h1");
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
    body.append(linkedText("this todo is no longer available."));
  }
  if (item) {
    if (item.content) body.append(linkedText(item.content));
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
      li.append(link(result.label || "answer", "/m/" + result.message_id));
      if (result.file_ref) li.append(link("open file", objectPath(result.file_ref)));
      li.append(el("time", time(result.at, timezone)));
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
  const route = address(location.href);
  if (route?.kind === "message") {
    const { id } = route;
    const m = await read("/api/messages/" + id, { signal: AbortSignal.timeout(6000) });
    if (ver !== routeVersion || document.hidden) return;
    $("message-unavailable").hidden = Boolean(m);
    if (!m) return;
    attention.remember(m);
    const alreadySelected = selectedMessage === id;
    const restore = reloadReading?.id === id;
    selectedMessage = id;
    merge([m]);
    if (alreadySelected) return;
    pendingOpening = null;
    pinned = false;
    const node = $("msg-" + id);
    node.classList.add("selected");
    scrollChat(chat.scrollTop + chatOffset(node) - (restore ? reloadReading.offset : 0));
    reloadReading = null;
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
    const kind = address(history.state.canvasSelection)?.kind;
    if (error.upgrade) return;
    if (part === "canvas" && ["artifacts", "view"].includes(kind)) {
      artifacts.failed(kind === "artifacts");
    } else if (part === "canvas" && kind === "todos") {
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
let pendingChat = null, readingChat = false, chatPoll = 0;
async function refreshChat(ver, fresh) {
  const pollNumber = ++chatPoll;
  const paired = await presence.read(fresh);
  if (pollNumber !== chatPoll || document.hidden || undoingTraversal || loginRequired || ver !== routeVersion)
    return;
  pendingChat = { ver, paired };
  if (readingChat) return;
  readingChat = true;
  try {
    while (pendingChat) {
      const next = pendingChat;
      pendingChat = null;
      if (document.hidden || undoingTraversal || loginRequired || next.ver !== routeVersion) continue;
      await poll("chat", async current => {
        try {
          await messages(current, next.paired);
        } catch (error) {
          if (current === routeVersion) presence.chatFailed(next.paired);
          throw error;
        }
      });
    }
  } finally {
    readingChat = false;
  }
}

function refresh() {
  if (document.hidden || undoingTraversal || loginRequired) return;
  poll("canvas", canvasRead);
  if (history.state?.canvasSelection === "/todos" && !(mobile.matches && history.state.panel))
    refreshTodoRows(true);
  poll("detail", detailRead);
  refreshChat(routeVersion);
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
new ResizeObserver(() => {
  showTableControls();
  restoreChatReturn();
}).observe($("chat"));
showFiles();
startRoute();
window.addEventListener("pagehide", () => {
  inspection.close();
  rememberOverview();
  artifacts.remember();
  files.remember(document.activeElement);
  files.close();
  rememberReading();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    armed = null;
    pendingChat = null;
    presence.suspend();
    inspection.close();
  } else {
    reread = true;
    presence.resume();
    refresh();
  }
});
window.addEventListener("pageshow", event => {
  if (event.persisted) {
    reread = true;
    presence.resume();
  }
  refresh();
});
window.addEventListener("online", refresh);
setInterval(refresh, 3000);
setInterval(() => {
  if (!document.hidden || loginRequired) return;
  poll("shown counts", async ver => {
    const sequence = attention.reading();
    const data = await read("/api/shown", { signal: AbortSignal.timeout(6000) });
    if (ver === routeVersion && document.hidden) attention.totals(data, sequence);
  });
}, 60000);
