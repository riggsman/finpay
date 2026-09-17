import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import BalanceCard from "../components/BalanceCard";
import { dashboardApi, transactionsApi } from "../api/wallet";
import { useNotifications } from "../store/NotificationContext";
import { CREDIT_TYPES, transactionStatusClass, transactionTitle } from "../utils/transactions";

function money(minor) {
  return (Number(minor) / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

export default function Wallet() {
  const navigate = useNavigate();
  const { pendingRequests } = useNotifications();
  const [wallet, setWallet] = useState({ balance: 0, currency: "XAF" });
  const [transactions, setTransactions] = useState([]);
  const [hideBal, setHideBal] = useState(false);

  const refresh = useCallback(async () => {
    const [summary, txns] = await Promise.all([
      dashboardApi.summary(),
      transactionsApi.list(5),
    ]);
    setWallet(summary.wallet);
    setTransactions(txns);
  }, []);

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  return (
    <AppShell showNav title="Wallet" className="dash-screen">
      <div className="dash-pad">
        <BalanceCard
          label="Total wallet balance"
          amount={money(wallet.balance)}
          currency={wallet.currency}
          hidden={hideBal}
          onToggleHide={() => setHideBal((v) => !v)}
          chip="Main wallet"
          meta="Updated just now"
          onAdd={() => navigate("/wallet/add")}
          onSend={() => navigate("/wallet/withdraw")}
          addLabel="+ Top up"
          sendLabel="Withdraw"
        />

        <div className="dash-section">
          <div className="dash-section-head">
            <h3>Quick actions</h3>
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
                  ? `Request, ${pendingRequests} pending request${pendingRequests === 1 ? "" : "s"}`
                  : "Request"
              }
            >
              <span className="service-ico green">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 5v14M5 12l7 7 7-7" /></svg>
                {pendingRequests > 0 && (
                  <span className="count">{pendingRequests > 99 ? "99+" : pendingRequests}</span>
                )}
              </span>
              <span>Request</span>
            </button>
            <button type="button" className="service-item" onClick={() => navigate("/wallet/withdraw")}>
              <span className="service-ico amber"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 5v14M5 12l7 7 7-7" /></svg></span>
              <span>Withdraw</span>
            </button>
            <button type="button" className="service-item" onClick={() => navigate("/transactions")}>
              <span className="service-ico slate"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 6h16M4 12h16M4 18h10" /></svg></span>
              <span>History</span>
            </button>
          </div>
        </div>

        <div className="dash-section">
          <div className="dash-section-head">
            <h3>Recent transactions</h3>
            <button type="button" onClick={() => navigate("/transactions")}>View all</button>
          </div>
          <div className="activity-list">
            {transactions.length === 0 ? (
              <div className="empty">No transactions yet.</div>
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
                        {isCredit ? <path d="M12 19V5M5 12l7-7 7 7" /> : <path d="M12 5v14M5 12l7 7 7-7" />}
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
    </AppShell>
  );
}
