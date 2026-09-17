export function transactionTitle(t) {
  if (!t) return "";
  if (t.description) return t.description;
  switch (t.type) {
    case "MONEY_REQUEST_OUT":
      return "Request to";
    case "MONEY_REQUEST_IN":
      return "Request from";
    case "MONEY_REQUEST_COLLECT":
      return "Request payment";
    case "CAMPAY_COLLECT":
      return "Campay collect";
    case "CAMPAY_WITHDRAW":
      return "Campay withdraw";
    default:
      return String(t.type || "").replaceAll("_", " ");
  }
}

/** Map txn status to badge tone class (SUCCESS green / FAILED red / PENDING blue). */
export function transactionStatusClass(status) {
  const s = String(status || "").toUpperCase();
  if (s === "SUCCESS") return "SUCCESS";
  if (s === "FAILED" || s === "REVERSED") return "FAILED";
  if (s === "PENDING" || s === "PROCESSING" || s === "CREATED") return "PENDING";
  return s || "PENDING";
}

export const CREDIT_TYPES = new Set([
  "ADD_MONEY",
  "TRANSFER_RECEIVED",
  "MONEY_REQUEST_OUT",
]);
