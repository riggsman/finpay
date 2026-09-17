import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { securityApi } from "../api/security";
import { devicesApi } from "../api/devices";
import { registerDevice, isConfigured } from "../services/pushService";
import { useNotifications } from "../store/NotificationContext";

function Note({ msg }) {
  if (!msg) return null;
  const cls = msg.ok ? "alert-success" : "alert-error";
  return <div className={`alert ${cls}`}>{msg.text}</div>;
}

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

const PANELS = {
  password: "Change password",
  pin: "Transaction PIN",
  limits: "Limit request",
  notifications: "Notifications",
};

const MENU = [
  {
    id: "password",
    label: "Change password",
    hint: "Update your sign-in password",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <rect x="5" y="10" width="14" height="10" rx="2" />
        <path d="M8 10V8a4 4 0 018 0v2" />
      </svg>
    ),
  },
  {
    id: "pin",
    label: "Transaction PIN",
    hint: "PIN used to confirm payments",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M4 8h16v10H4z" />
        <path d="M8 12h.01M12 12h.01M16 12h.01" />
      </svg>
    ),
  },
  {
    id: "limits",
    label: "Limit request",
    hint: "Request a temporary raise",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M4 19V5M4 19h16" />
        <path d="M8 15v-4M12 15V9M16 15v-7" />
      </svg>
    ),
  },
  {
    id: "notifications",
    label: "Notifications",
    hint: "Push alerts on this device",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M6 16v-5a6 6 0 0112 0v5" />
        <path d="M5 16h14" />
        <path d="M10 19a2 2 0 004 0" />
      </svg>
    ),
  },
];

export default function Security() {
  const navigate = useNavigate();
  const { limitsRevision } = useNotifications();
  const [panel, setPanel] = useState(null);

  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [pwMsg, setPwMsg] = useState(null);

  const [pin, setPin] = useState({ current_pin: "", new_pin: "" });
  const [pinMsg, setPinMsg] = useState(null);

  const [limits, setLimits] = useState(null);
  const [requests, setRequests] = useState([]);
  const [limitForm, setLimitForm] = useState({ per_txn: "", daily: "", reason: "" });
  const [limitMsg, setLimitMsg] = useState(null);
  const [limitBusy, setLimitBusy] = useState(false);

  const [sessions, setSessions] = useState([]);
  const [sessMsg, setSessMsg] = useState(null);

  const [fcmEnabled, setFcmEnabled] = useState(false);
  const [devices, setDevices] = useState([]);
  const [pushMsg, setPushMsg] = useState(null);

  function refreshLimits() {
    securityApi.getLimits().then(setLimits).catch(() => {});
    securityApi.listLimitRequests().then(setRequests).catch(() => {});
  }

  function refreshSessions() {
    securityApi.listSessions().then(setSessions).catch(() => {});
  }

  function refreshDevices() {
    devicesApi.list().then(setDevices).catch(() => {});
  }

  useEffect(() => {
    refreshLimits();
    refreshSessions();
    devicesApi.config().then((c) => setFcmEnabled(c.fcm_enabled)).catch(() => {});
    refreshDevices();
  }, [limitsRevision]);

  async function enablePush() {
    setPushMsg(null);
    const res = await registerDevice();
    refreshDevices();
    if (!isConfigured()) {
      setPushMsg("Push is not configured in this build. This device was registered without notifications.");
    } else if (res.push) {
      setPushMsg("Push notifications enabled on this device.");
    } else {
      setPushMsg("Device registered. Allow notifications in the browser prompt to turn push on.");
    }
  }

  async function changePassword(e) {
    e.preventDefault();
    setPwMsg(null);
    try {
      await securityApi.changePassword(pw.current_password, pw.new_password);
      setPwMsg({ ok: true, text: "Password changed. Other sessions were signed out." });
      setPw({ current_password: "", new_password: "" });
      refreshSessions();
    } catch (err) {
      setPwMsg({ ok: false, text: err.message });
    }
  }

  async function changePin(e) {
    e.preventDefault();
    setPinMsg(null);
    try {
      await securityApi.setPin(pin.current_pin || null, pin.new_pin);
      setPinMsg({ ok: true, text: "Transaction PIN updated." });
      setPin({ current_pin: "", new_pin: "" });
    } catch (err) {
      setPinMsg({ ok: false, text: err.message });
    }
  }

  async function submitLimitRequest(e) {
    e.preventDefault();
    setLimitMsg(null);
    const per = toMinor(limitForm.per_txn);
    const daily = toMinor(limitForm.daily);
    if (!per || !daily) {
      setLimitMsg({ ok: false, text: "Enter valid per-transaction and daily limits in XAF." });
      return;
    }
    setLimitBusy(true);
    try {
      await securityApi.createLimitRequest({
        requested_per_txn_limit: per,
        requested_daily_limit: daily,
        reason: limitForm.reason.trim() || null,
      });
      setLimitForm({ per_txn: "", daily: "", reason: "" });
      setLimitMsg({ ok: true, text: "Limit increase request submitted for admin review." });
      refreshLimits();
    } catch (err) {
      setLimitMsg({ ok: false, text: err.message });
    } finally {
      setLimitBusy(false);
    }
  }

  async function revokeAll() {
    setSessMsg(null);
    try {
      const res = await securityApi.revokeAllSessions();
      setSessMsg({ ok: true, text: res.message });
      refreshSessions();
    } catch (err) {
      setSessMsg({ ok: false, text: err.message });
    }
  }

  const pendingLimit = requests.some((r) => r.status === "PENDING");
  const grant = limits?.active_grant;
  const title = panel ? PANELS[panel] : "Security";
  const backTo = panel ? () => setPanel(null) : "/profile";

  if (panel === "password") {
    return (
      <AppShell title={title} backTo={backTo} showNav className="dash-screen">
        <p className="screen-desc">Choose a strong password you do not reuse elsewhere.</p>
        <div className="dash-section">
          <form className="form-card" onSubmit={changePassword}>
            <label>Current password</label>
            <input
              type="password"
              value={pw.current_password}
              onChange={(e) => setPw({ ...pw, current_password: e.target.value })}
              required
            />
            <label>New password</label>
            <input
              type="password"
              value={pw.new_password}
              minLength={8}
              onChange={(e) => setPw({ ...pw, new_password: e.target.value })}
              required
            />
            <Note msg={pwMsg} />
            <div className="mt">
              <button className="btn-primary" disabled={pw.new_password.length < 8}>
                Update password
              </button>
            </div>
          </form>
        </div>
      </AppShell>
    );
  }

  if (panel === "pin") {
    return (
      <AppShell title={title} backTo={backTo} showNav className="dash-screen">
        <p className="screen-desc">This PIN confirms withdrawals, transfers, and bill payments.</p>
        <div className="dash-section">
          <form className="form-card" onSubmit={changePin}>
            <label>
              Current PIN <span className="muted small">(dev default: 1234)</span>
            </label>
            <input
              type="password"
              value={pin.current_pin}
              inputMode="numeric"
              maxLength={6}
              onChange={(e) => setPin({ ...pin, current_pin: e.target.value })}
            />
            <label>New PIN</label>
            <input
              type="password"
              value={pin.new_pin}
              inputMode="numeric"
              maxLength={6}
              onChange={(e) => setPin({ ...pin, new_pin: e.target.value })}
              required
            />
            <Note msg={pinMsg} />
            <div className="mt">
              <button className="btn-primary" disabled={pin.new_pin.length < 4}>
                Update PIN
              </button>
            </div>
          </form>
        </div>
      </AppShell>
    );
  }

  if (panel === "limits") {
    return (
      <AppShell title={title} backTo={backTo} showNav className="dash-screen">
        <p className="screen-desc">
          Request a temporary raise. Approvals are reviewed separately from KYC.
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
              Used today: {money(limits.spent_today)} XAF · Remaining today:{" "}
              {money(limits.remaining_daily)} XAF
            </p>
          )}
          {grant && (
            <div className="alert alert-info mt">
              Raised limit active until{" "}
              {grant.expires_at ? new Date(grant.expires_at).toLocaleString() : "—"}.
            </div>
          )}
        </div>

        <div className="dash-section">
          <div className="dash-section-head"><h3>New request</h3></div>
          {pendingLimit || grant ? (
            <p className="muted small">
              {pendingLimit
                ? "You already have a pending request. Wait for an admin decision."
                : "You already have an active raised limit. Request again after it expires or is fully used."}
            </p>
          ) : (
            <form className="form-card" onSubmit={submitLimitRequest}>
              <label>Requested per-transaction limit (XAF)</label>
              <input
                type="number"
                min="1"
                step="0.01"
                value={limitForm.per_txn}
                onChange={(e) => setLimitForm({ ...limitForm, per_txn: e.target.value })}
                placeholder="e.g. 1000000"
                required
              />
              <label>Requested daily limit (XAF)</label>
              <input
                type="number"
                min="1"
                step="0.01"
                value={limitForm.daily}
                onChange={(e) => setLimitForm({ ...limitForm, daily: e.target.value })}
                placeholder="e.g. 2000000"
                required
              />
              <label>Reason</label>
              <textarea
                rows={3}
                value={limitForm.reason}
                onChange={(e) => setLimitForm({ ...limitForm, reason: e.target.value })}
                placeholder="Why do you need higher limits?"
              />
              <Note msg={limitMsg} />
              <div className="mt">
                <button className="btn-primary" disabled={limitBusy}>
                  {limitBusy ? "Submitting…" : "Submit request"}
                </button>
              </div>
            </form>
          )}
          {limitMsg && (pendingLimit || grant) && (
            <div className={`alert ${limitMsg.ok ? "alert-success" : "alert-error"} mt`}>
              {limitMsg.text}
            </div>
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
                      {r.rejection_reason ? ` · ${r.rejection_reason}` : ""}
                    </span>
                  </div>
                  <span
                    className={`badge ${
                      r.status === "APPROVED"
                        ? "SUCCESS"
                        : r.status === "REJECTED"
                          ? "FAILED"
                          : "PENDING"
                    }`}
                  >
                    {r.status}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </AppShell>
    );
  }

  if (panel === "notifications") {
    return (
      <AppShell title={title} backTo={backTo} showNav className="dash-screen">
        <p className="screen-desc">
          {fcmEnabled
            ? "Allow FinPay to send alerts on this browser."
            : "Push delivery may be unavailable on the server. You can still register this device."}
        </p>

        <div className="dash-section">
          <div className="dash-section-head"><h3>This device</h3></div>
          {devices.length === 0 ? (
            <div className="empty">No devices registered yet.</div>
          ) : (
            <div className="activity-list">
              {devices.map((d, index) => (
                <div className="activity-item static" key={d.id}>
                  <div className="activity-copy">
                    <strong>
                      {String(d.device_type || "web").charAt(0).toUpperCase()
                        + String(d.device_type || "web").slice(1)}{" "}
                      device {index + 1}
                    </strong>
                    <span>Last active {new Date(d.last_seen_at).toLocaleString()}</span>
                  </div>
                  <span className={`badge ${d.push_enabled ? "SUCCESS" : "FAILED"}`}>
                    {d.push_enabled ? "ON" : "OFF"}
                  </span>
                </div>
              ))}
            </div>
          )}
          <Note msg={pushMsg} />
          <div className="mt">
            <button type="button" className="btn-primary" onClick={enablePush}>
              Enable push on this device
            </button>
          </div>
        </div>

        <div className="dash-section">
          <div className="dash-section-head"><h3>In-app inbox</h3></div>
          <p className="muted small" style={{ margin: "0 0 10px" }}>
            View alerts for payments, limits, KYC, and support.
          </p>
          <button type="button" className="btn-ghost" onClick={() => navigate("/notifications")}>
            Open notifications →
          </button>
        </div>

        <div className="dash-section">
          <div className="dash-section-head"><h3>Active sessions</h3></div>
          <p className="muted small" style={{ margin: "0 0 10px" }}>
            You have {sessions.length} active session(s).
          </p>
          <Note msg={sessMsg} />
          <button type="button" className="btn-ghost" onClick={revokeAll}>
            Sign out all other devices
          </button>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell title="Security" backTo="/profile" showNav className="dash-screen">
      <p className="screen-desc">Choose a setting to manage. Only one screen opens at a time.</p>

      <div className="dash-section">
        <div className="settings-list">
          {MENU.map((item) => (
            <button
              key={item.id}
              type="button"
              className="settings-item"
              onClick={() => setPanel(item.id)}
            >
              <span className="settings-left">
                <span className="settings-ico">{item.icon}</span>
                <span className="settings-copy">
                  <strong>{item.label}</strong>
                  <span className="muted small">{item.hint}</span>
                </span>
              </span>
              <span className="chev">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 18l6-6-6-6" />
                </svg>
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="dash-section">
        <button
          type="button"
          className="btn-ghost"
          style={{ width: "100%" }}
          onClick={() => navigate("/profile/activity")}
        >
          View account activity →
        </button>
      </div>
    </AppShell>
  );
}
