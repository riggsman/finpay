import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { authApi } from "../api/auth";
import { securityApi } from "../api/security";
import { devicesApi } from "../api/devices";
import { registerDevice, isConfigured } from "../services/pushService";
import { useAuth } from "../store/AuthContext";

function Section({ title, children }) {
  return (
    <div className="card mt" style={{ maxWidth: 620 }}>
      <h2>{title}</h2>
      {children}
    </div>
  );
}

function Note({ msg }) {
  if (!msg) return null;
  const cls = msg.ok ? "alert-success" : "alert-error";
  return <div className={`alert ${cls}`}>{msg.text}</div>;
}

export default function Security() {
  const navigate = useNavigate();
  const { user, login, auth } = useAuth();

  const [profile, setProfile] = useState({ first_name: "", last_name: "", email: "" });
  const [profileMsg, setProfileMsg] = useState(null);

  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [pwMsg, setPwMsg] = useState(null);

  const [pin, setPin] = useState({ current_pin: "", new_pin: "" });
  const [pinMsg, setPinMsg] = useState(null);

  const [limits, setLimits] = useState({ per_txn_limit: 0, daily_limit: 0 });
  const [limitsMsg, setLimitsMsg] = useState(null);

  const [sessions, setSessions] = useState([]);
  const [sessMsg, setSessMsg] = useState(null);

  const [fcmEnabled, setFcmEnabled] = useState(false);
  const [devices, setDevices] = useState([]);
  const [pushMsg, setPushMsg] = useState(null);

  const [activity, setActivity] = useState([]);

  useEffect(() => {
    authApi.me().then((me) =>
      setProfile({ first_name: me.first_name || "", last_name: me.last_name || "", email: me.email || "" })
    ).catch(() => {});
    securityApi.getLimits().then((l) =>
      setLimits({ per_txn_limit: l.per_txn_limit / 100, daily_limit: l.daily_limit / 100 })
    ).catch(() => {});
    refreshSessions();
    devicesApi.config().then((c) => setFcmEnabled(c.fcm_enabled)).catch(() => {});
    refreshDevices();
    securityApi.activity(30).then(setActivity).catch(() => {});
  }, []);

  function refreshSessions() {
    securityApi.listSessions().then(setSessions).catch(() => {});
  }

  function refreshDevices() {
    devicesApi.list().then(setDevices).catch(() => {});
  }

  async function enablePush() {
    setPushMsg(null);
    const res = await registerDevice();
    refreshDevices();
    if (!isConfigured()) {
      setPushMsg("Push is not configured in this build. Device registered without a push token.");
    } else if (res.push) {
      setPushMsg("Push enabled on this device.");
    } else {
      setPushMsg("Device registered. Allow notifications to receive push.");
    }
  }

  async function saveProfile(e) {
    e.preventDefault();
    setProfileMsg(null);
    try {
      const me = await securityApi.updateProfile(profile);
      setProfileMsg({ ok: true, text: "Profile updated." });
      // Keep the cached user in sync for the dashboard greeting.
      if (auth) login({ ...auth, user: { ...auth.user, ...me } });
    } catch (err) {
      setProfileMsg({ ok: false, text: err.message });
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

  async function saveLimits(e) {
    e.preventDefault();
    setLimitsMsg(null);
    try {
      const l = await securityApi.updateLimits(
        Math.round(limits.per_txn_limit * 100),
        Math.round(limits.daily_limit * 100)
      );
      setLimits({ per_txn_limit: l.per_txn_limit / 100, daily_limit: l.daily_limit / 100 });
      setLimitsMsg({ ok: true, text: "Limits updated." });
    } catch (err) {
      setLimitsMsg({ ok: false, text: err.message });
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

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand"><span className="dot" /> FinPay</div>
        <button className="btn-ghost" onClick={() => navigate("/dashboard")}>← Dashboard</button>
      </div>

      <h1>Profile &amp; Security</h1>
      <p className="muted">Manage your profile, credentials, limits, and sessions.</p>

      <Section title="Profile">
        <form onSubmit={saveProfile}>
          <div className="row">
            <div>
              <label>First name</label>
              <input value={profile.first_name} onChange={(e) => setProfile({ ...profile, first_name: e.target.value })} />
            </div>
            <div>
              <label>Last name</label>
              <input value={profile.last_name} onChange={(e) => setProfile({ ...profile, last_name: e.target.value })} />
            </div>
          </div>
          <label>Email</label>
          <input type="email" value={profile.email} onChange={(e) => setProfile({ ...profile, email: e.target.value })} />
          <Note msg={profileMsg} />
          <div className="mt"><button className="btn-primary">Save profile</button></div>
        </form>
      </Section>

      <Section title="Change password">
        <form onSubmit={changePassword}>
          <label>Current password</label>
          <input type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />
          <label>New password</label>
          <input type="password" value={pw.new_password} minLength={8} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />
          <Note msg={pwMsg} />
          <div className="mt"><button className="btn-primary" disabled={pw.new_password.length < 8}>Update password</button></div>
        </form>
      </Section>

      <Section title="Transaction PIN">
        <form onSubmit={changePin}>
          <label>Current PIN <span className="muted small">(dev default: 1234)</span></label>
          <input type="password" value={pin.current_pin} inputMode="numeric" maxLength={6} onChange={(e) => setPin({ ...pin, current_pin: e.target.value })} />
          <label>New PIN</label>
          <input type="password" value={pin.new_pin} inputMode="numeric" maxLength={6} onChange={(e) => setPin({ ...pin, new_pin: e.target.value })} />
          <Note msg={pinMsg} />
          <div className="mt"><button className="btn-primary" disabled={pin.new_pin.length < 4}>Update PIN</button></div>
        </form>
      </Section>

      <Section title="Transaction limits">
        <form onSubmit={saveLimits}>
          <div className="row">
            <div>
              <label>Per-transaction limit (XAF)</label>
              <input type="number" min="1" value={limits.per_txn_limit} onChange={(e) => setLimits({ ...limits, per_txn_limit: parseFloat(e.target.value || "0") })} />
            </div>
            <div>
              <label>Daily limit (XAF)</label>
              <input type="number" min="1" value={limits.daily_limit} onChange={(e) => setLimits({ ...limits, daily_limit: parseFloat(e.target.value || "0") })} />
            </div>
          </div>
          <Note msg={limitsMsg} />
          <div className="mt"><button className="btn-primary">Save limits</button></div>
        </form>
      </Section>

      <Section title="Active sessions">
        <p className="muted small">You have {sessions.length} active session(s).</p>
        <Note msg={sessMsg} />
        <div className="mt">
          <button className="btn-ghost" onClick={revokeAll}>Sign out all other devices</button>
        </div>
      </Section>

      <Section title="Notifications & devices">
        <p className="muted small">
          Push delivery is <strong style={{ color: fcmEnabled ? "var(--accent)" : "var(--muted)" }}>
            {fcmEnabled ? "enabled" : "not configured"}
          </strong> on the server.
        </p>
        {devices.length === 0 ? (
          <div className="empty">No devices registered.</div>
        ) : (
          devices.map((d) => (
            <div className="txn" key={d.id}>
              <div className="meta">
                <span>{d.device_type} · {d.device_id.slice(0, 16)}…</span>
                <span className="muted small">last seen {new Date(d.last_seen_at).toLocaleString()}</span>
              </div>
              <span className={`badge ${d.has_push_token ? "SUCCESS" : ""}`}>
                {d.has_push_token ? "PUSH ON" : "NO TOKEN"}
              </span>
            </div>
          ))
        )}
        <Note msg={pushMsg} />
        <div className="mt">
          <button className="btn-ghost" onClick={enablePush}>Enable push on this device</button>
        </div>
      </Section>

      <Section title="Recent activity">
        {activity.length === 0 ? (
          <div className="empty">No recent activity.</div>
        ) : (
          activity.map((a) => (
            <div className="txn" key={a.id}>
              <div className="meta">
                <span>{a.action.replaceAll("_", " ")}</span>
                <span className="muted small">
                  {new Date(a.created_at).toLocaleString()}{a.ip ? ` · ${a.ip}` : ""}
                </span>
              </div>
              <span className={`badge ${a.result === "SUCCESS" ? "SUCCESS" : "FAILED"}`}>{a.result}</span>
            </div>
          ))
        )}
      </Section>
    </div>
  );
}
