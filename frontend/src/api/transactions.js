import { api } from "./client";

function toQuery(params) {
  const q = new URLSearchParams();
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.append(k, v);
  });
  const s = q.toString();
  return s ? `?${s}` : "";
}

export const transactionsApi = {
  list: (params) => api.get(`/transactions${toQuery(params)}`),
  get: (id) => api.get(`/transactions/${id}`),
  events: (id) => api.get(`/transactions/${id}/events`),
  receipt: (id) => api.get(`/transactions/${id}/receipt`),
};
