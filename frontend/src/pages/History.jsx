import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { transactionsApi } from "../api/transactions";

const CREDIT_TYPES = new Set(["ADD_MONEY", "TRANSFER_RECEIVED"]);

function money(minor) {
  return (minor / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

const TYPES = ["", "ADD_MONEY", "SEND_MONEY", "TRANSFER_RECEIVED", "WITHDRAW", "ELECTRICITY"];
const STATUSES = ["", "SUCCESS", "PROCESSING", "PENDING", "FAILED", "REVERSED"];

const EMPTY = {
  type: "",
  status: "",
  search: "",
  amount_min: "",
  amount_max: "",
  date_from: "",
  date_to: "",
};

export default function History() {
  const navigate = useNavigate();
  const [filters, setFilters] = useState(EMPTY);
  const [applied, setApplied] = useState(EMPTY);
  const [rows, setRows] = useState([]);
  const [page, setPage] = useState(1);
  const limit = 10;

  const load = useCallback(async (f, p) => {
    const params = { ...f, page: p, limit };
    if (params.amount_min) params.amount_min = Math.round(parseFloat(params.amount_min) * 100);
    if (params.amount_max) params.amount_max = Math.round(parseFloat(params.amount_max) * 100);
    if (params.date_from) params.date_from = new Date(params.date_from).toISOString();
    if (params.date_to) params.date_to = new Date(params.date_to).toISOString();
    const data = await transactionsApi.list(params);
    setRows(data);
  }, []);

  useEffect(() => {
    load(applied, page).catch(() => {});
  }, [applied, page, load]);

  function applyFilters(e) {
    e.preventDefault();
    setPage(1);
    setApplied(filters);
  }

  function reset() {
    setFilters(EMPTY);
    setApplied(EMPTY);
    setPage(1);
  }

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand"><span className="dot" /> FinPay</div>
        <button className="btn-ghost" onClick={() => navigate("/dashboard")}>← Dashboard</button>
      </div>

      <h1>Transaction history</h1>

      <form className="card mt filters" onSubmit={applyFilters}>
        <div className="filter-grid">
          <div>
            <label>Type</label>
            <select value={filters.type} onChange={(e) => setFilters({ ...filters, type: e.target.value })}>
              {TYPES.map((t) => <option key={t} value={t}>{t ? t.replaceAll("_", " ") : "All types"}</option>)}
            </select>
          </div>
          <div>
            <label>Status</label>
            <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
              {STATUSES.map((s) => <option key={s} value={s}>{s || "All statuses"}</option>)}
            </select>
          </div>
          <div>
            <label>Search</label>
            <input value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} placeholder="reference or description" />
          </div>
          <div>
            <label>Min amount</label>
            <input type="number" min="0" value={filters.amount_min} onChange={(e) => setFilters({ ...filters, amount_min: e.target.value })} />
          </div>
          <div>
            <label>Max amount</label>
            <input type="number" min="0" value={filters.amount_max} onChange={(e) => setFilters({ ...filters, amount_max: e.target.value })} />
          </div>
          <div>
            <label>From</label>
            <input type="date" value={filters.date_from} onChange={(e) => setFilters({ ...filters, date_from: e.target.value })} />
          </div>
          <div>
            <label>To</label>
            <input type="date" value={filters.date_to} onChange={(e) => setFilters({ ...filters, date_to: e.target.value })} />
          </div>
        </div>
        <div className="row mt" style={{ maxWidth: 320 }}>
          <button className="btn-primary">Apply filters</button>
          <button type="button" className="btn-ghost" onClick={reset}>Reset</button>
        </div>
      </form>

      <div className="card mt">
        {rows.length === 0 ? (
          <div className="empty">No transactions match these filters.</div>
        ) : (
          rows.map((t) => {
            const isCredit = CREDIT_TYPES.has(t.type);
            return (
              <div className="txn clickable" key={t.id} onClick={() => navigate(`/transactions/${t.id}`)}>
                <div className="meta">
                  <span>{t.type.replaceAll("_", " ")}</span>
                  <span className="muted small">{t.reference} · {new Date(t.created_at).toLocaleString()}</span>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="amt" style={{ color: isCredit ? "var(--accent)" : "var(--text)" }}>
                    {isCredit ? "+" : "−"}{money(t.amount)} {t.currency}
                  </div>
                  <span className={`badge ${t.status}`}>{t.status}</span>
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className="row mt" style={{ maxWidth: 320 }}>
        <button className="btn-ghost" disabled={page === 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>← Prev</button>
        <span className="pill" style={{ justifyContent: "center" }}>Page {page}</span>
        <button className="btn-ghost" disabled={rows.length < limit} onClick={() => setPage((p) => p + 1)}>Next →</button>
      </div>
    </div>
  );
}
