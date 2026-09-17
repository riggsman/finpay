import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import Pagination, { usePagination } from "../components/Pagination";
import { useNotifications } from "../store/NotificationContext";

const PAGE_SIZE = 10;

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
  return d.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function timeLabel(iso) {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function routeForNotification(n) {
  const type = String(n.type || "").toUpperCase();
  const data = n.data || {};
  if (type.startsWith("LIMIT_")) return "/security/limits";
  if (data.transaction_id) return `/transactions/${data.transaction_id}`;
  if (data.ticket_id) return `/support/tickets/${data.ticket_id}`;
  if (data.request_id) return "/wallet/requests";
  if (type.startsWith("KYC_")) return "/kyc";
  if (type.startsWith("SUPPORT_") || type.startsWith("DISPUTE_")) return "/support";
  if (type.includes("TRANSFER") || type.includes("WALLET") || type.includes("BILL") || type.includes("PAYMENT") || type.includes("MONEY")) {
    return "/transactions";
  }
  return null;
}

export default function Notifications() {
  const navigate = useNavigate();
  const { items, unread, markRead, markAllRead } = useNotifications();
  const [openingId, setOpeningId] = useState(null);
  const pager = usePagination(items, PAGE_SIZE);

  const groups = useMemo(() => {
    const map = new Map();
    pager.pageItems.forEach((row) => {
      const key = dayKey(row.created_at);
      if (!map.has(key)) map.set(key, { heading: dayHeading(row.created_at), items: [] });
      map.get(key).items.push(row);
    });
    return [...map.values()];
  }, [pager.pageItems]);

  async function openNotification(n) {
    if (openingId != null) return;
    setOpeningId(n.id ?? n.event_id ?? "pending");
    try {
      if (!n.is_read && n.id != null) {
        await markRead(n.id);
      }
      const target = routeForNotification(n);
      if (target) navigate(target);
    } catch {
      /* stay on the list; mark-read may have partially applied */
    } finally {
      setOpeningId(null);
    }
  }

  return (
    <AppShell title="Notifications" backTo="/dashboard" showNav className="dash-screen">
      <div className="notif-toolbar">
        <p className="muted small" style={{ margin: 0 }}>
          {unread > 0 ? `${unread} unread` : "You're all caught up"}
        </p>
        {unread > 0 && (
          <button type="button" className="btn-ghost" onClick={() => markAllRead().catch(() => {})}>
            Mark all read
          </button>
        )}
      </div>

      {items.length === 0 ? (
        <div className="empty mt">No notifications yet. Transaction and account alerts will show up here.</div>
      ) : (
        <div className="notif-feed mt">
          {groups.map((group) => (
            <section key={group.heading} className="notif-day">
              <h3 className="notif-day-heading">{group.heading}</h3>
              <ul className="notif-list">
                {group.items.map((n) => {
                  const key = n.id ?? `${n.event_id}-${n.created_at}`;
                  const busy = openingId === (n.id ?? n.event_id ?? "pending");
                  return (
                    <li key={key}>
                      <button
                        type="button"
                        className={`notif ${n.is_read ? "is-read" : "is-unread"}${busy ? " is-opening" : ""}`}
                        onClick={() => openNotification(n)}
                        disabled={busy}
                        aria-label={`${n.is_read ? "Read" : "Unread"} notification: ${n.title}`}
                      >
                        <div className="notif-top">
                          <strong>{n.title}</strong>
                          <span className="muted small">{timeLabel(n.created_at)}</span>
                        </div>
                        <p>{n.message}</p>
                        <div className="notif-meta">
                          <span className="muted small mono">{String(n.type || "").replaceAll("_", " ")}</span>
                          {!n.is_read && <span className="notif-unread-dot" aria-label="Unread" />}
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}

          <Pagination
            page={pager.page}
            totalPages={pager.totalPages}
            total={pager.total}
            pageSize={pager.pageSize}
            onChange={pager.setPage}
          />
        </div>
      )}
    </AppShell>
  );
}
