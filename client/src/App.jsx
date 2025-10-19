import React, { useEffect, useState } from 'react';
import Camera from "./component/Camere";
import QuestionGenerator from "./component/QuestionGenerator";
// import AudioRecorder from "./component/Audio";

const App = () => {



  return (
    <div className="min-h-screen bg-gray-100 font-sans">
      {/* Navigation Bar */}
      <nav className="bg-white shadow-md p-4">
        <ul className="flex justify-center space-x-8">
          <li className="text-blue-500 hover:text-blue-700 cursor-pointer font-semibold">Home</li>
          <li className="text-blue-500 hover:text-blue-700 cursor-pointer font-semibold">About</li>
        </ul>
      </nav>

      {/* Main Content */}
      <main className="flex flex-col md:flex-row justify-center items-center gap-8 p-6">
        <div className="bg-white p-6 rounded-lg shadow-md w-full max-w-md">
          <h4 className="text-xl font-semibold text-gray-800 mb-4 text-center">AI-BASED MOCK INTERVIEW</h4>
          <Camera />
        </div>
        <div className="bg-white p-6 rounded-lg shadow-md w-full max-w-md">
          <h4 className="text-xl font-semibold text-gray-800 mb-4 text-center">AI-BASED MOCK INTERVIEW</h4>
          <QuestionGenerator />
        </div>

        {/* Uncomment this if you want to include the AudioRecorder */}
        {/* <div className="bg-white p-6 rounded-lg shadow-md w-full max-w-md">
          <h4 className="text-xl font-semibold text-gray-800 mb-4 text-center">Audio Recorder</h4>
          <AudioRecorder />
        </div> */}
      </main>

      {/* ✅ Show Flask message */}
      
    </div>
  );
};

export default App;
