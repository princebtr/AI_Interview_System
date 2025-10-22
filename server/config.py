import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    FLASK_APP = os.getenv('FLASK_APP', 'app.py')
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    FLASK_PORT = int(os.getenv('FLASK_PORT', 5001))
    API_KEY = os.getenv('API_KEY', 'AIzaSyBI0xLveYGlI3uGdmTDMSD1qOYInSl9Aac')
    MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://localhost:27017/interview_db')
    DEBUG = os.getenv('FLASK_ENV') == 'development'
