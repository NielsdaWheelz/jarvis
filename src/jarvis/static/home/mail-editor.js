import { button, el, link } from "./home-dom.js";

const addressFields = ["to", "cc", "bcc"];
const byteSize = (value) => new TextEncoder().encode(value).length;
function mailbox({ name, address }) {
  if (!name) return address;
  const display = /[,"<>\\]/.test(name) ? JSON.stringify(name) : name;
  return display + " <" + address + ">";
}
function recipients(text) {
  if (!text.trim()) return [];
  // Quoted display names can contain commas and escaped quotes.
  const tokens = text.match(/(?:"(?:\\.|[^"\\])*"|[^,"\n])+|[,\n]|./gs);
  const values = [];
  let needed = true;
  for (const token of tokens || []) {
    if (token === "," || token === "\n") {
      if (needed) throw new Error();
      needed = true;
      continue;
    }
    const part = token.trim();
    if (!part && needed) continue;
    const match = /^(?:(.+?)\s*<([^<>]+)>|([^<>]+))$/.exec(part);
    const address = (match?.[2] || match?.[3] || "").trim();
    if (!needed || !/^[^\s@<>,"]+@[^\s@<>,"]+$/.test(address)) throw new Error();
    let name = match[1]?.trim() || null;
    if (name?.startsWith('"')) name = JSON.parse(name);
    values.push({ name, address });
    needed = false;
  }
  if (needed || values.length > 50) throw new Error();
  return values;
}
function nameFile(file, files) {
  const name = file.name ?? file.filename;
  const bytes = file.bytes ?? file.size_bytes;
  const duplicate =
    files.filter(
      (other) =>
        (other.name ?? other.filename) === name && (other.bytes ?? other.size_bytes) === bytes,
    ).length > 1;
  return (
    name +
    " · " +
    bytes.toLocaleString() +
    " bytes" +
    (duplicate && file.sha256 ? " · " + file.sha256.slice(-8) : "")
  );
}
function quoting(text) {
  const details = el("details");
  details.append(el("summary", "quoted text"), el("div", text, "mail-text"));
  return details;
}
function review(value, historical = false) {
  const box = el("div", undefined, "mail-review");
  box.append(
    el("h2", value.subject == null ? "(subject unavailable)" : value.subject || "(no subject)"),
  );
  const envelope = el("dl");
  for (const key of ["from", ...addressFields]) {
    const addresses = key === "from" && value.from ? [value.from] : value[key];
    envelope.append(
      el("dt", key),
      el("dd", addresses ? addresses.map(mailbox).join(", ") || "none" : "unavailable"),
    );
  }
  box.append(envelope);
  const body = historical ? value.body_text : value.body;
  if (body != null) {
    const text =
      historical && value.quote && body.endsWith(value.quote)
        ? body.slice(0, -value.quote.length)
        : body;
    box.append(el("div", text || "empty email body", "mail-text"));
  }
  if (value.quote) box.append(quoting(value.quote));
  if (value.files?.length) {
    const files = el("ol");
    for (const file of value.files) {
      const item = el("li", nameFile(file, value.files));
      if (historical) item.append(" · historical file bytes unavailable");
      files.append(item);
    }
    box.append(el("h3", "attachments"), files);
  }
  return box;
}
export function draftPreview(revision, current) {
  if (!revision) return el("p", "draft revision is not available for this message.");
  if (revision.status === "integrity") return el("p", "draft revision failed integrity checks.");
  if (!["partial", "complete"].includes(revision.status))
    return el("p", revision.omission || "exact revision unavailable");
  const panel = el("div");
  const at = revision.observed_at ? " · " + new Date(revision.observed_at).toLocaleString() : "";
  panel.append(
    el("p", (current ? "as drafted" : "recorded revision") + at, "secondary"),
    review(revision, true),
  );
  if (revision.omission) panel.append(el("p", revision.omission));
  return panel;
}
const reasons = {
  unrepresentable_draft_mime:
    "this draft contains formatting, headers or inline files the editor cannot preserve.",
  draft_missing: "this draft is no longer available in gmail.",
  editor_epoch_changed: "this saved revision is available for inspection only.",
  permission_denied: "gmail denied permission for this request.",
  rate_limited: "gmail’s quota was reached. try again later.",
  temporary: "gmail is temporarily unavailable.",
  too_large: "the message or its attachments exceed the gmail size limit.",
  invalid_reply_subject: "the reply subject must match its thread.",
  unsupported_mime: "gmail formatting or inline attachments cannot be preserved in this editor.",
  unsupported_content: "this draft contains content the editor cannot preserve.",
  stale_version: "this draft changed in gmail",
  reconnect_required: "reconnect the owner gmail account to continue.",
  quota_exceeded: "gmail’s quota was reached. try again later.",
  denied: "gmail denied this request.",
  missing_draft: "this draft is no longer available in gmail.",
};
function explanation(data) {
  return (
    reasons[data.reason] ||
    reasons[data.state] ||
    data.reason?.replaceAll("_", " ") ||
    "could not complete the request."
  );
}
async function mailRequest(url, options) {
  const response = await fetch(url, { cache: "no-store", redirect: "manual", ...options });
  if (response.type === "opaqueredirect") throw new Error("sign in to continue.");
  const payload = await response.json().catch(() => ({}));
  const data = typeof payload.detail === "object" ? payload.detail : payload;
  if (!response.ok && !data.state) {
    let reason = data.reason || (typeof data.detail === "string" ? data.detail : null);
    if (response.status === 410) reason = "missing_draft";
    if (response.status === 413) reason = "attachment size limit exceeded";
    if (!reason && [401, 403].includes(response.status)) reason = "sign in to continue.";
    return { state: "failed", reason: reason || "request failed (" + response.status + ")" };
  }
  return data;
}

export function openEditor(panel, path, original, digest) {
  const api = "/api" + path;
  const form = el("fieldset", undefined, "mail-fields"),
    actions = el("div", undefined, "mail-actions");
  const status = el("p", "", "mail-status"),
    choices = el("div", undefined, "mail-choices");
  status.setAttribute("role", "status");
  const preview = panel.firstElementChild;
  panel.append(form, actions, status, choices);
  form.hidden = true;
  const cells = {};
  let live,
    files = [],
    generation = 0,
    confirmed = 0,
    timeout,
    saveDue = 0;
  let inFlight = null,
    sending = false,
    blocked = false,
    reading = false,
    picking = false,
    closed = false;
  const dirty = () => generation !== confirmed || picking || Boolean(inFlight) || sending;
  function notice(text) {
    status.textContent = text;
  }
  function stopTimer() {
    clearTimeout(timeout);
  }
  function valid(kind) {
    try {
      command(kind);
      return !picking;
    } catch {
      return false;
    }
  }
  function command(kind) {
    const result = {
      kind,
      base: live.version,
      subject: cells.subject.value,
      body: cells.body.value,
      files: [],
    };
    if (byteSize(result.subject) > 998) throw new Error("subject exceeds 998 bytes.");
    if (byteSize(result.body + (live.quote || "")) > 100000)
      throw new Error("body exceeds 100,000 bytes.");
    for (const field of addressFields) {
      try {
        result[field] = recipients(cells[field].value);
      } catch {
        throw new Error("finish the " + field + " addresses.");
      }
    }
    if (kind === "send" && !addressFields.some((key) => result[key].length))
      throw new Error("add a recipient to send.");
    let uploads = 0;
    result.files = files.map((f) =>
      f.local ? { upload: uploads++ } : { keep: f.slot, sha256: f.sha256 },
    );
    return result;
  }
  function controls() {
    form.disabled = sending || blocked;
    send.disabled = sending || reading || blocked || (live && !valid("send"));
    edit.disabled = reading || sending || blocked;
  }
  function schedule() {
    stopTimer();
    if (!live || !dirty() || closed || blocked || sending || inFlight || picking) return;
    if (!navigator.onLine) {
      notice("changes only on this device");
      return;
    }
    try {
      command("save");
    } catch (e) {
      notice(e.message);
      return;
    }
    timeout = setTimeout(() => start("save"), Math.max(0, saveDue - Date.now()));
  }
  function changed() {
    generation++;
    saveDue = Date.now() + (files.reduce((sum, f) => sum + f.bytes, 0) > 5000000 ? 5000 : 1000);
    notice(navigator.onLine ? "changes on this device" : "changes only on this device");
    controls();
    schedule();
  }
  function drawFiles(list) {
    list.replaceChildren();
    for (const [i, file] of files.entries()) {
      const row = el("li");
      const source = file.local
        ? URL.createObjectURL(file.local)
        : api + "/files/" + file.slot + "?version=" + encodeURIComponent(live.version);
      if (file.local) objectUrls.push(source);
      const a = link(nameFile(file, files), source);
      a.target = "_blank";
      a.rel = "noopener";
      if (file.local) a.download = file.name;
      // A GET is opened by the owner. Do not prefetch provider data while rendering rows.
      const remove = button("remove", () => {
        const index = files.indexOf(file);
        if (index < 0) return;
        files.splice(index, 1);
        redrawFiles();
        (
          list.children[Math.min(index, files.length - 1)]?.querySelector("button") || picker
        ).focus();
        changed();
      });
      remove.setAttribute("aria-label", "remove " + file.name + " · attachment " + (i + 1));
      row.append(a, " ", remove);
      list.append(row);
    }
  }
  const list = el("ol"),
    picker = el("input"),
    objectUrls = [];
  function releaseFileUrls() {
    for (const url of objectUrls.splice(0)) URL.revokeObjectURL(url);
  }
  function redrawFiles() {
    const active = document.activeElement;
    const index = [...list.children].findIndex((row) => row.contains(active));
    releaseFileUrls();
    drawFiles(list);
    if (index >= 0)
      list.children[index]?.querySelector(active.tagName)?.focus({ preventScroll: true });
  }
  picker.type = "file";
  picker.multiple = true;
  picker.addEventListener("change", async () => {
    const selected = [...picker.files];
    picker.value = "";
    if (!selected.length) return;
    picking = true;
    stopTimer();
    controls();
    picker.disabled = true;
    try {
      if (selected.length + files.length > 10) throw new Error("choose at most ten attachments.");
      if (
        selected.reduce(
          (n, f) => n + f.size,
          files.reduce((n, f) => n + f.bytes, 0),
        ) > 25000000
      )
        throw new Error("attachments exceed 25,000,000 bytes.");
      const added = [];
      for (const f of selected) {
        if (!f.name || byteSize(f.name) > 255 || /[\x00-\x1f\\/]/.test(f.name))
          throw new Error("invalid attachment name · " + f.name);
        added.push({
          name: f.name,
          type: f.type || "application/octet-stream",
          bytes: f.size,
          sha256: await digest(f),
          local: f,
        });
      }
      if (!closed && !blocked) {
        files.push(...added);
        redrawFiles();
        changed();
      }
    } catch (e) {
      notice(e.message);
    } finally {
      picking = false;
      picker.disabled = false;
      controls();
      schedule();
    }
  });
  function openForm(data) {
    live = data;
    blocked = false;
    files = [...data.files];
    preview.hidden = true;
    choices.replaceChildren();
    form.replaceChildren(el("legend", "gmail draft"), el("p", "from · " + mailbox(data.from)));
    for (const key of [...addressFields, "subject", "body"]) {
      const field = el(key === "body" || addressFields.includes(key) ? "textarea" : "input");
      field.value = addressFields.includes(key) ? data[key].map(mailbox).join(", ") : data[key];
      field.readOnly = key === "subject" && data.threaded;
      if (key === "body") field.rows = 10;
      if (addressFields.includes(key)) {
        field.rows = 1;
        field.autocapitalize = "none";
        field.spellcheck = false;
      }
      const label = el("label", key);
      label.append(field);
      form.append(label);
      cells[key] = field;
      if (field.readOnly) form.append(el("small", "the reply subject stays with its thread."));
      field.addEventListener("input", changed);
    }
    if (data.quote) form.append(quoting(data.quote));
    const attach = el("label", "attach files");
    attach.append(picker);
    form.append(list, attach);
    form.hidden = false;
    redrawFiles();
    edit.hidden = true;
    send.hidden = false;
    controls();
  }
  const edit = button("edit", () => activate("edit"));
  const send = button("send", () => (live ? start("send") : activate("send")));
  actions.append(edit, send);
  async function activate(kind) {
    if (closed || reading || blocked || sending) return;
    reading = true;
    controls();
    notice("checking gmail…");
    try {
      const data = await mailRequest(api);
      if (closed) return;
      if (data.state !== "ready") {
        await held(data);
        return;
      }
      if (!data.as_drafted) {
        preview.hidden = false;
        openComparison(data, true);
        return;
      }
      openForm(data);
      notice("");
      if (kind === "send" && !document.hidden) {
        reading = false;
        await start("send");
      }
    } catch (e) {
      if (!closed) notice(e.message);
    } finally {
      reading = false;
      controls();
    }
  }
  function openComparison(remote, first, heldId = null) {
    blocked = true;
    stopTimer();
    controls();
    notice(
      !heldId && first
        ? "this draft changed in gmail. review it before continuing."
        : heldId
          ? remote.acknowledged_message_id
            ? "gmail acknowledged the save. its result is unverified. review both versions."
            : remote.desired_observed
              ? "the requested changes are in gmail. the earlier save is unconfirmed."
              : "save unconfirmed. review both versions."
          : "this draft changed in gmail. your changes are here.",
    );
    choices.replaceChildren();
    const available = [...remote.files];
    const matches = [];
    const missing = [];
    for (const entry of files) {
      const index = available.findIndex(
        (f) =>
          !entry.local &&
          f.sha256 === entry.sha256 &&
          f.name === entry.name &&
          f.bytes === entry.bytes &&
          f.type === entry.type,
      );
      if (entry.local) matches.push({ entry, keep: true });
      else if (index >= 0) matches.push({ entry: available.splice(index, 1)[0], keep: true });
      else missing.push(entry);
    }
    const resolutionFiles = matches.concat(available.map((entry) => ({ entry, keep: false })));
    choices.append(el("h2", "gmail version"), review(remote));
    if (!first && live) {
      choices.append(el("h3", "attachments to reapply"));
      for (const file of missing)
        choices.append(
          el("p", nameFile(file, files) + " is missing from gmail. reapplying omits this file."),
        );
      if (!resolutionFiles.length) choices.append(el("p", "none"));
      for (const choice of resolutionFiles) {
        const option = el("input");
        option.type = "checkbox";
        option.checked = choice.keep;
        const label = el("label");
        label.append(
          option,
          nameFile(
            choice.entry,
            resolutionFiles.map((x) => x.entry),
          ),
        );
        choices.append(label);
        option.onchange = () => {
          choice.keep = option.checked;
        };
      }
    }
    let resolving = false;
    const use = async (reapply) => {
      if (resolving || closed) return;
      resolving = true;
      for (const control of choices.querySelectorAll("button,input")) control.disabled = true;
      try {
        const base = heldId
          ? await mailRequest(api + "/resolve-save", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ operation_id: heldId, version: remote.version }),
            })
          : remote;
        if (closed) return;
        if (base.state !== "ready") {
          await held(base);
          return;
        }
        const values =
          reapply &&
          Object.fromEntries([...addressFields, "subject", "body"].map((k) => [k, cells[k].value]));
        openForm(base);
        confirmed = generation;
        notice("");
        if (values) {
          for (const [key, value] of Object.entries(values))
            if (!cells[key].readOnly) cells[key].value = value;
          files = resolutionFiles.filter((c) => c.keep).map((c) => c.entry);
          redrawFiles();
          generation++;
          controls();
          await start("save");
        }
      } catch (e) {
        if (!closed) notice(e.message);
      } finally {
        resolving = false;
        if (!closed)
          for (const control of choices.querySelectorAll("button,input")) control.disabled = false;
      }
    };
    choices.append(
      button(first && !heldId ? "edit gmail version" : "use gmail version", () => use(false)),
    );
    if (!first && live) choices.append(button("reapply my edits", () => use(true)));
  }
  async function compareCurrent() {
    const remote = await mailRequest(api);
    if (closed) return;
    if (remote.version && (remote.state === "ready" || remote.state === "save_unknown"))
      openComparison(remote, !live, remote.state === "save_unknown" ? remote.operation_id : null);
    else if (remote.reason === "stale_version" || remote.reason === "draft_changed") {
      notice("the gmail version changed again.");
      checkAgain("review gmail version", compareCurrent);
    } else await held(remote);
  }
  function checkAgain(label, run) {
    const check = button(label, async () => {
      if (check.disabled) return;
      check.disabled = true;
      try {
        await run();
      } catch (e) {
        if (!closed) notice(e.message);
      } finally {
        check.disabled = false;
      }
    });
    choices.replaceChildren(check);
  }
  async function held(data, sentHere = false) {
    if (closed) return;
    blocked = true;
    stopTimer();
    controls();
    choices.replaceChildren();
    if (data.state === "sent") {
      if (sentHere) confirmed = generation;
      const label = sentHere ? "sent" : "a send was already recorded for this draft";
      notice(
        label +
          (data.message_id ? " · " + data.message_id : "") +
          (!sentHere && generation !== confirmed ? ". your local edits have no send receipt." : ""),
      );
      send.hidden = true;
      edit.hidden = true;
      return;
    }
    if (data.state === "send_unknown") {
      notice(
        "send unconfirmed · check sent mail" +
          (data.acknowledged_message_id
            ? " · gmail acknowledged the request; the result could not be verified."
            : ""),
      );
      const account = live?.account || original.from?.address;
      const a = link(
        "check sent mail",
        "https://mail.google.com/mail/u/" + encodeURIComponent(account) + "/#sent",
      );
      a.target = "_blank";
      a.rel = "noopener";
      choices.append(a);
      return;
    }
    if (data.state === "save_unknown") {
      notice(
        data.acknowledged_message_id
          ? "gmail acknowledged the save. the result could not be verified."
          : "save unconfirmed · check the gmail version",
      );
      if (data.version && data.files) openComparison(data, !live, data.operation_id);
      else checkAgain("review gmail version", compareCurrent);
      return;
    }
    if (
      ["operation_expired", "operation_changed", "save_resolution_unavailable"].includes(
        data.reason,
      )
    ) {
      notice(explanation(data));
      checkAgain("review gmail version", compareCurrent);
      return;
    }
    if (data.state === "entered") {
      notice(data.kind === "send" ? "checking send receipt…" : "checking save receipt…");
      checkAgain("check status", async () => {
        const result = await mailRequest(
          api + "/operations/" + encodeURIComponent(data.operation_id),
        );
        if (result.state === "saved") await compareCurrent();
        else await held(result);
      });
      return;
    }
    if (["stale_version", "stale_file", "draft_changed"].includes(data.reason)) {
      notice("this draft changed in gmail");
      checkAgain("review gmail version", compareCurrent);
      await compareCurrent();
      return;
    }
    let failure = explanation(data);
    if (Number.isInteger(data.slot)) failure += " · attachment " + data.slot;
    if (Number.isInteger(data.upload)) {
      const entry = files.filter((f) => f.local)[data.upload];
      if (entry) failure += " · " + entry.name;
    }
    notice(failure);
    if (data.state === "reconnect_required" || data.reason === "reconnect_required") {
      checkAgain("check connection", compareCurrent);
      return;
    }
    if (
      ["unavailable", "unsupported"].includes(data.state) ||
      [
        "draft_missing",
        "editor_epoch_changed",
        "missing_draft",
        "unrepresentable_draft_mime",
        "unsupported_mime",
        "unsupported_content",
        "unrepresentable",
      ].includes(data.reason)
    )
      return;
    blocked = false;
    controls();
    // A definite rejection leaves edits intact. Explicit retry also covers going offline.
    if (live && dirty()) checkAgain("save changes", () => start("save"));
  }
  async function perform(kind) {
    const desired = command(kind);
    const prior = [...files],
      writing = generation,
      id = crypto.randomUUID();
    const formData = new FormData();
    formData.append("command", JSON.stringify(desired));
    for (const entry of prior) if (entry.local) formData.append("file", entry.local, entry.name);
    const op = api + "/operations/" + id;
    async function settle(data) {
      while (!closed && data.state === "entered" && data.operation_id === id) {
        await new Promise((resolve) => setTimeout(resolve, 650));
        if (closed) return false;
        data = await mailRequest(op);
        if (data.operation_id !== id || data.kind !== kind)
          throw new Error("operation receipt unavailable");
      }
      if (closed) return false;
      if (data.state === "saved" && data.operation_id === id && kind === "save") {
        const slots = data.files;
        if (
          !data.version ||
          slots?.length !== prior.length ||
          slots.some(
            (f, i) =>
              f.name !== prior[i].name ||
              f.bytes !== prior[i].bytes ||
              f.sha256 !== prior[i].sha256 ||
              f.slot !== i + 1,
          )
        ) {
          blocked = true;
          controls();
          notice("could not match gmail’s saved attachments. review the gmail version.");
          checkAgain("review gmail version", compareCurrent);
          return false;
        }
        live.version = data.version;
        files = files.map((entry) => {
          const i = prior.indexOf(entry);
          return i === -1 ? entry : slots[i];
        });
        confirmed = writing;
        blocked = false;
        choices.replaceChildren();
        controls();
        redrawFiles();
        notice(generation === writing ? "saved in gmail" : "changes on this device");
        // A manual lookup can settle after the original request and its autosave loop have ended.
        if (!inFlight && generation !== confirmed) schedule();
        return true;
      }
      await held(data, kind === "send" && data.operation_id === id && data.kind === kind);
      return false;
    }
    // After a transport loss the only automatic follow-up is reading this same operation.
    async function recover() {
      try {
        const response = await mailRequest(op);
        if (response.operation_id !== id) throw new Error();
        return await settle(response);
      } catch {
        blocked = true;
        controls();
        notice(
          kind === "send"
            ? "send unconfirmed · check sent mail"
            : "save unconfirmed · check status",
        );
        checkAgain("check status", recover);
        if (kind === "send") {
          const sent = link(
            "check sent mail",
            "https://mail.google.com/mail/u/" + encodeURIComponent(live.account) + "/#sent",
          );
          sent.target = "_blank";
          sent.rel = "noopener";
          choices.append(sent);
        }
        return false;
      }
    }
    try {
      const result = await mailRequest(op, { method: "PUT", body: formData });
      if (result.state === "failed" && /^request failed \(5/.test(result.reason || ""))
        return await recover();
      return await settle(result);
    } catch {
      return await recover();
    }
  }
  async function start(kind) {
    if (closed || blocked || reading || sending || picking || (kind === "save" && inFlight)) return;
    stopTimer();
    if (!navigator.onLine) {
      notice("changes only on this device");
      return;
    }
    try {
      command(kind);
    } catch (e) {
      notice(e.message);
      return;
    }
    if (kind === "send") {
      sending = true;
      controls();
    }
    choices.replaceChildren();
    try {
      // While sending, controls stay frozen. Only an earlier confirmed save can rebind its files.
      if (inFlight && !(await inFlight)) return;
      if (closed || blocked || !navigator.onLine) return;
      if (kind === "send" && document.hidden) {
        notice("review the draft and press send.");
        return;
      }
      notice(kind === "send" ? "sending…" : "saving…");
      const work = perform(kind);
      inFlight = work;
      const saved = await work;
      if (inFlight === work) inFlight = null;
      if (saved && generation !== confirmed && !sending) schedule();
    } catch (e) {
      if (!closed) notice(e.message);
    } finally {
      if (kind === "send") sending = false;
      if (!closed) controls();
    }
  }
  function beforeLeave(e) {
    if (dirty()) {
      e.preventDefault();
      e.returnValue = "";
    }
  }
  function offline() {
    stopTimer();
    if (dirty()) notice("changes only on this device");
  }
  function online() {
    if (dirty() && !blocked && !inFlight && !sending)
      checkAgain("save changes", () => start("save"));
  }
  window.addEventListener("beforeunload", beforeLeave);
  window.addEventListener("offline", offline);
  window.addEventListener("online", online);
  return {
    path,
    dirty,
    close() {
      closed = true;
      stopTimer();
      releaseFileUrls();
      window.removeEventListener("beforeunload", beforeLeave);
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", online);
    },
  };
}
