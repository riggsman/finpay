import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { supportApi } from "../api/support";

export default function TicketDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [ticket, setTicket] = useState(null);
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    supportApi.getTicket(id).then(setTicket).catch(() => {});
  }

  useEffect(() => { load(); }, [id]);

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
