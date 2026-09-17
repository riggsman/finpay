import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { adminApi } from "../api/admin";
import { useAuth } from "../store/AuthContext";

const DEV_ADMIN_EMAIL = "admin@local.dev";
const DEV_ADMIN_PASSWORD = "admin1234";

/**
 * Separate admin login — uses POST /admin/login (not /auth/login).
 * Mobile-first layout; works on phone and desktop.
 */
export default function AdminLogin() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { login } = useAuth();
  const [identifier, setIdentifier] = useState(DEV_ADMIN_EMAIL);
  const [password, setPassword] = useState(DEV_ADMIN_PASSWORD);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await adminApi.login(identifier, password);
      if (!res?.user?.is_admin) {
        setError("Administrator access required.");
        return;
      }
      login(res);
      const next = params.get("next");
      navigate(next && next.startsWith("/admin") ? next : "/admin");
    } catch (err) {
      setError(err.message || "Admin sign-in failed.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="center-screen admin-login-screen">
      <form className="card auth-card admin-auth-card" onSubmit={onSubmit}>
        <div className="endpoint-pill">POST /admin/login</div>
        <div className="brand">
          <span className="dot" />
          FinPay Admin
        </div>
        <h1>Admin sign in</h1>
        <p className="muted">
          Separate from the customer app. Use your Back Office admin account.
        </p>

        <label>Admin email or phone</label>
        <input
          value={identifier}
          onChange={(e) => setIdentifier(e.target.value)}
          placeholder={DEV_ADMIN_EMAIL}
          autoComplete="username"
          autoFocus
        />

        <label>Password</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Admin password"
          autoComplete="current-password"
        />

        {error && <div className="alert alert-error">{error}</div>}

        <div className="mt-lg">
          <button className="btn-primary" disabled={loading}>
            {loading ? "Signing in…" : "Sign in to Admin"}
          </button>
        </div>

        <div className="admin-demo-hint muted small">
          <strong>Seeded admin (dev)</strong>
          <br />
          Email: {DEV_ADMIN_EMAIL}
          <br />
          Phone: +237600000001
          <br />
          Password: {DEV_ADMIN_PASSWORD}
        </div>

        <p className="center mt muted small">
          Customer account? <Link className="link" to="/login">Use app login</Link>
        </p>
      </form>
    </div>
  );
}
