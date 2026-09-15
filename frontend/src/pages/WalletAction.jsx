import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { walletApi } from "../api/wallet";
import { beneficiariesApi } from "../api/social";
import { computeFee } from "../services/feeConfig";

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
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [savedMsg, setSavedMsg] = useState(null);

  useEffect(() => {
    walletApi.get().then(setWallet).catch(() => {});
    if (isSend) beneficiariesApi.list().then(setBeneficiaries).catch(() => {});
  }, [isSend]);

  async function saveBeneficiary() {
    setSavedMsg(null);
    try {
      await beneficiariesApi.add(target);
      const list = await beneficiariesApi.list();
      setBeneficiaries(list);
      setSavedMsg("Saved to beneficiaries.");
    } catch (err) {
      setSavedMsg(err.message);
    }
  }

  const amountMinor = Math.round(parseFloat(amount || "0") * 100);
  const operation = isSend ? "SEND_MONEY" : "WITHDRAW";
  const fee = computeFee(operation, amountMinor);
  const totalMinor = amountMinor + fee;

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

            {isSend && beneficiaries.length > 0 && (
              <>
                <label>Beneficiaries</label>
                <div className="chips">
                  {beneficiaries.map((b) => (
                    <button
                      type="button"
                      key={b.id}
                      className={`chip ${target === b.phone ? "active" : ""}`}
                      onClick={() => setTarget(b.phone)}
                    >
                      {b.display_name}
                    </button>
                  ))}
                </div>
              </>
            )}

            <label>{isSend ? "Recipient phone or email" : "Destination account"}</label>
            <input
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder={isSend ? "+237650000002" : "Bank ****1234"}
              autoFocus
            />
            {isSend && target && !beneficiaries.some((b) => b.phone === target) && (
              <div className="mt small">
                <span className="link" onClick={saveBeneficiary}>+ Save as beneficiary</span>
                {savedMsg && <span className="muted"> — {savedMsg}</span>}
              </div>
            )}

            <label>Amount ({wallet.currency})</label>
            <input type="number" min="1" value={amount} onChange={(e) => setAmount(e.target.value)} />

            {amountMinor > 0 && (
              <div className="fee-box">
                <div className="review-row"><span className="muted">Amount</span><span>{money(amountMinor)} {wallet.currency}</span></div>
                <div className="review-row"><span className="muted">Service fee</span><span>{money(fee)} {wallet.currency}</span></div>
                <div className="review-row total"><span>Total</span><span>{money(totalMinor)} {wallet.currency}</span></div>
              </div>
            )}

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
