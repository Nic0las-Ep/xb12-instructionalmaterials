@echo off
REM Setup script for Course Materials Chatbot (Windows)
REM Foothill-De Anza Community College District

echo ==================================================
echo Course Materials Chatbot - Setup Script
echo Foothill-De Anza Community College District
echo ==================================================
echo.

REM Check Python version
echo Checking Python version...
python --version

if %errorlevel% neq 0 (
    echo Error: Python is not installed
    echo Please install Python 3.8 or higher from python.org
    pause
    exit /b 1
)

echo Python is installed
echo.

REM Navigate to backend directory
cd backend

REM Create virtual environment
echo Creating virtual environment...
python -m venv venv

if %errorlevel% neq 0 (
    echo Error: Failed to create virtual environment
    pause
    exit /b 1
)

echo Virtual environment created
echo.

REM Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat

REM Install dependencies
echo Installing Python dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo Error: Failed to install dependencies
    pause
    exit /b 1
)

echo Dependencies installed
echo.

REM Create .env file if it doesn't exist
if not exist .env (
    echo Creating .env configuration file...
    copy .env.example .env
    echo Created .env file
    echo WARNING: Please edit backend\.env and add your AWS and SerpAPI credentials
) else (
    echo .env file already exists
)

echo.
echo ==================================================
echo Setup Complete!
echo ==================================================
echo.
echo Next steps:
echo.
echo 1. Configure your credentials:
echo    Edit backend\.env with your AWS and SerpAPI keys
echo.
echo 2. Start the backend server:
echo    cd backend
echo    venv\Scripts\activate
echo    python app.py
echo.
echo 3. Open the demo in your browser:
echo    Open frontend\demo.html in your browser
echo.
echo 4. Test the chatbot:
echo    Click the blue button in bottom-right corner
echo    Type 'Biology 10' or 'BIOL 10'
echo.
echo For more information, see README.md
echo ==================================================
pause
