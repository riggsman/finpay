import { api } from "./client";

export const supportApi = {
  listTickets: () => api.get("/support/tickets"),
  createTicket: (payload) => api.post("/support/tickets", payload),
  getTicket: (id) => api.get(`/support/tickets/${id}`),
  addMessage: (id, body) => api.post(`/support/tickets/${id}/messages`, { body }),
  closeTicket: (id) => api.post(`/support/tickets/${id}/close`),
  listDisputes: () => api.get("/support/disputes"),
  createDispute: (transactionId, reason, description) =>
    api.post(`/support/disputes?transaction_id=${transactionId}`, { reason, description }),
};
