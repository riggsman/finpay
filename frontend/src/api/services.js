import { api } from "./client";

export const servicesApi = {
  list: () => api.get("/services"),
};
