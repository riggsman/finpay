import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { adminApi } from "../api/admin";
import { useAuth } from "../store/AuthContext";
import KycValidationPanel from "../components/KycValidationPanel";
import Pagination, { usePagination } from "../components/Pagination";

const toMajor = (m) => (m == null ? "" : (Number(m) / 100).toString());
const toMinor = (x) => (x === "" || x == null ? null : Math.round(parseFloat(x) * 100));

const LIMIT_SETTING_KEYS = new Set([
  "default_per_txn_limit",
  "default_daily_limit",
  "kyc_approved_per_txn_limit",
  "kyc_approved_daily_limit",
]);

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

function feeSummary(d) {
  if (!d) return "—";
  if (d.fee_type === "FLAT") {
    return d.flat === "" || d.flat == null ? "Flat —" : `Flat · ${Number(d.flat).toLocaleString()} XAF`;
  }
  if (d.fee_type === "PERCENTAGE") {
    const parts = [`${d.percent || 0}%`];
    if (d.min_fee !== "" && d.min_fee != null) parts.push(`min ${d.min_fee}`);
    if (d.max_fee !== "" && d.max_fee != null) parts.push(`max ${d.max_fee}`);
    return `Percentage · ${parts.join(" · ")}`;
  }
  if (d.fee_type === "TIERED") {
    const n = (d.tiers || []).length;
    return `Tiered · ${n} tier${n === 1 ? "" : "s"}`;
  }
  return d.fee_type || "—";
}

function opLabel(op) {
  return String(op || "").replaceAll("_", " ");
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
  const DEFAULT_PROVIDER_FIELDS = (phoneLabel = "Phone number") => [
    { key: "phone", enabled: true, required: true, label: phoneLabel },
    { key: "amount", enabled: true, required: true, label: "Amount" },
    { key: "message", enabled: false, required: false, label: "Message" },
  ];
  const EMPTY_PROVIDER = {
    category: "electricity",
    category_custom: "",
    provider_id: "",
    name: "",
    description: "",
    flow: "validate_pay",
    integration_mode: "MOCK",
    base_url: "",
    target_label: "Meter number",
    icon: "",
    sort_order: 100,
    fields: DEFAULT_PROVIDER_FIELDS("Meter number"),
    config_text: "{\n  \"api_key_ref\": \"\",\n  \"timeout_seconds\": 30\n}",
    enabled: true,
  };
  const [newProvider, setNewProvider] = useState(EMPTY_PROVIDER);
  const [showNewProvider, setShowNewProvider] = useState(false);
  const [editingProvider, setEditingProvider] = useState(null);
  const [providerFilter, setProviderFilter] = useState("all");
  const [msg, setMsg] = useState(null);

  const [userFilters, setUserFilters] = useState({ user_id: "", phone: "", name: "" });
  const [users, setUsers] = useState([]);
  const [selectedUser, setSelectedUser] = useState(null);
  const [kycStatus, setKycStatus] = useState("");
  const [kycRows, setKycRows] = useState([]);
  const [selectedKyc, setSelectedKyc] = useState(null);
  const [rejectReason, setRejectReason] = useState("");
  const [txnFilters, setTxnFilters] = useState({
    user_id: "", phone: "", account_number: "", direction: "", type: "",
  });
  const [txns, setTxns] = useState([]);
  const [editingFee, setEditingFee] = useState(null);
  const [limitRequests, setLimitRequests] = useState([]);
  const [limitFilter, setLimitFilter] = useState("PENDING");
  const [selectedLimitReq, setSelectedLimitReq] = useState(null);
  const [limitApprove, setLimitApprove] = useState({
    per_txn: "", daily: "", duration_days: "30", spending_cap: "",
  });
  const [limitRejectReason, setLimitRejectReason] = useState("");
  const [campayStatus, setCampayStatus] = useState(null);
  const [campayBalance, setCampayBalance] = useState(null);
  const [campayHolderPhone, setCampayHolderPhone] = useState("");
  const [campayHolder, setCampayHolder] = useState(null);
  const [campayTestPhone, setCampayTestPhone] = useState("");
  const [campayTestAmount, setCampayTestAmount] = useState("100");
  const [campayTestResult, setCampayTestResult] = useState(null);
  const [campayStatusRef, setCampayStatusRef] = useState("");
  const [campayTxnStatus, setCampayTxnStatus] = useState(null);
  const [campayBusy, setCampayBusy] = useState(false);
  const LIST_LIMIT = 500;

  function loadProviders() {
    adminApi.listProviders().then(setProviders).catch(() => {});
  }
  function loadSettings() {
    adminApi.listSettings().then((rows) => {
      setSettingsRows(rows);
      setSettingsDraft(Object.fromEntries(rows.map((s) => [s.key, s.value])));
    }).catch(() => {});
  }

  async function loadUsers(filters = userFilters) {
    const params = { limit: LIST_LIMIT };
    if (filters.user_id) params.user_id = Number(filters.user_id);
    if (filters.phone) params.phone = filters.phone;
    if (filters.name) params.name = filters.name;
    const rows = await adminApi.listUsers(params);
    setUsers(rows);
  }

  async function loadKyc(status = kycStatus) {
    const params = { limit: LIST_LIMIT };
    if (status) params.status = status;
    const rows = await adminApi.listKyc(params);
    setKycRows(rows);
  }

  async function loadTxns(filters = txnFilters) {
    const params = { limit: LIST_LIMIT };
    if (filters.user_id) params.user_id = Number(filters.user_id);
    if (filters.phone) params.phone = filters.phone;
    if (filters.account_number) params.account_number = filters.account_number;
    if (filters.direction) params.direction = filters.direction;
    if (filters.type) params.type = filters.type;
    const rows = await adminApi.listTransactions(params);
    setTxns(rows);
  }

  async function loadLimitRequests(status = limitFilter) {
    const params = {};
    if (status && status !== "ALL") params.status = status;
    const rows = await adminApi.listLimitRequests(params);
    setLimitRequests(rows);
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

  useEffect(() => {
    if (!user?.is_admin) return;
    if (tab === "users") loadUsers().catch((e) => setMsg(e.message));
    if (tab === "kyc") loadKyc().catch((e) => setMsg(e.message));
    if (tab === "transactions") loadTxns().catch((e) => setMsg(e.message));
    if (tab === "limits") loadLimitRequests().catch((e) => setMsg(e.message));
    if (tab === "campay") {
      adminApi.campayStatus().then(setCampayStatus).catch((e) => setMsg(e.message));
    }
  }, [user, tab, limitFilter]);

  if (!user?.is_admin) {
    return (
      <div className="container">
        <div className="card mt">
          <div className="alert alert-error">Administrator access required.</div>
          <button className="btn-primary mt" onClick={() => navigate("/admin/login")}>
            Go to Admin login
          </button>
        </div>
      </div>
    );
  }

  const setDraft = (op, patch) => setDrafts((d) => ({ ...d, [op]: { ...d[op], ...patch } }));

  async function saveFee(op) {
    setMsg(null);
    try {
      await adminApi.updateFee(op, draftToPayload(drafts[op]));
      setMsg(`Saved ${opLabel(op)} fee.`);
    } catch (e) {
      setMsg(e.message);
    }
  }

  async function toggleService(key, patch) {
    await adminApi.updateService(key, patch);
    adminApi.listServices().then(setServices).catch(() => {});
  }

  async function toggleProvider(id, enabled) {
    await adminApi.updateProvider(id, { enabled });
    loadProviders();
  }

  function parseProviderConfig(text) {
    const raw = (text || "").trim();
    if (!raw) return {};
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
      throw new Error("Config must be a JSON object.");
    } catch (err) {
      throw new Error(err.message || "Invalid integration config JSON.");
    }
  }

  function configTextWithoutFields(config) {
    const cfg = { ...(config || {}) };
    delete cfg.fields;
    return JSON.stringify(cfg, null, 2);
  }

  function normalizeFormFields(fields, phoneFallback = "Phone number") {
    const list = Array.isArray(fields) && fields.length
      ? fields
      : DEFAULT_PROVIDER_FIELDS(phoneFallback);
    const byKey = Object.fromEntries(list.map((f) => [f.key, f]));
    return ["phone", "amount", "message"].map((key) => {
      const f = byKey[key] || DEFAULT_PROVIDER_FIELDS(phoneFallback).find((d) => d.key === key);
      return {
        key,
        enabled: f.enabled !== false,
        required: !!f.required,
        label: (f.label || key).trim() || key,
      };
    });
  }

  function setFormField(setter, form, key, patch) {
    setter({
      ...form,
      fields: (form.fields || DEFAULT_PROVIDER_FIELDS()).map((f) =>
        f.key === key ? { ...f, ...patch } : f
      ),
    });
  }

  function resolveCategory(form) {
    if (form.category === "__custom") return (form.category_custom || "").trim();
    return form.category;
  }

  function providerPayload(form) {
    const fields = normalizeFormFields(form.fields, form.target_label || "Phone number");
    const phoneLabel = fields.find((f) => f.key === "phone")?.label || form.target_label || "Phone number";
    const config = parseProviderConfig(form.config_text);
    config.fields = fields;
    return {
      category: resolveCategory(form),
      provider_id: form.provider_id.trim(),
      name: form.name.trim(),
      description: form.description.trim() || null,
      enabled: form.enabled !== false,
      flow: form.flow,
      integration_mode: form.integration_mode,
      base_url: form.base_url.trim() || null,
      target_label: phoneLabel,
      icon: form.icon.trim() || null,
      sort_order: Number(form.sort_order) || 100,
      config,
    };
  }

  function renderFieldsEditor(form, setter) {
    const fields = normalizeFormFields(form.fields, form.target_label || "Phone number");
    return (
      <div className="mt">
        <h3 style={{ margin: "12px 0 6px", fontSize: 15 }}>Form fields</h3>
        <p className="muted small" style={{ margin: "0 0 8px" }}>
          Up to three checkout fields. Disabled fields are hidden on Service Pay. PIN is always separate.
        </p>
        {fields.map((f) => (
          <div
            key={f.key}
            className="row"
            style={{ alignItems: "flex-end", gap: 12, marginBottom: 8, flexWrap: "wrap" }}
          >
            <label className="switch" style={{ minWidth: 110 }}>
              <input
                type="checkbox"
                checked={f.enabled}
                onChange={(e) => setFormField(setter, form, f.key, { enabled: e.target.checked })}
                style={{ width: "auto" }}
              />
              {f.key}
            </label>
            <div style={{ flex: 1, minWidth: 160 }}>
              <label>Label</label>
              <input
                value={f.label}
                disabled={!f.enabled}
                onChange={(e) => {
                  const label = e.target.value;
                  const next = {
                    ...form,
                    fields: (form.fields || []).map((row) =>
                      row.key === f.key ? { ...row, label } : row
                    ),
                  };
                  if (f.key === "phone") next.target_label = label;
                  setter(next);
                }}
              />
            </div>
            <label className="switch" style={{ minWidth: 100 }}>
              <input
                type="checkbox"
                checked={f.required}
                disabled={!f.enabled}
                onChange={(e) => setFormField(setter, form, f.key, { required: e.target.checked })}
                style={{ width: "auto" }}
              />
              Required
            </label>
          </div>
        ))}
      </div>
    );
  }

  async function addProvider(e) {
    e.preventDefault();
    setMsg(null);
    try {
      const body = providerPayload(newProvider);
      await adminApi.createProvider(body);
      setNewProvider(EMPTY_PROVIDER);
      setShowNewProvider(false);
      loadProviders();
      adminApi.listServices().then(setServices).catch(() => {});
      adminApi.listFees().then((rows) => {
        const d = {};
        rows.forEach((r) => (d[r.operation] = ruleToDraft(r)));
        setDrafts(d);
      }).catch(() => {});
      setMsg(`Provider “${body.name}” added under ${body.category}.`);
    } catch (err) {
      setMsg(err.message);
    }
  }

  function openNewProvider() {
    setEditingProvider(null);
    setNewProvider(EMPTY_PROVIDER);
    setShowNewProvider(true);
  }

  function closeNewProvider() {
    setShowNewProvider(false);
    setNewProvider(EMPTY_PROVIDER);
  }

  function startEditProvider(p) {
    setShowNewProvider(false);
    const fields = normalizeFormFields(p.fields, p.target_label || "Phone number");
    setEditingProvider({
      id: p.id,
      name: p.name,
      description: p.description || "",
      enabled: p.enabled,
      flow: p.flow || "direct_topup",
      integration_mode: p.integration_mode || "MOCK",
      base_url: p.base_url || "",
      target_label: fields.find((f) => f.key === "phone")?.label || p.target_label || "",
      icon: p.icon || "",
      sort_order: p.sort_order ?? 100,
      fields,
      config_text: configTextWithoutFields(p.config || {}),
    });
  }

  async function saveEditProvider(e) {
    e.preventDefault();
    if (!editingProvider) return;
    setMsg(null);
    try {
      const fields = normalizeFormFields(editingProvider.fields, editingProvider.target_label);
      const phoneLabel = fields.find((f) => f.key === "phone")?.label || editingProvider.target_label;
      const config = parseProviderConfig(editingProvider.config_text);
      config.fields = fields;
      await adminApi.updateProvider(editingProvider.id, {
        name: editingProvider.name.trim(),
        description: editingProvider.description.trim() || null,
        enabled: editingProvider.enabled,
        flow: editingProvider.flow,
        integration_mode: editingProvider.integration_mode,
        base_url: editingProvider.base_url.trim() || null,
        target_label: phoneLabel,
        icon: editingProvider.icon.trim() || null,
        sort_order: Number(editingProvider.sort_order) || 100,
        config,
      });
      setEditingProvider(null);
      loadProviders();
      setMsg("Provider updated.");
    } catch (err) {
      setMsg(err.message);
    }
  }

  function onCategoryChange(value) {
    const defaults = {
      electricity: { flow: "validate_pay", target_label: "Meter number" },
      airtime: { flow: "direct_topup", target_label: "Phone number" },
      data: { flow: "direct_topup", target_label: "Phone number" },
      water: { flow: "direct_topup", target_label: "Account / meter number" },
      __custom: { flow: "direct_topup", target_label: "Account / phone number" },
    };
    const d = defaults[value] || defaults.__custom;
    setNewProvider((p) => ({
      ...p,
      category: value,
      ...d,
      fields: DEFAULT_PROVIDER_FIELDS(d.target_label),
    }));
  }

  const knownCategories = [...new Set(providers.map((p) => p.category))].sort();
  const filteredProviders = providers.filter(
    (p) => providerFilter === "all" || p.category === providerFilter
  );
  const feeRows = useMemo(() => Object.entries(drafts), [drafts]);
  const usersPage = usePagination(users);
  const kycPage = usePagination(kycRows);
  const limitsPage = usePagination(limitRequests);
  const txnsPage = usePagination(txns);
  const feesPage = usePagination(feeRows);
  const providersPage = usePagination(filteredProviders);

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

  async function openUser(id) {
    setMsg(null);
    try {
      const profile = await adminApi.getUser(id);
      setSelectedUser(profile);
    } catch (err) {
      setMsg(err.message);
    }
  }

  async function approveKyc(id) {
    setMsg(null);
    try {
      await adminApi.approveKyc(id);
      setSelectedKyc(null);
      await loadKyc();
      adminApi.overview().then(setOverview).catch(() => {});
      setMsg("KYC approved.");
    } catch (err) {
      setMsg(err.message);
    }
  }

  async function rejectKyc(id) {
    setMsg(null);
    try {
      await adminApi.rejectKyc(id, rejectReason || undefined);
      setRejectReason("");
      setSelectedKyc(null);
      await loadKyc();
      adminApi.overview().then(setOverview).catch(() => {});
      setMsg("KYC rejected.");
    } catch (err) {
      setMsg(err.message);
    }
  }

  function openLimitRequest(row) {
    setSelectedLimitReq(row);
    setLimitRejectReason("");
    setLimitApprove({
      per_txn: row.requested_per_txn_limit != null ? String(Number(row.requested_per_txn_limit) / 100) : "",
      daily: row.requested_daily_limit != null ? String(Number(row.requested_daily_limit) / 100) : "",
      duration_days: "30",
      spending_cap: "",
    });
  }

  async function approveLimitRequest() {
    if (!selectedLimitReq) return;
    setMsg(null);
    try {
      const body = {
        duration_days: Number(limitApprove.duration_days) || 30,
      };
      if (limitApprove.per_txn !== "") body.approved_per_txn_limit = toMinor(limitApprove.per_txn);
      if (limitApprove.daily !== "") body.approved_daily_limit = toMinor(limitApprove.daily);
      if (limitApprove.spending_cap !== "") body.spending_cap = toMinor(limitApprove.spending_cap);
      await adminApi.approveLimitRequest(selectedLimitReq.id, body);
      setSelectedLimitReq(null);
      await loadLimitRequests();
      setMsg("Limit increase approved.");
    } catch (err) {
      setMsg(err.message);
    }
  }

  async function rejectLimitRequest() {
    if (!selectedLimitReq) return;
    setMsg(null);
    try {
      await adminApi.rejectLimitRequest(selectedLimitReq.id, limitRejectReason || undefined);
      setSelectedLimitReq(null);
      setLimitRejectReason("");
      await loadLimitRequests();
      setMsg("Limit increase rejected.");
    } catch (err) {
      setMsg(err.message);
    }
  }

  return (
    <div className={`container${tab === "providers" ? " container--providers" : ""}`}>
      <div className="topbar">
        <div className="brand"><span className="dot" /> FinPay <span className="muted small">Back Office</span></div>
        <button className="btn-ghost" onClick={() => navigate("/dashboard")}>← Front store</button>
      </div>

      <div className="tabs">
        <button className={`tab ${tab === "overview" ? "active" : ""}`} onClick={() => setTab("overview")}>Overview</button>
        <button className={`tab ${tab === "users" ? "active" : ""}`} onClick={() => setTab("users")}>Users</button>
        <button className={`tab ${tab === "kyc" ? "active" : ""}`} onClick={() => setTab("kyc")}>KYC</button>
        <button className={`tab ${tab === "limits" ? "active" : ""}`} onClick={() => setTab("limits")}>Limit requests</button>
        <button className={`tab ${tab === "transactions" ? "active" : ""}`} onClick={() => setTab("transactions")}>Transactions</button>
        <button className={`tab ${tab === "fees" ? "active" : ""}`} onClick={() => setTab("fees")}>Service fees</button>
        <button className={`tab ${tab === "services" ? "active" : ""}`} onClick={() => setTab("services")}>Features</button>
        <button className={`tab ${tab === "providers" ? "active" : ""}`} onClick={() => setTab("providers")}>Providers</button>
        <button className={`tab ${tab === "campay" ? "active" : ""}`} onClick={() => setTab("campay")}>Campay</button>
        <button className={`tab ${tab === "settings" ? "active" : ""}`} onClick={() => setTab("settings")}>Settings</button>
      </div>

      {msg && <div className="alert alert-info">{msg}</div>}

      {tab === "overview" && overview && (
        <div className="metric-grid mt">
          <div className="metric"><div className="val">{overview.users}</div><div className="lbl">Users</div></div>
          <div className="metric"><div className="val">{overview.pending_kyc ?? 0}</div><div className="lbl">Pending KYC</div></div>
          <div className="metric"><div className="val">{overview.transactions}</div><div className="lbl">Transactions</div></div>
          <div className="metric"><div className="val">{overview.successful_transactions}</div><div className="lbl">Successful</div></div>
          <div className="metric"><div className="val">{money(overview.processed_volume)}</div><div className="lbl">Volume (XAF)</div></div>
          <div className="metric"><div className="val">{money(overview.fees_collected)}</div><div className="lbl">Fees collected (XAF)</div></div>
        </div>
      )}

      {tab === "users" && (
        <div className="users-admin-layout mt">
          <div className="card">
            <h2>Users</h2>
            <form
              className="filters"
              onSubmit={(e) => {
                e.preventDefault();
                setSelectedUser(null);
                loadUsers().catch((err) => setMsg(err.message));
              }}
            >
              <div className="filter-grid">
                <div>
                  <label>User ID</label>
                  <input value={userFilters.user_id} onChange={(e) => setUserFilters({ ...userFilters, user_id: e.target.value })} placeholder="e.g. 12" />
                </div>
                <div>
                  <label>Phone</label>
                  <input value={userFilters.phone} onChange={(e) => setUserFilters({ ...userFilters, phone: e.target.value })} placeholder="+237…" />
                </div>
                <div>
                  <label>Name</label>
                  <input value={userFilters.name} onChange={(e) => setUserFilters({ ...userFilters, name: e.target.value })} placeholder="First or last name" />
                </div>
              </div>
              <div className="row mt" style={{ maxWidth: 280 }}>
                <button className="btn-primary">Search</button>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => {
                    const empty = { user_id: "", phone: "", name: "" };
                    setUserFilters(empty);
                    setSelectedUser(null);
                    loadUsers(empty).catch((err) => setMsg(err.message));
                  }}
                >
                  Reset
                </button>
              </div>
            </form>

            <div className="mt">
              {users.length === 0 ? (
                <div className="empty">No users match these filters.</div>
              ) : (
                <>
                  {usersPage.pageItems.map((u) => (
                    <div
                      className={`txn clickable ${selectedUser?.id === u.id ? "selected" : ""}`}
                      key={u.id}
                      onClick={() => openUser(u.id)}
                    >
                      <div className="meta">
                        <span>{u.full_name || `${u.first_name || ""} ${u.last_name || ""}`.trim() || "—"}</span>
                        <span className="muted small">#{u.id} · {u.phone} · {u.account_number || "no acct"}</span>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <span className={`badge ${u.status}`}>{u.status}</span>
                        <div className="muted small">{u.kyc_status || "NO_KYC"}</div>
                      </div>
                    </div>
                  ))}
                  <Pagination
                    page={usersPage.page}
                    totalPages={usersPage.totalPages}
                    total={usersPage.total}
                    pageSize={usersPage.pageSize}
                    onChange={usersPage.setPage}
                  />
                </>
              )}
            </div>
          </div>

          <div className="card users-profile-card">
            <h2>User profile</h2>
            {!selectedUser ? (
              <p className="muted">Select a user to view full profile and statuses.</p>
            ) : (
              <>
                <div className="review-row"><span className="muted">User ID</span><span>{selectedUser.id}</span></div>
                <div className="review-row"><span className="muted">Name</span><span>{selectedUser.full_name || "—"}</span></div>
                <div className="review-row"><span className="muted">Phone</span><span>{selectedUser.phone}</span></div>
                <div className="review-row"><span className="muted">Email</span><span>{selectedUser.email || "—"}</span></div>
                <div className="review-row"><span className="muted">Account</span><span>{selectedUser.account_number || "—"}</span></div>
                <div className="review-row"><span className="muted">User status</span><span className={`badge ${selectedUser.status}`}>{selectedUser.status}</span></div>
                <div className="review-row"><span className="muted">Phone verified</span><span>{selectedUser.phone_verified ? "Yes" : "No"}</span></div>
                <div className="review-row"><span className="muted">Email verified</span><span>{selectedUser.email_verified ? "Yes" : "No"}</span></div>
                <div className="review-row"><span className="muted">Per-txn limit</span><span>{money(selectedUser.per_txn_limit)} XAF</span></div>
                <div className="review-row"><span className="muted">Daily limit</span><span>{money(selectedUser.daily_limit)} XAF</span></div>
                <div className="review-row"><span className="muted">Wallet</span><span>{selectedUser.wallet ? `${money(selectedUser.wallet.balance)} ${selectedUser.wallet.currency}` : "—"}</span></div>
                <div className="review-row"><span className="muted">KYC status</span><span>{selectedUser.kyc?.status || "NOT_STARTED"}</span></div>
                {selectedUser.kyc && (
                  <>
                    <div className="review-row"><span className="muted">KYC name</span><span>{selectedUser.kyc.first_name} {selectedUser.kyc.last_name}</span></div>
                    <div className="review-row"><span className="muted">ID</span><span>{selectedUser.kyc.id_type} · {selectedUser.kyc.id_number}</span></div>
                    <div className="review-row"><span className="muted">Address</span><span>{selectedUser.kyc.address_line}, {selectedUser.kyc.city}, {selectedUser.kyc.country}</span></div>
                    {selectedUser.kyc.rejection_reason && (
                      <div className="review-row"><span className="muted">Rejection</span><span>{selectedUser.kyc.rejection_reason}</span></div>
                    )}
                  </>
                )}
                <div className="row mt" style={{ maxWidth: 360 }}>
                  <button
                    className="btn-ghost"
                    onClick={() => {
                      setTxnFilters({
                        user_id: String(selectedUser.id),
                        phone: "",
                        account_number: "",
                        direction: "",
                        type: "",
                      });
                      setTab("transactions");
                    }}
                  >
                    View transactions
                  </button>
                  <button className="btn-ghost" onClick={() => setSelectedUser(null)}>Close</button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {tab === "kyc" && (
        <div className="kyc-admin-layout mt">
          <div className="card">
            <h2>KYC queue</h2>
            <div className="row" style={{ maxWidth: 420, alignItems: "end" }}>
              <div style={{ flex: 1 }}>
                <label>Status</label>
                <select
                  value={kycStatus}
                  onChange={(e) => {
                    setKycStatus(e.target.value);
                    setSelectedKyc(null);
                    loadKyc(e.target.value).catch((err) => setMsg(err.message));
                  }}
                >
                  <option value="">All statuses</option>
                  <option value="UNDER_REVIEW">Under review</option>
                  <option value="APPROVED">Approved</option>
                  <option value="REJECTED">Rejected</option>
                  <option value="IN_PROGRESS">In progress</option>
                  <option value="NOT_STARTED">Not started</option>
                </select>
              </div>
              <button className="btn-ghost" type="button" onClick={() => loadKyc().catch((err) => setMsg(err.message))}>Refresh</button>
            </div>

            <div className="mt">
              {kycRows.length === 0 ? (
                <div className="empty">No KYC submissions for this status.</div>
              ) : (
                <>
                  {kycPage.pageItems.map((k) => (
                    <div
                      className={`txn clickable ${selectedKyc?.id === k.id ? "selected" : ""}`}
                      key={k.id}
                      onClick={() => { setSelectedKyc(k); setRejectReason(""); }}
                    >
                      <div className="meta">
                        <span>{k.first_name} {k.last_name}</span>
                        <span className="muted small">KYC #{k.id} · user #{k.user_id} · {k.user_phone}</span>
                      </div>
                      <span className={`badge ${k.status}`}>{k.status}</span>
                    </div>
                  ))}
                  <Pagination
                    page={kycPage.page}
                    totalPages={kycPage.totalPages}
                    total={kycPage.total}
                    pageSize={kycPage.pageSize}
                    onChange={kycPage.setPage}
                  />
                </>
              )}
            </div>
          </div>

          <div className="card kyc-validation-card">
            <h2>Validation workspace</h2>
            <KycValidationPanel
              kyc={selectedKyc}
              rejectReason={rejectReason}
              setRejectReason={setRejectReason}
              onApprove={approveKyc}
              onReject={rejectKyc}
            />
          </div>
        </div>
      )}

      {tab === "limits" && (
        <div className="kyc-admin-layout mt">
          <div className="card">
            <h2>Limit increase requests</h2>
            <p className="muted small">Review temporary raises separately from KYC. Defaults are configured in Settings (500,000 XAF).</p>
            <div className="row" style={{ maxWidth: 420, alignItems: "end" }}>
              <div style={{ flex: 1 }}>
                <label>Status</label>
                <select
                  value={limitFilter}
                  onChange={(e) => {
                    setLimitFilter(e.target.value);
                    setSelectedLimitReq(null);
                  }}
                >
                  <option value="PENDING">Pending</option>
                  <option value="APPROVED">Approved</option>
                  <option value="REJECTED">Rejected</option>
                  <option value="EXPIRED">Expired</option>
                  <option value="EXHAUSTED">Exhausted</option>
                  <option value="ALL">All</option>
                </select>
              </div>
              <button className="btn-ghost" type="button" onClick={() => loadLimitRequests().catch((err) => setMsg(err.message))}>Refresh</button>
            </div>

            {limitRequests.length === 0 ? (
              <div className="empty mt">No requests for this filter.</div>
            ) : (
              <>
                <div className="table-wrap mt">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>User</th>
                        <th>Requested</th>
                        <th>Status</th>
                        <th>Submitted</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {limitsPage.pageItems.map((r) => (
                        <tr key={r.id} className={selectedLimitReq?.id === r.id ? "is-active" : ""}>
                          <td>
                            <strong>{r.user_name || `User #${r.user_id}`}</strong>
                            <div className="muted small">{r.user_phone}</div>
                          </td>
                          <td>
                            {money(r.requested_per_txn_limit)} / {money(r.requested_daily_limit)} XAF
                          </td>
                          <td><span className={`badge ${r.status === "APPROVED" ? "SUCCESS" : r.status === "REJECTED" ? "FAILED" : "PENDING"}`}>{r.status}</span></td>
                          <td className="muted small">{new Date(r.created_at).toLocaleString()}</td>
                          <td>
                            <button type="button" className="btn-ghost" onClick={() => openLimitRequest(r)}>Review</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination
                  page={limitsPage.page}
                  totalPages={limitsPage.totalPages}
                  total={limitsPage.total}
                  pageSize={limitsPage.pageSize}
                  onChange={limitsPage.setPage}
                />
              </>
            )}
          </div>

          <div className="card">
            {!selectedLimitReq ? (
              <div className="empty">Select a request to approve or reject.</div>
            ) : (
              <>
                <h2>Review request #{selectedLimitReq.id}</h2>
                <div className="review-row"><span className="muted">User</span><span>{selectedLimitReq.user_name} ({selectedLimitReq.user_phone})</span></div>
                <div className="review-row"><span className="muted">Requested per-txn</span><span>{money(selectedLimitReq.requested_per_txn_limit)} XAF</span></div>
                <div className="review-row"><span className="muted">Requested daily</span><span>{money(selectedLimitReq.requested_daily_limit)} XAF</span></div>
                <div className="review-row"><span className="muted">Reason</span><span>{selectedLimitReq.reason || "—"}</span></div>
                <div className="review-row"><span className="muted">Status</span><span>{selectedLimitReq.status}</span></div>

                {selectedLimitReq.status === "PENDING" ? (
                  <>
                    <label className="mt">Approve per-txn (XAF)</label>
                    <input type="number" step="0.01" value={limitApprove.per_txn} onChange={(e) => setLimitApprove({ ...limitApprove, per_txn: e.target.value })} />
                    <label>Approve daily (XAF)</label>
                    <input type="number" step="0.01" value={limitApprove.daily} onChange={(e) => setLimitApprove({ ...limitApprove, daily: e.target.value })} />
                    <label>Duration (days)</label>
                    <input type="number" min="1" max="365" value={limitApprove.duration_days} onChange={(e) => setLimitApprove({ ...limitApprove, duration_days: e.target.value })} />
                    <label>Spending allowance (XAF, optional)</label>
                    <input type="number" step="0.01" value={limitApprove.spending_cap} onChange={(e) => setLimitApprove({ ...limitApprove, spending_cap: e.target.value })} placeholder="Leave blank for duration-only" />
                    <div className="row mt">
                      <button type="button" className="btn-primary" onClick={approveLimitRequest}>Approve raise</button>
                    </div>
                    <label className="mt">Rejection reason</label>
                    <textarea rows={3} value={limitRejectReason} onChange={(e) => setLimitRejectReason(e.target.value)} />
                    <div className="row mt">
                      <button type="button" className="btn-ghost" onClick={rejectLimitRequest}>Reject</button>
                    </div>
                  </>
                ) : (
                  <p className="muted small mt">This request is already {selectedLimitReq.status.toLowerCase()}.</p>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {tab === "transactions" && (
        <div className="card mt">
          <h2>Transactions</h2>
          <form
            className="filters"
            onSubmit={(e) => {
              e.preventDefault();
              loadTxns().catch((err) => setMsg(err.message));
            }}
          >
            <div className="filter-grid">
              <div>
                <label>User ID</label>
                <input value={txnFilters.user_id} onChange={(e) => setTxnFilters({ ...txnFilters, user_id: e.target.value })} />
              </div>
              <div>
                <label>Phone</label>
                <input value={txnFilters.phone} onChange={(e) => setTxnFilters({ ...txnFilters, phone: e.target.value })} />
              </div>
              <div>
                <label>Account number</label>
                <input value={txnFilters.account_number} onChange={(e) => setTxnFilters({ ...txnFilters, account_number: e.target.value })} placeholder="FP00000012" />
              </div>
              <div>
                <label>Direction</label>
                <select value={txnFilters.direction} onChange={(e) => setTxnFilters({ ...txnFilters, direction: e.target.value })}>
                  <option value="">All</option>
                  <option value="IN">Money in</option>
                  <option value="OUT">Money out</option>
                </select>
              </div>
              <div>
                <label>Type</label>
                <input value={txnFilters.type} onChange={(e) => setTxnFilters({ ...txnFilters, type: e.target.value })} placeholder="ADD_MONEY, SEND_MONEY…" />
              </div>
            </div>
            <div className="row mt" style={{ maxWidth: 280 }}>
              <button className="btn-primary">Apply filters</button>
              <button
                type="button"
                className="btn-ghost"
                onClick={() => {
                  const empty = { user_id: "", phone: "", account_number: "", direction: "", type: "" };
                  setTxnFilters(empty);
                  loadTxns(empty).catch((err) => setMsg(err.message));
                }}
              >
                Reset
              </button>
            </div>
          </form>

          <div className="mt">
            {txns.length === 0 ? (
              <div className="empty">No transactions match these filters.</div>
            ) : (
              <>
                <div className="table-wrap">
                  <table className="data-table txn-admin-table">
                    <thead>
                      <tr>
                        <th>ID</th>
                        <th>Date</th>
                        <th>Dir</th>
                        <th>Type</th>
                        <th>Sender</th>
                        <th>Receiver</th>
                        <th>User</th>
                        <th>Phone</th>
                        <th>Account</th>
                        <th>Reference</th>
                        <th>Status</th>
                        <th className="num">Amount</th>
                        <th className="num">Fee</th>
                      </tr>
                    </thead>
                    <tbody>
                      {txnsPage.pageItems.map((t) => (
                        <tr key={t.id}>
                          <td className="mono">#{t.id}</td>
                          <td className="nowrap">{new Date(t.created_at).toLocaleString()}</td>
                          <td>
                            <span className={`dir-pill ${t.direction === "IN" ? "in" : "out"}`}>
                              {t.direction === "IN" ? "IN" : "OUT"}
                            </span>
                          </td>
                          <td className="nowrap">{t.type.replaceAll("_", " ")}</td>
                          <td className="party-cell" title={t.sender || ""}>{t.sender || "—"}</td>
                          <td className="party-cell" title={t.receiver || ""}>{t.receiver || "—"}</td>
                          <td className="mono">#{t.user_id}</td>
                          <td className="nowrap">{t.user_phone || "—"}</td>
                          <td className="mono nowrap">{t.account_number || "—"}</td>
                          <td className="mono ref-cell" title={t.reference}>{t.reference}</td>
                          <td><span className={`badge ${t.status}`}>{t.status}</span></td>
                          <td className={`num amt ${t.direction === "IN" ? "in" : "out"}`}>
                            {t.direction === "IN" ? "+" : "−"}{money(t.amount)} {t.currency}
                          </td>
                          <td className="num muted">{t.fee > 0 ? money(t.fee) : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination
                  page={txnsPage.page}
                  totalPages={txnsPage.totalPages}
                  total={txnsPage.total}
                  pageSize={txnsPage.pageSize}
                  onChange={txnsPage.setPage}
                />
              </>
            )}
          </div>
        </div>
      )}

      {tab === "fees" && (
        <div className="mt fee-config-layout">
          <div className="card">
            <h2>Service fees</h2>
            <p className="muted small">
              Overview of fee rules by operation. Use Configure to open the editor for a specific service.
            </p>
            {Object.keys(drafts).length === 0 ? (
              <div className="empty mt">No fee rules loaded.</div>
            ) : (
              <>
                <div className="table-wrap mt">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>Operation</th>
                        <th>Model</th>
                        <th>Summary</th>
                        <th>Status</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {feesPage.pageItems.map(([op, d]) => (
                        <tr key={op} className={editingFee === op ? "is-active" : ""}>
                          <td>
                            <strong className="fee-op-name">{opLabel(op)}</strong>
                            <div className="muted small mono">{op}</div>
                          </td>
                          <td>{d.fee_type}</td>
                          <td>{feeSummary(d)}</td>
                          <td>
                            <span className={`badge ${d.active ? "SUCCESS" : "FAILED"}`}>
                              {d.active ? "Active" : "Inactive"}
                            </span>
                          </td>
                          <td>
                            <div className="table-actions">
                              <button
                                type="button"
                                className="btn-ghost"
                                onClick={() => setEditingFee(op)}
                              >
                                Configure
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination
                  page={feesPage.page}
                  totalPages={feesPage.totalPages}
                  total={feesPage.total}
                  pageSize={feesPage.pageSize}
                  onChange={feesPage.setPage}
                />
              </>
            )}
          </div>

          {editingFee && drafts[editingFee] && (
            <div className="card fee-editor-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <div>
                  <div className="muted small">Configuring</div>
                  <h2 style={{ margin: 0 }}>{opLabel(editingFee)}</h2>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <label className="switch">
                    <input
                      type="checkbox"
                      checked={drafts[editingFee].active}
                      onChange={(e) => setDraft(editingFee, { active: e.target.checked })}
                      style={{ width: "auto" }}
                    />
                    Active
                  </label>
                  <button type="button" className="btn-ghost" onClick={() => setEditingFee(null)}>Close</button>
                </div>
              </div>

              <label>Fee model</label>
              <select
                value={drafts[editingFee].fee_type}
                onChange={(e) => setDraft(editingFee, { fee_type: e.target.value })}
              >
                <option value="FLAT">Flat</option>
                <option value="PERCENTAGE">Percentage</option>
                <option value="TIERED">Tiered</option>
              </select>

              {drafts[editingFee].fee_type === "FLAT" && (
                <>
                  <label>Fee (XAF)</label>
                  <input
                    type="number"
                    min="0"
                    value={drafts[editingFee].flat}
                    onChange={(e) => setDraft(editingFee, { flat: e.target.value })}
                  />
                </>
              )}

              {drafts[editingFee].fee_type === "PERCENTAGE" && (
                <div className="row">
                  <div>
                    <label>Percent (%)</label>
                    <input
                      type="number"
                      min="0"
                      step="0.1"
                      value={drafts[editingFee].percent}
                      onChange={(e) => setDraft(editingFee, { percent: e.target.value })}
                    />
                  </div>
                  <div>
                    <label>Min fee (XAF)</label>
                    <input
                      type="number"
                      min="0"
                      value={drafts[editingFee].min_fee}
                      onChange={(e) => setDraft(editingFee, { min_fee: e.target.value })}
                    />
                  </div>
                  <div>
                    <label>Max fee (XAF)</label>
                    <input
                      type="number"
                      min="0"
                      value={drafts[editingFee].max_fee}
                      onChange={(e) => setDraft(editingFee, { max_fee: e.target.value })}
                    />
                  </div>
                </div>
              )}

              {drafts[editingFee].fee_type === "TIERED" && (
                <div>
                  <label>Tiers (amount range → fee, in XAF)</label>
                  {drafts[editingFee].tiers.map((t, i) => (
                    <div className="tier-row" key={i}>
                      <div>
                        <span className="muted small">From</span>
                        <input
                          type="number"
                          value={t.min}
                          onChange={(e) => setDraft(editingFee, {
                            tiers: drafts[editingFee].tiers.map((x, j) =>
                              j === i ? { ...x, min: e.target.value } : x
                            ),
                          })}
                        />
                      </div>
                      <div>
                        <span className="muted small">To (blank = ∞)</span>
                        <input
                          type="number"
                          value={t.max}
                          onChange={(e) => setDraft(editingFee, {
                            tiers: drafts[editingFee].tiers.map((x, j) =>
                              j === i ? { ...x, max: e.target.value } : x
                            ),
                          })}
                        />
                      </div>
                      <div>
                        <span className="muted small">Fee</span>
                        <input
                          type="number"
                          value={t.fee}
                          onChange={(e) => setDraft(editingFee, {
                            tiers: drafts[editingFee].tiers.map((x, j) =>
                              j === i ? { ...x, fee: e.target.value } : x
                            ),
                          })}
                        />
                      </div>
                      <button
                        type="button"
                        className="btn-ghost"
                        onClick={() => setDraft(editingFee, {
                          tiers: drafts[editingFee].tiers.filter((_, j) => j !== i),
                        })}
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    className="btn-ghost mt"
                    onClick={() => setDraft(editingFee, {
                      tiers: [...drafts[editingFee].tiers, { min: "", max: "", fee: "" }],
                    })}
                  >
                    + Add tier
                  </button>
                </div>
              )}

              <div className="row mt" style={{ maxWidth: 360 }}>
                <button type="button" className="btn-primary" onClick={() => saveFee(editingFee)}>
                  Save {opLabel(editingFee)}
                </button>
                <button type="button" className="btn-ghost" onClick={() => setEditingFee(null)}>
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {tab === "services" && (
        <div className="card mt">
          <h2>Features &amp; email alerts</h2>
          <p className="muted small">
            Turn a feature on for the front-store, and choose whether users get email
            for that service’s deposits, payments, and related alerts.
            Funding flags (<code>funding_card</code>, <code>funding_bank</code>,{" "}
            <code>funding_mobile_money</code>) control which Add Money methods appear in the app.
          </p>
          {services.length === 0 ? (
            <div className="empty mt">No features configured.</div>
          ) : (
            <div className="table-wrap mt">
              <table className="data-table features-admin-table">
                <thead>
                  <tr>
                    <th>Label</th>
                    <th>Key</th>
                    <th>Kind</th>
                    <th>Feature</th>
                    <th>Email alerts</th>
                  </tr>
                </thead>
                <tbody>
                  {services.map((s) => (
                    <tr key={s.key}>
                      <td><strong>{s.label}</strong></td>
                      <td className="mono">{s.key}</td>
                      <td className="nowrap">
                        <span className="badge">{s.kind}</span>
                      </td>
                      <td>
                        {s.kind === "notification" ? (
                          <span className="muted small">N/A</span>
                        ) : (
                          <label className="switch table-switch">
                            <input
                              type="checkbox"
                              checked={!!s.enabled}
                              onChange={(e) => toggleService(s.key, { enabled: e.target.checked })}
                              style={{ width: "auto" }}
                            />
                            {s.enabled ? "On" : "Off"}
                          </label>
                        )}
                      </td>
                      <td>
                        <label className="switch table-switch">
                          <input
                            type="checkbox"
                            checked={s.email_enabled !== false}
                            onChange={(e) => toggleService(s.key, { email_enabled: e.target.checked })}
                            style={{ width: "auto" }}
                          />
                          {s.email_enabled !== false ? "On" : "Off"}
                        </label>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {tab === "providers" && (
        <div className="mt">
          <div className="fee-config-layout">
            <div className="card">
              <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", flexWrap: "wrap" }}>
                <div>
                  <h2 style={{ margin: 0 }}>Providers</h2>
                  <p className="muted small" style={{ margin: "6px 0 0" }}>
                    Overview of integrators. Use Configure to edit a provider’s settings.
                  </p>
                </div>
                <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  <select value={providerFilter} onChange={(e) => setProviderFilter(e.target.value)} style={{ maxWidth: 180 }}>
                    <option value="all">All categories</option>
                    {knownCategories.map((c) => (
                      <option key={c} value={c}>{c}</option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={openNewProvider}
                  >
                    + New provider
                  </button>
                </div>
              </div>

              {filteredProviders.length === 0 ? (
                <div className="empty mt">No providers in this filter.</div>
              ) : (
                <>
                  <div className="table-wrap mt">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>Provider</th>
                          <th>Category</th>
                          <th>Flow</th>
                          <th>Mode</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {providersPage.pageItems.map((p) => (
                          <tr key={p.id} className={editingProvider?.id === p.id ? "is-active" : ""}>
                            <td>
                              <strong>{p.icon ? `${p.icon} ` : ""}{p.name}</strong>
                              <div className="muted small mono">{p.provider_id}</div>
                            </td>
                            <td>{p.category}</td>
                            <td>{p.flow === "validate_pay" ? "Validate then pay" : "Direct top-up"}</td>
                            <td>{p.integration_mode}</td>
                            <td>
                              <span className={`badge ${p.enabled ? "SUCCESS" : "FAILED"}`}>
                                {p.enabled ? "On" : "Off"}
                              </span>
                            </td>
                            <td>
                              <div className="table-actions">
                                <button type="button" className="btn-ghost" onClick={() => startEditProvider(p)}>
                                  Configure
                                </button>
                                <label className="switch">
                                  <input
                                    type="checkbox"
                                    checked={p.enabled}
                                    onChange={(e) => toggleProvider(p.id, e.target.checked)}
                                    style={{ width: "auto" }}
                                  />
                                </label>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <Pagination
                    page={providersPage.page}
                    totalPages={providersPage.totalPages}
                    total={providersPage.total}
                    pageSize={providersPage.pageSize}
                    onChange={providersPage.setPage}
                  />
                </>
              )}
            </div>

            {editingProvider && (
              <div className="card fee-editor-card">
                <form onSubmit={saveEditProvider}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <div>
                      <div className="muted small">Configuring</div>
                      <h2 style={{ margin: 0 }}>{editingProvider.name || "Provider"}</h2>
                    </div>
                    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                      <label className="switch">
                        <input
                          type="checkbox"
                          checked={editingProvider.enabled}
                          onChange={(e) => setEditingProvider({ ...editingProvider, enabled: e.target.checked })}
                          style={{ width: "auto" }}
                        />
                        Active
                      </label>
                      <button type="button" className="btn-ghost" onClick={() => setEditingProvider(null)}>Close</button>
                    </div>
                  </div>

                  <label>Display name</label>
                  <input value={editingProvider.name} onChange={(e) => setEditingProvider({ ...editingProvider, name: e.target.value })} required />
                  <label>Description</label>
                  <input value={editingProvider.description} onChange={(e) => setEditingProvider({ ...editingProvider, description: e.target.value })} />
                  <div className="row">
                    <div>
                      <label>Payment flow</label>
                      <select value={editingProvider.flow} onChange={(e) => setEditingProvider({ ...editingProvider, flow: e.target.value })}>
                        <option value="validate_pay">Validate then pay</option>
                        <option value="direct_topup">Direct top-up</option>
                      </select>
                    </div>
                    <div>
                      <label>Integration mode</label>
                      <select value={editingProvider.integration_mode} onChange={(e) => setEditingProvider({ ...editingProvider, integration_mode: e.target.value })}>
                        <option value="MOCK">MOCK (simulated)</option>
                        <option value="HTTP">HTTP (external API)</option>
                      </select>
                    </div>
                  </div>
                  <label>API base URL</label>
                  <input value={editingProvider.base_url} onChange={(e) => setEditingProvider({ ...editingProvider, base_url: e.target.value })} placeholder="https://api.provider.example/v1" />
                  {renderFieldsEditor(editingProvider, setEditingProvider)}
                  <div className="row">
                    <div>
                      <label>Icon</label>
                      <input value={editingProvider.icon} onChange={(e) => setEditingProvider({ ...editingProvider, icon: e.target.value })} placeholder="⚡" />
                    </div>
                    <div>
                      <label>Sort order</label>
                      <input type="number" value={editingProvider.sort_order} onChange={(e) => setEditingProvider({ ...editingProvider, sort_order: e.target.value })} />
                    </div>
                  </div>
                  <label>Integration config (JSON)</label>
                  <textarea
                    className="provider-config"
                    rows={6}
                    value={editingProvider.config_text}
                    onChange={(e) => setEditingProvider({ ...editingProvider, config_text: e.target.value })}
                  />
                  <div className="row mt" style={{ maxWidth: 360 }}>
                    <button className="btn-primary">Save changes</button>
                    <button type="button" className="btn-ghost" onClick={() => setEditingProvider(null)}>Cancel</button>
                  </div>
                </form>
              </div>
            )}
          </div>

          {showNewProvider && (
            <div className="card mt">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                <div>
                  <h2 style={{ margin: 0 }}>New provider</h2>
                  <p className="muted small" style={{ margin: "6px 0 0" }}>
                    Register a new integrator for an existing or custom category. A matching front-store service tile and fee rule are created automatically.
                  </p>
                </div>
                <button type="button" className="btn-ghost" onClick={closeNewProvider}>Close</button>
              </div>
              <form onSubmit={addProvider} className="mt">
                <label>Category</label>
                <select value={newProvider.category} onChange={(e) => onCategoryChange(e.target.value)}>
                  <option value="electricity">electricity</option>
                  <option value="airtime">airtime</option>
                  <option value="data">data</option>
                  <option value="water">water</option>
                  {knownCategories.filter((c) => !["electricity", "airtime", "data", "water"].includes(c)).map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                  <option value="__custom">Custom category…</option>
                </select>
                {newProvider.category === "__custom" && (
                  <>
                    <label>Custom category slug</label>
                    <input
                      value={newProvider.category_custom}
                      onChange={(e) => setNewProvider({ ...newProvider, category_custom: e.target.value })}
                      placeholder="e.g. cable_tv"
                      required
                    />
                  </>
                )}
                <label>Provider ID (slug)</label>
                <input value={newProvider.provider_id} onChange={(e) => setNewProvider({ ...newProvider, provider_id: e.target.value })} placeholder="e.g. camtel" required />
                <label>Display name</label>
                <input value={newProvider.name} onChange={(e) => setNewProvider({ ...newProvider, name: e.target.value })} placeholder="e.g. CAMTEL" required />
                <label>Description</label>
                <input value={newProvider.description} onChange={(e) => setNewProvider({ ...newProvider, description: e.target.value })} placeholder="Optional short note" />
                <div className="row">
                  <div>
                    <label>Payment flow</label>
                    <select value={newProvider.flow} onChange={(e) => setNewProvider({ ...newProvider, flow: e.target.value })}>
                      <option value="validate_pay">Validate then pay</option>
                      <option value="direct_topup">Direct top-up</option>
                    </select>
                  </div>
                  <div>
                    <label>Integration mode</label>
                    <select value={newProvider.integration_mode} onChange={(e) => setNewProvider({ ...newProvider, integration_mode: e.target.value })}>
                      <option value="MOCK">MOCK</option>
                      <option value="HTTP">HTTP</option>
                    </select>
                  </div>
                </div>
                <label>API base URL</label>
                <input value={newProvider.base_url} onChange={(e) => setNewProvider({ ...newProvider, base_url: e.target.value })} placeholder="Required when mode is HTTP" />
                {renderFieldsEditor(newProvider, setNewProvider)}
                <div className="row">
                  <div>
                    <label>Icon</label>
                    <input value={newProvider.icon} onChange={(e) => setNewProvider({ ...newProvider, icon: e.target.value })} placeholder="📡" />
                  </div>
                  <div>
                    <label>Sort order</label>
                    <input type="number" value={newProvider.sort_order} onChange={(e) => setNewProvider({ ...newProvider, sort_order: e.target.value })} />
                  </div>
                </div>
                <label>Integration config (JSON)</label>
                <textarea
                  className="provider-config"
                  rows={6}
                  value={newProvider.config_text}
                  onChange={(e) => setNewProvider({ ...newProvider, config_text: e.target.value })}
                />
                <div className="row mt" style={{ maxWidth: 360 }}>
                  <button type="submit" className="btn-primary">Add provider</button>
                  <button type="button" className="btn-ghost" onClick={closeNewProvider}>Cancel</button>
                </div>
              </form>
            </div>
          )}
        </div>
      )}

      {tab === "campay" && (
        <div className="card mt" style={{ maxWidth: 720 }}>
          <h2>Campay mobile money</h2>
          <p className="muted small">
            Credentials come from <code>.env</code> (<code>CAMPAY_USERNAME</code> / <code>CAMPAY_PASSWORD</code>).
            Sandbox collect/withdraw calls Campay whenever credentials are set and does not move FinPay wallets.
            User wallet MoMo only uses Campay when <code>PAYMENT_MODE=live</code>.
          </p>

          <div className="fee-box mt">
            <div className="review-row">
              <span className="muted">Credentials</span>
              <span>{campayStatus?.credentials_ready || campayStatus?.configured ? "Yes" : "No"}</span>
            </div>
            <div className="review-row">
              <span className="muted">Payment mode</span>
              <span>{campayStatus?.payment_mode || "—"}</span>
            </div>
            <div className="review-row">
              <span className="muted">Wallet MoMo via Campay</span>
              <span>{campayStatus?.wallet_campay_enabled ? "Enabled (live)" : "Off (mock / simulated)"}</span>
            </div>
            <div className="review-row">
              <span className="muted">Reconcile worker</span>
              <span>
                {campayStatus?.reconcile_worker_enabled
                  ? `On (every ${campayStatus?.reconcile_interval_seconds ?? "?"}s)`
                  : "Off"}
              </span>
            </div>
            <div className="review-row">
              <span className="muted">Base URL</span>
              <span>{campayStatus?.base_url || "—"}</span>
            </div>
            <div className="review-row">
              <span className="muted">Username</span>
              <span>{campayStatus?.username_masked || "—"}</span>
            </div>
            <div className="review-row">
              <span className="muted">Webhook key</span>
              <span>{campayStatus?.webhook_configured ? "Set" : "Not set"}</span>
            </div>
          </div>

          <div className="row mt" style={{ maxWidth: 420, gap: 8 }}>
            <button
              type="button"
              className="btn-primary"
              disabled={campayBusy || !(campayStatus?.credentials_ready || campayStatus?.configured)}
              onClick={async () => {
                setCampayBusy(true);
                setMsg(null);
                try {
                  const r = await adminApi.campayTestToken();
                  setMsg(`Token OK (${r.token_preview || "received"}).`);
                } catch (err) {
                  setMsg(err.message);
                } finally {
                  setCampayBusy(false);
                }
              }}
            >
              Test token
            </button>
            <button
              type="button"
              className="btn-ghost"
              disabled={campayBusy || !(campayStatus?.credentials_ready || campayStatus?.configured)}
              onClick={async () => {
                setCampayBusy(true);
                setMsg(null);
                try {
                  setCampayBalance(await adminApi.campayBalance());
                } catch (err) {
                  setMsg(err.message);
                } finally {
                  setCampayBusy(false);
                }
              }}
            >
              Refresh balance
            </button>
          </div>

          {campayBalance && (
            <div className="fee-box mt">
              <div className="review-row"><span className="muted">Total</span><span>{campayBalance.total_balance} {campayBalance.currency || "XAF"}</span></div>
              <div className="review-row"><span className="muted">MTN</span><span>{campayBalance.mtn_balance}</span></div>
              <div className="review-row"><span className="muted">Orange</span><span>{campayBalance.orange_balance}</span></div>
            </div>
          )}

          <h3 className="mt">Holder lookup</h3>
          <div className="row" style={{ alignItems: "flex-end", gap: 8 }}>
            <div style={{ flex: 1 }}>
              <label>Phone</label>
              <input value={campayHolderPhone} onChange={(e) => setCampayHolderPhone(e.target.value)} placeholder="2376XXXXXXXX" />
            </div>
            <button
              type="button"
              className="btn-ghost"
              disabled={campayBusy || !campayHolderPhone.trim()}
              onClick={async () => {
                setCampayBusy(true);
                setMsg(null);
                try {
                  setCampayHolder(await adminApi.campayHolderInfo(campayHolderPhone.trim()));
                } catch (err) {
                  setCampayHolder(null);
                  setMsg(err.message);
                } finally {
                  setCampayBusy(false);
                }
              }}
            >
              Lookup
            </button>
          </div>
          {campayHolder && (
            <pre className="mt small" style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(campayHolder, null, 2)}</pre>
          )}

          <h3 className="mt">Sandbox collect / withdraw</h3>
          <p className="muted small">Live Campay calls only — FinPay wallets are not updated.</p>
          <label>Phone</label>
          <input value={campayTestPhone} onChange={(e) => setCampayTestPhone(e.target.value)} placeholder="2376XXXXXXXX" />
          <label>Amount (whole XAF)</label>
          <input type="number" min="1" step="1" value={campayTestAmount} onChange={(e) => setCampayTestAmount(e.target.value)} />
          <div className="row mt" style={{ maxWidth: 420, gap: 8 }}>
            <button
              type="button"
              className="btn-primary"
              disabled={campayBusy || !campayTestPhone.trim() || !Number(campayTestAmount)}
              onClick={async () => {
                setCampayBusy(true);
                setMsg(null);
                try {
                  const r = await adminApi.campayTestCollect(campayTestPhone.trim(), Number(campayTestAmount));
                  setCampayTestResult(r);
                  if (r.reference) setCampayStatusRef(r.reference);
                } catch (err) {
                  setMsg(err.message);
                } finally {
                  setCampayBusy(false);
                }
              }}
            >
              Test collect
            </button>
            <button
              type="button"
              className="btn-ghost"
              disabled={campayBusy || !campayTestPhone.trim() || !Number(campayTestAmount)}
              onClick={async () => {
                setCampayBusy(true);
                setMsg(null);
                try {
                  const r = await adminApi.campayTestWithdraw(campayTestPhone.trim(), Number(campayTestAmount));
                  setCampayTestResult(r);
                  if (r.reference) setCampayStatusRef(r.reference);
                } catch (err) {
                  setMsg(err.message);
                } finally {
                  setCampayBusy(false);
                }
              }}
            >
              Test withdraw
            </button>
          </div>
          {campayTestResult && (
            <pre className="mt small" style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(campayTestResult, null, 2)}</pre>
          )}

          <h3 className="mt">Transaction status</h3>
          <div className="row" style={{ alignItems: "flex-end", gap: 8 }}>
            <div style={{ flex: 1 }}>
              <label>Campay reference</label>
              <input value={campayStatusRef} onChange={(e) => setCampayStatusRef(e.target.value)} placeholder="UUID from collect/withdraw" />
            </div>
            <button
              type="button"
              className="btn-ghost"
              disabled={campayBusy || !campayStatusRef.trim()}
              onClick={async () => {
                setCampayBusy(true);
                setMsg(null);
                try {
                  setCampayTxnStatus(await adminApi.campayTestTransaction(campayStatusRef.trim()));
                } catch (err) {
                  setCampayTxnStatus(null);
                  setMsg(err.message);
                } finally {
                  setCampayBusy(false);
                }
              }}
            >
              Check status
            </button>
          </div>
          {campayTxnStatus && (
            <pre className="mt small" style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(campayTxnStatus, null, 2)}</pre>
          )}
        </div>
      )}

      {tab === "settings" && (
        <div className="card mt" style={{ maxWidth: 640 }}>
          <h2>Platform settings</h2>
          {settingsRows.map((s) => {
            const isLimit = LIMIT_SETTING_KEYS.has(s.key);
            const draftValue = settingsDraft[s.key] ?? "";
            const displayValue = isLimit
              ? (draftValue === "" ? "" : String(Number(draftValue) / 100))
              : draftValue;
            return (
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
                    type={isLimit || s.value_type === "int" ? "number" : "text"}
                    step={isLimit ? "0.01" : s.value_type === "int" ? "1" : undefined}
                    value={displayValue}
                    onChange={(e) => {
                      if (isLimit) {
                        const major = e.target.value;
                        if (major === "") {
                          setSettingsDraft({ ...settingsDraft, [s.key]: "" });
                          return;
                        }
                        const parsed = parseFloat(major);
                        if (!Number.isFinite(parsed)) return;
                        setSettingsDraft({ ...settingsDraft, [s.key]: String(Math.round(parsed * 100)) });
                      } else {
                        setSettingsDraft({ ...settingsDraft, [s.key]: e.target.value });
                      }
                    }}
                  />
                )}
                {isLimit && (
                  <p className="muted small" style={{ margin: "4px 0 0" }}>
                    Entered in XAF. Stored and enforced as {money(Number(draftValue) || 0)} XAF.
                  </p>
                )}
              </div>
            );
          })}
          <div className="row mt" style={{ maxWidth: 420 }}>
            <button className="btn-primary" onClick={saveSettings}>Save settings</button>
            <button className="btn-ghost" onClick={sendTestEmail}>Send test email</button>
          </div>
          <p className="muted small mt">
            Default per-transaction and daily limits apply to every user (recommended 500,000 XAF). Temporary raises are approved under Limit requests.
          </p>
        </div>
      )}
    </div>
  );
}
