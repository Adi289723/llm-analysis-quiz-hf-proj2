---
title: LLM Quiz Solver 🚀 - Project 2 IITM
emoji: 🚀
colorFrom: blue
colorTo: purple
sdk: docker
sdk_version: 1.0.0
app_file: main.py
pinned: true
license: mit
---

🚀 LLM Quiz Solver – Hugging Face Docker Deployment

An automated quiz-solving API that:
	•	Scrapes HTML (static + dynamic),
	•	Extracts question metadata using an LLM (via AIPipe),
	•	Executes preprocessing or scripts if required,
	•	Generates a solution plan using AI,
	•	Computes the answer and submits it back,
	•	Iteratively continues solving until no new URL is returned.

⚠️ Designed for the IITM TDS Project 2 – LLM Analysis Quiz  ￼
Evaluation occurs between Sat 29 Nov 2025, 3:00–4:00 PM IST, where your API must independently solve quiz questions under 3 minutes per request.  ￼

⸻

📦 Deploying on Hugging Face (Docker SDK)

1️⃣ Repository Structure

├── main.py
├── services/
│   ├── quiz_handler.py
│   ├── llm_client.py
│   ├── extractors.py
│   └── executor.py
├── utils/
│   ├── config.py
│   └── retry.py
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md

🌐 Environment Variables (.env)
STUDENT_EMAIL="your_id@ds.study.iitm.ac.in"
STUDENT_SECRET="your_password_here"
AIPIPE_TOKEN="your_aipipe_token_here"
LLM_MODEL="openai/gpt-4o-mini"
QUIZ_TIMEOUT_SECONDS=170
MAX_RETRIES=

⚠️ Never hardcode credentials. They are validated per request.  ￼

⸻

🔌 API Endpoint (FastAPI)

📍 POST /solve

{
  "email": "your email",
  "secret": "your secret",
  "url": "https://example.com/quiz-123"
}

🐳 Dockerfile (For Hugging Face Deployment

FROM python:3.10-slim

WORKDIR /app
COPY . /app

# Install system dependencies for Playwright
RUN apt-get update \
    && apt-get install -y wget curl libnss3 libatk1.0-0 libatk-bridge2.0-0 libcairo2 \
    libx11-6 libx11-xcb1 libxcomposite1 libxdamage1 libxrandr2 libgbm-dev libpango1.0-0 \
    libdrm-dev libglib2.0-0 libjpeg62-turbo libpng-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
RUN pip install -r requirements.txt
RUN playwright install

EXPOSE 7860
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]

🚀 Deploy to Hugging Face
	1.	Create a Hugging Face Space
	•	Type: Docker
	2.	Upload your entire repository.
	3.	Set .env variables under Space → Variables & Secrets.
	4.	Hit Restart Space.


⚙️ Logging & Debugging
	•	Logs are stored under:
/attempt_<id>/logs/quiz.log
	•	Downloads, scripts, and result files stored per attempt in structured folders.

⸻

📝 MIT License

Ensure your GitHub repo is public and includes MIT LICENSE during evaluation.
