import { api, qs } from "../api.js";
import { h, mount, form, card, dataTable, loading, errorBox, badge, definitionList, modal, confirmDialog, formatTs, formatDate, pageHeader, toast, errorMessage } from "../ui.js";
import { can } from "../roles.js";

function simpleTable(headers, rows) {
  return h("div", { class: "table-scroll" }, h("table", { class: "table" }, h("thead", {}, h("tr", {}, headers.map((t) => h("th", {}, t)))),
    h("tbody", {}, rows.map((cells) => h("tr", {}, cells.map((c) => h("td", {}, c ?? "—")))))));
}

export function issuersPage({ user }) {
  const root = h("div", {}, loading());
  const load = async () => {
    try {
      const issuers = await api("/issuers");
      const create = can(user, ["platform_admin"]) ? h("button", { class: "btn btn-primary", onClick: () => {
        const dialog = modal({ title: "Register issuer", body: form({ fields: [{ name: "name", label: "Issuer name", required: true }], submitLabel: "Register issuer and create signing key", onCancel: () => dialog.close(),
          onSubmit: async (v) => { const i = await api("/issuers", { method: "POST", body: v }); dialog.close(); toast(`Registered ${i.issuer_id}`); load(); } }) });
      } }, "Register issuer") : null;
      mount(root, pageHeader("Issuers", "Organisations that sign credentials. Retired issuers stay verifiable through their published keys.", create),
        card(null, simpleTable(["ID", "Name", "Status", "Active key", "Credentials", "Valid from", "Valid to", "Successor"],
          issuers.map((i) => [h("a", { href: `#/issuers/${i.issuer_id}` }, i.issuer_id), i.name, badge(i.status), i.active_key_id, i.credential_count, formatDate(i.valid_from), i.valid_to ? formatDate(i.valid_to) : "—", i.successor_name]))));
    } catch (err) { mount(root, errorBox(err, load)); }
  };
  load();
  return root;
}

export function issuerDetailPage({ user, params }) {
  const root = h("div", {}, loading());
  const load = async () => {
    try {
      const i = await api(`/issuers/${params.id}`);
      const platform = can(user, ["platform_admin"]);
      const buttons = [];
      if (platform && i.status === "active") {
        buttons.push(h("button", { class: "btn", onClick: async () => {
          if (!(await confirmDialog({ title: "Rotate signing key", message: "A new key becomes the active signing key. The old key remains published so existing credentials still verify.", confirmLabel: "Rotate key" }))) return;
          try { await api(`/issuers/${i.issuer_id}/rotate-key`, { method: "POST" }); toast("Key rotated"); load(); } catch (err) { toast(errorMessage(err), "error"); }
        } }, "Rotate key"));
        buttons.push(h("button", { class: "btn btn-danger", onClick: async () => {
          const all = await api("/issuers");
          const options = all.filter((x) => x.status === "active" && x.issuer_id !== i.issuer_id).map((x) => ({ value: x.issuer_id, label: `${x.name} (${x.issuer_id})` }));
          const dialog = modal({ title: `Retire ${i.name}`, body: h("div", {}, h("div", { class: "alert alert-warn" }, "All rules currently assigned to this issuer move to the successor from now on. Credentials already issued are unaffected."),
            form({ fields: [{ name: "successor_issuer_id", label: "Successor issuer", type: "select", required: true, options }], submitLabel: "Retire issuer", onCancel: () => dialog.close(),
              onSubmit: async (v) => { await api(`/issuers/${i.issuer_id}/retire`, { method: "POST", body: v }); dialog.close(); toast("Issuer retired and rules transferred"); load(); } })) });
        } }, "Retire issuer"));
      }
      mount(root, pageHeader(i.name, i.issuer_id, buttons),
        card("Details", definitionList([["Status", badge(i.status)], ["Valid from", formatTs(i.valid_from)], ["Valid to", i.valid_to ? formatTs(i.valid_to) : "—"], ["Successor", i.successor_issuer_id ? h("a", { href: `#/issuers/${i.successor_issuer_id}` }, i.successor_issuer_id) : "—"], ["Credentials issued", i.credential_count]])),
        card("Signing keys (public)", simpleTable(["Key", "Algorithm", "Status", "Valid from", "Valid to", "Public key (base64)"], i.keys.map((k) => [k.key_id, k.algorithm, badge(k.status), formatTs(k.valid_from), k.valid_to ? formatTs(k.valid_to) : "—", h("span", { class: "mono" }, k.public_key_b64)]))),
        card("Rule assignments", simpleTable(["Rule", "Programme", "From", "To"], i.rule_assignments.map((a) => [h("a", { href: `#/rules/${a.rule_id}` }, a.rule_id), a.title, formatTs(a.effective_from), a.effective_to ? formatTs(a.effective_to) : "current"]))));
    } catch (err) { mount(root, errorBox(err, load)); }
  };
  load();
  return root;
}

export function auditPage() {
  const holder = h("div", {}, loading());
  const chainBox = h("div", {});
  const build = (actions) => {
    const table = dataTable({
      filters: [{ name: "q", label: "Search entity or event ID" }, { name: "action", label: "All actions", type: "select", options: actions },
        { name: "entity_type", label: "All entity types", type: "select", options: ["credential", "verification_request", "completion_record", "credential_rule", "issuer", "learner", "course", "app_user"] }],
      load: (p) => api(`/audit${qs(p)}`),
      columns: [{ label: "Seq", render: (r) => r.seq }, { label: "When", render: (r) => formatTs(r.occurred_at) }, { label: "Action", render: (r) => r.action },
        { label: "Entity", render: (r) => `${r.entity_type} ${r.entity_id}` }, { label: "Actor", render: (r) => (r.actor_user_id || r.actor_type) },
        { label: "Details", render: (r) => h("a", { href: "#/audit", onClick: (e) => { e.preventDefault(); modal({ title: r.event_id, wide: true, body: h("div", {}, h("pre", {}, JSON.stringify(JSON.parse(r.details_json), null, 2)), definitionList([["Previous hash", h("span", { class: "mono" }, r.prev_hash)], ["Event hash", h("span", { class: "mono" }, r.event_hash)]])) }); } }, "View") }],
    });
    const verify = h("button", { class: "btn btn-primary", onClick: async () => {
      mount(chainBox, loading("Verifying hash chain…"));
      try {
        const r = await api("/audit/verify-chain");
        mount(chainBox, h("div", { class: r.valid ? "alert alert-good" : "alert alert-error" }, r.valid ? `Chain intact: ${r.events_checked.toLocaleString()} events verified.` : `Chain broken at ${r.first_broken_event}: ${r.problem}`));
      } catch (err) { mount(chainBox, errorBox(err)); }
    } }, "Verify hash chain");
    return h("div", {}, h("div", { class: "page-actions" }, verify), chainBox, card(null, table));
  };
  api("/audit/actions").then((a) => mount(holder, build(a))).catch((e) => mount(holder, errorBox(e)));
  return h("div", {}, pageHeader("Audit log", "Immutable, hash-chained history. Events cannot be edited or deleted."), holder);
}

function renderScan(scan) {
  const types = Object.keys(scan.counts);
  return h("div", {}, h("div", { class: scan.total_findings ? "alert alert-warn" : "alert alert-good" }, `${scan.total_findings} finding(s). Audit chain ${scan.audit_chain.valid ? "intact" : "BROKEN"}.`),
    types.length ? simpleTable(["Issue type", "Count"], types.map((t) => [t.replace(/_/g, " "), scan.counts[t]])) : null,
    ...types.map((t) => h("div", {}, h("h3", {}, `${t.replace(/_/g, " ")} (showing ${scan.findings[t].length} of ${scan.counts[t]})`),
      simpleTable(["Entity", "Related", "Detail"], scan.findings[t].map((f) => [f.entity_id, f.related_entity_id, f.detail])))));
}

function renderEvaluation(e) {
  const v = e.verification_engine;
  const pct = (x) => (x === null ? "—" : `${(x * 100).toFixed(2)}%`);
  const statuses = [...new Set([...Object.keys(v.confusion_matrix), ...Object.values(v.confusion_matrix).flatMap((r) => Object.keys(r))])].sort();
  return h("div", {}, h("h3", {}, "Anomaly detection vs ground truth"),
    simpleTable(["Issue type", "Labelled", "Detected", "TP", "FP", "FN", "Precision", "Recall"], e.detection.map((d) => [d.issue_type.replace(/_/g, " "), d.labelled, d.detected, d.true_positives, d.false_positives, d.false_negatives, pct(d.precision), pct(d.recall)])),
    h("h3", {}, "Verification engine"), definitionList([["Requests evaluated", v.requests_evaluated.toLocaleString()], ["Engine result accuracy", pct(v.engine_result_accuracy)], ["Engine identity accuracy", pct(v.engine_identity_accuracy)],
      ["Recorded result accuracy", pct(v.recorded_result_accuracy)], ["Recorded results that were wrong", v.recorded_result_errors]]),
    h("h3", {}, "Confusion matrix (rows: expected, columns: engine)"),
    simpleTable(["Expected \\ Engine", ...statuses], Object.keys(v.confusion_matrix).sort().map((exp) => [exp, ...statuses.map((s) => v.confusion_matrix[exp][s] || 0)])),
    v.recorded_error_samples.length ? [h("h3", {}, "Recorded results that disagree with the rules"), simpleTable(["Verification", "Expected", "Recorded"], v.recorded_error_samples.map((s) => [s.verification_id, badge(s.expected), badge(s.recorded)]))] : null);
}

export function integrityPage() {
  const scanBox = h("div", { class: "muted" }, "Run a scan to look for anomalies in the stored data. The scanner only reads database records.");
  const evalBox = h("div", { class: "muted" }, "Compares scanner findings and verification decisions with the separate ground-truth files.");
  const rejectBox = h("div", {}, loading());
  const runner = (box, path, render, label) => h("button", { class: "btn btn-primary", onClick: async () => {
    mount(box, loading(label));
    try { mount(box, render(await api(path))); } catch (err) { mount(box, errorBox(err)); }
  } }, label);
  api("/integrity/import-rejections").then((rows) => mount(rejectBox, rows.length ? simpleTable(["Source file", "Row", "Record key", "Reason"], rows.map((r) => [r.source_file, r.row_number, r.record_key, r.reason])) : h("p", { class: "muted" }, "No rows were rejected during import."))).catch((e) => mount(rejectBox, errorBox(e)));
  return h("div", {}, pageHeader("Data integrity & evaluation", "Detects the labelled edge cases and measures detection quality."),
    card("Integrity scan", h("div", {}, runner(scanBox, "/integrity/scan", renderScan, "Run integrity scan"), scanBox)),
    card("Rows rejected at import by database constraints", rejectBox),
    card("Evaluation against ground truth", h("div", {}, runner(evalBox, "/integrity/evaluation", renderEvaluation, "Run evaluation"), evalBox)));
}

export function usersPage({ user }) {
  let table;
  const showPassword = (title, password) => modal({ title, body: h("div", {}, h("div", { class: "alert alert-warn" }, "Copy this temporary password now. It is not stored and cannot be shown again."), h("pre", {}, password)) });
  const create = h("button", { class: "btn btn-primary", onClick: () => {
    const dialog = modal({ title: "Create user", body: form({
      fields: [{ name: "email", label: "Email", type: "email", required: true }, { name: "role", label: "Role", type: "select", required: true, options: ["learner", "instructor", "academic_admin", "support_staff", "platform_admin"] },
        { name: "learner_id", label: "Learner ID", hint: "Required for the learner role." }, { name: "instructor_id", label: "Instructor ID", hint: "Required for the instructor role." },
        { name: "password", label: "Password", type: "password", hint: "Leave empty to generate a temporary password." }],
      submitLabel: "Create user", onCancel: () => dialog.close(),
      onSubmit: async (v) => { const u = await api("/users", { method: "POST", body: v }); dialog.close(); table.refresh(); toast(`Created ${u.user_id}`); if (u.temporary_password) showPassword(`Temporary password for ${u.email}`, u.temporary_password); } }) });
  } }, "Create user");
  table = dataTable({
    filters: [{ name: "q", label: "Search email or ID" }, { name: "role", label: "All roles", type: "select", options: ["learner", "instructor", "academic_admin", "support_staff", "platform_admin"] }],
    load: (p) => api(`/users${qs(p)}`), actions: create,
    columns: [{ key: "user_id", label: "ID" }, { key: "email", label: "Email" }, { label: "Role", render: (r) => r.role.replace(/_/g, " ") }, { label: "Linked record", render: (r) => r.learner_id || r.instructor_id || "—" },
      { label: "Password set", render: (r) => (r.has_password ? "Yes" : "No") }, { label: "Active", render: (r) => badge(r.is_active ? "active" : "closed") },
      { label: "", render: (r) => h("span", {},
        h("button", { class: "btn btn-small", disabled: r.user_id === user.user_id, onClick: async () => {
          try { await api(`/users/${r.user_id}`, { method: "PATCH", body: { is_active: !r.is_active } }); toast(r.is_active ? "User deactivated" : "User activated"); table.refresh(); } catch (err) { toast(errorMessage(err), "error"); } } }, r.is_active ? "Deactivate" : "Activate"), " ",
        h("button", { class: "btn btn-small", onClick: async () => {
          if (!(await confirmDialog({ title: "Reset password", message: `Generate a new temporary password for ${r.email}?`, confirmLabel: "Reset" }))) return;
          try { const out = await api(`/users/${r.user_id}/reset-password`, { method: "POST" }); showPassword(`Temporary password for ${r.email}`, out.temporary_password); table.refresh(); } catch (err) { toast(errorMessage(err), "error"); } } }, "Reset password")) }],
  });
  return h("div", {}, pageHeader("Users", "Accounts, roles and access. Passwords are stored as salted hashes."), card(null, table));
}

export function accountPage({ user }) {
  return h("div", {}, pageHeader("My account", user.email),
    card("Change password", form({ fields: [{ name: "current_password", label: "Current password", type: "password", required: true, autocomplete: "current-password" },
      { name: "new_password", label: "New password", type: "password", required: true, hint: "At least 10 characters.", autocomplete: "new-password" }],
      submitLabel: "Update password", onSubmit: async (v) => { await api("/auth/change-password", { method: "POST", body: v }); toast("Password updated"); } })),
    card("Role", definitionList([["Role", user.role.replace(/_/g, " ")], ["User ID", user.user_id], ["Linked learner", user.learner_id], ["Linked instructor", user.instructor_id]])));
}
