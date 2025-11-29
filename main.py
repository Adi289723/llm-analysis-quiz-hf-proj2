"""
LLM Quiz Solver - FastAPI Service
Hugging Face Spaces Docker Deployment
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
import asyncio
import logging
from datetime import datetime
import os
from typing import List, Dict
from collections import deque

from utils.config import settings
from utils.models import QuizRequest, QuizResponse, LogEntry
from utils.quiz_solver import QuizSolver

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
# from utils.config import setup_logging
# logging = setup_logging()

# FIX DOUBLE LOGGING - ADD THIS BLOCK:
logging.getLogger().handlers.clear()  # Remove duplicates
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(logging.INFO)


# Create FastAPI app
app = FastAPI(
    title="LLM Quiz Solver API",
    description="Automated quiz solver using LLMs via AIPipe - Deployed on HF Spaces",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store logs in memory (thread-safe deque)
quiz_logs: deque = deque(maxlen=200)
active_tasks: Dict[str, dict] = {}


def add_log(message: str, level: str = "info"):
    """Add log message with timestamp"""
    timestamp = datetime.now().isoformat()
    log_entry = {
        "timestamp": timestamp,
        "message": message,
        "level": level
    }
    quiz_logs.append(log_entry)
    
    # Also log to console
    if level == "error":
        logger.error(message)
    elif level == "warning":
        logger.warning(message)
    else:
        logger.info(message)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint with HTML interface"""
    
    space_url = settings.API_ENDPOINT_URL or os.getenv("SPACE_HOST", "https://your-space.hf.space")
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>LLM Quiz Solver</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 2rem;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 2rem;
                text-align: center;
            }}
            .header h1 {{
                font-size: 2.5rem;
                margin-bottom: 0.5rem;
            }}
            .header p {{
                opacity: 0.9;
                font-size: 1.1rem;
            }}
            .content {{
                padding: 2rem;
            }}
            .status-card {{
                background: #f8f9fa;
                border-left: 4px solid #667eea;
                padding: 1.5rem;
                margin-bottom: 1.5rem;
                border-radius: 4px;
            }}
            .status-card h3 {{
                color: #667eea;
                margin-bottom: 1rem;
            }}
            .status-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 1rem;
            }}
            .status-item {{
                display: flex;
                justify-content: space-between;
                padding: 0.75rem;
                background: white;
                border-radius: 4px;
                border: 1px solid #e0e0e0;
            }}
            .status-label {{
                font-weight: 600;
                color: #333;
            }}
            .status-value {{
                color: #666;
                font-family: monospace;
            }}
            .status-ok {{
                color: #28a745;
            }}
            .status-error {{
                color: #dc3545;
            }}
            .endpoint-box {{
                background: #2d3748;
                color: #e2e8f0;
                padding: 1.5rem;
                border-radius: 8px;
                margin: 1.5rem 0;
                font-family: 'Courier New', monospace;
            }}
            .endpoint-box pre {{
                margin: 0.5rem 0;
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
            .button {{
                display: inline-block;
                padding: 0.75rem 1.5rem;
                background: #667eea;
                color: white;
                text-decoration: none;
                border-radius: 6px;
                font-weight: 600;
                transition: background 0.3s;
                margin: 0.5rem 0.5rem 0.5rem 0;
            }}
            .button:hover {{
                background: #5568d3;
            }}
            .logs-section {{
                margin-top: 2rem;
            }}
            .logs-container {{
                background: #1e1e1e;
                color: #d4d4d4;
                padding: 1.5rem;
                border-radius: 8px;
                max-height: 500px;
                overflow-y: auto;
                font-family: 'Courier New', monospace;
                font-size: 0.9rem;
            }}
            .log-entry {{
                padding: 0.5rem 0;
                border-bottom: 1px solid #333;
            }}
            .log-timestamp {{
                color: #888;
                margin-right: 1rem;
            }}
            .log-info {{ color: #4fc3f7; }}
            .log-warning {{ color: #ffb74d; }}
            .log-error {{ color: #e57373; }}
            .refresh-btn {{
                background: #28a745;
                border: none;
                color: white;
                padding: 0.5rem 1rem;
                border-radius: 4px;
                cursor: pointer;
                margin-bottom: 1rem;
            }}
            .refresh-btn:hover {{
                background: #218838;
            }}
            .footer {{
                text-align: center;
                padding: 2rem;
                color: #666;
                border-top: 1px solid #e0e0e0;
            }}
        </style>
        <script>
            async function refreshLogs() {{
                try {{
                    const response = await fetch('/logs');
                    const logs = await response.json();
                    const logsContainer = document.getElementById('logs-container');
                    
                    logsContainer.innerHTML = logs.map(log => `
                        <div class="log-entry">
                            <span class="log-timestamp">${{new Date(log.timestamp).toLocaleTimeString()}}</span>
                            <span class="log-${{log.level}}">${{log.message}}</span>
                        </div>
                    `).join('') || '<div class="log-entry">No logs yet. Waiting for requests...</div>';
                    
                    logsContainer.scrollTop = logsContainer.scrollHeight;
                }} catch (error) {{
                    console.error('Failed to refresh logs:', error);
                }}
            }}
            
            // Auto-refresh logs every 3 seconds
            setInterval(refreshLogs, 3000);
            
            // Initial load
            window.onload = refreshLogs;
        </script>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🤖 LLM Quiz Solver</h1>
                <p>Automated Quiz Solver powered by AIPipe • Deployed on Hugging Face Spaces 🚀</p>
            </div>
            
            <div class="content">
                <div class="status-card">
                    <h3>📊 System Status</h3>
                    <div class="status-grid">
                        <div class="status-item">
                            <span class="status-label">Status</span>
                            <span class="status-value status-ok">🟢 Running</span>
                        </div>
                        <div class="status-item">
                            <span class="status-label">Email</span>
                            <span class="status-value">{'✅ ' + settings.STUDENT_EMAIL if settings.STUDENT_EMAIL else '❌ Not set'}</span>
                        </div>
                        <div class="status-item">
                            <span class="status-label">AIPipe Token</span>
                            <span class="status-value">{'✅ Configured' if settings.AIPIPE_TOKEN else '❌ Not set'}</span>
                        </div>
                        <div class="status-item">
                            <span class="status-label">LLM Model</span>
                            <span class="status-value">{settings.LLM_MODEL}</span>
                        </div>
                        <div class="status-item">
                            <span class="status-label">Deployment</span>
                            <span class="status-value">Docker 🐳</span>
                        </div>
                        <div class="status-item">
                            <span class="status-label">Timeout</span>
                            <span class="status-value">{settings.QUIZ_TIMEOUT_SECONDS}s</span>
                        </div>
                    </div>
                </div>
                
                <div class="status-card">
                    <h3>🔌 API Endpoint</h3>
                    <p>POST requests should be sent to:</p>
                    <div class="endpoint-box">
                        <strong>POST</strong> {space_url}/quiz
                    </div>
                    
                    <p><strong>Example Request:</strong></p>
                    <div class="endpoint-box">
<pre>curl -X POST {space_url}/quiz \\
  -H "Content-Type: application/json" \\
  -d '{{
    "email": "{settings.STUDENT_EMAIL or 'your-email@example.com'}",
    "secret": "your-secret",
    "url": "https://quiz-url"
  }}'</pre>
                    </div>
                    
                    <a href="/docs" class="button">📖 API Documentation</a>
                    <a href="/health" class="button">🏥 Health Check</a>
                    <a href="/logs" class="button">📋 JSON Logs</a>
                </div>
                
                <div class="logs-section">
                    <h3>📡 Live Activity Logs</h3>
                    <button class="refresh-btn" onclick="refreshLogs()">🔄 Refresh Now</button>
                    <div class="logs-container" id="logs-container">
                        <div class="log-entry">Loading logs...</div>
                    </div>
                </div>
            </div>
            
            <div class="footer">
                <p>🎓 IIT Madras TDS Project • Powered by <a href="https://aipipe.org" target="_blank">AIPipe</a></p>
                <p style="margin-top: 0.5rem; font-size: 0.9rem;">Version 1.0.0 • Docker Deployment</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "config": {
            "email": settings.STUDENT_EMAIL,
            "has_aipipe_token": bool(settings.AIPIPE_TOKEN),
            "llm_model": settings.LLM_MODEL,
            "timeout_seconds": settings.QUIZ_TIMEOUT_SECONDS,
        },
        "deployment": {
            "platform": "Hugging Face Spaces",
            "runtime": "Docker",
            "playwright_installed": True,
        },
        "aipipe_url": "https://aipipe.org",
        "active_tasks": len(active_tasks),
        "total_logs": len(quiz_logs)
    }


@app.get("/logs")
async def get_logs(limit: int = 100):
    """Get recent logs"""
    logs_list = list(quiz_logs)
    return logs_list[-limit:]


@app.delete("/logs")
async def clear_logs():
    """Clear all logs"""
    quiz_logs.clear()
    add_log("🗑️ Logs cleared via API")
    return {"message": "Logs cleared", "timestamp": datetime.now().isoformat()}


@app.get("/status")
async def status():
    """Get current status and active tasks"""
    return {
        "active_tasks": active_tasks,
        "total_logs": len(quiz_logs),
        "recent_logs": list(quiz_logs)[-10:],
        "timestamp": datetime.now().isoformat()
    }


@app.post("/quiz")
async def handle_quiz(
    request: QuizRequest,
    background_tasks: BackgroundTasks
):
    """
    Main quiz endpoint - receives quiz task and processes it
    
    Args:
        request: QuizRequest with email, secret, and quiz URL
    
    Returns:
        Immediate 200 response, processing continues in background
    """
    
    # Verify secret
    if request.secret != settings.STUDENT_SECRET:
        logger.warning(f"Invalid secret from {request.email}")
        add_log(f"❌ Invalid secret attempt from {request.email}", "warning")
        raise HTTPException(status_code=403, detail="Invalid secret")
    
    # Verify email
    if request.email.lower() != settings.STUDENT_EMAIL.lower():
        logger.warning(f"Email mismatch: {request.email} != {settings.STUDENT_EMAIL}")
        add_log(f"❌ Email mismatch: {request.email}", "warning")
        raise HTTPException(status_code=403, detail="Email mismatch")
    
    # Create task ID
    task_id = f"quiz_{datetime.now().timestamp()}"
    active_tasks[task_id] = {
        "url": request.url,
        "started_at": datetime.now().isoformat(),
        "status": "processing"
    }
    
    logger.info(f"Received quiz request for {request.url}")
    add_log(f"📨 Received quiz request: {request.url}")
    
    # Start quiz solving in background
    background_tasks.add_task(
        solve_quiz_background,
        request.email,
        request.secret,
        request.url,
        task_id
    )
    
    # Return immediate response
    return JSONResponse(
        status_code=200,
        content={
            "status": "received",
            "message": f"Quiz processing started for {request.url}",
            "task_id": task_id,
            "timestamp": datetime.now().isoformat()
        }
    )


async def solve_quiz_background(email: str, secret: str, url: str, task_id: str):
    """
    Background task to solve quiz chain
    
    Args:
        email: Student email
        secret: Student secret
        url: Quiz URL
        task_id: Unique task identifier
    """
    
    solver = QuizSolver()
    
    try:
        add_log(f"🚀 Starting quiz solver for {url}")
        
        # Update task status
        if task_id in active_tasks:
            active_tasks[task_id]["status"] = "solving"
        
        # Solve the quiz chain
        await solver.solve_quiz_chain(email, secret, url, callback=add_log)
        
        add_log(f"✅ Quiz chain completed for {url}")
        
        # Update task status
        if task_id in active_tasks:
            active_tasks[task_id]["status"] = "completed"
            active_tasks[task_id]["completed_at"] = datetime.now().isoformat()
        
    except Exception as e:
        logger.error(f"Quiz solving error: {e}")
        add_log(f"❌ Error solving quiz: {str(e)}", "error")
        
        # Update task status
        if task_id in active_tasks:
            active_tasks[task_id]["status"] = "failed"
            active_tasks[task_id]["error"] = str(e)
            active_tasks[task_id]["failed_at"] = datetime.now().isoformat()
        
        import traceback
        traceback.print_exc()
    finally:
        await solver.close()
        
        # Remove from active tasks after some time
        await asyncio.sleep(300)  # Keep for 5 minutes
        if task_id in active_tasks:
            del active_tasks[task_id]


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle validation errors"""
    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "timestamp": datetime.now().isoformat()
        }
    )

@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle invalid JSON or request validation errors"""
    return JSONResponse(
        status_code=400,
        content={
            "detail": "Invalid JSON or request body",
            "errors": exc.errors(),
            "timestamp": datetime.now().isoformat()
        }
    )


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    add_log("🚀 LLM Quiz Solver started")
    add_log(f"📧 Configured email: {settings.STUDENT_EMAIL}")
    add_log(f"🤖 LLM Model: {settings.LLM_MODEL}")
    add_log(f"⏱️  Timeout: {settings.QUIZ_TIMEOUT_SECONDS}s")
    add_log("✅ Ready to receive quiz requests")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    add_log("🛑 LLM Quiz Solver shutting down")


# For local testing
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("PORT", 8000))
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info"
    )
