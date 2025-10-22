const axios = require("axios");

// Generate AI question
const generateQuestion = async (req, res) => {
  try {
    const { subject } = req.body;

    if (!subject || !subject.trim()) {
      return res.status(400).json({
        success: false,
        message: "Subject is required",
      });
    }

    const prompt = `Generate one interview question for the subject: ${subject}`;

    const response = await axios.post(
      `${process.env.GEMINI_API_URL}?key=${process.env.GEMINI_API_KEY}`,
      {
        contents: [
          {
            parts: [{ text: prompt }],
          },
        ],
      },
      {
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    const result = response.data;
    const question =
      result.candidates?.[0]?.content?.parts?.[0]?.text ||
      "No question generated.";

    console.log("Generated Question:", question);

    res.status(200).json({
      success: true,
      question: question,
    });
  } catch (error) {
    console.error("Question generation error:", error.message);
    res.status(500).json({
      success: false,
      message: "Failed to generate question",
    });
  }
};

// Evaluate answer
const evaluateAnswer = async (req, res) => {
  try {
    const { question, answer } = req.body;

    if (!question || !answer) {
      return res.status(400).json({
        success: false,
        message: "Question and answer are required",
      });
    }

    const prompt = `Evaluate the following answer for the given question on a scale of 0 to 10.

Question: ${question}
Answer: ${answer}

Only respond with a number from 0 to 10, no explanation. Give a score based on the relevance and correctness of the answer, and be lenient in evaluation.`;

    const response = await axios.post(
      `${process.env.GEMINI_API_URL}?key=${process.env.GEMINI_API_KEY}`,
      {
        contents: [
          {
            parts: [{ text: prompt }],
          },
        ],
      },
      {
        headers: {
          "Content-Type": "application/json",
        },
      }
    );

    const result = response.data;
    const evaluation = result.candidates?.[0]?.content?.parts?.[0]?.text || "0";

    // Extract number from response
    const score = evaluation.match(/\d+/)?.[0] || "0";

    res.status(200).json({
      success: true,
      evaluation: score,
    });
  } catch (error) {
    console.error("Answer evaluation error:", error.message);
    res.status(500).json({
      success: false,
      message: "Failed to evaluate answer",
    });
  }
};

module.exports = {
  generateQuestion,
  evaluateAnswer,
};
