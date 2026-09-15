import { api } from "./client";

export const adminApi = {
  overview: () => api.get("/admin/overview"),
  listFees: () => api.get("/admin/fees"),
  updateFee: (operation, body) => api.put(`/admin/fees/${operation}`, body),
  listServices: () => api.get("/admin/services"),
  updateService: (key, enabled) => api.put(`/admin/services/${key}`, { enabled }),
};
