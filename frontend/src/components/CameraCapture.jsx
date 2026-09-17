import { useEffect, useRef, useState } from "react";

/**
 * Camera-only capture for KYC. Gallery upload is not offered.
 * Uses getUserMedia when available; falls back to capture= input (camera on mobile).
 */
export default function CameraCapture({
  label,
  facingMode = "environment",
  value,
  previewUrl,
  onCaptured,
  busy = false,
  required = false,
}) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const fileRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [live, setLive] = useState(false);
  const [error, setError] = useState(null);
  const [capturing, setCapturing] = useState(false);

  useEffect(() => () => stopStream(), []);

  function stopStream() {
    streamRef.current?.getTracks()?.forEach((t) => t.stop());
    streamRef.current = null;
    setLive(false);
  }

  async function startCamera() {
    setError(null);
    setOpen(true);
    stopStream();
    if (!navigator.mediaDevices?.getUserMedia) {
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: {
          facingMode: { ideal: facingMode },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      });
      streamRef.current = stream;
      setLive(true);
      // Attach after paint so video element exists.
      requestAnimationFrame(async () => {
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
      });
    } catch (err) {
      setError(err.message || "Camera permission is required.");
    }
  }

  function closeCamera() {
    stopStream();
    setOpen(false);
  }

  function canvasFromVideo() {
    const video = videoRef.current;
    if (!video || !video.videoWidth) return null;
    const max = 1280;
    const scale = Math.min(1, max / Math.max(video.videoWidth, video.videoHeight));
    const w = Math.round(video.videoWidth * scale);
    const h = Math.round(video.videoHeight * scale);
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    canvas.getContext("2d").drawImage(video, 0, 0, w, h);
    return canvas.toDataURL("image/jpeg", 0.85);
  }

  async function takePhoto() {
    setCapturing(true);
    setError(null);
    try {
      const dataUrl = canvasFromVideo();
      if (!dataUrl) {
        setError("Camera is not ready yet. Wait a moment and try again.");
        return;
      }
      await onCaptured(dataUrl);
      closeCamera();
    } catch (err) {
      setError(err.message || "Could not save capture.");
    } finally {
      setCapturing(false);
    }
  }

  async function onFileChange(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setCapturing(true);
    setError(null);
    try {
      const dataUrl = await readAsDataUrl(file);
      await onCaptured(dataUrl);
      closeCamera();
    } catch (err) {
      setError(err.message || "Could not save capture.");
    } finally {
      setCapturing(false);
    }
  }

  return (
    <div className="camera-capture">
      <div className="capture-preview">
        {previewUrl ? (
          <img src={previewUrl} alt="" className="capture-thumb" />
        ) : (
          <div className="capture-placeholder">No photo yet</div>
        )}
        <div className="capture-meta">
          <strong>{label}</strong>
          <span className="muted small">
            {value ? "Captured ✓" : required ? "Required — camera only" : "Camera required"}
          </span>
        </div>
      </div>

      <button type="button" className="btn-ghost" style={{ width: "100%" }} disabled={busy || capturing} onClick={startCamera}>
        {value ? "Retake with camera" : "Open camera"}
      </button>

      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        capture={facingMode === "user" ? "user" : "environment"}
        hidden
        onChange={onFileChange}
      />

      {error && !open && <div className="alert alert-error">{error}</div>}

      {open && (
        <div className="camera-modal" role="dialog" aria-modal="true" aria-label={label}>
          <div className="camera-sheet">
            <div className="camera-sheet-head">
              <strong>{label}</strong>
              <button type="button" className="btn-ghost" onClick={closeCamera}>Close</button>
            </div>
            <p className="muted small">Use your device camera. Photo library upload is not allowed.</p>
            {live ? (
              <video ref={videoRef} className="camera-video" playsInline muted autoPlay />
            ) : (
              <div className="capture-placeholder tall">
                {error || "Starting camera… If preview fails, use the device camera app below."}
              </div>
            )}
            {error && live && <div className="alert alert-error">{error}</div>}
            <div className="camera-actions">
              <button type="button" className="btn-primary" disabled={capturing || busy || !live} onClick={takePhoto}>
                {capturing ? "Saving…" : "Capture photo"}
              </button>
              <button
                type="button"
                className="btn-ghost"
                disabled={capturing || busy}
                onClick={() => fileRef.current?.click()}
              >
                Use device camera app
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function readAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) {
      reject(new Error("Please capture an image."));
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read capture."));
    reader.onload = () => resolve(reader.result);
    reader.readAsDataURL(file);
  });
}
