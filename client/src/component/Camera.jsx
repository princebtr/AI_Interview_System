import React, { useRef, useState, useEffect } from "react";
import Webcam from "react-webcam";
import axios from "axios";
import { getApiUrl } from "../config/api.js";

const Camera = () => {
  const webcamRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const [recording, setRecording] = useState(false);
  const [recordedChunks, setRecordedChunks] = useState([]);
  const [showWarning, setShowWarning] = useState(false);

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      alert("Tab switching detected! This may be considered cheating.");
    }
  });

  const startRecording = () => {
    if (webcamRef.current && webcamRef.current.stream) {
      mediaRecorderRef.current = new MediaRecorder(webcamRef.current.stream, {
        mimeType: "video/webm",
      });

      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          setRecordedChunks((prev) => [...prev, event.data]);
        }
      };

      mediaRecorderRef.current.start();
      setRecording(true);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current) {
      mediaRecorderRef.current.stop();
      setRecording(false);
    }
  };

  const detectFaces = async () => {
    const imageSrc = webcamRef.current.getScreenshot();
    const blob = await fetch(imageSrc).then((res) => res.blob());
    const formData = new FormData();
    formData.append("image", blob, "frame.jpg");

    try {
      const response = await axios.post(
        getApiUrl("/detect_faces", true),
        formData
      );
      if (response.data.count > 1) {
        setShowWarning(true);
        setTimeout(() => setShowWarning(false), 3000);
      }
      console.log("Faces detected:", response.data.count);
    } catch (error) {
      console.error("Face detection error:", error);
    }
  };

  const detectPhones = async () => {
    const imageSrc = webcamRef.current.getScreenshot();
    const blob = await fetch(imageSrc).then((res) => res.blob());
    const formData = new FormData();
    formData.append("image", blob, "frame.jpg");

    try {
      const response = await axios.post(
        getApiUrl("/detect_phone", true),
        formData
      );
      if (response.data.phone_detected) {
        alert("Phone detected! Please put it away.");
        setShowWarning(true);
        setTimeout(() => setShowWarning(false), 3000);
      }
      console.log("Phone detected:", response.data.phone_detected);
    } catch (error) {
      console.error("Phone detection error:", error);
    }
  };

  const handleStartInterview = async (e) => {
    e.preventDefault();

    const screenshot = webcamRef.current.getScreenshot();
    const blob = await fetch(screenshot).then((res) => res.blob());

    const formData = new FormData();
    formData.append("screenshot", blob, "frame.jpg");

    try {
      await axios.post(getApiUrl("/modify_details", true), formData);
      startRecording();
    } catch (error) {
      console.error("Error saving user details:", error);
    }
  };

  useEffect(() => {
    const interval = setInterval(() => {
      detectFaces();
      detectPhones();
    }, 2000);

    return () => {
      clearInterval(interval);
      if (
        mediaRecorderRef.current &&
        mediaRecorderRef.current.state !== "inactive"
      ) {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

  return (
    <div className="fixed top-17 right-4 z-50">
      {/* Minimal Camera Card */}
      <div className="bg-white rounded-xl shadow-lg overflow-hidden w-80">
        {/* Camera Container */}
        <div className="relative">
          <Webcam
            audio={true}
            ref={webcamRef}
            mirrored={true}
            screenshotFormat="image/jpeg"
            className="w-full h-auto"
            videoConstraints={{ facingMode: "user" }}
          />

          {/* Recording Overlay */}
          {recording && (
            <div className="absolute top-2 left-2 bg-red-500 text-white px-2 py-1 rounded-full text-xs font-medium flex items-center animate-pulse">
              <div className="w-1.5 h-1.5 bg-white rounded-full mr-1 animate-pulse"></div>
              REC
            </div>
          )}
        </div>

        {/* Multiple Faces Warning - Below Camera */}
        {showWarning && (
          <div className="p-3 bg-red-50 border-t border-red-200">
            <div className="flex items-center space-x-2">
              <div className="text-lg">⚠️</div>
              <div>
                <div className="text-red-800 font-semibold text-sm">
                  Multiple faces detected!
                </div>
                <div className="text-red-600 text-xs">
                  Please ensure only one person is visible
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Hidden Form for Interview Controls */}
        <form onSubmit={handleStartInterview} className="hidden">
          {!recording ? (
            <button type="submit">Start Interview</button>
          ) : (
            <button type="button" onClick={stopRecording}>
              Stop Interview
            </button>
          )}
        </form>
      </div>
    </div>
  );
};

export default Camera;
