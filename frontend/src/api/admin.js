import { api } from "./client";

function qs(params = {}) {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export const adminApi = {
  login: (identifier, password) => api.post("/admin/login", { identifier, password }),
  overview: () => api.get("/admin/overview"),
  listFees: () => api.get("/admin/fees"),
  updateFee: (operation, body) => api.put(`/admin/fees/${operation}`, body),
  listServices: () => api.get("/admin/services"),
  updateService: (key, payload) =>
    api.put(`/admin/services/${key}`, typeof payload === "boolean" ? { enabled: payload } : payload),
  listProviders: () => api.get("/admin/providers"),
  listProviderCategories: () => api.get("/admin/providers/categories"),
  createProvider: (body) => api.post("/admin/providers", body),
  updateProvider: (id, body) => api.put(`/admin/providers/${id}`, body),
  listSettings: () => api.get("/admin/settings"),
  updateSettings: (values) => api.put("/admin/settings", { values }),
  emailTest: (subject, body) => api.post("/admin/email/test", { subject, body }),

  listKyc: (params) => api.get(`/admin/kyc${qs(params)}`),
  getKyc: (id) => api.get(`/admin/kyc/${id}`),
  approveKyc: (id) => api.post(`/admin/kyc/${id}/approve`, {}),
  rejectKyc: (id, reason) => api.post(`/admin/kyc/${id}/reject`, { reason }),

  listUsers: (params) => api.get(`/admin/users${qs(params)}`),
  getUser: (id) => api.get(`/admin/users/${id}`),

  listTransactions: (params) => api.get(`/admin/transactions${qs(params)}`),
  verifyTransactionProvider: (id) => api.post(`/admin/transactions/${id}/verify-provider`, {}),
  reconcileTransaction: (id) => api.post(`/admin/transactions/${id}/reconcile`, {}),
  listLimitRequests: (params) => api.get(`/admin/limit-requests${qs(params)}`),
  approveLimitRequest: (id, body = {}) => api.post(`/admin/limit-requests/${id}/approve`, body),
  rejectLimitRequest: (id, reason) => api.post(`/admin/limit-requests/${id}/reject`, { reason }),

  listTickets: (params) => api.get(`/admin/tickets${qs(params)}`),
  getTicket: (id) => api.get(`/admin/tickets/${id}`),
  replyTicket: (id, body) => api.post(`/admin/tickets/${id}/messages`, { body }),
  updateTicketStatus: (id, status) => api.post(`/admin/tickets/${id}/status`, { status }),

  campayStatus: () => api.get("/admin/campay/status"),
  campayBalance: () => api.get("/admin/campay/balance"),
  campayHolderInfo: (phone) => api.get(`/admin/campay/holder-info${qs({ phone })}`),
  campayTestToken: () => api.post("/admin/campay/test/token", {}),
  campayTestCollect: (phone, amount) => api.post("/admin/campay/test/collect", { phone, amount }),
  campayTestWithdraw: (phone, amount) => api.post("/admin/campay/test/withdraw", { phone, amount }),
  campayTestTransaction: (reference) => api.get(`/admin/campay/test/transaction/${encodeURIComponent(reference)}`),
};
