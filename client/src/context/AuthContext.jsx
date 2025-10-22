import { createContext, useContext, useReducer, useEffect } from "react";
import api from "../utils/axios";
import toast from "react-hot-toast";

const AuthContext = createContext();

// Initial state
const initialState = {
  user: null,
  token: localStorage.getItem("token"),
  isAuthenticated: false,
  loading: true,
  error: null,
};

// Auth reducer
const authReducer = (state, action) => {
  switch (action.type) {
    case "AUTH_START":
      return {
        ...state,
        loading: true,
        error: null,
      };
    case "AUTH_SUCCESS":
      return {
        ...state,
        user: action.payload.user,
        token: action.payload.token,
        isAuthenticated: true,
        loading: false,
        error: null,
      };
    case "AUTH_FAILURE":
      return {
        ...state,
        user: null,
        token: null,
        isAuthenticated: false,
        loading: false,
        error: action.payload,
      };
    case "LOGOUT":
      return {
        ...state,
        user: null,
        token: null,
        isAuthenticated: false,
        loading: false,
        error: null,
      };
    case "CLEAR_ERROR":
      return {
        ...state,
        error: null,
      };
    case "UPDATE_USER":
      return {
        ...state,
        user: { ...state.user, ...action.payload },
      };
    default:
      return state;
  }
};

// Auth provider component
export const AuthProvider = ({ children }) => {
  const [state, dispatch] = useReducer(authReducer, initialState);

  // Set up token in localStorage
  useEffect(() => {
    if (state.token) {
      localStorage.setItem("token", state.token);
    } else {
      localStorage.removeItem("token");
    }
  }, [state.token]);

  // Load user on app start
  useEffect(() => {
    if (state.token) {
      loadUser();
    } else {
      dispatch({ type: "AUTH_FAILURE", payload: null });
    }
  }, []);

  // Load user function
  const loadUser = async () => {
    try {
      dispatch({ type: "AUTH_START" });
      const response = await api.get("/auth/me");
      dispatch({
        type: "AUTH_SUCCESS",
        payload: {
          user: response.data.user,
          token: state.token,
        },
      });
    } catch (error) {
      dispatch({ type: "AUTH_FAILURE", payload: null });
      localStorage.removeItem("token");
    }
  };

  // Register function
  const register = async (userData) => {
    try {
      dispatch({ type: "AUTH_START" });
      const response = await api.post("/auth/register", userData);

      dispatch({
        type: "AUTH_SUCCESS",
        payload: response.data,
      });

      toast.success("Registration successful!");
      return { success: true };
    } catch (error) {
      const message = error.response?.data?.message || "Registration failed";
      dispatch({ type: "AUTH_FAILURE", payload: message });
      toast.error(message);
      return { success: false, error: message };
    }
  };

  // Login function
  const login = async (userData) => {
    try {
      dispatch({ type: "AUTH_START" });
      const response = await api.post("/auth/login", userData);

      dispatch({
        type: "AUTH_SUCCESS",
        payload: response.data,
      });

      toast.success("Login successful!");
      return { success: true };
    } catch (error) {
      const message = error.response?.data?.message || "Login failed";
      dispatch({ type: "AUTH_FAILURE", payload: message });
      toast.error(message);
      return { success: false, error: message };
    }
  };

  // Logout function
  const logout = async () => {
    try {
      await api.get("/auth/logout");
    } catch (error) {
      console.error("Logout error:", error);
    } finally {
      dispatch({ type: "LOGOUT" });
      toast.success("Logged out successfully");
    }
  };

  // Update user details
  const updateUser = async (userData) => {
    try {
      const response = await api.put("/auth/updatedetails", userData);
      dispatch({
        type: "UPDATE_USER",
        payload: response.data.user,
      });
      toast.success("Profile updated successfully!");
      return { success: true };
    } catch (error) {
      const message = error.response?.data?.message || "Update failed";
      toast.error(message);
      return { success: false, error: message };
    }
  };

  // Update password
  const updatePassword = async (passwordData) => {
    try {
      const response = await api.put("/auth/updatepassword", passwordData);
      dispatch({
        type: "AUTH_SUCCESS",
        payload: response.data,
      });
      toast.success("Password updated successfully!");
      return { success: true };
    } catch (error) {
      const message = error.response?.data?.message || "Password update failed";
      toast.error(message);
      return { success: false, error: message };
    }
  };

  // Clear error
  const clearError = () => {
    dispatch({ type: "CLEAR_ERROR" });
  };

  const value = {
    ...state,
    register,
    login,
    logout,
    updateUser,
    updatePassword,
    clearError,
    loadUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

// Custom hook to use auth context
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};

export default AuthContext;
