import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { authApi } from "../api/auth";
import { useAuth } from "../store/AuthContext";

export default function Login() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { login } = useAuth();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await authApi.login(identifier, password);
      login(res);
      const next = params.get("next");
      navigate(next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-viewport">
      <div className="app-frame">
        <div className="app-scroll" style={{ display: "grid", placeItems: "center", padding: 20 }}>
          <form className="auth-card" onSubmit={onSubmit} style={{ width: "100%" }}>
            <div className="brand">
              <span className="dot" />
              FinPay
            </div>
            <h1>Welcome back</h1>
            <p className="muted">Log in with your phone or email.</p>

            <label>Phone or email</label>
            <input
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="+237650000001"
              autoFocus
            />

            <label>Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Your password"
            />

            {error && <div className="alert alert-error">{error}</div>}

            <div className="mt-lg">
              <button className="btn-primary" disabled={loading}>
                {loading ? "Signing in..." : "Sign in"}
              </button>
            </div>
            <p className="center mt muted small">
              <Link className="link" to="/forgot-password">Forgot password?</Link>
            </p>
            <p className="center muted small">
              New here? <Link className="link" to="/register">Create an account</Link>
            </p>
            <p className="center muted small">
              Administrator? <Link className="link" to="/admin/login">Admin login</Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
