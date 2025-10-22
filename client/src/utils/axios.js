import axios from "axios";
import { API_CONFIG } from "../config/api";

// Create axios instance with base configuration
const api = axios.create({
  baseURL: API_CONFIG.BASE_URL,
  timeout: API_CONFIG.TIMEOUT,
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: API_CONFIG.WITH_CREDENTIALS,
});

// Request interceptor
api.interceptors.request.use(
  (config) => {
    // Add auth token if available
    const token = localStorage.getItem("token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // Handle common errors
    if (error.response?.status === 401) {
      // Unauthorized - clear token and redirect to login
      localStorage.removeItem("token");
      window.location.href = "/login";
    } else if (error.response?.status === 403) {
      // Forbidden
      console.error("Access forbidden");
    } else if (error.response?.status >= 500) {
      // Server error
      console.error("Server error:", error.response?.data?.message);
    }

    return Promise.reject(error);
  }
);

export default api;
