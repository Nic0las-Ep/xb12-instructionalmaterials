#!/bin/bash

# Setup script for Course Materials Chatbot
# Foothill-De Anza Community College District

echo "=================================================="
echo "Course Materials Chatbot - Setup Script"
echo "Foothill-De Anza Community College District"
echo "=================================================="
echo ""

# Check Python version
echo "Checking Python version..."
python3 --version

if [ $? -ne 0 ]; then
    echo "❌ Error: Python 3 is not installed"
    echo "Please install Python 3.8 or higher"
    exit 1
fi

echo "✓ Python 3 is installed"
echo ""

# Navigate to backend directory
cd backend

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to create virtual environment"
    exit 1
fi

echo "✓ Virtual environment created"
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to install dependencies"
    exit 1
fi

echo "✓ Dependencies installed"
echo ""

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
    echo "Creating .env configuration file..."
    cp .env.example .env
    echo "✓ Created .env file"
    echo "⚠️  Please edit backend/.env and add your AWS and SerpAPI credentials"
else
    echo "✓ .env file already exists"
fi

echo ""
echo "=================================================="
echo "Setup Complete! 🎉"
echo "=================================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Configure your credentials:"
echo "   Edit backend/.env with your AWS and SerpAPI keys"
echo ""
echo "2. Start the backend server:"
echo "   cd backend"
echo "   source venv/bin/activate"
echo "   python app.py"
echo ""
echo "3. Open the demo in your browser:"
echo "   Open frontend/demo.html"
echo "   Or run: python3 -m http.server 8000"
echo "   Then visit: http://localhost:8000/demo.html"
echo ""
echo "4. Test the chatbot:"
echo "   Click the blue button in bottom-right corner"
echo "   Type 'Biology 10' or 'BIOL 10'"
echo ""
echo "For more information, see README.md"
echo "=================================================="
