import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AppShell from "../components/AppShell";
import { moneyRequestsApi } from "../api/social";
import { recoveryApi } from "../api/wallet";
import { socketService } from "../services/socketService";
import { useNotifications } from "../store/NotificationContext";

function money(minor) {
  return (Number(minor) / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

const STATUS_CLASS = {
  PENDING: "PROCESSING",
  PROCESSING: "PROCESSING",
  PAID: "SUCCESS",
  DECLINED: "FAILED",
  FAILED: "FAILED",
  CANCELLED: "",
};

const QUICK_AMOUNTS = [500, 1000, 2500, 5000, 10000];

export default function Requests() {
  const { refreshPendingRequests } = useNotifications();
  const [mainTab, setMainTab] = useState("current"); // current | make
  const [filter, setFilter] = useState("incoming"); // incoming | outgoing
  const [incoming, setIncoming] = useState([]);
  const [outgoing, setOutgoing] = useState([]);
  const [form, setForm] = useState({ payer: "", amount: "500", note: "" });
  const [pinFor, setPinFor] = useState(null);
  const [pin, setPin] = useState("");
  const [payPhone, setPayPhone] = useState("");
  const [error, setError] = useState(null);
  const [okMsg, setOkMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef(null);

  const load = useCallback(() => {
    moneyRequestsApi.list("incoming").then(setIncoming).catch(() => {});
    moneyRequestsApi.list("outgoing").then(setOutgoing).catch(() => {});
    refreshPendingRequests().catch(() => {});
  }, [refreshPendingRequests]);

  useEffect(() => {
    load();
  }, [load]);

  // Live updates when the other party creates / pays / declines / cancels.
  useEffect(() => {
    const refresh = () => load();
    const onIncomingRequest = () => {
      setMainTab("current");
      setFilter("incoming");
      setOkMsg("New money request received.");
      load();
    };
    const events = [
      "MONEY_REQUEST_PAID",
      "MONEY_REQUEST_DECLINED",
      "MONEY_REQUEST_UPDATED",
      "TRANSFER_RECEIVED",
      "WALLET_BALANCE_UPDATED",
      "notification:new",
    ];
    events.forEach((ev) => socketService.on(ev, refresh));
    socketService.on("MONEY_REQUESTED", onIncomingRequest);
    return () => {
      events.forEach((ev) => socketService.off(ev, refresh));
      socketService.off("MONEY_REQUESTED", onIncomingRequest);
    };
  }, [load]);

  const pendingIncoming = useMemo(
    () => incoming.filter((r) => r.status === "PENDING").length,
    [incoming]
  );
  const pendingOutgoing = useMemo(
    () => outgoing.filter((r) => r.status === "PENDING" || r.status === "PROCESSING").length,
    [outgoing]
  );
  const processingCount = useMemo(
    () =>
      [...incoming, ...outgoing].filter((r) => r.status === "PROCESSING").length,
    [incoming, outgoing]
  );

  // While Campay collects are in flight, nudge status checks frequently and refresh.
  useEffect(() => {
    clearInterval(pollRef.current);
    if (processingCount === 0) return undefined;
    const tick = () => {
      recoveryApi
        .reconcile()
        .catch(() => {})
        .finally(() => load());
    };
    tick();
    pollRef.current = setInterval(tick, 2500);
    return () => clearInterval(pollRef.current);
  }, [processingCount, load]);
  const list = filter === "incoming" ? incoming : outgoing;
  const amountMinor = Math.round(parseFloat(form.amount || "0") * 100);
  const canCreate = !!form.payer.trim() && amountMinor > 0 && !busy;

  function switchMain(next) {
    setMainTab(next);
    setError(null);
    setOkMsg(null);
    setPinFor(null);
    setPin("");
    setPayPhone("");
  }

  async function createRequest(e) {
    e.preventDefault();
    if (!canCreate) return;
    setError(null);
    setOkMsg(null);
    setBusy(true);
    try {
      await moneyRequestsApi.create(form.payer.trim(), amountMinor, form.note.trim());
      setForm({ payer: "", amount: "500", note: "" });
      setOkMsg("Request sent. It appears in history as pending until paid.");
      setFilter("outgoing");
      setMainTab("current");
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function pay(id) {
    setError(null);
    setBusy(true);
    try {
      const updated = await moneyRequestsApi.pay(id, pin, payPhone.trim() || undefined);
      setPinFor(null);
      setPin("");
      setPayPhone("");
      setIncoming((prev) => prev.map((r) => (r.id === id ? { ...r, ...updated } : r)));
      if (updated.status === "PROCESSING") {
        setOkMsg("Confirm the payment on your phone. We’ll credit the requester when Campay confirms.");
      } else {
        setOkMsg("Payment sent.");
      }
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function act(fn, id) {
    setError(null);
    try {
      const updated = await fn(id);
      if (updated?.id) {
        setIncoming((prev) => prev.map((r) => (r.id === id ? { ...r, ...updated } : r)));
        setOutgoing((prev) => prev.map((r) => (r.id === id ? { ...r, ...updated } : r)));
      }
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <AppShell title="Money requests" backTo="/wallet" showNav={false} className="dash-screen">
      <div className="wallet-action-pad requests-page">
        <div className="requests-main-tabs" role="tablist" aria-label="Money requests">
          <button
            type="button"
            role="tab"
            aria-selected={mainTab === "current"}
            className={`requests-main-tab ${mainTab === "current" ? "active" : ""}`}
            onClick={() => switchMain("current")}
          >
            Current requests
            {pendingIncoming + pendingOutgoing > 0 && (
              <span className="requests-count">{pendingIncoming + pendingOutgoing}</span>
            )}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mainTab === "make"}
            className={`requests-main-tab ${mainTab === "make" ? "active" : ""}`}
            onClick={() => switchMain("make")}
          >
            Make request
          </button>
        </div>

        {error && <div className="alert alert-error">{error}</div>}
        {okMsg && <div className="alert alert-success">{okMsg}</div>}

        {mainTab === "current" && (
          <section className="requests-panel" aria-label="Current requests">
            <p className="muted small requests-lead">
              Review money you’ve been asked for, or track requests you sent. Updates appear live.
            </p>

            <div className="chips requests-filter">
              <button
                type="button"
                className={`chip ${filter === "incoming" ? "active" : ""}`}
                onClick={() => {
                  setFilter("incoming");
                  setPinFor(null);
                  setPin("");
                }}
              >
                Incoming{pendingIncoming ? ` (${pendingIncoming})` : ""}
              </button>
              <button
                type="button"
                className={`chip ${filter === "outgoing" ? "active" : ""}`}
                onClick={() => setFilter("outgoing")}
              >
                Outgoing{pendingOutgoing ? ` (${pendingOutgoing})` : ""}
              </button>
            </div>

            {list.length === 0 ? (
              <div className="requests-empty">
                <strong>No {filter} requests</strong>
                <p className="muted small">
                  {filter === "incoming"
                    ? "When someone asks you for money, it will show up here."
                    : "Requests you send will appear here until they’re paid or cancelled."}
                </p>
                <button type="button" className="btn-primary" onClick={() => switchMain("make")}>
                  Make a request
                </button>
              </div>
            ) : (
              <ul className="requests-list">
                {list.map((r) => {
                  const counterparty = filter === "incoming" ? r.requester : r.payer;
                  const roleLabel = filter === "incoming" ? "From" : "To";
                  return (
                  <li className="request-card" key={r.id}>
                    <div className="request-card-top">
                      <div className="request-card-copy">
                        <strong>
                          {money(r.amount)} {r.currency}
                        </strong>
                        {counterparty ? (
                          <div className="request-party">
                            <span className="request-party-role">{roleLabel}</span>
                            <strong className="request-party-name">{counterparty.name}</strong>
                            {counterparty.phone ? (
                              <span className="muted small">{counterparty.phone}</span>
                            ) : null}
                            {counterparty.email ? (
                              <span className="muted small">{counterparty.email}</span>
                            ) : null}
                          </div>
                        ) : null}
                        {r.note ? <span className="request-note">{r.note}</span> : null}
                        <span className="muted small mono">{r.reference}</span>
                      </div>
                      <span className={`badge ${STATUS_CLASS[r.status] || ""}`}>{r.status}</span>
                    </div>

                    {filter === "incoming" && r.status === "PENDING" && (
                      <div className="request-card-actions">
                        {pinFor === r.id ? (
                          <>
                            <input
                              type="password"
                              placeholder="PIN"
                              value={pin}
                              onChange={(e) => setPin(e.target.value)}
                              inputMode="numeric"
                              maxLength={6}
                              aria-label="Transaction PIN"
                            />
                            <input
                              type="tel"
                              placeholder="MoMo phone (if wallet short)"
                              value={payPhone}
                              onChange={(e) => setPayPhone(e.target.value)}
                              aria-label="Mobile money phone for Campay"
                            />
                            <button
                              type="button"
                              className="btn-accent"
                              disabled={busy || pin.length < 4}
                              onClick={() => pay(r.id)}
                            >
                              {busy ? "Paying…" : "Confirm pay"}
                            </button>
                            <button
                              type="button"
                              className="btn-ghost"
                              onClick={() => {
                                setPinFor(null);
                                setPin("");
                                setPayPhone("");
                              }}
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <>
                            <button type="button" className="btn-primary" onClick={() => setPinFor(r.id)}>
                              Pay
                            </button>
                            <button
                              type="button"
                              className="btn-ghost"
                              onClick={() => act(moneyRequestsApi.decline, r.id)}
                            >
                              Decline
                            </button>
                          </>
                        )}
                      </div>
                    )}

                    {filter === "incoming" && r.status === "PROCESSING" && (
                      <p className="muted small">
                        Waiting for mobile money confirmation
                        {r.funding_mode === "CAMPAY" ? " (Campay)" : ""}. Approve on your phone if prompted.
                      </p>
                    )}

                    {filter === "outgoing" && r.status === "PROCESSING" && (
                      <p className="muted small">Payer is confirming mobile money. You’ll be credited when it clears.</p>
                    )}

                    {filter === "outgoing" && r.status === "PENDING" && (
                      <div className="request-card-actions">
                        <button
                          type="button"
                          className="btn-ghost"
                          onClick={() => act(moneyRequestsApi.cancel, r.id)}
                        >
                          Cancel request
                        </button>
                      </div>
                    )}
                  </li>
                  );
                })}
              </ul>
            )}
          </section>
        )}

        {mainTab === "make" && (
          <section className="requests-panel" aria-label="Make a request">
            <p className="muted small requests-lead">
              Ask someone to pay you. They’ll see it under Incoming, and you’ll be notified the moment they pay.
            </p>

            <form className="wallet-action-form requests-form" onSubmit={createRequest}>
              <label htmlFor="req-payer">From (phone or email)</label>
              <input
                id="req-payer"
                value={form.payer}
                onChange={(e) => setForm({ ...form, payer: e.target.value })}
                placeholder="+237650000002"
                autoComplete="tel"
                required
              />

              <label htmlFor="req-amount">Amount (XAF)</label>
              <div className="amount-field">
                <span className="amount-prefix">XAF</span>
                <input
                  id="req-amount"
                  className="amount-input"
                  type="number"
                  min="1"
                  step="1"
                  inputMode="decimal"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                  placeholder="0"
                  required
                />
              </div>
              <div className="chips amount-chips">
                {QUICK_AMOUNTS.map((v) => (
                  <button
                    type="button"
                    key={v}
                    className={`chip ${Number(form.amount) === v ? "active" : ""}`}
                    onClick={() => setForm({ ...form, amount: String(v) })}
                  >
                    {v.toLocaleString()}
                  </button>
                ))}
              </div>

              <label htmlFor="req-note">Note (optional)</label>
              <input
                id="req-note"
                value={form.note}
                onChange={(e) => setForm({ ...form, note: e.target.value })}
                placeholder="What's it for?"
                maxLength={120}
              />

              {amountMinor > 0 && (
                <div className="fee-box">
                  <div className="review-row total">
                    <span>You’re requesting</span>
                    <span>{money(amountMinor)} XAF</span>
                  </div>
                </div>
              )}

              <div className="mt-lg">
                <button type="submit" className="btn-accent" style={{ width: "100%" }} disabled={!canCreate}>
                  {busy ? "Sending…" : "Send request"}
                </button>
              </div>
            </form>
          </section>
        )}
      </div>
    </AppShell>
  );
}
