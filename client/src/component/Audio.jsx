import React, { useState } from "react";

const AudioRecorder = () => {
    const [isRecording, setIsRecording] = useState(false);
    const [audioBlob, setAudioBlob] = useState(null);
    const [transcription, setTranscription] = useState("");

    let mediaRecorder;
    let audioChunks = [];

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream);

            mediaRecorder.ondataavailable = (event) => {
                audioChunks.push(event.data);
            };

            mediaRecorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: "audio/wav" });
                setAudioBlob(audioBlob);
                audioChunks = [];
                convertAudioToText(audioBlob).then((text) => {
                    console.log("Transcription:", text);
                });
            };

            mediaRecorder.start();
            setIsRecording(true);

            // Automatically stop recording after 5 seconds
            setTimeout(() => {
                if (mediaRecorder.state === "recording") {
                    mediaRecorder.stop();
                    setIsRecording(false);
                }
            }, 5000);
        } catch (error) {
            console.error("Error accessing microphone:", error);
        }
    };

    const stopRecording = () => {
        if (mediaRecorder) {
            mediaRecorder.stop();
            setIsRecording(false);
        }
    };

    const convertAudioToText = async (audioBlob) => {
        const formData = new FormData();
        formData.append("audio", audioBlob);

        try {
            const response = await fetch("https://mock-interview-49z9.onrender.com/transcribe", {
                method: "POST",
                body: formData,
            });

            if (response.ok) {
                const data = await response.json();
                setTranscription(data.transcription);
            } else {
                console.error("Failed to transcribe audio");
            }
        } catch (error) {
            console.error("Error sending audio to backend:", error);
        }
    };

    return (
        <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100 font-sans">
            <h1 className="text-3xl font-bold mb-6">Audio Recorder</h1>
            <button
                onClick={isRecording ? stopRecording : startRecording}
                className={`px-6 py-3 text-white font-semibold rounded-lg shadow-md transition duration-300 ${
                    isRecording ? "bg-red-500 hover:bg-red-600" : "bg-green-500 hover:bg-green-600"
                }`}
            >
                {isRecording ? "Stop Recording" : "Start Recording"}
            </button>
            {transcription && (
                <div className="mt-6 p-4 bg-white rounded-lg shadow-md w-4/5 md:w-1/2">
                    <h2 className="text-xl font-semibold mb-2">Transcription:</h2>
                    <p className="text-gray-700">{transcription}</p>
                </div>
            )}
        </div>
    );
};

export default AudioRecorder;
