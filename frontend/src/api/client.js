const BASE = "/api/v1";

let accessToken = null;
let refreshToken = null;
let refreshPromise = null;

/** @type {null | ((accessToken: string) => void)} */
let onAccessTokenUpdated = null;
/** @type {null | ((reason?: string) => void)} */
let onSessionExpired = null;

const NO_REFRESH_PATHS = [
  "/auth/login",
  "/auth/refresh",
  "/auth/register",
  "/auth/register/initiate",
  "/auth/verify-otp",
  "/auth/password-reset/request",
  "/auth/password-reset/verify",
  "/auth/password-reset/complete",
  "/admin/login",
];

export function setAccessToken(token) {
  accessToken = token || null;
}

export function getAccessToken() {
  return accessToken;
}

export function setRefreshToken(token) {
  refreshToken = token || null;
}

export function getRefreshToken() {
  return refreshToken;
}

export function setSessionHandlers({ onAccessTokenUpdated: onUpdate, onSessionExpired: onExpired } = {}) {
  onAccessTokenUpdated = onUpdate || null;
  onSessionExpired = onExpired || null;
}

function shouldAttemptRefresh(path) {
  return !NO_REFRESH_PATHS.some((p) => path === p || path.startsWith(`${p}?`));
}

function parseBody(text) {
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function makeError(res, data) {
  const message =
    (data && data.error && data.error.message) ||
    (data && data.detail) ||
    `Request failed (${res.status})`;
  const err = new Error(message);
  err.status = res.status;
  err.code = data && data.error && data.error.code;
  err.payload = data;
  return err;
}

async function rawFetch(method, path, body, headers = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...headers },
    body: body !== undefined && body !== null ? JSON.stringify(body) : undefined,
  });
  const data = parseBody(await res.text());
  if (!res.ok) throw makeError(res, data);
  return data;
}

/**
 * Exchange refresh token for a new access token.
 * Uses a single in-flight promise so concurrent 401s share one refresh.
 */
export async function refreshAccessToken() {
  if (!refreshToken) {
    const err = new Error("Session expired. Please sign in again.");
    err.status = 401;
    err.code = "NO_REFRESH_TOKEN";
    throw err;
  }

  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    try {
      const data = await rawFetch("POST", "/auth/refresh", {
        refresh_token: refreshToken,
      });
      const next = data?.access_token;
      if (!next) {
        const err = new Error("Invalid refresh response.");
        err.status = 401;
        err.code = "INVALID_REFRESH_RESPONSE";
        throw err;
      }
      accessToken = next;
      onAccessTokenUpdated?.(next);
      return next;
    } catch (err) {
      // Refresh failed (expired/revoked) — end the session.
      accessToken = null;
      refreshToken = null;
      onSessionExpired?.(err?.code || "REFRESH_FAILED");
      throw err;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

function clearLocalTokens() {
  accessToken = null;
  refreshToken = null;
}

export function clearSessionTokens() {
  clearLocalTokens();
  refreshPromise = null;
}

async function request(method, path, body, extraHeaders = {}, { retry = true } = {}) {
  const headers = { ...extraHeaders };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;

  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers: { "Content-Type": "application/json", ...headers },
      body: body !== undefined && body !== null ? JSON.stringify(body) : undefined,
    });
  } catch (networkErr) {
    const err = new Error(networkErr.message || "Network error");
    err.status = 0;
    err.code = "NETWORK_ERROR";
    throw err;
  }

  const data = parseBody(await res.text());

  if (res.status === 401 && retry && shouldAttemptRefresh(path) && refreshToken) {
    try {
      await refreshAccessToken();
    } catch {
      // Session expired handler already ran.
      throw makeError(res, data);
    }
    return request(method, path, body, extraHeaders, { retry: false });
  }

  if (!res.ok) throw makeError(res, data);
  return data;
}

export const api = {
  get: (path, headers) => request("GET", path, null, headers),
  post: (path, body, headers) => request("POST", path, body, headers),
  put: (path, body, headers) => request("PUT", path, body, headers),
  patch: (path, body, headers) => request("PATCH", path, body, headers),
  del: (path, headers) => request("DELETE", path, null, headers),
};
