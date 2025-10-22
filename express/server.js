const express = require("express");
const mongoose = require("mongoose");
const cors = require("cors");
const helmet = require("helmet");
const rateLimit = require("express-rate-limit");
const cookieParser = require("cookie-parser");
require("dotenv").config({ path: "./config.env" });

// Import routes
const authRoutes = require("./routes/auth");
const interviewRoutes = require("./routes/interview");

const app = express();

// CORS configuration - MUST come before other middleware
const corsOptions = {
  origin: ["http://localhost:3000", "http://localhost:5173"],
  credentials: true,
  methods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
  allowedHeaders: ["Content-Type", "Authorization", "X-Requested-With"],
  exposedHeaders: ["Set-Cookie"],
  optionsSuccessStatus: 200,
};

app.use(cors(corsOptions));

// Manual CORS headers to ensure they're set correctly
app.use((req, res, next) => {
  const origin = req.headers.origin;
  if (
    origin &&
    ["http://localhost:3000", "http://localhost:5173"].includes(origin)
  ) {
    res.header("Access-Control-Allow-Origin", origin);
    res.header("Access-Control-Allow-Credentials", "true");
    res.header(
      "Access-Control-Allow-Methods",
      "GET, POST, PUT, DELETE, OPTIONS"
    );
    res.header(
      "Access-Control-Allow-Headers",
      "Content-Type, Authorization, X-Requested-With"
    );
    res.header("Access-Control-Expose-Headers", "Set-Cookie");
  }

  if (req.method === "OPTIONS") {
    res.status(200).end();
    return;
  }

  next();
});

// Security middleware (configured to work with CORS)
app.use(
  helmet({
    crossOriginEmbedderPolicy: false,
    contentSecurityPolicy: false,
  })
);

// Debug middleware for CORS (remove in production)
if (process.env.NODE_ENV === "development") {
  app.use((req, res, next) => {
    console.log(`${req.method} ${req.url} - Origin: ${req.headers.origin}`);
    next();
  });
}

// Rate limiting (after CORS)
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100, // limit each IP to 100 requests per windowMs
  message: {
    success: false,
    message: "Too many requests from this IP, please try again later.",
  },
});

// Apply rate limiting to all requests
app.use(limiter);

// Stricter rate limiting for auth routes
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 5, // limit each IP to 5 requests per windowMs
  message: {
    success: false,
    message: "Too many authentication attempts, please try again later.",
  },
});

// Body parser middleware
app.use(express.json({ limit: "10mb" }));
app.use(express.urlencoded({ extended: true, limit: "10mb" }));

// Cookie parser middleware
app.use(cookieParser());

// Connect to MongoDB
mongoose
  .connect(process.env.MONGODB_URI, {
    useNewUrlParser: true,
    useUnifiedTopology: true,
  })
  .then(() => {
    console.log("✅ MongoDB connected successfully");
  })
  .catch((error) => {
    console.error("❌ MongoDB connection error:", error);
    process.exit(1);
  });

// Routes (temporarily disable rate limiting for testing)
app.use("/api/auth", authRoutes);
app.use("/api", interviewRoutes);

// Health check route
app.get("/api/health", (req, res) => {
  res.status(200).json({
    success: true,
    message: "Server is running",
    timestamp: new Date().toISOString(),
  });
});

// CORS test route
app.get("/api/cors-test", (req, res) => {
  res.status(200).json({
    success: true,
    message: "CORS is working",
    origin: req.headers.origin,
    timestamp: new Date().toISOString(),
  });
});

// 404 handler
app.use("*", (req, res) => {
  res.status(404).json({
    success: false,
    message: "Route not found",
  });
});

// Global error handler
app.use((err, req, res, next) => {
  console.error("Error:", err.stack);

  // Mongoose bad ObjectId
  if (err.name === "CastError") {
    return res.status(400).json({
      success: false,
      message: "Resource not found",
    });
  }

  // Mongoose duplicate key
  if (err.code === 11000) {
    return res.status(400).json({
      success: false,
      message: "Duplicate field value entered",
    });
  }

  // Mongoose validation error
  if (err.name === "ValidationError") {
    const message = Object.values(err.errors).map((val) => val.message);
    return res.status(400).json({
      success: false,
      message: message.join(", "),
    });
  }

  res.status(err.statusCode || 500).json({
    success: false,
    message: err.message || "Server Error",
  });
});

const PORT = process.env.PORT || 5000;

app.listen(PORT, () => {
  console.log(
    `🚀 Server running in ${process.env.NODE_ENV} mode on port ${PORT}`
  );
});

// Handle unhandled promise rejections
process.on("unhandledRejection", (err, promise) => {
  console.log(`❌ Unhandled Rejection: ${err.message}`);
  // Close server & exit process
  process.exit(1);
});

// Handle uncaught exceptions
process.on("uncaughtException", (err) => {
  console.log(`❌ Uncaught Exception: ${err.message}`);
  process.exit(1);
});
