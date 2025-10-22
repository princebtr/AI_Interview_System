import React from "react";
import { Link } from "react-router-dom";
import Camera from "../component/Camere";
import QuestionGenerator from "../component/QuestionGenerator";

const InterviewSystem = () => {
  return (
    <div className="min-h-screen bg-gray-100">
      {/* Navigation Bar */}
      <nav className="bg-white shadow-md p-4">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <div className="flex space-x-8">
            <Link
              to="/dashboard"
              className="text-blue-500 hover:text-blue-700 cursor-pointer font-semibold"
            >
              Dashboard
            </Link>
            <span className="text-blue-500 font-semibold">
              Interview System
            </span>
          </div>
          <div className="text-sm text-gray-600">
            AI-Based Mock Interview Platform
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="flex flex-col md:flex-row justify-center items-center gap-8 p-6">
        <div className="bg-white p-6 rounded-lg shadow-md w-full max-w-md">
          <h4 className="text-xl font-semibold text-gray-800 mb-4 text-center">
            Camera & Face Detection
          </h4>
          <Camera />
        </div>
        <div className="bg-white p-6 rounded-lg shadow-md w-full max-w-md">
          <h4 className="text-xl font-semibold text-gray-800 mb-4 text-center">
            AI Question Generator
          </h4>
          <QuestionGenerator />
        </div>
      </main>

      {/* Instructions */}
      <div className="max-w-4xl mx-auto px-6 pb-8">
        <div className="bg-white p-6 rounded-lg shadow-md">
          <h3 className="text-lg font-semibold text-gray-800 mb-4">
            How to Use the Interview System
          </h3>
          <div className="grid md:grid-cols-2 gap-6">
            <div>
              <h4 className="font-medium text-gray-700 mb-2">Camera System:</h4>
              <ul className="text-sm text-gray-600 space-y-1">
                <li>• Allows camera access for face detection</li>
                <li>• Monitors for multiple faces (cheating detection)</li>
                <li>• Detects phone usage during interview</li>
                <li>• Takes screenshots for security</li>
              </ul>
            </div>
            <div>
              <h4 className="font-medium text-gray-700 mb-2">
                Question Generator:
              </h4>
              <ul className="text-sm text-gray-600 space-y-1">
                <li>• Enter your subject/topic</li>
                <li>• AI generates relevant interview questions</li>
                <li>• Submit your answers for evaluation</li>
                <li>• Get AI-powered feedback and scoring</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default InterviewSystem;
