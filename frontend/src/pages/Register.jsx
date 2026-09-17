import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authApi } from "../api/auth";
import { useAuth } from "../store/AuthContext";

export default function Register() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [step, setStep] = useState("details"); // details | otp
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    phone: "+237",
    password: "",
  });
  const [otp, setOtp] = useState("");
  const [otpHint, setOtpHint] = useState(null);
  const [error, setError] = useState(null);
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(false);

  const update = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submitDetails(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await authApi.register(form);
      const initiated = await authApi.registerInitiate(form.phone);
      // In development the backend returns the OTP to simplify testing.
      if (initiated.otp_debug) {
        setOtpHint(initiated.otp_debug);
        setInfo(`We emailed your verification code. Dev hint: ${initiated.otp_debug}`);
      } else {
        setInfo("We sent a verification code to your email (@local.dev).");
      }
      setStep("otp");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function submitOtp(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await authApi.verifyOtp(form.phone, otp);
      login(res);
      navigate("/dashboard");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="center-screen">
      <div className="card auth-card">
        <div className="brand">
          <span className="dot" />
          FinPay
        </div>

        {step === "details" ? (
          <form onSubmit={submitDetails}>
            <h1>Create your account</h1>
            <p className="muted">It only takes a minute.</p>

            <div className="row">
              <div>
                <label>First name</label>
                <input value={form.first_name} onChange={update("first_name")} required />
              </div>
              <div>
                <label>Last name</label>
                <input value={form.last_name} onChange={update("last_name")} required />
              </div>
            </div>

            <label>Phone</label>
            <input value={form.phone} onChange={update("phone")} placeholder="+237650000001" required />

            <label>Email local-part (optional)</label>
            <div className="row" style={{ alignItems: "center", gap: 8 }}>
              <input
                value={form.email}
                onChange={update("email")}
                placeholder="john"
                style={{ flex: 1 }}
              />
              <span className="muted">@local.dev</span>
            </div>
            <p className="muted small" style={{ marginTop: 4 }}>
              Leave blank to auto-assign from your first name (e.g. john@local.dev).
            </p>

            <label>Password</label>
            <input
              type="password"
              value={form.password}
              onChange={update("password")}
              placeholder="At least 8 characters"
              minLength={8}
              required
            />

            {error && <div className="alert alert-error">{error}</div>}

            <div className="mt-lg">
              <button className="btn-primary" disabled={loading}>
                {loading ? "Creating..." : "Continue"}
              </button>
            </div>
            <p className="center mt muted small">
              Already have an account? <Link className="link" to="/login">Sign in</Link>
            </p>
          </form>
        ) : (
          <form onSubmit={submitOtp}>
            <h1>Verify your email</h1>
            <p className="muted">Enter the 6-digit code we sent to your FinPay email.</p>

            {info && <div className="alert alert-info">{info}</div>}

            <label>Verification code</label>
            <input
              value={otp}
              onChange={(e) => setOtp(e.target.value)}
              placeholder="123456"
              inputMode="numeric"
              maxLength={6}
              autoFocus
            />

            {error && <div className="alert alert-error">{error}</div>}

            <div className="mt-lg">
              <button className="btn-primary" disabled={loading}>
                {loading ? "Verifying..." : "Verify & continue"}
              </button>
            </div>
            {otpHint && (
              <p className="center mt muted small">
                Autofill dev code:{" "}
                <span className="link" onClick={() => setOtp(otpHint)}>
                  {otpHint}
                </span>
              </p>
            )}
          </form>
        )}
      </div>
    </div>
  );
}
