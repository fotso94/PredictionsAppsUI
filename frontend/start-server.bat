@echo off
echo 🚀 Starting Soccer Predictions Frontend Server...
echo.
cd dist
echo 📁 Serving from: %CD%
echo 🌐 Server will be available at: http://localhost:3000
echo.
echo ⏳ Starting server...
python -m http.server 3000
pause
