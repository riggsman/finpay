import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import { servicesApi } from "../api/services";
import { refreshConfig } from "../services/feeConfig";

const ICONS = {
  electricity: "⚡",
  airtime: "📱",
  data: "🌐",
  water: "💧",
};

export default function Services() {
  const navigate = useNavigate();
  const [services, setServices] = useState([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await refreshConfig().catch(() => {});
      try {
        const r = await servicesApi.list();
        // Backend already returns enabled-only; keep a client filter as a safety net.
        const visible = (r.services || []).filter((s) => s.enabled !== false);
        if (!cancelled) setServices(visible);
      } catch {
        if (!cancelled) setServices([]);
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AppShell showNav title="Pay bills" backTo="/dashboard" className="dash-screen">
      <p className="screen-desc">Choose a service to pay from your FinPay wallet.</p>
      <div className="dash-section">
        {!loaded ? (
          <div className="empty">Loading services…</div>
        ) : services.length === 0 ? (
          <div className="empty">
            No bill payment services are available right now. Check back later or contact support.
          </div>
        ) : (
          <div className="services-grid">
            {services.map((s) => (
              <button
                key={s.id}
                type="button"
                className="service-tile"
                onClick={() => navigate(`/services/${s.id}`)}
              >
                <span className="service-icon">{s.icon || ICONS[s.id] || "•"}</span>
                <span className="service-name">{s.name}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
