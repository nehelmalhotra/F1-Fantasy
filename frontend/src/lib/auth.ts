"use client";

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import { createElement } from "react";
import { api, type User } from "./api";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string, leagueId?: number) => Promise<void>;
  loginWithToken: (token: string, leagueId?: number) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  login: async () => {},
  loginWithToken: async () => {},
  logout: async () => {},
  refresh: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const u = await api.me();
      setUser(u);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string, leagueId?: number) => {
      await api.login(email, password, leagueId);
      await refresh();
    },
    [refresh]
  );

  const loginWithToken = useCallback(
    async (token: string, leagueId?: number) => {
      await api.loginWithToken(token, leagueId);
      await refresh();
    },
    [refresh]
  );

  const logout = useCallback(async () => {
    await api.logout();
    setUser(null);
  }, []);

  return createElement(
    AuthContext.Provider,
    { value: { user, loading, login, loginWithToken, logout, refresh } },
    children
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
