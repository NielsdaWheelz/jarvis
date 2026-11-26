import { button, el, link } from "./home-dom.js";

const day = (date, zone) => date && new Intl.DateTimeFormat(undefined, {
  month: "short", day: "numeric", year: "numeric", timeZone: zone,
}).format(new Date(date));

function editionLabel(edition, work) {
  const published = day(edition.published_at, work.timezone);
  const ambiguous = !published || work.editions.some(other =>
    other.rev !== edition.rev && day(other.published_at, work.timezone) === published
  );
  let prefix = 8;
  while (ambiguous && work.editions.some(other =>
    other.rev !== edition.rev && other.rev.slice(0, prefix) === edition.rev.slice(0, prefix)
  )) prefix++;
  return (published || "date unknown") + (ambiguous ? " · " + edition.rev.slice(0, prefix) : "");
}

const view = (slug, rev) => ({ kind: "view", slug, rev });

export function bindArtifacts({ $, read, refresh, objectPath, changeState, empty, discuss }) {
  const shelf = $("artifacts");
  const canvas = $("canvas");
  const tools = $("object-tools");
  const object = $("object");
  const locationLabel = $("location");
  const status = $("artifact-status");
  let renderedShelf = "";
  let renderedReader = "";
  let restoreShelf = false;
  let savedWorks = [];

  function position(origin) {
    return { scroll: canvas.scrollTop, control: origin?.closest("[data-artifact-control]")?.dataset.artifactControl };
  }

  function remember(origin = document.activeElement) {
    if (shelf.hidden || history.state?.canvasSelection !== "/artifacts" ||
        getComputedStyle(shelf).visibility === "hidden") return;
    changeState({ artifactPosition: position(origin) });
  }

  canvas.addEventListener("scrollend", () => remember());

  function leave() {
    restoreShelf = true;
    renderedShelf = "";
    renderedReader = "";
    savedWorks = [];
    status.hidden = true;
    shelf.replaceChildren();
  }

  async function showShelf(same) {
    const page = await read("/api/artifacts");
    if (!same()) return;
    if (!page) throw new Error("artifact collection missing");
    const selection = history.state.openArtifacts?.join(" ") || "";
    const open = (history.state.openArtifacts || []).filter(slug => page.items.some(item =>
      item.edition_count > 1 && item.slug === slug
    ));
    const works = await Promise.all(open.map(async slug => {
      try {
        return await read("/api/artifacts/" + slug);
      } catch (error) {
        if (error.login || error.upgrade) throw error;
        const previous = savedWorks.find(work => work?.slug === slug);
        return { ...previous, slug, stale: true };
      }
    }));
    if (!same() || selection !== (history.state.openArtifacts?.join(" ") || "")) return;
    status.hidden = true;
    const signature = JSON.stringify([page, open, works]);
    if (signature === renderedShelf) return;
    const returning = restoreShelf ? history.state.artifactPosition : position(document.activeElement);
    renderedShelf = signature;
    savedWorks = works;
    restoreShelf = false;
    const heading = el("h1", "artifacts");
    heading.tabIndex = -1;
    const rows = el("ul", undefined, "artifact-works");
    page.items.forEach((item, i) => {
      const row = el("li");
      const pinned = objectPath(view(item.slug, item.current));
      const title = link(item.title, pinned, "artifact-title");
      title.dataset.artifactControl = "work:" + item.slug;
      row.append(title);
      if (item.description) row.append(el("p", item.description));
      if (item.last_published_at) row.append(el("small", day(item.last_published_at, page.timezone)));
      if (item.edition_count > 1) {
        const work = works.find(work => work?.slug === item.slug);
        const expanded = open.includes(item.slug);
        const list = el("ol", undefined, "artifact-editions");
        const toggle = button(item.edition_count + " editions", () => {
          const selected = history.state.openArtifacts || [];
          const show = list.hidden;
          list.hidden = !show;
          toggle.setAttribute("aria-expanded", String(show));
          if (show && !list.firstChild) list.append(el("li", "loading editions…"));
          remember(toggle);
          changeState({ openArtifacts: show ? [...selected, item.slug] : selected.filter(slug => slug !== item.slug) });
          refresh();
        });
        toggle.dataset.artifactControl = item.slug;
        toggle.setAttribute("aria-label", item.edition_count + " editions of " + item.title);
        toggle.setAttribute("aria-expanded", String(expanded));
        toggle.setAttribute("aria-controls", "artifact-editions-" + i);
        row.append(toggle);
        list.id = "artifact-editions-" + i;
        list.hidden = !expanded;
        if (expanded) {
          for (const edition of work?.editions || []) {
            const entry = el("li");
            const pin = objectPath(view(item.slug, edition.rev));
            const opens = link(editionLabel(edition, work), pin);
            opens.dataset.artifactControl = pin + ":edition";
            entry.append(opens);
            if (edition.rev === work.current) entry.append(el("small", "current", "artifact-current"));
            if (edition.change) entry.append(el("p", edition.change));
            list.append(entry);
          }
          if (!work || work.stale) {
            const unavailable = el("li", work?.editions ? "showing the last checked editions. " : "edition history unavailable. ");
            unavailable.append(button("retry", refresh));
            list.append(unavailable);
          }
        }
        row.append(list);
      }
      rows.append(row);
    });
    shelf.replaceChildren(heading, rows);
    if (!page.items.length) shelf.append(el("p", "no published artifacts."));
    if (returning) {
      const focus = [...shelf.querySelectorAll("[data-artifact-control]")].find(control =>
        control.dataset.artifactControl === returning.control
      );
      canvas.scrollTop = returning.scroll;
      if (returning.control) (focus || heading).focus({ preventScroll: true });
    }
    if (open.length !== (history.state.openArtifacts || []).length)
      changeState({ openArtifacts: open });
  }

  function unavailable() {
    renderedReader = "";
    object.replaceChildren(empty("this edition is unavailable."));
    locationLabel.replaceChildren();
    tools.replaceChildren();
    tools.hidden = true;
  }

  async function showEdition(work, edition, ref, same) {
    const canonical = objectPath(ref);
    if (renderedReader !== canonical) {
      renderedReader = canonical;
      const frame = el("iframe");
      frame.title = edition.title;
      frame.setAttribute("sandbox", "allow-scripts");
      frame.src = "/content/" + ref.slug + "/" + ref.rev;
      object.replaceChildren(frame);
      const copied = el("span");
      copied.setAttribute("role", "status");
      const copy = button("copy edition link", async () => {
        try {
          await navigator.clipboard.writeText(new URL(canonical, location.origin).href);
          copied.textContent = "link copied.";
        } catch {
          copied.textContent = "copy the pinned address from the title link.";
        }
      });
      const ask = button("discuss this edition", event => discuss(ref, edition.title, event.currentTarget));
      ask.id = "discuss-object";
      const current = el("span");
      current.id = "artifact-current-edition";
      const delivery = el("span");
      delivery.id = "artifact-delivery";
      tools.replaceChildren(copy, ask, current, delivery, copied);
      tools.hidden = false;
    }
    const title = location.pathname === "/" ? edition.title : edition.title + " · " + editionLabel(edition, work);
    const titleLink = locationLabel.firstElementChild;
    if (titleLink?.getAttribute("href") !== canonical) locationLabel.replaceChildren(link(title, canonical));
    else if (titleLink.textContent !== title) titleLink.textContent = title;
    const current = $("artifact-current-edition");
    const currentPath = objectPath(view(ref.slug, work.current));
    if (work.current === ref.rev) {
      if (current.textContent !== "current") current.textContent = "current";
    } else if (current.firstElementChild?.getAttribute("href") !== currentPath) {
      current.replaceChildren(link("open current edition", currentPath));
    }
    status.hidden = true;
    let message;
    let failed = false;
    try {
      message = await read("/api/artifacts/" + ref.slug + "/" + ref.rev + "/discussion");
    } catch (error) {
      if (error.login || error.upgrade) throw error;
      failed = true;
    }
    if (!same()) return;
    const delivery = $("artifact-delivery");
    const target = message?.message_id && "/m/" + message.message_id;
    if (failed) {
      if (!delivery.querySelector("button")) delivery.replaceChildren(button("retry discussion", refresh));
    } else if (target) {
      if (delivery.firstElementChild?.getAttribute("href") !== target)
        delivery.replaceChildren(link("open chat message", target));
    } else delivery.replaceChildren();
  }

  function failed(isShelf) {
    const loaded = isShelf ? renderedShelf : renderedReader;
    const message = loaded
      ? isShelf ? "showing the last checked library." : "showing the last checked edition."
      : isShelf ? "couldn’t check the library." : "couldn’t check this edition.";
    if (status.firstChild?.textContent !== message)
      status.replaceChildren(message, " ", button("retry", refresh));
    status.hidden = false;
  }

  return { remember, leave, showShelf, showEdition, unavailable, failed };
}
