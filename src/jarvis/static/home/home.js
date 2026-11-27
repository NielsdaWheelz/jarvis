import { bindArtifacts } from "./artifacts.js";
import { el, button, link } from "./home-dom.js";
import { draftPreview, openEditor } from "./mail-editor.js";
import { bindFiles, drivePath, driveRoute, originStatus } from "./drive.js";
import { chatAttention, instant, precedingArticle, tracked } from "./chat-attention.js";

import { address } from "./home-address.js";
import { linkedText, parseMessage, renderMarkdown, showTableControls, updateCitations } from "./chat-reader.js";
import { bindInspection } from "./inspection.js";
import { bindPresence, stampDigits, time as stampTime } from "./presence.js";

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
  receiptPending: () => Boolean(activeSend) || draft.uncertain,
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
  keepBottom: preservePage,
});
const draftKey = "jarvis.home.draft";
let reloadReading = null;
let chatReturn = null;
const newDraft = () => ({ id: null, text: "", ref: null, files: [], uncertain: false });
let draft = JSON.parse(sessionStorage.getItem(draftKey) || "null") || newDraft();
let armed = null,
  activeSend = null,
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
let advance = null, receiptSequence = 0;
let fontLoad = "waiting", fontOpening = null;
let reread = true, visitOpening = true, placeVisit = true, earlierRead = null;
let pageSequence = 0, owedSequence = 0, owedIds = "";
const fine = matchMedia("(pointer: fine)");
const reducedMotion = matchMedia("(prefers-reduced-motion: reduce)");
const attention = chatAttention({
  chat,
  list: transcript,
  ledge: $("chat-ledge"),
  sidebarOpen: $("sidebar-open"),
  icon: $("chat-icon"),
  live: $("chat-live"),
  formatTime: stampTime,
  advancing: () => Boolean(advance),
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
    finishAdvance();
    fontOpening = null;
    pinned = false;
    scrollChat(insetPosition(node));
  },
  jump(id) { navigate("/m/" + id); },
  earlier: earlierMessages,
  failure(error) {
    if (error) failure(error, "shown");
    else if (failures.delete("shown")) showConnection();
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
  finishAdvance();
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
function openSidebar(origin, keepPresentation = false) {
  if (!keepPresentation) armed = null;
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
  if (e.key !== "Escape" || e.isComposing) return;
  if (dragDepth) clearDrag();
  else if (!$("discard-choice").hidden) $("keep").click();
  else if (!$("draft-choice").hidden) {
    preservePage(() => { $("draft-choice").hidden = true; });
    $("message").focus({ preventScroll: true });
  } else if (mobile.matches && history.state?.panel) closeSidebar();
});
function canStage() {
  return !activeSend && (!draft.uncertain || receiptMissing) && $("discard-choice").hidden;
}
function fitMessage() {
  const field = $("message");
  const scroll = field.scrollTop;
  field.style.height = "auto";
  field.style.height = field.scrollHeight + "px";
  field.scrollTop = scroll;
}
function updateComposer() {
  preservePage(() => {
    const field = $("message");
    if (field.value !== draft.text) field.value = draft.text;
    fitMessage();
    const editable = !activeSend && !draft.uncertain;
    field.readOnly = !editable;
    $("composer").toggleAttribute("data-sending", Boolean(activeSend));
    $("composer").toggleAttribute("data-held", draft.uncertain && !activeSend);
    $("files").disabled = !canStage();
    $("context").hidden = !draft.ref;
    $("ref-label").textContent = draft.ref ? "about · " + (draft.refLabel || label(draft.ref)) : "";
    $("remove-ref").hidden = !editable;
    for (const control of $("file-list").querySelectorAll("button")) {
      const restore = control.dataset.reselect !== undefined;
      control.hidden = !editable && !(restore && canStage());
      control.disabled = Boolean(staging);
    }
    const missing = draft.files.some((entry) => !entry.file);
    $("attach").hidden = $("send").hidden = !editable;
    $("retry-send").hidden = Boolean(activeSend) || !draft.uncertain;
    $("send").disabled = !editable || Boolean(staging) || missing || (!draft.text.trim() && !draft.files.length);
    $("retry-send").disabled = Boolean(staging) || missing;
    $("discard").hidden = $("retry-send").hidden;
    $("discard").disabled = Boolean(staging);
  });
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
    const thumbnail = el("span", undefined, "draft-thumbnail");
    thumbnail.setAttribute("aria-hidden", "true");
    if (entry.preview) thumbnail.append(entry.preview);
    else thumbnail.textContent = entry.name.includes(".") ? entry.name.split(".").at(-1).slice(0, 5) : "file";
    const name = el("span", entry.name, "draft-name");
    name.title = entry.name;
    row.append(thumbnail, name, el("small", entry.size < 1024 ? entry.size + " b"
      : entry.size < 1024 ** 2 ? (entry.size / 1024).toFixed(1) + " kib"
      : (entry.size / 1024 ** 2).toFixed(1) + " mib"));
    if (!entry.file) {
      const choose = button("reselect", () => {
        reselect = entry;
        $("files").multiple = false;
        $("files").click();
      });
      choose.dataset.reselect = "";
      choose.setAttribute("aria-label", "reselect " + entry.name);
      row.append(choose);
    }
    const remove = button("×", () => {
      draft.files.splice(index, 1);
      $("file-problem").textContent = "";
      save();
      showFiles();
      const next = $("file-list").children[index] || $("file-list").lastChild;
      (next?.lastChild || $("files")).focus({ preventScroll: true });
    });
    remove.setAttribute("aria-label", "remove " + entry.name);
    row.append(remove);
    return row;
  });
  preservePage(() => { $("file-list").replaceChildren(...rows); });
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
    $("file-list").children[draft.files.indexOf(entry)]
      ?.querySelector(".draft-thumbnail").replaceChildren(canvas);
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
    const hash = await digest(file);
    const match = candidates.find((entry) =>
      entry.sha256 === hash || (!draft.uncertain && !entry.sha256 && entry.name === fileName(file)));

    if (!match) throw new Error(fileName(file) + " does not match a missing original file.");
    missing.splice(missing.indexOf(match), 1);
    matches.push({ entry: match, hash, file });
  }
  for (const {entry, hash, file} of matches) {
    entry.sha256 = hash;
    attachBytes(entry, file);
  }
  save();
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
        const entries = [];
        for (const file of files)
          entries.push({ name: fileName(file), size: file.size, sha256: await digest(file) });
        draft.files.push(...entries);
        for (const [i, entry] of entries.entries()) attachBytes(entry, files[i]);
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
  $("sidebar").classList.remove("dragging");
}
function fileDrag(e) {
  return e.dataTransfer?.types.includes("Files");
}
$("sidebar").ondragenter = (e) => {
  if (!fileDrag(e)) return;
  e.preventDefault();
  dragDepth++;
  $("sidebar").classList.toggle("dragging", canStage());
};
$("sidebar").ondragover = (e) => {
  if (!fileDrag(e)) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = canStage() ? "copy" : "none";
};
$("sidebar").ondragleave = () => {
  if (--dragDepth <= 0) clearDrag();
};
$("sidebar").ondrop = (e) => {
  clearDrag();
  stageTransfer(e, e.dataTransfer);
};
for (const kind of ["dragover", "drop"]) document.addEventListener(kind, (e) => {
  if (!fileDrag(e) || (e.target instanceof Element && e.target.closest("#sidebar"))) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = "none";
  clearDrag();
});
window.addEventListener("dragend", clearDrag);
window.addEventListener("blur", clearDrag);
function discuss(ref, title, origin) {
  const blocked = activeSend || draft.uncertain;
  openSidebar(origin, blocked);
  if (blocked) {
    caption("settle the earlier message first.");
    return;
  }
  const choice = $("draft-choice");
  choice.hidden = true;
  const use = () => {
    draft.ref = ref;
    draft.refLabel = title || label(ref);
    save();
    updateComposer();
    choice.hidden = true;
    $("message").focus({ preventScroll: true });
  };
  if (
    !draft.ref ||
    (objectPath(draft.ref) === objectPath(ref) && draft.ref.action_id === ref.action_id)
  )
    return use();
  const keep = button("keep draft", () => {
    preservePage(() => { choice.hidden = true; });
    $("message").focus({ preventScroll: true });
  });
  choice.replaceChildren(
    "change the reference to " + (title || label(ref)) + "? ",
    keep,
    button("use this item", use),
  );
  preservePage(() => { choice.hidden = false; });
  keep.focus({ preventScroll: true });
}
async function request(path, { allowServerError = false, ...options } = {}) {
  const headers = new Headers(options.headers);
  headers.set("X-Jarvis-Viewer-Contract", "cited-sources-v1");
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
function caption(text) {
  const node = $("receipt");
  if (node.textContent !== text) preservePage(() => { node.textContent = text; });
}
function resetDraft() {
  draft = newDraft();
  receiptMissing = false;
  save();
  resetPicker();
  $("file-problem").textContent = "";
  $("receipt").textContent = "";
  $("discard-choice").hidden = $("draft-choice").hidden = true;
  $("compose-actions").hidden = false;
  showFiles();
}
$("discard").onclick = () => {
  preservePage(() => {
    $("compose-actions").hidden = true;
    $("discard-choice").hidden = false;
  });
  $("keep").focus({ preventScroll: true });
};
$("keep").onclick = () => {
  preservePage(() => {
    $("discard-choice").hidden = true;
    $("compose-actions").hidden = false;
  });
  $("discard").focus({ preventScroll: true });
};
$("confirm-discard").onclick = () => {
  if (activeSend || !draft.uncertain) return;
  if (armed?.submission === draft.id) armed = null;
  failures.delete("receipt");
  showConnection();
  preservePage(resetDraft);
  $("message").focus({ preventScroll: true });
  refresh();
};
function finishAdvance() {
  advance?.cancel();
  advance = null;
}
function accepted(receipt, submission) {
  if (loginRequired) return;
  if (draft.id !== submission && $("msg-" + receipt.id)) return;
  receiptSequence++;
  finishAdvance();
  if (draft.id !== submission) {
    merge([receipt.message]);
    return;
  }
  const focused = $("composer").contains(document.activeElement);
  const follow = pinned && chat.clientHeight && chat.scrollHeight - chat.scrollTop - chat.clientHeight <= 2;
  const anchor = chatAnchor();
  const last = transcript.querySelector("article:last-child");
  const offset = last && chatOffset(last);
  const scroll = chat.scrollTop;
  failures.delete("receipt");
  showConnection();
  if (armed?.submission === submission) armed.request = receipt.id;
  resetDraft();
  merge([receipt.message]);
  presence.accepted();
  if (follow) scrollChat(chat.scrollHeight);
  else restoreChatAnchor(anchor);
  if (focused) $("message").focus({ preventScroll: true });
  if (follow && last && scroll !== chat.scrollTop && !document.hidden && !reducedMotion.matches) {
    const dy = offset - chatOffset(last);
    if (dy) {
      attention.beforeLayoutChange();
      advance = $("chat-page").animate([{ transform: "translateY(" + dy + "px)" }, { transform: "none" }],
        { duration: Math.min(420, 140 + .5 * Math.abs(dy)), easing: "cubic-bezier(.2,0,0,1)" });
      advance.onfinish = () => { advance = null; };
    }
  }
  present();
}
function validReceipt(receipt) {
  if (!receipt?.id || receipt.message?.id !== receipt.id) throw new Error("invalid send receipt");
  return receipt;
}
async function findReceipt(id, signal) {
  const receipt = await read("/api/submissions/" + id, { signal });
  return receipt && validReceipt(receipt);
}
async function reconcile() {
  const id = draft.id;
  const receipt = await findReceipt(id, AbortSignal.timeout(6000));
  if (activeSend && draft.id === id) return;
  if (receipt) {
    accepted(receipt, id);
    refresh();
  } else if (draft.id === id && !receiptMissing) {
    receiptMissing = true;
    caption("no receipt yet. retry is safe: it cannot arrive twice.");
    updateComposer();
  }
}
$("stop-waiting").onclick = () => activeSend?.abort();
$("composer").onsubmit = async (event) => {
  event.preventDefault();
  const trigger = $(draft.uncertain ? "retry-send" : "send");
  if (activeSend || trigger.disabled || !$("discard-choice").hidden) return;
  if (new TextEncoder().encode(draft.text).length > 16 * 1024) {
    $("file-problem").textContent = "the caption exceeds 16 kib. shorten it to send.";
    return;
  }
  const retry = draft.uncertain;
  const id = draft.id ?? crypto.randomUUID();
  const flight = new AbortController();
  activeSend = flight;
  armed = { submission: id, request: null };
  draft.id = id;
  draft.uncertain = true;
  receiptMissing = false;
  save();
  $("draft-choice").hidden = true;
  $("file-problem").textContent = "";
  caption("");
  updateComposer();
  $("message").focus({ preventScroll: true });
  attention.sent();
  fontOpening = pendingOpening = null;
  pinned = true;
  scrollChat(chat.scrollHeight);
  const sending = setTimeout(() => caption("sending…"), 400);
  const waiting = setTimeout(() => {
    preservePage(() => { $("stop-waiting").hidden = false; });
  }, 10000);
  let receipt;
  try {
    if (retry) receipt = await findReceipt(id, flight.signal);
    if (receipt) return;
    const descriptor = JSON.stringify({ text: draft.text, ref: draft.ref });
    const options = { method: "PUT", signal: flight.signal };
    if (draft.files.length) {
      const form = new FormData();
      form.append("message", descriptor);
      for (const entry of draft.files) form.append("file", entry.file, entry.name);
      options.body = form;
    } else {
      options.headers = { "Content-Type": "application/json" };
      options.body = descriptor;
    }
    const response = await request("/api/messages/" + id, options);
    if (response.ok) receipt = validReceipt(await response.json());
    else if (response.status === 409) {
      caption("a different message already used this send. it is in the conversation.");
      armed = null;
      draft.uncertain = false;
      draft.id = null;
      save();
    } else if ([400, 413, 422].includes(response.status)) {
      draft.uncertain = retry;
      if (!retry) {
        draft.id = null;
        armed = null;
      }
      save();
      $("file-problem").textContent = response.status === 400 ? "use the private home address to send."
        : response.status === 413 ? "message or files are too large."
        : "check the message, files and reference.";
      caption(retry ? "checking whether your message arrived…" : "");
    } else throw new Error("send unavailable");
  } catch (error) {
    if (error.upgrade && !retry) {
      draft.uncertain = false;
      draft.id = null;
      armed = null;
      save();
      caption("");
    } else {
      caption("checking whether your message arrived…");
      if (!flight.signal.aborted) failure(error, "receipt");
    }
  } finally {
    clearTimeout(sending);
    clearTimeout(waiting);
    $("stop-waiting").hidden = true;
    activeSend = null;
    if (receipt && !loginRequired) accepted(receipt, id);
    else updateComposer();
    refresh();
  }
};
$("message").onkeydown = (e) => {
  if (e.key !== "Enter" || e.altKey || e.isComposing || e.keyCode === 229 ||
      (!(e.ctrlKey || e.metaKey) && (e.shiftKey || !fine.matches))) return;
  if ($("message").readOnly) return;
  e.preventDefault();
  if (!e.repeat) $("send").click();
};

const localDate = new Intl.DateTimeFormat("en-GB", {
  weekday: "long", day: "numeric", month: "long", year: "numeric",
});
const revisionPath = (id, action) => "/mail/" + id + "/revision/" + action;

function apparatus(rows) {
  const list = el("div", undefined, "apparatus");
  let prior;
  for (const [kind, name, path, note] of rows) {
    const row = el("div", undefined, "apparatus-row");
    const heading = el("span", kind === prior ? "" : kind, "apparatus-kind");
    if (path) heading.setAttribute("aria-hidden", "true");
    const value = el("span");
    const entry = path ? link(name, path, path.startsWith("/mail/") ? "draft-revision-link" : undefined) : el("span", name);
    if (path) entry.setAttribute("aria-label", [kind, name, note].filter(Boolean).join(" · "));
    value.append(entry);
    if (note) value.append(el("small", " · " + note));
    row.append(heading, value);
    list.append(row);
    prior = kind;
  }
  return list;
}

function renderMessage(m, existing) {
  const node = existing || el("article");
  node.id = "msg-" + m.id;
  if (!existing) {
    const date = new Date(m.at);
    const localDay = [date.getFullYear(), date.getMonth() + 1, date.getDate()]
      .map((value, index) => String(value).padStart(index ? 2 : 4, "0")).join("-");
    const stamp = el("div", undefined, "stamp");
    const when = el("time");
    when.dateTime = date.toISOString();
    when.title = localDate.format(date);
    stampDigits(when, stampTime(m.at));
    stamp.append(el("strong", m.role === "owner" ? "you" : "jarvis", "sr-only"), when);
    node.append(stamp);
    Object.assign(node.dataset, { role: m.role, source: m.source, day: localDay });
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
  const rows = [];
  if (m.ref) rows.push(["about", label(m.ref), objectPath(m.ref)]);
  for (const file of m.files)
    rows.push(["file", file.name || "unnamed file", "/f/" + file.id,
      file.unavailable ? "file unavailable" : file.state === "filed" ? "filed"
        : originStatus(file.state, file.disposition)]);
  for (const draft of [...m.drafts.filter(draft => draft.editable), ...m.drafts.filter(draft => !draft.editable)]) {
    const subject = draft.subject || "(no subject)";
    const editable = draft.editable === true;
    const peers = m.drafts.filter(other => other.editable === draft.editable &&
      (other.subject || "(no subject)") === subject);
    const label = editable && peers.length > 1 ? subject + " · " + (peers.indexOf(draft) + 1) : subject;
    rows.push([editable ? "draft" : "revision", label, creationPath(m.id, draft)]);
  }
  const unchecked = m.draft_revision_error === "integrity";
  const revised = m.draft_revision_id && !m.drafts.some(draft =>
    !draft.editable && draft.create_action_id === m.draft_revision_id);
  if (revised || unchecked)
    rows.push(["revision", "draft revision", revised ? revisionPath(m.id, m.draft_revision_id) : null,
      unchecked ? "failed integrity checks" : null]);

  const proposals = m.proposals.map(proposal => {
    const group = el("section", undefined, "proposal");
    group.dataset.status = proposal.status;
    group.append(el("div", proposal.title, "proposal-title"),
      proposal.draft_revision_id ? el("p", proposal.detail, "prose") : linkedText(proposal.detail));
    const details = [];
    if (proposal.draft_revision_id)
      details.push(["revision", "draft revision", revisionPath(m.id, proposal.draft_revision_id)]);
    if (proposal.decision)
      details.push(["you", proposal.decision === "approve" ? "approved" : "denied", "/m/" + proposal.owner_message_id]);
    if (details.length) group.append(apparatus(details));
    const reply = button("reply", () => discuss(
      { kind: "proposal", message_id: m.id, action_id: proposal.action_id }, proposal.title));
    reply.dataset.action = proposal.action_id;
    const foot = el("div", undefined, "proposal-foot");
    foot.append(reply, el("span", proposal.status_label || proposal.status.replaceAll("_", " ")));
    group.append(foot);
    return group;
  });
  const seen = new Set([
    ...rows.map(([, , path]) => path),
    ...[node.reader, ...proposals].flatMap(group => [...group.querySelectorAll("a[href]")].map(a => a.getAttribute("href"))),
  ]);
  const refs = m.artifact_links.slice();
  if (m.present && !["draft", "source"].includes(m.present.ref.kind)) refs.push(m.present.ref);
  for (const ref of refs) {
    const path = objectPath(ref);
    if (!path || seen.has(path)) continue;
    seen.add(path);
    const file = ref.kind === "file" && m.files.find(file => file.id === ref.id);
    const kind = ref.kind === "view" ? "artifact" : ref.kind === "todo" ? "todo" : "file";
    rows.push([kind, file?.name || label({ ...ref, page: null }), path, ref.page ? "page " + ref.page : null]);
  }
  const controls = el("div");
  if (rows.length) controls.append(apparatus(rows));
  controls.append(...proposals);
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
  const preceding = precedingArticle(node);
  const line = parseFloat(getComputedStyle(preceding?.reader || node).lineHeight);
  return chat.scrollTop + chatOffset(node) - 4.5 * line;
}
function scrollChat(top) {
  if (!chat.clientHeight) return;
  const target = Math.min(Math.max(0, top), chat.scrollHeight - chat.clientHeight);
  const before = chat.scrollTop;
  if (fontOpening && fontOpening.scrollTop !== before) fontOpening = null;
  if (Math.abs(before - target) < .02) return;
  finishAdvance();
  chat.scrollTop = target;
  if (chat.scrollTop !== before) {
    scrollTarget = chat.scrollTop;
    if (fontOpening) fontOpening.scrollTop = scrollTarget;
  }
}
function chatAnchor() {
  if (!chat.clientHeight) return null;
  const top = chat.getBoundingClientRect().top;
  const node = [...transcript.children].find((child) =>
    child.matches("article") && child.getBoundingClientRect().bottom > top);
  return node ? { id:node.id, offset:chatOffset(node) } : null;
}
function preservePage(change) {
  finishAdvance();
  const anchor = chatAnchor();
  const bottom = pinned && !pendingOpening && chat.clientHeight &&
    chat.scrollHeight - chat.scrollTop - chat.clientHeight <= 2;
  attention.beforeLayoutChange();
  change();
  if (bottom) scrollChat(chat.scrollHeight);
  else restoreChatAnchor(anchor);
  attention.update();
}
function restoreChatAnchor(anchor) {
  const node = anchor && $(anchor.id);
  if (node) scrollChat(chat.scrollTop + chatOffset(node) - anchor.offset);
}
function applyOpening() {
  if (fontLoad === "waiting" || !pendingOpening || !chat.clientHeight) return;
  const opening = pendingOpening;
  const { node, capped, exactOffset } = opening;
  pendingOpening = null;
  if (chatReturn) return;
  if (exactOffset !== undefined) {
    if (location.pathname !== "/m/" + selectedMessage || node.id !== "msg-" + selectedMessage) return;
    scrollChat(chat.scrollTop + chatOffset(node) - exactOffset);
  } else {
    if (selectedMessage || isDetail(location.pathname)) return;
    scrollChat(capped ? 0 : node ? insetPosition(node) : chat.scrollHeight);
  }
  if (fontLoad === "fallback") fontOpening = { ...opening, scrollTop: chat.scrollTop };
  return true;
}
chat.addEventListener("scroll", () => {
  const programmatic = chat.scrollTop === scrollTarget;
  scrollTarget = null;
  if (programmatic) return;
  finishAdvance();
  fontOpening = pendingOpening = null;
  const remaining = chat.scrollHeight - chat.scrollTop - chat.clientHeight;
  pinned = draft.uncertain ? remaining <= 2 : remaining < 48;
}, { capture:true, passive:true });

for (const event of ["wheel", "touchstart", "pointerdown", "keydown"])
  chat.addEventListener(event, finishAdvance, { capture: true, passive: true });

function merge(items) {
  if (items.some(m => $("msg-" + m.id)?.dataset.version !== JSON.stringify(m))) finishAdvance();
  const anchor = chatAnchor();
  let mutated = false;
  // Only messages participate in the order, including when reading around a day head.
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
  if (mutated) {
    const heads = new Map([...transcript.querySelectorAll(".day-head")].map(node => [node.id, node]));
    let day;
    for (const node of ordered) {
      if (node.dataset.day === day) continue;
      day = node.dataset.day;
      const id = "day-" + day;
      let head = heads.get(id);
      heads.delete(id);
      if (!head) {
        const parts = Object.fromEntries(localDate.formatToParts(new Date(node.dataset.at))
          .map(({ type, value }) => [type, value]));
        const caption = [parts.weekday, parts.day, parts.month];
        if (Number(parts.year) !== new Date().getFullYear()) caption.push(parts.year);
        head = el("h2", caption.join(" ").toLowerCase(), "day-head");
        head.id = id;
      }
      if (head.nextElementSibling !== node) transcript.insertBefore(head, node);
    }
    for (const head of heads.values()) head.remove();
    attention.update();
  }
  restoreChatAnchor(anchor);
}

async function messagePage(cursor) {
  const sequence = ++pageSequence;
  const data = await read("/api/messages" + (cursor ? "?before=" + encodeURIComponent(cursor) : ""),
    { signal: AbortSignal.timeout(6000) });
  if (!Array.isArray(data.owed) || data.owed.length !== data.owed_total)
    throw new Error("incomplete conversation state");
  return { ...data, sequence };
}

function applyOwed({ owed, sequence }) {
  if (sequence <= owedSequence) return;
  owedSequence = sequence;
  const ids = owed.join(",");
  if (ids === owedIds) return;
  owedIds = ids;
  preservePage(() => attention.setOwed(owed));
}
function currentProjection(version) {
  return version === receiptSequence && !activeSend && !loginRequired && !document.hidden;
}
async function settlePage(version) {
  if (!currentProjection(version)) return false;
  if (!draft.uncertain) return true;
  const id = draft.id;
  await reconcile();
  return currentProjection(version) && (!draft.uncertain || draft.id === id);
}
async function messages(ver, paired) {
  const version = receiptSequence;
  const initial = latest === null;
  const allPages = initial || reread;
  reread = false;
  const pages = [], scanned = [];
  let data, cursor = null, depth = 0, firstNewPage = -1;
  let foundLatest = !latest, foundOldest = !allPages || !oldest;
  let latestId;
  try {
    do {
      data = await messagePage(cursor);
      if (ver !== routeVersion || document.hidden) {
        reread ||= allPages;
        return;
      }
      const items = data.items;
      if (!depth) {
        latestId = items.at(-1)?.id;
        // A new head and a late insert can arrive between the same two reads.
        if (paired && paired.chat !== chatToken && oldest) foundOldest = false;
      }
      if (!depth || !foundLatest || !foundOldest || initial && depth < 3) pages.push(data);
      foundLatest ||= items.some((m) => m.id === latest);
      foundOldest ||= items.some((m) => m.id === oldest);
      for (const m of items) if (tracked(m)) scanned.push({ id:m.id, at:m.at, role:m.role, source:m.source });
      if (initial) {
        const first = items.findIndex(attention.isNew);
        if (first >= 0) firstNewPage = depth + (first === 0 && data.next_before && depth < 2 ? 1 : 0);
      }
      depth++;
      cursor = data.next_before;
    } while (cursor && (!foundLatest || !foundOldest ||
      allPages && attention.afterStart(data.items[0]) ||
      initial && firstNewPage >= depth));
    if (!(await settlePage(version)) || !currentProjection(version) || ver !== routeVersion) {
      reread ||= allPages;
      return;
    }
  } catch (error) {
    reread ||= allPages;
    throw error;
  }

  applyOwed(data);
  if (initial) {
    if (!latestId) {
      visitOpening = false;
      presence.chatChecked(paired, null, false);
      return;
    }
    pages.splice(Math.min(3, Math.max(1, firstNewPage + 1)));
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
      if (!(await settlePage(version)) || !currentProjection(version) || ver !== routeVersion) {
        reread ||= allPages;
        return;
      }
    } catch (error) {
      reread ||= allPages;
      throw error;
    }
    if (origin) {
      rows.unshift(origin);
      scanned.push(origin);
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
  if ($("older").hidden !== !earliest) preservePage(() => { $("older").hidden = !earliest; });
  attention.receive(scanned, added);
  merge(rows);
  for (const terminal of terminals) knownTerminals.add(terminal.id);
  if (paired) {
    presence.chatChecked(paired, handoff ? $("msg-" + handoff) : null, Boolean(unpainted));
    chatToken = paired.chat;
    lastArrivingTerminal = paired.you ? arriving?.id || null : null;
  } else if (arriving) lastArrivingTerminal = arriving.id;
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
      pendingOpening = { node:$("chat-boundary") || boundary, capped:initial && firstNewPage >= 3 };
    visitOpening = false;
  }
  if (pendingOpening) applyOpening();
  else if (follow && added.length && !initial) {
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
  } else if (follow && !initial && rows.length && chat.clientHeight &&
    chat.scrollHeight - before - chat.clientHeight < 48) scrollChat(chat.scrollHeight);
  if (!isDetail(location.pathname)) restoreChatReturn();
  if (arriving) refreshChat(ver, true);
}

async function earlierMessages() {
  if (!earliest || earlierRead) return false;
  const before = earliest, ver = routeVersion, version = receiptSequence;
  $("older").disabled = earlierRead = true;
  try {
    const data = await messagePage(before);
    if (!(await settlePage(version)) || !currentProjection(version) || ver !== routeVersion) return false;
    applyOwed(data);
    earliest = data.next_before;
    oldest = data.items[0]?.id ?? oldest;
    if ($("older").hidden !== !earliest) preservePage(() => { $("older").hidden = !earliest; });
    attention.receive(data.items);
    for (const row of data.items)
      if (row.source === "native_final" || row.source === "native_failure") knownTerminals.add(row.id);
    merge(data.items);
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
  fontOpening = null;
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
    const version = receiptSequence;
    const m = await read("/api/messages/" + id, { signal: AbortSignal.timeout(6000) });
    if (!(await settlePage(version)) || !currentProjection(version) || ver !== routeVersion) return;
    $("message-unavailable").hidden = Boolean(m);
    if (!m) return;
    attention.receive([m]);
    const alreadySelected = selectedMessage === id;
    const restore = reloadReading?.id === id;
    selectedMessage = id;
    merge([m]);
    if (alreadySelected) return;
    pinned = false;
    const node = $("msg-" + id);
    node.classList.add("selected");
    pendingOpening = { node, exactOffset: restore ? reloadReading.offset : 0 };
    applyOpening();
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
  if (!activeSend && !staging && draft.uncertain) poll("receipt", reconcile);
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
let fieldWidth = 0;
new ResizeObserver(() => {
  const width = $("message").clientWidth;
  if (width && width !== fieldWidth) {
    fieldWidth = width;
    preservePage(fitMessage);
  }
  showTableControls();
  restoreChatReturn();
}).observe($("chat"));
const typeDeadline = setTimeout(() => {
  fontLoad = "fallback";
  applyOpening();
}, 1500);
Promise.allSettled([
  Promise.all([document.fonts.load("400 1rem Literata"), document.fonts.load("italic 400 1rem Literata")]),
  Promise.all([
    document.fonts.load('400 1rem "Cormorant Garamond"'),
    document.fonts.load('italic 400 1rem "Cormorant Garamond"'),
  ]),
]).then(results => {
  clearTimeout(typeDeadline);
  // A compositor can scroll before the corresponding DOM event is delivered.
  if (fontOpening?.scrollTop === chat.scrollTop) pendingOpening ||= fontOpening;
  fontOpening = null;
  const [reading, display] = results.map(result =>
    result.status === "fulfilled" && result.value.every(matches => matches.length > 0));
  preservePage(() => {
    const sidebar = $("sidebar");
    sidebar.toggleAttribute("data-literata", reading);
    sidebar.toggleAttribute("data-cormorant", display);
    fontLoad = "settled";
    fitMessage();
  });
  if (applyOpening()) attention.update();
});
if (draft.uncertain) $("receipt").textContent = "checking whether your message arrived…";
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
    finishAdvance();
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
