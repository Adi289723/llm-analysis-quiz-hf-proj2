#!/bin/bash
# Quick setup script for macOS/Linux

echo "🚀 Setting up LLM Quiz Solver..."

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright
playwright install chromium

echo "✅ Setup complete!"
echo "📝 Don't forget to:"
echo "   1. Create .env file with your credentials"
echo "   2. Get AIPipe token from https://aipipe.org/login"
echo ""
echo "🎯 Run with: python main.py"
