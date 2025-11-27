import asyncio 
import platform
import sys
# --- WINDOWS FIX: Force ProactorEventLoop (CRITICAL for Playwright) ---
# This ensures Playwright can launch its internal process on Windows.
if platform.system() == "Windows":
    # Python 3.13+ changed the default loop on Windows
    # We need ProactorEventLoop for subprocess support (required by Playwright)
    if sys.version_info >= (3, 8):
        try:
            # Set the policy to WindowsProactorEventLoopPolicy
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            # Fallback for older Python versions or specific setups
            pass
# --- END WINDOWS FIX ---

import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, BackgroundTasks
# We only need BaseModel, EmailStr, HttpUrl, ConfigDict if defining them here, 
# but since we move QuizRequest, we can remove the unused ones if QuizRequest 
# is the only Pydantic model defined in the main file. We'll keep them for safety 
# but move the QuizRequest definition.
# from pydantic import BaseModel, EmailStr, HttpUrl, ConfigDict 

from logger import quiz_logger # Import the logger
from solver import solve_quiz_sequence # <-- NEW IMPORT of the actual solver function
from models import QuizRequest # <-- NEW IMPORT of the Pydantic Model definition

# --- 1. Load Environment Variables ---
load_dotenv()
MASTER_SECRET = os.getenv("MASTER_QUIZ_SECRET")

# --- 2. Initialize FastAPI App ---
app = FastAPI(title="API Endpoint Quiz Solver")

# Thread pool for running background tasks with their own event loop
executor = ThreadPoolExecutor(max_workers=5)


def run_quiz_in_thread(payload: QuizRequest):
    """Run the quiz solver in a separate thread with its own event loop"""
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Set ProactorEventLoop policy for Windows
    if platform.system() == "Windows":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        # Run the async function in this thread's event loop
        loop.run_until_complete(solve_quiz_sequence(payload))
    except Exception as e:
        quiz_logger.error(f"Thread execution failed: {e}", exc_info=True)
    finally:
        loop.close()


@app.on_event("startup")
async def startup_event():
    """Ensure correct event loop policy on startup"""
    if platform.system() == "Windows":
        try:
            loop = asyncio.get_running_loop()
            quiz_logger.info(f"Main app running with event loop: {type(loop).__name__}")
        except Exception as e:
            quiz_logger.warning(f"Could not check event loop: {e}")

# --- 3. Pydantic Models ---
# The QuizRequest class definition and the old placeholder solve_quiz_sequence 
# function have been removed, as they are now imported from models.py and solver.py.

# --- 4. Define the API Endpoint ---

@app.post("/quiz-task", status_code=200)
async def handle_quiz_request(payload: QuizRequest, background_tasks: BackgroundTasks):
    """
    Receives the initial quiz task, validates the secret, and delegates the solving.
    """

    # --- A. Log Raw Incoming Payload ---
    raw_payload_dict = payload.model_dump(mode='json')
    quiz_logger.info(f"INCOMING PAYLOAD: {json.dumps(raw_payload_dict)}")

    # --- B. Verify Secret (Authentication) ---
    if payload.secret != MASTER_SECRET:
        quiz_logger.warning(f"ACCESS DENIED: Invalid secret received for email: {payload.email}")
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Invalid secret provided."
        )

    # --- C. Delegate Task (Authorization successful) ---
    quiz_logger.info(f"SECRET OK. Delegating task to background for URL: {payload.url}")

    # Run in a separate thread with its own event loop (Windows Python 3.13 workaround)
    executor.submit(run_quiz_in_thread, payload)

    # --- D. Respond Immediately ---
    return {
        "message": "Quiz task accepted and processing in the background.",
        "url": str(payload.url)
    }