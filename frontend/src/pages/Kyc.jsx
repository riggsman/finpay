import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { kycApi } from "../api/kyc";
import { socketService } from "../services/socketService";

const STEPS = ["intro", "personal", "address", "id", "selfie", "review", "status"];

const STATUS_LABEL = {
  NOT_STARTED: { cls: "down", text: "Not started" },
  IN_PROGRESS: { cls: "reconnecting", text: "In progress" },
  UNDER_REVIEW: { cls: "reconnecting", text: "Under review" },
  APPROVED: { cls: "live", text: "Approved" },
  REJECTED: { cls: "down", text: "Rejected" },
};

const EMPTY = {
  first_name: "", last_name: "", date_of_birth: "",
  address_line: "", city: "", country: "",
  id_type: "national_id", id_number: "",
  id_document_ref: "", selfie_ref: "",
};

export default function Kyc() {
  const navigate = useNavigate();
  const [step, setStep] = useState("intro");
  const [form, setForm] = useState(EMPTY);
  const [status, setStatus] = useState("NOT_STARTED");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    kycApi.get().then((k) => {
      setStatus(k.status);
      setForm((f) => ({
        ...f,
        ...Object.fromEntries(Object.keys(EMPTY).map((key) => [key, k[key] ?? f[key]])),
      }));
      if (k.status === "UNDER_REVIEW") setStep("status");
    }).catch(() => {});
  }, []);

  useEffect(() => () => clearInterval(pollRef.current), []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function saveDraft() {
    const { id_document_ref, selfie_ref, ...rest } = form;
    await kycApi.update({ ...rest, id_document_ref, selfie_ref });
  }

  async function next(target) {
    setError(null);
    setBusy(true);
    try {
      await saveDraft();
      setStep(target);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function listenForDecision() {
    const onUpdate = (evt) => {
      if (evt?.data?.status) setStatus(evt.data.status);
    };
    socketService.on("KYC_STATUS_UPDATED", onUpdate);
    pollRef.current = setInterval(async () => {
      try {
        const k = await kycApi.get();
        setStatus(k.status);
        if (k.status === "APPROVED" || k.status === "REJECTED") {
          clearInterval(pollRef.current);
        }
      } catch { /* ignore */ }
    }, 1000);
  }

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const k = await kycApi.submit();
      setStatus(k.status);
      setStep("status");
      listenForDecision();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const label = STATUS_LABEL[status] || STATUS_LABEL.NOT_STARTED;

  return (
    <div className="center-screen">
      <div className="card auth-card" style={{ maxWidth: 480 }}>
        <div className="topbar" style={{ padding: 0, marginBottom: 8 }}>
          <div className="brand"><span className="dot" /> FinPay</div>
          <button className="btn-ghost" onClick={() => navigate("/dashboard")}>← Dashboard</button>
        </div>

        {step === "intro" && (
          <>
            <h1>Verify your identity</h1>
            <p className="muted">
              Complete KYC to raise your transaction limits. You'll need your
              personal details, an ID document, and a selfie.
            </p>
            <span className={`pill ${label.cls}`}><span className="status-dot" /> {label.text}</span>
            <div className="mt-lg">
              <button className="btn-primary" onClick={() => setStep("personal")}>Start verification</button>
            </div>
          </>
        )}

        {step === "personal" && (
          <>
            <h1>Personal information</h1>
            <div className="row">
              <div><label>First name</label><input value={form.first_name} onChange={set("first_name")} /></div>
              <div><label>Last name</label><input value={form.last_name} onChange={set("last_name")} /></div>
            </div>
            <label>Date of birth</label>
            <input type="date" value={form.date_of_birth || ""} onChange={set("date_of_birth")} />
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg"><button className="btn-primary" disabled={busy} onClick={() => next("address")}>Continue</button></div>
          </>
        )}

        {step === "address" && (
          <>
            <h1>Address</h1>
            <label>Address line</label>
            <input value={form.address_line} onChange={set("address_line")} />
            <div className="row">
              <div><label>City</label><input value={form.city} onChange={set("city")} /></div>
              <div><label>Country</label><input value={form.country} onChange={set("country")} /></div>
            </div>
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg"><button className="btn-primary" disabled={busy} onClick={() => next("id")}>Continue</button></div>
          </>
        )}

        {step === "id" && (
          <>
            <h1>Identity document</h1>
            <label>ID type</label>
            <select value={form.id_type} onChange={set("id_type")}>
              <option value="national_id">National ID</option>
              <option value="passport">Passport</option>
              <option value="drivers_license">Driver's license</option>
            </select>
            <label>ID number</label>
            <input value={form.id_number} onChange={set("id_number")} placeholder="CM123456789" />
            <label>ID document</label>
            <button
              className={`btn-ghost ${form.id_document_ref ? "" : ""}`}
              style={{ width: "100%" }}
              onClick={() => setForm({ ...form, id_document_ref: `id_${Date.now()}.jpg` })}
            >
              {form.id_document_ref ? `✓ ${form.id_document_ref}` : "Upload ID document"}
            </button>
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button className="btn-primary" disabled={busy || !form.id_number || !form.id_document_ref} onClick={() => next("selfie")}>Continue</button>
            </div>
          </>
        )}

        {step === "selfie" && (
          <>
            <h1>Selfie / liveness</h1>
            <p className="muted">Take a selfie so we can match it to your ID.</p>
            <button
              className="btn-ghost"
              style={{ width: "100%" }}
              onClick={() => setForm({ ...form, selfie_ref: `selfie_${Date.now()}.jpg` })}
            >
              {form.selfie_ref ? `✓ ${form.selfie_ref}` : "Capture selfie"}
            </button>
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button className="btn-primary" disabled={busy || !form.selfie_ref} onClick={() => next("review")}>Continue</button>
            </div>
          </>
        )}

        {step === "review" && (
          <>
            <h1>Review &amp; submit</h1>
            <div className="review-row"><span className="muted">Name</span><span>{form.first_name} {form.last_name}</span></div>
            <div className="review-row"><span className="muted">Date of birth</span><span>{form.date_of_birth}</span></div>
            <div className="review-row"><span className="muted">Address</span><span>{form.address_line}, {form.city}, {form.country}</span></div>
            <div className="review-row"><span className="muted">ID</span><span>{form.id_type} · {form.id_number}</span></div>
            <div className="review-row"><span className="muted">Documents</span><span>{form.id_document_ref ? "ID ✓" : "—"} {form.selfie_ref ? "Selfie ✓" : ""}</span></div>
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button className="btn-accent" style={{ width: "100%" }} disabled={busy} onClick={submit}>Submit for verification</button>
              <div className="spacer" />
              <button className="btn-ghost" style={{ width: "100%" }} onClick={() => setStep("id")}>Back</button>
            </div>
          </>
        )}

        {step === "status" && (
          <div className="center">
            {status === "APPROVED" ? (
              <>
                <div className="result-icon success">✓</div>
                <h1 className="mt">Identity verified</h1>
                <p className="muted">Your limits have been raised.</p>
              </>
            ) : status === "REJECTED" ? (
              <>
                <div className="result-icon failed">✕</div>
                <h1 className="mt">Verification failed</h1>
                <p className="muted">Please review your details and resubmit.</p>
              </>
            ) : (
              <>
                <div className="spinner" />
                <h1 className="mt">Under review</h1>
                <p className="muted">We're verifying your identity. This updates live.</p>
              </>
            )}
            <span className={`pill ${label.cls} mt`}><span className="status-dot" /> {label.text}</span>
            <div className="mt-lg">
              {status === "REJECTED" ? (
                <button className="btn-primary" onClick={() => setStep("personal")}>Edit &amp; resubmit</button>
              ) : (
                <button className="btn-primary" onClick={() => navigate("/dashboard")}>Done</button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
