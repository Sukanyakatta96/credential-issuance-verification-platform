import { api, qs } from "../api.js";
import { h, mount, form, card, dataTable, loading, errorBox, badge, definitionList, modal, confirmDialog, formatTs, formatDate, pageHeader, toast, errorMessage } from "../ui.js";
import { can, ADMIN_ROLES } from "../roles.js";

const COUNTRIES = ["IN", "US", "GB", "DE", "CA", "AU", "SG", "AE", "BR", "ZA", "FR", "NG"];

function refreshOnSuccess(table, dialog, message) { dialog.close(); toast(message); table.refresh(); }

export function learnersPage({ user, query }) {
  let table;
  const actions = can(user, ADMIN_ROLES) ? h("button", { class: "btn btn-primary", onClick: () => {
    const dialog = modal({ title: "Register learner", body: form({
      fields: [{ name: "full_name", label: "Full name", required: true }, { name: "email", label: "Email", type: "email", required: true },
        { name: "date_of_birth", label: "Date of birth", type: "date", required: true },
        { name: "country_code", label: "Country", type: "select", required: true, options: COUNTRIES }],
      submitLabel: "Register", onCancel: () => dialog.close(),
      onSubmit: async (v) => { const created = await api("/learners", { method: "POST", body: v }); refreshOnSuccess(table, dialog, `Registered ${created.learner_id}`);
        if (created.same_name_count) toast(`${created.same_name_count} other learner(s) share this name — identity checks need email or date of birth.`, "success"); },
    }) });
  } }, "Register learner") : null;
  table = dataTable({
    initial: { q: query.q || "" },
    filters: [{ name: "q", label: "Search name, email or ID" }, { name: "status", label: "All statuses", type: "select", options: ["active", "suspended", "closed"] }],
    load: (p) => api(`/learners${qs(p)}`),
    columns: [
      { label: "ID", render: (r) => h("a", { href: `#/learners/${r.learner_id}` }, r.learner_id) },
      { label: "Name", render: (r) => h("span", {}, r.full_name, r.same_name_count ? [" ", h("span", { class: "badge badge-warn", title: "Other learners share this exact name" }, `+${r.same_name_count} same name`)] : null) },
      { key: "email", label: "Email" }, { label: "Born", render: (r) => r.date_of_birth }, { key: "country_code", label: "Country" },
      { label: "Credentials", render: (r) => r.credential_count }, { label: "Status", render: (r) => badge(r.status) }],
    actions,
  });
  return h("div", {}, pageHeader("Learners", "Search by name, email or learner ID. Names are not unique — email and date of birth anchor identity."), card(null, table));
}

export function learnerDetailPage({ user, params }) {
  const root = h("div", {}, loading());
  const load = async () => {
    try {
      const l = await api(`/learners/${params.id}`);
      const staff = can(user, ADMIN_ROLES);
      const edit = staff ? h("button", { class: "btn", onClick: () => {
        const dialog = modal({ title: `Edit ${l.learner_id}`, body: form({
          fields: [{ name: "full_name", label: "Full name" }, { name: "email", label: "Email", type: "email" },
            { name: "country_code", label: "Country", type: "select", options: COUNTRIES }, { name: "status", label: "Status", type: "select", options: ["active", "suspended", "closed"] }],
          initial: l, submitLabel: "Save changes", onCancel: () => dialog.close(),
          onSubmit: async (v) => { await api(`/learners/${l.learner_id}`, { method: "PATCH", body: v }); dialog.close(); toast("Learner updated"); load(); } }) });
      } }, "Edit") : null;
      const enroll = staff ? h("button", { class: "btn", onClick: () => {
        const dialog = modal({ title: `Enrol ${l.full_name}`, body: form({
          fields: [{ name: "course_id", label: "Course ID", required: true, placeholder: "CRS-000001" }], submitLabel: "Enrol", onCancel: () => dialog.close(),
          onSubmit: async (v) => { await api("/completions", { method: "POST", body: { learner_id: l.learner_id, course_id: v.course_id } }); dialog.close(); toast("Learner enrolled"); load(); } }) });
      } }, "Enrol in course") : null;
      mount(root,
        pageHeader(l.full_name, l.learner_id, [edit, enroll]),
        l.same_name_count ? h("div", { class: "alert alert-warn" }, `${l.same_name_count} other learner(s) share this exact name` +
          (l.same_name_and_birthdate_count ? `, ${l.same_name_and_birthdate_count} also share the date of birth` : "") + ". Always confirm with email before acting on a name match.") : null,
        card("Profile", definitionList([["Email", l.email], ["Date of birth", l.date_of_birth], ["Country", l.country_code], ["Registered", formatTs(l.registered_at)],
          ["Status", badge(l.status)], ["Enrolments", l.completion_count], ["Credentials", l.credential_count]])),
        card("Course enrolments", dataTable({ load: (p) => api(`/completions${qs({ ...p, learner_id: l.learner_id })}`), pageSize: 10,
          columns: [{ label: "Record", render: (r) => h("a", { href: `#/completions/${r.completion_id}` }, r.course_id) }, { key: "course_title", label: "Course" },
            { label: "Status", render: (r) => badge(r.status) }, { label: "Progress", render: (r) => `${r.progress_pct}%` }, { label: "Score", render: (r) => r.final_score ?? "—" }, { label: "Finalised", render: (r) => formatDate(r.finalized_at) }] })),
        card("Credentials", dataTable({ load: (p) => api(`/credentials${qs({ ...p, learner_id: l.learner_id })}`), pageSize: 10,
          columns: [{ label: "Credential", render: (r) => h("a", { href: `#/credentials/${r.credential_id}` }, r.credential_id) }, { key: "rule_title", label: "Programme" },
            { key: "issuer_name", label: "Issuer" }, { label: "Issued", render: (r) => formatDate(r.issued_at) }, { label: "Status", render: (r) => badge(r.effective_status) }] })));
    } catch (err) { mount(root, errorBox(err, load)); }
  };
  load();
  return root;
}

export function coursesPage({ user, query }) {
  let table;
  const optionsPromise = api("/meta/course-options");
  const build = (options) => {
    const actions = can(user, ADMIN_ROLES) ? h("button", { class: "btn btn-primary", onClick: () => {
      const dialog = modal({ title: "Create course", body: form({
        fields: [{ name: "title", label: "Title", required: true }, { name: "category", label: "Category", required: true, hint: "Existing: " + options.categories.join(", ") },
          { name: "level", label: "Level", type: "select", required: true, options: ["introductory", "intermediate", "advanced"] },
          { name: "credit_hours", label: "Credit hours", type: "number", required: true, min: 1, max: 200 },
          { name: "pass_mark", label: "Pass mark (%)", type: "number", required: true, min: 40, max: 100 },
          { name: "max_attempts", label: "Maximum assessment attempts", type: "number", required: true, min: 1, max: 10 },
          { name: "instructor_id", label: "Instructor", type: "select", required: true, options: options.instructors.map((i) => ({ value: i.instructor_id, label: `${i.full_name} (${i.instructor_id})` })) }],
        submitLabel: "Create course", onCancel: () => dialog.close(),
        onSubmit: async (v) => { const c = await api("/courses", { method: "POST", body: v }); refreshOnSuccess(table, dialog, `Created ${c.course_id}`); } }) });
    } }, "Create course") : null;
    table = dataTable({
      initial: { q: query.q || "" },
      filters: [{ name: "q", label: "Search title or ID" }, { name: "category", label: "All categories", type: "select", options: options.categories },
        { name: "level", label: "All levels", type: "select", options: ["introductory", "intermediate", "advanced"] }, { name: "status", label: "All statuses", type: "select", options: ["active", "archived"] },
        ...(user.role === "instructor" ? [{ name: "mine", label: "All instructors", type: "select", options: [{ value: "1", label: "My courses only" }] }] : [])],
      load: (p) => api(`/courses${qs(p)}`),
      columns: [{ label: "ID", render: (r) => h("a", { href: `#/courses/${r.course_id}` }, r.course_id) }, { key: "title", label: "Title" }, { key: "category", label: "Category" },
        { label: "Level", render: (r) => badge(r.level) }, { label: "Pass mark", render: (r) => `${r.pass_mark}%` }, { key: "instructor_name", label: "Instructor" },
        { label: "Completed / enrolled", render: (r) => `${r.completed_count} / ${r.enrollment_count}` }, { label: "Status", render: (r) => badge(r.status) }],
      actions,
    });
    return card(null, table);
  };
  const holder = h("div", {}, loading());
  optionsPromise.then((o) => mount(holder, build(o))).catch((e) => mount(holder, errorBox(e)));
  return h("div", {}, pageHeader("Courses", "Each course sets its own pass mark and attempt limit."), holder);
}

export function courseDetailPage({ user, params }) {
  const root = h("div", {}, loading());
  const load = async () => {
    try {
      const c = await api(`/courses/${params.id}`);
      const edit = can(user, ADMIN_ROLES) ? h("button", { class: "btn", onClick: async () => {
        const options = await api("/meta/course-options");
        const dialog = modal({ title: `Edit ${c.course_id}`, body: form({
          fields: [{ name: "title", label: "Title" }, { name: "category", label: "Category" }, { name: "status", label: "Status", type: "select", options: ["active", "archived"] },
            { name: "instructor_id", label: "Instructor", type: "select", options: options.instructors.map((i) => ({ value: i.instructor_id, label: `${i.full_name} (${i.instructor_id})` })) }],
          initial: c, submitLabel: "Save changes", onCancel: () => dialog.close(),
          onSubmit: async (v) => { await api(`/courses/${c.course_id}`, { method: "PATCH", body: v }); dialog.close(); toast("Course updated"); load(); } }) });
      } }, "Edit") : null;
      const staff = user.role !== "learner";
      mount(root, pageHeader(c.title, c.course_id, edit),
        card("Details", definitionList([["Category", c.category], ["Level", badge(c.level)], ["Credit hours", c.credit_hours], ["Pass mark", `${c.pass_mark}%`],
          ["Attempt limit", c.max_attempts], ["Instructor", `${c.instructor_name} (${c.instructor_id})`], ["Status", badge(c.status)],
          ["Enrolment outcomes", Object.entries(c.status_breakdown).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v}`).join(" · ") || "No enrolments"]])),
        staff && user.role !== "instructor" ? card("Used by credential rules", c.rules.length ? h("ul", {}, c.rules.map((r) => h("li", {}, h("a", { href: `#/rules/${r.rule_id}` }, r.title), " ", r.is_mandatory ? badge("mandatory") : null, " ", badge(r.status)))) : h("p", { class: "muted" }, "Not part of any rule.")) : null,
        staff ? card("Enrolments", dataTable({ load: (p) => api(`/completions${qs({ ...p, course_id: c.course_id })}`), pageSize: 10, filters: [{ name: "status", label: "All statuses", type: "select", options: ["enrolled", "in_progress", "completed", "failed", "withdrawn"] }],
          columns: [{ label: "Record", render: (r) => h("a", { href: `#/completions/${r.completion_id}` }, r.completion_id) }, { key: "learner_name", label: "Learner" },
            { label: "Status", render: (r) => badge(r.status) }, { label: "Progress", render: (r) => `${r.progress_pct}%` }, { label: "Score", render: (r) => r.final_score ?? "—" }] })) : null);
    } catch (err) { mount(root, errorBox(err, load)); }
  };
  load();
  return root;
}

export function completionsPage({ user }) {
  let table;
  const actions = can(user, ADMIN_ROLES) ? h("button", { class: "btn btn-primary", onClick: () => {
    const dialog = modal({ title: "Enroll learner in course", body: form({
      fields: [{ name: "learner_id", label: "Learner ID", required: true, placeholder: "LRN-000001" }, { name: "course_id", label: "Course ID", required: true, placeholder: "CRS-000001" }],
      submitLabel: "Enrol", onCancel: () => dialog.close(),
      onSubmit: async (v) => { const c = await api("/completions", { method: "POST", body: v }); refreshOnSuccess(table, dialog, `Created ${c.completion_id}`); } }) });
  } }, "Enroll learner") : null;
  table = dataTable({
    filters: [{ name: "q", label: user.role === "learner" ? "Search record ID" : "Search learner name or record ID" },
      { name: "status", label: "All statuses", type: "select", options: ["enrolled", "in_progress", "completed", "failed", "withdrawn"] }],
    load: (p) => api(`/completions${qs(p)}`),
    columns: [{ label: "Record", render: (r) => h("a", { href: `#/completions/${r.completion_id}` }, r.completion_id) },
      ...(user.role === "learner" ? [] : [{ key: "learner_name", label: "Learner" }]), { key: "course_title", label: "Course" },
      { label: "Status", render: (r) => badge(r.status) }, { label: "Progress", render: (r) => `${r.progress_pct}%` }, { label: "Attempts", render: (r) => r.attempts_used },
      { label: "Score", render: (r) => r.final_score ?? "—" }, { label: "Finalised", render: (r) => formatDate(r.finalized_at) }],
    actions,
  });
  const subtitle = user.role === "instructor" ? "Completions for the courses you teach." : user.role === "learner" ? "Your course enrolments." : "All course enrolments and assessment outcomes.";
  return h("div", {}, pageHeader("Course completions", subtitle), card(null, table));
}

export function completionDetailPage({ user, params }) {
  const root = h("div", {}, loading());
  const load = async () => {
    try {
      const c = await api(`/completions/${params.id}`);
      const open = !["completed", "failed", "withdrawn"].includes(c.status);
      const manage = open && can(user, [...ADMIN_ROLES, "instructor"]);
      const forms = [];
      if (manage) {
        forms.push(card("Record progress", form({ fields: [{ name: "progress_pct", label: "Progress (%)", type: "number", required: true, min: c.progress_pct, max: 100, hint: "Progress can only increase." }],
          submitLabel: "Update progress", onSubmit: async (v) => { await api(`/completions/${c.completion_id}/progress`, { method: "POST", body: v }); toast("Progress updated"); load(); } })));
        forms.push(card("Record assessment attempt", form({ fields: [{ name: "score", label: `Score (0–100). Pass mark ${c.pass_mark}`, type: "number", required: true, min: 0, max: 100, step: "0.1",
          hint: c.progress_pct < 100 ? "Progress must be 100% before an assessment can be recorded." : `Attempt ${c.attempts_used + 1} of ${c.max_attempts}.` }],
          submitLabel: "Record attempt", onSubmit: async (v) => { const r = await api(`/completions/${c.completion_id}/assessments`, { method: "POST", body: v }); toast(`Attempt recorded — status ${r.status.replace(/_/g, " ")}`); load(); } })));
      }
      const canWithdraw = open && (can(user, ADMIN_ROLES) || user.role === "learner");
      const withdraw = canWithdraw ? h("button", { class: "btn btn-danger", onClick: async () => {
        if (!(await confirmDialog({ title: "Withdraw from course", message: "Withdrawing is final and cannot be undone.", confirmLabel: "Withdraw", danger: true }))) return;
        try { await api(`/completions/${c.completion_id}/withdraw`, { method: "POST" }); toast("Enrolment withdrawn"); load(); } catch (err) { toast(errorMessage(err), "error"); }
      } }, "Withdraw") : null;
      mount(root, pageHeader(c.completion_id, `${c.learner_name} · ${c.course_title}`, withdraw),
        card("Status", definitionList([["Status", badge(c.status)], ["Progress", `${c.progress_pct}%`], ["Attempts used", `${c.attempts_used} of ${c.max_attempts}`],
          ["Final score", c.final_score ?? "—"], ["Pass mark", `${c.pass_mark}%`], ["Enrolled", formatTs(c.enrolled_at)], ["Finalised", formatTs(c.finalized_at)],
          ["Learner", can(user, ["academic_admin", "support_staff", "platform_admin"]) ? h("a", { href: `#/learners/${c.learner_id}` }, c.learner_id) : c.learner_id],
          ["Course", h("a", { href: `#/courses/${c.course_id}` }, c.course_id)]])),
        card("Assessment attempts", c.attempts.length ? h("table", { class: "table" }, h("thead", {}, h("tr", {}, ["Attempt", "ID", "Score", "Passed", "When"].map((t) => h("th", {}, t)))),
          h("tbody", {}, c.attempts.map((a) => h("tr", {}, h("td", {}, a.attempt_no), h("td", {}, a.attempt_id), h("td", {}, a.score), h("td", {}, badge(a.passed ? "completed" : "failed")), h("td", {}, formatTs(a.attempted_at)))))) : h("p", { class: "muted" }, "No attempts recorded.")),
        forms);
    } catch (err) { mount(root, errorBox(err, load)); }
  };
  load();
  return root;
}
