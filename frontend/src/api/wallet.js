import { api } from "./client";

export const walletApi = {
  get: () => api.get("/wallet"),
  addMoney: (amount, fundingMethod = "card", idempotencyKey, phone, cardDetails, bankDetails) =>
    api.post(
      "/wallet/add-money",
      {
        amount,
        funding_method: fundingMethod,
        ...(phone ? { phone } : {}),
        ...(cardDetails ? { card_details: cardDetails } : {}),
        ...(bankDetails ? { bank_details: bankDetails } : {}),
      },
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
  get: (id) => api.get(`/transactions/${id}`),
};

export const dashboardApi = {
  summary: () => api.get("/dashboard/summary"),
};

export const recoveryApi = {
  reconcile: () => api.post("/transactions/reconcile"),
};

export const notificationsApi = {
  list: (limit = 50) => api.get(`/notifications?limit=${limit}`),
  unreadCount: () => api.get("/notifications/unread-count"),
  markRead: (id) => api.patch(`/notifications/${id}/read`),
  markAllRead: () => api.patch("/notifications/read-all"),
};
