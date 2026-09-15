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
  const [msg, setMsg] = useState(null);

  useEffect(() => {
    if (!user?.is_admin) return;
    adminApi.overview().then(setOverview).catch(() => {});
    adminApi.listFees().then((rows) => {
      const d = {};
      rows.forEach((r) => (d[r.operation] = ruleToDraft(r)));
      setDrafts(d);
    }).catch(() => {});
    adminApi.listServices().then(setServices).catch(() => {});
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
    </div>
  );
}
