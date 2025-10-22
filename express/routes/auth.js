const express = require("express");
const {
  register,
  login,
  logout,
  getMe,
  updateDetails,
  updatePassword,
} = require("../controllers/authController");

const { protect } = require("../middleware/auth");
const {
  validateSignup,
  validateLogin,
  validateChangePassword,
} = require("../middleware/validation");

const router = express.Router();

// Public routes
router.post("/register", validateSignup, register);
router.post("/login", validateLogin, login);

// Protected routes
router.get("/logout", protect, logout);
router.get("/me", protect, getMe);
router.put("/updatedetails", protect, updateDetails);
router.put("/updatepassword", protect, validateChangePassword, updatePassword);

module.exports = router;
