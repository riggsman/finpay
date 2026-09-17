import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { billPaymentsApi } from "../api/billPayments";
import { walletApi } from "../api/wallet";
import { computeFee, refreshConfig } from "../services/feeConfig";

function money(minor) {
  return (minor / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function titleFor(category) {
  if (category === "data") return "Data Bundles";
  if (category === "airtime") return "Airtime";
  if (category === "water") return "Water";
  return category.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function Topup({ category: categoryProp }) {
  const navigate = useNavigate();
  const params = useParams();
  const category = categoryProp || params.category || "airtime";
  const title = titleFor(category);
  const [wallet, setWallet] = useState({ balance: 0, currency: "XAF" });
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState("");
  const [target, setTarget] = useState("");
  const [amount, setAmount] = useState("500");
  const [pin, setPin] = useState("");
  const [step, setStep] = useState("form");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    walletApi.get().then(setWallet).catch(() => {});
    refreshConfig().catch(() => {});
    billPaymentsApi.topupProviders(category).then((r) => {
      setProviders(r.providers || []);
      if (r.providers?.[0]) setProvider(r.providers[0].id);
      else setProvider("");
    }).catch(() => setProviders([]));
  }, [category]);

  const selected = useMemo(
    () => providers.find((p) => p.id === provider) || null,
    [providers, provider]
  );
  const targetLabel = selected?.target_label || "Account / phone number";
  const amountMinor = Math.round(parseFloat(amount || "0") * 100);
  const fee = computeFee(category.toUpperCase(), amountMinor);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const key = `topup-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const txn = await billPaymentsApi.confirmTopup(
        category, provider, target, amountMinor, pin, key
      );
      setResult(txn);
      setStep(txn.status === "SUCCESS" ? "done" : "failed");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-viewport">
      <div className="app-frame">
        <div className="app-scroll" style={{ padding: 16 }}>
      <div className="topbar" style={{ marginBottom: 8 }}>
        <button className="btn-ghost" onClick={() => navigate("/services")}>← Back</button>
        <div className="brand"><span className="dot" /> FinPay</div>
      </div>

        {step === "form" && (
          <form onSubmit={submit} className="topup-sheet" style={{ padding: 0 }}>
            <h1>{selected?.icon || "•"} {title}</h1>
            <p className="muted">
              Balance: <strong>{money(wallet.balance)} {wallet.currency}</strong>
            </p>
            {providers.length === 0 ? (
              <div className="alert alert-info">No providers are enabled for this service yet.</div>
            ) : (
              <>
                <label>Provider</label>
                <select value={provider} onChange={(e) => setProvider(e.target.value)}>
                  {providers.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </select>
                <label>{targetLabel}</label>
                <input
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  placeholder={targetLabel}
                  required
                />
                <label>Amount ({wallet.currency})</label>
                <input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} />
                {amountMinor > 0 && (
                  <div className="fee-box">
                    <div className="review-row"><span className="muted">Amount</span><span>{money(amountMinor)} {wallet.currency}</span></div>
                    <div className="review-row"><span className="muted">Service fee</span><span>{money(fee)} {wallet.currency}</span></div>
                    <div className="review-row total"><span>Total</span><span>{money(amountMinor + fee)} {wallet.currency}</span></div>
                  </div>
                )}
                <label>Transaction PIN <span className="muted small">(dev: 1234)</span></label>
                <input type="password" value={pin} onChange={(e) => setPin(e.target.value)} inputMode="numeric" maxLength={6} />
              </>
            )}
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button
                className="btn-accent"
                style={{ width: "100%" }}
                disabled={busy || providers.length === 0 || pin.length < 4 || !target}
              >
                {busy ? "Processing…" : `Buy ${money(amountMinor)} ${wallet.currency}`}
              </button>
            </div>
          </form>
        )}

        {step === "done" && (
          <div className="center">
            <div className="result-icon success">✓</div>
            <h1 className="mt">Top-up successful</h1>
            <p className="muted">{money(result.amount)} {result.currency} — {result.reference}</p>
            <div className="mt-lg">
              <button className="btn-primary" onClick={() => navigate("/dashboard")}>Done</button>
            </div>
          </div>
        )}

        {step === "failed" && (
          <div className="center">
            <div className="result-icon failed">✕</div>
            <h1 className="mt">Top-up failed</h1>
            <p className="muted">{result?.failure_reason || "The provider declined the request."}</p>
            <div className="mt-lg">
              <button className="btn-primary" onClick={() => setStep("form")}>Try again</button>
            </div>
          </div>
        )}
        </div>
      </div>
    </div>
  );
}
