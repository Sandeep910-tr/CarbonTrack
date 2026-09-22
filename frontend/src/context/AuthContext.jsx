import { createContext, useContext, useState, useCallback } from "react";
import api from "../lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(localStorage.getItem("cfl_token"));
  const [role, setRole] = useState(localStorage.getItem("cfl_role"));
  const [user, setUser] = useState(() => {
    const raw = localStorage.getItem("cfl_user");
    return raw ? JSON.parse(raw) : null;
  });

  const login = useCallback(async (username, password) => {
    const res = await api.post("/auth/login", { username, password });
    localStorage.setItem("cfl_token", res.data.token);
    localStorage.setItem("cfl_role", res.data.role);
    localStorage.setItem("cfl_user", JSON.stringify(res.data.user));
    setToken(res.data.token);
    setRole(res.data.role);
    setUser(res.data.user);
    return res.data;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("cfl_token");
    localStorage.removeItem("cfl_role");
    localStorage.removeItem("cfl_user");
    setToken(null);
    setRole(null);
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ token, role, user, login, logout, setUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
