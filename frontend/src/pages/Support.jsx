import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { supportApi } from "../api/support";

export default function Support() {
  const navigate = useNavigate();
  const [tickets, setTickets] = useState([]);
  const [disputes, setDisputes] = useState([]);
  const [form, setForm] = useState({ subject: "", category: "general", message: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  function refresh() {
    supportApi.listTickets().then(setTickets).catch(() => {});
    supportApi.listDisputes().then(setDisputes).catch(() => {});
  }

  useEffect(() => { refresh(); }, []);

  async function createTicket(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await supportApi.createTicket(form.subject, form.category, form.message);
      setForm({ subject: "", category: "general", message: "" });
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand"><span className="dot" /> FinPay</div>
        <button className="btn-ghost" onClick={() => navigate("/dashboard")}>← Dashboard</button>
      </div>

      <h1>Support</h1>

      <div className="grid mt">
        <div>
          <div className="card">
            <h2>Open a ticket</h2>
            <form onSubmit={createTicket}>
              <label>Subject</label>
              <input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} required />
              <label>Category</label>
              <select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                <option value="general">General</option>
                <option value="payments">Payments</option>
                <option value="account">Account</option>
                <option value="kyc">KYC</option>
              </select>
              <label>How can we help?</label>
              <textarea
                rows={4}
                value={form.message}
                onChange={(e) => setForm({ ...form, message: e.target.value })}
                required
                style={{ width: "100%", padding: "12px 14px", borderRadius: 12, border: "1px solid var(--border)", background: "var(--bg-soft)", color: "var(--text)", fontFamily: "inherit", fontSize: 15 }}
              />
              {error && <div className="alert alert-error">{error}</div>}
              <div className="mt"><button className="btn-primary" disabled={busy}>Submit ticket</button></div>
            </form>
          </div>

          <div className="card mt">
            <h2>My disputes</h2>
            {disputes.length === 0 ? (
              <div className="empty">No disputes filed.</div>
            ) : (
              disputes.map((d) => (
                <div className="txn" key={d.id}>
                  <div className="meta">
                    <span>{d.reason.replaceAll("_", " ")}</span>
                    <span className="muted small">{d.reference} · txn #{d.transaction_id}</span>
                  </div>
                  <span className={`badge ${d.status === "RESOLVED" ? "SUCCESS" : d.status === "REJECTED" ? "FAILED" : "PROCESSING"}`}>{d.status}</span>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="card">
          <h2>My tickets</h2>
          {tickets.length === 0 ? (
            <div className="empty">No tickets yet.</div>
          ) : (
            tickets.map((t) => (
              <div className="txn clickable" key={t.id} onClick={() => navigate(`/support/tickets/${t.id}`)}>
                <div className="meta">
                  <span>{t.subject}</span>
                  <span className="muted small">{t.reference} · {t.category}</span>
                </div>
                <span className={`badge ${t.status === "CLOSED" ? "" : t.status === "RESOLVED" ? "SUCCESS" : "PROCESSING"}`}>{t.status}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
