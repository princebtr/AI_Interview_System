// API Configuration
export const API_CONFIG = {
  // Express Backend (Main API - Authentication, User Management)
  EXPRESS_BASE_URL:
    import.meta.env.VITE_EXPRESS_API_URL || "http://localhost:5000/api",
  // Flask Backend (AI Features - Question Generation, Evaluation, Face Detection)
  FLASK_BASE_URL: import.meta.env.VITE_FLASK_API_URL || "http://localhost:5001",
  TIMEOUT: 10000,
  WITH_CREDENTIALS: true,
};

// Helper function to get the appropriate API URL
export const getApiUrl = (endpoint, useFlask = false) => {
  const baseUrl = useFlask
    ? API_CONFIG.FLASK_BASE_URL
    : API_CONFIG.EXPRESS_BASE_URL;
  return `${baseUrl}${endpoint}`;
};

export default API_CONFIG;
