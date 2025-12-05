import React, { useState } from "react";
import { getApiUrl } from "../config/api.js";

const QuickAssessment = () => {
  const [subject, setSubject] = useState("");
  const [numQuestions, setNumQuestions] = useState(5);
  const [questions, setQuestions] = useState([]);
  const [userAnswers, setUserAnswers] = useState({});
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [showResults, setShowResults] = useState(false);

  const generateQuestions = async () => {
    if (!subject.trim()) {
      alert("Please enter a subject.");
      return;
    }

    if (numQuestions < 1 || numQuestions > 20) {
      alert("Number of questions must be between 1 and 20.");
      return;
    }

    setLoading(true);
    setResults(null);
    setShowResults(false);
    setUserAnswers({});

    try {
      const response = await fetch(getApiUrl("/generate-mcq-questions", true), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ subject, numQuestions }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: `HTTP ${response.status}: ${response.statusText}` }));
        throw new Error(errorData.error || `Server error: ${response.status}`);
      }

      const data = await response.json();
      
      if (data.error) {
        alert(`Error: ${data.error}`);
        setLoading(false);
        return;
      }

      if (!data.questions || data.questions.length === 0) {
        alert("No questions were generated. Please try again with a different subject.");
        setLoading(false);
        return;
      }

      setQuestions(data.questions || []);
      setLoading(false);
    } catch (error) {
      console.error("Error generating questions:", error);
      const errorMessage = error.message || "Failed to generate questions. Please check your connection and try again.";
      alert(`Error: ${errorMessage}`);
      setLoading(false);
    }
  };

  const handleAnswerChange = (questionId, answer) => {
    setUserAnswers({
      ...userAnswers,
      [questionId]: answer,
    });
  };

  const submitAssessment = async () => {
    // Check if all questions are answered
    const unansweredQuestions = questions.filter(
      (q) => !userAnswers[q.id.toString()]
    );

    if (unansweredQuestions.length > 0) {
      alert(`Please answer all questions. ${unansweredQuestions.length} question(s) remaining.`);
      return;
    }

    setLoading(true);

    try {
      const response = await fetch(getApiUrl("/evaluate-mcq-answers", true), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ questions, userAnswers }),
      });

      const data = await response.json();
      
      if (data.error) {
        alert(`Error: ${data.error}`);
        setLoading(false);
        return;
      }

      setResults(data);
      setShowResults(true);
      setLoading(false);
    } catch (error) {
      console.error("Error evaluating answers:", error);
      alert("Failed to evaluate answers. Please try again.");
      setLoading(false);
    }
  };

  const resetAssessment = () => {
    setQuestions([]);
    setUserAnswers({});
    setResults(null);
    setShowResults(false);
    setSubject("");
    setNumQuestions(5);
  };

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h2 className="text-2xl font-bold text-gray-900 mb-2">
            Quick Assessment
          </h2>
          <p className="text-gray-600">
            Test your knowledge with AI-generated multiple choice questions
          </p>
        </div>

        {/* Input Form */}
        {questions.length === 0 && !showResults && (
          <div className="bg-white rounded-xl shadow-lg p-6 mb-6">
            <div className="space-y-4">
              <div>
                <label className="block text-gray-700 font-semibold mb-2">
                  Subject:
                </label>
                <input
                  type="text"
                  value={subject}
                  onChange={(e) => setSubject(e.target.value)}
                  placeholder="e.g., JavaScript, Python, Data Structures"
                  disabled={loading}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              <div>
                <label className="block text-gray-700 font-semibold mb-2">
                  Number of Questions:
                </label>
                <input
                  type="number"
                  value={numQuestions}
                  onChange={(e) => setNumQuestions(parseInt(e.target.value) || 5)}
                  min="1"
                  max="20"
                  disabled={loading}
                  className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
                <p className="text-sm text-gray-500 mt-1">
                  Choose between 1 and 20 questions
                </p>
              </div>

              <button
                onClick={generateQuestions}
                disabled={loading}
                className={`w-full px-4 py-3 text-white font-semibold rounded-lg shadow-md transition duration-300 ${
                  loading
                    ? "bg-gray-400 cursor-not-allowed"
                    : "bg-blue-500 hover:bg-blue-600"
                }`}
              >
                {loading ? "Generating Questions..." : "Generate Questions"}
              </button>
            </div>
          </div>
        )}

        {/* Questions Display */}
        {questions.length > 0 && !showResults && (
          <div className="space-y-6">
            {questions.map((question) => (
              <div
                key={question.id}
                className="bg-white rounded-xl shadow-lg p-6"
              >
                <h3 className="text-lg font-semibold text-gray-800 mb-4">
                  Question {question.id}: {question.question}
                </h3>
                <div className="space-y-3">
                  {["A", "B", "C", "D"].map((option) => (
                    <label
                      key={option}
                      className="flex items-center space-x-3 p-3 border border-gray-200 rounded-lg hover:bg-gray-50 cursor-pointer transition-colors"
                    >
                      <input
                        type="radio"
                        name={`question-${question.id}`}
                        value={option}
                        checked={userAnswers[question.id.toString()] === option}
                        onChange={() => handleAnswerChange(question.id.toString(), option)}
                        className="w-4 h-4 text-blue-600 focus:ring-blue-500"
                      />
                      <span className="font-medium text-gray-700">{option})</span>
                      <span className="text-gray-700">
                        {question.options[option] || `Option ${option}`}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))}

            <div className="bg-white rounded-xl shadow-lg p-6">
              <button
                onClick={submitAssessment}
                disabled={loading}
                className={`w-full px-4 py-3 text-white font-semibold rounded-lg shadow-md transition duration-300 ${
                  loading
                    ? "bg-gray-400 cursor-not-allowed"
                    : "bg-green-500 hover:bg-green-600"
                }`}
              >
                {loading ? "Evaluating..." : "Submit Assessment"}
              </button>
            </div>
          </div>
        )}

        {/* Results Display */}
        {showResults && results && (
          <div className="bg-white rounded-xl shadow-lg p-6">
            <div className="mb-6">
              <h3 className="text-2xl font-bold text-gray-900 mb-4">
                Assessment Results
              </h3>
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-6 mb-6">
                <div className="text-center">
                  <div className="text-4xl font-bold text-blue-600 mb-2">
                    {results.score} / {results.totalQuestions}
                  </div>
                  <div className="text-xl text-gray-700 mb-1">
                    {results.percentage}%
                  </div>
                  <div className="text-sm text-gray-600">
                    {results.percentage >= 70
                      ? "Excellent! 🎉"
                      : results.percentage >= 50
                      ? "Good job! 👍"
                      : "Keep practicing! 💪"}
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-4 mb-6">
              {results.results.map((result) => (
                <div
                  key={result.questionId}
                  className={`p-4 rounded-lg border-2 ${
                    result.isCorrect
                      ? "bg-green-50 border-green-200"
                      : "bg-red-50 border-red-200"
                  }`}
                >
                  <div className="flex items-start justify-between mb-2">
                    <h4 className="font-semibold text-gray-800">
                      Question {result.questionId}
                    </h4>
                    <span
                      className={`px-3 py-1 rounded-full text-sm font-medium ${
                        result.isCorrect
                          ? "bg-green-200 text-green-800"
                          : "bg-red-200 text-red-800"
                      }`}
                    >
                      {result.isCorrect ? "✓ Correct" : "✗ Incorrect"}
                    </span>
                  </div>
                  <p className="text-gray-700 mb-2">{result.question}</p>
                  <div className="space-y-1 text-sm">
                    <div className="text-gray-600">
                      <span className="font-medium">Your Answer:</span> {result.userAnswer || "Not answered"}
                    </div>
                    {!result.isCorrect && (
                      <div className="text-green-700">
                        <span className="font-medium">Correct Answer:</span> {result.correctAnswer}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>

            <button
              onClick={resetAssessment}
              className="w-full px-4 py-3 bg-blue-500 text-white font-semibold rounded-lg shadow-md hover:bg-blue-600 transition duration-300"
            >
              Start New Assessment
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

export default QuickAssessment;

