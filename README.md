# Interview System - MERN Stack with Secure Authentication

A comprehensive interview system built with MERN stack featuring secure user authentication, AI-powered question generation, and real-time monitoring capabilities.

## 🚀 Features

### Authentication System

- **Secure Registration & Login** with JWT tokens
- **Password hashing** using bcryptjs with salt rounds
- **Account lockout** after multiple failed login attempts
- **Form validation** with comprehensive error handling
- **Protected routes** with role-based access control
- **Session management** with secure cookies

### Interview System

- **AI-powered question generation** using Google's Gemini API
- **Real-time face detection** and monitoring
- **Cheating detection** (multiple faces, phone usage)
- **Answer evaluation** with AI scoring
- **Screenshot capture** for security
- **Responsive design** with modern UI

## 🛠️ Tech Stack

### Backend (Express.js)

- **Node.js** with Express.js framework
- **MongoDB** with Mongoose ODM
- **JWT** for authentication
- **bcryptjs** for password hashing
- **express-validator** for input validation
- **helmet** for security headers
- **express-rate-limit** for rate limiting
- **CORS** for cross-origin requests

### Frontend (React.js)

- **React 19** with modern hooks
- **React Router** for navigation
- **React Hook Form** for form management
- **Axios** for API calls
- **Tailwind CSS** for styling
- **React Hot Toast** for notifications
- **Heroicons** for icons

## 📋 Prerequisites

Before running this application, make sure you have the following installed:

- **Node.js** (v16 or higher)
- **MongoDB** (v4.4 or higher)
- **npm** or **yarn** package manager

## 🔧 Installation & Setup

### 1. Clone the Repository

```bash
git clone <your-repo-url>
cd interview-system
```

### 2. Backend Setup (Express)

Navigate to the express directory:

```bash
cd express
```

Install dependencies:

```bash
npm install
```

Set up environment variables:

```bash
# Copy the config file
cp config.env .env

# Edit the .env file with your configuration
```

Update the `config.env` file with your settings:

```env
NODE_ENV=development
PORT=5000
MONGODB_URI=mongodb://localhost:27017/interview_system
JWT_SECRET=your_super_secret_jwt_key_change_this_in_production
JWT_EXPIRE=7d
BCRYPT_ROUNDS=12
```

**Important**: Change the `JWT_SECRET` to a strong, random string in production!

Start the backend server:

```bash
# Development mode with nodemon
npm run dev

# Or production mode
npm start
```

The backend will be running on `http://localhost:5000`

### 3. Frontend Setup (React)

Navigate to the client directory:

```bash
cd client
```

Install dependencies:

```bash
npm install
```

Start the development server:

```bash
npm run dev
```

The frontend will be running on `http://localhost:5173`

### 4. MongoDB Setup

Make sure MongoDB is running on your system:

**Windows:**

```bash
# Start MongoDB service
net start MongoDB
```

**macOS (with Homebrew):**

```bash
brew services start mongodb-community
```

**Linux:**

```bash
sudo systemctl start mongod
```

## 🔐 Security Features

### Password Security

- Passwords are hashed using bcryptjs with 12 salt rounds
- Minimum 6 characters with complexity requirements
- Password confirmation validation

### Authentication Security

- JWT tokens with expiration
- Secure HTTP-only cookies
- Account lockout after 5 failed attempts (2-hour lockout)
- Rate limiting on authentication endpoints

### Input Validation

- Server-side validation with express-validator
- Client-side validation with react-hook-form
- XSS protection with helmet
- CORS configuration

### API Security

- Rate limiting (100 requests per 15 minutes)
- Stricter rate limiting for auth routes (5 requests per 15 minutes)
- Request timeout configuration
- Error handling without sensitive information exposure

## 📱 Usage

### 1. Registration

- Navigate to `/register`
- Fill in your details (name, email, password)
- Password must contain at least one uppercase, lowercase, and number
- Click "Create account"

### 2. Login

- Navigate to `/login`
- Enter your email and password
- Click "Sign in"

### 3. Dashboard

- View and update your profile information
- Change your password
- Access the interview system

### 4. Interview System

- Navigate to `/interview`
- Use the camera system for face detection
- Generate AI questions by entering a subject
- Submit answers for AI evaluation

## 🗂️ Project Structure

```
interview-system/
├── client/                 # React frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   │   ├── auth/       # Authentication components
│   │   │   └── ...
│   │   ├── context/        # React context (AuthContext)
│   │   ├── utils/          # Utility functions
│   │   └── ...
│   └── package.json
├── express/                # Express backend
│   ├── controllers/        # Route controllers
│   ├── middleware/         # Custom middleware
│   ├── models/            # MongoDB models
│   ├── routes/            # API routes
│   ├── server.js          # Main server file
│   └── package.json
├── server/                # Legacy Flask server (optional)
└── README.md
```

## 🔧 API Endpoints

### Authentication Routes

- `POST /api/auth/register` - User registration
- `POST /api/auth/login` - User login
- `GET /api/auth/logout` - User logout
- `GET /api/auth/me` - Get current user
- `PUT /api/auth/updatedetails` - Update user details
- `PUT /api/auth/updatepassword` - Update password

### Health Check

- `GET /api/health` - Server health check

## 🚨 Important Security Notes

1. **Change JWT Secret**: Always change the `JWT_SECRET` in production
2. **Environment Variables**: Never commit `.env` files to version control
3. **HTTPS**: Use HTTPS in production for secure cookie transmission
4. **Database Security**: Secure your MongoDB instance
5. **Rate Limiting**: Adjust rate limits based on your needs
6. **CORS**: Configure CORS properly for your domain

## 🐛 Troubleshooting

### Common Issues

1. **MongoDB Connection Error**

   - Ensure MongoDB is running
   - Check the connection string in config.env

2. **CORS Errors**

   - Verify CORS configuration in server.js
   - Check if frontend URL is in allowed origins

3. **JWT Token Issues**

   - Clear browser cookies and localStorage
   - Check JWT_SECRET configuration

4. **Port Conflicts**
   - Change PORT in config.env if 5000 is occupied
   - Update frontend axios baseURL accordingly

## 📝 Development

### Adding New Features

1. Create new routes in `express/routes/`
2. Add controllers in `express/controllers/`
3. Update frontend components as needed
4. Test thoroughly before deployment

### Code Style

- Use ESLint for code formatting
- Follow React best practices
- Implement proper error handling
- Add input validation

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

If you encounter any issues or have questions, please:

1. Check the troubleshooting section
2. Review the code documentation
3. Create an issue in the repository

---

**Happy Coding! 🎉**
