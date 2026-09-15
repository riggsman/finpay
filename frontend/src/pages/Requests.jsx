import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { moneyRequestsApi } from "../api/social";

function money(minor) {
  return (minor / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

const STATUS_BADGE = {
  PENDING: "PROCESSING",
  PAID: "SUCCESS",
  DECLINED: "FAILED",
  CANCELLED: "",
};

export default function Requests() {
  const navigate = useNavigate();
  const [tab, setTab] = useState("incoming");
  const [incoming, setIncoming] = useState([]);
  const [outgoing, setOutgoing] = useState([]);
  const [form, setForm] = useState({ payer: "", amount: "500", note: "" });
  const [pinFor, setPinFor] = useState(null);
  const [pin, setPin] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    moneyRequestsApi.list("incoming").then(setIncoming).catch(() => {});
    moneyRequestsApi.list("outgoing").then(setOutgoing).catch(() => {});
  }, []);

  useEffect(() => { load(); }, [load]);

  async function createRequest(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await moneyRequestsApi.create(form.payer, Math.round(parseFloat(form.amount) * 100), form.note);
      setForm({ payer: "", amount: "500", note: "" });
      setTab("outgoing");
      load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function pay(id) {
    setError(null);
    try {
      await moneyRequestsApi.pay(id, pin);
      setPinFor(null);
      setPin("");
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function act(fn, id) {
    try { await fn(id); load(); } catch (err) { setError(err.message); }
  }

  const list = tab === "incoming" ? incoming : outgoing;

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand"><span className="dot" /> FinPay</div>
        <button className="btn-ghost" onClick={() => navigate("/dashboard")}>← Dashboard</button>
      </div>

      <h1>Money requests</h1>

      <div className="grid mt">
        <div className="card">
          <div className="tabs">
            <button className={`tab ${tab === "incoming" ? "active" : ""}`} onClick={() => setTab("incoming")}>Incoming</button>
            <button className={`tab ${tab === "outgoing" ? "active" : ""}`} onClick={() => setTab("outgoing")}>Outgoing</button>
          </div>

          {error && <div className="alert alert-error">{error}</div>}

          {list.length === 0 ? (
            <div className="empty">No {tab} requests.</div>
          ) : (
            list.map((r) => (
              <div className="txn" key={r.id} style={{ flexWrap: "wrap" }}>
                <div className="meta">
                  <span>{money(r.amount)} {r.currency}{r.note ? ` · ${r.note}` : ""}</span>
                  <span className="muted small">{r.reference}</span>
                </div>
                <span className={`badge ${STATUS_BADGE[r.status]}`}>{r.status}</span>
                {tab === "incoming" && r.status === "PENDING" && (
                  <div className="row mt" style={{ width: "100%" }}>
                    {pinFor === r.id ? (
                      <>
                        <input type="password" placeholder="PIN (1234)" value={pin} onChange={(e) => setPin(e.target.value)} inputMode="numeric" maxLength={6} />
                        <button className="btn-accent" style={{ flex: "0 0 auto" }} onClick={() => pay(r.id)}>Pay</button>
                        <button className="btn-ghost" style={{ flex: "0 0 auto" }} onClick={() => { setPinFor(null); setPin(""); }}>Cancel</button>
                      </>
                    ) : (
                      <>
                        <button className="btn-primary" onClick={() => setPinFor(r.id)}>Pay</button>
                        <button className="btn-ghost" onClick={() => act(moneyRequestsApi.decline, r.id)}>Decline</button>
                      </>
                    )}
                  </div>
                )}
                {tab === "outgoing" && r.status === "PENDING" && (
                  <div className="row mt" style={{ width: "100%" }}>
                    <button className="btn-ghost" onClick={() => act(moneyRequestsApi.cancel, r.id)}>Cancel request</button>
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        <div className="card">
          <h2>Request money</h2>
          <form onSubmit={createRequest}>
            <label>From (phone or email)</label>
            <input value={form.payer} onChange={(e) => setForm({ ...form, payer: e.target.value })} placeholder="+237650000002" required />
            <label>Amount (XAF)</label>
            <input type="number" min="1" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} />
            <label>Note (optional)</label>
            <input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="What's it for?" />
            <div className="mt"><button className="btn-primary" disabled={busy}>Send request</button></div>
          </form>
        </div>
      </div>
    </div>
  );
}
