import { createContext, useContext, useState, useEffect } from "react";
import { MOCK_USERS } from "@/lib/mockData";
import { useStore } from "@/lib/store";
import { USE_MOCK } from "@/lib/config";
import {
  apiLogin,
  apiSignup,
  apiGetMe,
  getToken,
  setToken,
  clearToken,
} from "@/lib/api";

const AuthContext = createContext(null);

const STORAGE_KEY = "arfl-user";

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const setStoreUser = useStore((s) => s.setUser);

  // Rehydrate user on mount
  useEffect(() => {
    async function rehydrate() {
      try {
        if (USE_MOCK) {
          // Mock mode: use localStorage-stored user object
          const raw = localStorage.getItem(STORAGE_KEY);
          if (raw) {
            const parsed = JSON.parse(raw);
            setCurrentUser(parsed);
            setStoreUser(parsed);
          }
        } else {
          // API mode: verify token with /auth/me
          const token = getToken();
          if (token) {
            const data = await apiGetMe();
            const user = data.user;
            localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
            setCurrentUser(user);
            setStoreUser(user);
          }
        }
      } catch {
        // Token expired or invalid — clear everything
        clearToken();
        localStorage.removeItem(STORAGE_KEY);
        setCurrentUser(null);
      }
      setLoading(false);
    }
    rehydrate();
  }, [setStoreUser]);

  async function login(email, password) {
    if (USE_MOCK) {
      // Mock: check against hardcoded users
      const user = MOCK_USERS.find(
        (u) =>
          u.email.toLowerCase() === email.toLowerCase() &&
          u.password === password,
      );
      if (!user) throw new Error("Invalid email or password");

      localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
      setCurrentUser(user);
      setStoreUser(user);
      return user;
    }

    // API mode
    const data = await apiLogin(email, password);
    const user = data.user;
    setToken(data.token);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    setCurrentUser(user);
    setStoreUser(user);
    return user;
  }

  function logout() {
    clearToken();
    localStorage.removeItem(STORAGE_KEY);
    setCurrentUser(null);
    setStoreUser(null);
  }

  /** Update the persisted user object in-place (e.g., after a subscription upgrade). */
  function updateUser(updatedUser) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updatedUser));
    setCurrentUser(updatedUser);
    setStoreUser(updatedUser);
  }

  async function signup(name, email, password) {
    if (USE_MOCK) {
      return { success: true };
    }

    // API mode
    const data = await apiSignup(name, email, password);
    // Don't auto-login after signup — redirect to login page
    return data;
  }

  return (
    <AuthContext.Provider
      value={{ currentUser, loading, login, logout, signup, updateUser }}
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
