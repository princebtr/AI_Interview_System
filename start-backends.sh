#!/bin/bash

echo "Starting Interview System Backends..."
echo

echo "Starting Express Backend (Port 5000)..."
cd express && npm run dev &
EXPRESS_PID=$!

echo "Starting Flask AI Backend (Port 5001)..."
cd ../server && python app.py &
FLASK_PID=$!

echo
echo "Both backends are starting..."
echo "Express Backend: http://localhost:5000"
echo "Flask AI Backend: http://localhost:5001"
echo
echo "Press Ctrl+C to stop both backends"

# Function to handle cleanup
cleanup() {
    echo "Stopping backends..."
    kill $EXPRESS_PID 2>/dev/null
    kill $FLASK_PID 2>/dev/null
    exit
}

# Trap Ctrl+C
trap cleanup INT

# Wait for both processes
wait
