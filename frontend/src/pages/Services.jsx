import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { servicesApi } from "../api/services";

const ICONS = {
  electricity: "⚡",
  airtime: "📱",
  data: "🌐",
  water: "💧",
};

export default function Services() {
  const navigate = useNavigate();
  const [services, setServices] = useState([]);

  useEffect(() => {
    servicesApi.list().then((r) => setServices(r.services)).catch(() => {});
  }, []);

  return (
    <div className="container">
      <div className="topbar">
        <div className="brand">
          <span className="dot" />
          FinPay
        </div>
        <button className="btn-ghost" onClick={() => navigate("/dashboard")}>
          ← Dashboard
        </button>
      </div>

      <h1>Services</h1>
      <p className="muted">Pay bills and buy services from your wallet.</p>

      <div className="services-grid mt-lg">
        {services.map((s) => (
          <button
            key={s.id}
            className={`service-tile ${s.enabled ? "" : "disabled"}`}
            disabled={!s.enabled}
            onClick={() => s.id === "electricity" && navigate("/services/electricity")}
          >
            <span className="service-icon">{ICONS[s.id] || "•"}</span>
            <span className="service-name">{s.name}</span>
            {!s.enabled && <span className="soon">Coming soon</span>}
          </button>
        ))}
      </div>
    </div>
  );
}
