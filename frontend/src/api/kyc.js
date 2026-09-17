import { api } from "./client";

export const kycApi = {
  get: () => api.get("/me/kyc"),
  update: (payload) => api.put("/me/kyc", payload),
  submit: () => api.post("/me/kyc/submit"),
  capture: (kind, image_base64) =>
    api.post("/me/kyc/capture", { kind, image_base64 }),
};
