import { api } from "./client";

export const devicesApi = {
  config: () => api.get("/me/devices/config"),
  list: () => api.get("/me/devices"),
  register: (device_id, device_type, push_token) =>
    api.post("/me/devices", { device_id, device_type, push_token }),
  unregister: (id) => api.del(`/me/devices/${id}`),
};
