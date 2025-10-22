// API Configuration
export const API_CONFIG = {
  BASE_URL: import.meta.env.VITE_API_BASE_URL || "http://localhost:5000/api",
  TIMEOUT: 10000,
  WITH_CREDENTIALS: true,
};

export default API_CONFIG;
