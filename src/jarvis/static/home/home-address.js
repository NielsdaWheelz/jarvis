import { driveRoute } from "./drive.js";

const uuid = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const conversationRoute = new RegExp("^/(m|t)/(" + uuid + ")$");
const mailRoute = new RegExp("^/mail/(" + uuid + ")/(revision|draft)/(" + uuid + ")$");
const artifactRoute = /^\/artifacts\/([a-z0-9]+(?:-[a-z0-9]+)*)(?:\/([0-9a-f]{40}|[0-9a-f]{64}))?$/;
const inspection = new RegExp("^/m/(" + uuid + ")/(source|table)/([1-9][0-9]*)(?:/([0-9a-f]{64}))?$");
export function address(path) {
  if (!path) return null;
  const url = new URL(path, location.origin);
  if (url.origin !== location.origin || url.username || url.password || url.href.includes("#")) return null;
  if (!url.search && !url.href.endsWith("?")) {
    const pathname = url.pathname;
    if (pathname === "/") return { kind: "home" };
    if (pathname === "/todos") return { kind: "todos" };
    const literal = path.startsWith(location.origin) ? path.slice(location.origin.length) : path;
    if (literal === pathname) {
      if (pathname === "/artifacts") return { kind: "artifacts" };
      const view = artifactRoute.exec(pathname);
      if (view && view[1].length <= 64) return { kind: "view", slug: view[1], rev: view[2] };
      const inspected = inspection.exec(pathname);
      if (inspected && Number.isSafeInteger(Number(inspected[3])) &&
          (inspected[2] === "table") === Boolean(inspected[4])) {
        return { message: inspected[1], kind: inspected[2], number: Number(inspected[3]), digest: inspected[4] };
      }
    }
    const chat = conversationRoute.exec(pathname);
    if (chat) return { kind: chat[1] === "m" ? "message" : "todo", id: chat[2] };
    const mail = mailRoute.exec(pathname);
    if (mail) return { kind: "mail", message: mail[1], mode: mail[2], action: mail[3] };
  }
  return driveRoute(url.href);
}
