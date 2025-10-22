const express = require("express");
const {
  generateQuestion,
  evaluateAnswer,
} = require("../controllers/interviewController");

const router = express.Router();

// Interview routes
router.post("/generate-question", generateQuestion);
router.post("/evaluate-answer", evaluateAnswer);

module.exports = router;
