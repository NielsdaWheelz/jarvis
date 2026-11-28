import { button, el } from "./home-dom.js";

export function approvalForm({ label, prompt, note, details, choices, answer }) {
  const form = el("section", undefined, "approval-form");
  form.setAttribute("aria-label", label);
  form.tabIndex = -1;
  const status = el("p");
  status.setAttribute("role", "status");
  const actions = el("div", undefined, "approval-actions");
  let submitted = false;
  async function choose(value) {
    if (submitted) return;
    submitted = true;
    for (const control of actions.children) control.disabled = true;
    submitted = await answer(value, status);
    for (const control of actions.children) control.disabled = submitted;
  }
  for (const { value, label: title } of choices)
    actions.append(button(title, () => choose(value)));
  actions.append(button("cancel", () => choose(null)));
  form.append(el("p", prompt));
  if (note) form.append(el("small", note));
  if (details) form.append(details);
  form.append(actions, status);
  return form;
}
