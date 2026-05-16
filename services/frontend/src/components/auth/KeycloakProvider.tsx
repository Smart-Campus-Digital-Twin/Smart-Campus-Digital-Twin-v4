"use client";

import Keycloak from "keycloak-js";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

type AuthContextValue = {
  isReady: boolean;
  isAuthenticated: boolean;
  username: string | null;
  token: string | null;
  login: () => void;
  register: () => void;
  logout: () => void;
  fetchWithAuth: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function createKeycloakClient() {
  return new Keycloak({
    url: process.env.NEXT_PUBLIC_KEYCLOAK_URL || "/auth",
    realm: process.env.NEXT_PUBLIC_KEYCLOAK_REALM || "campus",
    clientId: process.env.NEXT_PUBLIC_KEYCLOAK_CLIENT_ID || "campus-frontend",
  });
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [keycloak] = useState(createKeycloakClient);
  const [isReady, setIsReady] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    keycloak
      .init({
        onLoad: "check-sso",
        pkceMethod: "S256",
        checkLoginIframe: false,
        silentCheckSsoRedirectUri: `${window.location.origin}/silent-check-sso.html`,
      })
      .then((authenticated) => {
        if (!active) {
          return;
        }

        setIsAuthenticated(authenticated);
        setUsername(
          authenticated
            ? (keycloak.tokenParsed?.preferred_username ?? keycloak.tokenParsed?.name ?? null)
            : null,
        );
        setToken(keycloak.token ?? null);
        setIsReady(true);
      })
      .catch((error) => {
        if (!active) {
          return;
        }

        console.error("Keycloak init failed:", error);
        setIsReady(true);
        setIsAuthenticated(false);
      });

    const refreshTimer = window.setInterval(async () => {
      if (!keycloak.authenticated) {
        return;
      }

      try {
        await keycloak.updateToken(30);
        if (!active) {
          return;
        }

        setToken(keycloak.token ?? null);
        setIsAuthenticated(Boolean(keycloak.authenticated));
        setUsername(
          keycloak.tokenParsed?.preferred_username ?? keycloak.tokenParsed?.name ?? null,
        );
      } catch (error) {
        if (!active) {
          return;
        }

        console.error("Keycloak token refresh failed:", error);
        setToken(null);
        setIsAuthenticated(false);
      }
    }, 30000);

    return () => {
      active = false;
      window.clearInterval(refreshTimer);
    };
  }, [keycloak]);

  const login = useCallback(() => {
    void keycloak.login({ redirectUri: window.location.href });
  }, [keycloak]);

  const register = useCallback(() => {
    void keycloak.register({ redirectUri: window.location.href });
  }, [keycloak]);

  const logout = useCallback(() => {
    void keycloak.logout({ redirectUri: window.location.origin });
  }, [keycloak]);

  const fetchWithAuth = useCallback(
    async (input: RequestInfo | URL, init: RequestInit = {}) => {
      if (!keycloak.authenticated) {
        throw new Error("Authentication required");
      }

      await keycloak.updateToken(30);

      const headers = new Headers(init.headers);
      if (keycloak.token) {
        headers.set("Authorization", `Bearer ${keycloak.token}`);
      }

      return fetch(input, {
        ...init,
        headers,
      });
    },
    [keycloak],
  );

  const value = useMemo(
    () => ({
      isReady,
      isAuthenticated,
      username,
      token,
      login,
      register,
      logout,
      fetchWithAuth,
    }),
    [fetchWithAuth, isAuthenticated, isReady, login, logout, register, token, username],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }

  return context;
}