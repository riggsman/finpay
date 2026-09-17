import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { securityApi } from "../api/security";

const PAGE_SIZE = 10;

function actionLabel(action) {
  return String(action || "").replaceAll("_", " ");
}

function dayKey(iso) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function dayHeading(iso) {
  const d = new Date(iso);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (dayKey(iso) === dayKey(today.toISOString())) return "Today";
  if (dayKey(iso) === dayKey(yesterday.toISOString())) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" });
}

export default function Activity() {
  const navigate = useNavigate();
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("ALL");
  const [page, setPage] = useState(1);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    setBusy(true);
    securityApi.activity(200)
      .then(setRows)
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false));
  }, []);

  const filtered = useMemo(() => {
    if (filter === "SUCCESS") return rows.filter((r) => r.result === "SUCCESS");
    if (filter === "FAILED") return rows.filter((r) => r.result !== "SUCCESS");
    return rows;
  }, [rows, filter]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);

  const pageRows = useMemo(() => {
    const start = (currentPage - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [filtered, currentPage]);

  const groups = useMemo(() => {
    const map = new Map();
    pageRows.forEach((row) => {
      const key = dayKey(row.created_at);
      if (!map.has(key)) map.set(key, { heading: dayHeading(row.created_at), items: [] });
      map.get(key).items.push(row);
    });
    return [...map.values()];
  }, [pageRows]);

  function setFilterAndReset(id) {
    setFilter(id);
    setPage(1);
  }

  const from = filtered.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1;
  const to = Math.min(currentPage * PAGE_SIZE, filtered.length);

  return (
    <AppShell title="Activity" backTo="/profile" showNav className="dash-screen">
      <p className="screen-desc">
        Security and account events on your FinPay profile. Transaction history lives in Wallet.
      </p>

      <div className="activity-filters">
        {[
          { id: "ALL", label: "All" },
          { id: "SUCCESS", label: "Successful" },
          { id: "FAILED", label: "Failed" },
        ].map((f) => (
          <button
            key={f.id}
            type="button"
            className={`chip ${filter === f.id ? "active" : ""}`}
            onClick={() => setFilterAndReset(f.id)}
          >
            {f.label}
          </button>
        ))}
      </div>

      <div className="dash-section activity-section">
        <div className="history-results-head activity-page-head">
          <p className="muted small" style={{ margin: 0 }}>
            {busy
              ? "Loading…"
              : filtered.length === 0
                ? "No matches"
                : `Showing ${from}–${to} of ${filtered.length}`}
          </p>
          <div className="history-pager">
            <button
              type="button"
              className="btn-ghost"
              disabled={busy || currentPage <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              ← Prev
            </button>
            <span className="pill">Page {currentPage} / {totalPages}</span>
            <button
              type="button"
              className="btn-ghost"
              disabled={busy || currentPage >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next →
            </button>
          </div>
        </div>

        {busy && <div className="empty">Loading activity…</div>}
        {error && <div className="alert alert-error">{error}</div>}
        {!busy && !error && filtered.length === 0 && (
          <div className="empty">No activity matches this filter.</div>
        )}

        {groups.map((group) => (
          <div className="activity-day" key={group.heading}>
            <div className="activity-day-label">{group.heading}</div>
            <div className="activity-list">
              {group.items.map((a) => (
                <div className="activity-item static" key={a.id}>
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
                    <span>
                      {new Date(a.created_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      {a.ip ? ` · ${a.ip}` : ""}
                      {a.user_agent ? ` · ${String(a.user_agent).slice(0, 28)}` : ""}
                    </span>
                  </div>
                  <span className={`badge ${a.result === "SUCCESS" ? "SUCCESS" : "FAILED"}`}>{a.result}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="dash-section">
        <button type="button" className="btn-ghost" style={{ width: "100%" }} onClick={() => navigate("/transactions")}>
          View wallet transactions →
        </button>
      </div>
    </AppShell>
  );
}
