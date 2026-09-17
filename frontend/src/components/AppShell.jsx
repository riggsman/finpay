import { useNavigate } from "react-router-dom";
import BottomNav from "./BottomNav";

export default function AppShell({
  children,
  title,
  backTo,
  showNav = false,
  wide = false,
  right,
  className = "",
}) {
  const navigate = useNavigate();
  const useWide = wide || showNav;

  return (
    <div className={`app-viewport ${showNav ? "has-nav" : ""} ${useWide ? "wide" : ""}`}>
      <div className={`app-frame ${className}`}>
        {(title || backTo || right) && (
          <header className="app-header space-between">
            {backTo ? (
              <button
                type="button"
                className="back-btn"
                aria-label="Back"
                onClick={() => {
                  if (typeof backTo === "function") backTo();
                  else if (typeof backTo === "number") navigate(backTo);
                  else navigate(backTo);
                }}
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M15 18l-6-6 6-6" />
                </svg>
              </button>
            ) : (
              <div className="header-spacer" />
            )}
            {title ? <h1 className="app-title">{title}</h1> : <div />}
            <div className="header-right">{right || <div className="header-spacer" />}</div>
          </header>
        )}
        <div className="app-scroll">{children}</div>
        {showNav && <BottomNav />}
      </div>
    </div>
  );
}
