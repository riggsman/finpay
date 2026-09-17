import { api } from "./client";

export const beneficiariesApi = {
  list: () => api.get("/beneficiaries"),
  add: (identifier) => api.post("/beneficiaries", { identifier }),
  remove: (id) => api.del(`/beneficiaries/${id}`),
};

export const moneyRequestsApi = {
  list: (direction = "all") => api.get(`/money-requests?direction=${direction}`),
  create: (payer, amount, note) => api.post("/money-requests", { payer, amount, note }),
  pay: (id, pin, phone) =>
    api.post(`/money-requests/${id}/pay`, { pin, ...(phone ? { phone } : {}) }),
  decline: (id) => api.post(`/money-requests/${id}/decline`),
  cancel: (id) => api.post(`/money-requests/${id}/cancel`),
};
