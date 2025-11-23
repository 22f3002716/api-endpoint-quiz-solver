from pydantic import BaseModel, Field, EmailStr, HttpUrl, ConfigDict
from typing import Optional, List, Literal

# --- Quiz Request Schema (Moved from main.py) ---

class QuizRequest(BaseModel):
    """
    Model for the incoming POST request payload from the Quiz Master.
    """
    email: EmailStr
    secret: str
    url: HttpUrl
    
    # Pydantic V2 way to allow extra fields (e.g., 'reason')
    model_config = ConfigDict(extra='allow')

# --- Pydantic Schemas for LLM Output (Strongly-Typed AI) ---

class QuizAnswerModel(BaseModel):
    """
    The structured output model that the LLM must adhere to.
    This forces the answer to be machine-readable and validated.
    """
    # A required field indicating the final answer
    final_answer: str = Field(
        description="The final calculated or derived answer to the quiz question, formatted exactly as requested (e.g., a number, a specific string, a date)."
    )

    # A required field for the LLM to explain its reasoning (for logging/audit)
    reasoning_summary: str = Field(
        description="A concise summary of the steps taken, including which data sources were used and the calculation performed to arrive at the final_answer."
    )

# --- Tool Output Schema (Example for Building AI Agents With Tools) ---

class CalculationToolOutput(BaseModel):
    """
    Model for when the LLM decides a complex calculation is needed.
    The LLM will call this tool by outputting JSON matching this schema.
    """
    tool_name: Literal["calculator"] = "calculator" # Forces the tool name
    expression: str = Field(
        description="The full Python-compatible arithmetic expression to evaluate (e.g., 'sum([12, 34, 56]) * 1.05')."
    )
    # Note: We can add more complex tools later (e.g., data aggregation tool)