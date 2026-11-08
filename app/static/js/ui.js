import { h, mount, clear } from "./dom.js";
import { ApiError } from "./api.js";

export function toast(message, kind = "success") {
  const holder = document.getElementById("toasts");
  const el = h("div", { class: `toast toast-${kind}`, role: "status" }, message);
  holder.appendChild(el);
  setTimeout(() => el.remove(), kind === "error" ? 7000 : 4000);
}

export function errorMessage(err) {
  return err instanceof ApiError ? err.message : "Something went wrong. Please try again.";
}

export function formatTs(value) {
  if (!value) return "—";
  return String(value).replace("T", " ").replace("Z", " UTC").replace(":00 UTC", " UTC");
}

export function formatDate(value) { return value ? String(value).slice(0, 10) : "—"; }

const STATUS_CLASS = {
  active: "good", valid: "good", matched: "good", completed: "good", issued: "good", ok: "good",
  revoked: "bad", tampered: "bad", mismatch: "bad", failed: "bad", closed: "bad", rotated: "muted",
  expired: "warn", suspended: "warn", insufficient_identifiers: "warn", in_progress: "info", enrolled: "info",
  withdrawn: "muted", retired: "muted", archived: "muted", draft: "muted", not_found: "warn", not_requested: "muted",
};

export function badge(value) {
  const text = value === null || value === undefined ? "—" : String(value).replace(/_/g, " ");
  return h("span", { class: `badge badge-${STATUS_CLASS[value] || "muted"}` }, text);
}

export function loading(label = "Loading…") { return h("div", { class: "loading" }, h("span", { class: "spinner" }), label); }

export function errorBox(err, retry) {
  return h("div", { class: "alert alert-error" }, errorMessage(err), retry ? h("button", { class: "btn btn-small", onClick: retry }, "Retry") : null);
}

export function card(title, body, actions) {
  return h("section", { class: "card" }, (title || actions) ? h("header", { class: "card-head" }, h("h2", {}, title || ""), actions || null) : null, body);
}

export function kpi(label, value, hint) {
  return h("div", { class: "kpi" }, h("div", { class: "kpi-value" }, value), h("div", { class: "kpi-label" }, label), hint ? h("div", { class: "kpi-hint" }, hint) : null);
}

export function definitionList(pairs) {
  return h("dl", { class: "dl" }, pairs.filter(Boolean).map(([k, v]) => [h("dt", {}, k), h("dd", {}, v === null || v === undefined || v === "" ? "—" : v)]));
}

export function link(href, text) { return h("a", { href }, text); }

export function modal({ title, body, wide = false, onClose }) {
  const backdrop = h("div", { class: "modal-backdrop" });
  const close = () => { backdrop.remove(); if (onClose) onClose(); };
  const dialog = h("div", { class: wide ? "modal modal-wide" : "modal", role: "dialog", "aria-modal": "true", "aria-label": title },
    h("header", { class: "modal-head" }, h("h2", {}, title), h("button", { class: "icon-btn", "aria-label": "Close", onClick: close }, "×")), h("div", { class: "modal-body" }, body));
  backdrop.appendChild(dialog);
  backdrop.addEventListener("click", (e) => { if (e.target === backdrop) close(); });
  document.body.appendChild(backdrop);
  return { close, element: dialog };
}

export function confirmDialog({ title, message, confirmLabel = "Confirm", danger = false }) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => { if (!settled) { settled = true; resolve(value); } };
    const m = modal({ title, onClose: () => finish(false), body: h("div", {},
      h("p", {}, message),
      h("div", { class: "form-actions" },
        h("button", { class: "btn", onClick: () => { m.close(); } }, "Cancel"),
        h("button", { class: danger ? "btn btn-danger" : "btn btn-primary", onClick: () => { finish(true); m.close(); } }, confirmLabel))) });
  });
}

function fieldControl(f, value) {
  const common = { id: `f-${f.name}`, name: f.name };
  if (f.type === "select") {
    return h("select", common, [h("option", { value: "" }, f.placeholder || "Select…"), ...f.options.map((o) => {
      const opt = typeof o === "string" ? { value: o, label: o.replace(/_/g, " ") } : o;
      return h("option", { value: opt.value, selected: String(opt.value) === String(value) }, opt.label);
    })]);
  }
  if (f.type === "textarea") return h("textarea", { ...common, rows: 3, maxlength: f.maxlength || 500 }, value || "");
  if (f.type === "checkbox") return h("input", { ...common, type: "checkbox", checked: !!value });
  return h("input", { ...common, type: f.type || "text", value: value ?? "", placeholder: f.placeholder, autocomplete: f.autocomplete || "off",
    min: f.min, max: f.max, step: f.step, maxlength: f.maxlength });
}

export function readControl(f, control) {
  if (f.type === "checkbox") return control.checked;
  const raw = control.value;
  if (raw === "" || raw === undefined) return undefined;
  if (f.type === "number") return Number(raw);
  return raw.trim();
}

export function form({ fields, submitLabel = "Save", initial = {}, onSubmit, onCancel }) {
  const controls = {};
  const errors = {};
  const banner = h("div", { class: "alert alert-error hidden", role: "alert" });
  const submit = h("button", { class: "btn btn-primary", type: "submit" }, submitLabel);
  const rows = fields.map((f) => {
    const control = fieldControl(f, initial[f.name]);
    const error = h("div", { class: "field-error" });
    controls[f.name] = control;
    errors[f.name] = error;
    return h("div", { class: f.type === "checkbox" ? "field field-check" : "field" },
      h("label", { for: `f-${f.name}` }, f.label, f.required ? h("span", { class: "req" }, " *") : null), control,
      f.hint ? h("div", { class: "hint" }, f.hint) : null, error);
  });
  const el = h("form", { novalidate: true, onSubmit: async (event) => {
    event.preventDefault();
    banner.classList.add("hidden");
    Object.values(errors).forEach((e) => { e.textContent = ""; });
    const values = {};
    for (const f of fields) {
      const value = readControl(f, controls[f.name]);
      if (value !== undefined) values[f.name] = value;
    }
    const missing = fields.filter((f) => f.required && (values[f.name] === undefined || values[f.name] === ""));
    if (missing.length) {
      missing.forEach((f) => { errors[f.name].textContent = "This field is required"; });
      return;
    }
    submit.disabled = true;
    submit.textContent = "Working…";
    try { await onSubmit(values); }
    catch (err) {
      if (err instanceof ApiError && err.details && typeof err.details === "object") {
        for (const [name, msg] of Object.entries(err.details)) if (errors[name]) errors[name].textContent = msg;
      }
      banner.textContent = errorMessage(err);
      banner.classList.remove("hidden");
    } finally { submit.disabled = false; submit.textContent = submitLabel; }
  } }, banner, rows, h("div", { class: "form-actions" }, onCancel ? h("button", { class: "btn", type: "button", onClick: onCancel }, "Cancel") : null, submit));
  el.controls = controls;
  return el;
}

export function pager(state, onChange) {
  const pages = Math.max(1, Math.ceil(state.total / state.page_size));
  const from = state.total ? (state.page - 1) * state.page_size + 1 : 0;
  const to = Math.min(state.total, state.page * state.page_size);
  return h("div", { class: "pager" }, h("span", { class: "muted" }, `${from.toLocaleString()}–${to.toLocaleString()} of ${state.total.toLocaleString()}`),
    h("div", {}, h("button", { class: "btn btn-small", disabled: state.page <= 1, onClick: () => onChange(state.page - 1) }, "Previous"),
      h("span", { class: "page-label" }, `Page ${state.page} of ${pages}`),
      h("button", { class: "btn btn-small", disabled: state.page >= pages, onClick: () => onChange(state.page + 1) }, "Next")));
}

export function dataTable({ columns, load, filters = [], initial = {}, pageSize = 25, emptyText = "Nothing to show.", actions }) {
  const query = { page: 1, page_size: pageSize };
  filters.forEach((f) => { query[f.name] = initial[f.name] || ""; });
  const body = h("div", { class: "table-body" });
  const filterEls = {};
  let timer = null;
  let requestId = 0;

  async function refresh() {
    const mine = ++requestId;
    mount(body, loading());
    try {
      const result = await load({ ...query });
      if (mine !== requestId) return;
      if (!result.items.length) { mount(body, h("p", { class: "empty" }, emptyText), pager(result, () => {})); return; }
      const table = h("div", { class: "table-scroll" }, h("table", { class: "table" },
        h("thead", {}, h("tr", {}, columns.map((c) => h("th", {}, c.label)))),
        h("tbody", {}, result.items.map((row) => h("tr", {}, columns.map((c) => h("td", { "data-label": c.label }, c.render ? c.render(row) : row[c.key] ?? "—")))))));
      mount(body, table, pager(result, (page) => { query.page = page; refresh(); }));
    } catch (err) { if (mine === requestId) mount(body, errorBox(err, refresh)); }
  }

  const bar = h("div", { class: "filters" }, filters.map((f) => {
    const control = f.type === "select"
      ? h("select", { "aria-label": f.label, onChange: (e) => { query[f.name] = e.target.value; query.page = 1; refresh(); } },
        [h("option", { value: "" }, f.label), ...f.options.map((o) => { const opt = typeof o === "string" ? { value: o, label: o.replace(/_/g, " ") } : o;
          return h("option", { value: opt.value, selected: opt.value === initial[f.name] }, opt.label); })])
      : h("input", { type: "search", placeholder: f.label, "aria-label": f.label, value: initial[f.name] || "", onInput: (e) => {
        clearTimeout(timer); timer = setTimeout(() => { query[f.name] = e.target.value.trim(); query.page = 1; refresh(); }, 300); } });
    filterEls[f.name] = control;
    return control;
  }), actions || null);
  const root = h("div", { class: "datatable" }, bar, body);
  root.refresh = refresh;
  refresh();
  return root;
}

export function pageHeader(title, subtitle, actions) {
  return h("div", { class: "page-head" }, h("div", {}, h("h1", {}, title), subtitle ? h("p", { class: "muted" }, subtitle) : null), actions ? h("div", { class: "page-actions" }, actions) : null);
}

export function checkList(checks) {
  return h("ul", { class: "checks" }, checks.map((c) => h("li", { class: c.passed ? "check-pass" : "check-fail" },
    h("span", { class: "check-icon", "aria-hidden": "true" }, c.passed ? "✓" : "✕"), h("div", {}, h("strong", {}, c.label), h("div", { class: "muted" }, c.detail)))));
}

export { h, mount, clear };
