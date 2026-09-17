import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { supportApi } from "../api/support";

async function capturePageScreenshot() {
  try {
    const html2canvas = (await import("html2canvas")).default;
    const canvas = await html2canvas(document.body, {
      useCORS: true,
      allowTaint: true,
      logging: false,
      scale: Math.min(window.devicePixelRatio || 1, 1.25),
      windowWidth: document.documentElement.scrollWidth,
      windowHeight: document.documentElement.scrollHeight,
    });
    return canvas.toDataURL("image/jpeg", 0.72);
  } catch {
    return null;
  }
}

function buildIssueContext() {
  return {
    path: window.location.pathname,
    search: window.location.search,
    hash: window.location.hash,
    viewport: {
      width: window.innerWidth,
      height: window.innerHeight,
      devicePixelRatio: window.devicePixelRatio || 1,
    },
    language: navigator.language,
    platform: navigator.platform,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    captured_at: new Date().toISOString(),
  };
}

export default function Support() {
  const navigate = useNavigate();
  const [tickets, setTickets] = useState([]);
  const [disputes, setDisputes] = useState([]);
  const [form, setForm] = useState({ subject: "", category: "general", message: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [captureNote, setCaptureNote] = useState(null);

  function refresh() {
    supportApi.listTickets().then(setTickets).catch(() => {});
    supportApi.listDisputes().then(setDisputes).catch(() => {});
  }

  useEffect(() => { refresh(); }, []);

  async function createTicket(e) {
    e.preventDefault();
    setError(null);
    setCaptureNote(null);
    setBusy(true);
    try {
      setCaptureNote("Capturing page screenshot…");
      const screenshot_base64 = await capturePageScreenshot();
      setCaptureNote(screenshot_base64 ? "Sending ticket with screenshot…" : "Sending ticket…");
      await supportApi.createTicket({
        subject: form.subject,
        category: form.category,
        message: form.message,
        page_url: window.location.href,
        user_agent: navigator.userAgent,
        context: buildIssueContext(),
        screenshot_base64: screenshot_base64 || undefined,
      });
      setForm({ subject: "", category: "general", message: "" });
      setCaptureNote(null);
      refresh();
    } catch (err) {
      setError(err.message);
      setCaptureNote(null);
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
            <p className="muted small">
              When you submit, FinPay automatically captures a screenshot of your current screen
              and sends page context so support can see exactly what you saw.
            </p>
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
              {captureNote && <div className="muted small mt">{captureNote}</div>}
              {error && <div className="alert alert-error">{error}</div>}
              <div className="mt"><button className="btn-primary" disabled={busy}>{busy ? "Submitting…" : "Submit ticket"}</button></div>
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
                  <span className="muted small">
                    {t.reference} · {t.category}
                    {t.has_screenshot ? " · screenshot attached" : ""}
                  </span>
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
