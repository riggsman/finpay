import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { securityApi } from "../api/security";
import { useNotifications } from "../store/NotificationContext";

function money(minor) {
  return (Number(minor) / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function toMinor(major) {
  const n = parseFloat(major);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.round(n * 100);
}

export default function LimitIncrease() {
  const navigate = useNavigate();
  const { limitsRevision } = useNotifications();
  const [limits, setLimits] = useState(null);
  const [requests, setRequests] = useState([]);
  const [form, setForm] = useState({ per_txn: "", daily: "", reason: "" });
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  function refresh() {
    securityApi.getLimits().then(setLimits).catch(() => {});
    securityApi.listLimitRequests().then(setRequests).catch(() => {});
  }

  useEffect(() => {
    refresh();
  }, [limitsRevision]);

  async function submit(e) {
    e.preventDefault();
    setMsg(null);
    const per = toMinor(form.per_txn);
    const daily = toMinor(form.daily);
    if (!per || !daily) {
      setMsg({ ok: false, text: "Enter valid per-transaction and daily limits in XAF." });
      return;
    }
    setBusy(true);
    try {
      await securityApi.createLimitRequest({
        requested_per_txn_limit: per,
        requested_daily_limit: daily,
        reason: form.reason.trim() || null,
      });
      setForm({ per_txn: "", daily: "", reason: "" });
      setMsg({ ok: true, text: "Limit increase request submitted for admin review." });
      refresh();
    } catch (err) {
      setMsg({ ok: false, text: err.message });
    } finally {
      setBusy(false);
    }
  }

  const pending = requests.some((r) => r.status === "PENDING");
  const grant = limits?.active_grant;

  return (
    <AppShell title="Limit increase" backTo="/security" showNav className="dash-screen">
      <p className="screen-desc">
        Request a temporary raise to your per-transaction and daily limits. Approvals are reviewed
        separately from KYC verification.
      </p>

      <div className="dash-section">
        <div className="dash-section-head"><h3>Current limits</h3></div>
        <div className="limits-card">
          <div className="limit-tile">
            <span className="muted small">Per transaction</span>
            <strong>{limits ? `${money(limits.per_txn_limit)} XAF` : "—"}</strong>
          </div>
          <div className="limit-tile">
            <span className="muted small">Daily</span>
            <strong>{limits ? `${money(limits.daily_limit)} XAF` : "—"}</strong>
          </div>
        </div>
        {limits && (
          <p className="muted small" style={{ marginTop: 8 }}>
            Used today: {money(limits.spent_today)} XAF · Remaining today: {money(limits.remaining_daily)} XAF
            {limits.default_per_txn_limit != null && (
              <> · Platform default: {money(limits.default_per_txn_limit)} XAF / txn</>
            )}
          </p>
        )}
        {grant && (
          <div className="alert alert-info mt">
            Raised limit active until {grant.expires_at ? new Date(grant.expires_at).toLocaleString() : "—"}.
            {grant.spending_cap != null && (
              <> Allowance left: {money(grant.remaining_allowance)} of {money(grant.spending_cap)} XAF.</>
            )}
          </div>
        )}
      </div>

      <div className="dash-section">
        <div className="dash-section-head"><h3>New request</h3></div>
        {pending || grant ? (
          <p className="muted small">
            {pending
              ? "You already have a pending request. Wait for an admin decision."
              : "You already have an active raised limit. You can request again after it expires or is fully used."}
          </p>
        ) : (
          <form className="form-card" onSubmit={submit}>
            <label>Requested per-transaction limit (XAF)</label>
            <input
              type="number"
              min="1"
              step="0.01"
              value={form.per_txn}
              onChange={(e) => setForm({ ...form, per_txn: e.target.value })}
              placeholder="e.g. 1000000"
              required
            />
            <label>Requested daily limit (XAF)</label>
            <input
              type="number"
              min="1"
              step="0.01"
              value={form.daily}
              onChange={(e) => setForm({ ...form, daily: e.target.value })}
              placeholder="e.g. 2000000"
              required
            />
            <label>Reason</label>
            <textarea
              rows={3}
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
              placeholder="Why do you need higher limits?"
            />
            {msg && <div className={`alert ${msg.ok ? "alert-success" : "alert-error"}`}>{msg.text}</div>}
            <div className="mt">
              <button className="btn-primary" disabled={busy}>
                {busy ? "Submitting…" : "Submit request"}
              </button>
            </div>
          </form>
        )}
        {msg && (pending || grant) && (
          <div className={`alert ${msg.ok ? "alert-success" : "alert-error"} mt`}>{msg.text}</div>
        )}
      </div>

      <div className="dash-section">
        <div className="dash-section-head"><h3>Request history</h3></div>
        {requests.length === 0 ? (
          <div className="empty">No limit increase requests yet.</div>
        ) : (
          <div className="activity-list">
            {requests.map((r) => (
              <div className="activity-item static" key={r.id}>
                <div className="activity-copy">
                  <strong>
                    {money(r.requested_per_txn_limit)} / {money(r.requested_daily_limit)} XAF
                  </strong>
                  <span>
                    {new Date(r.created_at).toLocaleString()}
                    {r.status === "APPROVED" && r.expires_at
                      ? ` · until ${new Date(r.expires_at).toLocaleDateString()}`
                      : ""}
                    {r.rejection_reason ? ` · ${r.rejection_reason}` : ""}
                  </span>
                </div>
                <span className={`badge ${r.status === "APPROVED" ? "SUCCESS" : r.status === "REJECTED" ? "FAILED" : "PENDING"}`}>
                  {r.status}
                </span>
              </div>
            ))}
          </div>
        )}
        <div className="mt">
          <button type="button" className="btn-ghost" onClick={() => navigate("/security")}>
            Back to Security
          </button>
        </div>
      </div>
    </AppShell>
  );
}
