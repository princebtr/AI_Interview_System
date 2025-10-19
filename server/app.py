from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import numpy as np
import cv2
from ultralytics import YOLO
from datetime import datetime
from pymongo import MongoClient
import os

app = Flask(__name__)
CORS(app)

client = MongoClient("mongodb://localhost:27017/")
db = client["interview_db"]
users_collection = db["user_details"]
os.makedirs("screenshots", exist_ok=True)

model = YOLO('yolov8n.pt')

API_KEY = 'AIzaSyBI0xLveYGlI3uGdmTDMSD1qOYInSl9Aac'

GEN_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={API_KEY}"

@app.route('/hello', methods=['GET'])
def hello():
    print("Hello from Flask!")  # prints in Flask console
    return jsonify({"message": "Hello from Flask API"})  # response to React

@app.route('/generate-question', methods=['POST'])
def generate_question():
    data = request.get_json()
    subject = data.get('subject', '')
    prompt = f"Generate one question for the subject: {subject}"
    print("P")
    res = requests.post(GEN_URL, json={
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }, headers={"Content-Type": "application/json"})
    
    result = res.json()
    question = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'No question generated.')
    print("Generated Question:", question)
    return jsonify({'question': question})



@app.route('/evaluate-answer', methods=['POST'])
def evaluate_answer():
    data = request.get_json()
    question = data.get('question', '')
    answer = data.get('answer', '')
    
    prompt = (
        f"Evaluate the following answer for the given question on a scale of 0 to 10.\n\n"
        f"Question: {question}\n"
        f"Answer: {answer}\n\n"
        f"Only respond with a number from 0 to 10, no explanation. "
        f"Give a score based on the relevance and correctness of the answer, and be lenient in evaluation."
)

    res = requests.post(GEN_URL, json={
        "contents": [{
            "parts": [{"text": prompt}]
        }]
    }, headers={"Content-Type": "application/json"})

    result = res.json()
    evaluation = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', 'invalid').lower()
    return jsonify({'evaluation': evaluation})

@app.route('/detect_faces', methods=['POST'])
def detect_faces():
    file = request.files['image']
    npimg = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    results = model.predict(source=frame, conf=0.3, verbose=False)
    faces = [d for d in results[0].boxes if int(d.cls[0]) == 0]

    return jsonify({'count': len(faces)})


@app.route('/detect_phone', methods=['POST'])
def detect_phone():
    file = request.files['image']
    npimg = np.frombuffer(file.read(), np.uint8)
    frame = cv2.imdecode(npimg, cv2.IMREAD_COLOR)
    results = model.predict(source=frame, conf=0.3, verbose=False)
    phone_detected = any(int(d.cls[0]) == 67 for d in results[0].boxes)
    return jsonify({'phone_detected': phone_detected})


@app.route("/modify_details", methods=["POST"])
def modify_details():
    try:
        print("Received request to modify user details")
        name = request.form.get("name")
        age = request.form.get("age")
        gender = request.form.get("gender")

        # Save screenshot if it exists
        screenshot = request.files.get("screenshot")
        screenshot_filename = None
        if screenshot:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            screenshot_filename = f"screenshots/{name}_{timestamp}.jpg"
            screenshot.save(screenshot_filename)

        # Save user info to MongoDB
        user_data = {
            "name": name,
            "age": age,
            "gender": gender,
            "timestamp": datetime.now(),
            "screenshot_path": screenshot_filename
        }

        users_collection.insert_one(user_data)
        return jsonify({"message": "User data saved successfully!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
