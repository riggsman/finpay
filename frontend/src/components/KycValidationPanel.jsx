import { useEffect, useMemo, useState } from "react";
import { getAccessToken } from "../api/client";

const STEPS = [
  { id: "personal", label: "Personal", short: "1. Personal" },
  { id: "address", label: "Address", short: "2. Address" },
  { id: "document", label: "Documents", short: "3. Documents" },
  { id: "selfie", label: "Selfie", short: "4. Selfie" },
  { id: "review", label: "Final review", short: "5. Review" },
];

const EMPTY_CHECKS = {
  personal: "pending",
  address: "pending",
  document: "pending",
  selfie: "pending",
};

function Field({ label, value }) {
  return (
    <div className="kyc-val-field">
      <span className="muted">{label}</span>
      <strong>{value || "—"}</strong>
    </div>
  );
}

function MediaPane({ title, src, emptyLabel, onOpen }) {
  return (
    <div className="kyc-media-pane">
      <div className="kyc-media-pane-head">
        <strong>{title}</strong>
        {src && (
          <button type="button" className="btn-ghost" onClick={() => onOpen(src, title)}>
            Enlarge
          </button>
        )}
      </div>
      {src ? (
        <button type="button" className="kyc-media-frame" onClick={() => onOpen(src, title)}>
          <img src={src} alt={title} />
        </button>
      ) : (
        <div className="kyc-media-empty">{emptyLabel || "No image uploaded"}</div>
      )}
    </div>
  );
}

function StepActions({ stepId, checks, setCheck, canValidate }) {
  if (!canValidate || stepId === "review") return null;
  const status = checks[stepId];
  return (
    <div className="kyc-step-actions">
      <button
        type="button"
        className={`btn-ghost ${status === "passed" ? "kyc-pass-active" : ""}`}
        onClick={() => setCheck(stepId, "passed")}
      >
        Mark validated
      </button>
      <button
        type="button"
        className={`btn-ghost ${status === "failed" ? "kyc-fail-active" : ""}`}
        onClick={() => setCheck(stepId, "failed")}
      >
        Flag issue
      </button>
      {status !== "pending" && (
        <button type="button" className="btn-ghost" onClick={() => setCheck(stepId, "pending")}>
          Reset
        </button>
      )}
    </div>
  );
}

async function loadBlob(kycId, ref) {
  if (!ref || !kycId) return null;
  const token = getAccessToken();
  const res = await fetch(`/api/v1/admin/kyc/${kycId}/media/${encodeURIComponent(ref)}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) return null;
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export default function KycValidationPanel({
  kyc,
  rejectReason,
  setRejectReason,
  onApprove,
  onReject,
  busy = false,
}) {
  const [step, setStep] = useState("personal");
  const [checks, setChecks] = useState({ ...EMPTY_CHECKS });
  const [media, setMedia] = useState({ front: null, back: null, selfie: null });
  const [lightbox, setLightbox] = useState(null);

  const canValidateSteps = kyc?.status === "UNDER_REVIEW";
  const canApprove = kyc?.status === "UNDER_REVIEW";
  const canReject = kyc?.status === "UNDER_REVIEW" || kyc?.status === "APPROVED";
  const validationSteps = useMemo(() => ["personal", "address", "document", "selfie"], []);
  const allPassed = validationSteps.every((id) => checks[id] === "passed");
  const anyFailed = validationSteps.some((id) => checks[id] === "failed");

  useEffect(() => {
    setStep("personal");
    setChecks({ ...EMPTY_CHECKS });
    setLightbox(null);
  }, [kyc?.id]);

  useEffect(() => {
    let cancelled = false;
    const urls = [];

    async function hydrate() {
      if (!kyc?.id) {
        setMedia({ front: null, back: null, selfie: null });
        return;
      }
      const [front, back, selfie] = await Promise.all([
        loadBlob(kyc.id, kyc.id_document_ref),
        loadBlob(kyc.id, kyc.id_document_back_ref),
        loadBlob(kyc.id, kyc.selfie_ref),
      ]);
      [front, back, selfie].forEach((u) => u && urls.push(u));
      if (!cancelled) setMedia({ front, back, selfie });
    }

    hydrate();
    return () => {
      cancelled = true;
      urls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, [kyc?.id, kyc?.id_document_ref, kyc?.id_document_back_ref, kyc?.selfie_ref]);

  function setCheck(id, value) {
    setChecks((prev) => ({ ...prev, [id]: value }));
  }

  function statusBadge(id) {
    const s = checks[id];
    if (s === "passed") return "ok";
    if (s === "failed") return "bad";
    return "pending";
  }

  if (!kyc) {
    return <p className="muted">Select a KYC row to open the validation workspace.</p>;
  }

  return (
    <div className="kyc-validation">
      <div className="kyc-val-top">
        <div>
          <div className="muted small">KYC #{kyc.id} · User #{kyc.user_id}</div>
          <strong>{kyc.first_name} {kyc.last_name}</strong>
          <div className="muted small">{kyc.user_phone} · {kyc.user_status || "—"}</div>
        </div>
        <span className={`badge ${kyc.status}`}>{kyc.status}</span>
      </div>

      <div className="kyc-step-nav" role="tablist" aria-label="KYC validation steps">
        {STEPS.map((s) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={step === s.id}
            className={`kyc-step-tab ${step === s.id ? "active" : ""} ${s.id !== "review" ? statusBadge(s.id) : ""}`}
            onClick={() => setStep(s.id)}
          >
            <span className="kyc-step-label">{s.short}</span>
            {s.id !== "review" && (
              <span className="kyc-step-dot" aria-hidden>
                {checks[s.id] === "passed" ? "✓" : checks[s.id] === "failed" ? "!" : "·"}
              </span>
            )}
          </button>
        ))}
      </div>

      <div className="kyc-step-body">
        {step === "personal" && (
          <>
            <h3>Personal information</h3>
            <p className="muted small">Confirm the applicant’s identity details look consistent and complete.</p>
            <div className="kyc-val-grid">
              <Field label="First name" value={kyc.first_name} />
              <Field label="Last name" value={kyc.last_name} />
              <Field label="Date of birth" value={kyc.date_of_birth} />
              <Field label="Account phone" value={kyc.user_phone} />
              <Field label="Account email" value={kyc.user_email} />
            </div>
            <StepActions stepId="personal" checks={checks} setCheck={setCheck} canValidate={canValidateSteps} />
          </>
        )}

        {step === "address" && (
          <>
            <h3>Location / address</h3>
            <p className="muted small">Validate that the residential address is plausible and fully filled in.</p>
            <div className="kyc-val-grid">
              <Field label="Address line" value={kyc.address_line} />
              <Field label="City" value={kyc.city} />
              <Field label="Country" value={kyc.country} />
            </div>
            <StepActions stepId="address" checks={checks} setCheck={setCheck} canValidate={canValidateSteps} />
          </>
        )}

        {step === "document" && (
          <>
            <h3>Document validation</h3>
            <p className="muted small">
              Review document metadata, then compare front and back side by side.
            </p>
            <div className="kyc-val-grid">
              <Field label="Document type" value={kyc.id_type} />
              <Field label="Document number" value={kyc.id_number} />
            </div>
            <div className="kyc-media-pair">
              <MediaPane
                title="Document front"
                src={media.front}
                emptyLabel="Front capture missing"
                onOpen={(src, title) => setLightbox({ src, title })}
              />
              <MediaPane
                title="Document back"
                src={media.back}
                emptyLabel="Back capture missing"
                onOpen={(src, title) => setLightbox({ src, title })}
              />
            </div>
            <StepActions stepId="document" checks={checks} setCheck={setCheck} canValidate={canValidateSteps} />
          </>
        )}

        {step === "selfie" && (
          <>
            <h3>Selfie validation</h3>
            <p className="muted small">
              Compare the live selfie with the document front photo. Faces and identity details should match.
            </p>
            <div className="kyc-media-pair">
              <MediaPane
                title="Document front"
                src={media.front}
                emptyLabel="Front capture missing"
                onOpen={(src, title) => setLightbox({ src, title })}
              />
              <MediaPane
                title="Live selfie"
                src={media.selfie}
                emptyLabel="Selfie capture missing"
                onOpen={(src, title) => setLightbox({ src, title })}
              />
            </div>
            <StepActions stepId="selfie" checks={checks} setCheck={setCheck} canValidate={canValidateSteps} />
          </>
        )}

        {step === "review" && (
          <>
            <h3>Final review</h3>
            <p className="muted small">
              Confirm every section below, then approve or reject.
              {canApprove
                ? " Approval requires all validation steps to be marked validated."
                : ""}
              {kyc.status === "APPROVED"
                ? " This KYC is approved and can still be rejected. A rejected KYC cannot be approved again."
                : ""}
              {kyc.status === "REJECTED"
                ? " This KYC was rejected and cannot be approved again."
                : ""}
            </p>

            <div className="kyc-review-checks">
              {validationSteps.map((id) => {
                const meta = STEPS.find((s) => s.id === id);
                return (
                  <button
                    key={id}
                    type="button"
                    className={`kyc-review-check ${statusBadge(id)}`}
                    onClick={() => setStep(id)}
                  >
                    <strong>{meta?.label}</strong>
                    <span>
                      {checks[id] === "passed"
                        ? "Validated"
                        : checks[id] === "failed"
                          ? "Issue flagged"
                          : "Not reviewed"}
                    </span>
                  </button>
                );
              })}
            </div>

            <div className="kyc-val-grid mt">
              <Field label="Name" value={`${kyc.first_name || ""} ${kyc.last_name || ""}`.trim()} />
              <Field label="Date of birth" value={kyc.date_of_birth} />
              <Field label="Address" value={[kyc.address_line, kyc.city, kyc.country].filter(Boolean).join(", ")} />
              <Field label="Document" value={`${kyc.id_type || "—"} · ${kyc.id_number || "—"}`} />
              <Field label="Submitted" value={kyc.submitted_at ? new Date(kyc.submitted_at).toLocaleString() : "—"} />
            </div>

            <div className="kyc-media-triple">
              <MediaPane title="Front" src={media.front} onOpen={(src, title) => setLightbox({ src, title })} />
              <MediaPane title="Back" src={media.back} onOpen={(src, title) => setLightbox({ src, title })} />
              <MediaPane title="Selfie" src={media.selfie} onOpen={(src, title) => setLightbox({ src, title })} />
            </div>

            {(canApprove || canReject) ? (
              <>
                {canApprove && anyFailed && (
                  <div className="alert alert-error">
                    One or more steps are flagged. Reject with a reason, or revisit those steps.
                  </div>
                )}
                {canApprove && !allPassed && !anyFailed && (
                  <div className="alert alert-info">
                    Mark personal, address, documents, and selfie as validated before approving.
                  </div>
                )}
                {canReject && (
                  <>
                    <label>Rejection reason {canApprove ? "(required when rejecting)" : "(required)"}</label>
                    <input
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      placeholder="Shown to the user if rejected"
                    />
                  </>
                )}
                <div className="row mt" style={{ maxWidth: 420 }}>
                  {canApprove && (
                    <button
                      className="btn-accent"
                      type="button"
                      disabled={busy || !allPassed}
                      onClick={() => onApprove(kyc.id)}
                    >
                      Approve KYC
                    </button>
                  )}
                  {canReject && (
                    <button
                      className="btn-ghost"
                      type="button"
                      disabled={busy || (kyc.status === "APPROVED" && !String(rejectReason || "").trim())}
                      onClick={() => onReject(kyc.id)}
                    >
                      Reject KYC
                    </button>
                  )}
                </div>
              </>
            ) : (
              <p className="muted mt">
                This submission is already {kyc.status}.
                {kyc.rejection_reason ? ` Reason: ${kyc.rejection_reason}` : ""}
                {kyc.status === "REJECTED" ? " It cannot be approved again." : ""}
              </p>
            )}
          </>
        )}
      </div>

      {step !== "review" && (canApprove || canReject) && (
        <div className="kyc-step-footer">
          <button type="button" className="btn-ghost" onClick={() => setStep("review")}>
            Jump to final review →
          </button>
        </div>
      )}

      {lightbox && (
        <div className="kyc-lightbox" role="dialog" aria-modal="true" onClick={() => setLightbox(null)}>
          <div className="kyc-lightbox-inner" onClick={(e) => e.stopPropagation()}>
            <div className="kyc-lightbox-head">
              <strong>{lightbox.title}</strong>
              <button type="button" className="btn-ghost" onClick={() => setLightbox(null)}>Close</button>
            </div>
            <img src={lightbox.src} alt={lightbox.title} />
          </div>
        </div>
      )}
    </div>
  );
}
