import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { walletApi, transactionsApi, recoveryApi } from "../api/wallet";
import { beneficiariesApi } from "../api/social";
import {
  computeFee,
  enabledFundingMethods,
  refreshConfig,
} from "../services/feeConfig";
import { useAuth } from "../store/AuthContext";

function money(minor) {
  return (minor / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

const QUICK_AMOUNTS = [1000, 5000, 10000, 25000, 50000, 100000];

const ALL_FUNDING_METHODS = [
  { id: "card", label: "Card" },
  { id: "mobile_money", label: "Mobile money" },
  { id: "bank", label: "Bank transfer" },
];

const PENDING_STATUSES = new Set(["CREATED", "PENDING", "PROCESSING"]);

function cardDetailsValid(card) {
  const digits = (card.number || "").replace(/\D/g, "");
  const cvv = (card.cvv || "").replace(/\D/g, "");
  const month = Number(card.expiryMonth);
  const year = Number(card.expiryYear);
  return (
    digits.length >= 12 &&
    digits.length <= 19 &&
    (card.holder || "").trim().length >= 3 &&
    month >= 1 &&
    month <= 12 &&
    year >= 2025 &&
    year <= 2100 &&
    (cvv.length === 3 || cvv.length === 4)
  );
}

function bankDetailsValid(bank) {
  return (
    (bank.code || "").trim().length >= 3 &&
    (bank.accountNumber || "").trim().length >= 6 &&
    (bank.accountHolder || "").trim().length >= 3
  );
}

// mode: "send" | "withdraw" | "deposit"
export default function WalletAction({ mode }) {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isSend = mode === "send";
  const isWithdraw = mode === "withdraw";
  const isDeposit = mode === "deposit";
  const [wallet, setWallet] = useState({ balance: 0, currency: "XAF" });
  const [target, setTarget] = useState("");
  const [phone, setPhone] = useState("");
  const [amount, setAmount] = useState(isDeposit ? "" : "500");
  const [fundingMethod, setFundingMethod] = useState("card");
  const [fundingOptions, setFundingOptions] = useState(ALL_FUNDING_METHODS);
  const [card, setCard] = useState({
    number: "",
    holder: "",
    expiryMonth: "",
    expiryYear: "",
    cvv: "",
  });
  const [bank, setBank] = useState({
    code: "",
    accountNumber: "",
    accountHolder: "",
  });
  const [pin, setPin] = useState("");
  const [step, setStep] = useState("form"); // form | pending | done | failed
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [beneficiaries, setBeneficiaries] = useState([]);
  const [savedMsg, setSavedMsg] = useState(null);
  const pollRef = useRef(null);

  useEffect(() => {
    walletApi.get().then(setWallet).catch(() => {});
    if (isSend) beneficiariesApi.list().then(setBeneficiaries).catch(() => {});
    refreshConfig()
      .then(() => {
        const available = enabledFundingMethods(ALL_FUNDING_METHODS);
        setFundingOptions(available);
        setFundingMethod((current) => {
          if (available.some((m) => m.id === current)) return current;
          return available[0]?.id || "";
        });
      })
      .catch(() => {});
    if (user?.phone) setPhone(user.phone);
  }, [isSend, user?.phone]);

  useEffect(() => () => clearInterval(pollRef.current), []);

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
  const operation = isDeposit ? "DEPOSIT" : isSend ? "SEND_MONEY" : "WITHDRAW";
  const fee = computeFee(operation, amountMinor);
  const totalMinor = isDeposit ? amountMinor : amountMinor + fee;
  const creditedMinor = isDeposit ? Math.max(0, amountMinor - fee) : amountMinor;
  const isMoMo = isDeposit && fundingMethod === "mobile_money";
  const isCard = isDeposit && fundingMethod === "card";
  const isBank = isDeposit && fundingMethod === "bank";

  const depositDetailsOk = useMemo(() => {
    if (!isDeposit) return true;
    if (!fundingMethod) return false;
    if (isMoMo) return !!phone.trim();
    if (isCard) return cardDetailsValid(card);
    if (isBank) return bankDetailsValid(bank);
    return false;
  }, [isDeposit, fundingMethod, isMoMo, isCard, isBank, phone, card, bank]);

  const title = isDeposit ? "Add money" : isSend ? "Send money" : "Withdraw";
  const backTo = isDeposit ? "/dashboard" : "/wallet";
  const canSubmit = isDeposit
    ? amountMinor > 0 && depositDetailsOk
    : amountMinor > 0 && pin.length >= 4 && !!target;

  function finishTxn(txn) {
    clearInterval(pollRef.current);
    setResult(txn);
    if (txn.status === "SUCCESS") setStep("done");
    else if (txn.status === "FAILED") setStep("failed");
    else setStep("pending");
  }

  function startPolling(txnId) {
    clearInterval(pollRef.current);
    let nudged = false;
    pollRef.current = setInterval(async () => {
      try {
        if (!nudged) {
          nudged = true;
          recoveryApi.reconcile().catch(() => {});
        }
        const txn = await transactionsApi.get(txnId);
        if (!PENDING_STATUSES.has(txn.status)) {
          walletApi.get().then(setWallet).catch(() => {});
          finishTxn(txn);
        }
      } catch {
        /* keep polling */
      }
    }, 2000);
  }

  async function submit(e) {
    e.preventDefault();
    if (!canSubmit || busy) return;
    setError(null);
    setBusy(true);
    try {
      const key = `${mode}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      let txn;
      if (isDeposit) {
        const cardPayload = isCard
          ? {
              card_number: card.number.replace(/\D/g, ""),
              card_holder: card.holder.trim(),
              expiry_month: Number(card.expiryMonth),
              expiry_year: Number(card.expiryYear),
              cvv: card.cvv.replace(/\D/g, ""),
            }
          : undefined;
        const bankPayload = isBank
          ? {
              bank_code: bank.code.trim(),
              account_number: bank.accountNumber.trim(),
              account_holder: bank.accountHolder.trim(),
            }
          : undefined;
        txn = await walletApi.addMoney(
          amountMinor,
          fundingMethod,
          key,
          isMoMo ? phone.trim() : undefined,
          cardPayload,
          bankPayload
        );
      } else if (isSend) {
        txn = await walletApi.send(target, amountMinor, pin, key);
      } else {
        txn = await walletApi.withdraw(amountMinor, target, pin, key);
      }
      setResult(txn);
      if (PENDING_STATUSES.has(txn.status)) {
        setStep("pending");
        startPolling(txn.id);
      } else if (txn.status === "FAILED") {
        setStep("failed");
      } else {
        setStep("done");
        walletApi.get().then(setWallet).catch(() => {});
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <AppShell title={title} backTo={backTo} showNav={false} className="dash-screen">
      <div className="wallet-action-pad">
        {step === "form" && (
          <form className="wallet-action-form" onSubmit={submit}>
            <p className="muted wallet-action-balance">
              Balance: <strong>{money(wallet.balance)} {wallet.currency}</strong>
            </p>

            {isDeposit && (
              <>
                <label>Funding method</label>
                {fundingOptions.length === 0 ? (
                  <p className="muted small">
                    No deposit methods are enabled. Ask an administrator to turn on card, bank,
                    or mobile money funding.
                  </p>
                ) : (
                  <div className="chips funding-chips">
                    {fundingOptions.map((m) => (
                      <button
                        type="button"
                        key={m.id}
                        className={`chip ${fundingMethod === m.id ? "active" : ""}`}
                        onClick={() => setFundingMethod(m.id)}
                      >
                        {m.label}
                      </button>
                    ))}
                  </div>
                )}
              </>
            )}

            {isMoMo && (
              <>
                <label>Mobile money number</label>
                <input
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="+2376XXXXXXXX"
                  inputMode="tel"
                  autoComplete="tel"
                />
                <p className="muted small">You will confirm the payment on your phone (MTN / Orange).</p>
              </>
            )}

            {isCard && (
              <div className="funding-details mt">
                <label>Card number</label>
                <input
                  value={card.number}
                  onChange={(e) => setCard({ ...card, number: e.target.value })}
                  placeholder="4111 1111 1111 1111"
                  inputMode="numeric"
                  autoComplete="cc-number"
                  maxLength={23}
                />
                <label>Name on card</label>
                <input
                  value={card.holder}
                  onChange={(e) => setCard({ ...card, holder: e.target.value })}
                  placeholder="Name as printed on card"
                  autoComplete="cc-name"
                />
                <div className="row" style={{ gap: 12 }}>
                  <div style={{ flex: 1 }}>
                    <label>Expiry month</label>
                    <input
                      value={card.expiryMonth}
                      onChange={(e) => setCard({ ...card, expiryMonth: e.target.value })}
                      placeholder="MM"
                      inputMode="numeric"
                      autoComplete="cc-exp-month"
                      maxLength={2}
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label>Expiry year</label>
                    <input
                      value={card.expiryYear}
                      onChange={(e) => setCard({ ...card, expiryYear: e.target.value })}
                      placeholder="YYYY"
                      inputMode="numeric"
                      autoComplete="cc-exp-year"
                      maxLength={4}
                    />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label>CVV</label>
                    <input
                      type="password"
                      value={card.cvv}
                      onChange={(e) => setCard({ ...card, cvv: e.target.value })}
                      placeholder="•••"
                      inputMode="numeric"
                      autoComplete="cc-csc"
                      maxLength={4}
                    />
                  </div>
                </div>
                <p className="muted small">
                  Card details are used to process the deposit. Only a masked card number is kept
                  on the transaction; the CVV is never stored.
                </p>
              </div>
            )}

            {isBank && (
              <div className="funding-details mt">
                <label>Bank code (BIC)</label>
                <input
                  value={bank.code}
                  onChange={(e) => setBank({ ...bank, code: e.target.value })}
                  placeholder="e.g. BICXXXX"
                  autoComplete="off"
                />
                <label>Account number / IBAN</label>
                <input
                  value={bank.accountNumber}
                  onChange={(e) => setBank({ ...bank, accountNumber: e.target.value })}
                  placeholder="Account number"
                  autoComplete="off"
                />
                <label>Account holder name</label>
                <input
                  value={bank.accountHolder}
                  onChange={(e) => setBank({ ...bank, accountHolder: e.target.value })}
                  placeholder="Name on the account"
                  autoComplete="name"
                />
                <p className="muted small">
                  Bank details identify the funding source. Only a masked account reference is kept
                  on the transaction.
                </p>
              </div>
            )}

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

            {!isDeposit && (
              <>
                <label>{isSend ? "Recipient phone or email" : "Mobile money number"}</label>
                <input
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  placeholder={isSend ? "+237650000002" : "+2376XXXXXXXX"}
                  autoFocus={!isDeposit}
                />
                {isSend && target && !beneficiaries.some((b) => b.phone === target) && (
                  <div className="mt small">
                    <span className="link" onClick={saveBeneficiary}>+ Save as beneficiary</span>
                    {savedMsg && <span className="muted"> — {savedMsg}</span>}
                  </div>
                )}
              </>
            )}

            <label>Amount ({wallet.currency})</label>
            <div className="amount-field">
              <span className="amount-prefix">{wallet.currency}</span>
              <input
                type="number"
                min="1"
                step="1"
                inputMode="decimal"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
                placeholder="0"
                autoFocus={isDeposit}
                className="amount-input"
              />
            </div>

            <div className="chips amount-chips">
              {QUICK_AMOUNTS.map((v) => (
                <button
                  type="button"
                  key={v}
                  className={`chip ${Number(amount) === v ? "active" : ""}`}
                  onClick={() => setAmount(String(v))}
                >
                  {v.toLocaleString()}
                </button>
              ))}
            </div>

            {amountMinor > 0 && (
              <div className="fee-box">
                <div className="review-row">
                  <span className="muted">{isDeposit ? "Deposit" : "Amount"}</span>
                  <span>{money(amountMinor)} {wallet.currency}</span>
                </div>
                <div className="review-row">
                  <span className="muted">Service fee</span>
                  <span>{money(fee)} {wallet.currency}</span>
                </div>
                {isDeposit ? (
                  <div className="review-row total">
                    <span>Credited to wallet</span>
                    <span>{money(creditedMinor)} {wallet.currency}</span>
                  </div>
                ) : (
                  <div className="review-row total">
                    <span>Total</span>
                    <span>{money(totalMinor)} {wallet.currency}</span>
                  </div>
                )}
              </div>
            )}

            {!isDeposit && (
              <>
                <label>Transaction PIN <span className="muted small">(dev: 1234)</span></label>
                <input
                  type="password"
                  value={pin}
                  onChange={(e) => setPin(e.target.value)}
                  placeholder="••••"
                  inputMode="numeric"
                  maxLength={6}
                />
              </>
            )}

            {error && <div className="alert alert-error">{error}</div>}

            <div className="mt-lg">
              <button
                type="submit"
                className="btn-accent"
                style={{ width: "100%" }}
                disabled={busy || !canSubmit}
              >
                {busy
                  ? "Processing…"
                  : isDeposit
                    ? `Deposit ${money(amountMinor)} ${wallet.currency}`
                    : `${isSend ? "Send" : "Withdraw"} ${money(amountMinor)} ${wallet.currency}`}
              </button>
            </div>
          </form>
        )}

        {step === "pending" && result && (
          <div className="center wallet-action-done">
            <div className="result-icon">…</div>
            <h1 className="mt">Confirm on your phone</h1>
            <p className="muted">
              Waiting for mobile money confirmation for {money(result.amount)} {result.currency}.
            </p>
            <p className="muted small">{result.reference}</p>
            <div className="mt-lg">
              <button type="button" className="btn-ghost" onClick={() => navigate("/transactions")}>
                View activity
              </button>
            </div>
          </div>
        )}

        {step === "done" && result && (
          <div className="center wallet-action-done">
            <div className="result-icon success">✓</div>
            <h1 className="mt">
              {isDeposit ? "Money added" : isSend ? "Money sent" : "Withdrawal successful"}
            </h1>
            <p className="muted">
              {money(result.amount)} {result.currency} — {result.reference}
            </p>
            <div className="mt-lg">
              <button type="button" className="btn-primary" onClick={() => navigate("/dashboard")}>
                Done
              </button>
            </div>
          </div>
        )}

        {step === "failed" && result && (
          <div className="center wallet-action-done">
            <div className="result-icon">✕</div>
            <h1 className="mt">Transaction failed</h1>
            <p className="muted">{result.failure_reason || "Please try again."}</p>
            <div className="mt-lg">
              <button type="button" className="btn-primary" onClick={() => { setStep("form"); setError(null); }}>
                Try again
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
