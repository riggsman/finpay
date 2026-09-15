const BASE = "/api/v1";

let accessToken = null;

export function setAccessToken(token) {
  accessToken = token;
}

export function getAccessToken() {
  return accessToken;
}

async function request(method, path, body, extraHeaders = {}) {
  const headers = { "Content-Type": "application/json", ...extraHeaders };
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  let data = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!res.ok) {
    const message =
      (data && data.error && data.error.message) ||
      (data && data.detail) ||
      `Request failed (${res.status})`;
    const err = new Error(message);
    err.status = res.status;
    err.code = data && data.error && data.error.code;
    err.payload = data;
    throw err;
  }
  return data;
}

export const api = {
  get: (path, headers) => request("GET", path, null, headers),
  post: (path, body, headers) => request("POST", path, body, headers),
  patch: (path, body, headers) => request("PATCH", path, body, headers),
};
