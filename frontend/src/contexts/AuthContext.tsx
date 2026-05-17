'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { api, AuthUser } from '@/lib/api';

interface AuthContextType {
  user: AuthUser | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isApproved: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (name: string, email: string, password: string) => Promise<void>;
  googleLogin: (credential: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Hydrate from localStorage on mount
    const savedToken = localStorage.getItem('autoref_token');
    const savedUser = localStorage.getItem('autoref_user');

    if (savedToken && savedUser) {
      setToken(savedToken);
      setUser(JSON.parse(savedUser));

      // Validate token is still valid
      api.getMe()
        .then((freshUser) => {
          setUser(freshUser);
          localStorage.setItem('autoref_user', JSON.stringify(freshUser));
        })
        .catch(() => {
          // Token expired
          clearAuth();
        })
        .finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, []);

  function saveAuth(accessToken: string, refreshToken: string, userData: AuthUser) {
    setToken(accessToken);
    setUser(userData);
    localStorage.setItem('autoref_token', accessToken);
    localStorage.setItem('autoref_refresh_token', refreshToken);
    localStorage.setItem('autoref_user', JSON.stringify(userData));
  }

  function clearAuth() {
    setToken(null);
    setUser(null);
    localStorage.removeItem('autoref_token');
    localStorage.removeItem('autoref_refresh_token');
    localStorage.removeItem('autoref_user');
  }

  async function login(email: string, password: string) {
    const result = await api.login({ email, password });
    saveAuth(result.access_token, result.refresh_token, result.user);
  }

  async function register(name: string, email: string, password: string) {
    const result = await api.register({ name, email, password });
    saveAuth(result.access_token, result.refresh_token, result.user);
  }

  async function googleLogin(credential: string) {
    const result = await api.googleLogin({ credential });
    saveAuth(result.access_token, result.refresh_token, result.user);
  }

  function logout() {
    clearAuth();
    window.location.href = '/login';
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!token && !!user,
        isApproved: !!user?.is_approved,
        login,
        register,
        googleLogin,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
