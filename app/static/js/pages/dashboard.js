import { api, downloadCsv } from "../api.js";
import { barChart, donutChart, lineChart } from "../charts.js";
import { h, mount, card, kpi, loading, errorBox, badge, formatDate, pageHeader, toast, errorMessage } from "../ui.js";

function exportButton(name, label) {
  return h("button", { class: "btn btn-small", onClick: async () => {
    try { await downloadCsv(`/reports/export/${name}`, `${name}.csv`); toast("Export downloaded"); }
    catch (err) { toast(errorMessage(err), "error"); }
  } }, label);
}

async function staffDashboard(root) {
  const d = await api("/reports/dashboard");
  const k = d.kpis;
  const n = (v) => Number(v).toLocaleString();
  mount(root,
    h("div", { class: "grid grid-kpi" },
      kpi("Credentials issued", n(k.credentials_total), `${n(k.credentials_active)} active`),
      kpi("Revoked", n(k.credentials_revoked), `${k.revocation_rate_pct}% of issued`),
      kpi("Expired", n(k.credentials_expired)),
      kpi("Verification checks", n(k.verifications_total), `${k.verification_valid_rate_pct}% returned valid`),
      kpi("Pending issuance", n(k.pending_issuance), `${k.issuance_coverage_pct}% of eligible issued`),
      kpi("Avg days to issue", k.mean_days_completion_to_issuance ?? "—", "last completion to issuance"),
      kpi("Learners", n(k.learners)), kpi("Courses", n(k.courses))),
    h("div", { class: "grid grid-2" },
      card("Credentials issued per month", lineChart(d.credentials_by_month)),
      card("Verification outcomes", donutChart(d.verification_outcomes)),
      card("Verification identity checks", donutChart(d.identity_outcomes)),
      card("Revocation reasons", barChart(d.revocation_reasons)),
      card("Credentials by issuer", barChart(d.issuer_breakdown)),
      card("Course completion funnel", donutChart(d.completion_funnel)),
      card("Top credential programmes", barChart(d.top_rules)),
      card("Verification checks per month", lineChart(d.verifications_by_month))),
    h("p", { class: "muted" }, `Generated ${d.generated_at}. `, exportButton("credentials", "Export credentials CSV"), " ",
      exportButton("verifications", "Export verifications CSV"), " ", exportButton("revocations", "Export revocations CSV"), " ",
      exportButton("pending_issuance", "Export pending issuance CSV")));
}

async function learnerDashboard(root) {
  const d = await api("/reports/me");
  mount(root,
    card("My credentials", d.credentials.length ? h("div", { class: "table-scroll" }, h("table", { class: "table" },
      h("thead", {}, h("tr", {}, ["Credential", "Programme", "Issuer", "Issued", "Expires", "Status", ""].map((t) => h("th", {}, t)))),
      h("tbody", {}, d.credentials.map((c) => {
        const expired = c.status === "active" && c.expires_at && c.expires_at <= d.now;
        return h("tr", {}, h("td", {}, h("a", { href: `#/credentials/${c.credential_id}` }, c.credential_id)), h("td", {}, c.rule_title),
          h("td", {}, c.issuer_name), h("td", {}, formatDate(c.issued_at)), h("td", {}, c.expires_at ? formatDate(c.expires_at) : "Never"),
          h("td", {}, badge(expired ? "expired" : c.status)), h("td", {}, h("a", { href: `#/verify?id=${c.credential_id}` }, "Verify")));
      })))) : h("p", { class: "empty" }, "You have not earned a credential yet.")),
    card("My course progress", donutChart(d.completion_breakdown)));
}

async function instructorDashboard(root) {
  const d = await api("/reports/me");
  mount(root, card("My courses", d.courses.length ? h("div", { class: "table-scroll" }, h("table", { class: "table" },
    h("thead", {}, h("tr", {}, ["Course", "Status", "Enrolled", "In progress", "Completed", "Failed", "Avg score"].map((t) => h("th", {}, t)))),
    h("tbody", {}, d.courses.map((c) => h("tr", {}, h("td", {}, h("a", { href: `#/courses/${c.course_id}` }, `${c.course_id} ${c.title}`)), h("td", {}, badge(c.status)),
      h("td", {}, c.enrollments), h("td", {}, c.in_progress ?? 0), h("td", {}, c.completed ?? 0), h("td", {}, c.failed ?? 0), h("td", {}, c.average_score ?? "—")))))) :
    h("p", { class: "empty" }, "No courses are assigned to you.")));
}

export function dashboardPage({ user }) {
  const root = h("div", {}, loading());
  const run = async () => {
    try {
      if (user.role === "learner") await learnerDashboard(root);
      else if (user.role === "instructor") await instructorDashboard(root);
      else await staffDashboard(root);
    } catch (err) { mount(root, errorBox(err, run)); }
  };
  run();
  return h("div", {}, pageHeader("Dashboard", `Signed in as ${user.email}`), root);
}
