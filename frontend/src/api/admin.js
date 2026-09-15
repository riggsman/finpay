import { api } from "./client";

export const adminApi = {
  overview: () => api.get("/admin/overview"),
  listFees: () => api.get("/admin/fees"),
  updateFee: (operation, body) => api.put(`/admin/fees/${operation}`, body),
  listServices: () => api.get("/admin/services"),
  updateService: (key, enabled) => api.put(`/admin/services/${key}`, { enabled }),
  listProviders: () => api.get("/admin/providers"),
  createProvider: (category, provider_id, name) =>
    api.post("/admin/providers", { category, provider_id, name }),
  updateProvider: (id, body) => api.put(`/admin/providers/${id}`, body),
  listSettings: () => api.get("/admin/settings"),
  updateSettings: (values) => api.put("/admin/settings", { values }),
  emailTest: (subject, body) => api.post("/admin/email/test", { subject, body }),
};
