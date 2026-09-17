import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import BalanceCard from "../components/BalanceCard";
import { dashboardApi, recoveryApi, transactionsApi } from "../api/wallet";
import { kycApi } from "../api/kyc";
import { socketService } from "../services/socketService";
import { useAuth } from "../store/AuthContext";
import { useNotifications } from "../store/NotificationContext";
import { CREDIT_TYPES, transactionStatusClass, transactionTitle } from "../utils/transactions";

function money(minor) {
  return (Number(minor) / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { unread, pendingRequests } = useNotifications();
  const [wallet, setWallet] = useState({ balance: 0, currency: "XAF" });
  const [transactions, setTransactions] = useState([]);
  const [kycStatus, setKycStatus] = useState(null);
  const [hideBal, setHideBal] = useState(false);

  const refresh = useCallback(async () => {
    const [summary, txns] = await Promise.all([
      dashboardApi.summary(),
      transactionsApi.list(3),
    ]);
    setWallet(summary.wallet);
    setTransactions(txns);
  }, []);

  useEffect(() => {
    recoveryApi.reconcile().catch(() => {}).finally(() => refresh().catch(() => {}));
    kycApi.get().then((k) => setKycStatus(k.status)).catch(() => {});
  }, [refresh]);

  useEffect(() => {
    const onWallet = (evt) => {
      setWallet((w) => ({ ...w, balance: evt.data.balance, currency: evt.data.currency }));
    };
    const onTxn = () => transactionsApi.list(3).then(setTransactions).catch(() => {});
    const onNotif = (evt) => {
      transactionsApi.list(3).then(setTransactions).catch(() => {});
      if (evt?.data?.type === "KYC_APPROVED" || evt?.data?.type === "KYC_REJECTED") {
        setKycStatus(evt.data.type === "KYC_APPROVED" ? "APPROVED" : "REJECTED");
      }
    };
    const onKyc = (evt) => {
      if (evt?.data?.status) setKycStatus(evt.data.status);
    };

    socketService.on("WALLET_BALANCE_UPDATED", onWallet);
    socketService.on("TRANSACTION_SUCCESS", onTxn);
    socketService.on("notification:new", onNotif);
    socketService.on("KYC_STATUS_UPDATED", onKyc);
    return () => {
      socketService.off("WALLET_BALANCE_UPDATED", onWallet);
      socketService.off("TRANSACTION_SUCCESS", onTxn);
      socketService.off("notification:new", onNotif);
      socketService.off("KYC_STATUS_UPDATED", onKyc);
    };
  }, []);

  const initials = useMemo(() => {
    const a = (user?.first_name || "?").slice(0, 1);
    const b = (user?.last_name || "").slice(0, 1);
    return `${a}${b}`.toUpperCase();
  }, [user]);

  const kycBanner = (() => {
    if (!kycStatus || kycStatus === "APPROVED") {
      return (
        <div className="kyc-banner">
          <span className="kyc-ico">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M20 6L9 17l-5-5" /></svg>
          </span>
          <div className="kyc-copy">
            <strong>KYC Verified</strong>
            <span>Identity confirmed</span>
          </div>
          <span className="kyc-pill">Active</span>
        </div>
      );
    }
    if (kycStatus === "UNDER_REVIEW") {
      return (
        <div className="kyc-banner pending">
          <span className="kyc-ico">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
          </span>
          <div className="kyc-copy">
            <strong>KYC under review</strong>
            <span>We’ll notify you when verification completes</span>
          </div>
          <span className="kyc-pill">Pending</span>
        </div>
      );
    }
    if (kycStatus === "REJECTED") {
      return (
        <button type="button" className="kyc-banner rejected kyc-banner-action" onClick={() => navigate("/kyc")}>
          <span className="kyc-ico">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </span>
          <div className="kyc-copy">
            <strong>Verification failed</strong>
            <span>Tap to review and resubmit</span>
          </div>
          <span className="kyc-pill">Action</span>
        </button>
      );
    }
    return (
      <button type="button" className="kyc-banner pending kyc-banner-action" onClick={() => navigate("/kyc")}>
        <span className="kyc-ico">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 3l9 4v6c0 5-3.8 9.6-9 11-5.2-1.4-9-6-9-11V7l9-4z" /></svg>
        </span>
        <div className="kyc-copy">
          <strong>Verify your identity</strong>
          <span>Complete KYC to unlock full account features</span>
        </div>
        <span className="kyc-pill">Start</span>
      </button>
    );
  })();

  return (
    <AppShell showNav wide className="dash-screen">
      <div className="dash-pad">
        <div className="dash-greeting">
          <div className="dash-user">
            <div className="dash-avatar" aria-hidden="true">{initials}</div>
            <div>
              <div className="hello">{greeting()}</div>
              <div className="name">{user?.first_name || "there"} {user?.last_name || ""}</div>
            </div>
          </div>
          <div className="dash-header-actions">
            <button
              type="button"
              className="dash-icon-btn"
              aria-label="Support"
              onClick={() => navigate("/support")}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="9" />
                <path d="M9.5 9.5a2.5 2.5 0 114 2c-.7.7-1.5 1.2-1.5 2.5M12 17h.01" />
              </svg>
            </button>
            <button
              type="button"
              className="dash-icon-btn bell"
              aria-label={unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}
              onClick={() => navigate("/notifications")}
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M6 9a6 6 0 0112 0c0 7 3 7 3 9H3c0-2 3-2 3-9" />
                <path d="M10 20a2 2 0 004 0" />
              </svg>
              {unread > 0 && <span className="count">{unread > 99 ? "99+" : unread}</span>}
            </button>
          </div>
        </div>

        <div className="dash-layout">
          <div className="dash-main">
            <BalanceCard
              amount={money(wallet.balance)}
              currency={wallet.currency}
              hidden={hideBal}
              onToggleHide={() => setHideBal((v) => !v)}
              chip={`Acct ••${String(user?.id || 0).padStart(4, "0").slice(-4)}`}
              meta="FinPay Wallet"
              onAdd={() => navigate("/wallet/add")}
              addLabel="+ Add money"
            />

            {kycBanner}

            <div className="dash-section">
              <div className="dash-section-head">
                <h3>Services</h3>
                <button type="button" onClick={() => navigate("/services")}>See all</button>
              </div>
              <div className="services-grid-4">
                <button type="button" className="service-item" onClick={() => navigate("/wallet/send")}>
                  <span className="service-ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 19V5M5 12l7-7 7 7" /></svg></span>
                  <span>Send</span>
                </button>
                <button
                  type="button"
                  className="service-item"
                  onClick={() => navigate("/wallet/requests")}
                  aria-label={
                    pendingRequests > 0
                      ? `Receive, ${pendingRequests} pending request${pendingRequests === 1 ? "" : "s"}`
                      : "Receive"
                  }
                >
                  <span className="service-ico green">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 5v14M5 12l7 7 7-7" /></svg>
                    {pendingRequests > 0 && (
                      <span className="count">{pendingRequests > 99 ? "99+" : pendingRequests}</span>
                    )}
                  </span>
                  <span>Receive</span>
                </button>
                <button type="button" className="service-item" onClick={() => navigate("/services")}>
                  <span className="service-ico amber"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16v10H4z" /><path d="M4 11h16" /></svg></span>
                  <span>Pay bills</span>
                </button>
              </div>
            </div>
          </div>

          <div className="dash-side">
            <div className="dash-section dash-activity">
              <div className="dash-section-head">
                <h3>Recent activity</h3>
                <button type="button" onClick={() => navigate("/transactions")}>View all</button>
              </div>
              <div className="activity-list">
                {transactions.length === 0 ? (
                  <div className="empty">No activity yet.</div>
                ) : (
                  transactions.map((t) => {
                    const isCredit = CREDIT_TYPES.has(t.type);
                    const isFailed = t.status === "FAILED";
                    return (
                      <button
                        type="button"
                        className="activity-item"
                        key={t.id}
                        onClick={() => navigate(`/transactions/${t.id}`)}
                      >
                        <span className={`activity-ico ${isFailed ? "out" : isCredit ? "in" : "out"}`}>
                          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            {isCredit ? (
                              <path d="M12 19V5M5 12l7-7 7 7" />
                            ) : (
                              <path d="M12 5v14M5 12l7 7 7-7" />
                            )}
                          </svg>
                        </span>
                        <div className="activity-body">
                          <div className="activity-top">
                            <div className="activity-copy">
                              <strong>{transactionTitle(t)}</strong>
                              <span>{new Date(t.created_at).toLocaleString()}</span>
                            </div>
                            <span className={`badge activity-status ${transactionStatusClass(t.status)}`}>
                              {t.status}
                            </span>
                          </div>
                          <div className="activity-bottom">
                            <div className={`activity-amt ${isFailed ? "failed" : isCredit ? "in" : "out"}`}>
                              {isCredit ? "+" : "−"}{money(t.amount)}
                            </div>
                          </div>
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
