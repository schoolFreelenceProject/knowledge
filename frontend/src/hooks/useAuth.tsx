import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { login as loginRequest, register as registerRequest } from "../api/auth";
import {
  clearStoredSession,
  getStoredSession,
  setStoredSession,
} from "../api/tokenStore";
import type { LoginRequest } from "../types/api";

type AuthContextValue = {
  accessToken: string;
  email: string;
  isAuthenticated: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  register: (credentials: LoginRequest) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSessionState] = useState(getStoredSession);

  const setSession = useCallback((accessToken: string, email: string) => {
    setStoredSession(accessToken, email);
    setSessionState({ accessToken, email });
  }, []);

  const logout = useCallback(() => {
    clearStoredSession();
    setSessionState({ accessToken: "", email: "" });
  }, []);

  const login = useCallback(
    async (credentials: LoginRequest) => {
      const response = await loginRequest(credentials);
      setSession(response.access_token, credentials.email.toLowerCase());
    },
    [setSession],
  );

  const register = useCallback(
    async (credentials: LoginRequest) => {
      await registerRequest(credentials);
      const response = await loginRequest(credentials);
      setSession(response.access_token, credentials.email.toLowerCase());
    },
    [setSession],
  );

  useEffect(() => {
    const handleExpiredSession = () => logout();
    window.addEventListener("company-rag-session-expired", handleExpiredSession);
    return () => {
      window.removeEventListener("company-rag-session-expired", handleExpiredSession);
    };
  }, [logout]);

  const value = useMemo<AuthContextValue>(
    () => ({
      accessToken: session.accessToken,
      email: session.email,
      isAuthenticated: Boolean(session.accessToken),
      login,
      register,
      logout,
    }),
    [login, logout, register, session.accessToken, session.email],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) {
    throw new Error("useAuth must be used inside AuthProvider.");
  }

  return value;
}
