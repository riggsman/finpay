import { Link, useLocation } from "react-router-dom";

const ITEMS = [
  {
    to: "/dashboard",
    label: "Home",
    match: (p) => p === "/dashboard",
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 10.5L12 4l8 6.5V20a1 1 0 01-1 1h-5v-6h-4v6H5a1 1 0 01-1-1v-9.5z" />
      </svg>
    ),
  },
  {
    to: "/wallet",
    label: "Wallet",
    match: (p) => p.startsWith("/wallet") || p.startsWith("/transactions"),
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 7h16v12H4z" />
        <path d="M8 7V5a4 4 0 018 0v2" />
      </svg>
    ),
  },
  {
    to: "/services",
    label: "Pay",
    match: (p) => p.startsWith("/services"),
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M3 12h18M12 3v18" />
      </svg>
    ),
  },
  {
    to: "/profile",
    label: "Profile",
    match: (p) => p.startsWith("/profile") || p.startsWith("/security") || p.startsWith("/kyc") || p.startsWith("/support"),
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="8" r="3.5" />
        <path d="M5 19a7 7 0 0114 0" />
      </svg>
    ),
  },
];

export default function BottomNav() {
  const { pathname } = useLocation();
  return (
    <nav className="bottom-nav" aria-label="Main">
      {ITEMS.map((item) => (
        <Link
          key={item.to}
          to={item.to}
          className={`nav-item ${item.match(pathname) ? "active" : ""}`}
        >
          {item.icon}
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
