import MarkdownIt from "./markdown-it-15.0.3/markdown-it.mjs";
import { el, link } from "./home-dom.js";
import { driveRoute } from "./drive.js";

const markdown = new MarkdownIt("commonmark", { html: true, linkify: false }).enable("table");
// Keep even a rejected destination's label. Only destination() below can create a link.
markdown.validateLink = () => true;
const literalLinks = new MarkdownIt("zero").enable("link");
literalLinks.validateLink = markdown.validateLink;
export const uuid = "[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}";
export const mailRoute = new RegExp("^/mail/(" + uuid + ")/(revision|draft)/(" + uuid + ")$");
const message = new RegExp("^/m/(" + uuid + ")$");
const todo = new RegExp("^/t/" + uuid + "$");
const view = /^\/v\/([a-z0-9]+(?:-[a-z0-9]+)*)(?:\/(?:[0-9a-f]{40}|[0-9a-f]{64}))?$/;
const inspection = new RegExp("^/m/(" + uuid + ")/(source|table)/([1-9][0-9]*)(?:/([0-9a-f]{64}))?$");

export function inspectionAt(path) {
  const match = inspection.exec(path);
  if (!match || !Number.isSafeInteger(Number(match[3])) || (match[2] === "table") !== Boolean(match[4])) return null;
  return { message: match[1], kind: match[2], number: Number(match[3]), digest: match[4] };
}
export const messagePath = path => message.test(path);

export function ordinaryPath(path) {
  const published = view.exec(path);
  return path === "/" || path === "/overview" || messagePath(path) || todo.test(path) || mailRoute.test(path) ||
    (published && published[1].length <= 64) || driveRoute(path) !== null;
}
function destination(raw) {
  if (/[\\\u0000-\u0020]/.test(raw) || raw.startsWith("//") || !/^(?:https?:\/\/|\/)/i.test(raw)) return null;
  let url;
  try { url = new URL(raw, location.origin); } catch { return null; }
  if (!url.hostname || url.username || url.password) return null;
  if (url.origin !== location.origin) return url.href;
  if (raw.includes("#") || (raw.includes("?") && !url.search)) return null;
  const path = url.pathname + url.search;
  return ordinaryPath(path) ? path : null;
}

const bare = /https?:\/\/[^\s<>]+|attachment:[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}|\/(?:[mftv]\/|files\/|mail\/)[^\s<>]+/gi;
function addPlainLinks(parent, value) {
  let end = 0;
  for (const match of value.matchAll(bare)) {
    if (match.index && /[\w:/]/.test(value[match.index - 1])) continue;
    let target = match[0].replace(/[.,;:!?'”"’\]}]+$/, "");
    const opens = (target.match(/\(/g) || []).length, closes = (target.match(/\)/g) || []).length;
    for (let extra = closes - opens; extra > 0 && target.endsWith(")"); --extra) target = target.slice(0, -1);
    const file = target.startsWith("attachment:");
    const href = destination(file ? "/f/" + target.slice(11) : target);
    if (!href) continue;
    const anchor = link(file ? "original file" : target, href);
    if (!href.startsWith("/")) { anchor.target = "_blank"; anchor.rel = "noopener noreferrer"; }
    parent.append(value.slice(end, match.index), anchor);
    end = match.index + target.length;
  }
  parent.append(value.slice(end));
}
export function linkedText(value) {
  const p = el("p", undefined, "prose");
  inline(p, literalLinks.parseInline(value, {})[0].children, null, "");
  return p;
}

export function parseMessage(text) {
  const lines = text.replace(/\r\n?/g, "\n").split("\n");
  const tokens = markdown.parse(text, {});
  const tables = [];
  for (const [start, token] of tokens.entries()) {
    if (token.type === "table_open") {
      const [first, after] = token.map;
      const block = lines.slice(first, after).join("\n");
      const digest = crypto.subtle.digest("SHA-256", new TextEncoder().encode(block))
        .then(bytes => Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, "0")).join(""));
      tables.push({ start, digest });
    } else if (token.type === "table_close") tables.at(-1).end = start + 1;
  }
  return { tokens, tables };
}

function inline(parent, tokens, m, prefix) {
  const stack = [parent];
  let linkDepth = 0;
  for (const [i, token] of tokens.entries()) {
    const current = stack.at(-1);
    if (token.nesting < 0) {
      if (token.type === "link_close") linkDepth--;
      stack.pop();
      continue;
    }
    if (token.type === "link_open") {
      linkDepth++;
      const raw = token.attrGet("href");
      const slot = /^#source-([1-9][0-9]*)$/.exec(raw);
      let href = null, unavailable = false;
      if (slot) {
        if (m?.role === "assistant" && Array.isArray(m.sources)) {
          const number = Number(slot[1]);
          const found = m.sources.find(source => source.slot === number);
          if (found?.state === "available") href = "/m/" + m.id + "/source/" + number;
          else unavailable = true;
        }
      } else href = destination(raw);
      const node = href ? link(undefined, href) : el("span");
      if (href && !href.startsWith("/")) { node.target = "_blank"; node.rel = "noopener noreferrer"; }
      if (slot && href) node.dataset.readerAnchor = prefix + "-" + i;
      current.append(node);
      if (unavailable) current.append(" · source unavailable");
      stack.push(node);
    } else if (token.nesting > 0) {
      const node = el(token.tag);
      current.append(node);
      stack.push(node);
    } else if (token.type === "text" && !linkDepth) addPlainLinks(current, token.content);
    else if (token.type === "code_inline") current.append(el("code", token.content));
    else if (token.type === "softbreak" || token.type === "hardbreak") current.append(el("br"));
    else if (token.type === "image") current.append(markdown.renderer.renderInlineAsText(token.children || [], markdown.options, {}));
    else current.append(token.content);
  }
}

function sizeTable(box) {
  const scroll = box.firstElementChild, expand = box.lastElementChild;
  if (expand !== scroll) expand.hidden = !expand.hasAttribute("href") || scroll.clientWidth === 0 || scroll.scrollWidth <= scroll.clientWidth;
}
export function showTableControls() {
  document.querySelectorAll(".chat-table").forEach(sizeTable);
}

export function renderMarkdown(m, parsed, tableNumber = null) {
  const root = el("div", undefined, "chat-markdown");
  const stack = [root];
  const selected = tableNumber === null ? null : parsed.tables[tableNumber - 1];
  const start = selected?.start ?? 0, end = selected?.end ?? parsed.tokens.length;
  let number = tableNumber || 0;
  for (let i = start; i < end; i++) {
    const token = parsed.tokens[i], parent = stack.at(-1);
    if (token.type === "table_open") {
      if (!selected) number++;
      const box = el("div", undefined, "chat-table");
      const scroll = el("div", undefined, "table-scroll"), table = el("table");
      scroll.append(table);
      box.append(scroll);
      if (!selected) {
        const anchor = el("a", "expand table");
        anchor.hidden = true;
        anchor.dataset.readerAnchor = "table-" + number;
        const path = "/m/" + m.id + "/table/" + number + "/";
        parsed.tables[number - 1].digest.then(hash => {
          anchor.href = path + hash;
          sizeTable(box);
        });
        box.append(anchor);
      }
      parent.append(box);
      stack.push(table);
    } else if (token.nesting < 0) stack.pop();
    else if (token.nesting > 0) {
      const node = el(token.tag);
      if (token.type === "ordered_list_open" && token.attrGet("start")) node.start = Number(token.attrGet("start"));
      if (token.tag === "th") node.scope = "col";
      parent.append(node);
      stack.push(node);
    } else if (token.type === "inline") inline(parent, token.children, m, "link-" + i);
    else if (token.type === "hr") parent.append(el("hr"));
    else if (token.type === "code_block" || token.type === "fence") {
      const pre = el("pre");
      pre.append(el("code", token.content));
      parent.append(pre);
    } else if (token.type === "html_block") parent.append(el("div", token.content, "literal"));
  }
  return root;
}
