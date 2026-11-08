import { api, qs, ApiError } from "../api.js";
import { h, mount, form, card, dataTable, loading, errorBox, badge, definitionList, modal, confirmDialog, checkList, formatTs, formatDate, pageHeader, toast, errorMessage } from "../ui.js";
import { can, ADMIN_ROLES, STAFF_ROLES } from "../roles.js";
import { renderVerification } from "./public.js";

const REASONS = ["issued_in_error", "learner_request", "academic_misconduct", "fraud", "rule_change"];

function coursePicker() {
  const selected = new Map();
  const list = h("div", {});
  const results = h("div", { class: "picker-results hidden" });
  let timer = null;
  const renderSelected = () => mount(list, ...[...selected.entries()].map(([id, info]) => h("div", { class: "selected-row" },
    h("span", {}, `${id} — ${info.title}`),
    h("label", {}, h("input", { type: "checkbox", checked: info.mandatory, onChange: (e) => { info.mandatory = e.target.checked; } }), " mandatory"),
    h("button", { type: "button", class: "btn btn-small", onClick: () => { selected.delete(id); renderSelected(); } }, "Remove"))));
  const search = h("input", { type: "search", placeholder: "Search courses to add (title or ID)", "aria-label": "Search courses", onInput: (e) => {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const q = e.target.value.trim();
      if (!q) { results.classList.add("hidden"); return; }
      const found = await api(`/courses${qs({ q, status: "active", page_size: 8 })}`);
      mount(results, ...found.items.map((c) => h("button", { type: "button", onClick: () => { selected.set(c.course_id, { title: c.title, mandatory: false }); renderSelected(); results.classList.add("hidden"); search.value = ""; } }, `${c.course_id} — ${c.title} (${c.category})`)));
      results.classList.remove("hidden");
    }, 250);
  } });
  return { element: h("div", { class: "field" }, h("label", {}, "Courses in this rule", h("span", { class: "req" }, " *")), search, results, list),
    value: () => [...selected.entries()].map(([course_id, info]) => ({ course_id, is_mandatory: info.mandatory })) };
}

export function rulesPage({ user, query }) {
  let table;
  const actions = can(user, ADMIN_ROLES) ? h("button", { class: "btn btn-primary", onClick: async () => {
    const issuers = (await api("/issuers")).filter((i) => i.status === "active");
    const picker = coursePicker();
    const f = form({
      fields: [{ name: "title", label: "Title", required: true }, { name: "credential_type", label: "Type", type: "select", required: true, options: ["micro_credential", "certificate", "professional_certificate"] },
        { name: "min_courses_required", label: "Minimum courses to complete", type: "number", required: true, min: 1 },
        { name: "min_avg_score", label: "Minimum average score (%)", type: "number", required: true, min: 0, max: 100 },
        { name: "min_course_score", label: "Minimum score per counted course (%)", type: "number", required: true, min: 0, max: 100 },
        { name: "validity_months", label: "Validity (months)", type: "number", min: 1, hint: "Leave empty for credentials that never expire." },
        { name: "issuer_id", label: "Issuer", type: "select", required: true, options: issuers.map((i) => ({ value: i.issuer_id, label: `${i.name} (${i.issuer_id})` })) }],
      submitLabel: "Create rule", onCancel: () => dialog.close(),
      onSubmit: async (v) => {
        const courses = picker.value();
        if (!courses.length) throw new ApiError(400, "VALIDATION_ERROR", "Add at least one course");
        const r = await api("/rules", { method: "POST", body: { ...v, courses } });
        dialog.close(); toast(`Created ${r.rule_id}`); table.refresh();
      },
    });
    const dialog = modal({ title: "Create credential rule", wide: true, body: h("div", {}, picker.element, f) });
  } }, "Create rule") : null;
  table = dataTable({
    initial: { q: query.q || "" },
    filters: [{ name: "q", label: "Search title or ID" }, { name: "status", label: "All statuses", type: "select", options: ["active", "retired", "draft"] }],
    load: (p) => api(`/rules${qs(p)}`),
    columns: [{ label: "ID", render: (r) => h("a", { href: `#/rules/${r.rule_id}` }, r.rule_id) }, { key: "title", label: "Programme" }, { label: "Type", render: (r) => r.credential_type.replace(/_/g, " ") },
      { label: "Courses", render: (r) => `${r.min_courses_required} of ${r.course_count}` }, { label: "Min avg", render: (r) => `${r.min_avg_score}%` },
      { label: "Validity", render: (r) => (r.validity_months ? `${r.validity_months} mo` : "No expiry") }, { key: "current_issuer", label: "Issuer" },
      { label: "Issued", render: (r) => r.credential_count }, { label: "Status", render: (r) => badge(r.status) }],
    actions,
  });
  return h("div", {}, pageHeader("Credential rules", "What a learner must complete before a credential can be issued."), card(null, table));
}

export function ruleDetailPage({ user, params }) {
  const root = h("div", {}, loading());
  const load = async () => {
    try {
      const r = await api(`/rules/${params.id}`);
      const admin = can(user, ADMIN_ROLES);
      const changeIssuer = admin && r.status !== "retired" ? h("button", { class: "btn", onClick: async () => {
        const issuers = (await api("/issuers")).filter((i) => i.status === "active");
        const dialog = modal({ title: "Change issuer", body: form({ fields: [{ name: "issuer_id", label: "New issuer", type: "select", required: true, options: issuers.map((i) => ({ value: i.issuer_id, label: `${i.name} (${i.issuer_id})` })) }],
          submitLabel: "Change issuer", onCancel: () => dialog.close(), onSubmit: async (v) => { await api(`/rules/${r.rule_id}/issuer`, { method: "POST", body: v }); dialog.close(); toast("Issuer changed; history preserved"); load(); } }) });
      } }, "Change issuer") : null;
      const retire = admin && r.status !== "retired" ? h("button", { class: "btn btn-danger", onClick: async () => {
        if (!(await confirmDialog({ title: "Retire rule", message: "No new credentials will be issued under this rule. Existing credentials stay valid.", confirmLabel: "Retire rule", danger: true }))) return;
        try { await api(`/rules/${r.rule_id}/retire`, { method: "POST" }); toast("Rule retired"); load(); } catch (err) { toast(errorMessage(err), "error"); }
      } }, "Retire rule") : null;
      mount(root, pageHeader(r.title, r.rule_id, [changeIssuer, retire]),
        card("Requirements", definitionList([["Type", r.credential_type.replace(/_/g, " ")], ["Courses required", `${r.min_courses_required} of ${r.courses.length} (mandatory ones must all be completed)`],
          ["Minimum score per course", `${r.min_course_score}%`], ["Minimum average", `${r.min_avg_score}%`], ["Validity", r.validity_months ? `${r.validity_months} months` : "Never expires"],
          ["Effective", `${formatTs(r.effective_from)} → ${r.effective_to ? formatTs(r.effective_to) : "open-ended"}`], ["Status", badge(r.status)], ["Credentials issued", r.credential_count]])),
        card("Courses", h("table", { class: "table" }, h("thead", {}, h("tr", {}, ["Course", "Title", "Pass mark", "Requirement"].map((t) => h("th", {}, t)))),
          h("tbody", {}, r.courses.map((c) => h("tr", {}, h("td", {}, h("a", { href: `#/courses/${c.course_id}` }, c.course_id)), h("td", {}, c.title), h("td", {}, `${c.pass_mark}%`), h("td", {}, c.is_mandatory ? badge("mandatory") : badge("optional"))))))),
        card("Issuer history", h("table", { class: "table" }, h("thead", {}, h("tr", {}, ["Issuer", "From", "To"].map((t) => h("th", {}, t)))),
          h("tbody", {}, r.issuer_history.map((a) => h("tr", {}, h("td", {}, user.role === "instructor" ? a.issuer_name : h("a", { href: `#/issuers/${a.issuer_id}` }, a.issuer_name)), h("td", {}, formatTs(a.effective_from)), h("td", {}, a.effective_to ? formatTs(a.effective_to) : "current")))))));
    } catch (err) { mount(root, errorBox(err, load)); }
  };
  load();
  return root;
}

export function issuancePage({ user, navigate }) {
  const admin = can(user, ADMIN_ROLES);
  const resultBox = h("div", {});
  const review = async (learnerId, ruleId) => {
    try {
      const e = await api(`/eligibility${qs({ learner_id: learnerId, rule_id: ruleId })}`);
      const dialog = modal({ title: `${e.learner_name} → ${e.rule_title}`, wide: true, body: h("div", {},
        h("p", {}, e.eligible ? badge("active") : badge("failed"), " ", e.eligible ? "All requirements are met." : "Requirements are not met — see the failed checks."),
        h("p", { class: "muted" }, `Average of counted courses: ${e.average_score}. Evaluated ${formatTs(e.evaluated_as_of)}.`), checkList(e.checks),
        admin ? h("div", { class: "form-actions" }, h("button", { class: "btn btn-primary", disabled: !e.eligible, onClick: async () => {
          try { const c = await api("/credentials", { method: "POST", body: { learner_id: learnerId, rule_id: ruleId } }); dialog.close(); toast(`Issued ${c.credential_id}`); navigate(`/credentials/${c.credential_id}`); }
          catch (err) { toast(errorMessage(err), "error"); }
        } }, "Issue credential")) : null) });
    } catch (err) { toast(errorMessage(err), "error"); }
  };
  const checker = form({ fields: [{ name: "learner_id", label: "Learner ID", required: true, placeholder: "LRN-000001" }, { name: "rule_id", label: "Rule ID", required: true, placeholder: "RUL-000001" }],
    submitLabel: "Check eligibility", onSubmit: async (v) => { await review(v.learner_id, v.rule_id); } });
  checker.classList.add("form-grid");
  const queue = dataTable({
    filters: [{ name: "q", label: "Search learner, ID or programme" }, { name: "rule_id", label: "Rule ID (e.g. RUL-000001)" }],
    load: (p) => api(`/eligibility/pending${qs(p)}`), emptyText: "No eligible learners are waiting for a credential.",
    columns: [{ label: "Learner", render: (r) => h("a", { href: `#/learners/${r.learner_id}` }, `${r.learner_name} (${r.learner_id})`) }, { label: "Programme", render: (r) => h("a", { href: `#/rules/${r.rule_id}` }, r.rule_title) },
      { label: "Average", render: (r) => r.average_score }, { label: "Last course completed", render: (r) => formatDate(r.latest_completion_at) },
      { label: "", render: (r) => h("button", { class: "btn btn-small btn-primary", onClick: () => review(r.learner_id, r.rule_id) }, admin ? "Review & issue" : "Review") }],
  });
  return h("div", {}, pageHeader("Credential issuance", "Credentials are only issued after the rule is re-evaluated against the learner's completion records."),
    card("Check a learner against a rule", checker), resultBox, card("Eligible and waiting for issuance", queue));
}

export function credentialsPage({ user, query }) {
  const staff = can(user, STAFF_ROLES);
  const table = dataTable({
    initial: { q: query.q || "", status: query.status || "" },
    filters: [{ name: "q", label: staff ? "Search credential ID or learner" : "Search credential ID" }, { name: "status", label: "All statuses", type: "select", options: ["active", "expired", "revoked"] },
      ...(staff ? [{ name: "rule_id", label: "Rule ID" }, { name: "issuer_id", label: "Issuer ID" }] : [])],
    load: (p) => api(`/credentials${qs(p)}`),
    columns: [{ label: "Credential", render: (r) => h("a", { href: `#/credentials/${r.credential_id}` }, r.credential_id) },
      ...(staff ? [{ label: "Learner", render: (r) => h("a", { href: `#/learners/${r.learner_id}` }, r.learner_name) }] : []),
      { key: "rule_title", label: "Programme" }, { key: "issuer_name", label: "Issuer" }, { label: "Issued", render: (r) => formatDate(r.issued_at) },
      { label: "Expires", render: (r) => (r.expires_at ? formatDate(r.expires_at) : "Never") }, { label: "Status", render: (r) => badge(r.effective_status) }],
  });
  return h("div", {}, pageHeader(staff ? "Credentials" : "My credentials", staff ? "Every issued credential with its current lifecycle state." : "Credentials issued to you."), card(null, table));
}

function downloadJson(filename, data) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url);
}

export function credentialDetailPage({ user, params }) {
  const root = h("div", {}, loading());
  const load = async () => {
    try {
      const c = await api(`/credentials/${params.id}`);
      const staff = can(user, STAFF_ROLES);
      const buttons = [
        h("button", { class: "btn", onClick: async () => {
          try { downloadJson(`${c.credential_id}.json`, await api(`/public/credentials/${c.credential_id}/document`, { auth: false })); } catch (err) { toast(errorMessage(err), "error"); }
        } }, "Download signed record"),
        h("a", { class: "btn", href: `#/verify?id=${c.credential_id}` }, "Open public verifier"),
      ];
      if (can(user, [...ADMIN_ROLES, "support_staff"])) buttons.push(h("button", { class: "btn btn-primary", onClick: async () => {
        try { const r = await api("/verifications", { method: "POST", body: { credential_id: c.credential_id } }); modal({ title: "Verification result", wide: true, body: renderVerification(r), onClose: load }); }
        catch (err) { toast(errorMessage(err), "error"); }
      } }, "Verify now"));
      if (can(user, ADMIN_ROLES) && c.status === "active") buttons.push(h("button", { class: "btn btn-danger", onClick: () => {
        const dialog = modal({ title: `Revoke ${c.credential_id}`, body: h("div", {}, h("div", { class: "alert alert-warn" }, "Revocation is permanent and takes effect immediately. It is recorded in the audit trail."),
          form({ fields: [{ name: "reason_code", label: "Reason", type: "select", required: true, options: REASONS }, { name: "reason_detail", label: "Details", type: "textarea" }],
            submitLabel: "Revoke credential", onCancel: () => dialog.close(), onSubmit: async (v) => { await api(`/credentials/${c.credential_id}/revoke`, { method: "POST", body: v }); dialog.close(); toast("Credential revoked"); load(); } })) });
      } }, "Revoke"));
      let pretty = c.payload_json;
      try { pretty = JSON.stringify(JSON.parse(c.payload_json), null, 2); } catch (err) { /* show raw */ }
      mount(root, pageHeader(c.rule_title, c.credential_id, buttons),
        card("Summary", definitionList([["Status", badge(c.effective_status)], ["Holder", staff ? h("a", { href: `#/learners/${c.learner_id}` }, `${c.learner_name} (${c.learner_id})`) : c.learner_name],
          ["Programme", staff ? h("a", { href: `#/rules/${c.rule_id}` }, c.rule_title) : c.rule_title], ["Issuer", `${c.issuer_name} (${c.issuer_id}${c.issuer_status === "retired" ? ", retired" : ""})`],
          ["Issued", formatTs(c.issued_at)], ["Expires", c.expires_at ? formatTs(c.expires_at) : "Never"], ["Verification checks", c.verification_count]])),
        c.revocations.length ? card("Revocation", h("table", { class: "table" }, h("thead", {}, h("tr", {}, ["Record", "Reason", "Effective", "Details"].map((t) => h("th", {}, t)))),
          h("tbody", {}, c.revocations.map((r) => h("tr", {}, h("td", {}, r.revocation_id), h("td", {}, badge(r.reason_code)), h("td", {}, formatTs(r.effective_at)), h("td", {}, r.reason_detail || "—")))))) : null,
        card("Signed record", h("div", {}, definitionList([["Algorithm", "Ed25519"], ["Signing key", c.key_id], ["Payload SHA-256", h("span", { class: "mono" }, c.payload_hash)], ["Signature (base64)", h("span", { class: "mono" }, c.signature_b64)]]), h("h3", {}, "Signed payload"), h("pre", {}, pretty))),
        card("Qualifying course completions", h("table", { class: "table" }, h("thead", {}, h("tr", {}, ["Record", "Course", "Score", "Completed"].map((t) => h("th", {}, t)))),
          h("tbody", {}, c.completions.map((x) => h("tr", {}, h("td", {}, staff ? h("a", { href: `#/completions/${x.completion_id}` }, x.completion_id) : x.completion_id), h("td", {}, x.course_title), h("td", {}, x.final_score), h("td", {}, formatTs(x.finalized_at))))))),
        staff ? card("Audit trail", c.audit_trail.length ? h("ul", {}, c.audit_trail.map((e) => h("li", {}, `${formatTs(e.occurred_at)} — ${e.action} (${e.event_id}, ${e.actor_type})`))) : h("p", { class: "muted" }, "No audit events.")) : null,
        staff ? card("Verification history", dataTable({ pageSize: 10, load: (p) => api(`/verifications${qs({ ...p, credential_id: c.credential_id })}`), columns: verificationColumns(user) })) : null);
    } catch (err) { mount(root, errorBox(err, load)); }
  };
  load();
  return root;
}

function verificationColumns(user, onOpen) {
  return [
    { label: "ID", render: (r) => (onOpen ? h("a", { href: "#/verifications", onClick: (e) => { e.preventDefault(); onOpen(r); } }, r.verification_id) : r.verification_id) },
    { label: "Checked", render: (r) => formatTs(r.requested_at) },
    { label: "Credential", render: (r) => (r.credential_id ? h("a", { href: `#/credentials/${r.credential_id}` }, r.credential_id) : h("span", { class: "muted" }, r.presented_credential_id)) },
    { label: "Result", render: (r) => badge(r.result_status) }, { label: "Identity", render: (r) => badge(r.identity_status) },
    { label: "Channel", render: (r) => r.channel.replace(/_/g, " ") }, { label: "Requester", render: (r) => r.requester_org || r.requester_type },
  ];
}

export function verificationsPage({ user }) {
  const staff = can(user, STAFF_ROLES);
  let table;
  const open = async (row) => {
    const body = h("div", {}, definitionList([["Presented ID", row.presented_credential_id], ["Checked", formatTs(row.requested_at)], ["Result (recorded)", badge(row.result_status)],
      ["Identity (recorded)", badge(row.identity_status)], ["Integrity OK", row.integrity_ok === null ? "—" : row.integrity_ok ? "Yes" : "No"], ["Channel", row.channel.replace(/_/g, " ")],
      ["Requester", `${row.requester_type}${row.requester_org ? " · " + row.requester_org : ""}`], ["Claimed name", row.claimed_name], ["Claimed email", row.claimed_email], ["Claimed DOB", row.claimed_dob], ["Presented hash", row.presented_hash]]));
    const out = h("div", {});
    const replay = h("button", { class: "btn btn-primary", onClick: async () => {
      try {
        const r = await api(`/verifications/${row.verification_id}/replay`, { method: "POST" });
        mount(out, h("div", { class: r.reproducible ? "alert alert-good" : "alert alert-error" }, r.reproducible ? "Reproducible: replaying the rules at the original time gives the recorded result." : "Not reproducible: " + r.differences.join("; ")),
          h("p", { class: "muted" }, "Replay evidence: " + r.reasons.join("; ")));
      } catch (err) { toast(errorMessage(err), "error"); }
    } }, "Replay this check");
    modal({ title: row.verification_id, wide: true, body: h("div", {}, body, h("div", { class: "form-actions" }, replay), out) });
  };
  const run = can(user, [...ADMIN_ROLES, "support_staff"]) ? h("button", { class: "btn btn-primary", onClick: () => {
    const dialog = modal({ title: "Run a verification", wide: true, body: form({
      fields: [{ name: "credential_id", label: "Credential ID", required: true, placeholder: "CRD-2026-000001" }, { name: "claimed_name", label: "Claimed holder name" },
        { name: "claimed_email", label: "Claimed holder email", type: "email" }, { name: "claimed_dob", label: "Claimed date of birth", type: "date" }, { name: "presented_hash", label: "Presented payload hash" },
        { name: "requester_org", label: "Requesting organisation" }],
      submitLabel: "Verify", onCancel: () => dialog.close(),
      onSubmit: async (v) => { const r = await api("/verifications", { method: "POST", body: v }); dialog.close(); modal({ title: "Verification result", wide: true, body: renderVerification(r), onClose: () => table.refresh() }); } }) });
  } }, "Run verification") : null;
  table = dataTable({
    filters: [{ name: "q", label: "Search ID, credential or organisation" }, { name: "result_status", label: "All results", type: "select", options: ["valid", "revoked", "expired", "not_found", "tampered"] },
      { name: "channel", label: "All channels", type: "select", options: ["public_api", "support_desk", "learner_share"] }],
    load: (p) => api(`/verifications${qs(p)}`), columns: verificationColumns(user, staff ? open : null), actions: run,
  });
  return h("div", {}, pageHeader(staff ? "Verification requests" : "Who checked my credentials", "Every check is recorded and can be replayed at the time it was made."), card(null, table));
}

export function revocationsPage() {
  const table = dataTable({
    filters: [{ name: "q", label: "Search credential or learner" }, { name: "reason_code", label: "All reasons", type: "select", options: REASONS }],
    load: (p) => api(`/revocations${qs(p)}`),
    columns: [{ key: "revocation_id", label: "Revocation" }, { label: "Credential", render: (r) => h("a", { href: `#/credentials/${r.credential_id}` }, r.credential_id) },
      { key: "learner_name", label: "Learner" }, { key: "rule_title", label: "Programme" }, { label: "Reason", render: (r) => badge(r.reason_code) },
      { label: "Effective", render: (r) => formatTs(r.effective_at) }, { label: "By", render: (r) => r.revoked_by || "—" }],
  });
  return h("div", {}, pageHeader("Revocations", "Append-only record of credentials withdrawn from use."), card(null, table));
}
