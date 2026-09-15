// Firebase Cloud Messaging registration for web push.
//
// Configuration is supplied entirely through Vite env values (VITE_FIREBASE_*).
// When they are absent the service degrades gracefully: the device is still
// registered with the backend (so it is tracked), just without a push token.
import { getApps, initializeApp } from "firebase/app";
import { getMessaging, getToken, isSupported, onMessage } from "firebase/messaging";

const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID,
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_FIREBASE_APP_ID,
};
const vapidKey = import.meta.env.VITE_FIREBASE_VAPID_KEY;

export function isConfigured() {
  return Boolean(
    firebaseConfig.apiKey &&
      firebaseConfig.projectId &&
      firebaseConfig.appId &&
      firebaseConfig.messagingSenderId &&
      vapidKey
  );
}

// A stable per-browser identifier so re-registration updates the same device row.
export function getDeviceId() {
  let id = localStorage.getItem("finpay.device_id");
  if (!id) {
    id = "web-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem("finpay.device_id", id);
  }
  return id;
}

let messageHandler = null;
export function onForegroundMessage(handler) {
  messageHandler = handler;
}

async function acquirePushToken() {
  if (!isConfigured()) return null;
  if (!("Notification" in window) || !("serviceWorker" in navigator)) return null;
  if (!(await isSupported().catch(() => false))) return null;

  const permission = await Notification.requestPermission();
  if (permission !== "granted") return null;

  const app = getApps().length ? getApps()[0] : initializeApp(firebaseConfig);

  // The background service worker needs the config; pass it via query params
  // so nothing sensitive is committed to the repository.
  const params = new URLSearchParams(firebaseConfig).toString();
  const swReg = await navigator.serviceWorker.register(
    `/firebase-messaging-sw.js?${params}`
  );

  const messaging = getMessaging(app);
  onMessage(messaging, (payload) => {
    if (messageHandler) messageHandler(payload);
  });

  return getToken(messaging, { vapidKey, serviceWorkerRegistration: swReg }).catch(
    () => null
  );
}

// Register (or refresh) this device with the backend. Best-effort: any failure
// is swallowed so it never blocks the authenticated session.
export async function registerDevice() {
  try {
    const { devicesApi } = await import("../api/devices");
    const pushToken = await acquirePushToken();
    await devicesApi.register(getDeviceId(), "web", pushToken || null);
    return { registered: true, push: Boolean(pushToken) };
  } catch {
    return { registered: false, push: false };
  }
}
