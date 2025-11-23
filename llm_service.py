import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel
from typing import Optional
from logger import quiz_logger
from models import QuizAnswerModel, CalculationToolOutput 

# --- LLM Client Initialization ---

try:
    # Client automatically uses the LLM_API_KEY from the environment
    LLM_CLIENT = genai.Client(api_key=os.getenv("LLM_API_KEY")) 
except Exception as e:
    quiz_logger.error(f"Failed to initialize Gemini Client: {e}")
    LLM_CLIENT = None # Handle client failure gracefully

# --- Core LLM Interaction ---

async def get_structured_answer(
    question_text: str, 
    scraped_data: str, 
    error_feedback: Optional[str] = None
) -> QuizAnswerModel:
    """
    Calls the LLM to process the question and scraped data, forcing 
    the output to conform to the QuizAnswerModel Pydantic schema.
    """
    if not LLM_CLIENT:
        raise RuntimeError("LLM client not initialized. Check LLM_API_KEY.")

    # 1. Construct the System Prompt (The Agent's Instructions)
    system_prompt = (
        "You are an expert Quiz Solver AI. Your task is to analyze the user's question "
        "and the provided scraped data to find the final, definitive answer. "
        "You MUST use the provided JSON schema for your response. "
        "If an ERROR_FEEDBACK is provided, you must review your previous reasoning and correct your approach."
    )

    # 2. Construct the User Prompt (The Data/Task)
    user_prompt = f"QUIZ QUESTION: {question_text}\n\nSCRAPED DATA:\n{scraped_data}"
    if error_feedback:
        user_prompt += f"\n\n--- PREVIOUS ATTEMPT ERROR FEEDBACK ---\n{error_feedback}"

    quiz_logger.info(f"LLM Prompt constructed. Length: {len(user_prompt)} chars.")

    try:
        # 3. Call the Gemini API with Structured Output Configuration
        # CORRECTED LINE: Use LLM_CLIENT.models.generate_content
        response = await LLM_CLIENT.models.generate_content(
            model='gemini-2.5-flash', # A fast, capable model
            contents=[user_prompt],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                # This tells the model to output a JSON that validates against QuizAnswerModel
                response_mime_type="application/json",
                response_schema=QuizAnswerModel,
                # Add tools here if we wanted the LLM to call them first (Advanced Agent step)
                # tools=[CalculationToolOutput], 
            )
        )

        # 4. Parse the Structured JSON Output
        # The SDK automatically handles the JSON string output and returns a Pydantic object
        if response.parsed:
            return response.parsed 
        else:
             # This handles cases where the model refuses or fails to generate valid JSON
            quiz_logger.error(f"LLM failed structured output: {response.text}")
            raise ValueError("LLM response was not valid JSON or model refused to answer.")

    except Exception as e:
        quiz_logger.error(f"Error during LLM API call: {e}")
        raise e