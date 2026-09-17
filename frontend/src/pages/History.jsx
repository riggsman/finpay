import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { transactionsApi } from "../api/transactions";
import { CREDIT_TYPES, transactionStatusClass, transactionTitle } from "../utils/transactions";

function money(minor) {
  return (minor / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

const TYPES = ["", "ADD_MONEY", "SEND_MONEY", "TRANSFER_RECEIVED", "MONEY_REQUEST_OUT", "MONEY_REQUEST_IN", "MONEY_REQUEST_COLLECT", "CAMPAY_COLLECT", "CAMPAY_WITHDRAW", "WITHDRAW", "ELECTRICITY", "AIRTIME", "DATA"];
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
  const [showFilters, setShowFilters] = useState(false);
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

  const filtersActive = Object.values(applied).some((v) => v !== "");

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
    <AppShell showNav wide title="History" backTo="/wallet" className="dash-screen">
      <div className="history-pad">
        <div className={`history-layout ${showFilters ? "filters-open" : "filters-collapsed"}`}>
          {showFilters && (
            <aside className="history-filters card">
              <div className="history-filters-head">
                <h2>Filters</h2>
                <div className="history-filters-head-actions">
                  <button type="button" className="link-btn" onClick={reset}>Reset</button>
                  <button
                    type="button"
                    className="btn-ghost history-filter-close"
                    aria-label="Hide filters"
                    onClick={() => setShowFilters(false)}
                  >
                    Hide
                  </button>
                </div>
              </div>
              <form onSubmit={applyFilters}>
                <div className="filter-grid">
                  <div>
                    <label>Type</label>
                    <select value={filters.type} onChange={(e) => setFilters({ ...filters, type: e.target.value })}>
                      {TYPES.map((t) => (
                        <option key={t || "all-types"} value={t}>
                          {t ? t.replaceAll("_", " ") : "All types"}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label>Status</label>
                    <select value={filters.status} onChange={(e) => setFilters({ ...filters, status: e.target.value })}>
                      {STATUSES.map((s) => (
                        <option key={s || "all-status"} value={s}>{s || "All statuses"}</option>
                      ))}
                    </select>
                  </div>
                  <div className="filter-span-2">
                    <label>Search</label>
                    <input
                      value={filters.search}
                      onChange={(e) => setFilters({ ...filters, search: e.target.value })}
                      placeholder="Reference or description"
                    />
                  </div>
                  <div>
                    <label>Min amount</label>
                    <input
                      type="number"
                      min="0"
                      value={filters.amount_min}
                      onChange={(e) => setFilters({ ...filters, amount_min: e.target.value })}
                    />
                  </div>
                  <div>
                    <label>Max amount</label>
                    <input
                      type="number"
                      min="0"
                      value={filters.amount_max}
                      onChange={(e) => setFilters({ ...filters, amount_max: e.target.value })}
                    />
                  </div>
                  <div>
                    <label>From</label>
                    <input
                      type="date"
                      value={filters.date_from}
                      onChange={(e) => setFilters({ ...filters, date_from: e.target.value })}
                    />
                  </div>
                  <div>
                    <label>To</label>
                    <input
                      type="date"
                      value={filters.date_to}
                      onChange={(e) => setFilters({ ...filters, date_to: e.target.value })}
                    />
                  </div>
                </div>
                <div className="history-filter-actions">
                  <button type="submit" className="btn-primary">Apply filters</button>
                </div>
              </form>
            </aside>
          )}

          <section className="history-results">
            <div className="history-results-head">
              <div>
                <h2>Transactions</h2>
                <p className="muted small">
                  {rows.length === 0 ? "No matches" : `Showing ${rows.length} on page ${page}`}
                  {filtersActive ? " · filters applied" : ""}
                </p>
              </div>
              <div className="history-toolbar">
                <button
                  type="button"
                  className={`btn-ghost history-filter-toggle ${showFilters ? "active" : ""} ${filtersActive ? "has-filters" : ""}`}
                  onClick={() => setShowFilters((v) => !v)}
                  aria-expanded={showFilters}
                >
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                    <path d="M4 6h16M7 12h10M10 18h4" />
                  </svg>
                  {showFilters ? "Hide filters" : "Filters"}
                  {filtersActive && !showFilters && <span className="filter-dot" />}
                </button>
                <div className="history-pager">
                  <button type="button" className="btn-ghost" disabled={page === 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                    ← Prev
                  </button>
                  <span className="pill">Page {page}</span>
                  <button type="button" className="btn-ghost" disabled={rows.length < limit} onClick={() => setPage((p) => p + 1)}>
                    Next →
                  </button>
                </div>
              </div>
            </div>

            <div className="card history-list-card">
              {rows.length === 0 ? (
                <div className="empty">No transactions match these filters.</div>
              ) : (
                <>
                  <div className="history-table-head" aria-hidden="true">
                    <span>Type</span>
                    <span>Reference / date</span>
                    <span>Amount</span>
                    <span>Status</span>
                  </div>
                  {rows.map((t) => {
                    const isCredit = CREDIT_TYPES.has(t.type);
                    const isFailed = t.status === "FAILED";
                    return (
                      <button
                        type="button"
                        className="history-row"
                        key={t.id}
                        onClick={() => navigate(`/transactions/${t.id}`)}
                      >
                        <div className="history-row-type">
                          <span className={`activity-ico ${isFailed ? "out" : isCredit ? "in" : "out"}`}>
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              {isCredit ? (
                                <path d="M12 19V5M5 12l7-7 7 7" />
                              ) : (
                                <path d="M12 5v14M5 12l7 7 7-7" />
                              )}
                            </svg>
                          </span>
                          <strong>{transactionTitle(t)}</strong>
                        </div>
                        <div className="history-row-meta">
                          <span className="mono">{t.reference}</span>
                          <span className="muted small">{new Date(t.created_at).toLocaleString()}</span>
                        </div>
                        <div className={`history-row-amt ${isFailed ? "failed" : isCredit ? "in" : "out"}`}>
                          {isCredit ? "+" : "−"}{money(t.amount)} {t.currency}
                        </div>
                        <div className="history-row-status">
                          <span className={`badge ${transactionStatusClass(t.status)}`}>{t.status}</span>
                        </div>
                      </button>
                    );
                  })}
                </>
              )}
            </div>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
