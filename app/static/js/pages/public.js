import { api, session } from "../api.js";
import { h, mount, form, card, badge, definitionList, formatTs, pageHeader, toast } from "../ui.js";

const RESULT_TEXT = {
  valid: "Valid credential", revoked: "Credential has been revoked", expired: "Credential has expired",
  not_found: "No such credential", tampered: "Credential failed integrity checks",
};
const IDENTITY_TEXT = {
  matched: "Holder identity matched", mismatch: "Holder details do not match this credential",
  insufficient_identifiers: "Name alone is not enough to confirm identity — add the holder's email or date of birth",
  not_requested: "No holder details were supplied",
};

export function renderVerification(result) {
  const c = result.credential;
  return h("div", { class: "verification-result" },
    h("div", { class: `result-banner result-${result.result_status}` }, RESULT_TEXT[result.result_status] || result.result_status),
    h("p", {}, badge(result.identity_status), " ", IDENTITY_TEXT[result.identity_status]),
    c ? definitionList([
      ["Credential", `${c.title} (${c.credential_id})`],
      ["Holder", c.holder_name_masked ? `${c.holder_name} (masked until identity is matched)` : c.holder_name],
      ["Issued by", `${c.issuer_name} (${c.issuer_id}${c.issuer_status === "retired" ? ", retired" : ""})`],
      ["Issued", formatTs(c.issued_at)], ["Expires", c.expires_at ? formatTs(c.expires_at) : "Never"],
      ["Signing key", c.key_id], ["Payload hash", h("span", { class: "mono" }, c.payload_hash)],
    ]) : null,
    h("h3", {}, "Why this result"), h("ul", {}, result.reasons.map((r) => h("li", {}, r))),
    result.notes.length ? h("div", { class: "alert alert-info" }, result.notes.join(" ")) : null,
    h("p", { class: "muted" }, `Reference ${result.verification_id} · checked ${formatTs(result.requested_at)}`));
}

export function loginPage({ navigate }) {
  const root = h("div", { class: "login-wrap" });
  const f = form({
    fields: [{ name: "email", label: "Email", type: "email", required: true, autocomplete: "username" },
      { name: "password", label: "Password", type: "password", required: true, autocomplete: "current-password" }],
    submitLabel: "Sign in",
    onSubmit: async (values) => {
      const result = await api("/auth/login", { method: "POST", body: values, auth: false });
      session.save(result.token, result.user);
      navigate("/dashboard", true);
    },
  });
  mount(root, card("Sign in to Credential Platform", h("div", {}, f,
    h("p", { class: "muted" }, "Verifying someone else's credential? ", h("a", { href: "#/verify" }, "Use the public verifier"), "."))));
  return root;
}

export function verifyPage({ query }) {
  const resultBox = h("div", {});
  const staff = session.user && session.user.role !== "learner" && session.user.role !== "instructor";
  const f = form({
    fields: [
      { name: "credential_id", label: "Credential ID", required: true, placeholder: "CRD-2026-000001" },
      { name: "claimed_name", label: "Holder's full name", hint: "Optional. Name alone never confirms identity." },
      { name: "claimed_email", label: "Holder's email", type: "email", hint: "Optional strong identifier." },
      { name: "claimed_dob", label: "Holder's date of birth", type: "date", hint: "Optional strong identifier." },
      { name: "presented_hash", label: "Payload hash from the document", hint: "Optional 64-character SHA-256 shown on the certificate." },
      { name: "requester_type", label: "You are a(n)", type: "select", options: ["employer", "institution", "other"] },
      { name: "requester_org", label: "Your organisation" },
    ],
    initial: { credential_id: query.id || "" },
    submitLabel: "Verify credential",
    onSubmit: async (values) => {
      const result = await api("/public/verify", { method: "POST", body: values, auth: false });
      mount(resultBox, card("Result", renderVerification(result)));
    },
  });
  f.classList.add("form-grid");
  const root = h("div", { class: session.token ? "" : "public-wrap" }, pageHeader("Verify a credential", "Check that a credential is genuine, current and belongs to the person presenting it."),
    card(null, f), resultBox,
    session.token ? null : h("p", {}, h("a", { href: "#/login" }, "Staff and learners: sign in")),
    staff ? h("p", { class: "muted" }, "Staff can also record verifications from the Verifications page.") : null);
  return root;
}
