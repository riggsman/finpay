import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { authApi } from "../api/auth";
import { securityApi } from "../api/security";
import { useAuth } from "../store/AuthContext";
import { fileToAvatarDataUrl, getAvatar, setAvatar } from "../services/avatarStore";

function money(minor) {
  return (Number(minor) / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function actionLabel(action) {
  return String(action || "").replaceAll("_", " ");
}

export default function Profile() {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const [me, setMe] = useState(user);
  const [limits, setLimits] = useState(null);
  const [activity, setActivity] = useState([]);
  const [avatar, setAvatarUrl] = useState(null);
  const [avatarMsg, setAvatarMsg] = useState(null);
  const [lang, setLang] = useState(localStorage.getItem("finpay_lang") || "en");
  const [showLang, setShowLang] = useState(false);
  const fileRef = useRef(null);

  useEffect(() => {
    authApi.me().then((m) => {
      setMe(m);
      setAvatarUrl(getAvatar(m.id));
    }).catch(() => {});
    securityApi.getLimits().then(setLimits).catch(() => {});
    securityApi.activity(3).then(setActivity).catch(() => {});
  }, []);

  const initials = useMemo(() => {
    const a = (me?.first_name || "?").slice(0, 1);
    const b = (me?.last_name || "").slice(0, 1);
    return `${a}${b}`.toUpperCase();
  }, [me]);

  async function onPickAvatar(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !me?.id) return;
    setAvatarMsg(null);
    try {
      const dataUrl = await fileToAvatarDataUrl(file);
      setAvatar(me.id, dataUrl);
      setAvatarUrl(dataUrl);
      setAvatarMsg("Profile picture updated.");
    } catch (err) {
      setAvatarMsg(err.message || "Could not update picture.");
    }
  }

  function saveLang(code) {
    setLang(code);
    localStorage.setItem("finpay_lang", code);
    setShowLang(false);
  }

  function signOut() {
    logout();
    navigate("/login");
  }

  if (showLang) {
    return (
      <AppShell title="Language" backTo={() => setShowLang(false)} showNav>
        <p className="screen-desc">Choose the language used across FinPay menus and notifications.</p>
        <div className="lang-list">
          {[
            { code: "en", flag: "🇬🇧", name: "English", note: "Default" },
            { code: "fr", flag: "🇫🇷", name: "Français", note: "Coming soon" },
          ].map((opt) => (
            <button
              key={opt.code}
              type="button"
              className={`lang-option ${lang === opt.code ? "selected" : ""}`}
              onClick={() => saveLang(opt.code)}
            >
              <span className="lang-flag">{opt.flag}</span>
              <span className="lang-meta">
                <strong>{opt.name}</strong>
                <span>{opt.note}</span>
              </span>
            </button>
          ))}
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell showNav className="dash-screen">
      <div className="dash-pad">
        <div className="profile-hero">
          <button
            type="button"
            className="avatar-edit"
            onClick={() => fileRef.current?.click()}
            aria-label="Change profile picture"
          >
            {avatar ? (
              <img src={avatar} alt="" className="avatar-img" />
            ) : (
              <span className="dash-avatar lg">{initials}</span>
            )}
            <span className="avatar-camera">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M4 8h3l2-2h6l2 2h3v11H4V8z" />
                <circle cx="12" cy="13" r="3.5" />
              </svg>
            </span>
          </button>
          <input ref={fileRef} type="file" accept="image/*" hidden onChange={onPickAvatar} />
          <div className="profile-hero-copy">
            <div className="hello">Your profile</div>
            <div className="name">{me?.first_name} {me?.last_name}</div>
            <p className="muted small">Only your photo can be changed. Other details are managed by FinPay.</p>
          </div>
        </div>
        {avatarMsg && <div className="alert alert-info" style={{ margin: "0 20px 12px" }}>{avatarMsg}</div>}

        <div className="profile-card">
          <div className="profile-row"><span className="k">Phone</span><span className="v">{me?.phone}</span></div>
          <div className="profile-row"><span className="k">Email</span><span className="v">{me?.email || "—"}</span></div>
          <div className="profile-row"><span className="k">Status</span><span className="v">{me?.status}</span></div>
          <div className="profile-row"><span className="k">Account</span><span className="v">FP{String(me?.id || 0).padStart(8, "0")}</span></div>
        </div>

          <div className="dash-section">
          <div className="dash-section-head">
            <h3>Transaction limits</h3>
            <button type="button" onClick={() => navigate("/security/limits")}>Request raise</button>
          </div>
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
          <p className="muted small" style={{ marginTop: 8 }}>
            Defaults are set by FinPay. Request a temporary increase for admin review.
          </p>
        </div>

        <div className="dash-section">
          <div className="dash-section-head">
            <h3>Recent activity</h3>
            <button type="button" onClick={() => navigate("/profile/activity")}>View all</button>
          </div>
          <div className="activity-list">
            {activity.length === 0 ? (
              <div className="empty">No recent activity.</div>
            ) : (
              activity.slice(0, 3).map((a) => (
                <button
                  type="button"
                  className="activity-item"
                  key={a.id}
                  onClick={() => navigate("/profile/activity")}
                >
                  <span className={`activity-ico ${a.result === "SUCCESS" ? "in" : "out"}`}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      {a.result === "SUCCESS" ? (
                        <path d="M20 6L9 17l-5-5" />
                      ) : (
                        <path d="M18 6L6 18M6 6l12 12" />
                      )}
                    </svg>
                  </span>
                  <div className="activity-copy">
                    <strong>{actionLabel(a.action)}</strong>
                    <span>{new Date(a.created_at).toLocaleString()}{a.ip ? ` · ${a.ip}` : ""}</span>
                  </div>
                  <span className={`badge ${a.result === "SUCCESS" ? "SUCCESS" : "FAILED"}`}>{a.result}</span>
                </button>
              ))
            )}
          </div>
        </div>

        <div className="dash-section">
          <div className="dash-section-head"><h3>Account</h3></div>
          <div className="settings-list">
            <button type="button" className="settings-item" onClick={() => navigate("/security")}>
              <span className="settings-left">
                <span className="settings-ico">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M12 3l9 4v6c0 5-3.8 9.6-9 11-5.2-1.4-9-6-9-11V7l9-4z" /></svg>
                </span>
                Security &amp; PIN
              </span>
              <span className="chev"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6" /></svg></span>
            </button>
            <button type="button" className="settings-item" onClick={() => navigate("/kyc")}>
              <span className="settings-left">
                <span className="settings-ico">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M20 6L9 17l-5-5" /></svg>
                </span>
                Identity verification
              </span>
              <span className="chev"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6" /></svg></span>
            </button>
            <button type="button" className="settings-item" onClick={() => setShowLang(true)}>
              <span className="settings-left">
                <span className="settings-ico">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3a14 14 0 010 18M12 3a14 14 0 000 18" /></svg>
                </span>
                Language
              </span>
              <span className="chev"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6" /></svg></span>
            </button>
          </div>
        </div>

        <div className="dash-section">
          <div className="dash-section-head"><h3>More</h3></div>
          <div className="settings-list">
            <button type="button" className="settings-item" onClick={() => navigate("/support")}>
              <span className="settings-left">
                <span className="settings-ico">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="12" cy="12" r="9" /><path d="M9.5 9.5a2.5 2.5 0 114 2c-.7.7-1.5 1.2-1.5 2.5M12 17h.01" /></svg>
                </span>
                Help &amp; support
              </span>
              <span className="chev"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6" /></svg></span>
            </button>
            {user?.is_admin && (
              <button type="button" className="settings-item" onClick={() => navigate("/admin")}>
                <span className="settings-left">
                  <span className="settings-ico">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M4 7h16v10H4z" /><path d="M8 7V5h8v2" /></svg>
                  </span>
                  Back Office
                </span>
                <span className="chev"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 18l6-6-6-6" /></svg></span>
              </button>
            )}
            <button type="button" className="settings-item danger-item" onClick={signOut}>
              <span className="settings-left">
                <span className="settings-ico rose">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M10 17l-5-5 5-5M5 12h11" /><path d="M14 5h4a1 1 0 011 1v12a1 1 0 01-1 1h-4" /></svg>
                </span>
                Sign out
              </span>
            </button>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
