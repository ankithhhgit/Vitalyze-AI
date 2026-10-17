import axios from 'axios';
import * as SecureStore from 'expo-secure-store';

const API_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8001/api/v1';

const api = axios.create({
  baseURL: API_URL,
  timeout: 20000,
  headers: {
    'Content-Type': 'application/json',
  },
});

type UnauthorizedHandler = () => void | Promise<void>;
let unauthorizedHandler: UnauthorizedHandler | undefined;
let handlingUnauthorized = false;

export const setUnauthorizedHandler = (handler?: UnauthorizedHandler) => {
  unauthorizedHandler = handler;
};

export const normalizePhoneNumber = (phone: string) => phone.trim().replace(/[\s().-]/g, '');
export const isE164PhoneNumber = (phone: string) => /^\+[1-9]\d{1,14}$/.test(phone);

export const formatApiError = (error: unknown, fallback: string): string => {
  const code = (error as any)?.code;
  if (code === 'ECONNABORTED' || code === 'ETIMEDOUT') {
    return 'The request timed out. Check that the backend is running on the demo network and try again.';
  }

  const detail = (error as any)?.response?.data?.detail;

  if (typeof detail === 'string' && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== 'object' || typeof item.msg !== 'string') return null;
        const location = Array.isArray(item.loc)
          ? item.loc.filter((part: unknown) => typeof part === 'string' && part !== 'body').join(' ')
          : '';
        return location ? `${location}: ${item.msg}` : item.msg;
      })
      .filter((message): message is string => Boolean(message));
    if (messages.length) return messages.join('\n');
  }

  return fallback;
};

// Request interceptor to add auth token
api.interceptors.request.use(
  async (config) => {
    // Replace the shared JSON default so Axios preserves React Native
    // FormData. React Native's native networking layer supplies the boundary.
    if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
      config.headers.set('Content-Type', 'multipart/form-data');
    }

    const token = await SecureStore.getItemAsync('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error?.response?.status;
    const requestUrl = error?.config?.url || '';
    if (status === 401 && !requestUrl.includes('/auth/login') && !requestUrl.includes('/auth/register') && !handlingUnauthorized) {
      handlingUnauthorized = true;
      try {
        await Promise.allSettled([
          SecureStore.deleteItemAsync('access_token'),
          SecureStore.deleteItemAsync('user_id'),
        ]);
        await unauthorizedHandler?.();
      } finally {
        handlingUnauthorized = false;
      }
    }
    return Promise.reject(error);
  }
);

export const authService = {
  register: async (userData: {
    name: string;
    phone_number: string;
    password: string;
    age?: number | null;
    gender: string;
  }) => {
    const response = await api.post('/auth/register', userData);
    return response.data;
  },

  login: async (phone: string, password: string) => {
    const params = new URLSearchParams();
    params.append('username', phone);
    params.append('password', password);

    const response = await api.post('/auth/login', params, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    return response.data;
  },

  getCurrentUser: async () => {
    const response = await api.get('/auth/me');
    return response.data;
  },

  logout: async () => {
    await SecureStore.deleteItemAsync('access_token');
    await SecureStore.deleteItemAsync('user_id');
  },

  setToken: async (token: string) => {
    await SecureStore.setItemAsync('access_token', token);
  },

  setUserId: async (userId: string) => {
    await SecureStore.setItemAsync('user_id', userId);
  },
};

export default api;
