import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { walletApi } from "../api/wallet";

function money(minor) {
  return (minor / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

// mode: "send" | "withdraw"
export default function WalletAction({ mode }) {
  const navigate = useNavigate();
  const isSend = mode === "send";
  const [wallet, setWallet] = useState({ balance: 0, currency: "XAF" });
  const [target, setTarget] = useState("");
  const [amount, setAmount] = useState("500");
  const [pin, setPin] = useState("");
  const [step, setStep] = useState("form"); // form | done
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    walletApi.get().then(setWallet).catch(() => {});
  }, []);

  const amountMinor = Math.round(parseFloat(amount || "0") * 100);

  async function submit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const key = `${mode}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const txn = isSend
        ? await walletApi.send(target, amountMinor, pin, key)
        : await walletApi.withdraw(amountMinor, target, pin, key);
      setResult(txn);
      setStep("done");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center-screen">
      <div className="card auth-card">
        <div className="topbar" style={{ padding: 0, marginBottom: 8 }}>
          <div className="brand"><span className="dot" /> FinPay</div>
          <button className="btn-ghost" onClick={() => navigate("/dashboard")}>← Dashboard</button>
        </div>

        {step === "form" && (
          <form onSubmit={submit}>
            <h1>{isSend ? "Send money" : "Withdraw"}</h1>
            <p className="muted">
              Balance: <strong style={{ color: "var(--text)" }}>{money(wallet.balance)} {wallet.currency}</strong>
            </p>

            <label>{isSend ? "Recipient phone or email" : "Destination account"}</label>
            <input
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder={isSend ? "+237650000002" : "Bank ****1234"}
              autoFocus
            />

            <label>Amount ({wallet.currency})</label>
            <input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} />

            <label>Transaction PIN <span className="muted small">(dev: 1234)</span></label>
            <input
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="••••"
              inputMode="numeric"
              maxLength={6}
            />

            {error && <div className="alert alert-error">{error}</div>}

            <div className="mt-lg">
              <button className="btn-accent" style={{ width: "100%" }} disabled={busy || pin.length < 4 || !target}>
                {busy ? "Processing…" : `${isSend ? "Send" : "Withdraw"} ${money(amountMinor)} ${wallet.currency}`}
              </button>
            </div>
          </form>
        )}

        {step === "done" && (
          <div className="center">
            <div className="result-icon success">✓</div>
            <h1 className="mt">{isSend ? "Money sent" : "Withdrawal successful"}</h1>
            <p className="muted">
              {money(result.amount)} {result.currency} — {result.reference}
            </p>
            <div className="mt-lg">
              <button className="btn-primary" onClick={() => navigate("/dashboard")}>Done</button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
