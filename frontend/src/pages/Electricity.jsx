import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { billPaymentsApi, transactionApi } from "../api/billPayments";
import { walletApi } from "../api/wallet";
import { socketService } from "../services/socketService";
import { computeFee, refreshConfig } from "../services/feeConfig";

function money(minor) {
  return (minor / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

// Steps: provider -> details -> review -> pin -> processing -> success | failed
export default function Electricity() {
  const navigate = useNavigate();
  const [step, setStep] = useState("provider");
  const [providers, setProviders] = useState([]);
  const [provider, setProvider] = useState(null);
  const [wallet, setWallet] = useState({ balance: 0, currency: "XAF" });
  const [meter, setMeter] = useState("");
  const [amount, setAmount] = useState("1000");
  const [validation, setValidation] = useState(null);
  const [pin, setPin] = useState("");
  const [txn, setTxn] = useState(null);
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [stillPending, setStillPending] = useState(false);
  const pollRef = useRef(null);
  const nudgedRef = useRef(false);

  useEffect(() => {
    billPaymentsApi.providers("electricity").then((r) => setProviders(r.providers)).catch(() => {});
    walletApi.get().then(setWallet).catch(() => {});
    refreshConfig().catch(() => {});
  }, []);

  useEffect(() => () => clearInterval(pollRef.current), []);

  const amountMinor = Math.round(parseFloat(amount || "0") * 100);

  async function selectProvider(p) {
    setProvider(p);
    setError(null);
    setStep("details");
  }

  async function validateMeter(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const v = await billPaymentsApi.validateMeter(provider.id, meter);
      setValidation(v);
      setStep("review");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function finishProcessing(finalTxn) {
    clearInterval(pollRef.current);
    setTxn(finalTxn);
    if (finalTxn.status === "SUCCESS") {
      transactionApi.receipt(finalTxn.id).then(setReceipt).catch(() => {});
      setStep("success");
    } else if (finalTxn.status === "FAILED") {
      setStep("failed");
    }
  }

  async function confirm() {
    setError(null);
    setBusy(true);
    try {
      const key = `elec-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const created = await billPaymentsApi.confirmElectricity(
        validation.validation_token,
        amountMinor,
        pin,
        key
      );
      setTxn(created);
      setStep("processing");

      // Subscribe to the transaction-specific room for live status.
      socketService.subscribeToTransaction(created.id);
      const onSuccess = (evt) => {
        if (evt?.data?.transaction_id === created.id) {
          transactionApi.get(created.id).then(finishProcessing).catch(() => {});
        }
      };
      const onFailed = (evt) => {
        if (evt?.data?.transaction_id === created.id) {
          transactionApi.get(created.id).then(finishProcessing).catch(() => {});
        }
      };
      socketService.on("transaction:success", onSuccess);
      socketService.on("transaction:failed", onFailed);
      socketService.on("TRANSACTION_SUCCESS", onSuccess);
      socketService.on("TRANSACTION_FAILED", onFailed);

      // Recovery path: poll in case a socket event is missed (SRS section 28).
      pollRef.current = setInterval(async () => {
        try {
          const latest = await transactionApi.get(created.id);
          if (latest.status === "SUCCESS" || latest.status === "FAILED") {
            finishProcessing(latest);
          } else if (latest.status === "PENDING") {
            // Provider timed out — the payment is being reconciled. Nudge the
            // reconciliation once so it settles promptly.
            setStillPending(true);
            if (!nudgedRef.current) {
              nudgedRef.current = true;
              transactionApi.reconcile().catch(() => {});
            }
          }
        } catch {
          /* ignore */
        }
      }, 1000);
    } catch (err) {
      setError(err.message);
      setStep("review");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-viewport">
      <div className="app-frame">
        <div className="app-scroll" style={{ padding: "12px 16px 28px" }}>
      <div className="topbar">
        <div className="brand">
          <span className="dot" />
          FinPay
        </div>
        <button className="btn-ghost" onClick={() => navigate("/services")}>
          ← Services
        </button>
      </div>

      <h1>⚡ Electricity</h1>
      <p className="muted">
        Wallet balance: <strong>{money(wallet.balance)} {wallet.currency}</strong>
      </p>

      <div className="card mt" style={{ maxWidth: 520 }}>
        {step === "provider" && (
          <>
            <h2>Select provider</h2>
            {providers.map((p) => (
              <button key={p.id} className="btn-ghost provider-row" onClick={() => selectProvider(p)}>
                <span>{p.name}</span>
                <span className="muted">›</span>
              </button>
            ))}
          </>
        )}

        {step === "details" && (
          <form onSubmit={validateMeter}>
            <h2>Meter details — {provider.name}</h2>
            <label>Meter number</label>
            <input
              value={meter}
              onChange={(e) => setMeter(e.target.value)}
              placeholder="e.g. 1234567890"
              inputMode="numeric"
              autoFocus
            />
            <label>Amount ({wallet.currency})</label>
            <input
              type="number"
              min="1"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button className="btn-primary" disabled={busy}>
                {busy ? "Validating…" : "Validate meter"}
              </button>
            </div>
          </form>
        )}

        {step === "review" && validation && (
          <>
            <h2>Review payment</h2>
            <div className="review-row"><span className="muted">Provider</span><span>{validation.provider.name}</span></div>
            <div className="review-row"><span className="muted">Meter number</span><span>{validation.customer.meter_number}</span></div>
            <div className="review-row"><span className="muted">Customer</span><span>{validation.customer.name}</span></div>
            <div className="review-row"><span className="muted">Amount</span><span>{money(amountMinor)} {wallet.currency}</span></div>
            <div className="review-row"><span className="muted">Service fee</span><span>{money(computeFee("ELECTRICITY", amountMinor))} {wallet.currency}</span></div>
            <div className="review-row total"><span>Total</span><span>{money(amountMinor + computeFee("ELECTRICITY", amountMinor))} {wallet.currency}</span></div>
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button className="btn-primary" onClick={() => setStep("pin")}>Confirm & pay</button>
              <div className="spacer" />
              <button className="btn-ghost" style={{ width: "100%" }} onClick={() => setStep("details")}>Back</button>
            </div>
          </>
        )}

        {step === "pin" && (
          <>
            <h2>Enter transaction PIN</h2>
            <p className="muted small">Dev PIN is <strong>1234</strong>.</p>
            <label>PIN</label>
            <input
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="••••"
              inputMode="numeric"
              maxLength={6}
              autoFocus
            />
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button className="btn-accent" style={{ width: "100%" }} onClick={confirm} disabled={busy || pin.length < 4}>
                {busy ? "Submitting…" : `Pay ${money(amountMinor)} ${wallet.currency}`}
              </button>
            </div>
          </>
        )}

        {step === "processing" && (
          <div className="center" style={{ padding: "20px 0" }}>
            <div className="spinner" />
            <h2 className="mt">{stillPending ? "Payment still processing…" : "Processing payment…"}</h2>
            <p className="muted">
              {stillPending
                ? "The provider is taking longer than usual. We're confirming your payment and will update this automatically."
                : "Waiting for provider confirmation in real time."}
            </p>
            <span className="pill reconnecting"><span className="status-dot" /> {txn?.reference}</span>
          </div>
        )}

        {step === "success" && (
          <div className="center">
            <div className="result-icon success">✓</div>
            <h2 className="mt">Payment successful</h2>
            {receipt && (
              <div className="receipt mt">
                <div className="review-row"><span className="muted">Receipt</span><span>{receipt.receipt_number}</span></div>
                <div className="review-row"><span className="muted">Customer</span><span>{receipt.customer}</span></div>
                <div className="review-row"><span className="muted">Meter</span><span>{receipt.meter_number}</span></div>
                <div className="review-row"><span className="muted">Provider ref</span><span>{receipt.provider_reference}</span></div>
                <div className="review-row total"><span>Total paid</span><span>{money(receipt.total)} {receipt.currency}</span></div>
              </div>
            )}
            <div className="mt-lg">
              <button className="btn-primary" onClick={() => navigate("/dashboard")}>Done</button>
            </div>
          </div>
        )}

        {step === "failed" && (
          <div className="center">
            <div className="result-icon failed">✕</div>
            <h2 className="mt">Payment failed</h2>
            <p className="muted">{txn?.failure_reason || "The transaction could not be completed."}</p>
            <div className="mt-lg">
              <button className="btn-ghost" style={{ width: "100%" }} onClick={() => setStep("details")}>Try again</button>
              <div className="spacer" />
              <button className="btn-primary" onClick={() => navigate("/dashboard")}>Back to dashboard</button>
            </div>
          </div>
        )}
      </div>
        </div>
      </div>
    </div>
  );
}
