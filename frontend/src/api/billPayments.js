import { api } from "./client";

export const billPaymentsApi = {
  providers: (category) =>
    api.get(`/bill-payments/providers?category=${encodeURIComponent(category)}`),
  validate: (category, providerId, phone) =>
    api.post("/bill-payments/validate", {
      category,
      provider_id: providerId,
      phone,
    }),
  pay: (body, idempotencyKey) =>
    api.post(
      "/bill-payments/pay",
      body,
      idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}
    ),
  // Legacy aliases kept for older callers/tests.
  validateMeter: (providerId, meterNumber) =>
    api.post("/bill-payments/electricity/validate", {
      provider_id: providerId,
      meter_number: meterNumber,
    }),
  confirmElectricity: (validationToken, amount, pin, idempotencyKey) =>
    api.post(
      "/bill-payments/electricity/confirm",
      { validation_token: validationToken, amount, pin },
      idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}
    ),
  topupProviders: (category) =>
    api.get(`/bill-payments/topup/providers?category=${encodeURIComponent(category)}`),
  confirmTopup: (category, providerId, target, amount, pin, idempotencyKey) =>
    api.post(
      "/bill-payments/topup/confirm",
      { category, provider_id: providerId, target, amount, pin },
      idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}
    ),
};

export const transactionApi = {
  get: (id) => api.get(`/transactions/${id}`),
  receipt: (id) => api.get(`/transactions/${id}/receipt`),
  reconcile: () => api.post("/transactions/reconcile"),
};
