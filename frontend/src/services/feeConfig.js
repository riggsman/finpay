// Client-side cache of the fee & feature configuration delivered on login
// (SRS 71.4). Fees shown to the user are computed from this cache; the backend
// remains authoritative when the request is settled.
import { api } from "../api/client";

const KEY = "finpay.config";

export function setConfig(cfg) {
  if (cfg) localStorage.setItem(KEY, JSON.stringify(cfg));
}

export function clearConfig() {
  localStorage.removeItem(KEY);
}

export function getConfig() {
  try {
    return JSON.parse(localStorage.getItem(KEY)) || null;
  } catch {
    return null;
  }
}

export async function refreshConfig() {
  try {
    const cfg = await api.get("/config");
    setConfig(cfg);
    return cfg;
  } catch {
    return getConfig();
  }
}

// Compute the fee (minor units) for an operation and amount from the cache.
export function computeFee(operation, amountMinor) {
  const cfg = getConfig();
  if (!cfg || !cfg.fees) return 0;
  const rule = cfg.fees[operation];
  if (!rule || !rule.active) return 0;
  const c = rule.config || {};
  if (rule.fee_type === "FLAT") return Math.max(0, Number(c.fee) || 0);
  if (rule.fee_type === "PERCENTAGE") {
    let fee = Math.round((amountMinor * (Number(c.percent) || 0)) / 100);
    if (c.min_fee != null) fee = Math.max(fee, Number(c.min_fee));
    if (c.max_fee != null) fee = Math.min(fee, Number(c.max_fee));
    return Math.max(0, fee);
  }
  if (rule.fee_type === "TIERED") {
    for (const t of c.tiers || []) {
      const lo = Number(t.min) || 0;
      const hi = t.max == null ? null : Number(t.max);
      if (amountMinor >= lo && (hi == null || amountMinor <= hi)) {
        return Math.max(0, Number(t.fee) || 0);
      }
    }
    return 0;
  }
  return 0;
}

export function isServiceEnabled(key) {
  const cfg = getConfig();
  if (!cfg || !cfg.services) return true;
  const flag = cfg.services.find((s) => s.key === key);
  return flag ? flag.enabled : true;
}
