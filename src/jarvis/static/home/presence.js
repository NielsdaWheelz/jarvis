import { el } from "./home-dom.js";

const verbs = {
  gmail: ["reading mail", "writing mail"],
  calendar: ["checking the calendar", "updating the calendar"],
  drive: ["reading drive", "writing to drive"],
  memory: ["searching memory", "taking a note"],
  work: ["checking todos", "updating todos"],
  maps: ["checking maps"],
  web: ["reading the web"],
  agent: ["working with a worker"],
  receipt: ["rereading a source"],
  shell: ["running a command"],
};
const triggers = {
  mail: "from mail",
  todo: "from your todos",
  result: "a result came back",
  recovery: "recovering",
};
const states = new Set(["idle", "queued", "working", "paused", "standby", "retrying"]);
const interruptions = new Set(["paused", "standby", "retrying"]);
export const time = at => new Date(at).toLocaleTimeString([], {
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});

// Literata's tabular substitution selects lining figures. Give its old-style
// figures equal cells, preserving the literal clock string.
export function stampDigits(node, value) {
  if (node.textContent !== value) {
    node.replaceChildren(...Array.from(value, char =>
      /\p{Nd}/u.test(char) ? el("span", char, "stamp-digit") : char));
  }
}

const lastHeard = at => "last heard " + (at === null ? "—" : time(at));

function workWords(work) {
  if (!work) return "working";
  if (!work.activity) return "thinking";
  const words = Object.hasOwn(verbs, work.activity) ? verbs[work.activity] : [];
  return (work.mode === "write" ? words[1] : null) || words[0] || "working";
}

function interruption(snapshot, state) {
  const when = snapshot.until && time(snapshot.until);
  if (state === "paused") return snapshot.draining ? "pausing" : "paused";
  if (state === "retrying") return when ? "next try " + when : "retrying";
  if (snapshot.reason === "quota") return "out of quota" + (when ? " · reset reported " + when : "");
  return "can't reach the model" + (when ? " · next try " + when : "");
}

function fade(node, from, to, duration) {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  return node.animate([{ opacity: from }, { opacity: to }], { duration: reduced ? 120 : duration, fill: "both" });
}

function headerState(snapshot, you, stale, heard) {
  if (stale) return ["none", lastHeard(heard), "offline", ""];
  const state = snapshot?.state;
  const work = snapshot?.work;
  if (state === "paused") {
    const words = interruption(snapshot, state);
    return ["stopped", words, state, "jarvis is " + words];
  }
  if (snapshot?.owed.length) return ["owed", "waiting on you", "¶ waiting on you", "jarvis is waiting on you"];
  if (state === "working" && work.triggers.includes("you")) {
    const words = workWords(work);
    return ["owner", words, words, "jarvis is " + words + " for you"];
  }
  if (state === "standby" || state === "retrying") {
    const words = interruption(snapshot, state);
    const title = state === "retrying" ? state : snapshot.reason === "quota" ? "out of quota" : "can't reach the model";
    const label = state === "retrying" ? "jarvis is retrying · " + words : "jarvis " + (snapshot.reason === "quota" ? "is " : "") + words;
    return ["stopped", words, title, label];
  }
  if (state === "working") {
    const activity = workWords(work);
    const trigger = work.triggers.find(trigger => Object.hasOwn(triggers, trigger));
    const words = trigger ? triggers[trigger] + " · " + activity : activity;
    return ["silent", words, "", "jarvis is " + activity + (trigger ? " · " + triggers[trigger] : "")];
  }
  if (snapshot?.workers > 0) {
    const count = snapshot.workers;
    const words = count + (count === 1 ? " worker running" : " workers running");
    return ["silent", words, "", "jarvis has " + words];
  }
  if (you?.state === "queued") return ["queued", "", "received", "jarvis received your message"];
  return ["none", "", "", ""];
}

export function bindPresence({ request, openOwed, keepBottom, receiptPending }) {
  const wordmark = document.querySelector(".wordmark");
  const workspace = wordmark.closest(".bar");
  const back = document.getElementById("chat-bar");
  const slot = document.getElementById("presence-slot");
  const mark = document.getElementById("presence-mark");
  const legend = document.getElementById("presence-legend");
  const description = document.getElementById("presence-description");
  const announcer = document.getElementById("presence-announcement");
  const tail = document.getElementById("presence-tail");
  const elapsed = tail.querySelector("time");
  const caption = tail.querySelector(".presence-caption");
  const point = caption.querySelector(".presence-point");
  const words = caption.querySelector(".presence-words");
  let snapshot = null, etag = null, heard = null, failures = 0, stale = false;
  let requestVersion = 0, flight = null, supported = true, authLost = false;
  let receipt = false, beat = "b", exit = null, tailHeard = null, clock = null, tailFailures = 0;
  let lastOwed, crossing = null, confirmationDeadline = null;
  let elapsedRunning = false;

  function renderElapsed() {
    if (!elapsedRunning || tail.hidden || document.hidden) return;
    const whole = Math.max(0, Math.floor((clock.elapsed + performance.now() - clock.at) / 1000));
    const value = whole < 20 ? "" : Math.floor(whole / 60) + ":" + String(whole % 60).padStart(2, "0");
    stampDigits(elapsed, value);
  }
  setInterval(renderElapsed, 500);

  function setWords(value) {
    if (words.textContent === value) return;
    if (!tail.hidden && words.textContent && !document.hidden) {
      const prior = el("span", words.textContent, "presence-prior");
      prior.setAttribute("aria-hidden", "true");
      words.after(prior);
      fade(prior, 1, 0, 140).onfinish = () => prior.remove();
      crossing?.cancel();
      crossing = fade(words, 0, 1, 220);
    }
    words.textContent = value;
  }

  function showTail(data, you, confirmed) {
    if (exit) {
      exit.cancel();
      exit = null;
    }
    const ownerWork = data?.work?.triggers.includes("you") ? data.work : null;
    const state = you.state;
    const queuedAfter = data?.state === "working" || you.ahead > 0;
    const value = state === "working" ? workWords(ownerWork)
      : state === "queued" ? (queuedAfter ? "received · after current work" : "received")
      : interruption(data, state);
    point.dataset.point = state === "working" ? (ownerWork ? "owner" : "stopped")
      : state === "queued" ? "queued" : "stopped";
    point.dataset.beat = confirmed ? beat : point.dataset.beat || "";
    tail.removeAttribute("data-stale");
    tailHeard = heard;
    tailFailures = 0;
    setWords(value);
    elapsedRunning = Boolean(ownerWork && (state === "working" || state === "paused"));
    if (elapsedRunning) {
      if (!clock || clock.since !== ownerWork.since) {
        clock = {
          since: ownerWork.since,
          at: performance.now(),
          elapsed: Date.parse(data.as_of) - Date.parse(ownerWork.since),
        };
      }
    } else stampDigits(elapsed, "");
    if (tail.hidden) keepBottom(() => { tail.hidden = false; });
    renderElapsed();
  }

  function staleTail() {
    if (tail.hidden) return;
    elapsedRunning = false;
    point.dataset.point = "none";
    tail.dataset.stale = "";
    crossing?.cancel();
    caption.querySelectorAll(".presence-prior").forEach(node => node.remove());
    words.textContent = lastHeard(tailHeard);
  }

  function paint(confirmed = false) {
    const data = supported ? snapshot : null;
    const waiting = !receipt && receiptPending();
    const you = receipt ? { state: "queued", ahead: 0 } : waiting ? null : data?.you;
    const [shape, text, title, sentence] = headerState(data, you, stale, heard);
    if (confirmed) beat = beat === "a" ? "b" : "a";
    mark.dataset.point = shape;
    if (confirmed) mark.dataset.beat = beat;
    if (sentence && mark.getAttribute("aria-label") !== sentence) mark.setAttribute("aria-label", sentence);
    if (!sentence && mark.hasAttribute("aria-label")) mark.removeAttribute("aria-label");
    if (description.textContent !== sentence) description.textContent = sentence;
    if (legend.textContent !== text) legend.textContent = text;
    legend.hidden = !text;
    legend.dataset.point = shape;
    document.body.toggleAttribute("data-presence-stale", stale);
    document.title = document.hidden || !supported ? "jarvis"
      : shape === "silent" ? "· jarvis" : title ? title + " · jarvis" : "jarvis";
    if (stale) staleTail();
    else if (you) showTail(data, you, confirmed);
    else if (!waiting) {
      elapsedRunning = false;
      point.removeAttribute("data-beat");
    }
  }

  function invalidate() {
    requestVersion++;
    flight = null;
  }

  function cancelDeadline() {
    clearTimeout(confirmationDeadline);
    confirmationDeadline = null;
  }

  function goStale() {
    cancelDeadline();
    if (!stale) {
      stale = true;
      paint();
    }
  }

  function read(fresh = false) {
    if (document.hidden || authLost || !supported) return Promise.resolve(null);
    if (fresh) invalidate();
    if (flight) return flight;
    if (!stale && !confirmationDeadline) confirmationDeadline = setTimeout(goStale, 9000);
    const version = requestVersion;
    flight = (async () => {
      try {
        const response = await request("/api/presence", {
          headers: etag ? { "If-None-Match": etag } : {},
          signal: AbortSignal.timeout(2700),
        });
        if (version !== requestVersion || document.hidden) return null;
        if (response.status === 404) {
          supported = false;
          cancelDeadline();
          snapshot = etag = null;
          failures = 0;
          stale = receipt = false;
          keepBottom(() => { tail.hidden = true; });
          paint();
          return null;
        }
        const next = response.status === 304 ? snapshot : response.ok ? await response.json() : null;
        if (version !== requestVersion || document.hidden) return null;
        const you = next?.you;
        if (!next || !states.has(next.state) || !Number.isFinite(Date.parse(next.as_of)) ||
            !Array.isArray(next.owed) || (next.state === "working" && !Array.isArray(next.work?.triggers)) ||
            (you !== null && (!states.has(you?.state) || you.state === "idle" ||
              !Number.isSafeInteger(you.ahead) || you.ahead < 0)))
          throw Error("invalid presence response");
        if (interruptions.has(next.state) && next.state !== snapshot?.state)
          announcer.textContent = interruption(next, next.state) + ".";
        snapshot = next;
        if (response.status !== 304) etag = response.headers.get("ETag");
        heard = Date.now();
        failures = 0;
        stale = receipt = false;
        cancelDeadline();
        confirmationDeadline = setTimeout(goStale, 9000);
        paint(true);
        return snapshot;
      } catch (error) {
        if (version === requestVersion && (error.login || ++failures >= 3)) goStale();
        return null;
      } finally {
        if (version === requestVersion) flight = null;
      }
    })();
    return flight;
  }

  function chatChecked(readSnapshot, reply, arriving) {
    if (!readSnapshot || readSnapshot !== snapshot || readSnapshot.you || receipt || tail.hidden) return;
    tailFailures = 0;
    if (reply && arriving && !document.hidden) {
      const reader = reply.reader;
      const previous = el("p", words.textContent, "presence-previous");
      previous.setAttribute("aria-hidden", "true");
      reader.classList.add("presence-handoff");
      for (const child of reader.children) {
        const fadeIn = fade(child, 0, 1, 280);
        fadeIn.onfinish = () => fadeIn.cancel();
      }
      reader.append(previous);
      fade(previous, 1, 0, 160).onfinish = () => {
        previous.remove();
        reader.classList.remove("presence-handoff");
      };
      tail.hidden = true;
    } else if (document.hidden) tail.hidden = true;
    else if (!exit) {
      exit = reply ? fade(caption, 1, 0, 160) : fade(tail, 1, 0, 200);
      exit.onfinish = () => {
        keepBottom(() => { tail.hidden = true; });
        exit.cancel();
        exit = null;
      };
    }
  }

  mark.addEventListener("click", () => {
    if (mark.dataset.point !== "owed") {
      mark.focus({ preventScroll: true });
      return;
    }
    const owed = snapshot.owed;
    const index = owed.findIndex(entry => entry.href === lastOwed);
    const next = owed[(index + 1) % owed.length];
    lastOwed = next.href;
    openOwed(next.href, mark);
  });

  return {
    read,
    chatChecked,
    chatFailed(readSnapshot) {
      if (readSnapshot && readSnapshot === snapshot && !snapshot.you && !receipt && ++tailFailures >= 3)
        staleTail();
    },
    place(narrow) {
      if (narrow && mark.parentElement !== back) {
        back.append(mark, legend);
      } else if (!narrow && mark.parentElement !== slot) {
        slot.append(mark);
        workspace.append(legend);
      }
    },
    accepted() {
      if (!supported || authLost) return;
      invalidate();
      receipt = true;
      if (!document.hidden) announcer.replaceChildren("received.");
      paint();
    },
    suspend() {
      invalidate();
      cancelDeadline();
      mark.removeAttribute("data-beat");
      point.removeAttribute("data-beat");
      document.title = "jarvis";
    },
    resume() {
      supported = true;
      if (stale) paint();
    },
    unauthenticated() {
      invalidate();
      authLost = true;
      goStale();
    },
  };
}
