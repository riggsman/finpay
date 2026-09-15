import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "../api/auth";

// Steps: request -> code -> reset -> done  (SCR-007 .. SCR-010)
export default function ForgotPassword() {
  const navigate = useNavigate();
  const [step, setStep] = useState("request");
  const [identifier, setIdentifier] = useState("");
  const [code, setCode] = useState("");
  const [codeHint, setCodeHint] = useState(null);
  const [resetToken, setResetToken] = useState(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submitRequest(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await authApi.passwordResetRequest(identifier);
      if (res.reset_code_debug) {
        setCodeHint(res.reset_code_debug);
        setInfo(`Dev mode: your reset code is ${res.reset_code_debug}`);
      } else {
        setInfo("If an account exists, a reset code has been sent.");
      }
      setStep("code");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitCode(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const res = await authApi.passwordResetVerify(identifier, code);
      setResetToken(res.reset_token);
      setStep("reset");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function submitReset(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await authApi.passwordResetComplete(resetToken, password);
      setStep("done");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center-screen">
      <div className="card auth-card">
        <div className="brand">
          <span className="dot" />
          FinPay
        </div>

        {step === "request" && (
          <form onSubmit={submitRequest}>
            <h1>Forgot password</h1>
            <p className="muted">Enter your phone or email to receive a reset code.</p>
            <label>Phone or email</label>
            <input
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              placeholder="+237650000001"
              autoFocus
            />
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button className="btn-primary" disabled={busy}>
                {busy ? "Sending…" : "Send reset code"}
              </button>
            </div>
            <p className="center mt muted small">
              <Link className="link" to="/login">Back to sign in</Link>
            </p>
          </form>
        )}

        {step === "code" && (
          <form onSubmit={submitCode}>
            <h1>Enter reset code</h1>
            <p className="muted">We sent a 6-digit code to {identifier}.</p>
            {info && <div className="alert alert-info">{info}</div>}
            <label>Reset code</label>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="123456"
              inputMode="numeric"
              maxLength={6}
              autoFocus
            />
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button className="btn-primary" disabled={busy}>
                {busy ? "Verifying…" : "Verify code"}
              </button>
            </div>
            {codeHint && (
              <p className="center mt muted small">
                Autofill dev code:{" "}
                <span className="link" onClick={() => setCode(codeHint)}>{codeHint}</span>
              </p>
            )}
          </form>
        )}

        {step === "reset" && (
          <form onSubmit={submitReset}>
            <h1>Create new password</h1>
            <p className="muted">Choose a new password for your account.</p>
            <label>New password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              minLength={8}
              autoFocus
            />
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button className="btn-primary" disabled={busy || password.length < 8}>
                {busy ? "Updating…" : "Update password"}
              </button>
            </div>
          </form>
        )}

        {step === "done" && (
          <div className="center">
            <div className="result-icon success">✓</div>
            <h1 className="mt">Password updated</h1>
            <p className="muted">You can now sign in with your new password.</p>
            <div className="mt-lg">
              <button className="btn-primary" onClick={() => navigate("/login")}>
                Go to sign in
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
