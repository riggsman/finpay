import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import {
  setAccessToken,
  setRefreshToken,
  setSessionHandlers,
  clearSessionTokens,
  refreshAccessToken,
} from "../api/client";
import { authApi } from "../api/auth";
import { socketService } from "../services/socketService";
import { registerDevice } from "../services/pushService";
import { setConfig, clearConfig, refreshConfig } from "../services/feeConfig";

const AuthContext = createContext(null);

const STORAGE_KEY = "finpay.auth";

function readStoredAuth() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function persistAuth(next) {
  if (next?.access_token || next?.refresh_token) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } else {
    localStorage.removeItem(STORAGE_KEY);
  }
}

function loginRedirectPath() {
  const path = window.location.pathname || "";
  if (path.startsWith("/admin")) return "/admin/login";
  return "/login";
}

function redirectToLogin() {
  const target = loginRedirectPath();
  const here = window.location.pathname || "";
  if (here === target || here === "/login" || here === "/admin/login") return;
  const search = window.location.search || "";
  const next = encodeURIComponent(`${here}${search}`);
  window.location.assign(`${target}?next=${next}`);
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => readStoredAuth());
  const authRef = useRef(auth);
  authRef.current = auth;

  // Keep API client tokens + session callbacks in sync with React state.
  useEffect(() => {
    setSessionHandlers({
      onAccessTokenUpdated: (access_token) => {
        setAuth((prev) => {
          if (!prev) return prev;
          const next = { ...prev, access_token };
          persistAuth(next);
          return next;
        });
        socketService.connect(access_token);
      },
      onSessionExpired: () => {
        clearSessionTokens();
        setAuth(null);
        persistAuth(null);
        socketService.disconnect();
        clearConfig();
        redirectToLogin();
      },
    });
  }, []);

  useEffect(() => {
    if (auth?.access_token || auth?.refresh_token) {
      setAccessToken(auth.access_token || null);
      setRefreshToken(auth.refresh_token || null);
      persistAuth(auth);

      if (auth.access_token) {
        socketService.connect(auth.access_token);
        registerDevice();
        if (auth.config) setConfig(auth.config);
        else refreshConfig();
      } else if (auth.refresh_token) {
        // Access token missing/expired on boot — renew silently.
        refreshAccessToken().catch(() => {
          // onSessionExpired handles redirect
        });
      }
    } else {
      clearSessionTokens();
      persistAuth(null);
      socketService.disconnect();
      clearConfig();
    }
  }, [auth]);

  const value = useMemo(
    () => ({
      auth,
      user: auth?.user || null,
      isAuthenticated: Boolean(auth?.access_token || auth?.refresh_token),
      login: (tokenResponse) => {
        setAccessToken(tokenResponse.access_token);
        setRefreshToken(tokenResponse.refresh_token);
        setAuth(tokenResponse);
      },
      updateTokens: (partial) => {
        setAuth((prev) => {
          if (!prev) return prev;
          const next = { ...prev, ...partial };
          setAccessToken(next.access_token || null);
          setRefreshToken(next.refresh_token || null);
          persistAuth(next);
          return next;
        });
      },
      logout: () => {
        const finish = () => {
          clearSessionTokens();
          setAuth(null);
          persistAuth(null);
          socketService.disconnect();
          clearConfig();
        };
        const current = authRef.current;
        if (current?.access_token || current?.refresh_token) {
          authApi.logout().catch(() => {}).finally(finish);
        } else {
          finish();
        }
      },
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
