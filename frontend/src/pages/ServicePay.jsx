import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import AppShell from "../components/AppShell";
import { billPaymentsApi, transactionApi } from "../api/billPayments";
import { walletApi } from "../api/wallet";
import { socketService } from "../services/socketService";
import { computeFee, isServiceEnabled, refreshConfig } from "../services/feeConfig";

function money(minor) {
  return (Number(minor) / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function titleFor(category) {
  return String(category || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function enabledFields(provider) {
  const fields = Array.isArray(provider?.fields) ? provider.fields : [];
  return fields.filter((f) => f && f.enabled);
}

export default function ServicePay() {
  const navigate = useNavigate();
  const { category: categoryParam } = useParams();
  const category = (categoryParam || "airtime").toLowerCase();
  const title = titleFor(category);

  const [wallet, setWallet] = useState({ balance: 0, currency: "XAF" });
  const [providers, setProviders] = useState([]);
  const [providerId, setProviderId] = useState("");
  const [values, setValues] = useState({ phone: "", amount: "500", message: "" });
  const [pin, setPin] = useState("");
  const [step, setStep] = useState("form"); // form | review | pin | processing | done | failed
  const [validation, setValidation] = useState(null);
  const [result, setResult] = useState(null);
  const [receipt, setReceipt] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [stillPending, setStillPending] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    walletApi.get().then(setWallet).catch(() => {});
    (async () => {
      await refreshConfig().catch(() => {});
      if (cancelled) return;
      if (!isServiceEnabled(category)) {
        setError("This service is currently unavailable.");
        setProviders([]);
        return;
      }
      try {
        const r = await billPaymentsApi.providers(category);
        if (cancelled) return;
        const list = r.providers || [];
        setProviders(list);
        setProviderId(list[0]?.id || "");
        setValidation(null);
        setStep("form");
        setValues({ phone: "", amount: "500", message: "" });
        setPin("");
        setError(null);
      } catch {
        if (!cancelled) setProviders([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [category]);

  useEffect(() => () => clearInterval(pollRef.current), []);

  const selected = useMemo(
    () => providers.find((p) => p.id === providerId) || null,
    [providers, providerId]
  );
  const fields = useMemo(() => enabledFields(selected), [selected]);
  const isValidatePay = selected?.flow === "validate_pay";
  const amountMinor = Math.round(parseFloat(values.amount || "0") * 100) || 0;
  const feeOp = category.toUpperCase();
  const fee = computeFee(feeOp, amountMinor);
  const needsAmount = fields.some((f) => f.key === "amount");
  const needsPin = needsAmount;

  function setField(key, value) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  function fieldMeta(key) {
    return fields.find((f) => f.key === key);
  }

  async function onValidate(e) {
    e.preventDefault();
    if (!selected) return;
    setError(null);
    setBusy(true);
    try {
      const v = await billPaymentsApi.validate(category, selected.id, values.phone);
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
    setResult(finalTxn);
    if (finalTxn.status === "SUCCESS") {
      transactionApi.receipt(finalTxn.id).then(setReceipt).catch(() => {});
      setStep("done");
    } else if (finalTxn.status === "FAILED") {
      setStep("failed");
    } else {
      setStillPending(true);
    }
  }

  async function onPay(e) {
    e?.preventDefault?.();
    if (!selected || busy) return;
    setError(null);
    setBusy(true);
    try {
      const key = `pay-${category}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const body = {
        category,
        provider_id: selected.id,
        phone: values.phone || null,
        amount: needsAmount ? amountMinor : null,
        message: values.message || null,
        pin,
        validation_token: validation?.validation_token || null,
      };
      const txn = await billPaymentsApi.pay(body, key);
      setResult(txn);

      if (isValidatePay && (txn.status === "PENDING" || txn.status === "PROCESSING")) {
        setStep("processing");
        socketService.subscribeToTransaction(txn.id);
        const onDone = (evt) => {
          if (evt?.data?.transaction_id === txn.id) {
            transactionApi.get(txn.id).then(finishProcessing).catch(() => {});
          }
        };
        socketService.on("TRANSACTION_SUCCESS", onDone);
        socketService.on("TRANSACTION_FAILED", onDone);
        pollRef.current = setInterval(() => {
          transactionApi.get(txn.id).then((t) => {
            if (t.status === "SUCCESS" || t.status === "FAILED") finishProcessing(t);
          }).catch(() => {});
        }, 1500);
      } else if (txn.status === "SUCCESS") {
        setStep("done");
      } else {
        setStep("failed");
      }
    } catch (err) {
      setError(err.message);
      if (isValidatePay && step === "review") setStep("pin");
    } finally {
      setBusy(false);
    }
  }

  const phoneField = fieldMeta("phone");
  const amountField = fieldMeta("amount");
  const messageField = fieldMeta("message");

  const canSubmitDirect =
    !!selected &&
    (!phoneField || !phoneField.required || !!values.phone.trim()) &&
    (!amountField || !amountField.required || amountMinor > 0) &&
    (!messageField || !messageField.required || !!values.message.trim()) &&
    (!needsPin || pin.length >= 4);

  return (
    <AppShell title={title} backTo="/services" showNav className="dash-screen">
      <p className="screen-desc">
        Balance: <strong>{money(wallet.balance)} {wallet.currency}</strong>
      </p>

      {(step === "form" || step === "pin") && (
        <form
          className="dash-section form-card"
          onSubmit={isValidatePay && step === "form" ? onValidate : onPay}
        >
          {providers.length === 0 ? (
            <div className="alert alert-info">No providers are enabled for this service yet.</div>
          ) : (
            <>
              <label>Provider</label>
              <select
                value={providerId}
                onChange={(e) => {
                  setProviderId(e.target.value);
                  setValidation(null);
                  setStep("form");
                  setError(null);
                }}
              >
                {providers.map((p) => (
                  <option key={p.id} value={p.id}>
                    {(p.icon ? `${p.icon} ` : "") + p.name}
                  </option>
                ))}
              </select>

              {phoneField && (step === "form" || !isValidatePay) && (
                <>
                  <label>{phoneField.label}</label>
                  <input
                    value={values.phone}
                    onChange={(e) => setField("phone", e.target.value)}
                    placeholder={phoneField.label}
                    required={!!phoneField.required}
                    inputMode="tel"
                  />
                </>
              )}

              {(!isValidatePay || step === "pin") && amountField && (
                <>
                  <label>{amountField.label} ({wallet.currency})</label>
                  <input
                    type="number"
                    min="1"
                    step="0.01"
                    value={values.amount}
                    onChange={(e) => setField("amount", e.target.value)}
                    required={!!amountField.required}
                  />
                  {amountMinor > 0 && (
                    <div className="fee-box">
                      <div className="review-row">
                        <span className="muted">Amount</span>
                        <span>{money(amountMinor)} {wallet.currency}</span>
                      </div>
                      <div className="review-row">
                        <span className="muted">Service fee</span>
                        <span>{money(fee)} {wallet.currency}</span>
                      </div>
                      <div className="review-row total">
                        <span>Total</span>
                        <span>{money(amountMinor + fee)} {wallet.currency}</span>
                      </div>
                    </div>
                  )}
                </>
              )}

              {(!isValidatePay || step === "pin") && messageField && (
                <>
                  <label>{messageField.label}</label>
                  <input
                    value={values.message}
                    onChange={(e) => setField("message", e.target.value)}
                    placeholder={messageField.label}
                    required={!!messageField.required}
                  />
                </>
              )}

              {(!isValidatePay || step === "pin") && needsPin && (
                <>
                  <label>Transaction PIN <span className="muted small">(dev: 1234)</span></label>
                  <input
                    type="password"
                    value={pin}
                    onChange={(e) => setPin(e.target.value)}
                    inputMode="numeric"
                    maxLength={6}
                    required
                  />
                </>
              )}
            </>
          )}

          {error && <div className="alert alert-error">{error}</div>}

          <div className="mt-lg">
            {isValidatePay && step === "form" ? (
              <button
                type="submit"
                className="btn-accent"
                style={{ width: "100%" }}
                disabled={busy || !selected || !values.phone.trim()}
              >
                {busy ? "Validating…" : "Continue"}
              </button>
            ) : (
              <button
                type="submit"
                className="btn-accent"
                style={{ width: "100%" }}
                disabled={busy || !canSubmitDirect}
              >
                {busy ? "Processing…" : `Pay ${money(amountMinor)} ${wallet.currency}`}
              </button>
            )}
          </div>
        </form>
      )}

      {step === "review" && validation && (
        <div className="dash-section form-card">
          <h3 style={{ marginTop: 0 }}>Confirm details</h3>
          <div className="review-row">
            <span className="muted">Customer</span>
            <span>{validation.customer?.name}</span>
          </div>
          <div className="review-row">
            <span className="muted">{phoneField?.label || "Account"}</span>
            <span>{validation.customer?.meter_number}</span>
          </div>
          <div className="review-row">
            <span className="muted">Provider</span>
            <span>{validation.provider?.name}</span>
          </div>
          {error && <div className="alert alert-error">{error}</div>}
          <div className="row mt">
            <button type="button" className="btn-ghost" onClick={() => setStep("form")}>
              Back
            </button>
            <button type="button" className="btn-primary" onClick={() => setStep("pin")}>
              Continue to pay
            </button>
          </div>
        </div>
      )}

      {step === "processing" && (
        <div className="dash-section center">
          <div className="spinner" />
          <h2 className="mt">Processing payment</h2>
          <p className="muted">
            {stillPending
              ? "Still waiting on the provider. You can leave — we’ll notify you."
              : "Please wait while the provider confirms."}
          </p>
          <button type="button" className="btn-ghost mt" onClick={() => navigate("/dashboard")}>
            Go to dashboard
          </button>
        </div>
      )}

      {step === "done" && result && (
        <div className="dash-section center">
          <div className="result-icon success">✓</div>
          <h2 className="mt">Payment successful</h2>
          <p className="muted">
            {money(result.amount)} {result.currency} — {result.reference}
          </p>
          {receipt?.token && (
            <p className="muted small">Token: {receipt.token}</p>
          )}
          <div className="mt-lg">
            <button type="button" className="btn-primary" onClick={() => navigate("/dashboard")}>
              Done
            </button>
          </div>
        </div>
      )}

      {step === "failed" && (
        <div className="dash-section center">
          <div className="result-icon failed">✕</div>
          <h2 className="mt">Payment failed</h2>
          <p className="muted">{result?.failure_reason || error || "The provider declined the request."}</p>
          <div className="mt-lg">
            <button
              type="button"
              className="btn-primary"
              onClick={() => {
                setStep("form");
                setValidation(null);
                setError(null);
              }}
            >
              Try again
            </button>
          </div>
        </div>
      )}
    </AppShell>
  );
}
