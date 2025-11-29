from pydantic import BaseModel, Field, validator
from typing import Any, Optional


class QuizRequest(BaseModel):
    """Incoming quiz request payload"""
    email: str
    secret: str
    url: str
    
    @validator('email')
    def validate_email(cls, v):
        if '@' not in v:
            raise ValueError('Invalid email format')
        return v.lower().strip()
    
    @validator('url')
    def validate_url(cls, v):
        if not v.startswith(('http://', 'https://')):
            raise ValueError('URL must start with http:// or https://')
        return v.strip()


class QuizResponse(BaseModel):
    """Response to quiz request"""
    status: str = "received"
    message: str = "Quiz processing started"
    task_id: Optional[str] = None
    timestamp: Optional[str] = None


class QuizAnswerPayload(BaseModel):
    """Payload for submitting quiz answers"""
    email: str
    secret: str
    url: str
    answer: Any


class QuizAnswerResponse(BaseModel):
    """Response from quiz submission"""
    correct: bool
    url: Optional[str] = None
    reason: Optional[str] = None


class LogEntry(BaseModel):
    """Log entry model"""
    timestamp: str
    message: str
    level: str = "info"
