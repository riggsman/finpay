import { Link } from "react-router-dom";

export default function Landing() {
  return (
    <div className="center-screen">
      <div className="card auth-card">
        <div className="brand">
          <span className="dot" />
          FinPay
        </div>
        <h1>Move money in real time.</h1>
        <p className="muted">
          A production-oriented fintech wallet: secure authentication, an
          idempotent transaction engine, and live Socket.IO updates backed by a
          persistent source of truth.
        </p>
        <div className="mt-lg">
          <Link to="/register">
            <button className="btn-primary">Create account</button>
          </Link>
          <div className="spacer" />
          <Link to="/login">
            <button className="btn-ghost" style={{ width: "100%" }}>
              I already have an account
            </button>
          </Link>
        </div>
      </div>
    </div>
  );
}
