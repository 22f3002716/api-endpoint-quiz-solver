import asyncio
import platform # <-- NEW IMPORT
import time
from typing import List
from playwright.async_api import async_playwright
from models import QuizRequest, QuizAnswerModel
from llm_service import get_structured_answer
from logger import quiz_logger
import requests # Standard library for API calls (for scraping/submission)

# --- WINDOWS FIX: Force ProactorEventLoop (CRITICAL) ---
# This ensures Playwright can launch its internal process on Windows.
if platform.system() == "Windows":
    try:
        if isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy):
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except AttributeError:
        pass
# --- END WINDOWS FIX ---

# --- Configuration ---
MAX_QUIZ_TIME_SECONDS = 180 
MAX_ATTEMPTS = 3 # Maximum retries per quiz stage

# --- Helper: Scrape the Current Quiz Page ---
async def scrape_quiz_page(page, url: str) -> str:
    """Navigates to the URL and scrapes the question and all visible text."""
    await page.goto(url, wait_until="networkidle")

    # --- A. Scrape Question/Text ---
    question_text = await page.inner_text("body") # Scrape all body text

    # --- B. Scrape Links/Data Sources (Crucial for multi-step) ---
    data_links = await page.eval_on_selector_all("a", "elements => elements.map(e => e.href)")

    scraped_data = f"PAGE URL: {url}\n\nPAGE CONTENT:\n{question_text}"

    # Enhance the scraped data with link information
    if data_links:
        scraped_data += "\n\nDISCOVERED DATA LINKS:\n" + "\n".join(set(data_links))

    return scraped_data

# --- Core Multi-Step Solver Function ---

async def solve_quiz_sequence_core(payload: QuizRequest):
    """
    Executes the full, multi-step, self-correcting quiz-solving workflow.
    """
    current_url = str(payload.url)
    email = payload.email
    # Set a hard deadline (3 minutes from the initial request time)
    deadline = time.time() + MAX_QUIZ_TIME_SECONDS

    # State tracking for the multi-step flow
    past_attempt_feedback: List[str] = []

    # This line now runs after the event loop policy is correctly set on Windows
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        while time.time() < deadline and current_url:
            time_left = round(deadline - time.time(), 2)
            quiz_logger.info(f"--- STARTING STAGE: {current_url} | Time Left: {time_left}s ---")

            # 1. Scrape the current page
            scraped_data = await scrape_quiz_page(page, current_url)

            # 2. LLM Orchestration Loop (with Retries)
            for attempt in range(MAX_ATTEMPTS):
                try:
                    # Combine all past error feedback for the next LLM call
                    error_context = "\n".join(past_attempt_feedback) if past_attempt_feedback else None

                    # Get the structured answer from the LLM
                    llm_output: QuizAnswerModel = await get_structured_answer(
                        question_text=scraped_data[:1000], # Pass summary of scraped data
                        scraped_data=scraped_data, 
                        error_feedback=error_context
                    )

                    quiz_logger.info(f"LLM Answer (Attempt {attempt+1}): {llm_output.final_answer[:50]}...")

                    # 3. Submission (Assume submission is a POST to the current URL for simplicity)
                    submission_url = current_url # In a real scenario, this might be scraped

                    # Payload structure based on typical quiz master response requirement
                    submission_data = {
                        "email": email,
                        "secret": payload.secret,
                        "answer": llm_output.final_answer,
                        "reasoning": llm_output.reasoning_summary # Include for auditing/debugging
                    }

                    # Use standard requests library for the final POST submission
                    response = requests.post(submission_url, json=submission_data)
                    response_data = response.json()

                    # 4. Check Submission Response
                    if response.status_code == 200 and response_data.get("correct") is True:
                        # SUCCESS: Check for next URL or final confirmation
                        current_url = response_data.get("url") # Could be the next stage URL
                        if not current_url:
                            quiz_logger.critical(f"🎉 FINAL QUIZ SUCCESS: {email} | Answer: {llm_output.final_answer}")
                            await browser.close()
                            return # Exit the main loop
                        break # Break the retry loop to continue to the next stage

                    elif response_data.get("correct") is False:
                        # FAILURE: Prepare for a retry
                        feedback = response_data.get("reason", "No specific reason provided.")
                        past_attempt_feedback.append(f"Attempt {attempt+1} failed. Reason: {feedback}. Submitted: {llm_output.final_answer}")
                        quiz_logger.warning(f"Submission failed. Retrying (Attempt {attempt+2}). Reason: {feedback}")

                    else:
                        # UNEXPECTED API RESPONSE: Treat as fatal for this stage
                        raise Exception(f"Quiz Master API returned unexpected response: {response.text}")

                except Exception as e:
                    # Error Handling & Error Logging
                    quiz_logger.error(f"CRITICAL STAGE ERROR (Attempt {attempt+1}): {e}", exc_info=True)
                    past_attempt_feedback.append(f"Attempt {attempt+1} failed due to internal error: {e}")
                    await asyncio.sleep(1) # Wait briefly before retry

            else:
                # This block runs if the retry loop completes without a successful 'break'
                quiz_logger.error(f"FAILURE: Stage {current_url} failed after {MAX_ATTEMPTS} attempts. Exiting.")
                await browser.close()
                return

        if time.time() >= deadline:
            quiz_logger.error(f"FAILURE: Quiz exceeded the {MAX_QUIZ_TIME_SECONDS} second deadline.")

        await browser.close()

# --- Integration with Phase 1 (Update main.py) ---
async def solve_quiz_sequence(payload: QuizRequest):
    """Wrapper for main.py's background task."""
    try:
        await solve_quiz_sequence_core(payload)
    except Exception as e:
        quiz_logger.critical(f"UNHANDLED FATAL ERROR in Quiz Sequence for {payload.email}: {e}", exc_info=True)