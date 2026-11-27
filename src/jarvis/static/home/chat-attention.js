import { el } from "./home-dom.js";

const KEY = "jarvis.home.shown";
const WAIT = 1000;
const STANDING = 1500;
const ATTENDING = 120000;
const VISIT = 300000;
const LIMIT = 2000;

export const tracked = (message) => message.role === "assistant" && message.source !== "native_progress";

export function instant(at) {
  const fraction = (at.match(/\.(\d+)/)?.[1] || "").padEnd(6, "0");
  return new Date(at).toISOString().slice(0, 19) + fraction;
}

export function precedingArticle(node) {
  let before = node.previousElementSibling;
  while (before && !before.matches("article")) before = before.previousElementSibling;
  return before;
}

export function chatAttention({ chat, list, ledge, sidebarOpen, icon, live, formatTime,
  stopAttending, newVisit, place, jump, earlier, failure, preservePosition }) {
  const [newButton, owedButton, undo] = ledge.querySelectorAll("button");
  const separator = el("div", undefined, "new-boundary");
  separator.id = "chat-boundary";
  const caption = el("span");
  caption.setAttribute("role", "separator");
  const clear = el("button", "clear");
  clear.type = "button";
  separator.append(caption, clear);

  let start = instant(new Date().toISOString());
  let shown = new Map();
  try {
    const stored = JSON.parse(localStorage.getItem(KEY));
    if (stored) {
      ({ start } = stored);
      shown = new Map(stored.shown);
    } else localStorage.setItem(KEY, JSON.stringify({ start, shown: [] }));
  } catch (error) {
    failure(error);
  }

  let known = new Map(), owed = new Set(), samples = new Map(), marks = new Set();
  let previous = 0, lastInput = -Infinity, absentSince = null;
  let wasAttending = false, owedAfter = null, pendingClear = null;
  let focusTarget = null, restoringFocus = false, nextPaint = Infinity, retryAt = 0;
  let lastAnnouncement = -Infinity, arrivals = new Set();
  let boundary = null;

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
  const afterStart = (message) => instant(message.at) > start;
  const isNew = (message) => tracked(message) && afterStart(message) && !shown.has(message.id);
  const isClearing = (id) => pendingClear && known.get(id) <= pendingClear.through;
  const fresh = (id) => known.get(id) > start && !shown.has(id) && !isClearing(id);
  const attending = () => !document.hidden && document.hasFocus() &&
    performance.now() - lastInput < ATTENDING;

  function write(nextStart, nextShown) {
    try {
      const persisted = JSON.parse(localStorage.getItem(KEY));
      if (persisted?.start > nextStart) nextStart = persisted.start;
      const ordered = [...new Map([...(persisted?.shown || []), ...nextShown])]
        .filter(([, at]) => at > nextStart);
      if (ordered.length > LIMIT) {
        ordered.sort((a, b) => a[1].localeCompare(b[1]));
        nextStart = ordered[ordered.length - LIMIT - 1][1];
      }
      const retained = ordered.filter(([, at]) => at > nextStart);
      localStorage.setItem(KEY, JSON.stringify({ start:nextStart, shown:retained }));
      start = nextStart;
      shown = new Map(retained);
    } catch (error) {
      retryAt = performance.now() + WAIT;
      failure(error);
      return false;
    }
    for (const [id, at] of known) if (at <= start) known.delete(id);
    failure(null);
    return true;
  }

  function observe(ids) {
    const observed = ids.filter(fresh);
    if (!observed.length || performance.now() < retryAt) return false;
    if (!write(start, new Map([...shown, ...observed.map((id) => [id, known.get(id)])])))
      return false;
    for (const id of observed) samples.delete(id);
    return true;
  }

  function settleClear() {
    if (!pendingClear) return;
    clearTimeout(pendingClear.timeout);
    const { through } = pendingClear;
    pendingClear = null;
    write(through > start ? through : start, shown);
    preservePosition(paint);
  }

  clear.onclick = () => {
    const newest = articles().findLast((node) => known.has(node.dataset.messageId));
    if (pendingClear || !newest) return;
    const through = known.get(newest.dataset.messageId);
    const count = [...known].filter(([id, at]) => at <= through && fresh(id)).length;
    if (!count) return;
    pendingClear = { through, count, timeout: setTimeout(settleClear, 5000) };
    preservePosition(paint);
  };
  undo.onclick = () => {
    if (!pendingClear) return;
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

  function paint() {
    const now = performance.now();
    nextPaint = Infinity;
    const nodes = articles();
    const loadedNew = [];
    let total = 0;
    for (const id of known.keys()) if (fresh(id)) total++;
    for (const node of nodes) {
      const id = node.dataset.messageId;
      const current = fresh(id);
      const label = node.querySelector(".owed-label");
      const marker = node.querySelector(".new-mark");
      if (!marker) continue;
      label.hidden = !owed.has(id);
      if (current) {
        loadedNew.push(node);
        let sample = samples.get(id);
        if (!sample) {
          sample = { since: now, first: 0, last: 0, focus: 0, visible: [] };
          samples.set(id, sample);
        }
        const stands = sample.since + STANDING;
        if (now >= stands) marks.add(id);
        else nextPaint = Math.min(nextPaint, stands);
      }
      marker.hidden = !marks.has(id);
      marker.classList.toggle("shown", !current);
      node.querySelector(".new-prefix").hidden = !current || marker.hidden;
    }

    if (boundary) {
      const start = document.getElementById("msg-" + boundary.id);
      const first = start?.previousElementSibling?.matches(".day-head") ? start.previousElementSibling : start;
      if (first && separator.nextSibling !== first) list.insertBefore(separator, first);
      separator.classList.toggle("dry", total === 0);
      clear.setAttribute("aria-disabled", String(total === 0 || Boolean(pendingClear)));
    }

    const state = owed.size ? "owed" : total ? "new" : "rest";
    const href = "/static/home/chat-" + state + ".svg";
    if (icon.getAttribute("href") !== href) icon.setAttribute("href", href);
    const count = sidebarOpen.querySelector(".chat-count");
    count.hidden = !total;
    if (count.textContent !== String(total)) count.textContent = total;
    const accessibleName = "open chat" + (total ? ", " + total + " new" : "");
    if (sidebarOpen.getAttribute("aria-label") !== accessibleName)
      sidebarOpen.setAttribute("aria-label", accessibleName);

    const { above, below } = offscreen(loadedNew.filter((node) => marks.has(node.dataset.messageId)));
    const aboveCount = above.length + Math.max(0, total - loadedNew.length);
    const offscreenCount = aboveCount + below.length;
    const newLabel = aboveCount && below.length ? " new, above and below" : aboveCount ? " new above" : " new below";
    ledgeAction(newButton, offscreenCount > 0 && !pendingClear, offscreenCount + newLabel,
      "no new messages off screen");
    const owedLabel = owed.size + (owed.size === 1 ? " needs a reply" : " need a reply");
    ledgeAction(owedButton, owed.size > 0, owedLabel, "nothing needs a reply");
    ledgeAction(undo, Boolean(pendingClear), pendingClear?.count + " cleared · undo", "undo unavailable");
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
      if (!fresh(id)) {
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
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) settleClear();
    update();
  });
  window.addEventListener("pagehide", settleClear);
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
  window.addEventListener("storage", (event) => {
    if (event.key !== KEY || !event.newValue) return;
    const newest = JSON.parse(event.newValue);
    if (newest.start > start) start = newest.start;
    shown = new Map([...shown, ...newest.shown].filter(([, at]) => at > start));
    preservePosition(paint);
  });

  return {
    afterStart,
    isNew,
    attending,
    fresh,
    update,
    beforeLayoutChange() {
      for (const state of samples.values()) state.visible = [];
    },
    receive(rows, added = []) {
      for (const message of rows)
        if (tracked(message) && afterStart(message)) known.set(message.id, instant(message.at));
      for (const id of added) if (fresh(id)) arrivals.add(id);
    },
    setOwed(ids) { owed = new Set(ids); },
    clearProjection() {
      clearTimeout(pendingClear?.timeout);
      pendingClear = null;
      known.clear();
      owed.clear();
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
      const before = precedingArticle(node);
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
        return fresh(node.dataset.messageId) && box.top >= bounds.top && box.bottom <= bounds.bottom;
      }).map((node) => node.dataset.messageId));
      preservePosition(paint);
    },
  };
}
