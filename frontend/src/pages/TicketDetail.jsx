import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { supportApi } from "../api/support";
import { getAccessToken } from "../api/client";

async function loadScreenshot(ticketId) {
  const token = getAccessToken();
  const res = await fetch(`/api/v1/support/tickets/${ticketId}/screenshot`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) return null;
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export default function TicketDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [ticket, setTicket] = useState(null);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [shotUrl, setShotUrl] = useState(null);

  function load() {
    supportApi.getTicket(id).then(setTicket).catch(() => {});
  }

  useEffect(() => { load(); }, [id]);

  useEffect(() => {
    let revoked = false;
    let url = null;
    if (!ticket?.has_screenshot) {
      setShotUrl(null);
      return undefined;
    }
    loadScreenshot(ticket.id).then((u) => {
      if (revoked) {
        if (u) URL.revokeObjectURL(u);
        return;
      }
      url = u;
      setShotUrl(u);
    });
    return () => {
      revoked = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [ticket?.id, ticket?.has_screenshot]);

  async function send(e) {
    e.preventDefault();
    if (!body.trim()) return;
    setBusy(true);
    try {
      await supportApi.addMessage(id, body);
      setBody("");
      load();
    } finally {
      setBusy(false);
    }
  }

  async function close() {
    await supportApi.closeTicket(id);
    load();
  }

  if (!ticket) return <div className="container"><p className="muted mt">Loading…</p></div>;

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand"><span className="dot" /> FinPay</div>
        <button className="btn-ghost" onClick={() => navigate("/support")}>← Support</button>
      </div>

      <h1>{ticket.subject}</h1>
      <p className="muted">
        {ticket.reference} · {ticket.category} · <span className={`badge ${ticket.status === "CLOSED" ? "" : "PROCESSING"}`}>{ticket.status}</span>
      </p>

      {(ticket.page_url || ticket.has_screenshot) && (
        <div className="card mt" style={{ maxWidth: 680 }}>
          <h2>Issue context</h2>
          {ticket.page_url && (
            <p className="small"><span className="muted">Page:</span> {ticket.page_url}</p>
          )}
          {ticket.context?.viewport && (
            <p className="small muted">
              Viewport {ticket.context.viewport.width}×{ticket.context.viewport.height}
              {ticket.context.timezone ? ` · ${ticket.context.timezone}` : ""}
            </p>
          )}
          {shotUrl && (
            <div className="mt">
              <img
                src={shotUrl}
                alt="Issue screenshot"
                style={{ width: "100%", borderRadius: 12, border: "1px solid var(--border)" }}
              />
            </div>
          )}
        </div>
      )}

      <div className="card mt" style={{ maxWidth: 680 }}>
        <div className="thread">
          {ticket.messages.map((m) => (
            <div key={m.id} className={`bubble ${m.sender === "user" ? "me" : "agent"}`}>
              <div className="bubble-sender">{m.sender === "user" ? "You" : "Support agent"}</div>
              <div>{m.body}</div>
              <div className="muted small mt">{new Date(m.created_at).toLocaleString()}</div>
            </div>
          ))}
        </div>

        {ticket.status !== "CLOSED" && (
          <form onSubmit={send} className="mt-lg">
            <div className="row">
              <input value={body} onChange={(e) => setBody(e.target.value)} placeholder="Write a reply…" />
              <button className="btn-primary" style={{ flex: "0 0 auto" }} disabled={busy}>Send</button>
            </div>
            <div className="mt"><button type="button" className="btn-ghost" onClick={close}>Close ticket</button></div>
          </form>
        )}
      </div>
    </div>
  );
}
