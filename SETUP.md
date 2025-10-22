# Interview System - Dual Backend Setup

This project uses both Express.js and Flask backends running simultaneously:

- **Express Backend (Port 5000)**: Handles authentication, user management, and main application logic
- **Flask Backend (Port 5001)**: Handles AI features (question generation, evaluation, face detection, phone detection)

## Prerequisites

### Node.js and npm

- Install Node.js (v16 or higher)
- Install npm (comes with Node.js)

### Python

- Install Python (v3.8 or higher)
- Install pip (comes with Python)

### MongoDB

- Install MongoDB locally or use MongoDB Atlas
- Make sure MongoDB is running on `mongodb://localhost:27017/`

## Installation & Setup

### 1. Install Express Backend Dependencies

```bash
cd express
npm install
```

### 2. Install Flask Backend Dependencies

```bash
cd server
pip install -r requirements.txt
```

### 3. Install Client Dependencies

```bash
cd client
npm install
```

### 4. Environment Configuration

#### Express Backend (.env file in express/config.env)

```
NODE_ENV=development
PORT=5000
MONGODB_URI=mongodb://localhost:27017/ai_interview_system
JWT_SECRET=your_jwt_secret_here
JWT_EXPIRE=7d
BCRYPT_ROUNDS=12

# Gemini AI Configuration
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_API_URL=https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent
```

#### Flask Backend (config.py is already configured)

The Flask backend uses the config.py file for configuration. Make sure your API key is set correctly.

## Running the Application

### Option 1: Use the Startup Scripts

#### Windows:

```bash
./start-backends.bat
```

#### Linux/Mac:

```bash
chmod +x start-backends.sh
./start-backends.sh
```

### Option 2: Manual Start

#### Terminal 1 - Express Backend:

```bash
cd express
npm run dev
```

#### Terminal 2 - Flask Backend:

```bash
cd server
python app.py
```

#### Terminal 3 - React Client:

```bash
cd client
npm run dev
```

## API Endpoints

### Express Backend (Port 5000)

- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `GET /api/health` - Health check
- `GET /api/cors-test` - CORS test

### Flask Backend (Port 5001)

- `GET /hello` - Hello endpoint
- `POST /generate-question` - Generate AI questions
- `POST /evaluate-answer` - Evaluate user answers
- `POST /detect_faces` - Face detection
- `POST /detect_phone` - Phone detection
- `POST /modify_details` - Save user details

## Troubleshooting

### Port Conflicts

- Express runs on port 5000
- Flask runs on port 5001
- React runs on port 5173 (Vite default)

### MongoDB Connection Issues

- Ensure MongoDB is running
- Check the connection string in config.env
- Verify database permissions

### Python Dependencies

- Make sure all packages in requirements.txt are installed
- Use virtual environment if needed: `python -m venv venv`

### Node.js Dependencies

- Run `npm install` in both express and client directories
- Check for any missing dependencies

## Development Notes

- The client automatically detects which backend to use based on the endpoint
- AI features (question generation, evaluation, face detection) use Flask
- Authentication and user management use Express
- Both backends share the same MongoDB database

## File Structure

```
interview System/
├── client/                 # React frontend
├── express/               # Express backend (main API)
├── server/                # Flask backend (AI features)
├── start-backends.bat     # Windows startup script
├── start-backends.sh      # Linux/Mac startup script
└── SETUP.md              # This file
```
