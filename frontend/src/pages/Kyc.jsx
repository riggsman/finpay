import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import CameraCapture from "../components/CameraCapture";
import { kycApi } from "../api/kyc";
import { getAccessToken } from "../api/client";
import { socketService } from "../services/socketService";

const PREV_STEP = {
  personal: "intro",
  address: "personal",
  id: "address",
  selfie: "id",
  review: "selfie",
};

const STATUS_LABEL = {
  NOT_STARTED: { cls: "down", text: "Not started" },
  IN_PROGRESS: { cls: "reconnecting", text: "In progress" },
  UNDER_REVIEW: { cls: "reconnecting", text: "Under review" },
  APPROVED: { cls: "live", text: "Approved" },
  REJECTED: { cls: "down", text: "Rejected" },
};

const TITLES = {
  intro: "Identity verification",
  personal: "Personal information",
  address: "Address",
  id: "Identity document",
  selfie: "Selfie",
  review: "Review & submit",
  status: "Verification status",
};

const EMPTY = {
  first_name: "", last_name: "", date_of_birth: "",
  address_line: "", city: "", country: "",
  id_type: "", id_number: "",
  id_document_ref: "", id_document_back_ref: "", selfie_ref: "",
};

function mediaUrl(ref) {
  if (!ref) return null;
  if (String(ref).startsWith("data:")) return ref;
  return `/api/v1/me/kyc/media/${encodeURIComponent(ref)}`;
}

async function fetchMediaBlob(ref) {
  if (!ref) return null;
  const token = getAccessToken();
  const res = await fetch(mediaUrl(ref), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) return null;
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export default function Kyc() {
  const navigate = useNavigate();
  const [step, setStep] = useState("intro");
  const [form, setForm] = useState(EMPTY);
  const [previews, setPreviews] = useState({ front: null, back: null, selfie: null });
  const [status, setStatus] = useState("NOT_STARTED");
  const [rejectionReason, setRejectionReason] = useState(null);
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef(null);
  const toastRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    const objectUrls = [];

    async function hydrate() {
      try {
        const k = await kycApi.get();
        if (cancelled) return;
        setStatus(k.status);
        setRejectionReason(k.rejection_reason || null);
        setForm((f) => ({
          ...f,
          ...Object.fromEntries(Object.keys(EMPTY).map((key) => [key, k[key] ?? f[key]])),
        }));

        const nextPreviews = { front: null, back: null, selfie: null };
        const pairs = [
          ["front", k.id_document_ref],
          ["back", k.id_document_back_ref],
          ["selfie", k.selfie_ref],
        ];
        for (const [kind, ref] of pairs) {
          if (!ref) continue;
          const url = await fetchMediaBlob(ref);
          if (url) {
            objectUrls.push(url);
            nextPreviews[kind] = url;
          }
        }
        if (!cancelled) setPreviews(nextPreviews);

        if (k.status === "UNDER_REVIEW" || k.status === "APPROVED" || k.status === "REJECTED") {
          setStep("status");
          if (k.status === "UNDER_REVIEW") listenForDecision();
        }
      } catch {
        /* ignore */
      }
    }

    hydrate();
    return () => {
      cancelled = true;
      objectUrls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, []);

  useEffect(() => () => {
    clearInterval(pollRef.current);
    clearTimeout(toastRef.current);
  }, []);

  useEffect(() => {
    const onNotif = (evt) => {
      const d = evt?.data;
      if (!d) return;
      if (d.type === "KYC_APPROVED" || d.type === "KYC_REJECTED") {
        setToast(`${d.title} — ${d.message}`);
        clearTimeout(toastRef.current);
        toastRef.current = setTimeout(() => setToast(null), 6000);
      }
    };
    const onKyc = (evt) => {
      if (!evt?.data?.status) return;
      setStatus(evt.data.status);
      if (evt.data.rejection_reason) setRejectionReason(evt.data.rejection_reason);
      setStep("status");
    };
    socketService.on("notification:new", onNotif);
    socketService.on("KYC_STATUS_UPDATED", onKyc);
    return () => {
      socketService.off("notification:new", onNotif);
      socketService.off("KYC_STATUS_UPDATED", onKyc);
    };
  }, []);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  function leaveFlow() {
    if (window.history.length > 1) navigate(-1);
    else navigate("/profile");
  }

  function goBack() {
    if (PREV_STEP[step]) {
      setError(null);
      setStep(PREV_STEP[step]);
      return;
    }
    leaveFlow();
  }

  async function saveDraft(extra = {}) {
    const payload = { ...form, ...extra };
    const { id_document_ref, id_document_back_ref, selfie_ref, ...rest } = payload;
    await kycApi.update({ ...rest, id_document_ref, id_document_back_ref, selfie_ref });
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

  async function onCapture(kind, dataUrl) {
    setBusy(true);
    setError(null);
    try {
      const res = await kycApi.capture(kind, dataUrl);
      const field = res.field;
      setForm((f) => ({ ...f, [field]: res.ref }));
      setPreviews((p) => ({ ...p, [kind]: dataUrl }));
    } finally {
      setBusy(false);
    }
  }

  function listenForDecision() {
    clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const k = await kycApi.get();
        setStatus(k.status);
        setRejectionReason(k.rejection_reason || null);
        if (k.status === "APPROVED" || k.status === "REJECTED") {
          clearInterval(pollRef.current);
          setStep("status");
        }
      } catch { /* ignore */ }
    }, 1500);
  }

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      await saveDraft();
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
  const docRequirements = [
    { key: "id_type", label: "Document type", done: Boolean(form.id_type) },
    { key: "id_number", label: "Document number", done: Boolean(String(form.id_number || "").trim()) },
    { key: "front", label: "Front of document (camera)", done: Boolean(form.id_document_ref) },
    { key: "back", label: "Back of document (camera)", done: Boolean(form.id_document_back_ref) },
  ];
  const docsReady = docRequirements.every((r) => r.done);

  function validateDocumentStep() {
    const missing = docRequirements.filter((r) => !r.done).map((r) => r.label);
    if (missing.length) {
      setError(`Required: ${missing.join(", ")}.`);
      return false;
    }
    setError(null);
    return true;
  }

  return (
    <AppShell title={TITLES[step] || "Identity verification"} backTo={goBack} showNav className="dash-screen">
      {toast && <div className="toast-banner alert alert-info">{toast}</div>}

      <div className="kyc-flow">
        {step === "intro" && (
          <>
            <h2 className="kyc-heading">Verify your identity</h2>
            <p className="screen-desc" style={{ paddingLeft: 0, paddingRight: 0 }}>
              You will capture the front and back of your ID with your camera, then take a live selfie.
              Gallery uploads are not accepted.
            </p>
            <span className={`pill ${label.cls}`}><span className="status-dot" /> {label.text}</span>
            <div className="mt-lg">
              <button type="button" className="btn-primary" onClick={() => setStep("personal")}>Start verification</button>
            </div>
          </>
        )}

        {step === "personal" && (
          <>
            <div className="row">
              <div>
                <label>First name <span className="req">*</span></label>
                <input value={form.first_name} onChange={set("first_name")} required />
              </div>
              <div>
                <label>Last name <span className="req">*</span></label>
                <input value={form.last_name} onChange={set("last_name")} required />
              </div>
            </div>
            <label>Date of birth <span className="req">*</span></label>
            <input type="date" value={form.date_of_birth || ""} onChange={set("date_of_birth")} required />
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button
                type="button"
                className="btn-primary"
                disabled={busy || !form.first_name || !form.last_name || !form.date_of_birth}
                onClick={() => next("address")}
              >
                Continue
              </button>
            </div>
          </>
        )}

        {step === "address" && (
          <>
            <label>Address line <span className="req">*</span></label>
            <input value={form.address_line} onChange={set("address_line")} required />
            <div className="row">
              <div>
                <label>City <span className="req">*</span></label>
                <input value={form.city} onChange={set("city")} required />
              </div>
              <div>
                <label>Country <span className="req">*</span></label>
                <input value={form.country} onChange={set("country")} required />
              </div>
            </div>
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button
                type="button"
                className="btn-primary"
                disabled={busy || !form.address_line || !form.city || !form.country}
                onClick={() => next("id")}
              >
                Continue
              </button>
            </div>
          </>
        )}

        {step === "id" && (
          <>
            <h2 className="kyc-heading">Document capture</h2>
            <p className="screen-desc" style={{ paddingLeft: 0, paddingRight: 0 }}>
              Provide your document details and capture both sides with your camera. All fields below are required.
            </p>

            <ul className="req-checklist">
              {docRequirements.map((r) => (
                <li key={r.key} className={r.done ? "done" : ""}>
                  <span className="req-check">{r.done ? "✓" : "○"}</span>
                  {r.label}
                </li>
              ))}
            </ul>

            <label htmlFor="kyc-id-type">Document type <span className="req">*</span></label>
            <select
              id="kyc-id-type"
              value={form.id_type}
              onChange={set("id_type")}
              required
            >
              <option value="">Select document type</option>
              <option value="national_id">National ID</option>
              <option value="passport">Passport</option>
              <option value="drivers_license">Driver's license</option>
            </select>

            <label htmlFor="kyc-id-number">Document number <span className="req">*</span></label>
            <input
              id="kyc-id-number"
              value={form.id_number}
              onChange={set("id_number")}
              placeholder="e.g. CM123456789"
              required
              autoComplete="off"
            />

            <div className="capture-stack">
              <div className="capture-block">
                <div className="capture-block-head">
                  <h3>Front of document <span className="req">*</span></h3>
                  <span className={`capture-status ${form.id_document_ref ? "ok" : ""}`}>
                    {form.id_document_ref ? "Captured" : "Required"}
                  </span>
                </div>
                <p className="muted small">Photograph the front side clearly. Gallery upload is not allowed.</p>
                <CameraCapture
                  label="Front of document"
                  facingMode="environment"
                  value={form.id_document_ref}
                  previewUrl={previews.front}
                  busy={busy}
                  required
                  onCaptured={(dataUrl) => onCapture("front", dataUrl)}
                />
              </div>

              <div className="capture-block">
                <div className="capture-block-head">
                  <h3>Back of document <span className="req">*</span></h3>
                  <span className={`capture-status ${form.id_document_back_ref ? "ok" : ""}`}>
                    {form.id_document_back_ref ? "Captured" : "Required"}
                  </span>
                </div>
                <p className="muted small">Photograph the back side. For passports, capture the page opposite the biodata page if needed.</p>
                <CameraCapture
                  label="Back of document"
                  facingMode="environment"
                  value={form.id_document_back_ref}
                  previewUrl={previews.back}
                  busy={busy}
                  required
                  onCaptured={(dataUrl) => onCapture("back", dataUrl)}
                />
              </div>
            </div>

            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button
                type="button"
                className="btn-primary"
                disabled={busy || !docsReady}
                onClick={() => {
                  if (!validateDocumentStep()) return;
                  next("selfie");
                }}
              >
                Continue to selfie
              </button>
              {!docsReady && (
                <p className="muted small" style={{ marginTop: 8 }}>
                  Complete document type, number, front photo, and back photo to continue.
                </p>
              )}
            </div>
          </>
        )}

        {step === "selfie" && (
          <>
            <h2 className="kyc-heading">Live selfie <span className="req">*</span></h2>
            <p className="screen-desc" style={{ paddingLeft: 0, paddingRight: 0 }}>
              Take a live selfie with your front camera so we can match it to your ID. Gallery upload is not allowed.
            </p>
            <CameraCapture
              label="Live selfie"
              facingMode="user"
              value={form.selfie_ref}
              previewUrl={previews.selfie}
              busy={busy}
              required
              onCaptured={(dataUrl) => onCapture("selfie", dataUrl)}
            />
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button type="button" className="btn-primary" disabled={busy || !form.selfie_ref} onClick={() => next("review")}>Continue</button>
            </div>
          </>
        )}

        {step === "review" && (
          <>
            <div className="review-row"><span className="muted">Name</span><span>{form.first_name} {form.last_name}</span></div>
            <div className="review-row"><span className="muted">Date of birth</span><span>{form.date_of_birth}</span></div>
            <div className="review-row"><span className="muted">Address</span><span>{form.address_line}, {form.city}, {form.country}</span></div>
            <div className="review-row"><span className="muted">ID</span><span>{form.id_type} · {form.id_number}</span></div>
            <div className="review-row">
              <span className="muted">Documents</span>
              <span>
                {form.id_document_ref ? "Front ✓" : "Front ✕"}{" "}
                {form.id_document_back_ref ? "Back ✓" : "Back ✕"}{" "}
                {form.selfie_ref ? "Selfie ✓" : "Selfie ✕"}
              </span>
            </div>
            <div className="capture-stack review-thumbs">
              {previews.front && <img src={previews.front} alt="ID front" className="capture-thumb" />}
              {previews.back && <img src={previews.back} alt="ID back" className="capture-thumb" />}
              {previews.selfie && <img src={previews.selfie} alt="Selfie" className="capture-thumb" />}
            </div>
            {error && <div className="alert alert-error">{error}</div>}
            <div className="mt-lg">
              <button type="button" className="btn-accent" style={{ width: "100%" }} disabled={busy} onClick={submit}>Submit for verification</button>
            </div>
          </>
        )}

        {step === "status" && (
          <div className="center">
            {status === "APPROVED" ? (
              <>
                <div className="result-icon success">✓</div>
                <h2 className="kyc-heading mt">Successful KYC verification</h2>
                <p className="muted">Your identity has been verified. A confirmation was sent in-app and by email.</p>
              </>
            ) : status === "REJECTED" ? (
              <>
                <div className="result-icon failed">✕</div>
                <h2 className="kyc-heading mt">KYC verification rejected</h2>
                <p className="muted">{rejectionReason || "Please review your details and resubmit."}</p>
                <p className="muted small">You also received an in-app notification and email about this decision.</p>
              </>
            ) : (
              <>
                <div className="spinner" />
                <h2 className="kyc-heading mt">Under review</h2>
                <p className="muted">We're verifying your identity. You will get an in-app notification and email when a decision is made.</p>
              </>
            )}
            <span className={`pill ${label.cls} mt`}><span className="status-dot" /> {label.text}</span>
            <div className="mt-lg">
              {status === "REJECTED" ? (
                <button type="button" className="btn-primary" onClick={() => setStep("personal")}>Edit &amp; resubmit</button>
              ) : (
                <button type="button" className="btn-primary" onClick={leaveFlow}>Done</button>
              )}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
}
