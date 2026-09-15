import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { setAccessToken } from "../api/client";
import { socketService } from "../services/socketService";
import { registerDevice } from "../services/pushService";

const AuthContext = createContext(null);

const STORAGE_KEY = "finpay.auth";

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    if (auth?.access_token) {
      setAccessToken(auth.access_token);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(auth));
      socketService.connect(auth.access_token);
      // Register this device for push (best-effort; no-op without FCM config).
      registerDevice();
    } else {
      setAccessToken(null);
      localStorage.removeItem(STORAGE_KEY);
      socketService.disconnect();
    }
    return () => {};
  }, [auth]);

  const value = useMemo(
    () => ({
      auth,
      user: auth?.user || null,
      isAuthenticated: Boolean(auth?.access_token),
      login: (tokenResponse) => setAuth(tokenResponse),
      logout: () => setAuth(null),
    }),
    [auth]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
