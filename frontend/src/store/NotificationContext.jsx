import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { moneyRequestsApi } from "../api/social";
import { notificationsApi } from "../api/wallet";
import { onForegroundMessage } from "../services/pushService";
import { socketService } from "../services/socketService";
import { useAuth } from "./AuthContext";

const NotificationContext = createContext(null);

const LIMIT_EVENTS = [
  "LIMIT_INCREASE_APPROVED",
  "LIMIT_INCREASE_REJECTED",
  "LIMIT_INCREASE_EXHAUSTED",
];

function normalizeIncoming(payload) {
  const data = payload?.data || payload || {};
  const idRaw = data.notification_id;
  const id = idRaw != null && idRaw !== "" ? Number(idRaw) : null;
  return {
    id: Number.isFinite(id) ? id : null,
    event_id: data.event_id || payload?.event_id || "",
    type: data.type || payload?.event_type || "NOTICE",
    title: data.title || "FinPay",
    message: data.message || data.body || "",
    priority: data.priority || "NORMAL",
    is_read: false,
    created_at: payload?.timestamp || new Date().toISOString(),
    read_at: null,
    data: typeof data.data === "object" ? data.data : null,
  };
}

export function NotificationProvider({ children }) {
  const { isAuthenticated } = useAuth();
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [pendingRequests, setPendingRequests] = useState(0);
  const [limitsRevision, setLimitsRevision] = useState(0);
  const [toast, setToast] = useState(null);
  const toastRef = useRef(null);
  const seenIds = useRef(new Set());

  const refreshPendingRequests = useCallback(async () => {
    if (!isAuthenticated) {
      setPendingRequests(0);
      return;
    }
    try {
      const rows = await moneyRequestsApi.list("incoming");
      setPendingRequests((rows || []).filter((r) => r.status === "PENDING").length);
    } catch {
      /* keep last known count */
    }
  }, [isAuthenticated]);

  const refresh = useCallback(async () => {
    if (!isAuthenticated) return;
    const [list, count] = await Promise.all([
      notificationsApi.list(100),
      notificationsApi.unreadCount(),
    ]);
    setItems(list);
    setUnread(count.unread);
    seenIds.current = new Set(list.map((n) => n.id));
    await refreshPendingRequests();
  }, [isAuthenticated, refreshPendingRequests]);

  const showToast = useCallback((title, message) => {
    const text = message ? `${title} — ${message}` : title;
    setToast(text);
    clearTimeout(toastRef.current);
    toastRef.current = setTimeout(() => setToast(null), 5000);
  }, []);

  const bumpLimits = useCallback(() => {
    setLimitsRevision((n) => n + 1);
  }, []);

  const ingest = useCallback((payload, { flash = true } = {}) => {
    const row = normalizeIncoming(payload);
    if (row.id != null && seenIds.current.has(row.id)) {
      if (String(row.type || "").startsWith("LIMIT_INCREASE")) bumpLimits();
      return;
    }
    if (row.id != null) seenIds.current.add(row.id);

    setItems((prev) => {
      if (row.id != null && prev.some((n) => n.id === row.id)) return prev;
      return [row, ...prev].slice(0, 100);
    });
    setUnread((u) => u + 1);
    if (flash && row.title) showToast(row.title, row.message);
    if (String(row.type || "").startsWith("LIMIT_INCREASE")) bumpLimits();

    notificationsApi.list(100).then((list) => {
      setItems(list);
      seenIds.current = new Set(list.map((n) => n.id));
    }).catch(() => {});
    notificationsApi.unreadCount().then((c) => setUnread(c.unread)).catch(() => {});
  }, [showToast, bumpLimits]);

  useEffect(() => {
    if (!isAuthenticated) {
      setItems([]);
      setUnread(0);
      setPendingRequests(0);
      setToast(null);
      seenIds.current = new Set();
      return;
    }
    refresh().catch(() => {});
  }, [isAuthenticated, refresh]);

  useEffect(() => {
    if (!isAuthenticated) return undefined;

    const moneyTypes = new Set([
      "MONEY_REQUESTED",
      "MONEY_REQUEST_PAID",
      "MONEY_REQUEST_DECLINED",
    ]);
    const limitTypes = new Set(LIMIT_EVENTS);

    const onNotif = (evt) => {
      const type = evt?.data?.type;
      ingest(evt, { flash: !moneyTypes.has(type) && !limitTypes.has(type) });
      if (moneyTypes.has(type)) refreshPendingRequests().catch(() => {});
      if (limitTypes.has(type) || String(type || "").startsWith("LIMIT_INCREASE")) bumpLimits();
    };

    const onMoneyEvent = (evt) => {
      const d = evt?.data || {};
      const type = evt?.event_type || d.type || "MONEY_REQUESTED";
      const title =
        d.title ||
        (type === "MONEY_REQUEST_PAID"
          ? "Request Paid"
          : type === "MONEY_REQUEST_DECLINED"
            ? "Request Declined"
            : type === "MONEY_REQUEST_UPDATED"
              ? "Request Updated"
              : "Money Requested");
      const message =
        d.message ||
        (type === "MONEY_REQUESTED"
          ? `${d.from || "Someone"} requested money from you.`
          : type === "MONEY_REQUEST_PAID"
            ? "Your money request was paid."
            : type === "MONEY_REQUEST_DECLINED"
              ? "Your money request was declined."
              : "");
      if (type === "MONEY_REQUESTED" || type === "MONEY_REQUEST_PAID" || type === "MONEY_REQUEST_DECLINED") {
        showToast(title, message);
      }
      refresh().catch(() => {});
      refreshPendingRequests().catch(() => {});
    };

    const onLimitEvent = (evt) => {
      const d = evt?.data || {};
      const type = evt?.event_type || d.type || "LIMIT_INCREASE_APPROVED";
      const title =
        d.title ||
        (type === "LIMIT_INCREASE_APPROVED"
          ? "Limit increase approved"
          : type === "LIMIT_INCREASE_REJECTED"
            ? "Limit increase declined"
            : "Limit update");
      const message = d.message || "";
      showToast(title, message);
      bumpLimits();
      refresh().catch(() => {});
    };

    const moneyEvents = [
      "MONEY_REQUESTED",
      "MONEY_REQUEST_PAID",
      "MONEY_REQUEST_DECLINED",
      "MONEY_REQUEST_UPDATED",
    ];

    const bindSocket = () => {
      socketService.off("notification:new", onNotif);
      socketService.on("notification:new", onNotif);
      moneyEvents.forEach((ev) => {
        socketService.off(ev, onMoneyEvent);
        socketService.on(ev, onMoneyEvent);
      });
      LIMIT_EVENTS.forEach((ev) => {
        socketService.off(ev, onLimitEvent);
        socketService.on(ev, onLimitEvent);
      });
    };
    bindSocket();
    const unsubState = socketService.onStateChange((state) => {
      if (state === "CONNECTED") bindSocket();
    });

    onForegroundMessage((payload) => {
      const n = payload?.notification || {};
      const d = payload?.data || {};
      const type = String(d.type || "");
      ingest({
        event_id: d.event_id,
        data: {
          notification_id: d.notification_id,
          type,
          title: n.title || "FinPay",
          message: n.body || "",
          priority: "HIGH",
          event_id: d.event_id,
        },
      }, { flash: true });
      if (type.startsWith("MONEY_REQUEST")) {
        refreshPendingRequests().catch(() => {});
      }
      if (type.startsWith("LIMIT_INCREASE")) {
        bumpLimits();
      }
    });

    return () => {
      socketService.off("notification:new", onNotif);
      moneyEvents.forEach((ev) => socketService.off(ev, onMoneyEvent));
      LIMIT_EVENTS.forEach((ev) => socketService.off(ev, onLimitEvent));
      unsubState();
      onForegroundMessage(null);
      clearTimeout(toastRef.current);
    };
  }, [isAuthenticated, ingest, refresh, refreshPendingRequests, showToast, bumpLimits]);

  const markRead = useCallback(async (id) => {
    setItems((prev) => {
      const target = prev.find((n) => n.id === id);
      if (target && !target.is_read) {
        setUnread((u) => Math.max(0, u - 1));
      }
      return prev.map((n) =>
        n.id === id && !n.is_read
          ? { ...n, is_read: true, read_at: new Date().toISOString() }
          : n
      );
    });

    try {
      const updated = await notificationsApi.markRead(id);
      setItems((prev) =>
        prev.map((n) => (n.id === id ? { ...n, ...updated, data: updated.data ?? n.data } : n))
      );
      notificationsApi.unreadCount().then((c) => setUnread(c.unread)).catch(() => {});
      return updated;
    } catch (err) {
      await refresh().catch(() => {});
      throw err;
    }
  }, [refresh]);

  const markAllRead = useCallback(async () => {
    await notificationsApi.markAllRead();
    setItems((prev) => prev.map((n) => ({ ...n, is_read: true, read_at: n.read_at || new Date().toISOString() })));
    setUnread(0);
  }, []);

  const clearToast = useCallback(() => {
    setToast(null);
    clearTimeout(toastRef.current);
  }, []);

  const value = useMemo(
    () => ({
      items,
      unread,
      pendingRequests,
      limitsRevision,
      toast,
      refresh,
      refreshPendingRequests,
      ingest,
      markRead,
      markAllRead,
      clearToast,
      showToast,
    }),
    [
      items,
      unread,
      pendingRequests,
      limitsRevision,
      toast,
      refresh,
      refreshPendingRequests,
      ingest,
      markRead,
      markAllRead,
      clearToast,
      showToast,
    ]
  );

  return (
    <NotificationContext.Provider value={value}>
      {children}
      {toast && (
        <div
          className="alert alert-success toast-banner toast-banner--global"
          role="status"
          onClick={clearToast}
        >
          {toast}
        </div>
      )}
    </NotificationContext.Provider>
  );
}

export function useNotifications() {
  const ctx = useContext(NotificationContext);
  if (!ctx) throw new Error("useNotifications must be used within NotificationProvider");
  return ctx;
}
