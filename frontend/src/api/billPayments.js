import { api } from "./client";

export const billPaymentsApi = {
  providers: (category) =>
    api.get(`/bill-payments/providers?category=${encodeURIComponent(category)}`),
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
};

export const transactionApi = {
  get: (id) => api.get(`/transactions/${id}`),
  receipt: (id) => api.get(`/transactions/${id}/receipt`),
  reconcile: () => api.post("/transactions/reconcile"),
};
