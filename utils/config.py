from pydantic_settings import BaseSettings
from typing import Optional
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    """Application configuration settings"""
    
    # Student credentials
    STUDENT_EMAIL: str = os.getenv("STUDENT_EMAIL", "")
    STUDENT_SECRET: str = os.getenv("STUDENT_SECRET", "")
    API_ENDPOINT_URL: str = os.getenv("API_ENDPOINT_URL", "")
    
    # AIPipe Configuration
    AIPIPE_TOKEN: str = os.getenv("AIPIPE_TOKEN", "")
    
    # Quiz settings
    QUIZ_TIMEOUT_SECONDS: int = 170
    MAX_RETRIES: int = 3
    
    # LLM Model
    LLM_MODEL: str = "openai/gpt-4o-mini"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"

# Initialize settings
settings = Settings()

# Auto-detect Hugging Face Space URL if not set
if not settings.API_ENDPOINT_URL and os.getenv("SPACE_ID"):
    space_id = os.getenv("SPACE_ID")
    settings.API_ENDPOINT_URL = f"https://{space_id.replace('/', '-')}.hf.space"

# Also try SPACE_HOST environment variable
if not settings.API_ENDPOINT_URL and os.getenv("SPACE_HOST"):
    settings.API_ENDPOINT_URL = os.getenv("SPACE_HOST")

import logging
import sys
from logging.handlers import RotatingFileHandler

def setup_logging():
    """Setup single console + optional file logging"""
    
    # Clear existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)
    
    # Console handler (NO duplicate)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    
    logging.root.addHandler(console_handler)
    logging.root.setLevel(logging.INFO)
    
    return logging.root

