import { api } from "./client";

export const authApi = {
  registerInitiate: (phone) =>
    api.post("/auth/register/initiate", { signup_method: "phone", phone }),
  register: (payload) => api.post("/auth/register", payload),
  verifyOtp: (phone, otp) => api.post("/auth/verify-otp", { phone, otp }),
  login: (identifier, password) => api.post("/auth/login", { identifier, password }),
  me: () => api.get("/me"),
  passwordResetRequest: (identifier) =>
    api.post("/auth/password-reset/request", { identifier }),
  passwordResetVerify: (identifier, code) =>
    api.post("/auth/password-reset/verify", { identifier, code }),
  passwordResetComplete: (reset_token, new_password) =>
    api.post("/auth/password-reset/complete", { reset_token, new_password }),
  logout: () => api.post("/auth/logout"),
};
