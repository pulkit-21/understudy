import { createContext, ReactNode, useContext, useEffect, useState } from "react";
import { api, AuthUser, auth as tokenStore, setUnauthorizedHandler } from "./api";

interface AuthCtx {
  user: AuthUser | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => void;
}

const Ctx = createContext<AuthCtx>({} as AuthCtx);
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // a stale/expired token anywhere in the app bounces us back to sign-in
    setUnauthorizedHandler(() => setUser(null));
    if (tokenStore.get()) {
      api.me().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false));
    } else {
      setLoading(false);
    }
  }, []);

  const login = async (email: string, password: string) => {
    const res = await api.login(email, password);
    tokenStore.set(res.token);
    setUser(res.user);
  };
  const register = async (email: string, password: string, name: string) => {
    const res = await api.register(email, password, name);
    tokenStore.set(res.token);
    setUser(res.user);
  };
  const logout = () => {
    tokenStore.clear();
    setUser(null);
  };

  return (
    <Ctx.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </Ctx.Provider>
  );
}
