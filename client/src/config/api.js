// API Configuration — a single Django backend serves auth and AI features.
export const API_CONFIG = {
  BASE_URL: import.meta.env.VITE_API_URL || "http://localhost:8000/api",
  TIMEOUT: 30000, // AI calls can take a while
  WITH_CREDENTIALS: false, // the API authenticates with the Bearer token only
};

export default API_CONFIG;

/** Absolute URL for a path the API returns (e.g. an institution's logoUrl). */
export const apiAsset = (path) => (path ? new URL(path, API_CONFIG.BASE_URL).toString() : null);
