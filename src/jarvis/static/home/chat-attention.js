import { el } from "./home-dom.js";

const WAIT = 1000;
const STANDING = 1500;
const ATTENDING = 120000;
const VISIT = 300000;

export const tracked = (message) => message.role === "assistant" && message.source !== "native_progress";

export function instant(at) {
  const fraction = (at.match(/\.(\d+)/)?.[1] || "").padEnd(6, "0");
  return new Date(at).toISOString().slice(0, 19) + fraction;
}

export function chatAttention({ chat, list, ledge, sidebarOpen, icon, live, formatTime,
  stopAttending, newVisit, place, jump, earlier, request, recheck, failure, preservePosition }) {
  const [newButton, owedButton, undo] = ledge.querySelectorAll("button");
  const separator = el("div", undefined, "new-boundary");
  separator.id = "chat-boundary";
  const caption = el("span");
  caption.setAttribute("role", "separator");
  const clear = el("button", "clear");
  clear.type = "button";
  separator.append(caption, clear);

  try {
    localStorage.removeItem("jarvis.home.shown");
  } catch {}

  let known = new Map(), owed = new Set(), samples = new Map(), marks = new Set();
  let previous = 0, lastInput = -Infinity, absentSince = null;
  let wasAttending = false, owedAfter = null, pendingClear = null;
  let focusTarget = null, restoringFocus = false, nextPaint = Infinity;
  let lastAnnouncement = -Infinity, arrivals = new Set();
  let boundary = null, awaitingClearCount = false;
  let newTotal = 0, owedTotal = 0, readNumber = 0, newRead = 0, owedRead = 0, clearRead = 0;
  let reportTimer, reporting = null, writes = 0;
  const reports = new Map();

  const articles = () => [...list.querySelectorAll(":scope > article")];
  const range = document.createRange();
  const viewport = () => {
    const box = chat.getBoundingClientRect();
    const view = window.visualViewport;
    return {
      top: Math.max(box.top, view?.offsetTop ?? 0),
      bottom: Math.min(box.bottom, view ? view.offsetTop + view.height : window.innerHeight),
    };
  };
  const isClearing = (state) => pendingClear && state.order <= pendingClear.order;
  const eligible = (id) => {
    const state = known.get(id);
    return state && state.new !== false && !reports.has(id) && !isClearing(state);
  };
  const fresh = (id) => known.get(id)?.new === true && eligible(id);
  const attending = () => !document.hidden && document.hasFocus() &&
    performance.now() - lastInput < ATTENDING;

  function remember(message) {
    if (!tracked(message)) return;
    if (!known.has(message.id))
      known.set(message.id, { order: instant(message.at) + message.id });
    return known.get(message.id);
  }

  function setTotals(data, number) {
    if (!Number.isSafeInteger(data?.new_total) || data.new_total < 0 ||
        !Number.isSafeInteger(data.owed_total) || data.owed_total < 0)
      throw new Error("incomplete conversation state");
    // A GET issued across a local write cannot tell us whether its count includes
    // that write. Per-message false values can still be merged permanently.
    if (!writes && number > newRead) {
      newRead = number;
      newTotal = data.new_total;
      awaitingClearCount = false;
    }
    if (number > owedRead) {
      owedRead = number;
      owedTotal = data.owed_total;
      if (data.owed) owed = new Set(data.owed);
    }
  }

  async function post(path, body) {
    writes++;
    try {
      const response = await request(path, {
        method: "POST", keepalive: true, signal: AbortSignal.timeout(6000),
        headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      if (response.status !== 204) throw new Error("could not record shown messages");
      newRead = readNumber;
    } finally {
      writes--;
    }
  }

  function scheduleReport() {
    if (reportTimer === undefined) reportTimer = setTimeout(flush, WAIT);
  }

  async function report(ids) {
    for (const id of ids) reports.set(id, true);
    try {
      await post("/api/shown", { ids });
      let unknown = false;
      for (const id of ids) {
        reports.delete(id);
        const state = known.get(id);
        if (!state) continue;
        if (state.new === undefined) unknown = true;
        if (state.new) newTotal = Math.max(0, newTotal - 1);
        state.new = false;
      }
      if (!reports.size) failure(null, "shown");
      if (unknown) recheck();
    } catch (error) {
      failure(error, "shown");
      if (error.login || error.upgrade) reports.clear();
      else {
        for (const id of ids) if (reports.has(id)) reports.set(id, false);
        if (reports.size) scheduleReport();
      }
    }
  }

  function flush() {
    clearTimeout(reportTimer);
    reportTimer = undefined;
    const ids = [...reports.keys()].filter(id => !reports.get(id));
    if (!ids.length) return reporting;
    const batches = [reporting];
    for (let i = 0; i < ids.length; i += 200) batches.push(report(ids.slice(i, i + 200)));
    const complete = Promise.all(batches).then(() => {
      if (reporting === complete) reporting = null;
      preservePosition(paint);
    });
    reporting = complete;
    return reporting;
  }

  function observe(ids) {
    const observed = ids.filter(eligible);
    if (!observed.length) return false;
    for (const id of observed) {
      reports.set(id, false);
      samples.delete(id);
    }
    scheduleReport();
    return true;
  }

  async function settleClear() {
    const clearing = pendingClear;
    if (!clearing?.timeout) return;
    clearTimeout(clearing.timeout);
    clearing.timeout = null;
    const affected = [...known.values()].filter((state) => state.order <= clearing.order);
    preservePosition(paint);
    try {
      await post("/api/shown/clear", { through: clearing.id });
      if (pendingClear !== clearing) return;
      for (const state of affected) state.new = false;
      clearRead = readNumber;
      awaitingClearCount = true;
      failure(null, "clear");
      recheck(true);
    } catch (error) {
      failure(error, "clear");
    } finally {
      if (pendingClear === clearing) {
        pendingClear = null;
        preservePosition(paint);
      }
    }
  }

  clear.onclick = () => {
    const newest = articles().findLast((node) => known.has(node.dataset.messageId));
    if (pendingClear || !newest) return;
    const order = newest.dataset.order;
    const later = [...known].filter(([id, state]) => state.order > order && fresh(id)).length;
    const count = newCount() - later;
    if (count <= 0) return;
    pendingClear = { id: newest.dataset.messageId, order, count, timeout: setTimeout(settleClear, 5000) };
    preservePosition(paint);
  };
  undo.onclick = () => {
    if (!pendingClear?.timeout) return;
    clearTimeout(pendingClear.timeout);
    pendingClear = null;
    preservePosition(paint);
  };

  function offscreen(nodes) {
    const { top, bottom } = viewport();
    const above = [], below = [];
    for (const node of nodes) {
      const box = node.getBoundingClientRect();
      if (box.bottom <= top) above.push(node);
      else if (box.top >= bottom) below.push(node);
    }
    return { above, below };
  }

  newButton.onclick = async () => {
    if (newButton.getAttribute("aria-disabled") === "true") return;
    const targets = offscreen(articles().filter((node) =>
      fresh(node.dataset.messageId) && marks.has(node.dataset.messageId)));
    const target = targets.below[0] || targets.above.at(-1);
    if (target) place(target);
    else {
      const before = new Set(articles().map((node) => node.dataset.messageId));
      while (await earlier()) {
        const older = articles().findLast((node) =>
          !before.has(node.dataset.messageId) && fresh(node.dataset.messageId));
        if (older) {
          place(older);
          break;
        }
      }
    }
  };
  owedButton.onclick = () => {
    if (owedButton.getAttribute("aria-disabled") === "true") return;
    const loaded = new Map(articles().map((node) => [node.dataset.messageId, node]));
    const { above, below } = offscreen([...loaded.values()]);
    const outside = new Set([...above, ...below]);
    const candidates = [...owed].filter((id) => !loaded.has(id) || outside.has(loaded.get(id)));
    const next = candidates[(candidates.indexOf(owedAfter) + 1) % candidates.length];
    if (!next) return;
    owedAfter = next;
    if (loaded.has(next)) place(loaded.get(next));
    else jump(next);
  };

  function ledgeAction(control, available, label, empty) {
    control.hidden = !available && document.activeElement !== control;
    const disabled = String(!available);
    if (control.getAttribute("aria-disabled") !== disabled)
      control.setAttribute("aria-disabled", disabled);
    const target = control === newButton ? control.lastElementChild : control;
    const text = available ? label : empty;
    if (target.textContent !== text) target.textContent = text;
  }

  function newCount() {
    if (pendingClear || awaitingClearCount) return [...known.keys()].filter(fresh).length;
    let count = newTotal;
    for (const id of reports.keys()) if (known.get(id)?.new) count--;
    return Math.max(0, count);
  }

  function paintCounts(total) {
    const state = owedTotal ? "owed" : total ? "new" : "rest";
    const href = "/static/home/chat-" + state + ".svg";
    if (icon.getAttribute("href") !== href) icon.setAttribute("href", href);
    const count = sidebarOpen.querySelector(".chat-count");
    count.hidden = !total;
    if (count.textContent !== String(total)) count.textContent = total;
    const accessibleName = "open chat" + (total ? ", " + total + " new" : "");
    if (sidebarOpen.getAttribute("aria-label") !== accessibleName)
      sidebarOpen.setAttribute("aria-label", accessibleName);
  }

  function paint() {
    const now = performance.now();
    nextPaint = Infinity;
    const nodes = articles();
    const loadedNew = [];
    const total = newCount();
    for (const node of nodes) {
      const id = node.dataset.messageId;
      const current = fresh(id);
      const label = node.querySelector(".owed-label");
      const marker = node.querySelector(".new-mark");
      if (!marker) continue;
      label.hidden = !owed.has(id);
      if (eligible(id)) {
        let sample = samples.get(id);
        if (!sample) {
          sample = { since: null, first: 0, last: 0, focus: 0, visible: [] };
          samples.set(id, sample);
        }
        if (current) {
          loadedNew.push(node);
          sample.since ??= now;
          const stands = sample.since + STANDING;
          if (now >= stands) marks.add(id);
          else nextPaint = Math.min(nextPaint, stands);
        }
      }
      marker.hidden = !marks.has(id);
      marker.classList.toggle("shown", !current);
      node.querySelector(".new-prefix").hidden = !current || marker.hidden;
    }

    if (boundary) {
      const start = document.getElementById("msg-" + boundary.id);
      if (start && separator.nextSibling !== start) list.insertBefore(separator, start);
      separator.classList.toggle("dry", total === 0);
      clear.setAttribute("aria-disabled", String(total === 0 || Boolean(pendingClear)));
    }

    paintCounts(total);

    const { above, below } = offscreen(loadedNew.filter((node) => marks.has(node.dataset.messageId)));
    const aboveCount = above.length + Math.max(0, total - loadedNew.length);
    const offscreenCount = aboveCount + below.length;
    const newLabel = aboveCount && below.length ? " new, above and below" : aboveCount ? " new above" : " new below";
    ledgeAction(newButton, offscreenCount > 0 && !pendingClear, offscreenCount + newLabel,
      "no new messages off screen");
    const owedLabel = owed.size + (owed.size === 1 ? " needs a reply" : " need a reply");
    ledgeAction(owedButton, owed.size > 0, owedLabel, "nothing needs a reply");
    ledgeAction(undo, Boolean(pendingClear?.timeout), pendingClear?.count + " cleared · undo", "undo unavailable");
    ledge.hidden = newButton.hidden && owedButton.hidden && undo.hidden;

    if (arrivals.size && now - lastAnnouncement >= 10000 && !document.hidden) {
      const needed = [...arrivals].filter((id) => owed.has(id)).length;
      live.textContent = arrivals.size + " new from jarvis" +
        (needed ? ", " + needed + (needed === 1 ? " needs a reply" : " need a reply") : "");
      arrivals.clear();
      lastAnnouncement = now;
    } else if (arrivals.size && !document.hidden)
      nextPaint = Math.min(nextPaint, lastAnnouncement + 10000);
  }

  function endpoints(node, viewport) {
    const reader = node.reader;
    const body = document.createTreeWalker(reader, NodeFilter.SHOW_TEXT);
    let firstLine;
    for (let text = body.nextNode(); text && !firstLine; text = body.nextNode()) {
      if (!text.textContent.trim() || text.parentElement.closest('[aria-hidden="true"]')) continue;
      range.selectNodeContents(text);
      firstLine = [...range.getClientRects()].find((rect) => rect.height && rect.width);
    }
    firstLine ??= node.querySelector(".stamp").getBoundingClientRect();
    const end = node.controls?.lastElementChild || reader;
    range.selectNodeContents(end);
    const trailing = end.lastElementChild;
    if (trailing?.getAttribute("aria-hidden") === "true") range.setEndBefore(trailing);
    const lastLine = [...range.getClientRects()].findLast((rect) => rect.height && rect.width)
      ?? end.getBoundingClientRect();
    return [firstLine, lastLine].map((line) =>
      line.height > 0 && line.top >= viewport.top && line.bottom <= viewport.bottom);
  }

  // Both observations must bracket the interval. Discard dropped frames and elapsed
  // time across a layout or visibility change.
  function sample() {
    const now = performance.now();
    const active = attending();
    if (!active && wasAttending) {
      absentSince = Math.min(now, lastInput + ATTENDING);
      stopAttending();
    }
    if (active && absentSince !== null) {
      const visiting = now - absentSince >= VISIT;
      absentSince = null;
      if (visiting) {
        samples.clear();
        marks = new Set([...marks].filter(fresh));
        newVisit();
        nextPaint = now;
      }
    }
    const elapsed = active && wasAttending && now - previous <= 250 ? now - previous : 0;
    previous = now;
    wasAttending = active;
    if (!samples.size) return false;
    if (!active || !chat.clientHeight) {
      for (const state of samples.values()) {
        state.visible = [];
        state.focus = 0;
      }
      return false;
    }
    const bounds = viewport();
    const ready = [];
    for (const node of articles()) {
      const id = node.dataset.messageId;
      const state = samples.get(id);
      if (!state) continue;
      if (!eligible(id)) {
        state.visible = [];
        state.focus = 0;
        continue;
      }
      const box = node.getBoundingClientRect();
      const [first, last] = box.bottom > bounds.top && box.top < bounds.bottom
        ? endpoints(node, bounds) : [false, false];
      const focus = focusTarget === document.activeElement && node.contains(focusTarget);
      if (first && state.visible[0]) state.first += elapsed;
      if (last && state.visible[1]) state.last += elapsed;
      if (focus && state.visible[2] && elapsed) state.focus += elapsed;
      else state.focus = 0;
      state.visible = [first, last, focus];
      if ((state.first >= WAIT && state.last >= WAIT) || state.focus >= WAIT) ready.push(id);
    }
    return observe(ready);
  }

  function update() {
    sample();
    preservePosition(paint);
  }
  setInterval(() => {
    if (document.hidden) return;
    if (sample() || performance.now() >= nextPaint) preservePosition(paint);
  }, 100);
  const input = (event) => {
    if (!event.isTrusted) return;
    const now = performance.now();
    if (wasAttending && now - lastInput >= ATTENDING) sample();
    lastInput = now;
    if (sample()) preservePosition(paint);
  };
  for (const event of ["pointerdown", "pointermove", "keydown", "wheel", "touchstart"])
    document.addEventListener(event, input, { capture:true, passive:true });
  for (const event of ["focus", "blur"]) window.addEventListener(event, update);
  const leave = () => {
    settleClear();
    flush();
  };
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) leave();
    update();
  });
  window.addEventListener("pagehide", leave);
  ledge.addEventListener("focusout", () => queueMicrotask(() => preservePosition(paint)));
  chat.addEventListener("scroll", update, { passive:true });
  const resize = () => {
    for (const state of samples.values()) state.visible = [];
    update();
  };
  new ResizeObserver(resize).observe(chat);
  window.visualViewport?.addEventListener("resize", resize);
  chat.addEventListener("focusin", (event) => {
    if (!restoringFocus) focusTarget = event.target;
    update();
  });
  chat.addEventListener("focusout", (event) => {
    const article = focusTarget?.closest("article");
    const state = samples.get(article?.dataset.messageId);
    if (state && !restoringFocus && !article.contains(event.relatedTarget)) {
      state.focus = 0;
      state.visible[2] = false;
    }
  });
  list.addEventListener("click", (event) => {
    if (!event.isTrusted || !attending()) return;
    const article = event.target.closest("a, button")?.closest("article[data-message-id]");
    if (!article) return;
    observe([article.dataset.messageId]);
    preservePosition(paint);
  }, true);
  return {
    attending,
    fresh,
    update,
    flush,
    reading() { return ++readNumber; },
    totals(data, number) {
      setTotals(data, number);
      paintCounts(newCount());
    },
    page(data, number) {
      setTotals(data, number);
      const freshIds = new Set(data.new);
      for (const message of data.items) {
        const state = remember(message);
        if (!state || state.new === false ||
            state.new && writes && (reports.has(message.id) || isClearing(state))) continue;
        const current = freshIds.has(message.id);
        // An earlier read can describe a newly loaded row as new before the clear.
        if (current && number <= clearRead) continue;
        state.new = current;
        if (!state.new) samples.delete(message.id);
      }
    },
    olderStale(total) {
      return total < articles().filter((node) => known.get(node.dataset.messageId)?.new).length;
    },
    beforeLayoutChange() {
      for (const state of samples.values()) state.visible = [];
    },
    remember,
    announce(ids) { for (const id of ids) if (fresh(id)) arrivals.add(id); },
    clearProjection() {
      clearTimeout(pendingClear?.timeout);
      clearTimeout(reportTimer);
      reportTimer = undefined;
      pendingClear = null;
      reports.clear();
      known.clear();
      owed.clear();
      newTotal = owedTotal = 0;
      awaitingClearCount = false;
      samples.clear();
      marks.clear();
      arrivals.clear();
      boundary = null;
      separator.remove();
      live.textContent = "";
      paint();
    },
    render(node, message) {
      node.dataset.messageId = message.id;
      if (!tracked(message)) return;
      const stamp = node.querySelector(".stamp");
      const label = el("span", "needs a reply", "owed-label");
      label.hidden = !owed.has(message.id);
      stamp.firstElementChild.after(label);
      const marker = el("span", undefined, "new-mark");
      marker.setAttribute("aria-hidden", "true");
      marker.hidden = !marks.has(message.id);
      marker.classList.toggle("shown", !fresh(message.id));
      const prefix = el("span", "new", "sr-only new-prefix");
      prefix.hidden = marker.hidden || !fresh(message.id);
      node.prepend(marker, prefix);
    },
    openBoundary(node) {
      separator.remove();
      boundary = null;
      if (!node) return;
      const before = node.previousElementSibling;
      const text = before ? "new since " + formatTime(before.dataset.at) : "new";
      separator.dataset.order = node.dataset.order;
      boundary = { id:node.dataset.messageId };
      caption.setAttribute("aria-label", text);
      caption.textContent = text;
      paint();
    },
    restoreFocus(control, previousFocus) {
      if (!control) return;
      restoringFocus = true;
      control.focus({ preventScroll:true });
      restoringFocus = false;
      if (focusTarget === previousFocus) focusTarget = control;
    },
    sent() {
      if (!attending() || !chat.clientHeight) return;
      const bounds = viewport();
      observe(articles().filter((node) => {
        const box = node.getBoundingClientRect();
        return eligible(node.dataset.messageId) && box.top >= bounds.top && box.bottom <= bounds.bottom;
      }).map((node) => node.dataset.messageId));
      preservePosition(paint);
    },
  };
}
