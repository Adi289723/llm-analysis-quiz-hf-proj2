import asyncio
import httpx
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import base64
import re
import json
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
import pandas as pd
import io
from PyPDF2 import PdfReader
from urllib.parse import urljoin

from utils.config import settings
from utils.models import QuizAnswerPayload, QuizAnswerResponse
from utils.llm_handler import LLMHandler


class QuizSolver:
    """Handles quiz solving logic"""
    
    def __init__(self):
        self.llm = LLMHandler()
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.start_time = None
    
    async def solve_quiz_chain(
        self, 
        email: str, 
        secret: str, 
        initial_url: str,
        callback: Optional[Callable] = None
    ):
        """
        Solve a chain of quiz questions
        """
        
        def log(msg: str, level: str = "info"):
            print(msg)
            if callback:
                callback(msg, level)
        
        self.start_time = datetime.now()
        current_url = initial_url
        question_count = 0
        
        log(f"\n\n{'='*60}")
        log(f"🚀 Starting quiz chain at {self.start_time.strftime('%H:%M:%S')}")
        log(f"📍 Initial URL: {initial_url}")
        log(f"{'='*60}\n\n")
        
        while current_url:
            question_count += 1
            elapsed = (datetime.now() - self.start_time).total_seconds()
            
            log(f"\n--- Question {question_count} (Elapsed: {elapsed:.1f}s) ---")
            log(f"🔗 URL: {current_url}")
            
            if elapsed > settings.QUIZ_TIMEOUT_SECONDS:
                log(f"⚠️  Timeout reached ({settings.QUIZ_TIMEOUT_SECONDS}s)", "warning")
                break
            
            try:
                result = await self._solve_single_question(
                    email, secret, current_url, log
                )
                
                if result.correct:
                    log(f"✅ Correct answer!")
                    current_url = result.url
                    
                    if not current_url:
                        log("\n🎉 Quiz completed successfully!")
                        break
                else:
                    log(f"❌ Incorrect answer: {result.reason}", "warning")
                    
                    if result.url:
                        log(f"→ Moving to next question anyway")
                        current_url = result.url
                    else:
                        log("→ No more questions")
                        break
                        
            except Exception as e:
                log(f"❌ Error solving question: {e}", "error")
                import traceback
                traceback.print_exc()
                break
        
        total_time = (datetime.now() - self.start_time).total_seconds()
        log(f"\n{'='*60}")
        log(f"🏁 Quiz session ended")
        log(f"📊 Questions attempted: {question_count}")
        log(f"⏱️  Total time: {total_time:.1f}s")
        log(f"{'='*60}")
    
    async def _solve_single_question(
        self, 
        email: str, 
        secret: str, 
        quiz_url: str,
        log: Callable
    ) -> QuizAnswerResponse:
        """Solve a single quiz question"""
        
        log("\n\n\n📄 Fetching quiz page...")
        page_content = await self._fetch_quiz_page(quiz_url)
        
        log("\n\n\n🔍 Parsing question...")
        question_data = await self._parse_question(page_content, quiz_url)
        
        log(f"\n\n\n📝 Question Data: \n\n{json.dumps(question_data, indent=2)}\n\n")
        
        if question_data.get('file_urls'):
            log(f"  📥 Downloading {len(question_data['file_urls'])} file(s)...")
            log("\n\n\n")
            print(question_data['file_urls'])
            question_data['downloaded_files'] = await self.download_files(
                question_data['file_urls']
            )
        
        log("\n\n\n🤖 Analyzing with LLM (via AIPipe)...")
        solution = await self.llm.analyze_quiz(
            question_data,
            page_content,
            quiz_url
        )
        
        log(f"\n\n\n💡 Strategy:{json.dumps(solution, indent=2)}\n\n")
        
        log("\n\n\n⚙️ Computing answer...")
        answer = await self.llm.execute_solution(solution, question_data)
        
        log(f"\n\n\n📤 Submitting answer: {answer}")
        
        result = await self._submit_answer(
            email, 
            secret, 
            quiz_url, 
            question_data['submit_url'], 
            answer
        )
        
        return result
    
    async def _fetch_quiz_page(self, url: str) -> str:
        """
        Fetch and render quiz page using Playwright
        Enhanced for complex dynamic content
        """
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-setuid-sandbox']  # Better compatibility
            )
            
            try:
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = await context.new_page()
                
                # Enable JavaScript
                await context.set_extra_http_headers({
                    'Accept-Language': 'en-US,en;q=0.9'
                })
                
                # Navigate with extended timeout
                await page.goto(url, wait_until='networkidle', timeout=30000)
                
                # Wait for common dynamic content indicators
                try:
                    # Wait for specific elements that might indicate content is loaded
                    await page.wait_for_selector('body', timeout=5000)
                    
                    # Check if there's a result div (like in your example)
                    result_div = await page.query_selector('#result')
                    if result_div:
                        # Wait a bit more for it to populate
                        await page.wait_for_timeout(1000)
                    
                    # Check for common loading indicators and wait for them to disappear
                    loading_selectors = ['.loading', '.spinner', '#loading', '[data-loading]']
                    for selector in loading_selectors:
                        try:
                            await page.wait_for_selector(selector, state='hidden', timeout=2000)
                        except:
                            pass  # Not found or already hidden
                    
                except Exception as e:
                    print(f"Warning: Element wait timeout: {e}")
                
                # Additional wait for any delayed JavaScript
                await page.wait_for_timeout(3000)
                
                # Optional: Scroll to bottom to trigger lazy loading
                await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                await page.wait_for_timeout(1000)
                
                # Get fully rendered HTML
                content = await page.content()
                
                # Also get text content directly (sometimes more reliable)
                text_content = await page.evaluate('document.body.innerText')
                
                # Store both for debugging
                return content
                
            except Exception as e:
                print(f"Error fetching page: {e}")
                raise
            finally:
                await browser.close()

    async def _parse_question(self, html_content: str, base_url: str) -> Dict[str, Any]:
        """Parse quiz question from HTML"""
        
        soup = BeautifulSoup(html_content, 'html.parser')
        
        for script in soup(["script", "style"]):
            script.decompose()
        
        text = soup.get_text(separator='\n', strip=True)
        
        base64_pattern = r'atob\([\'"]([A-Za-z0-9+/=]+)[\'"]\)'
        base64_matches = re.findall(base64_pattern, html_content)
        
        decoded_texts = []
        for b64 in base64_matches:
            try:
                decoded = base64.b64decode(b64).decode('utf-8')
                decoded_texts.append(decoded)
            except:
                pass
        
        if decoded_texts:
            text = '\n'.join(decoded_texts) + '\n' + text
        
        file_urls = []
        # ✅ EXTRACT AUDIO FROM <audio> TAGS
        for audio_tag in soup.find_all('audio'):
            if audio_tag.get('src'):
                src = audio_tag['src']
                # Make complete URL
                if not src.startswith(('http://', 'https://')):
                    src = urljoin(base_url, src)
                file_urls.append(src)
                print(f"  🎵 Found audio: {src}")
            
            # Also check <source> tags inside <audio>
            for source_tag in audio_tag.find_all('source'):
                if source_tag.get('src'):
                    src = source_tag['src']
                    if not src.startswith(('http://', 'https://')):
                        src = urljoin(base_url, src)
                    if src not in file_urls:  # Avoid duplicates
                        file_urls.append(src)
                        print(f"  🎵 Found audio source: {src}")

        # ✅ EXTRACT FILES FROM <a> TAGS (href)
        for link in soup.find_all('a', href=True):
            href = link['href']
            # Make complete URL
            if not href.startswith(('http://', 'https://')):
                href = urljoin(base_url, href)
            
            # Check for file extensions
            audio_extensions = ['.opus', '.mp3', '.wav', '.m4a', '.ogg', '.flac']
            file_extensions = ['.pdf', '.csv', '.xlsx', '.json', '.txt', '.png', '.jpg', '.jpeg']
            all_extensions = audio_extensions + file_extensions
            
            if any(ext in href.lower() for ext in all_extensions):
                if href not in file_urls:  # Avoid duplicates
                    file_urls.append(href)

        # ✅ ALSO CHECK FOR VIDEO/SOURCE ELEMENTS
        for video_tag in soup.find_all('video'):
            if video_tag.get('src'):
                src = video_tag['src']
                if not src.startswith(('http://', 'https://')):
                    src = urljoin(base_url, src)
                if src not in file_urls:
                    file_urls.append(src)
                    print(f"  🎥 Found video: {src}")

        # Remove duplicates while preserving order
        unique_file_urls = []
        for url in file_urls:
            if url not in unique_file_urls:
                unique_file_urls.append(url)

        

        submit_url = None
        submit_pattern = r'(?:POST|post|Post|submit|Submit).*?(?:to|at)\s+(https?://[^\s\'"<>]+)'
        submit_match = re.search(submit_pattern, text, re.IGNORECASE)
        if submit_match:
            submit_url = submit_match.group(1)
            submit_url = "https://tds-llm-analysis.s-anand.net/submit"
        
        if not submit_url:
            html_url_pattern = r'https?://[^\s\'"<>]+'
            all_urls = re.findall(html_url_pattern, text)
            for url in all_urls:
                if 'submit' in url.lower() or '/answer' in url.lower():
                    submit_url = url
                    break
        
        tables = []
        for table in soup.find_all('table'):
            tables.append(str(table))
        
        return {
            'question_text': text,
            'submit_url': submit_url,
            'file_urls': unique_file_urls,
            'tables': tables,
            'html': html_content
        }
    
    async def download_files(self, urls: List[str]) -> Dict[str, Any]:
        """Download files from URLs with retry logic and status checks"""
        files = {}
        max_retries = 2
        
        for url in urls:
            success = False
            last_error = None
            
            for attempt in range(max_retries + 1):
                try:
                    print(f"📥 Downloading: {url} (Attempt {attempt + 1}/{max_retries + 1})")
                    
                    # Download with timeout
                    response = await self.http_client.get(url, timeout=30.0)
                    
                    # ✅ CHECK STATUS IMMEDIATELY
                    if response.status_code != 200:
                        print(f"   ⚠️  Status {response.status_code}, retrying...")
                        last_error = f"HTTP {response.status_code}"
                        await asyncio.sleep(1)  # Wait before retry
                        continue
                    
                    # ✅ Verify content received
                    content_type = response.headers.get('content-type', '')
                    content_length = len(response.content)
                    
                    if content_length == 0:
                        print(f"   ⚠️  Empty response, retrying...")
                        last_error = "Empty response"
                        await asyncio.sleep(1)
                        continue
                    
                    print(f"   ✓ Downloaded {content_length} bytes (Status: 200 OK)")
                    
                    # Handle audio files
                    if any(ext in url.lower() for ext in ['.opus', '.mp3', '.wav', '.m4a', '.ogg', '.flac']):
                        audio_data = response.content
                        audio_text = await self.transcribe_audio(audio_data, url)
                        files[url] = {
                            'type': 'audio',
                            'format': url.split('.')[-1],
                            'transcription': audio_text,
                            'base64': base64.b64encode(audio_data).decode()
                        }
                        print(f"   🎵 Audio transcribed: {audio_text[:50]}...")
                    
                    # Handle CSV files
                    elif 'csv' in content_type or url.lower().endswith('.csv'):
                        try:
                            df = pd.read_csv(io.BytesIO(response.content))
                            files[url] = {
                                'type': 'csv',
                                'dataframe': df,
                                'data': df.to_dict(orient='records'),
                                'columns': list(df.columns),
                                'shape': df.shape
                            }
                            print(f"   📊 CSV loaded: {df.shape[0]} rows, {df.shape[1]} columns")
                        except Exception as e:
                            print(f"   ❌ CSV parse error: {e}")
                            files[url] = {'type': 'csv', 'error': str(e)}
                    
                    # Handle PDF files
                    elif 'pdf' in content_type or url.lower().endswith('.pdf'):
                        try:
                            pdf_data = await self.parse_pdf(response.content)
                            files[url] = pdf_data
                            print(f"   📄 PDF parsed: {pdf_data.get('num_pages', '?')} pages")
                        except Exception as e:
                            print(f"   ❌ PDF parse error: {e}")
                            files[url] = {'type': 'pdf', 'error': str(e)}
                    
                    # Handle JSON files
                    elif 'json' in content_type or url.lower().endswith('.json'):
                        try:
                            json_data = response.json()
                            files[url] = {
                                'type': 'json',
                                'data': json_data
                            }
                            print(f"   📋 JSON loaded")
                        except Exception as e:
                            print(f"   ❌ JSON parse error: {e}")
                            files[url] = {'type': 'json', 'error': str(e)}
                    
                    # Handle other files
                    else:
                        files[url] = {
                            'type': 'binary',
                            'content': response.text,
                            'size': content_length
                        }
                        print(f"   📦 File stored: {content_length} bytes")
                    
                    success = True
                    break  # ✅ Break on success
                    
                except asyncio.TimeoutError:
                    print(f"   ⏱️  Timeout (Attempt {attempt + 1}), retrying...")
                    last_error = "Timeout"
                    if attempt < max_retries:
                        await asyncio.sleep(2)  # Wait longer before retry
                        
                except Exception as e:
                    print(f"   ❌ Error (Attempt {attempt + 1}): {str(e)}")
                    last_error = str(e)
                    if attempt < max_retries:
                        await asyncio.sleep(1)  # Wait before retry
            
            # ✅ If all retries failed, store error
            if not success:
                print(f"   ❌ FAILED after {max_retries + 1} attempts: {last_error}")
                files[url] = {
                    'type': 'error',
                    'error': last_error,
                    'attempts': max_retries + 1
                }
        
        print(f"\n✅ Download complete: {len(files)} files processed")
        return files


    async def transcribe_audio(self, audio_bytes: bytes, url: str) -> str:
        """Transcribe audio file using speech-to-text with proper ffmpeg handling"""
        try:
            import speech_recognition as sr
            from pydub import AudioSegment
            import io
            import subprocess
            
            print(f"🎵 Starting transcription for: {url}")
            
            # Detect audio format from URL
            audio_format = url.split('.')[-1].lower()
            print(f"   Audio format detected: {audio_format}")
            
            # Try direct ffmpeg conversion first (most reliable)
            try:
                # Convert any format to WAV using ffmpeg
                result = subprocess.run(
                    ['ffmpeg', '-i', 'pipe:', '-f', 'wav', 'pipe:'],
                    input=audio_bytes,
                    capture_output=True,
                    timeout=30
                )
                
                if result.returncode == 0:
                    wav_bytes = io.BytesIO(result.stdout)
                    print(f"   ✓ Converted {audio_format} to WAV via ffmpeg")
                else:
                    print(f"   ⚠️ ffmpeg conversion failed, trying pydub")
                    wav_bytes = None
            except FileNotFoundError:
                print(f"   ⚠️ ffmpeg not found, trying pydub")
                wav_bytes = None
            except Exception as e:
                print(f"   ⚠️ ffmpeg error: {e}, trying pydub")
                wav_bytes = None
            
            # Fallback: Use pydub if ffmpeg didn't work
            if wav_bytes is None:
                try:
                    audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
                    wav_bytes = io.BytesIO()
                    audio.export(wav_bytes, format="wav")
                    wav_bytes.seek(0)
                    print(f"   ✓ Converted {audio_format} to WAV via pydub")
                except Exception as e:
                    print(f"   ❌ pydub conversion failed: {e}")
                    print(f"   Returning fallback transcription from URL")
                    return f"Audio file: {url.split('/')[-1]} - manual review needed"
            
            # Now transcribe the WAV file
            recognizer = sr.Recognizer()
            try:
                with sr.AudioFile(wav_bytes) as source:
                    audio_data = recognizer.record(source)
                
                # Try Google Speech Recognition
                text = recognizer.recognize_google(audio_data)
                print(f"   ✓ Transcribed: '{text[:100]}...'")
                return text
                
            except sr.UnknownValueError:
                print(f"   ⚠️ Audio could not be understood")
                return "Audio transcription: Unable to understand speech"
                
            except sr.RequestError as e:
                print(f"   ⚠️ Google API error: {e}")
                return f"Transcription failed: {str(e)}"
            
        except ImportError as e:
            print(f"   ❌ Missing dependency: {e}")
            print(f"   Install: pip install SpeechRecognition pydub")
            return f"Transcription requires: {str(e)}"
            
        except Exception as e:
            print(f"   ❌ Transcription error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return f"Transcription error: {str(e)}"

    async def _parse_pdf(self, pdf_bytes: bytes) -> Dict[str, Any]:
        """Parse PDF file"""
        
        try:
            pdf_file = io.BytesIO(pdf_bytes)
            reader = PdfReader(pdf_file)
            
            pages = []
            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                pages.append({
                    'page_number': i + 1,
                    'text': text
                })
            
            return {
                'type': 'pdf',
                'num_pages': len(reader.pages),
                'pages': pages
            }
            
        except Exception as e:
            return {
                'type': 'pdf',
                'error': str(e)
            }
    
    async def _submit_answer(
        self,
        email: str,
        secret: str,
        quiz_url: str,
        submit_url: Optional[str],
        answer: Any
    ) -> QuizAnswerResponse:
        """Submit answer to quiz endpoint"""

        submit_url = "https://tds-llm-analysis.s-anand.net/submit"
        
        if not submit_url:
            if '/quiz-' in quiz_url or '/quiz/' in quiz_url:
                submit_url = re.sub(r'/quiz[-/]', '/submit-', quiz_url)
            else:
                from urllib.parse import urljoin, urlparse
                parsed = urlparse(quiz_url)
                submit_url = f"{parsed.scheme}://{parsed.netloc}/submit"
        
        payload = QuizAnswerPayload(
            email=email,
            secret=secret,
            url=quiz_url,
            answer=answer if isinstance(answer, (str, int, float, bool)) else json.dumps(answer)
        )
        
        try:
            response = await self.http_client.post(
                submit_url,
                json=payload.model_dump(),
                timeout=10.0
            )
            
            response.raise_for_status()
            result_data = response.json()
            
            return QuizAnswerResponse(**result_data)
            
        except httpx.HTTPStatusError as e:
            print(f"HTTP error: {e.response.status_code}")
            print(f"Response: {e.response.text}")
            raise
        except Exception as e:
            print(f"Submit error: {e}")
            raise
    
    async def close(self):
        """Cleanup resources"""
        await self.http_client.aclose()
        await self.llm.close()
