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
        if not data:
            return jsonify({'error': 'Invalid request data'}), 400
            
        subject = data.get('subject', '').strip()
        num_questions = data.get('numQuestions', 5)
        
        if not subject:
            return jsonify({'error': 'Subject is required'}), 400
        
        if not isinstance(num_questions, int) or num_questions < 1 or num_questions > 20:
            return jsonify({'error': 'Number of questions must be between 1 and 20'}), 400
        
        prompt = (
            f"Generate {num_questions} multiple choice questions (MCQ) for the subject: {subject}\n\n"
            f"Format each question EXACTLY as follows:\n"
            f"Q1. [Question text]\n"
            f"A) [Option A]\n"
            f"B) [Option B]\n"
            f"C) [Option C]\n"
            f"D) [Option D]\n"
            f"Correct Answer: [A/B/C/D]\n\n"
            f"Repeat this format for all {num_questions} questions. "
            f"Make sure each question has exactly 4 options (A, B, C, D) and clearly indicate the correct answer. "
            f"Only output the questions in the specified format, no additional text."
        )
        
        print(f"Generating {num_questions} MCQ questions for subject: {subject}")
        
        res = requests.post(GEN_URL, json={
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }, headers={"Content-Type": "application/json"}, timeout=30)
        
        if res.status_code != 200:
            error_msg = f"Gemini API error: {res.status_code}"
            try:
                error_data = res.json()
                error_msg = error_data.get('error', {}).get('message', error_msg)
            except:
                pass
            print(f"Gemini API error: {error_msg}")
            return jsonify({'error': f'Failed to generate questions: {error_msg}'}), 500
        
        result = res.json()
        
        # Check if response has candidates
        if 'candidates' not in result or not result['candidates']:
            print(f"Invalid Gemini response structure: {result}")
            return jsonify({'error': 'Invalid response from AI service'}), 500
        
        # Extract text from response
        candidate = result['candidates'][0]
        if 'content' not in candidate or 'parts' not in candidate['content']:
            print(f"Invalid candidate structure: {candidate}")
            return jsonify({'error': 'Invalid response format from AI service'}), 500
        
        questions_text = candidate['content']['parts'][0].get('text', '')
        
        if not questions_text:
            print(f"Empty response from Gemini")
            return jsonify({'error': 'No questions generated. Please try again with a different subject.'}), 500
        
        print(f"Received questions text (first 200 chars): {questions_text[:200]}")
        
        # Parse the questions into structured format
        questions = parse_mcq_questions(questions_text, num_questions)
        
        if not questions or len(questions) == 0:
            print(f"Failed to parse questions from text")
            return jsonify({'error': 'Failed to parse generated questions. Please try again.'}), 500
        
        print(f"Successfully parsed {len(questions)} questions")
        return jsonify({'questions': questions})
        
    except requests.exceptions.Timeout:
        print("Request timeout")
        return jsonify({'error': 'Request timeout. Please try again.'}), 500
    except requests.exceptions.RequestException as e:
        print(f"Request error: {str(e)}")
        return jsonify({'error': f'Network error: {str(e)}'}), 500
    except Exception as e:
        print(f"Error generating MCQ questions: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Error generating questions: {str(e)}'}), 500

def parse_mcq_questions(text, num_questions):
    """Parse MCQ questions from Gemini response text"""
    import re
    questions = []
    
    # Clean up the text - remove markdown formatting if present
    text = re.sub(r'```[a-z]*\n?', '', text)
    text = re.sub(r'```', '', text)
    
    # Try multiple patterns to split questions
    # Pattern 1: Q1., Q2., etc.
    question_blocks = re.split(r'Q\d+\.', text)
    if len(question_blocks) <= 1:
        # Pattern 2: 1., 2., etc.
        question_blocks = re.split(r'\n\s*\d+\.', text)
    if len(question_blocks) <= 1:
        # Pattern 3: Just split by double newlines
        question_blocks = re.split(r'\n\n+', text)
    
    question_blocks = [block.strip() for block in question_blocks if block.strip()]
    
    for i, block in enumerate(question_blocks[:num_questions]):
        try:
            # Extract question text (before options)
            # Try multiple patterns
            question_match = re.search(r'^(.+?)(?=\n\s*[A-D]\)|$)', block, re.DOTALL | re.MULTILINE)
            if not question_match:
                question_match = re.search(r'^(.+?)(?=A\)|$)', block, re.DOTALL)
            
            question_text = question_match.group(1).strip() if question_match else f"Question {i+1}"
            # Clean up question text
            question_text = re.sub(r'^\d+\.\s*', '', question_text).strip()
            question_text = re.sub(r'^Q\d+\.\s*', '', question_text).strip()
            
            # Extract options - try multiple patterns
            options = {}
            for option in ['A', 'B', 'C', 'D']:
                # Pattern 1: A) option text
                option_match = re.search(rf'{option}\)\s*(.+?)(?=\n\s*[A-D]\)|Correct Answer:|Answer:|$)', block, re.DOTALL | re.MULTILINE)
                if not option_match:
                    # Pattern 2: A. option text
                    option_match = re.search(rf'{option}\.\s*(.+?)(?=\n\s*[A-D]\.|Correct Answer:|Answer:|$)', block, re.DOTALL | re.MULTILINE)
                if not option_match:
                    # Pattern 3: A) option text (simpler)
                    option_match = re.search(rf'{option}\)\s*(.+?)(?=[A-D]\)|Correct Answer:|$)', block, re.DOTALL)
                
                if option_match:
                    option_text = option_match.group(1).strip()
                    # Clean up option text
                    option_text = re.sub(r'\n+', ' ', option_text).strip()
                    options[option] = option_text
            
            # If we don't have all 4 options, try to fill them
            if len(options) < 4:
                # Try to find options in a different format
                lines = block.split('\n')
                option_letters = ['A', 'B', 'C', 'D']
                for line in lines:
                    for opt in option_letters:
                        if opt not in options:
                            if re.match(rf'^\s*{opt}[\)\.]\s*.+', line, re.IGNORECASE):
                                options[opt] = re.sub(rf'^\s*{opt}[\)\.]\s*', '', line, flags=re.IGNORECASE).strip()
            
            # Ensure we have at least 4 options
            for opt in ['A', 'B', 'C', 'D']:
                if opt not in options:
                    options[opt] = f"Option {opt}"
            
            # Extract correct answer - try multiple patterns
            correct_answer = 'A'  # Default
            correct_match = re.search(r'Correct Answer:\s*([A-D])', block, re.IGNORECASE)
            if not correct_match:
                correct_match = re.search(r'Answer:\s*([A-D])', block, re.IGNORECASE)
            if not correct_match:
                correct_match = re.search(r'Correct:\s*([A-D])', block, re.IGNORECASE)
            if not correct_match:
                # Try to find it at the end of the block
                correct_match = re.search(r'([A-D])\s*$', block.strip(), re.IGNORECASE)
            
            if correct_match:
                correct_answer = correct_match.group(1).upper()
            
            questions.append({
                'id': i + 1,
                'question': question_text,
                'options': options,
                'correctAnswer': correct_answer
            })
            
            print(f"Parsed question {i+1}: {question_text[:50]}...")
            
        except Exception as e:
            print(f"Error parsing question {i+1}: {str(e)}")
            import traceback
            traceback.print_exc()
            # Fallback: create a simple question structure
            questions.append({
                'id': i + 1,
                'question': f"Question {i+1} - Parsing error occurred",
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
