import { api } from "./client";

export const authApi = {
  registerInitiate: (phone) =>
    api.post("/auth/register/initiate", { signup_method: "phone", phone }),
  register: (payload) => api.post("/auth/register", payload),
  verifyOtp: (phone, otp) => api.post("/auth/verify-otp", { phone, otp }),
  login: (identifier, password) => api.post("/auth/login", { identifier, password }),
  me: () => api.get("/me"),
};
