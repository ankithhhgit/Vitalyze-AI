import React, { createContext, useContext, useState, useEffect, ReactNode, useCallback } from 'react';
import * as SecureStore from 'expo-secure-store';
import { authService, setUnauthorizedHandler } from '../services/api';

interface User {
  loggedIn: boolean;
  phone?: string;
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (phone: string, password: string) => Promise<void>;
  register: (userData: {
    name: string;
    phone_number: string;
    password: string;
    age?: number | null;
    gender: string;
  }) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkAuth();
  }, []);

  const handleUnauthorized = useCallback(async () => {
    setUser(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(handleUnauthorized);
    return () => setUnauthorizedHandler(undefined);
  }, [handleUnauthorized]);

  const checkAuth = async () => {
    try {
      const token = await SecureStore.getItemAsync('access_token');
      if (token) {
        // Keep the app behind the loading guard until the stored token is checked.
        try {
          const profile = await authService.getCurrentUser();
          setUser({ loggedIn: true, phone: profile.phone_number });
        } catch (error: any) {
          if (error?.response?.status !== 401) {
            // A temporary network/server failure does not invalidate a stored token.
            setUser({ loggedIn: true });
          }
        }
      }
    } catch (error) {
      console.error('Auth check error:', error);
    } finally {
      setLoading(false);
    }
  };

  const login = async (phone: string, password: string) => {
    const data = await authService.login(phone, password);
    await SecureStore.setItemAsync('access_token', data.access_token);
    if (data.user_id) {
      await SecureStore.setItemAsync('user_id', data.user_id.toString());
    }
    setUser({ loggedIn: true, phone });
  };

  const register = async (userData: {
    name: string;
    phone_number: string;
    password: string;
    age?: number | null;
    gender: string;
  }) => {
    await authService.register(userData);
  };

  const logout = async () => {
    await Promise.allSettled([
      SecureStore.deleteItemAsync('access_token'),
      SecureStore.deleteItemAsync('user_id'),
    ]);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
