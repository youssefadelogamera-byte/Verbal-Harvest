import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { api } from './api.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(undefined); // undefined = loading
  const [meta, setMeta] = useState(null);

  useEffect(() => {
    api('/auth/me').then((d) => setUser(d.user)).catch(() => setUser(null));
    api('/meta').then(setMeta).catch(() => {});
  }, []);

  // Theme the whole app for the learner's audience (children get a playful skin).
  useEffect(() => {
    document.documentElement.dataset.audience = user?.audience || '';
  }, [user?.audience]);

  const refresh = useCallback(async () => {
    const d = await api('/auth/me');
    setUser(d.user);
    return d.user;
  }, []);

  const logout = useCallback(async () => {
    await api('/auth/logout', { method: 'POST', body: {} });
    setUser(null);
  }, []);

  return <AuthContext.Provider value={{ user, setUser, refresh, logout, meta }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
