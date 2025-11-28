import asyncio
import platform 
import time
import re # <-- NEW IMPORT for regular expressions
from typing import List, Tuple, Optional
from playwright.async_api import async_playwright
from models import QuizRequest, QuizAnswerModel
from llm_service import get_structured_answer
from logger import quiz_logger
import requests 
import json
from bs4 import BeautifulSoup
import sys

# --- WINDOWS FIX: Force ProactorEventLoop for Playwright on Windows ---
if platform.system() == "Windows":
    # Python 3.13+ changed the default loop on Windows
    # We need ProactorEventLoop for subprocess support (required by Playwright)
    if sys.version_info >= (3, 8):
        try:
            # Try to set ProactorEventLoop policy
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            quiz_logger.info("Set Windows ProactorEventLoop policy for Playwright")
        except Exception as e:
            quiz_logger.warning(f"Could not set event loop policy: {e}")

# --- Configuration (Retained) ---
MAX_STAGE_TIME_SECONDS = 120  # Maximum time per stage (reduced from 180 for efficiency)
MAX_ATTEMPTS = 3 


def format_answer_with_padding(answer: str, page_content: str) -> str:
    """
    Post-process answer to apply correct padding for PREFIX-NUMBER formats.
    Detects patterns like MATRIX-094, DATE-020, REGEX-008 from examples in page content
    and applies the same digit padding to the LLM's answer.
    
    Applies padding when:
    1. Examples show LEADING ZEROS (e.g., 094, 020, 008)
    2. Placeholders indicate digit count (e.g., MATRIX-???, MATRIX-XXX)
    
    Args:
        answer: Raw answer from LLM (e.g., "MATRIX-94")
        page_content: HTML/text content of the page with examples
    
    Returns:
        Formatted answer with correct padding (e.g., "MATRIX-094")
    """
    # Pattern: PREFIX-NUMBER (e.g., MATRIX-94, DATE-20, REGEX-8)
    match = re.match(r'^([A-Z-]+)-(\d+)$', answer)
    if not match:
        return answer  # No PREFIX-NUMBER pattern, return as-is
    
    prefix, number = match.groups()
    
    # Strategy 1: Look for examples with same prefix showing leading zeros
    example_pattern = rf'{prefix}-(\d+)'
    examples = re.findall(example_pattern, page_content)
    
    for example_num in examples:
        if example_num.startswith('0') and len(example_num) > 1:
            # Found an example with leading zero - apply same padding
            target_length = len(example_num)
            padded_number = number.zfill(target_length)
            formatted_answer = f"{prefix}-{padded_number}"
            
            if formatted_answer != answer:
                quiz_logger.info(f"📝 Format correction: {answer} → {formatted_answer} (padding to {target_length} digits based on example {prefix}-{example_num})")
            
            return formatted_answer
    
    # Strategy 2: Look for placeholder patterns like MATRIX-???, DATE-XXX, PARSE-????
    # Try multiple pattern variations (case-insensitive)
    placeholder_patterns = [
        rf'{prefix}-([\?X]+)',  # MATRIX-???
        rf'{prefix.lower()}-([\?x]+)',  # matrix-???
        rf'\({prefix}-([\?X]+)\)',  # (MATRIX-???)
        rf'e\.g\.,?\s*{prefix}-([\?X]+)',  # e.g., MATRIX-???
    ]
    
    for pattern in placeholder_patterns:
        matches = re.findall(pattern, page_content, re.IGNORECASE)
        for placeholder in matches:
            # Placeholder length indicates required digit count
            target_length = len(placeholder)
            if target_length >= len(number):  # Only pad if placeholder is longer
                padded_number = number.zfill(target_length)
                formatted_answer = f"{prefix}-{padded_number}"
                
                if formatted_answer != answer:
                    quiz_logger.info(f"📝 Format correction: {answer} → {formatted_answer} (padding to {target_length} digits based on placeholder pattern)")
                
                return formatted_answer
    
    # Strategy 3: If answer format example exists (e.g., "PARSE-{count}"), infer from context
    # Look for format hints in the prompt like "e.g., PARSE-137" or "format: PARSE-XXX"
    format_hint_pattern = rf'format[:\s]+{prefix}-([X\?]+)|e\.g\.,?\s*{prefix}-([X\?]+)'
    format_hints = re.findall(format_hint_pattern, page_content, re.IGNORECASE)
    
    for hint_tuple in format_hints:
        for hint in hint_tuple:
            if hint:  # Found a format hint
                target_length = len(hint)
                if target_length >= len(number):
                    padded_number = number.zfill(target_length)
                    formatted_answer = f"{prefix}-{padded_number}"
                    
                    if formatted_answer != answer:
                        quiz_logger.info(f"📝 Format correction: {answer} → {formatted_answer} (padding to {target_length} digits based on format hint)")
                    
                    return formatted_answer
    
    return answer  # No padding needed

# --- OPTIMIZATION: HTML Content Cleaning ---
def clean_html_for_llm(html_content: str) -> str:
    """
    Cleans HTML content to reduce tokens sent to LLM.
    Removes: scripts, styles, comments, excessive whitespace
    Keeps: text content, important attributes, structure, canvas elements
    Target: 40-60% token reduction
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Check if there's a canvas element (preserve it for rendering context)
        has_canvas = soup.find('canvas') is not None
        if has_canvas:
            quiz_logger.info("🎨 Canvas element detected - preserving rendering context")
        
        # Remove script and style tags (but keep canvas)
        for tag in soup(['script', 'style', 'noscript', 'iframe', 'svg']):
            tag.decompose()
        
        # Remove comments
        for comment in soup.find_all(string=lambda text: isinstance(text, type(soup.find_all(string=True)[0])) and text.strip().startswith('<!--')):
            comment.extract()
        
        # Get cleaned text
        cleaned = soup.get_text(separator='\n', strip=True)
        
        # Compress multiple newlines and spaces
        cleaned = re.sub(r'\n\s*\n+', '\n\n', cleaned)
        cleaned = re.sub(r' +', ' ', cleaned)
        
        original_len = len(html_content)
        cleaned_len = len(cleaned)
        reduction = ((original_len - cleaned_len) / original_len * 100) if original_len > 0 else 0
        
        quiz_logger.info(f"🧹 HTML cleaned: {original_len} → {cleaned_len} chars ({reduction:.1f}% reduction)")
        
        return cleaned
    except Exception as e:
        quiz_logger.warning(f"⚠️ HTML cleaning failed: {e}, using original content")
        return html_content 

# --- Helper: Scrape Additional Data URLs ---
async def scrape_additional_url(page, base_url: str, relative_or_absolute_url: str) -> str:
    """
    Scrapes an additional URL mentioned in the quiz instructions.
    Handles both relative and absolute URLs.
    """
    from urllib.parse import urljoin
    
    # Convert relative URL to absolute if needed
    if relative_or_absolute_url.startswith('http'):
        target_url = relative_or_absolute_url
    else:
        target_url = urljoin(base_url, relative_or_absolute_url)
    
    quiz_logger.info(f"🔗 Scraping additional data from: {target_url}")
    
    try:
        await page.goto(target_url, wait_until="networkidle", timeout=30000)
        content = await page.inner_text("body")
        quiz_logger.info(f"✅ Successfully scraped additional data ({len(content)} chars)")
        return content
    except Exception as e:
        quiz_logger.error(f"❌ Failed to scrape {target_url}: {e}")
        return f"Error scraping {target_url}: {str(e)}"


# --- Helper: Scrape the Current Quiz Page (MODIFIED) ---
async def scrape_quiz_page(page, url: str) -> Tuple[str, Optional[str], str, bool, Optional[str]]:
    """
    Navigates to the URL, scrapes the question/data, and attempts to find the submission URL.
    Returns: (scraped_data: str, submission_url: Optional[str], raw_html: str, has_canvas: bool, canvas_image_path: Optional[str])
    """
    await page.goto(url, wait_until="networkidle")
    
    # Wait additional time for JavaScript execution (especially for base64 decoding, DOM manipulation)
    await page.wait_for_timeout(2000)  # 2 seconds for JS to execute
    
    # Initialize canvas_image_path (will remain None if no canvas)
    canvas_image_path = None
    
    # Check if page has canvas element that needs rendering
    has_canvas = await page.evaluate("""() => {
        return document.querySelector('canvas') !== null;
    }""")
    
    canvas_info = ""
    if has_canvas:
        quiz_logger.info("🎨 Detected canvas element - extracting rendered content...")
        # Wait for canvas to render and scripts to execute (increased from 2s to 4s)
        await page.wait_for_timeout(4000)
        
        # Try to extract canvas-related information using multiple strategies
        try:
            canvas_data = await page.evaluate("""() => {
                const canvas = document.querySelector('canvas');
                if (!canvas) return null;
                
                // Strategy 1: Look for JavaScript that draws on canvas (in script tags)
                const scripts = Array.from(document.querySelectorAll('script'))
                    .map(s => s.textContent)
                    .join('\\n');
                
                // Strategy 2: Get ALL text content from page (including hidden elements)
                const allText = document.body.textContent;
                
                // Strategy 3: Try to capture canvas as image and get data URL
                let canvasDataUrl = '';
                try {
                    canvasDataUrl = canvas.toDataURL('image/png');
                } catch (e) {
                    // Canvas might be tainted, skip
                }
                
                // Strategy 4: Look for data attributes or nearby elements
                const canvasRect = canvas.getBoundingClientRect();
                const nearbyElements = Array.from(document.querySelectorAll('*'))
                    .filter(el => {
                        const rect = el.getBoundingClientRect();
                        return Math.abs(rect.top - canvasRect.top) < 200 || 
                               Math.abs(rect.left - canvasRect.left) < 200;
                    })
                    .map(el => el.outerHTML)
                    .join('\\n');
                
                return {
                    dimensions: `${canvas.width}x${canvas.height}`,
                    allPageText: allText,
                    scriptContent: scripts.substring(0, 5000), // Limit script size
                    nearbyHTML: nearbyElements.substring(0, 2000),
                    hasDataUrl: canvasDataUrl.length > 0,
                    canvasDataUrl: canvasDataUrl  // Return the actual base64 image
                };
            }""")
            
            if canvas_data:
                quiz_logger.info(f"📝 Canvas detected ({canvas_data['dimensions']})")
                
                # Save canvas image if available
                if canvas_data.get('hasDataUrl') and canvas_data.get('canvasDataUrl'):
                    try:
                        import base64
                        import tempfile
                        # Extract base64 data (remove data:image/png;base64, prefix)
                        data_url = canvas_data['canvasDataUrl']
                        if 'base64,' in data_url:
                            base64_data = data_url.split('base64,')[1]
                            image_bytes = base64.b64decode(base64_data)
                            # Save to temp file
                            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.png')
                            temp_file.write(image_bytes)
                            temp_file.close()
                            canvas_image_path = temp_file.name
                            quiz_logger.info(f"🖼️ Canvas image saved: {canvas_image_path} ({len(image_bytes)} bytes)")
                    except Exception as e:
                        quiz_logger.warning(f"⚠️ Could not save canvas image: {e}")
                
                # Build comprehensive canvas information
                canvas_info = f"\n\n=== CANVAS ELEMENT DETECTED ===\n"
                canvas_info += f"Canvas Size: {canvas_data['dimensions']}\n"
                if canvas_image_path:
                    canvas_info += f"\n🎨 CANVAS IMAGE AVAILABLE - Use vision model to read the alphametic puzzle directly from the image!\n"
                canvas_info += f"\nAll Page Text (including canvas-rendered content if in DOM):\n{canvas_data['allPageText'][:1000]}\n"
                
                # Include relevant script snippets that might contain the alphametic logic
                if 'fillText' in canvas_data['scriptContent'] or 'strokeText' in canvas_data['scriptContent']:
                    canvas_info += f"\nCanvas Drawing Script (contains text drawing logic):\n{canvas_data['scriptContent'][:2000]}\n"
                    quiz_logger.info("🎯 Found canvas text drawing code in scripts")
                
                # Log script snippet for debugging deterministic parsing
                script_preview = canvas_data['scriptContent'][:500].replace('\n', ' ')
                quiz_logger.info(f"📜 Script preview: {script_preview}...")
                quiz_logger.info(f"📝 Canvas info extracted: {len(canvas_info)} chars, has_canvas={has_canvas}")
        except Exception as e:
            quiz_logger.warning(f"⚠️ Could not extract canvas text: {e}")
    
    # Check if page has base64 content that needs decoding
    has_base64 = await page.evaluate("""() => {
        return document.body.innerHTML.includes('atob(') || 
               document.body.innerHTML.includes('base64') ||
               document.querySelector('[data-encoded]') !== null;
    }""")
    
    if has_base64:
        quiz_logger.info("🔐 Detected base64 content - waiting for decoding...")
        # Wait longer for base64 decoding and DOM updates
        await page.wait_for_timeout(3000)  # Additional 3 seconds

    # --- A. Scrape Question/Text ---
    question_text = await page.inner_text("body") # Scrape all body text
    html_content = await page.content() # Also get full HTML for media detection

    # --- OPTIMIZATION: Clean HTML content ---
    cleaned_html = clean_html_for_llm(html_content)

    # --- B. Scrape Links/Data Sources (Retained) ---
    data_links = await page.eval_on_selector_all("a", "elements => elements.map(e => e.href)")

    scraped_data = f"PAGE URL: {url}\n\nPAGE CONTENT:\n{question_text}\n\nCLEANED HTML:\n{cleaned_html}"

    # Add canvas information if detected
    if canvas_info:
        scraped_data += canvas_info

    if data_links:
        scraped_data += "\n\nDISCOVERED DATA LINKS:\n" + "\n".join(set(data_links))
    
    # --- B2. Detect if quiz asks to scrape additional URLs ---
    # Look for patterns like "Scrape /path", "Get data from URL", "Download from"
    additional_data_pattern = re.search(
        r'(?:Scrape|Get.*from|Download|Visit|Access)\s+([^\s]+\.(?:html|json|csv|pdf|txt|xml)|/[^\s<>"\')\]]+)',
        question_text,
        re.IGNORECASE
    )
    
    if additional_data_pattern:
        additional_url = additional_data_pattern.group(1)
        quiz_logger.info(f"📎 Detected request to scrape additional URL: {additional_url}")
        
        # Scrape the additional URL
        from urllib.parse import urlparse
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        additional_content = await scrape_additional_url(page, base_url, additional_url)
        scraped_data += f"\n\n=== ADDITIONAL SCRAPED DATA FROM {additional_url} ===\n{additional_content}"

    # --- C. Extract Submission URL (ENHANCED LOGIC) ---
    submission_url = None
    
    # Pattern 1: "POST this JSON to URL"
    match = re.search(r'POST this JSON to\s+(https?://[^\s<>"\')]+)', question_text, re.IGNORECASE)
    if match:
        submission_url = match.group(1)
    
    # Pattern 2: "Post your answer to URL"
    if not submission_url:
        match = re.search(r'Post your answer to\s+(https?://[^\s<>"\')]+)', question_text, re.IGNORECASE)
        if match:
            submission_url = match.group(1)
    
    # Pattern 3: "submit to URL" or "send to URL"
    if not submission_url:
        match = re.search(r'(?:submit|send)\s+(?:to|at)?\s+(https?://[^\s<>"\')]+)', question_text, re.IGNORECASE)
        if match:
            submission_url = match.group(1)
    
    # Pattern 4: Look for any URL containing 'submit' in the text
    if not submission_url:
        match = re.search(r'(https?://[^\s<>"\')]*submit[^\s<>"\')]*)', question_text, re.IGNORECASE)
        if match:
            submission_url = match.group(1)
    
    # Pattern 5: Extract from anchor tags in scraped links
    if not submission_url and data_links:
        for link in data_links:
            if 'submit' in link.lower() or 'answer' in link.lower():
                submission_url = link
                break
    
    # Pattern 6: Look in JSON-like structures for submission endpoint
    if not submission_url:
        match = re.search(r'["\'](?:submit_url|endpoint|url)["\']\s*:\s*["\']([^"\']]+)["\']', question_text, re.IGNORECASE)
        if match:
            submission_url = match.group(1)
    
    # Clean up the URL (remove trailing punctuation)
    if submission_url:
        submission_url = re.sub(r'[.,;!?\)]+$', '', submission_url)
        quiz_logger.info(f"✅ Extracted Submission URL: {submission_url}")
    else:
        quiz_logger.warning(f"⚠️ Could not extract submission URL from page content")

    return scraped_data, submission_url, html_content, has_canvas, canvas_image_path

# --- Core Multi-Step Solver Function (MODIFIED) ---

async def solve_quiz_sequence_core(payload: QuizRequest):
    current_url = str(payload.url)
    email = payload.email
    past_attempt_feedback: List[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        while current_url:
            # Each stage gets its own time budget
            stage_deadline = time.time() + MAX_STAGE_TIME_SECONDS
            time_left = MAX_STAGE_TIME_SECONDS
            quiz_logger.info(f"--- STARTING STAGE: {current_url} | Stage Budget: {time_left}s ---")
            quiz_logger.info(f"⏱️  Allocation: ~{MAX_STAGE_TIME_SECONDS}s per stage (3 attempts × 40s each)")

            # 1. Scrape the current page (Receives submission_url, raw HTML, canvas flag, and canvas image path)
            scraped_data, submission_url, raw_html, has_canvas_element, canvas_image_path = await scrape_quiz_page(page, current_url)

            # Quick deterministic attempt: if this is a canvas stage and the page contains
            # a deterministic formula (e.g., emailNumber * A + B mod 1e8), compute the key
            # locally (SHA1(email) -> int) and try submitting that before invoking the LLM.
            # This improves reliability for crypto/alphametic tasks and is additive only.
            async def try_deterministic_key_submission():
                try:
                    if not has_canvas_element:
                        quiz_logger.info("ℹ️ Skipping deterministic attempt (no canvas detected)")
                        return False
                    
                    quiz_logger.info("🔢 Starting deterministic key computation for canvas stage...")

                    import hashlib
                    import re
                    # Try to extract constants A and B and modulus from scraped_data
                    # Look for patterns like: (emailNumber * 7919 + 12345) % 100000000
                    text = scraped_data
                    # Narrow search to the canvas script block if present
                    script_block = None
                    m_block = re.search(r'Canvas Drawing Script \(contains text drawing logic\):\\n(.*)', text, re.IGNORECASE | re.DOTALL)
                    if m_block:
                        script_block = m_block.group(1)
                    else:
                        # Fallback to full text
                        script_block = text

                    # Pattern 1: emailNumber * A + B (with optional mod)
                    m = re.search(r'email\w*\s*\*\s*(\d+)\s*\+\s*(\d+)(?:\s*\)\s*%\s*(\d+))?', script_block, re.IGNORECASE)
                    if not m:
                        m = re.search(r'\(\s*email\w*\s*\*\s*(\d+)\s*\+\s*(\d+)\s*\)\s*%\s*(\d+)', script_block, re.IGNORECASE)

                    if not m:
                        # Try looser search for the known constants (common case)
                        mA = re.search(r'(\d{3,6})\s*\*\s*email', script_block, re.IGNORECASE)
                        mB = re.search(r'\+\s*(\d{3,6})', script_block)
                        mod_m = re.search(r'%\s*(100000000|1e8|10\*\*8)', script_block, re.IGNORECASE)
                        if mA and mB:
                            A = int(mA.group(1))
                            B = int(mB.group(1))
                            mod = 100000000 if mod_m else 100000000
                        else:
                            return False
                    else:
                        # m groups: A, B, optional mod
                        A = int(m.group(1))
                        B = int(m.group(2))
                        mod = int(m.group(3)) if m.lastindex and m.lastindex >= 3 and m.group(3) else 100000000

                    quiz_logger.info(f"🔢 Deterministic formula constants found: A={A}, B={B}, mod={mod}")

                    # Compute SHA1(email) once and prepare digest
                    sha1_hex = hashlib.sha1(email.encode('utf-8')).hexdigest()
                    sha1_digest = hashlib.sha1(email.encode('utf-8')).digest()

                    # Determine submission endpoint robustly from script_block / nearby HTML
                    target_url = submission_url if submission_url else None
                    try:
                        from urllib.parse import urlparse, urljoin
                        parsed = urlparse(current_url)
                        base_url = f"{parsed.scheme}://{parsed.netloc}"

                        if not target_url:
                            # Look for absolute fetch/XHR URLs
                            murl = re.search(r"fetch\(\s*['\"](https?://[^'\"]+)['\"]", script_block, re.IGNORECASE)
                            if murl:
                                target_url = murl.group(1)

                        if not target_url:
                            # Look for relative fetch paths or form actions containing 'submit'
                            murl2 = re.search(r"fetch\(\s*['\"](\/[^'\"]*submit[^'\"]*)['\"]", script_block, re.IGNORECASE)
                            if murl2:
                                target_url = urljoin(base_url, murl2.group(1))

                        if not target_url:
                            # Look for XHR open("POST", "/submit...")
                            murl3 = re.search(r"open\(\s*['\"]POST['\"]\s*,\s*['\"]([^'\"]+)['\"]", script_block, re.IGNORECASE)
                            if murl3:
                                candidate = murl3.group(1)
                                target_url = candidate if candidate.startswith('http') else urljoin(base_url, candidate)

                        if not target_url:
                            # Look for submit_url variable or JSON property
                            mvar = re.search(r"submit_url['\"]?\s*[:=]\s*['\"]([^'\"]+)['\"]", script_block, re.IGNORECASE)
                            if mvar:
                                candidate = mvar.group(1)
                                target_url = candidate if candidate.startswith('http') else urljoin(base_url, candidate)

                        if not target_url:
                            # Look for form action attributes in nearby HTML
                            ma = re.search(r"action=[\"']([^\"']+)[\"']", script_block, re.IGNORECASE)
                            if ma:
                                candidate = ma.group(1)
                                target_url = candidate if candidate.startswith('http') else urljoin(base_url, candidate)

                        if not target_url:
                            # Final fallback to base /submit
                            target_url = urljoin(base_url, '/submit')

                        quiz_logger.info(f"🔗 Deterministic submission target: {target_url}")
                    except Exception as e:
                        quiz_logger.warning(f"⚠️ Could not determine submission endpoint from scripts: {e}")
                        target_url = submission_url or current_url

                    # Try multiple SHA1->int conversion variants to match server-side conversion
                    conversion_methods = [
                        ("full_hex", lambda: int(sha1_hex, 16)),
                        ("digest_big", lambda: int.from_bytes(sha1_digest, 'big')),
                        ("first8_hex", lambda: int(sha1_hex[:8], 16)),
                        ("last8_hex", lambda: int(sha1_hex[-8:], 16)),
                        ("first8_bytes_big", lambda: int.from_bytes(sha1_digest[:8], 'big')),
                        ("last8_bytes_big", lambda: int.from_bytes(sha1_digest[-8:], 'big')),
                        ("first4_hex", lambda: int(sha1_hex[:4], 16)),
                        ("last4_hex", lambda: int(sha1_hex[-4:], 16)),
                        ("first8_little", lambda: int.from_bytes(sha1_digest[:8], 'little')),
                        ("last8_little", lambda: int.from_bytes(sha1_digest[-8:], 'little')),
                    ]

                    submission_attempts = []
                    for name, fn in conversion_methods:
                        try:
                            email_num_variant = fn()
                        except Exception as e:
                            quiz_logger.debug(f"Conversion {name} failed: {e}")
                            continue

                        key_num = (email_num_variant * A + B) % mod
                        key_str = str(key_num).zfill(8)
                        quiz_logger.info(f"🧪 Deterministic attempt [{name}]: {key_str} (sha1:{sha1_hex[:8]}...)")

                        submission_data = {
                            "email": email,
                            "secret": payload.secret,
                            "url": current_url,
                            "answer": key_str,
                            "reasoning": f"Deterministic attempt using conversion: {name}"
                        }

                        try:
                            resp = requests.post(target_url, json=submission_data, timeout=10)
                        except Exception as e:
                            quiz_logger.warning(f"Failed to POST deterministic attempt {name}: {e}")
                            submission_attempts.append((name, None, str(e)))
                            await asyncio.sleep(0.5)
                            continue

                        resp_text = resp.text[:1000]
                        resp_json = {}
                        try:
                            if 'application/json' in resp.headers.get('Content-Type', '').lower() or resp.text.strip().startswith(('{', '[')):
                                resp_json = resp.json()
                        except Exception:
                            resp_json = {}

                        submission_attempts.append((name, resp.status_code, resp_text))

                        if resp.status_code == 200 and resp_json.get('correct') is True:
                            quiz_logger.critical(f"🎉 DETERMINISTIC SUCCESS [{name}]: {email} | Answer: {key_str}")
                            next_url = resp_json.get('url')
                            if next_url:
                                return next_url
                            return True

                        # If not correct, capture follow-up URL or reason for LLM feedback
                        feedback = resp_json.get('reason', f"Status {resp.status_code}")
                        follow_url = resp_json.get('url')
                        if follow_url:
                            try:
                                quiz_logger.info(f"Following server-provided URL for more context: {follow_url}")
                                follow_resp = requests.get(follow_url, timeout=5)
                                follow_text = follow_resp.text[:2000]
                                quiz_logger.info(f"Fetched follow-up content: {follow_text[:200]}...")
                                past_attempt_feedback.append(f"Deterministic attempt {name} failed. Reason: {feedback}. Server follow-up: {follow_url} -> {follow_text[:200]}")
                            except Exception as e:
                                quiz_logger.warning(f"Could not fetch follow-up URL: {e}")
                                past_attempt_feedback.append(f"Deterministic attempt {name} failed. Reason: {feedback}. Submitted: {key_str}")
                        else:
                            past_attempt_feedback.append(f"Deterministic attempt {name} failed. Reason: {feedback}. Submitted: {key_str}")

                        # Small delay between attempts to avoid flooding
                        await asyncio.sleep(0.5)

                    # Log summary of deterministic attempts
                    quiz_logger.info(f"Deterministic attempts summary: {submission_attempts}")
                    return False

                except Exception as e:
                    quiz_logger.warning(f"⚠️ Deterministic attempt raised exception: {e}")
                    return False

            # Try deterministic submission first (non-blocking); if it returns a string, treat as next_url
            det_result = await try_deterministic_key_submission()
            if isinstance(det_result, str) and det_result:
                current_url = det_result
                continue
            # If deterministic succeeded boolean True (final stage), exit
            if det_result is True:
                await browser.close()
                return
            
            # --- CRITICAL CHECK: Ensure we have a submission URL ---
            if not submission_url:
                # Fallback: try to construct from base URL
                from urllib.parse import urlparse, urljoin
                parsed = urlparse(current_url)
                base_url = f"{parsed.scheme}://{parsed.netloc}"
                submission_url = urljoin(base_url, "/submit")
                quiz_logger.warning(f"Using fallback submission URL: {submission_url}")

            # 2. LLM Orchestration Loop (with Retries)
            for attempt in range(MAX_ATTEMPTS):
                try:
                    error_context = "\n".join(past_attempt_feedback) if past_attempt_feedback else None
                    
                    # Adaptive timeout based on stage complexity
                    time_left = stage_deadline - time.time()
                    
                    # Detect if this is a multimodal stage (has audio/video)
                    is_multimodal = 'audio' in scraped_data.lower() or 'video' in scraped_data.lower() or '.opus' in scraped_data or '.mp4' in scraped_data
                    
                    # Allocate timeout intelligently
                    if is_multimodal:
                        # Multimodal needs more time but cap at 30s
                        base_timeout = 30
                    else:
                        # Text-only can be faster
                        base_timeout = 20
                    
                    # Reduce timeout if running low on time
                    attempt_timeout = min(base_timeout, time_left / (MAX_ATTEMPTS - attempt + 1))
                    
                    # Emergency mode: if < 30s total, use minimal timeout
                    if time_left < 30:
                        attempt_timeout = min(15, time_left / 2)
                        quiz_logger.warning(f"⏱️  EMERGENCY MODE: Only {time_left:.0f}s left, using {attempt_timeout:.0f}s timeout")
                    
                    # Add retry delay for 503 errors (exponential backoff)
                    if attempt > 0 and "503" in str(past_attempt_feedback[-1]) if past_attempt_feedback else False:
                        retry_delay = min(2 ** attempt, 5)  # 2s, 4s, max 5s
                        quiz_logger.info(f"⏳ Waiting {retry_delay}s before retry due to API overload...")
                        await asyncio.sleep(retry_delay)

                    # Get the structured answer from the LLM with timeout
                    llm_output: QuizAnswerModel = await asyncio.wait_for(
                        get_structured_answer(
                            question_text=scraped_data[:1000], 
                            scraped_data=scraped_data,
                            email=email,
                            secret=payload.secret,
                            page_url=current_url,
                            error_feedback=error_context,
                            use_fast_model=(not is_multimodal and time_left < 60),  # Use faster model if text-only and low time
                            raw_html=raw_html,  # Pass raw HTML for media detection
                            has_canvas=has_canvas_element,  # Pass canvas detection flag
                            canvas_image_path=canvas_image_path  # Pass canvas image for vision model
                        ),
                        timeout=attempt_timeout
                    )

                    # Apply smart formatting with padding detection (use raw HTML to find placeholders)
                    formatted_answer = format_answer_with_padding(llm_output.final_answer, raw_html)

                    quiz_logger.info(f"LLM Answer (Attempt {attempt+1}): {formatted_answer[:50]}...")

                    # 3. Submission (Uses the scraped submission URL)
                    submission_data = {
                        "email": email,
                        "secret": payload.secret,
                        "url": current_url, # Pass the URL we are answering for
                        "answer": formatted_answer,  # Use formatted answer with padding
                        "reasoning": llm_output.reasoning_summary
                    }

                    # Use standard requests library for the final POST submission
                    response = requests.post(submission_url, json=submission_data)
                    
                    # --- CRITICAL FIX: Defensive JSON Parsing ---
                    response_data = {}
                    try:
                        # Check for JSON content type or try parsing
                        if 'application/json' in response.headers.get('Content-Type', '').lower() or response.text.strip().startswith(('{', '[')):
                            response_data = response.json()
                        else:
                            # Log the raw text if it wasn't JSON (likely a success message or failure text)
                            quiz_logger.warning(f"Submission response was not JSON. Text: {response.text[:100]}...")
                            # Force a failure path if it's not JSON, as we rely on the JSON keys below
                            raise ValueError(f"Quiz Master API returned non-JSON response (Status: {response.status_code}).")

                    except json.JSONDecodeError as json_e:
                        # Catch the exact JSON failure and wrap it
                        quiz_logger.error(f"JSON Decode Failed. Raw response text: {response.text[:200]}...")
                        raise ValueError(f"Could not parse JSON response from Quiz Master: {json_e}") from json_e


                    # 4. Check Submission Response (Logic Retained, now using parsed JSON)
                    if response.status_code == 200 and response_data.get("correct") is True:
                        # SUCCESS
                        current_url = response_data.get("url") # Could be the next stage URL
                        if not current_url:
                            quiz_logger.critical(f"🎉 FINAL QUIZ SUCCESS: {email} | Answer: {llm_output.final_answer}")
                            await browser.close()
                            return 
                        break # Break the retry loop to continue to the next stage

                    elif response_data.get("correct") is False:
                        # FAILURE: Prepare for a retry
                        feedback = response_data.get("reason", "No specific reason provided.")
                        past_attempt_feedback.append(f"Attempt {attempt+1} failed. Reason: {feedback}. Submitted: {llm_output.final_answer}")
                        quiz_logger.warning(f"Submission failed. Retrying (Attempt {attempt+2}). Reason: {feedback}")

                    else:
                        # UNEXPECTED API RESPONSE FORMAT
                        raise Exception(f"Quiz Master API returned unexpected structure or status {response.status_code}.")

                except asyncio.TimeoutError:
                    quiz_logger.warning(f"⏱️  LLM attempt {attempt+1} timed out after {attempt_timeout:.1f}s")
                    past_attempt_feedback.append(f"Attempt {attempt+1} timed out - be faster and more direct")
                    # Continue to next attempt
                    
                except Exception as e:
                    quiz_logger.error(f"CRITICAL STAGE ERROR (Attempt {attempt+1}): {e}", exc_info=True)
                    past_attempt_feedback.append(f"Attempt {attempt+1} failed due to internal error: {e}")
                    await asyncio.sleep(1) 
            else:
                # Runs if retry loop finishes without 'break' - all attempts failed
                time_left = stage_deadline - time.time()
                quiz_logger.warning(f"⚠️  Stage {current_url} failed after {MAX_ATTEMPTS} attempts. Skipping to next stage...")
                
                # ============================================================
                # ⚠️ TESTING ONLY - CUSTOM QUIZ SERVER WORKAROUND
                # The demo quiz does NOT support skipping failed stages.
                # This manual stage increment is ONLY for testing with custom_quiz_server.py
                # REMOVE THIS BEFORE USING WITH REAL DEMO QUIZ!
                # ============================================================
                # Try to increment stage number manually
                try:
                    import re
                    stage_match = re.search(r'stage(\d+)', current_url)
                    if stage_match:
                        stage_num = int(stage_match.group(1))
                        
                        # CHECK: Don't skip beyond stage 32 (last stage of custom quiz)
                        if stage_num >= 32:
                            quiz_logger.warning(f"🧪 [TESTING] Reached final stage (stage{stage_num}). Stopping quiz.")
                            await browser.close()
                            return
                        
                        next_stage = stage_num + 1
                        # Replace stage number in URL
                        next_url = re.sub(r'stage\d+', f'stage{next_stage}', current_url)
                        current_url = next_url
                        quiz_logger.warning(f"🧪 [TESTING] Manually skipping to: {current_url}")
                        continue  # Skip to next iteration of while loop
                except Exception as e:
                    quiz_logger.error(f"Failed to increment stage: {e}")
                # ============================================================
                # END TESTING-ONLY CODE
                # ============================================================
                
                # If we can't find next URL or out of time, exit
                if time_left < 10:
                    quiz_logger.error(f"FAILURE: Insufficient time remaining ({time_left:.0f}s). Exiting.")
                    await browser.close()
                    return
                else:
                    # No next URL found, but still have time - try submitting empty/skip
                    quiz_logger.warning(f"No next URL found. Cannot continue. Exiting.")
                    await browser.close()
                    return

        # Stage completed or failed, continue to next stage
        await browser.close()

# --- Integration with Phase 1 (Retained) ---
async def solve_quiz_sequence(payload: QuizRequest):
    """Wrapper for main.py's background task."""
    try:
        await solve_quiz_sequence_core(payload)
    except Exception as e:
        quiz_logger.critical(f"UNHANDLED FATAL ERROR in Quiz Sequence for {payload.email}: {e}", exc_info=True)