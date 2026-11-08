const TOKEN_KEY = "cp_token";
const USER_KEY = "cp_user";

export class ApiError extends Error {
  constructor(status, code, message, details) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export const session = {
  get token() { return sessionStorage.getItem(TOKEN_KEY); },
  get user() { const raw = sessionStorage.getItem(USER_KEY); return raw ? JSON.parse(raw) : null; },
  save(token, user) { sessionStorage.setItem(TOKEN_KEY, token); sessionStorage.setItem(USER_KEY, JSON.stringify(user)); },
  clear() { sessionStorage.removeItem(TOKEN_KEY); sessionStorage.removeItem(USER_KEY); },
};

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

export function qs(params) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params || {})) {
    if (value !== undefined && value !== null && value !== "") search.set(key, value);
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && session.token) headers.Authorization = `Bearer ${session.token}`;
  let response;
  try {
    response = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (err) {
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the server. Check your connection and try again.");
  }
  return response;
}

export async function api(path, options = {}) {
  const response = await request(path, options);
  let data = null;
  try { data = await response.json(); } catch (err) { data = null; }
  if (!response.ok) {
    const error = (data && data.error) || {};
    if (response.status === 401 && options.auth !== false && error.code !== "INVALID_CREDENTIALS") onUnauthorized(error.message);
    throw new ApiError(response.status, error.code || "ERROR", error.message || `Request failed (${response.status})`, error.details);
  }
  return data;
}

export async function downloadCsv(path, filename) {
  const response = await request(path);
  if (!response.ok) throw new ApiError(response.status, "EXPORT_FAILED", "Export failed");
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
