import { api, session, setUnauthorizedHandler } from "./api.js";
import { h, mount, toast } from "./ui.js";
import { loginPage, verifyPage } from "./pages/public.js";
import { dashboardPage } from "./pages/dashboard.js";
import { learnersPage, learnerDetailPage, coursesPage, courseDetailPage, completionsPage, completionDetailPage } from "./pages/people.js";
import { rulesPage, ruleDetailPage, issuancePage, credentialsPage, credentialDetailPage, verificationsPage, revocationsPage } from "./pages/credentials.js";
import { issuersPage, issuerDetailPage, auditPage, integrityPage, usersPage, accountPage } from "./pages/admin.js";

const ALL = ["learner", "instructor", "academic_admin", "support_staff", "platform_admin"];
const STAFF = ["academic_admin", "support_staff", "platform_admin"];
const ADMINS = ["academic_admin", "platform_admin"];

export const ROUTES = [
  { path: "/login", public: true, render: loginPage },
  { path: "/verify", public: true, render: verifyPage },
  { path: "/dashboard", roles: ALL, render: dashboardPage, nav: ["Dashboard", ALL, "Overview"] },
  { path: "/learners", roles: STAFF, render: learnersPage, nav: ["Learners", STAFF, "People"] },
  { path: "/learners/:id", roles: ["learner", ...STAFF], render: learnerDetailPage },
  { path: "/courses", roles: ["instructor", ...STAFF], render: coursesPage, nav: ["Courses", ["instructor", ...STAFF], "Learning"] },
  { path: "/courses/:id", roles: ["instructor", ...STAFF], render: courseDetailPage },
  { path: "/completions", roles: ALL, render: completionsPage, nav: ["Completions", ALL, "Learning"] },
  { path: "/completions/:id", roles: ALL, render: completionDetailPage },
  { path: "/rules", roles: ["instructor", ...STAFF], render: rulesPage, nav: ["Credential rules", ["instructor", ...STAFF], "Credentials"] },
  { path: "/rules/:id", roles: ["instructor", ...STAFF], render: ruleDetailPage },
  { path: "/issuance", roles: STAFF, render: issuancePage, nav: ["Issuance", STAFF, "Credentials"] },
  { path: "/credentials", roles: ["learner", ...STAFF], render: credentialsPage, nav: ["Credentials", ["learner", ...STAFF], "Credentials"] },
  { path: "/credentials/:id", roles: ["learner", ...STAFF], render: credentialDetailPage },
  { path: "/verifications", roles: ["learner", ...STAFF], render: verificationsPage, nav: ["Verifications", ["learner", ...STAFF], "Credentials"] },
  { path: "/revocations", roles: STAFF, render: revocationsPage, nav: ["Revocations", STAFF, "Credentials"] },
  { path: "/issuers", roles: STAFF, render: issuersPage, nav: ["Issuers", STAFF, "Governance"] },
  { path: "/issuers/:id", roles: STAFF, render: issuerDetailPage },
  { path: "/audit", roles: STAFF, render: auditPage, nav: ["Audit log", STAFF, "Governance"] },
  { path: "/integrity", roles: ADMINS, render: integrityPage, nav: ["Integrity & evaluation", ADMINS, "Governance"] },
  { path: "/users", roles: ["platform_admin"], render: usersPage, nav: ["Users", ["platform_admin"], "Governance"] },
  { path: "/account", roles: ALL, render: accountPage, nav: ["My account", ALL, "Overview"] },
];

export function parseHash(hash) {
  const raw = (hash || "").replace(/^#/, "") || "/";
  const [path, search = ""] = raw.split("?");
  const query = {};
  new URLSearchParams(search).forEach((v, k) => { query[k] = v; });
  return { path, query };
}

export function matchRoute(path) {
  for (const route of ROUTES) {
    const names = [];
    const pattern = new RegExp("^" + route.path.replace(/:([a-z]+)/g, (_, n) => { names.push(n); return "([^/]+)"; }) + "$");
    const m = path.match(pattern);
    if (m) return { route, params: Object.fromEntries(names.map((n, i) => [n, decodeURIComponent(m[i + 1])])) };
  }
  return null;
}

function navigate(path, replace = false) {
  const target = `#${path}`;
  if (replace) { location.replace(target); if (location.hash === target) render(); }
  else location.hash = target;
}

function layout(user, content, activePath) {
  const groups = {};
  ROUTES.filter((r) => r.nav && r.nav[1].includes(user.role)).forEach((r) => { (groups[r.nav[2]] = groups[r.nav[2]] || []).push(r); });
  const nav = h("nav", { class: "nav", "aria-label": "Main" }, Object.entries(groups).map(([group, routes]) => [
    h("div", { class: "nav-group" }, group), ...routes.map((r) => h("a", { href: `#${r.path}`, class: activePath === r.path || activePath.startsWith(r.path + "/") ? "active" : "" }, r.nav[0]))]),
    h("div", { class: "nav-group" }, "Public"), h("a", { href: "#/verify", class: activePath === "/verify" ? "active" : "" }, "Verify a credential"));
  const sidebar = h("aside", { class: "sidebar", id: "sidebar" }, h("div", { class: "brand" }, "Credential Platform"), nav);
  sidebar.addEventListener("click", (e) => { if (e.target.tagName === "A") sidebar.classList.remove("open"); });
  const topbar = h("header", { class: "topbar" },
    h("button", { class: "btn menu-toggle", "aria-label": "Toggle navigation", onClick: () => sidebar.classList.toggle("open") }, "☰"),
    h("div", { class: "who" }, h("span", {}, user.email), h("span", { class: "badge badge-info" }, user.role.replace(/_/g, " ")),
      h("button", { class: "btn btn-small", onClick: () => { session.clear(); navigate("/login"); } }, "Sign out")));
  return h("div", { class: "shell" }, sidebar, h("div", { class: "main" }, topbar, h("main", { class: "content", id: "content" }, content)));
}

export async function render() {
  const root = document.getElementById("app");
  const { path, query } = parseHash(location.hash);
  const found = matchRoute(path);
  const user = session.token ? session.user : null;
  if (path === "/" || !found) { navigate(user ? "/dashboard" : "/login", true); return; }
  const { route, params } = found;
  const ctx = { user, params, query, navigate };
  if (route.public) {
    if (route.path === "/login" && user) { navigate("/dashboard", true); return; }
    mount(root, route.render(ctx));
    return;
  }
  if (!user) { navigate("/login", true); return; }
  if (!route.roles.includes(user.role)) {
    mount(root, layout(user, h("div", { class: "alert alert-error" }, "Your role does not have access to this page."), path));
    return;
  }
  try {
    const me = await api("/auth/me");
    if (me.role !== user.role) { session.clear(); navigate("/login", true); return; }
  } catch (err) { return; }
  mount(root, layout(user, route.render(ctx), path));
}

export function start() {
  setUnauthorizedHandler((message) => { session.clear(); toast(message || "Please sign in again", "error"); navigate("/login", true); });
  window.addEventListener("hashchange", render);
  return render();
}

if (typeof window !== "undefined" && !window.__TESTING__) start();
