// Drives the real frontend modules against a running server using a minimal DOM shim.
// Usage: BASE_URL=http://127.0.0.1:5056 DEMO_PASSWORD=... node tests/frontend_smoke.mjs
const BASE = process.env.BASE_URL || "http://127.0.0.1:5056";
const PASSWORD = process.env.DEMO_PASSWORD || "Demo-Passw0rd!";
const ACCOUNTS = JSON.parse(process.env.ACCOUNTS || "{}");

class Text { constructor(t) { this.data = String(t); this.parent = null; } get textContent() { return this.data; } }
class El {
  constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.attrs = {}; this.listeners = {}; this.className = ""; this.parent = null; this.value = ""; this.checked = false; this.disabled = false; this.style = {}; }
  appendChild(c) { if (c.parent) c.parent.removeChild(c); c.parent = this; this.children.push(c); return c; }
  removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parent = null; return c; }
  get firstChild() { return this.children[0] || null; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k === "class") this.className = String(v); if (k === "value") this.value = String(v); }
  getAttribute(k) { return this.attrs[k]; }
  addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); }
  remove() { if (this.parent) this.parent.removeChild(this); }
  click() { return this.dispatch("click"); }
  get classList() { const self = this; return {
    add: (c) => { if (!self.className.split(" ").includes(c)) self.className = (self.className + " " + c).trim(); },
    remove: (c) => { self.className = self.className.split(" ").filter((x) => x && x !== c).join(" "); },
    toggle: (c) => { const has = self.className.split(" ").includes(c); has ? this.remove(c) : this.add(c); },
    contains: (c) => self.className.split(" ").includes(c) }; }
  get textContent() { return this.children.map((c) => c.textContent).join(""); }
  set textContent(v) { this.children = v === "" ? [] : [new Text(v)]; }
  dispatch(type, extra = {}) { const out = []; for (const f of this.listeners[type] || []) out.push(f({ type, target: this, preventDefault() {}, ...extra })); return Promise.all(out); }
  find(pred) { if (pred(this)) return this; for (const c of this.children) { if (c instanceof El) { const r = c.find(pred); if (r) return r; } } return null; }
  findAll(pred, acc = []) { if (pred(this)) acc.push(this); this.children.forEach((c) => c instanceof El && c.findAll(pred, acc)); return acc; }
}
const body = new El("body");
let inflight = 0, fetchCount = 0;
const store = new Map();
const hashListeners = [];
let hashValue = "";
globalThis.window = { __TESTING__: true, addEventListener: (t, f) => { if (t === "hashchange") hashListeners.push(f); } };
globalThis.document = {
  body, createElement: (t) => new El(t), createElementNS: (_, t) => new El(t), createTextNode: (t) => new Text(t),
  getElementById: (id) => body.find((e) => e.attrs.id === id),
};
globalThis.sessionStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, String(v)), removeItem: (k) => store.delete(k) };
let pendingRender = Promise.resolve();
globalThis.location = {
  get hash() { return hashValue; },
  set hash(v) { hashValue = v.startsWith("#") ? v : "#" + v; pendingRender = Promise.all(hashListeners.map((f) => f())); },
  replace(v) { hashValue = v; },
};
const realFetch = globalThis.fetch;
globalThis.fetch = async (url, init) => { inflight++; fetchCount++; try { return await realFetch(url.startsWith("http") ? url : BASE + url, init); } finally { inflight--; } };
globalThis.URL.createObjectURL = () => "blob:test";
globalThis.URL.revokeObjectURL = () => {};
body.appendChild(Object.assign(new El("div"), { attrs: { id: "app" } }));
body.appendChild(Object.assign(new El("div"), { attrs: { id: "toasts" } }));

async function settle() {
  let stable = 0, last = -1;
  while (stable < 4) {
    await new Promise((r) => setTimeout(r, 25));
    if (inflight === 0 && fetchCount === last) stable++; else stable = 0;
    last = fetchCount;
  }
  await pendingRender;
}
const app = () => document.getElementById("app");
const text = () => app().textContent + document.getElementById("toasts").textContent + body.children.filter((c) => c.className.includes("modal-backdrop")).map((c) => c.textContent).join(" ");
const modals = () => body.children.filter((c) => c.className.includes("modal-backdrop"));
let failures = 0, checks = 0;
function check(name, ok, detail = "") { checks++; if (!ok) { failures++; console.log(`  FAIL ${name} ${detail}`); } else console.log(`  ok   ${name}`); }
async function go(path) { location.hash = path; await settle(); }
function errorsOnPage() { return app().findAll((e) => e.className.includes("alert-error") && !e.className.includes("hidden")).map((e) => e.textContent); }
const byId = (root, id) => root.find((e) => e.attrs.id === id);
const buttonWith = (root, label) => root.find((e) => e.tagName === "BUTTON" && e.textContent.trim() === label);
function fill(root, values) { for (const [k, v] of Object.entries(values)) { const el = byId(root, `f-${k}`); if (!el) throw new Error(`no field ${k}`); el.value = v; } }
async function submit(root) { const form = root.find((e) => e.tagName === "FORM"); await form.dispatch("submit"); await settle(); }
async function login(email) {
  const r = await realFetch(BASE + "/api/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password: PASSWORD }) });
  const data = await r.json();
  store.set("cp_token", data.token); store.set("cp_user", JSON.stringify(data.user));
  return data.user;
}
const apiGet = async (path, email) => { const u = await login(email); const r = await realFetch(BASE + "/api" + path, { headers: { Authorization: "Bearer " + store.get("cp_token") } }); return r.json(); };

const main = await import("../app/static/js/main.js");
await main.start();

console.log("Public verifier");
const staffEmail = ACCOUNTS.academic_admin;
const sample = (await apiGet("/credentials?page_size=1&status=active", staffEmail)).items[0];
store.clear();
await go("/verify?id=" + sample.credential_id);
check("public verify page renders without login", text().includes("Verify a credential"));
fill(app(), { claimed_name: sample.learner_name });
await submit(app());
check("name-only claim reports insufficient identifiers", text().includes("Name alone is not enough"), text().slice(0, 200));
check("valid credential banner", text().includes("Valid credential"));
await go("/verify?id=CRD-2026-999999");
await submit(app());
check("unknown credential reports not found", text().includes("No such credential"));
await go("/learners");
check("anonymous user redirected to login", location.hash === "#/login" && text().includes("Sign in"));

console.log("Login form");
fill(app(), { email: staffEmail, password: "wrong-password" });
await submit(app());
check("wrong password shows error", text().includes("Email or password is incorrect"));
fill(app(), { email: staffEmail, password: PASSWORD });
await submit(app());
await settle();
check("successful login lands on dashboard", location.hash === "#/dashboard" && text().includes("Credentials issued"), location.hash);
check("dashboard renders charts", app().findAll((e) => e.tagName === "SVG" || e.className.includes("chart")).length > 3);

const learnerSample = (await apiGet("/learners?page_size=1", staffEmail)).items[0];
const credSample = (await apiGet("/credentials?page_size=1", staffEmail)).items[0];
const courseSample = (await apiGet("/courses?page_size=1", staffEmail)).items[0];
const ruleSample = (await apiGet("/rules?page_size=1", staffEmail)).items[0];
const completionSample = (await apiGet("/completions?page_size=1", staffEmail)).items[0];
const issuerSample = (await apiGet("/issuers", staffEmail))[0];

const pagesFor = {
  platform_admin: ["/dashboard", "/learners", `/learners/${learnerSample.learner_id}`, "/courses", `/courses/${courseSample.course_id}`, "/completions", `/completions/${completionSample.completion_id}`, "/rules", `/rules/${ruleSample.rule_id}`, "/issuance", "/credentials", `/credentials/${credSample.credential_id}`, "/verifications", "/revocations", "/issuers", `/issuers/${issuerSample.issuer_id}`, "/audit", "/integrity", "/users", "/account"],
  academic_admin: ["/dashboard", "/learners", "/courses", "/rules", "/issuance", "/credentials", `/credentials/${credSample.credential_id}`, "/verifications", "/revocations", "/issuers", "/audit", "/integrity", "/account"],
  support_staff: ["/dashboard", "/learners", `/learners/${learnerSample.learner_id}`, "/credentials", `/credentials/${credSample.credential_id}`, "/verifications", "/revocations", "/audit", "/account"],
  instructor: ["/dashboard", "/courses", "/completions", "/rules", "/account"],
  learner: ["/dashboard", "/credentials", "/completions", "/verifications", "/account"],
};
for (const [role, pages] of Object.entries(pagesFor)) {
  console.log(`Pages as ${role}`);
  await login(ACCOUNTS[role]);
  for (const page of pages) {
    await go(page);
    const errs = errorsOnPage();
    check(`${role} ${page}`, errs.length === 0 && app().textContent.length > 80 && location.hash === "#" + page, errs.join("|") + " " + location.hash);
  }
}

console.log("Role restrictions in the UI");
await login(ACCOUNTS.learner);
await go("/users");
check("learner blocked from users page", text().includes("does not have access"));
await go("/learners");
check("learner blocked from learners page", text().includes("does not have access"));
await login(ACCOUNTS.support_staff);
await go("/users");
check("support blocked from users page", text().includes("does not have access"));
await go("/issuance");
check("support sees issuance page but cannot issue", app().findAll((e) => e.tagName === "BUTTON" && e.textContent.includes("Review & issue")).length === 0);

console.log("Issuance → verification → revocation workflow (academic admin)");
await login(ACCOUNTS.academic_admin);
await go("/issuance");
const reviewBtn = buttonWith(app(), "Review & issue");
check("pending queue has rows", Boolean(reviewBtn));
await reviewBtn.click(); await settle();
const dlg = modals().at(-1);
check("eligibility checks listed in modal", dlg && dlg.textContent.includes("mandatory courses"));
await buttonWith(dlg, "Issue credential").click(); await settle();
check("issuing navigates to the new credential", /^#\/credentials\/CRD-\d{4}-\d{6}$/.test(location.hash), location.hash);
const newId = location.hash.split("/").pop();
check("new credential shows signed record", text().includes("Ed25519") && text().includes(newId));
await buttonWith(app(), "Verify now").click(); await settle();
check("verify now reports a valid credential", text().includes("Valid credential"));
modals().forEach((m) => m.remove());
await buttonWith(app(), "Revoke").click(); await settle();
const revModal = modals().at(-1);
fill(revModal, { reason_code: "issued_in_error", reason_detail: "smoke test" });
await submit(revModal); await settle();
check("revocation shows revoked state", text().includes("revoked") && text().includes(`REV-${newId}-01`), text().slice(0, 300));
await go("/verify?id=" + newId);
await submit(app());
check("public verifier now reports revoked", text().includes("Credential has been revoked"));

console.log("Instructor and learner actions");
const instructorEmail = ACCOUNTS.instructor;
const open = (await apiGet("/completions?status=in_progress&page_size=50", instructorEmail)).items.find((c) => c.progress_pct < 100) ;
await login(instructorEmail);
if (open) {
  await go(`/completions/${open.completion_id}`);
  fill(app(), { progress_pct: 100 });
  await submit(app());
  check("instructor progress update succeeds", text().includes("100%"));
  const scoreForm = app().findAll((e) => e.tagName === "FORM")[1];
  fill(scoreForm, { score: 91.5 });
  await submit(scoreForm);
  check("assessment recorded and status derived", text().includes("completed") && text().includes("91.5"));
} else console.log("  (no in-progress enrolment available for the instructor; skipped)");
await login(ACCOUNTS.learner);
await go("/credentials");
check("learner sees only their own credentials", !text().includes("Search credential ID or learner"));

console.log("Other UI forms and actions");
await login(ACCOUNTS.academic_admin);
await go("/learners");
await buttonWith(app(), "Register learner").click(); await settle();
let dialogEl = modals().at(-1);
const stamp = Date.now();
fill(dialogEl, { full_name: "Smoke Tester", email: `smoke.${stamp}@mail.example`, date_of_birth: "1991-02-03", country_code: "GB" });
await submit(dialogEl);
check("register learner form creates a learner", /Registered LRN-\d{6}/.test(text()), text().slice(-200));
modals().forEach((m) => m.remove());
await go("/courses");
const instructors = (await apiGet("/meta/course-options", ACCOUNTS.academic_admin)).instructors;
await login(ACCOUNTS.academic_admin);
await buttonWith(app(), "Create course").click(); await settle();
dialogEl = modals().at(-1);
fill(dialogEl, { title: `Smoke Course ${stamp}`, category: "Data Science", level: "intermediate", credit_hours: 12, pass_mark: 60, max_attempts: 3, instructor_id: instructors[0].instructor_id });
await submit(dialogEl);
check("create course form creates a course", /Created CRS-\d{6}/.test(text()), text().slice(-200));
await go("/courses");
dialogEl = null;
await buttonWith(app(), "Create course").click(); await settle();
fill(modals().at(-1), { title: "x" });
await submit(modals().at(-1));
check("course form shows validation errors", text().includes("This field is required"));
modals().forEach((m) => m.remove());

await login(ACCOUNTS.platform_admin);
await go("/users");
await buttonWith(app(), "Create user").click(); await settle();
dialogEl = modals().at(-1);
fill(dialogEl, { email: `smoke.staff.${stamp}@credentials.example`, role: "support_staff" });
await submit(dialogEl);
check("create user shows a one-time temporary password", text().includes("Temporary password for") && text().includes("cannot be shown again"));
modals().forEach((m) => m.remove());
await go("/issuers/ISS-003");
buttonWith(app(), "Rotate key").click(); await settle();
const confirmBox = modals().at(-1);
buttonWith(confirmBox, "Rotate key").click(); await settle();
check("rotate key via confirmation dialog", text().includes("Key rotated") && text().includes("KEY-ISS-003-03"), text().slice(-300));
await go("/integrity");
await buttonWith(app(), "Run integrity scan").click(); await settle();
check("integrity scan lists labelled anomaly types", text().includes("payload hash altered") && text().includes("credential issued before completion"));
await buttonWith(app(), "Run evaluation").click(); await settle();
check("evaluation shows precision/recall and confusion matrix", text().includes("Precision") && text().includes("Confusion matrix"));
await go("/audit");
await buttonWith(app(), "Verify hash chain").click(); await settle();
check("audit hash chain verifies in the UI", text().includes("Chain intact"));

await login(ACCOUNTS.learner);
await go("/account");
fill(app(), { current_password: PASSWORD, new_password: "A-new-Passw0rd-123" });
await submit(app());
check("change password form succeeds", text().includes("Password updated"));
await go("/credentials");
const firstLink = app().find((e) => e.tagName === "A" && (e.attrs.href || "").startsWith("#/credentials/CRD"));
if (firstLink) {
  await go(firstLink.attrs.href.slice(1));
  check("learner opens own credential and sees signed record", text().includes("Signed record") && !text().includes("Revoke"));
}

console.log(`\n${checks - failures}/${checks} frontend checks passed`);
process.exit(failures ? 1 : 0);
