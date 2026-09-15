import { api } from "./client";

export const walletApi = {
  get: () => api.get("/wallet"),
  addMoney: (amount, fundingMethod = "card", idempotencyKey) =>
    api.post(
      "/wallet/add-money",
      { amount, funding_method: fundingMethod },
      idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}
    ),
  send: (recipient, amount, pin, idempotencyKey) =>
    api.post(
      "/wallet/send",
      { recipient, amount, pin },
      idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}
    ),
  withdraw: (amount, destination, pin, idempotencyKey) =>
    api.post(
      "/wallet/withdraw",
      { amount, destination, pin },
      idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}
    ),
};

export const transactionsApi = {
  list: (limit = 20) => api.get(`/transactions?limit=${limit}`),
};

export const dashboardApi = {
  summary: () => api.get("/dashboard/summary"),
};

export const notificationsApi = {
  list: (limit = 20) => api.get(`/notifications?limit=${limit}`),
  unreadCount: () => api.get("/notifications/unread-count"),
  markAllRead: () => api.patch("/notifications/read-all"),
};
