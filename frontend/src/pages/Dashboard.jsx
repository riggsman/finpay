import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { dashboardApi, notificationsApi, transactionsApi, walletApi } from "../api/wallet";
import { socketService } from "../services/socketService";
import { useAuth } from "../store/AuthContext";

function formatMoney(minor, currency) {
  return `${(minor / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

const CREDIT_TYPES = new Set(["ADD_MONEY", "TRANSFER_RECEIVED"]);

const CONN_LABEL = {
  CONNECTED: { cls: "live", text: "Live" },
  CONNECTING: { cls: "reconnecting", text: "Connecting…" },
  RECONNECTING: { cls: "reconnecting", text: "Reconnecting…" },
  DISCONNECTED: { cls: "down", text: "Offline" },
  AUTHENTICATION_FAILED: { cls: "down", text: "Auth failed" },
};

export default function Dashboard() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [wallet, setWallet] = useState({ balance: 0, currency: "XAF" });
  const [transactions, setTransactions] = useState([]);
  const [notifications, setNotifications] = useState([]);
  const [unread, setUnread] = useState(0);
  const [connState, setConnState] = useState(socketService.getConnectionState());
  const [amount, setAmount] = useState("100");
  const [busy, setBusy] = useState(false);
  const [flashId, setFlashId] = useState(null);
  const [toast, setToast] = useState(null);
  const flashRef = useRef(null);

  const refresh = useCallback(async () => {
    const [summary, txns, notifs, count] = await Promise.all([
      dashboardApi.summary(),
      transactionsApi.list(10),
      notificationsApi.list(10),
      notificationsApi.unreadCount(),
    ]);
    setWallet(summary.wallet);
    setTransactions(txns);
    setNotifications(notifs);
    setUnread(count.unread);
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  // Wire realtime events to live UI updates (SRS section 59).
  useEffect(() => {
    const unsub = socketService.onStateChange(setConnState);

    const onWallet = (evt) => {
      setWallet((w) => ({ ...w, balance: evt.data.balance, currency: evt.data.currency }));
    };
    const onTxn = () => {
      transactionsApi.list(10).then(setTransactions).catch(() => {});
    };
    const onNotif = (evt) => {
      setUnread((u) => u + 1);
      setToast(evt.data.title + " — " + evt.data.message);
      setTimeout(() => setToast(null), 4000);
      // Refresh transactions too so received transfers appear live.
      transactionsApi.list(10).then(setTransactions).catch(() => {});
      notificationsApi.list(10).then((list) => {
        setNotifications(list);
        if (list[0]) {
          setFlashId(list[0].id);
          clearTimeout(flashRef.current);
          flashRef.current = setTimeout(() => setFlashId(null), 1500);
        }
      });
    };

    socketService.on("WALLET_BALANCE_UPDATED", onWallet);
    socketService.on("TRANSACTION_SUCCESS", onTxn);
    socketService.on("notification:new", onNotif);

    return () => {
      socketService.off("WALLET_BALANCE_UPDATED", onWallet);
      socketService.off("TRANSACTION_SUCCESS", onTxn);
      socketService.off("notification:new", onNotif);
      unsub();
    };
  }, []);

  async function addMoney() {
    const minor = Math.round(parseFloat(amount || "0") * 100);
    if (!minor || minor <= 0) return;
    setBusy(true);
    try {
      // Client-generated idempotency key protects against double taps / retries.
      const key = `add-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      await walletApi.addMoney(minor, "card", key);
      // The wallet + notification updates arrive via Socket.IO; also refresh as a
      // recovery path in case an event was missed.
      setTimeout(() => refresh().catch(() => {}), 600);
    } catch (e) {
      setToast(e.message);
      setTimeout(() => setToast(null), 4000);
    } finally {
      setBusy(false);
    }
  }

  async function markAllRead() {
    await notificationsApi.markAllRead();
    setUnread(0);
    notificationsApi.list(10).then(setNotifications).catch(() => {});
  }

  function signOut() {
    logout();
    navigate("/");
  }

  const conn = CONN_LABEL[connState] || CONN_LABEL.DISCONNECTED;

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand">
          <span className="dot" />
          FinPay
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span className={`pill ${conn.cls}`}>
            <span className="status-dot" />
            {conn.text}
          </span>
          <span className="bell pill">
            🔔 {unread > 0 && <span className="count">{unread}</span>}
          </span>
          <button className="btn-accent" onClick={() => navigate("/services")}>Pay bills</button>
          <button className="btn-ghost" onClick={() => navigate("/security")}>Settings</button>
          <button className="btn-ghost" onClick={signOut}>Sign out</button>
        </div>
      </div>

      {toast && <div className="alert alert-success">{toast}</div>}

      <p className="muted">
        Welcome back, <strong style={{ color: "var(--text)" }}>{user?.first_name}</strong>.
      </p>

      <div className="grid mt">
        <div className="card balance-card">
          <div className="muted small">Wallet balance</div>
          <div className="balance">
            {formatMoney(wallet.balance, wallet.currency)}
            <span className="cur">{wallet.currency}</span>
          </div>

          <div className="mt-lg">
            <label>Add money (amount in {wallet.currency})</label>
            <div className="row">
              <input
                type="number"
                min="1"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
              <button
                className="btn-accent"
                style={{ flex: "0 0 auto", minWidth: 150 }}
                onClick={addMoney}
                disabled={busy}
              >
                {busy ? "Processing…" : "＋ Add money"}
              </button>
            </div>
            <p className="muted small mt">
              Runs the full engine: transaction → ledger → wallet → event →
              notification → Socket.IO. Balance updates live.
            </p>
            <div className="row mt">
              <button className="btn-ghost" onClick={() => navigate("/wallet/send")}>↗ Send money</button>
              <button className="btn-ghost" onClick={() => navigate("/wallet/withdraw")}>↘ Withdraw</button>
            </div>
          </div>

          <h2 className="mt-lg">Recent transactions</h2>
          {transactions.length === 0 ? (
            <div className="empty">No transactions yet.</div>
          ) : (
            transactions.map((t) => {
              const isCredit = CREDIT_TYPES.has(t.type);
              return (
                <div className="txn" key={t.id}>
                  <div className="meta">
                    <span>{t.type.replaceAll("_", " ")}</span>
                    <span className="muted small">{t.reference}</span>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <div className="amt" style={{ color: isCredit ? "var(--accent)" : "var(--text)" }}>
                      {isCredit ? "+" : "−"}{formatMoney(t.amount, t.currency)} {t.currency}
                    </div>
                    <span className={`badge ${t.status}`}>{t.status}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        <div className="card">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h2 style={{ margin: 0 }}>Notifications</h2>
            {unread > 0 && (
              <span className="link small" onClick={markAllRead}>
                Mark all read
              </span>
            )}
          </div>
          <div className="mt">
            {notifications.length === 0 ? (
              <div className="empty">You're all caught up.</div>
            ) : (
              notifications.map((n) => (
                <div className={`notif ${flashId === n.id ? "flash" : ""}`} key={n.id}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <strong>{n.title}</strong>
                    <span className={`badge ${n.priority === "HIGH" ? "SUCCESS" : ""}`}>
                      {n.priority}
                    </span>
                  </div>
                  <div className="muted small mt">{n.message}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
