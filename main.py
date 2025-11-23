import asyncio 
import platform 
# --- WINDOWS FIX: Force ProactorEventLoop (CRITICAL) ---
# This ensures Playwright can launch its internal process on Windows.
if platform.system() == "Windows":
    try:
        # Check if the current policy is SelectorEventLoopPolicy (the problematic default)
        if isinstance(asyncio.get_event_loop_policy(), asyncio.WindowsSelectorEventLoopPolicy):
            # Set the policy to WindowsProactorEventLoopPolicy
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except AttributeError:
        # Fallback for older Python versions or specific setups
        pass
# --- END WINDOWS FIX ---

import json
import os
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

    # Start the heavy lifting in a non-blocking background task
    background_tasks.add_task(solve_quiz_sequence, payload)

    # --- D. Respond Immediately ---
    return {
        "message": "Quiz task accepted and processing in the background.",
        "url": str(payload.url)
    }