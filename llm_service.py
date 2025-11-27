import os
import json
import re
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
import asyncio
# Import the standard, top-level Client.
# This client handles both synchronous and asynchronous operations via its accessors.
from google.genai import Client as genai_Client
from google.genai import types
from google.genai.errors import ServerError
from pydantic import BaseModel
from typing import Optional, List, Tuple
from logger import quiz_logger
from models import QuizAnswerModel, CalculationToolOutput
from dotenv import load_dotenv
from rate_limiter import get_rate_limiter

# Load environment to check for mock mode
load_dotenv()
USE_MOCK_LLM = os.getenv("USE_MOCK_LLM", "false").lower() == "true" 

# --- LLM Client Initialization ---
# LLM_CLIENT will hold the asynchronous client instance (client.aio)

if USE_MOCK_LLM:
    quiz_logger.warning("⚠️  MOCK LLM MODE ENABLED - No real API calls will be made")
    LLM_CLIENT = None  # Will use mock instead
else:
    try:
        # Initialize the standard Client (synchronous object). 
        # It automatically reads the GEMINI_API_KEY from the environment.
        sync_client = genai_Client()
        
        # CRITICAL FIX: Access the asynchronous interface via the .aio accessor
        LLM_CLIENT = sync_client.aio 
        quiz_logger.info("✅ Real Gemini LLM client initialized")

    except Exception as e:
        # This should now catch initialization failures cleanly
        quiz_logger.error(f"Failed to initialize Gemini Client: {e}")
        LLM_CLIENT = None

# --- Media File Handling ---

def detect_media_files(scraped_data: str, page_url: str) -> List[Tuple[str, str]]:
    """
    Detect audio, video, and image files in scraped content.
    Returns: List of (media_type, url) tuples
    """
    quiz_logger.info(f"🔍 Scanning for media files in {len(scraped_data)} chars of HTML...")
    media_files = []
    
    # Patterns for different media types
    audio_patterns = [
        r'<audio[^>]*src=["\']([^"\'>]+)["\']',
        r'<source[^>]*src=["\']([^"\'>]+\.(?:mp3|wav|ogg|opus|m4a|flac|aac))["\']',
        r'href=["\']([^"\'>]+\.(?:mp3|wav|ogg|opus|m4a|flac|aac))["\']'
    ]
    
    video_patterns = [
        r'<video[^>]*src=["\']([^"\'>]+)["\']',
        r'<source[^>]*src=["\']([^"\'>]+\.(?:mp4|webm|ogg))["\']',
        r'href=["\']([^"\'>]+\.(?:mp4|webm|ogg))["\']'
    ]
    
    image_patterns = [
        r'<img[^>]*src=["\']([^"\'>]+)["\']',
        r'href=["\']([^"\'>]+\.(?:jpg|jpeg|png|gif|webp))["\']'
    ]
    
    # CSV/data file patterns
    csv_patterns = [
        r'<a[^>]*href=["\']([^"\'>]+\.(?:csv|json|txt|xml))["\']',
        r'href=["\']([^"\'>]+\.(?:csv|json|txt|xml))["\']'
    ]
    
    # CSV/data file patterns
    csv_patterns = [
        r'<a[^>]*href=["\']([^"\'>]+\.(?:csv|json|txt|xml))["\']',
        r'href=["\']([^"\'>]+\.(?:csv|json|txt|xml))["\']'
    ]
    
    # Search for audio files
    for pattern in audio_patterns:
        matches = re.findall(pattern, scraped_data, re.IGNORECASE)
        quiz_logger.info(f"  Audio pattern found {len(matches)} matches")
        for match in matches:
            full_url = urljoin(page_url, match)
            media_files.append(('audio', full_url))
            quiz_logger.info(f"    ✓ Audio: {full_url}")
    
    # Search for video files
    for pattern in video_patterns:
        matches = re.findall(pattern, scraped_data, re.IGNORECASE)
        for match in matches:
            full_url = urljoin(page_url, match)
            media_files.append(('video', full_url))
    
    # Search for images
    for pattern in image_patterns:
        matches = re.findall(pattern, scraped_data, re.IGNORECASE)
        for match in matches:
            full_url = urljoin(page_url, match)
            media_files.append(('image', full_url))
    
    # Search for CSV/data files
    for pattern in csv_patterns:
        matches = re.findall(pattern, scraped_data, re.IGNORECASE)
        quiz_logger.info(f"  CSV pattern found {len(matches)} matches")
        for match in matches:
            full_url = urljoin(page_url, match)
            media_files.append(('data', full_url))
            quiz_logger.info(f"    ✓ Data file: {full_url}")
    
    # Remove duplicates
    media_files = list(dict.fromkeys(media_files))
    
    if media_files:
        quiz_logger.info(f"🎬 Detected {len(media_files)} media file(s): {[m[0] for m in media_files]}")
    
    return media_files


def download_media_file(url: str, media_type: str) -> Optional[str]:
    """
    Download media file to temporary location.
    Returns: Local file path or None if download fails
    """
    try:
        quiz_logger.info(f"⬇️  Downloading {media_type}: {url}")
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        # Get file extension
        parsed_url = urlparse(url)
        ext = Path(parsed_url.path).suffix or '.tmp'
        
        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp_file:
            tmp_file.write(response.content)
            local_path = tmp_file.name
        
        quiz_logger.info(f"✅ Downloaded to: {local_path} ({len(response.content)} bytes)")
        return local_path
        
    except Exception as e:
        quiz_logger.error(f"❌ Failed to download {url}: {e}")
        return None


# --- OPTIMIZATION: Adaptive Token Limits ---
def estimate_stage_complexity(scraped_data: str, question_text: str) -> str:
    """
    Estimates the complexity of a quiz stage to determine appropriate token limits.
    Returns: 'simple', 'medium', or 'complex'
    """
    data_length = len(scraped_data)
    
    # Keywords indicating complex processing
    complex_keywords = [
        'csv', 'json', 'calculate', 'analyze', 'aggregate', 'transform',
        'filter', 'group', 'merge', 'join', 'parse', 'extract multiple',
        'complex', 'nested', 'multi-step',
        'valid', 'invalid', 'validate', 'regex', 'pattern', 'match'
    ]
    
    # Check for complex indicators
    text_lower = (scraped_data + question_text).lower()
    complexity_score = sum(1 for keyword in complex_keywords if keyword in text_lower)
    
    # Special case: Multiple items/records need medium complexity minimum
    has_multiple_items = any(indicator in text_lower for indicator in [
        'record', 'item', 'entry', 'row', 'element', 'email'
    ])
    
    # Special case: Large validation tables need COMPLEX tier (more reasoning tokens)
    has_large_validation = (
        ('valid' in text_lower or 'invalid' in text_lower or 'validate' in text_lower) and
        data_length > 800
    )
    
    # Special case: Complex conditional logic with multiple entities
    has_complex_branching = (
        ('bonus' in text_lower or 'rules' in text_lower or 'conditional' in text_lower or 'if' in text_lower) and
        ('employee' in text_lower or 'calculation rules' in text_lower) and
        data_length > 700
    )
    
    # Special case: Audio/video with calculation = complex (requires transcription + processing)
    is_media_with_calc = (
        any(media in text_lower for media in ['audio', 'video', 'image']) and
        any(calc in text_lower for calc in ['sum', 'calculate', 'cutoff', 'filter'])
    )
    
    # Decision logic
    if is_media_with_calc:
        # Audio/video with calculation (e.g., transcribe cutoff → filter CSV → sum)
        # Needs extra tokens for transcription + data processing + reasoning
        return 'very_complex'
    elif has_large_validation:
        # Large validation tasks need detailed per-record reasoning
        return 'complex'
    elif has_complex_branching:
        # Complex conditional logic with multiple entities (e.g., bonus calculations per employee)
        return 'complex'
    elif data_length > 5000 or complexity_score >= 3:
        return 'complex'  # Needs detailed reasoning and large output
    elif data_length > 1500 or complexity_score >= 1 or has_multiple_items:
        return 'medium'   # Moderate processing (lowered threshold to catch more)
    else:
        return 'simple'   # Simple extraction/lookup
    

def get_adaptive_token_limit(scraped_data: str, question_text: str) -> int:
    """
    Returns appropriate max_output_tokens based on stage complexity.
    Target: 30-50% token savings on simple stages without compromising accuracy.
    """
    complexity = estimate_stage_complexity(scraped_data, question_text)
    
    token_limits = {
        'simple': 512,         # Basic extraction, single value answers
        'medium': 1536,        # Moderate calculations, small datasets (increased for regex/validation)
        'complex': 2048,       # Large CSV/JSON, multi-step reasoning
        'very_complex': 4096   # Large dataset + audio/video transcription + complex calculation
    }
    
    limit = token_limits[complexity]
    quiz_logger.info(f"🎯 Stage complexity: {complexity.upper()} → max_output_tokens={limit}")
    
    return limit


# --- Core LLM Interaction ---

async def get_structured_answer(
    question_text: str,
    scraped_data: str,
    email: str,
    secret: str,
    page_url: str,
    error_feedback: Optional[str] = None,
    use_fast_model: bool = False,
    raw_html: str = ""
) -> QuizAnswerModel:
    """
    Calls the LLM to process the question and scraped data, forcing 
    the output to conform to the QuizAnswerModel Pydantic schema.
    
    If USE_MOCK_LLM=true in .env, uses the mock implementation instead.
    """
    
    # Use mock if enabled
    if USE_MOCK_LLM or not LLM_CLIENT:
        from llm_service_mock import get_structured_answer_mock
        return await get_structured_answer_mock(question_text, scraped_data, error_feedback)
    
    # Otherwise use real LLM
    if not LLM_CLIENT:
        raise RuntimeError("LLM client not initialized. Check GEMINI_API_KEY.")

    # 1. Construct the System Prompt (The Agent's Instructions)
    system_prompt = (
        "You are an expert Data Science Quiz Solver AI with comprehensive analytical capabilities. "
        "Your task is to analyze quiz questions and scraped data to provide precise, actionable answers.\n\n"
        
        "TASK CATEGORIES YOU CAN HANDLE:\n"
        "1. WEB SCRAPING: Extract information from HTML/JavaScript-rendered pages\n"
        "2. API CALLS: Parse API responses and extract required data\n"
        "3. DATA CLEANSING: Clean text, parse PDFs, handle messy data\n"
        "4. DATA PROCESSING: Transform, transcribe, analyze using vision/NLP\n"
        "5. DATA ANALYSIS: Filter, sort, aggregate, statistical analysis, ML predictions\n"
        "6. VISUALIZATION: Describe charts/visualizations (note: cannot generate actual images)\n\n"
        
        "SPECIAL HANDLING:\n"
        "• BASE64 ENCODED CONTENT: If you see 'atob(...)' or base64 strings in HTML, the DECODED content is what matters\n"
        "  - The page has already executed JavaScript and decoded it\n"
        "  - Look for the DECODED text in the page content, NOT the base64 string\n"
        "  - Example: If you see 'BASE64-MTMy' in raw HTML but 'BASE64-11111' in decoded text, use 'BASE64-11111'\n"
        "• DOM MANIPULATION: JavaScript-rendered content is already executed - read the final rendered text\n"
        "• DYNAMIC CONTENT: Always trust the PAGE CONTENT section over HTML SOURCE\n\n"
        
        "MULTIMEDIA & FILE HANDLING:\n"
        "• Audio files: If audio is provided as input, transcribe it and extract any numbers or codes mentioned\n"
        "• Video files: Extract any text, speech, or visual information if provided\n"
        "• Images: Analyze for text (OCR), codes, numbers, or visual patterns if provided as input\n"
        "• Data files (CSV/JSON): Will be included in the prompt text - analyze them directly\n"
        "• IMPORTANT: Always look for contextual data like cutoff values, thresholds, parameters displayed on the page\n\n"
        
        "CRITICAL INSTRUCTIONS:\n"
        "• ALWAYS scan the ENTIRE page for: cutoff values, thresholds, parameters, constraints\n"
        "• Questions may be in: audio descriptions, video captions, or page text near the media\n"
        "• If page has audio/video: The actual question/task is usually described in text on the same page\n"
        "• For calculations: Look for numbers, cutoffs, filters, conditions in the page content\n"
        "• Extract ALL relevant data: numbers, arrays, cutoffs, thresholds before computing\n"
        "• If asked to POST specific JSON: Extract the EXACT answer value from the instructions\n"
        "• For 'what is your secret': Return the secret code from context\n"
        "• For aggregations with conditions: Apply filters (>=, <=, etc.) BEFORE computing sum/average\n"
        "• For COMPLEX CALCULATIONS: Show step-by-step breakdown in reasoning_summary to verify accuracy\n"
        "• DOUBLE-CHECK all arithmetic before submitting - verify sums, products, and formulas\n\n"
        
        "OUTPUT FORMAT:\n"
        "• 'final_answer': ONLY the answer value - NEVER the full JSON structure\n"
        "  ✓ CORRECT: 52314\n"
        "  ✗ WRONG: {\"email\": \"...\", \"secret\": \"...\", \"answer\": \"52314\"}\n"
        "  ✓ CORRECT: 35548978\n"
        "  ✗ WRONG: {\"answer\": 35548978}\n"
        "  ✓ CORRECT: anything you want\n"
        "  - If page asks for 'the secret' or 'your secret': Return EXACTLY the secret value\n"
        "  - If page asks to 'sum numbers': Return ONLY the numeric sum\n"
        "  - If page asks 'scrape this URL': Return the scraped value directly\n"
        "  - For answers with prefixes (e.g., 'MATRIX-XXX', 'BONUS-XXX'): Match expected format EXACTLY\n"
        "  - CRITICAL: If numeric answer needs padding (e.g., MATRIX-094), count digits in example and pad with zeros\n"
        "  - Example formats: MATRIX-094 (3 digits), DATE-020 (3 digits), REGEX-008 (3 digits) - always match digit count\n"
        "  - When you see examples like 'e.g., REGEX-008', the '008' shows you need 3 digits with leading zeros\n"
        "  - Look for format hints in examples or instructions on the page\n"
        "• 'reasoning_summary': Brief explanation showing key calculation steps\n\n"
        
        "ERROR HANDLING:\n"
        "If ERROR_FEEDBACK mentions 'Secret mismatch': You returned JSON instead of plain answer.\n"
        "If ERROR_FEEDBACK mentions 'Wrong sum': Recheck filters/conditions before calculation.\n"
        "Adjust your answer based on feedback - use simpler, more direct responses."
    )

    # 2. Construct the User Prompt (Concise)
    user_prompt = f"""PAGE: {question_text}

DATA:
{scraped_data}

CONTEXT:
Email: {email}
Secret: {secret}

TASK: Extract the answer from the page/data above.
- If "what is your secret": return {secret}
- If filtering/sum: apply condition (>=cutoff) FIRST, then calculate
- Return ONLY the final value, NO JSON wrapping
"""
    if error_feedback:
        user_prompt += f"\n\nPREVIOUS ERROR: {error_feedback}\nFix: Return plain value only.\n"

    quiz_logger.info(f"LLM Prompt constructed. Length: {len(user_prompt)} chars.")

    # Detect and download media files (use raw HTML to find tags before cleaning)
    media_html = raw_html if raw_html else scraped_data
    media_files = detect_media_files(media_html, page_url)
    downloaded_files = []
    
    try:
        # Download and prepare media files for multimodal input
        # First pass: download all files and add data files to prompt
        audio_video_image_files = []
        
        for media_type, media_url in media_files:
            local_path = download_media_file(media_url, media_type)
            if local_path:
                downloaded_files.append(local_path)
                
                # Read file content
                with open(local_path, 'rb') as f:
                    file_data = f.read()
                
                if media_type == 'data':
                    # Add CSV/data files as text to the prompt
                    data_text = file_data.decode('utf-8', errors='ignore')
                    user_prompt += f"\n\n=== DATA FILE CONTENT ({Path(local_path).name}) ===\n{data_text}\n"
                    quiz_logger.info(f"📄 Added data file to prompt: {Path(local_path).name} ({len(data_text)} chars)")
                else:
                    # Store audio/video/image for later
                    audio_video_image_files.append((media_type, local_path, file_data))
        
        # Now create content_parts with updated prompt
        content_parts = [user_prompt]
        
        # Second pass: add audio/video/image to content_parts
        for media_type, local_path, file_data in audio_video_image_files:
            if media_type == 'audio':
                # Detect MIME type based on file extension
                file_ext = Path(local_path).suffix.lower()
                mime_map = {
                    '.mp3': 'audio/mp3',
                    '.wav': 'audio/wav',
                    '.ogg': 'audio/ogg',
                    '.opus': 'audio/ogg',  # Opus is encapsulated in OGG
                    '.m4a': 'audio/mp4',
                    '.flac': 'audio/flac',
                    '.aac': 'audio/aac'
                }
                mime_type = mime_map.get(file_ext, 'audio/mp3')
                
                content_parts.append(types.Part.from_bytes(
                    data=file_data,
                    mime_type=mime_type
                ))
                quiz_logger.info(f"🎵 Added audio to multimodal input ({mime_type})")
                
            elif media_type == 'video':
                content_parts.append(types.Part.from_bytes(
                    data=file_data,
                    mime_type='video/mp4'
                ))
                quiz_logger.info(f"🎬 Added video to multimodal input")
                
            elif media_type == 'image':
                content_parts.append(types.Part.from_bytes(
                    data=file_data,
                    mime_type='image/jpeg'
                ))
                quiz_logger.info(f"🖼️  Added image to multimodal input")
        
        # 3. Call the Gemini API with Structured Output Configuration
        model_name = 'gemini-2.5-flash'
        has_media = any(media_type in ['audio', 'video', 'image'] for media_type, _, _ in audio_video_image_files)
        
        # Get stage complexity for token limit
        complexity = estimate_stage_complexity(scraped_data, question_text)
        quiz_logger.info(f"📊 Using model: {model_name} | Complexity: {complexity.upper()}")
        
        if use_fast_model:
            quiz_logger.info("⚡ Using fast mode override")
        elif has_media:
            quiz_logger.info(f"🎥 Multimodal mode: {model_name}")
        else:
            quiz_logger.info(f"📝 Text mode: {model_name}")
        
        # Retry logic with exponential backoff (max 60 seconds total)
        # Strategy: 5 retries with backoff [2s, 4s, 8s, 16s, 30s] = ~60s total
        max_retries = 5
        retry_delays = [2, 4, 8, 16, 30]  # Exponential backoff in seconds
        response = None
        
        # OPTIMIZATION: Get adaptive token limit based on complexity
        max_tokens = get_adaptive_token_limit(scraped_data, question_text)
        
        # OPTIMIZATION: Rate limiting protection
        rate_limiter = get_rate_limiter()
        await rate_limiter.wait_if_needed(estimated_tokens=max_tokens)
        
        for attempt in range(max_retries):
            try:
                quiz_logger.info(f"🔄 LLM API attempt {attempt + 1}/{max_retries}")
                response = await LLM_CLIENT.models.generate_content(
                    model=model_name,
                    contents=content_parts,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        response_mime_type="application/json",
                        response_schema=QuizAnswerModel,
                        temperature=0.1,
                        top_p=0.9,
                        top_k=20,
                        max_output_tokens=max_tokens,  # Dynamic based on stage complexity
                    )
                )
                quiz_logger.info(f"✅ LLM API succeeded on attempt {attempt + 1}")
                
                # Record successful request for rate limiting
                rate_limiter.record_request(tokens_used=max_tokens)
                
                break  # Success - exit retry loop
            except ServerError as e:
                if '503' in str(e) or 'overloaded' in str(e).lower():
                    quiz_logger.warning(f"⚠️  Model overloaded (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        delay = retry_delays[attempt]
                        quiz_logger.info(f"⏳ Retrying in {delay} seconds...")
                        await asyncio.sleep(delay)
                    else:
                        quiz_logger.error(f"❌ All {max_retries} attempts failed - model overloaded")
                        raise ValueError(f"LLM service unavailable after {max_retries} attempts (60s timeout)")
                else:
                    # Non-503 error - don't retry
                    quiz_logger.error(f"❌ LLM API error (non-retryable): {e}")
                    raise
            except Exception as e:
                quiz_logger.error(f"❌ Unexpected error on attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    raise
                await asyncio.sleep(retry_delays[attempt])
        
        if response is None:
            raise ValueError("LLM failed to generate response after all retries")

        # 4. Parse the Structured JSON Output
        quiz_logger.debug(f"LLM Response - parsed: {response.parsed}, text: {response.text[:200] if response.text else 'None'}")
        
        if response.parsed:
            result = response.parsed
            
            # CRITICAL VALIDATION: Aggressively clean up final_answer
            final_answer_str = str(result.final_answer).strip()
            original_answer = final_answer_str
            
            # Strategy 1: Check if LLM returned JSON structure
            if final_answer_str.startswith('{') and final_answer_str.endswith('}'):
                try:
                    parsed_json = json.loads(final_answer_str)
                    # Try multiple keys that might contain the answer
                    for key in ['answer', 'final_answer', 'value', 'result', 'secret']:
                        if key in parsed_json:
                            result.final_answer = str(parsed_json[key])
                            quiz_logger.warning(f"🔧 Unwrapped JSON: extracted '{key}' = {result.final_answer}")
                            final_answer_str = str(result.final_answer).strip()
                            break
                except json.JSONDecodeError:
                    pass
            
            # Strategy 2: Remove surrounding quotes
            if final_answer_str.startswith('"') and final_answer_str.endswith('"'):
                final_answer_str = final_answer_str[1:-1]
            if final_answer_str.startswith("'") and final_answer_str.endswith("'"):
                final_answer_str = final_answer_str[1:-1]
            
            # Strategy 3: Check for nested JSON in string format
            if '{' in final_answer_str and '}' in final_answer_str:
                try:
                    # Extract JSON from string
                    json_match = re.search(r'\{[^}]+\}', final_answer_str)
                    if json_match:
                        nested_json = json.loads(json_match.group())
                        for key in ['answer', 'final_answer', 'value', 'result']:
                            if key in nested_json:
                                final_answer_str = str(nested_json[key])
                                quiz_logger.warning(f"🔧 Extracted from nested JSON: {final_answer_str}")
                                break
                except:
                    pass
            
            result.final_answer = final_answer_str
            
            if original_answer != final_answer_str:
                quiz_logger.info(f"✅ Answer cleaned: '{original_answer[:50]}...' -> '{final_answer_str[:50]}...'")
            
            return result
        else:
            quiz_logger.error(f"LLM failed structured output. Response.parsed is None")
            quiz_logger.error(f"Response.text: {response.text[:500] if response.text else 'None'}")
            quiz_logger.error(f"Response candidates: {len(response.candidates) if response.candidates else 0}")
            if response.candidates and len(response.candidates) > 0:
                first_candidate = response.candidates[0]
                quiz_logger.error(f"First candidate finish_reason: {first_candidate.finish_reason}")
                quiz_logger.error(f"First candidate safety_ratings: {first_candidate.safety_ratings}")
                if first_candidate.content and first_candidate.content.parts:
                    quiz_logger.error(f"First candidate parts count: {len(first_candidate.content.parts)}")
                    quiz_logger.error(f"First candidate parts[0]: {str(first_candidate.content.parts[0])[:200]}")
            raise ValueError("LLM response was not valid JSON or model refused to answer.")

    except Exception as e:
        quiz_logger.error(f"Error during LLM API call: {e}")
        raise e
    finally:
        # Cleanup downloaded media files
        for file_path in downloaded_files:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    quiz_logger.debug(f"🗑️  Cleaned up: {file_path}")
            except Exception as cleanup_error:
                quiz_logger.warning(f"Failed to cleanup {file_path}: {cleanup_error}")