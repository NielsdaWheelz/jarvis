const el = (tag, text, cls) => {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
};
function button(label, click) {
  const node = el("button", label);
  node.type = "button";
  node.addEventListener("click", click);
  return node;
}
function link(label, path, cls) {
  const node = el("a", label, cls);
  node.href = path;
  return node;
}

export { el, button, link };
