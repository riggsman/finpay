const KEY = (userId) => `finpay.avatar.${userId || "anon"}`;

export function getAvatar(userId) {
  try {
    return localStorage.getItem(KEY(userId)) || null;
  } catch {
    return null;
  }
}

export function setAvatar(userId, dataUrl) {
  if (!userId) return;
  if (!dataUrl) localStorage.removeItem(KEY(userId));
  else localStorage.setItem(KEY(userId), dataUrl);
}

/** Compress an image file to a small JPEG data URL for local avatar storage. */
export function fileToAvatarDataUrl(file, maxSize = 320) {
  return new Promise((resolve, reject) => {
    if (!file || !file.type.startsWith("image/")) {
      reject(new Error("Please choose an image file."));
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read image."));
    reader.onload = () => {
      const img = new Image();
      img.onerror = () => reject(new Error("Invalid image."));
      img.onload = () => {
        const scale = Math.min(1, maxSize / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * scale));
        const h = Math.max(1, Math.round(img.height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL("image/jpeg", 0.85));
      };
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}
