import axios from 'axios';
import * as SecureStore from 'expo-secure-store';

const API_URL = 'http://10.209.40.99:8000/api/v1';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
api.interceptors.request.use(
  async (config) => {
    const token = await SecureStore.getItemAsync('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
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
    return await SecureStore.getItemAsync('access_token');
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
