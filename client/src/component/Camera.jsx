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
  const [warningMessage, setWarningMessage] = useState("");
  const [tabSwitchCount, setTabSwitchCount] = useState(0);
  const lastPhoneAlertTime = useRef(0);
  const lastTabSwitchAlertTime = useRef(0);

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
    if (!webcamRef.current) {
      return;
    }

    try {
      const imageSrc = webcamRef.current.getScreenshot();
      if (!imageSrc) {
        return;
      }

      const blob = await fetch(imageSrc).then((res) => res.blob());
      const formData = new FormData();
      formData.append("image", blob, "frame.jpg");

      const response = await axios.post(
        getApiUrl("/detect_faces", true),
        formData
      );
      
      const faceCount = response.data.count || 0;
      console.log("Faces detected:", faceCount);
      
      if (faceCount > 1) {
        setWarningMessage(`Multiple faces detected (${faceCount})! Please ensure only one person is visible.`);
        setShowWarning(true);
        // Keep warning visible for 5 seconds
        setTimeout(() => {
          setShowWarning(false);
          setWarningMessage("");
        }, 5000);
      } else if (faceCount === 0) {
        // No face detected - could be an issue
        setWarningMessage("No face detected! Please ensure you are visible in the camera.");
        setShowWarning(true);
        setTimeout(() => {
          setShowWarning(false);
          setWarningMessage("");
        }, 3000);
      }
    } catch (error) {
      console.error("Face detection error:", error);
    }
  };

  const detectPhones = async () => {
    if (!webcamRef.current) {
      return;
    }

    try {
      const imageSrc = webcamRef.current.getScreenshot();
      if (!imageSrc) {
        return;
      }

      const blob = await fetch(imageSrc).then((res) => res.blob());
      const formData = new FormData();
      formData.append("image", blob, "frame.jpg");

      const response = await axios.post(
        getApiUrl("/detect_phone", true),
        formData
      );
      
      if (response.data.phone_detected) {
        const now = Date.now();
        // Show alert only if 5 seconds have passed since last alert
        if (now - lastPhoneAlertTime.current > 5000) {
          alert("⚠️ WARNING: Phone Detected!\n\nA phone has been detected in your camera view. Please put it away immediately. This violation may be reported.");
          lastPhoneAlertTime.current = now;
        }
        setWarningMessage("Phone detected! Please put it away.");
        setShowWarning(true);
        setTimeout(() => {
          setShowWarning(false);
          setWarningMessage("");
        }, 5000);
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

  // Tab switch detection
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.hidden) {
        const now = Date.now();
        setTabSwitchCount((prev) => {
          const newCount = prev + 1;
          
          // Show alert only if 3 seconds have passed since last alert
          if (now - lastTabSwitchAlertTime.current > 3000) {
            alert(`⚠️ WARNING: Tab Switch Detected!\n\nYou have switched tabs ${newCount} time(s). Tab switching during an interview/assessment may be considered cheating and could result in disqualification.\n\nPlease stay on this page.`);
            lastTabSwitchAlertTime.current = now;
          }
          
          setWarningMessage(`Tab switching detected! (${newCount} time(s)). This may be considered cheating.`);
          setShowWarning(true);
          setTimeout(() => {
            setShowWarning(false);
            setWarningMessage("");
          }, 5000);
          return newCount;
        });
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  // Face and phone detection
  useEffect(() => {
    if (!webcamRef.current) {
      return;
    }

    const interval = setInterval(() => {
      if (webcamRef.current) {
        detectFaces();
        detectPhones();
      }
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

        {/* Warning Messages - Below Camera */}
        {showWarning && (
          <div className="p-3 bg-red-50 border-t border-red-200 animate-pulse">
            <div className="flex items-center space-x-2">
              <div className="text-lg">⚠️</div>
              <div className="flex-1">
                <div className="text-red-800 font-semibold text-sm">
                  {warningMessage || "Warning detected!"}
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
