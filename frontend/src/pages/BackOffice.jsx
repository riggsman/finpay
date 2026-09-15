import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminApi } from "../api/admin";
import { useAuth } from "../store/AuthContext";

const toMajor = (m) => (m == null ? "" : (Number(m) / 100).toString());
const toMinor = (x) => (x === "" || x == null ? null : Math.round(parseFloat(x) * 100));

function money(minor) {
  return (Number(minor) / 100).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function ruleToDraft(rule) {
  const c = rule.config || {};
  return {
    fee_type: rule.fee_type,
    active: rule.active,
    flat: toMajor(c.fee),
    percent: c.percent ?? "",
    min_fee: toMajor(c.min_fee),
    max_fee: toMajor(c.max_fee),
    tiers: (c.tiers || []).map((t) => ({ min: toMajor(t.min), max: toMajor(t.max), fee: toMajor(t.fee) })),
  };
}

function draftToPayload(d) {
  let config = {};
  if (d.fee_type === "FLAT") config = { fee: toMinor(d.flat) || 0 };
  else if (d.fee_type === "PERCENTAGE") {
    config = { percent: parseFloat(d.percent) || 0 };
    if (d.min_fee !== "") config.min_fee = toMinor(d.min_fee);
    if (d.max_fee !== "") config.max_fee = toMinor(d.max_fee);
  } else if (d.fee_type === "TIERED") {
    config = {
      tiers: d.tiers.map((t) => ({
        min: toMinor(t.min) || 0,
        max: t.max === "" ? null : toMinor(t.max),
        fee: toMinor(t.fee) || 0,
      })),
    };
  }
  return { fee_type: d.fee_type, config, active: d.active };
}

export default function BackOffice() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [tab, setTab] = useState("overview");
  const [overview, setOverview] = useState(null);
  const [drafts, setDrafts] = useState({});
  const [services, setServices] = useState([]);
  const [providers, setProviders] = useState([]);
  const [settingsRows, setSettingsRows] = useState([]);
  const [settingsDraft, setSettingsDraft] = useState({});
  const [newProvider, setNewProvider] = useState({ category: "electricity", provider_id: "", name: "" });
  const [msg, setMsg] = useState(null);

  function loadProviders() {
    adminApi.listProviders().then(setProviders).catch(() => {});
  }
  function loadSettings() {
    adminApi.listSettings().then((rows) => {
      setSettingsRows(rows);
      setSettingsDraft(Object.fromEntries(rows.map((s) => [s.key, s.value])));
    }).catch(() => {});
  }

  useEffect(() => {
    if (!user?.is_admin) return;
    adminApi.overview().then(setOverview).catch(() => {});
    adminApi.listFees().then((rows) => {
      const d = {};
      rows.forEach((r) => (d[r.operation] = ruleToDraft(r)));
      setDrafts(d);
    }).catch(() => {});
    adminApi.listServices().then(setServices).catch(() => {});
    loadProviders();
    loadSettings();
  }, [user]);

  if (!user?.is_admin) {
    return (
      <div className="container">
        <div className="card mt"><div className="alert alert-error">Administrator access required.</div>
          <button className="btn-primary mt" onClick={() => navigate("/dashboard")}>Back to dashboard</button>
        </div>
      </div>
    );
  }

  const setDraft = (op, patch) => setDrafts((d) => ({ ...d, [op]: { ...d[op], ...patch } }));

  async function saveFee(op) {
    setMsg(null);
    try {
      await adminApi.updateFee(op, draftToPayload(drafts[op]));
      setMsg(`Saved ${op} fee.`);
    } catch (e) {
      setMsg(e.message);
    }
  }

  async function toggleService(key, enabled) {
    await adminApi.updateService(key, enabled);
    adminApi.listServices().then(setServices).catch(() => {});
  }

  async function toggleProvider(id, enabled) {
    await adminApi.updateProvider(id, { enabled });
    loadProviders();
  }

  async function addProvider(e) {
    e.preventDefault();
    setMsg(null);
    try {
      await adminApi.createProvider(newProvider.category, newProvider.provider_id, newProvider.name);
      setNewProvider({ category: "electricity", provider_id: "", name: "" });
      loadProviders();
      setMsg("Provider added.");
    } catch (err) {
      setMsg(err.message);
    }
  }

  async function saveSettings() {
    setMsg(null);
    try {
      await adminApi.updateSettings(settingsDraft);
      loadSettings();
      setMsg("Settings saved.");
    } catch (err) {
      setMsg(err.message);
    }
  }

  async function sendTestEmail() {
    setMsg(null);
    try {
      const r = await adminApi.emailTest("FinPay Back Office test", "This is a test email.");
      setMsg(r.sent ? `Test email sent to ${r.to} (${r.backend}).` : `Email not sent (backend: ${r.backend}).`);
    } catch (err) {
      setMsg(err.message);
    }
  }

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand"><span className="dot" /> FinPay <span className="muted small">Back Office</span></div>
        <button className="btn-ghost" onClick={() => navigate("/dashboard")}>← Front store</button>
      </div>

      <div className="tabs">
        <button className={`tab ${tab === "overview" ? "active" : ""}`} onClick={() => setTab("overview")}>Overview</button>
        <button className={`tab ${tab === "fees" ? "active" : ""}`} onClick={() => setTab("fees")}>Service fees</button>
        <button className={`tab ${tab === "services" ? "active" : ""}`} onClick={() => setTab("services")}>Features</button>
        <button className={`tab ${tab === "providers" ? "active" : ""}`} onClick={() => setTab("providers")}>Providers</button>
        <button className={`tab ${tab === "settings" ? "active" : ""}`} onClick={() => setTab("settings")}>Settings</button>
      </div>

      {msg && <div className="alert alert-info">{msg}</div>}

      {tab === "overview" && overview && (
        <div className="metric-grid mt">
          <div className="metric"><div className="val">{overview.users}</div><div className="lbl">Users</div></div>
          <div className="metric"><div className="val">{overview.transactions}</div><div className="lbl">Transactions</div></div>
          <div className="metric"><div className="val">{overview.successful_transactions}</div><div className="lbl">Successful</div></div>
          <div className="metric"><div className="val">{money(overview.processed_volume)}</div><div className="lbl">Volume (XAF)</div></div>
          <div className="metric"><div className="val">{money(overview.fees_collected)}</div><div className="lbl">Fees collected (XAF)</div></div>
        </div>
      )}

      {tab === "fees" && (
        <div className="mt">
          {Object.entries(drafts).map(([op, d]) => (
            <div className="card mt" key={op} style={{ maxWidth: 720 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <h2 style={{ margin: 0 }}>{op.replaceAll("_", " ")}</h2>
                <label className="switch"><input type="checkbox" checked={d.active} onChange={(e) => setDraft(op, { active: e.target.checked })} style={{ width: "auto" }} /> Active</label>
              </div>
              <label>Fee model</label>
              <select value={d.fee_type} onChange={(e) => setDraft(op, { fee_type: e.target.value })}>
                <option value="FLAT">Flat</option>
                <option value="PERCENTAGE">Percentage</option>
                <option value="TIERED">Tiered</option>
              </select>

              {d.fee_type === "FLAT" && (
                <>
                  <label>Fee (XAF)</label>
                  <input type="number" min="0" value={d.flat} onChange={(e) => setDraft(op, { flat: e.target.value })} />
                </>
              )}

              {d.fee_type === "PERCENTAGE" && (
                <div className="row">
                  <div><label>Percent (%)</label><input type="number" min="0" step="0.1" value={d.percent} onChange={(e) => setDraft(op, { percent: e.target.value })} /></div>
                  <div><label>Min fee (XAF)</label><input type="number" min="0" value={d.min_fee} onChange={(e) => setDraft(op, { min_fee: e.target.value })} /></div>
                  <div><label>Max fee (XAF)</label><input type="number" min="0" value={d.max_fee} onChange={(e) => setDraft(op, { max_fee: e.target.value })} /></div>
                </div>
              )}

              {d.fee_type === "TIERED" && (
                <div>
                  <label>Tiers (amount range → fee, in XAF)</label>
                  {d.tiers.map((t, i) => (
                    <div className="tier-row" key={i}>
                      <div><span className="muted small">From</span><input type="number" value={t.min} onChange={(e) => setDraft(op, { tiers: d.tiers.map((x, j) => j === i ? { ...x, min: e.target.value } : x) })} /></div>
                      <div><span className="muted small">To (blank = ∞)</span><input type="number" value={t.max} onChange={(e) => setDraft(op, { tiers: d.tiers.map((x, j) => j === i ? { ...x, max: e.target.value } : x) })} /></div>
                      <div><span className="muted small">Fee</span><input type="number" value={t.fee} onChange={(e) => setDraft(op, { tiers: d.tiers.map((x, j) => j === i ? { ...x, fee: e.target.value } : x) })} /></div>
                      <button className="btn-ghost" onClick={() => setDraft(op, { tiers: d.tiers.filter((_, j) => j !== i) })}>✕</button>
                    </div>
                  ))}
                  <button className="btn-ghost mt" onClick={() => setDraft(op, { tiers: [...d.tiers, { min: "", max: "", fee: "" }] })}>+ Add tier</button>
                </div>
              )}

              <div className="mt"><button className="btn-primary" onClick={() => saveFee(op)}>Save {op.replaceAll("_", " ")}</button></div>
            </div>
          ))}
        </div>
      )}

      {tab === "services" && (
        <div className="card mt" style={{ maxWidth: 620 }}>
          <h2>Front-store features</h2>
          {services.map((s) => (
            <div className="txn" key={s.key}>
              <div className="meta">
                <span>{s.label}</span>
                <span className="muted small">{s.kind} · {s.key}</span>
              </div>
              <label className="switch">
                <input type="checkbox" checked={s.enabled} onChange={(e) => toggleService(s.key, e.target.checked)} style={{ width: "auto" }} />
                {s.enabled ? "Enabled" : "Disabled"}
              </label>
            </div>
          ))}
        </div>
      )}

      {tab === "providers" && (
        <div className="grid mt">
          <div className="card">
            <h2>Providers</h2>
            {providers.map((p) => (
              <div className="txn" key={p.id}>
                <div className="meta">
                  <span>{p.name}</span>
                  <span className="muted small">{p.category} · {p.provider_id}</span>
                </div>
                <label className="switch">
                  <input type="checkbox" checked={p.enabled} onChange={(e) => toggleProvider(p.id, e.target.checked)} style={{ width: "auto" }} />
                  {p.enabled ? "Enabled" : "Disabled"}
                </label>
              </div>
            ))}
          </div>
          <div className="card">
            <h2>Add provider</h2>
            <form onSubmit={addProvider}>
              <label>Category</label>
              <select value={newProvider.category} onChange={(e) => setNewProvider({ ...newProvider, category: e.target.value })}>
                <option value="electricity">Electricity</option>
                <option value="airtime">Airtime</option>
                <option value="data">Data</option>
              </select>
              <label>Provider ID (slug)</label>
              <input value={newProvider.provider_id} onChange={(e) => setNewProvider({ ...newProvider, provider_id: e.target.value })} placeholder="e.g. camtel" required />
              <label>Display name</label>
              <input value={newProvider.name} onChange={(e) => setNewProvider({ ...newProvider, name: e.target.value })} placeholder="e.g. CAMTEL" required />
              <div className="mt"><button className="btn-primary">Add provider</button></div>
            </form>
          </div>
        </div>
      )}

      {tab === "settings" && (
        <div className="card mt" style={{ maxWidth: 640 }}>
          <h2>Platform settings</h2>
          {settingsRows.map((s) => (
            <div key={s.key}>
              <label>{s.label || s.key}</label>
              {s.value_type === "bool" ? (
                <label className="switch">
                  <input type="checkbox" checked={String(settingsDraft[s.key]).toLowerCase() === "true"}
                    onChange={(e) => setSettingsDraft({ ...settingsDraft, [s.key]: e.target.checked ? "true" : "false" })}
                    style={{ width: "auto" }} />
                  {String(settingsDraft[s.key]).toLowerCase() === "true" ? "On" : "Off"}
                </label>
              ) : (
                <input
                  type={s.value_type === "int" ? "number" : "text"}
                  value={settingsDraft[s.key] ?? ""}
                  onChange={(e) => setSettingsDraft({ ...settingsDraft, [s.key]: e.target.value })}
                />
              )}
            </div>
          ))}
          <div className="row mt" style={{ maxWidth: 420 }}>
            <button className="btn-primary" onClick={saveSettings}>Save settings</button>
            <button className="btn-ghost" onClick={sendTestEmail}>Send test email</button>
          </div>
          <p className="muted small mt">Limit values are in minor units (÷100 for XAF).</p>
        </div>
      )}
    </div>
  );
}
