/* Firebase Cloud Messaging background service worker.
 * Config is provided via query parameters at registration time so no secrets
 * are committed to the repository. */
importScripts("https://www.gstatic.com/firebasejs/11.1.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/11.1.0/firebase-messaging-compat.js");

const params = new URLSearchParams(self.location.search);
const config = {
  apiKey: params.get("apiKey"),
  authDomain: params.get("authDomain"),
  projectId: params.get("projectId"),
  messagingSenderId: params.get("messagingSenderId"),
  appId: params.get("appId"),
};

if (config.apiKey && config.projectId && config.messagingSenderId) {
  firebase.initializeApp(config);
  const messaging = firebase.messaging();
  messaging.onBackgroundMessage((payload) => {
    const title = (payload.notification && payload.notification.title) || "FinPay";
    const body = (payload.notification && payload.notification.body) || "";
    self.registration.showNotification(title, { body, icon: "/vite.svg" });
  });
}
