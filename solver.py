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
    Keeps: text content, important attributes, structure
    Target: 40-60% token reduction
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Remove script and style tags
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
async def scrape_quiz_page(page, url: str) -> Tuple[str, Optional[str], str]:
    """
    Navigates to the URL, scrapes the question/data, and attempts to find the submission URL.
    Returns: (scraped_data: str, submission_url: Optional[str], raw_html: str)
    """
    await page.goto(url, wait_until="networkidle")
    
    # Wait additional time for JavaScript execution (especially for base64 decoding, DOM manipulation)
    await page.wait_for_timeout(2000)  # 2 seconds for JS to execute
    
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

    return scraped_data, submission_url, html_content

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

            # 1. Scrape the current page (Receives submission_url and raw HTML here)
            scraped_data, submission_url, raw_html = await scrape_quiz_page(page, current_url)
            
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
                            raw_html=raw_html  # Pass raw HTML for media detection
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