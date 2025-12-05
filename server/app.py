from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import numpy as np
import cv2
from ultralytics import YOLO
from datetime import datetime
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from config import Config

app = Flask(__name__)
CORS(app)

client = MongoClient(Config.MONGODB_URI)
db = client["interview_db"]
users_collection = db["user_details"]
os.makedirs("screenshots", exist_ok=True)

model = YOLO('yolov8n.pt')

api_key = Config.API_KEY

GEN_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

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

@app.route('/generate-mcq-questions', methods=['POST'])
def generate_mcq_questions():
    try:
        data = request.get_json()
        subject = data.get('subject', '')
        num_questions = data.get('numQuestions', 5)
        
        if not subject or not num_questions:
            return jsonify({'error': 'Subject and number of questions are required'}), 400
        
        prompt = (
            f"Generate {num_questions} multiple choice questions (MCQ) for the subject: {subject}\n\n"
            f"Format each question as follows:\n"
            f"Q1. [Question text]\n"
            f"A) [Option A]\n"
            f"B) [Option B]\n"
            f"C) [Option C]\n"
            f"D) [Option D]\n"
            f"Correct Answer: [A/B/C/D]\n\n"
            f"Repeat this format for all {num_questions} questions. "
            f"Make sure each question has exactly 4 options (A, B, C, D) and clearly indicate the correct answer."
        )
        
        res = requests.post(GEN_URL, json={
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }, headers={"Content-Type": "application/json"})
        
        result = res.json()
        questions_text = result.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        
        # Parse the questions into structured format
        questions = parse_mcq_questions(questions_text, num_questions)
        
        return jsonify({'questions': questions})
    except Exception as e:
        print(f"Error generating MCQ questions: {str(e)}")
        return jsonify({'error': str(e)}), 500

def parse_mcq_questions(text, num_questions):
    """Parse MCQ questions from Gemini response text"""
    import re
    questions = []
    
    # Split by question markers
    question_blocks = re.split(r'Q\d+\.', text)
    question_blocks = [block.strip() for block in question_blocks if block.strip()]
    
    for i, block in enumerate(question_blocks[:num_questions]):
        try:
            # Extract question text (before options)
            question_match = re.search(r'^(.+?)(?=A\)|$)', block, re.DOTALL)
            question_text = question_match.group(1).strip() if question_match else f"Question {i+1}"
            
            # Extract options
            options = {}
            for option in ['A', 'B', 'C', 'D']:
                option_match = re.search(rf'{option}\)\s*(.+?)(?=[A-D]\)|Correct Answer:|$)', block, re.DOTALL)
                if option_match:
                    options[option] = option_match.group(1).strip()
            
            # Extract correct answer
            correct_match = re.search(r'Correct Answer:\s*([A-D])', block, re.IGNORECASE)
            correct_answer = correct_match.group(1).upper() if correct_match else 'A'
            
            questions.append({
                'id': i + 1,
                'question': question_text,
                'options': options,
                'correctAnswer': correct_answer
            })
        except Exception as e:
            print(f"Error parsing question {i+1}: {str(e)}")
            # Fallback: create a simple question structure
            questions.append({
                'id': i + 1,
                'question': f"Question {i+1}",
                'options': {'A': 'Option A', 'B': 'Option B', 'C': 'Option C', 'D': 'Option D'},
                'correctAnswer': 'A'
            })
    
    return questions

@app.route('/evaluate-mcq-answers', methods=['POST'])
def evaluate_mcq_answers():
    try:
        data = request.get_json()
        questions = data.get('questions', [])
        user_answers = data.get('userAnswers', {})
        
        if not questions or not user_answers:
            return jsonify({'error': 'Questions and user answers are required'}), 400
        
        results = []
        correct_count = 0
        
        for question in questions:
            question_id = str(question.get('id', ''))
            correct_answer = question.get('correctAnswer', '')
            user_answer = user_answers.get(question_id, '')
            
            is_correct = user_answer.upper() == correct_answer.upper()
            if is_correct:
                correct_count += 1
            
            results.append({
                'questionId': question_id,
                'question': question.get('question', ''),
                'correctAnswer': correct_answer,
                'userAnswer': user_answer,
                'isCorrect': is_correct
            })
        
        total_questions = len(questions)
        score_percentage = (correct_count / total_questions * 100) if total_questions > 0 else 0
        
        return jsonify({
            'results': results,
            'score': correct_count,
            'totalQuestions': total_questions,
            'percentage': round(score_percentage, 2)
        })
    except Exception as e:
        print(f"Error evaluating MCQ answers: {str(e)}")
        return jsonify({'error': str(e)}), 500

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
        print("Received request to start interview session")

        # Save screenshot if it exists
        screenshot = request.files.get("screenshot")
        screenshot_filename = None
        if screenshot:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            screenshot_filename = f"screenshots/interview_{timestamp}.jpg"
            screenshot.save(screenshot_filename)

        # Save interview session info to MongoDB
        session_data = {
            "timestamp": datetime.now(),
            "screenshot_path": screenshot_filename,
            "status": "started"
        }

        users_collection.insert_one(session_data)
        return jsonify({"message": "Interview session started successfully!"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Run Flask on port 5001 to avoid conflict with Express (port 5000)
    print(f"🚀 Flask AI Server starting on port {Config.FLASK_PORT}")
    app.run(debug=Config.DEBUG, port=Config.FLASK_PORT, host='0.0.0.0')
