import { Link } from "react-router-dom";

export default function Landing() {
  return (
    <div className="app-viewport">
      <div className="app-frame">
        <div className="app-scroll" style={{ display: "grid", placeItems: "center", padding: 24 }}>
          <div style={{ width: "100%" }}>
            <div className="brand" style={{ marginBottom: 24 }}>
              <span className="dot" />
              FinPay
            </div>
            <h1>Move money in real time.</h1>
            <p className="muted">
              Pay bills, send money, and manage your wallet with the same mobile experience on every screen size.
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
      </div>
    </div>
  );
}
