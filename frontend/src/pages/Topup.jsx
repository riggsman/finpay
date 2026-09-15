import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { billPaymentsApi } from "../api/billPayments";
import { walletApi } from "../api/wallet";

function money(minor) {
  return (minor / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

// category: "airtime" | "data"
export default function Topup({ category }) {
  const navigate = useNavigate();
  const title = category === "data" ? "Data Bundles" : "Airtime";
  const [wallet, setWallet] = useState({ balance: 0, currency: "XAF" });
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState("");
  const [target, setTarget] = useState("");
  const [amount, setAmount] = useState("500");
  const [pin, setPin] = useState("");
  const [step, setStep] = useState("form"); // form | done | failed
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    walletApi.get().then(setWallet).catch(() => {});
    billPaymentsApi.topupProviders(category).then((r) => {
      setProviders(r.providers);
      if (r.providers[0]) setProvider(r.providers[0].id);
    }).catch(() => {});
  }, [category]);

  const amountMinor = Math.round(parseFloat(amount || "0") * 100);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const key = `topup-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const txn = await billPaymentsApi.confirmTopup(category, provider, target, amountMinor, pin, key);
      setResult(txn);
      setStep(txn.status === "SUCCESS" ? "done" : "failed");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center-screen">
      <div className="card auth-card" style={{ maxWidth: 460 }}>
        <div className="topbar" style={{ padding: 0, marginBottom: 8 }}>
          <div className="brand"><span className="dot" /> FinPay</div>
          <button className="btn-ghost" onClick={() => navigate("/services")}>← Services</button>
        </div>

        {step === "form" && (
          <form onSubmit={submit}>
            <h1>{category === "data" ? "📶" : "📱"} {title}</h1>
            <p className="muted">
              Balance: <strong style={{ color: "var(--text)" }}>{money(wallet.balance)} {wallet.currency}</strong>
            </p>
            <label>Provider</label>
            <select value={provider} onChange={(e) => setProvider(e.target.value)}>
              {providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            <label>Phone number</label>
            <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="+237650000000" required />
            <label>Amount ({wallet.currency})</label>
            <input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} />
            <label>Transaction PIN <span className="muted small">(dev: 1234)</span></label>
            <input type="password" value={pin} onChange={(e) => setPin(e.target.value)} inputMode="numeric" maxLength={6} />
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button className="btn-accent" style={{ width: "100%" }} disabled={busy || pin.length < 4 || !target}>
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
            <div className="mt-lg"><button className="btn-primary" onClick={() => navigate("/dashboard")}>Done</button></div>
          </div>
        )}

        {step === "failed" && (
          <div className="center">
            <div className="result-icon failed">✕</div>
            <h1 className="mt">Top-up failed</h1>
            <p className="muted">{result?.failure_reason || "The top-up could not be completed."}</p>
            <div className="mt-lg">
              <button className="btn-ghost" style={{ width: "100%" }} onClick={() => setStep("form")}>Try again</button>
              <div className="spacer" />
              <button className="btn-primary" onClick={() => navigate("/dashboard")}>Back to dashboard</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
