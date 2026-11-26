import { el, link, button } from "./home-dom.js";
import { parseMessage, renderMarkdown, updateCitations } from "./chat-reader.js";

function evidence(value, time) {
  const body = document.createDocumentFragment();
  const headings = { preview: "mail preview", excerpt: "mail excerpt", event: "calendar event" };
  body.append(el("p", headings[value.coverage.kind] + " · seen " + time(value.observed_at, "UTC"), "secondary"));
  const fields = el("dl");
  for (const field of value.fields) fields.append(el("dt", field.label), el("dd", field.value));
  body.append(fields);
  if (value.coverage.passage === "missing") body.append(el("p", "exact passage unavailable"));
  for (const omission of value.coverage.omissions) body.append(el("p", omission, "secondary"));
  const decoder = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true });
  let previous, paragraph, stamps;
  for (const segment of value.segments) {
    if (!previous || previous.part !== segment.part || previous.digest !== segment.digest || previous.end !== segment.start) {
      paragraph = el("p", undefined, "literal");
      stamps = el("small");
      body.append(stamps, paragraph);
    }
    const piece = el("span");
    if (segment.observed_at) {
      piece.title = "seen " + time(segment.observed_at, "UTC");
      if (segment.observed_at !== value.observed_at && (!stamps.textContent || previous?.observed_at !== segment.observed_at)) {
        if (stamps.textContent) stamps.append(" · ");
        stamps.append(piece.title);
      }
    }
    const focus = value.focus;
    if (focus && focus.part === segment.part && focus.digest === segment.digest &&
        focus.start < segment.end && focus.end > segment.start) {
      const bytes = new TextEncoder().encode(segment.text);
      const start = Math.max(0, focus.start - segment.start);
      const end = Math.min(bytes.length, focus.end - segment.start);
      piece.append(decoder.decode(bytes.slice(0, start)), el("mark", decoder.decode(bytes.slice(start, end))),
        decoder.decode(bytes.slice(end)));
    } else piece.textContent = segment.text;
    paragraph.append(piece);
    previous = segment;
  }
  if (value.original_url) {
    const url = new URL(value.original_url);
    const gmail = value.kind === "mail";
    if (url.origin === (gmail ? "https://mail.google.com" : "https://calendar.google.com") &&
        !url.username && !url.password) {
      const original = link("open current in " + (gmail ? "gmail" : "calendar"), url.href);
      original.target = "_blank";
      original.rel = "noopener noreferrer";
      body.append(original);
    }
  }
  return body;
}

export function bindInspection({ object, request, time, restore, restoring, refresh }) {
  let active = null;
  function close() {
    if (!active) return;
    active.controller.abort();
    active.sheet.remove();
    active = null;
  }

  async function show(path, route) {
    if (active?.path !== path) {
      close();
      const from = history.state.inspectionOrigin;
      const back = link(from?.table ? "back to table" : "back to message", from?.table || "/m/" + route.message);
      if (from) back.addEventListener("click", e => {
        if (!e.button && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) {
          e.preventDefault();
          history.back();
        }
      });
      const title = el("h1", route.kind === "source" ? "cited source" : "expanded table");
      title.tabIndex = -1;
      const content = el("div");
      const sheet = el("section");
      sheet.id = "inspection";
      sheet.append(back, title, content);
      object.replaceChildren(sheet);
      active = { path, route, sheet, content, controller: new AbortController(), rendered: null };
      content.append(el("p", route.kind === "source" ? "checking source…" : "opening table…"));
      if (!restoring() && (document.activeElement === document.body || document.activeElement?.dataset.readerAnchor))
        title.focus({ preventScroll: true });
    }
    const view = active;
    // Poll source access while open. An unchanged response keeps the reader's selection and position.
    if ((route.kind === "table" && view.rendered === "table") || view.pending) return;
    view.pending = true;
    const api = "/api/messages/" + route.message + (route.kind === "source" ? "/sources/" + route.number : "");
    try {
      const signal = AbortSignal.any([view.controller.signal, AbortSignal.timeout(8000)]);
      const response = await request(api, { signal });
      if (!response.ok && response.status !== 404) throw new Error("read failed");
      const data = response.ok ? await response.json() : null;
      if (view !== active || document.hidden) return;
      if (route.kind === "table" && data) {
        const parsed = parseMessage(data.text);
        const digest = await parsed.tables[route.number - 1]?.digest;
        if (view !== active || document.hidden) return;
        if (digest === route.digest) {
          view.content.replaceChildren(renderMarkdown(data, parsed, route.number));
          view.rendered = "table";
          restore();
          return;
        }
      }
      if (route.kind === "source" && data?.state === "available") {
        const signature = JSON.stringify(data);
        if (view.rendered !== signature) {
          const first = !view.rendered;
          view.content.replaceChildren(evidence(data, time));
          view.rendered = signature;
          if (first) view.content.querySelector("mark")?.scrollIntoView({ block: "nearest" });
        }
      } else {
        if (view.rendered !== "unavailable") {
          view.content.replaceChildren(el("p", route.kind + " unavailable"));
          if (route.kind === "source" && response.ok) view.content.append(button("retry", refresh));
        }
        view.rendered = "unavailable";
      }
    } catch {
      if (view !== active || document.hidden) return;
      if (view.rendered !== "failed") {
        view.content.replaceChildren(el("p", "couldn’t check this " + route.kind + "."), button("retry", refresh));
        view.rendered = "failed";
      }
    } finally { view.pending = false; }
  }
  function updateTable(m) {
    if (active?.rendered === "table" && active.route.message === m.id) updateCitations(active.content, m);
  }
  return { close, show, updateTable };
}
