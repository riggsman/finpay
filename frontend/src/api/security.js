import { api } from "./client";

export const securityApi = {
  updateProfile: (payload) => api.patch("/me/profile", payload),
  changePassword: (current_password, new_password) =>
    api.post("/me/security/change-password", { current_password, new_password }),
  setPin: (current_pin, new_pin) =>
    api.put("/me/security/pin", { current_pin, new_pin }),
  getLimits: () => api.get("/me/security/limits"),
  updateLimits: (per_txn_limit, daily_limit) =>
    api.patch("/me/security/limits", { per_txn_limit, daily_limit }),
  listSessions: () => api.get("/me/security/sessions"),
  revokeAllSessions: () => api.post("/me/security/sessions/revoke-all"),
};
