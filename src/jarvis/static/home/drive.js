import { el, button, link } from "./home-dom.js";

const driveId = /^[A-Za-z0-9_-]{1,255}$/;
const folderType = "application/vnd.google-apps.folder";
const previewLimit = 100 * 1024 * 1024;

export function drivePath(ref) {
  const path = ref.kind === "file"
    ? "/f/" + ref.id
    : "/files/" + encodeURIComponent(ref.subject) + "/" + encodeURIComponent(ref.id);
  return path + (ref.page ? "?page=" + ref.page : "");
}

export function driveRoute(path) {
  const url = new URL(path, location.origin);
  if (url.origin !== location.origin || url.hash) return null;
  if (url.pathname === "/files" && !url.search) return { kind: "files" };
  const parts = url.pathname.split("/");
  const page = url.search && /^\?page=([1-9][0-9]{0,15})$/.exec(url.search)?.[1];
  if (url.search && (!page || !Number.isSafeInteger(Number(page)))) return null;
  if (parts[1] === "files" && parts.length === 4 && parts.slice(2).every(id => driveId.test(id)))
    return { kind: "drive_file", subject: parts[2], id: parts[3], ...(page ? { page: Number(page) } : {}) };
  if (parts[1] === "f" && parts.length === 3 &&
      /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/.test(parts[2]))
    return { kind: "file", id: parts[2], ...(page ? { page: Number(page) } : {}) };
  return null;
}

const messages = {
  drive_disconnected: "google drive isn’t connected.",
  drive_inaccessible: "this file is missing or you no longer have access.",
  drive_invalid_input: "this drive address is invalid.",
  drive_rate_limited: "google drive is limiting requests. try again shortly.",
  drive_version_changed: "the file changed while opening. try again.",
  drive_cursor_stale: "this search expired. start it again.",
  drive_preview_too_large: "this file is too large to preview.",
  drive_preview_unsupported: "this file cannot be previewed here.",
  drive_unavailable: "google drive couldn’t complete this read. try again.",
};

export function originStatus(state, disposition) {
  if (state === "filed") return "open in files";
  if (state === "unavailable") return disposition === "deleted" ? "deleted" : "file unavailable";
  if (state === "uncertain") return "local copy · drive may have received a file";
  if (state === "created") return "only on jarvis · checking the drive copy";
  return "only on jarvis";
}

function typeLabel(type) {
  switch (type) {
    case folderType: return "folder";
    case "application/pdf": return "pdf";
    case "application/vnd.google-apps.document": return "google doc";
    case "application/vnd.google-apps.spreadsheet": return "google sheet";
    case "application/vnd.google-apps.presentation": return "google slides";
    default: return type.startsWith("image/") ? "image" : type.split("/").at(-1);
  }
}

async function pdfPreview(data, number, region, signal) {
  const pdf = await import("./pdf/pdf.min.mjs");
  if (signal.aborted) return;
  pdf.GlobalWorkerOptions.workerSrc = new URL("./pdf/pdf.worker.min.mjs", import.meta.url).href;
  const task = pdf.getDocument({
    data,
    isEvalSupported: false,
    useWasm: false,
    useSystemFonts: true,
    disableFontFace: true,
    maxImageSize: 24_000_000,
    canvasMaxAreaInBytes: 64 * 1024 * 1024,
    wasmUrl: new URL("./pdf/", import.meta.url).href,
  });
  const close = () => task.destroy().catch(() => {});
  signal.addEventListener("abort", close, { once: true });
  try {
    if (signal.aborted) return;
    const document = await task.promise;
    if (number > document.numPages) return { count: document.numPages, missing: true };
    const page = await document.getPage(number);
    const natural = page.getViewport({ scale: 1 });
    const scale = Math.min(1600 / natural.width, 2400 / natural.height, 4);
    const viewport = page.getViewport({ scale });
    const canvas = el("canvas");
    canvas.width = Math.ceil(viewport.width);
    canvas.height = Math.ceil(viewport.height);
    if (!canvas.width || !canvas.height) throw new Error("invalid page geometry");
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", "page " + number + " of " + document.numPages);
    await page.render({ canvas, viewport }).promise;
    if (!signal.aborted) region.replaceChildren(canvas);
    return { count: document.numPages, missing: false };
  } finally {
    signal.removeEventListener("abort", close);
    await close();
  }
}

export function bindFiles({ $, navigate, changeState, request, time, attach }) {
  const page = $("drive");
  const canvas = $("canvas");
  let active = null;

  function close() {
    if (!active) return;
    active.controller.abort();
    active = null;
    page.replaceChildren();
  }

  function remember(origin) {
    if (!active?.list || page.hidden) return;
    const row = origin?.closest?.("[data-drive-id]");
    const before = history.state?.filesPosition;
    changeState({ filesPosition: {
      depth: active.list.depth,
      scroll: canvas.scrollTop,
      row: row?.dataset.driveId || before?.row,
    } });
  }
  canvas.addEventListener("scrollend", () => remember(document.activeElement));
  page.addEventListener("focusin", event => remember(event.target));

  async function read(path, signal, binary = false) {
    let response;
    try {
      response = await request(path, { signal, allowServerError: true });
    } catch (error) {
      if (signal.aborted || error.login) throw error;
      throw new Error("couldn’t reach jarvis. try again.");
    }
    if (!response.ok) {
      const code = (await response.json().catch(() => ({}))).detail;
      const wait = response.headers.get("Retry-After");
      const message = code === "drive_rate_limited" && /^\d+$/.test(wait || "")
        ? "google drive is limiting requests. retry in " + wait + (wait === "1" ? " second." : " seconds.")
        : messages[code] || "couldn’t open google drive.";
      throw Object.assign(new Error(message), { code });
    }
    if (!binary) return response.json();
    const length = Number(response.headers.get("Content-Length"));
    if (!Number.isSafeInteger(length) || length > previewLimit || length <= 0)
      throw new Error(messages.drive_preview_too_large);
    if (response.headers.get("Content-Type") === "application/pdf") {
      const data = new Uint8Array(await response.arrayBuffer());
      if (data.byteLength !== length) throw new Error("this file didn’t finish downloading.");
      return data;
    }
    const image = await response.blob();
    if (image.size !== length) throw new Error("this file didn’t finish downloading.");
    return image;
  }

  function official(label, url) {
    const a = link(label, url);
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    return a;
  }

  function pageLink(label, ref) {
    const node = link(label, drivePath(ref));
    node.setAttribute("data-file-page", "");
    return node;
  }

  function downloadOrigin(record) {
    const download = link("download", "/api/drive/origin/" + record.id + "/content");
    download.download = record.name || "";
    return download;
  }

  function originLine(record) {
    const row = el("li");
    const title = record.name || "file";
    row.append(
      link(title, "/f/" + record.id),
      el("small", originStatus(record.state, record.disposition) + " · received " + time(record.received_at)),
      downloadOrigin(record),
    );
    row.firstChild.dataset.driveId = record.id;
    return row;
  }

  function controls(selector, folder, subject) {
    const bar = el("nav", undefined, "drive-breadcrumbs");
    bar.setAttribute("aria-label", "drive location");
    bar.append(link("my drive", "/files"));
    function part(node) {
      const separator = el("span", "/");
      separator.setAttribute("aria-hidden", "true");
      bar.append(separator, node);
    }
    for (const item of folder?.trail || [])
      part(link(item.name, drivePath({ kind: "drive_file", subject, id: item.id })));
    if (folder) part(el("span", folder.name));
    const form = el("form", undefined, "drive-search");
    form.setAttribute("role", "search");
    const query = el("input");
    query.type = "search";
    query.maxLength = 255;
    query.value = selector.q || "";
    query.placeholder = "search filenames";
    query.setAttribute("aria-label", "search filenames");
    const submit = el("button", "search");
    submit.type = "submit";
    form.append(query, submit);
    form.onsubmit = (event) => {
      event.preventDefault();
      if (query.value.trim())
        navigate("/files", { filesSelector: { q: query.value.trim() } });
    };
    page.append(bar, form, button("recent", () => navigate("/files", { filesSelector: { recent: "true" } })));
  }

  async function showList(ref, folder, view) {
    const { signal } = view.controller;
    const selector = folder ? { folder: folder.id } : history.state?.filesSelector || { folder: "root" };
    const previous = history.state?.filesPosition;
    const snapshot = { depth: 0, rows: new Map(), next: null, partial: false };
    view.list = snapshot;
    controls(selector, folder, ref.subject);
    if (folder) page.append(button("attach to chat", () => attach(
      { kind: "drive_file", subject: ref.subject, id: folder.id }, folder.name,
    )));
    const title = folder?.name || (selector.q ? "search results" : selector.recent ? "recent" : "my drive");
    const pending = el("section", undefined, "drive-pending");
    page.append(el("h1", title), pending);
    const list = el("ul", undefined, "drive-list");
    const status = el("div", undefined, "drive-status");
    status.setAttribute("role", "status");
    const more = button("more files", () => load(snapshot.next));
    more.hidden = true;
    page.append(list, status, more);
    if (!folder && selector.folder === "root") {
      let pendingRead = false;
      let observed = null;
      view.refreshPending = async () => {
        if (pendingRead) return;
        pendingRead = true;
        try {
          const rows = await read("/api/drive/pending", signal);
          const json = JSON.stringify(rows);
          if (signal.aborted || json === observed) return;
          observed = json;
          const selected = pending.contains(document.activeElement) && document.activeElement;
          const list = el("ul", undefined, "drive-list");
          list.append(...rows.map(originLine));
          if (rows.length) pending.replaceChildren(el("h2", "pending uploads"), list);
          else pending.replaceChildren();
          if (selected) [...list.querySelectorAll("a")].find(node => node.href === selected.href)
            ?.focus({ preventScroll: true });
        } catch (error) {
          if (!signal.aborted && observed === null) pending.textContent = error.login
            ? "sign in to check pending uploads." : "couldn’t check pending uploads.";
        } finally {
          pendingRead = false;
        }
      };
      view.refreshPending();
    }

    const locations = new Map();
    function showLocations(subject) {
      const groups = new Map();
      for (const entry of snapshot.rows.values()) {
        const group = groups.get(entry.file.name) || [];
        group.push(entry);
        groups.set(entry.file.name, group);
      }
      for (const group of groups.values()) {
        if (group.length < 2) continue;
        for (const entry of group) {
          if (entry.details) continue;
          const id = entry.file.id;
          const suffix = group.some(other => other !== entry && other.file.parent === entry.file.parent)
            ? " · " + id.slice(-8) : "";
          const set = text => {
            if (!signal.aborted) entry.place.textContent = " · " + text + suffix;
          };
          if (!entry.file.parent) {
            set("no accessible parent");
            continue;
          }
          const parent = entry.file.parent;
          if (!locations.has(parent))
            locations.set(parent, read("/api/drive/" + subject + "/" + parent, signal));
          entry.details = locations.get(parent)
            .then(item => set([...item.trail.map(part => part.name), item.name].join(" / ")))
            .catch(() => set("location unavailable"));
        }
      }
    }

    async function load(cursor) {
      more.disabled = true;
      status.textContent = snapshot.depth ? "" : "checking drive…";
      const query = new URLSearchParams(selector);
      if (cursor) query.set("cursor", cursor);
      try {
        const result = await read("/api/drive/files?" + query, signal);
        if (signal.aborted) return false;
        if (ref.subject && result.subject !== ref.subject) throw new Error(messages.drive_inaccessible);
        for (const item of result.items) {
          if (snapshot.rows.has(item.id)) continue;
          const row = el("li");
          const open = link(item.name, drivePath({ kind: "drive_file", subject: result.subject, id: item.id }));
          open.dataset.driveId = item.id;
          const details = el("small");
          const place = el("span");
          details.append(typeLabel(item.mime), item.modified ? " · " + time(item.modified) : "", place);
          row.append(open, details);
          list.append(row);
          snapshot.rows.set(item.id, { file: item, open, place });
        }
        showLocations(result.subject);
        snapshot.depth++;
        snapshot.next = result.next || null;
        snapshot.partial ||= result.coverage === "partial";
        more.hidden = !snapshot.next;
        status.textContent = snapshot.partial ? "some locations could not be searched."
          : !snapshot.rows.size && !snapshot.next ? "no files found." : "";
        return true;
      } catch (error) {
        if (!signal.aborted) {
          status.replaceChildren(
            error.login ? "sign in to check your files. " : error.message + " ",
            button(error.login ? "sign in" : error.code === "drive_cursor_stale" ? "restart" : "retry", () => {
              if (error.login) location.reload();
              else if (error.code === "drive_cursor_stale") reload();
              else load(cursor);
            }),
          );
        }
        return false;
      } finally {
        more.disabled = false;
      }
    }

    if (await load(null)) {
      for (let index = 1; !signal.aborted && snapshot.next && index < (previous?.depth || 1); index++)
        if (!await load(snapshot.next)) break;
      if (!signal.aborted && previous) {
        canvas.scrollTop = previous.scroll;
        const row = snapshot.rows.get(previous.row)?.open || [...pending.querySelectorAll("[data-drive-id]")]
          .find(node => node.dataset.driveId === previous.row);
        row?.focus({ preventScroll: true });
      }
    }
  }

  async function showItem(ref, view) {
    const { signal } = view.controller;
    const base = "/api/drive/" + ref.subject + "/" + ref.id;
    const item = await read(base, signal);
    if (signal.aborted) return;
    if (item.mime === folderType) {
      await showList(ref, item, view);
      return;
    }
    page.append(el("h1", item.name));
    const tools = el("nav", undefined, "drive-object-actions");
    tools.setAttribute("aria-label", "file actions");
    const copied = el("span");
    copied.setAttribute("role", "status");
    let attachRef = { kind: "drive_file", subject: ref.subject, id: ref.id };
    tools.append(official("open in drive", item.url),
      button("attach to chat", () => attach(attachRef, item.name)),
      button(ref.page ? "copy page link" : "copy file link", async () => {
        const path = drivePath(ref);
        try {
          await navigator.clipboard.writeText(new URL(path, location.origin).href);
          copied.textContent = "link copied";
        } catch {
          copied.replaceChildren(link("link address", path));
        }
      }), copied);
    page.append(tools);
    if (ref.page && item.mime !== "application/pdf") {
      page.append(el("p", "this file is no longer a pdf."),
        pageLink("open the file", { ...ref, page: null }));
      return;
    }
    if (!item.preview) return;
    const region = el("div", undefined, "drive-preview");
    region.append(el("p", "opening file…"));
    page.append(region);
    try {
      const data = await read(base + "/content?version=" + encodeURIComponent(item.version), signal, true);
      if (signal.aborted) return;
      if (data instanceof Uint8Array) {
        const number = ref.page || 1;
        const result = await pdfPreview(data, number, region, signal);
        if (signal.aborted) return;
        if (result.missing) {
          region.replaceChildren(el("p", "page " + number + " is unavailable in this file."),
            pageLink("open page 1", { ...ref, page: 1 }));
        } else {
          if (ref.page) attachRef = ref;
          if (result.count === 1) return;
          if (number > 1) tools.append(pageLink("previous page", { ...ref, page: number - 1 }));
          tools.append(el("span", "page " + number + " of " + result.count));
          if (number < result.count) tools.append(pageLink("next page", { ...ref, page: number + 1 }));
        }
      } else {
        const url = URL.createObjectURL(data);
        signal.addEventListener("abort", () => URL.revokeObjectURL(url), { once: true });
        const img = el("img");
        img.src = url;
        img.alt = item.name;
        img.onerror = () => {
          if (!signal.aborted) region.textContent = "this image could not be opened.";
        };
        region.replaceChildren(img);
      }
    } catch (error) {
      if (!signal.aborted) region.replaceChildren(
        el("p", error.code ? error.message : "this file could not be previewed."),
        button("retry", reload),
      );
    }
  }

  async function show(path, version) {
    if (active?.path === path && active.version === version) {
      await active.refreshPending?.();
      return;
    }
    close();
    const view = { path, version, controller: new AbortController() };
    active = view;
    const { signal } = view.controller;
    const ref = driveRoute(path);
    if (!ref) {
      page.append(el("p", messages.drive_invalid_input));
      return;
    }
    try {
      if (ref.kind === "files") await showList(ref, null, view);
      else if (ref.kind === "file") {
        const record = await read("/api/drive/origin/" + ref.id, signal);
        if (signal.aborted) return;
        if (record.state === "filed") {
          const canonical = { kind: "drive_file", subject: record.subject, id: record.file_id, page: ref.page };
          const destination = drivePath(canonical);
          if (location.pathname.startsWith("/f/"))
            changeState({ canvasSelection: destination }, destination);
          else changeState({ canvasSelection: destination, canvasAddress: destination });
          view.path = destination;
          await showItem(canonical, view);
        } else {
          page.append(el("h1", record.name || "file"), el("p", originStatus(record.state, record.disposition)));
          if (record.state !== "unavailable") page.append(downloadOrigin(record));
        }
      } else await showItem(ref, view);
    } catch (error) {
      if (!signal.aborted) page.replaceChildren(el("p", error.message),
        button(error.login ? "sign in" : "retry", error.login ? () => location.reload() : reload));
    }
  }

  function reload() {
    if (!active) return;
    const { path, version } = active;
    close();
    show(path, version);
  }

  return { show, close, remember, reload };
}
