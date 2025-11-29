import httpx
from typing import Optional, Dict, Any
import base64
import json
from utils.config import settings
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

STUDENT_EMAIL: str = os.getenv("STUDENT_EMAIL", "")
STUDENT_SECRET: str = os.getenv("STUDENT_SECRET", "")

class URLResolvingRequests:
    """Requests wrapper that automatically resolves relative URLs to absolute"""
    
    def __init__(self, base_url: str):
        """Initialize with base URL for resolution"""
        self.base_url = base_url
        self._requests = requests  # Reference to real requests module
    
    def _resolve_url(self, url: str) -> str:
        """Convert relative URLs to absolute using base_url"""
        if not url:
            return url
        # Already absolute (has scheme)
        if url.startswith('http://') or url.startswith('https://'):
            return url
        # Relative path
        if url.startswith('/'):
            return self.base_url + url
        # Relative without slash
        return self.base_url + '/' + url
    
    def get(self, url, **kwargs):
        """GET request with automatic URL resolution"""
        resolved_url = self._resolve_url(url)
        return self._requests.get(resolved_url, **kwargs)
    
    def post(self, url, **kwargs):
        """POST request with automatic URL resolution"""
        resolved_url = self._resolve_url(url)
        return self._requests.post(resolved_url, **kwargs)
    
    def put(self, url, **kwargs):
        """PUT request with automatic URL resolution"""
        resolved_url = self._resolve_url(url)
        return self._requests.put(resolved_url, **kwargs)
    
    def delete(self, url, **kwargs):
        """DELETE request with automatic URL resolution"""
        resolved_url = self._resolve_url(url)
        return self._requests.delete(resolved_url, **kwargs)
    
    def patch(self, url, **kwargs):
        """PATCH request with automatic URL resolution"""
        resolved_url = self._resolve_url(url)
        return self._requests.patch(resolved_url, **kwargs)
    
    def __getattr__(self, name):
        """Pass through other attributes to real requests"""
        return getattr(self._requests, name)

class LLMHandler:
    """Handles interactions with LLM APIs via AIPipe"""
    
    def __init__(self):
        self.aipipe_token = settings.AIPIPE_TOKEN
        self.model = settings.LLM_MODEL
        self.http_client = httpx.AsyncClient(timeout=60.0)
    
    async def analyze_quiz(
        self, 
        question_data: Any, 
        page_content,
        quiz_url
    ) -> Dict[str, Any]:
        """Analyze quiz question and generate solution strategy.

        Before analysis, try to extract the submission URL for this quiz page
        (using the question_url and html_content entries in the context, if present)
        and include it in the context that is passed to the analysis LLM.
        """
        # Try to have the LLM infer the submission URL from the raw HTML
        if quiz_url and page_content:
            question_details = await self._extract_submission_url(
                question_url=quiz_url,
                html_content=page_content,
            )

        prompt = self._build_analysis_prompt(question_data, question_details, quiz_url)
        return await self._call_llm(prompt, question_details)
    
    async def _extract_submission_url(
        self,
        question_url: Optional[str],
        html_content: Optional[str],
    ) -> Optional[str]:
        """Use the LLM to infer the correct submission URL for this quiz page.

        The model is given the original question URL and the full HTML content of the page
        and must return a JSON object of the form:
            {"submission_url": "https://..."}

        If the URL cannot be reliably determined, it should return null.
        """
        if not question_url or not html_content:
            return None

        system_message = """You are an expert quiz-solving agent. Your job is to analyze a webpage and extract all information needed to programmatically solve the quiz.

You will be given:
1. **QUIZ URL**
2. **HTML CONTENT** (may contain dynamically rendered elements, base64 encoded content, or hidden instructions)

Your output must be a **strictly valid JSON object (no markdown, no explanation)** with the following keys:

{
  "question_description": "...",            // Clear description of what needs to be solved
  "submission_url": "...",                  // Absolute URL where the answer must be POSTed
  "additional_links": [],                   // List of downloadable file links (PDF, CSV, JSON, etc.)
  "additional_scripts": null or "code",     // Python script ONLY if necessary to extract hidden data
  "base64_decoded_texts": [],               // Any text extracted from decoding atob(...) patterns
  "detected_tables_html": [],               // List of full HTML for each <table> element
  "raw_visible_text": "..."                 // Full visible text extracted from the HTML (cleaned)
}

### Parsing Rules

- Remove all `<script>` and `<style>` before processing visible text.
- Look for base64-encoded text using patterns like `atob("...")` or `atob('...')`, decode if found.
- For file links:
  - Include links for files ending in `.pdf`, `.csv`, `.xlsx`, `.json`, `.txt`, `.png`, `.jpg`, `.jpeg`
  - Convert relative links to absolute using the quiz URL as base
- Detect submission URL:
  - Look for phrases like “POST to …”, “Submit at …”, or embedded JSON examples.
  - If missing, infer from context or use typical patterns like `<base_url>/submit`
- Extract HTML of all `<table>` elements
- Always extract fully the question text and any constraints or extra instructions

### IMPORTANT
- Only return valid JSON → no markdown, no commentary.
- If something is missing, return `null` or empty list instead of omitting the key.
- Prefer explicit extraction over inference, but use logical inference when needed (e.g., relative URLs).
- Your response must be machine-readable JSON ready for parsing.

Now extract using the above structure."""

        user_message = (
            f"QUESTION URL:\n{question_url}\n\n"
            f"HTML CONTENT:\n{html_content}"
        )

        print("\n\n\n")
        print("==" * 64)
        print("==" * 64)
        print(f"\n\n\n[DEBUG] Submission URL extraction LLM input:\n{user_message}\n\n\n")  
        print("==" * 64)
        print("==" * 64)
        print("\n\n\n")

        try:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_message},
                ],
                "temperature": 0,
                "max_tokens": 512,
            }

            response = await self.http_client.post(
                "https://aipipe.org/openrouter/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.aipipe_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            raw = data["choices"][0]["message"]["content"].strip()
            print("==" * 64)
            print(f"\n\n\n[DEBUG] Submission URL extraction LLM response:\n{raw}\n\n\n")
            print("==" * 64)

            return raw
        
        except Exception as e:
            print(f"Failed to extract submission URL: {e}")
            return None

    def _build_analysis_prompt(
        self, 
        question_data: Any, 
        question_details: Any,
        quiz_url: str = ""
    ) -> str:
        """Build comprehensive analysis prompt"""
        
        prompt = f"""You are an expert data analyst tasked with solving a quiz question. 

            If email is required, use STUDENT_EMAIL and STUDENT_SECRET for authentication. Use them directly as provided, do not modify. No need to hide or encode them.
            STUDENT_EMAIL: {STUDENT_EMAIL}
            STUDENT_SECRET: {STUDENT_SECRET}

            QUESTION TEXT:
            {question_data["question_text"]}

            QUESTION URL:
            {quiz_url}

            QUESTION DETAILS:
            {json.dumps(question_details, indent=2) if question_details else "N/A"}

            """
        
        if question_data:
            prompt += "\nADDITIONAL CONTEXT:\n"
            
            if question_data.get('downloaded_files'):
                files_info = []
                for url, file_data in question_data['downloaded_files'].items():
                    file_type = file_data.get('type', 'unknown')
                    files_info.append(f"  - {url} (type: {file_type})")
                    
                    if file_type == 'csv' and 'dataframe' in file_data:
                        df = file_data['dataframe']
                        files_info.append(f"    Columns: {list(df.columns)}")
                        files_info.append(f"    Rows: {len(df)}")
                        files_info.append(f"    Preview:\n{df.head(3).to_string()}")

                    elif file_type == 'audio':
                        files_info.append(f"- Audio: {url}")
                        if 'transcription' in file_data:
                            files_info.append(f"  Transcription: {file_data['transcription']}")

                    
                    elif file_type == 'pdf' and 'pages' in file_data:
                        pages = file_data['pages']
                        files_info.append(f"    Pages: {len(pages)}")
                        for page in pages[:2]:
                            files_info.append(f"    Page {page['page_number']}:\n{page['text'][:500]}")
                    
                    elif file_type == 'json' and 'data' in file_data:
                        files_info.append(f"    Data: {json.dumps(file_data['data'], indent=2)[:500]}")
                    
                    elif file_type == 'text' and 'content' in file_data:
                        files_info.append(f"    Content: {file_data['content'][:500]}")
                
                prompt += "- Downloaded files:\n" + "\n".join(files_info) + "\n"
            
            if question_data.get('tables'):
                tables_info = []
                for i, table_html in enumerate(question_data['tables'], 1):
                    tables_info.append(f"Table {i}:\n{table_html[:1000]}")
                prompt += "\n\nTABLES FOUND IN PAGE:\n" + "\n".join(tables_info)

        prompt += """
            INSTRUCTIONS:
            1. Analyze the question carefully
            2. Identify what data/files need to be processed
            3. Determine the analysis steps required
            4. Provide the approach as a JSON object

            Respond ONLY with a valid JSON object in this exact format:
            {
                "analysis": "Detailed analysis of what needs to be done",
                "data_needed": ["list", "of", "data", "sources"],
                "steps": ["Step 1", "Step 2", "..."],
                "answer_type": "number|string|boolean|object",
                "solution_code": "Python code as a string to print out the final answer, else null",
                "final_answer": "Direct answer if applicable, else null"
            }

            The "solution_code" field must contain valid Python code that, when executed, will compute the final answer and print out the 'final_answer'. The aim is to provide code that can be run in a secure environment to get the final answer.
            Do not populate the "solution_code" if you can give a direct answer instead.
            Note: The email and secret variables are available as STUDENT_EMAIL and STUDENT_SECRET. They are not needed to be handled in the "solution_code" or in the "final_answer". They have been handled separately.
            The email, secret, and submission URL are provided for context only; do not include them in the "solution_code".

            - For numerical answers, provide just the number (not formatted text)
            - Ensure the JSON is valid and properly escaped
            - The "solution_code" must not include any POST requests; submission will be handled separately.
            - The "solution_code" must be within a try except block to handle errors gracefully. In case of error, print a relevant error message.

            Example for data processing:
            {
                "analysis": "Sum values in CSV column",
                "data_needed": ["data.csv"],
                "steps": ["Load CSV", "Sum 'value' column"],
                "answer_type": "number",
                "solution_code": "import pandas as pd\\n ..."
            }

            Example for direct answer:
            {
                "analysis": "Simple calculation",
                "data_needed": [],
                "steps": ["Add numbers"],
                "answer_type": "number",
                "solution_code": "42"
            }

            Go through all the QUESTION DETAILS and the ADDITIONAL CONTEXT to understand what needs to be done. The downloaded files often contain very important information to help answer this question. It might contain videos, audios, pdfs that dictate the question 
            and csvs, tables, etc. that might contain required data.
            """
        
        print("\n\n\n")
        print("==" * 64)
        print("==" * 64)
        print(f"\n\n\n[DEBUG] Analysis LLM input:\n{[prompt]}\n\n\n")  
        print("==" * 64)
        print("==" * 64)
        print("\n\n\n")

        return prompt
    
    async def _call_llm(
        self, 
        prompt: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call LLM via AIPipe"""
        
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are an expert data analyst. Always respond with valid JSON only, no additional text."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": 0,
                "max_tokens": 4096
            }
            
            response = await self.http_client.post(
                "https://aipipe.org/openrouter/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.aipipe_token}",
                    "Content-Type": "application/json",
                },
                json=payload
            )
            
            response.raise_for_status()
            data = response.json()

            print("="*64)
            print("\n\n\ LLM Response:\n\n\n")            
            llm_response = data["choices"][0]["message"]["content"]
            print(llm_response)

            return self._process_llm_response(llm_response)
        
        except Exception as e:
            print(f"Error calling LLM: {e}")
            raise
    
    def _process_llm_response(self, llm_response: str) -> Dict[str, Any]:
        """Process LLM response into structured solution"""
        
        try:
            cleaned = llm_response.strip()
            
            if cleaned.startswith("```"):
                cleaned = cleaned.strip("`")
                if "\n" in cleaned:
                    cleaned = cleaned.split("\n", 1)[1]
            
            return self._parse_json_response(cleaned)
        except Exception as e:
            print(f"Error processing LLM response: {e}")
            return {
                "analysis": "Failed to parse LLM response",
                "data_needed": [],
                "steps": [],
                "answer_type": "string",
                "solution": llm_response
            }
    
    def _parse_json_response(self, text: str) -> Dict[str, Any]:
        """Extract JSON object from text response"""
        
        try:
            return json.loads(text)
        except:
            pass
        
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except:
                pass
        
        cleaned = text.replace("```json", "").replace("```", "").strip()
        
        cleaned = cleaned.replace("\n", " ").replace("\t", " ")
        cleaned = cleaned.replace("“", '"').replace("”", '"').replace("’", "'")
        
        cleaned = cleaned.replace("\\'", "'").replace("\\\"", '"')
        
        cleaned = "".join(ch for ch in cleaned if ch.isprintable())
        
        import re as _re
        cleaned = _re.sub(r'``````', '', cleaned)
        try:
            return json.loads(cleaned)
        except:
            pass
        
        return {
            "analysis": f"Failed to parse JSON. Raw response: {text[:200]}",
            "data_needed": [],
            "steps": ["Manual parsing required"],
            "answer_type": "string",
            "solution": text
        }
    
    async def execute_solution(
        self, 
        solution: Dict[str, Any], 
        context: Dict[str, Any]
    ) -> Any:
        """Execute the solution strategy to get the final answer"""
        
        answer_type = solution.get('answer_type', 'string')
        solution_code = solution.get('solution_code', '')
        
        if any(keyword in solution_code for keyword in ['import', 'def ', 'for ', 'while ', '=']):
            return await self._execute_python_solution(solution_code, context)
        
        answer = solution_code
        
        if answer_type == 'number':
            try:
                answer_str = str(answer).replace(',', '').strip()
                if '.' in answer_str:
                    return float(answer_str)
                return int(answer_str)
            except:
                return answer
        elif answer_type == 'boolean':
            if isinstance(answer, str):
                return answer.lower() in ('true', 'yes', '1')
            return bool(answer)
        elif answer_type == 'object':
            if isinstance(answer, str):
                try:
                    return json.loads(answer)
                except:
                    return answer
            return answer
        
        return answer
    
    async def _execute_python_solution(
        self, solution_code: str, context: Dict[str, Any]
    ) -> Any:
        """Execute Python solution in subprocess with URL resolution"""
        
        import subprocess
        import sys
        import tempfile
        import json as json_module
        from urllib.parse import urlparse
        from textwrap import dedent
        
        # Extract base URL from context
        quiz_url = context.get('quiz_url', '') if context else ''
        if quiz_url:
            parsed = urlparse(quiz_url)
            base_url = f"{parsed.scheme}://{parsed.netloc}"
        else:
            base_url = 'https://tds-llm-analysis.s-anand.net'
        
        print(f"\n\n\n[DEBUG] Executing solution with base_url: {base_url}")
        print(f"[DEBUG] Solution code:\n{solution_code}\n\n\n")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(solution_code)
            script_path = f.name

        print(f"[DEBUG] Written temp script to: {script_path}")
        
        try:
            # Execute subprocess
            completed = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if completed.returncode != 0:
                error_output = completed.stderr if completed.stderr else completed.stdout
                print(f"[ERROR] Subprocess failed: {error_output}")
                raise RuntimeError(f"Subprocess execution failed: {error_output}")
            
            print(f"\n\n\n[DEBUG] Subprocess output: {completed.stdout}")
            # Parse result
            final_answer = completed.stdout.strip()

            return final_answer
                
        finally:
            import os
            try:
                os.unlink(script_path)
            except:
                pass

    async def close(self):
        """Close HTTP client and cleanup resources"""
        if self.http_client:
            await self.http_client.aclose()
