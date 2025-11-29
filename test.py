from playwright.async_api import async_playwright
import asyncio
import json
from typing import Dict, Any
import re


async def _fetch_demo_scrape_page(url: str, email: str) -> Dict[str, Any]:
    """
    Fetch and render demo-scrape page using Playwright, and try to extract the secret code.

    Returns a dict with:
      - html: full rendered HTML
      - text: body innerText
      - secret_code: best-guess extracted code (or None)
      - url, email, status
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox'],
        )

        try:
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent=(
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                ),
            )
            page = await context.new_page()

            await context.set_extra_http_headers({
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Referer': 'https://tds-llm-analysis.s-anand.net/',
            })

            print(f"[*] Navigating to: {url}")
            await page.goto(url, wait_until='networkidle', timeout=30000)
            print("[+] Page loaded successfully")

            try:
                await page.wait_for_selector('body', timeout=5000)
                print("[+] Body element found")

                # Look for likely content containers
                result_selectors = [
                    '#question', '#result', '#answer',
                    '[data-content]', '.content', 'main', 'article',
                ]
                for selector in result_selectors:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            print(f"[+] Found potential content container: {selector}")
                            break
                    except Exception:
                        pass

                # Let loading indicators disappear if present
                loading_selectors = [
                    '.loading', '.spinner', '#loading',
                    '[data-loading="true"]', '.loader',
                ]
                for selector in loading_selectors:
                    try:
                        await page.wait_for_selector(selector, state='hidden', timeout=2000)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[!] Warning: element wait timeout: {e}")

            # Extra time for any delayed JS
            await page.wait_for_timeout(2000)

            # Scroll to trigger lazy loading if any
            await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            await page.wait_for_timeout(1000)

            # Get rendered content
            html_content = await page.content()
            text_content = await page.evaluate('document.body.innerText')
            print(f"[+] HTML length: {len(html_content)}, text length: {len(text_content)}")

            secret_code = _extract_secret_code(html_content, text_content)

            return {
                "html": html_content,
                "text": text_content,
                "secret_code": secret_code,
                "url": url,
                "email": email,
                "status": "success",
            }

        except Exception as e:
            print(f"[!] Error fetching page: {e}")
            return {
                "html": None,
                "text": None,
                "secret_code": None,
                "url": url,
                "email": email,
                "status": f"error: {e}",
            }
        finally:
            await browser.close()
            print("[+] Browser closed")


def _extract_secret_code(html_content: str, text_content: str) -> str | None:
    """
    Try multiple patterns over HTML and text to extract a secret-looking code.
    """
    if not html_content and not text_content:
        return None

    # Look in HTML first
    patterns = [
        r'<code[^>]*>([^<]+)</code>',             # <code>XXX</code>
        r'<pre[^>]*>([^<]+)</pre>',               # <pre>XXX</pre>
        r'<h1[^>]*>([^<]+)</h1>',                 # <h1>XXX</h1>
        r'<span[^>]*id=["\']?code["\']?[^>]*>([^<]+)</span>',
        r'<div[^>]*id=["\']?secret["\']?[^>]*>([^<]+)</div>',
        r'SECRET[:\s]+([A-Za-z0-9_-]+)',          # SECRET: XXXX
        r'CODE[:\s]+([A-Za-z0-9_-]+)',            # CODE: XXXX
        r'"secret"\s*:\s*"([^"]+)"',              # "secret": "XXXX"
        r'"code"\s*:\s*"([^"]+)"',                # "code": "XXXX"
        r'answer["\']?\s*:\s*["\']?([A-Za-z0-9_-]+)["\']?',  # answer: XXXX
    ]

    for pattern in patterns:
        m = re.search(pattern, html_content, flags=re.IGNORECASE | re.DOTALL)
        if m:
            candidate = m.group(1).strip()
            if candidate and len(candidate) > 2:
                print(f"[+] Secret code extracted using pattern: {pattern}")
                return candidate

    # Fallback: scan text for code-like lines
    for line in text_content.split("\n"):
        line = line.strip()
        if (
            line
            and re.match(r"^[A-Za-z0-9_-]{6,}$", line)
            and not _is_common_word(line)
        ):
            print(f"[+] Potential secret code from text line: {line}")
            return line

    print("[!] Could not extract secret code from content")
    return None


def _is_common_word(text: str) -> bool:
    common = {
        "the", "and", "or", "to", "from", "with", "for",
        "scrape", "page", "email", "submit", "post", "get",
    }
    return text.lower() in common


async def solve_demo_scrape_challenge(
    email: str,
    base_url: str = "https://tds-llm-analysis.s-anand.net",
) -> Dict[str, Any]:
    """
    High-level helper:
      1) Fetch /demo-scrape-data?email=...
      2) Extract secret code
      3) Build ready-to-submit payload
    """
    scrape_url = f"{base_url}/demo-scrape-data?email={email}"

    print("\n[*] Step 1: fetching scrape page...")
    result = await _fetch_demo_scrape_page(scrape_url, email)

    if result["status"] != "success":
        print(f"[!] Failed to fetch page: {result['status']}")
        return result

    print(f"[*] Step 2: secret code = {result['secret_code']}")

    submission_payload = {
        "email": email,
        "secret": "your secret",  # replace with your actual secret if your infra needs it
        "url": scrape_url,
        "answer": result["secret_code"],
    }

    print("\n[+] Ready to submit payload:")
    print(json.dumps(submission_payload, indent=2))

    return {
        "payload": submission_payload,
        "submit_url": f"{base_url}/submit",
        "scrape_result": result,
    }


if __name__ == "__main__":
    # Quick manual run
    EMAIL = "21f3002781@ds.study.iitm.ac.in"

    result = asyncio.run(solve_demo_scrape_challenge(EMAIL))
    print("\n[*] To submit, POST to:", result["submit_url"])
    print("[*] Payload:")
    print(json.dumps(result["payload"], indent=2))