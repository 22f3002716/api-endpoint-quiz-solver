"""
Mock LLM Service for Local Testing
This module provides a simple mock implementation that doesn't require API keys.
"""
import re
from typing import Optional
from models import QuizAnswerModel
from logger import quiz_logger


async def get_structured_answer_mock(
    question_text: str, 
    scraped_data: str, 
    error_feedback: Optional[str] = None
) -> QuizAnswerModel:
    """
    Mock LLM function that uses simple heuristics to answer quiz questions.
    This allows testing without requiring actual LLM API keys.
    
    Returns: QuizAnswerModel with answer and reasoning
    """
    quiz_logger.info("Using MOCK LLM (no API call)")
    
    # Extract numbers from the scraped data for simple math questions
    numbers = re.findall(r'\d+', scraped_data)
    
    # Simple heuristic: if question asks for sum, add all numbers found
    if 'sum' in question_text.lower() or 'sum' in scraped_data.lower():
        if numbers:
            total = sum(int(n) for n in numbers)
            return QuizAnswerModel(
                final_answer=str(total),
                reasoning_summary=f"Mock LLM: Found {len(numbers)} numbers in data: {numbers}. Calculated sum: {total}"
            )
    
    # If question asks for count
    if 'count' in question_text.lower() or 'how many' in scraped_data.lower():
        count = len(numbers) if numbers else 0
        return QuizAnswerModel(
            final_answer=str(count),
            reasoning_summary=f"Mock LLM: Counted {count} numbers in the scraped data."
        )
    
    # Default: return first number found or a placeholder
    if numbers:
        return QuizAnswerModel(
            final_answer=numbers[0],
            reasoning_summary=f"Mock LLM: Extracted first number found: {numbers[0]}"
        )
    
    # Fallback for demo URLs or unclear questions
    return QuizAnswerModel(
        final_answer="42",
        reasoning_summary="Mock LLM: No clear pattern detected. Using placeholder answer: 42"
    )
