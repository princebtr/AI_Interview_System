import React, { useRef, useState, useEffect } from "react";
import Webcam from "react-webcam";
import axios from "axios";

const Camera = () => {
    const webcamRef = useRef(null);
    const mediaRecorderRef = useRef(null);
    const [recording, setRecording] = useState(false);
    const [recordedChunks, setRecordedChunks] = useState([]);
    const [showWarning, setShowWarning] = useState(false);
    const [name, setName] = useState("");
    const [age, setAge] = useState("");
    const [gender, setGender] = useState("");


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
        const blob = await fetch(imageSrc).then(res => res.blob());
        const formData = new FormData();
        formData.append("image", blob, "frame.jpg");

        try {
            const response = await axios.post("http://localhost:5000/detect_faces", formData);
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
        const blob = await fetch(imageSrc).then(res => res.blob());
        const formData = new FormData();
        formData.append("image", blob, "frame.jpg");

        try {
            const response = await axios.post("http://localhost:5000/detect_phone", formData);
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
        const blob = await fetch(screenshot).then(res => res.blob());

        const formData = new FormData();
        formData.append("name", name);
        formData.append("age", age);
        formData.append("gender", gender);
        formData.append("screenshot", blob, "frame.jpg");

        try {
            await axios.post("http://localhost:5000/modify_details", formData);
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
            if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
                mediaRecorderRef.current.stop();
            }
        };
    }, []);

    return (
        <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100 font-sans">
            {showWarning && <div className="text-2xl text-red-500">⚠️ Multiple faces detected!</div>}
            <h4 className="text-2xl font-bold mb-6 text-gray-800">Mock Interview Recorder</h4>
            <div className="bg-white p-4 rounded-lg shadow-md">
                <Webcam
                    audio={true}
                    ref={webcamRef}
                    mirrored={true}
                    screenshotFormat="image/jpeg"
                    className="rounded-lg border border-gray-300"
                    videoConstraints={{ facingMode: "user" }}
                />
                <form onSubmit={handleStartInterview} className="flex flex-col space-y-4 mt-4">
                    <input
                        type="text"
                        name="name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        placeholder="Enter your name"
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                    />
                    <input
                        type="text"
                        name="age"
                        value={age}
                        onChange={(e) => setAge(e.target.value)}
                        placeholder="Enter your age"
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                    />
                    <input
                        type="text"
                        name="gender"
                        value={gender}
                        onChange={(e) => setGender(e.target.value)}
                        placeholder="Enter your gender"
                        className="w-full px-4 py-2 border border-gray-300 rounded-lg"
                    />
                    {!recording ? (
                        <button
                            type="submit"
                            className="px-6 py-2 bg-green-500 text-white font-semibold rounded-lg shadow-md hover:bg-green-600 transition duration-300"
                        >
                            Start Interview
                        </button>
                    ) : (
                        <button
                            type="button"
                            onClick={stopRecording}
                            className="px-6 py-2 bg-red-500 text-white font-semibold rounded-lg shadow-md hover:bg-red-600 transition duration-300"
                        >
                            Stop Interview
                        </button>
                    )}
                </form>
            </div>
        </div>
    );
};

export default Camera;
