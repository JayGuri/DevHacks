import { createContext, useContext, useState, useEffect } from "react";
import { MOCK_USERS } from "@/lib/mockData";
import { useStore } from "@/lib/store";

const AuthContext = createContext(null);

const STORAGE_KEY = "arfl-user";

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const setStoreUser = useStore((s) => s.setUser);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        setCurrentUser(parsed);
        setStoreUser(parsed);
      }
    } catch {
      setCurrentUser(null);
    }
    setLoading(false);
  }, [setStoreUser]);

  function login(email, password) {
    const user = MOCK_USERS.find(
      (u) =>
        u.email.toLowerCase() === email.toLowerCase() &&
        u.password === password
    );
    if (!user) throw new Error("Invalid email or password");

    localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    setCurrentUser(user);
    setStoreUser(user);
    return user;
  }

  function logout() {
    localStorage.removeItem(STORAGE_KEY);
    setCurrentUser(null);
    setStoreUser(null);
  }

  function signup() {
    return { success: true };
  }

  return (
    <AuthContext.Provider
      value={{ currentUser, loading, login, logout, signup }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
