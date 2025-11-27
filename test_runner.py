"""
Test runner for custom quiz stages 1-24
"""
import asyncio
import sys
import os
from dotenv import load_dotenv
from models import QuizRequest
from solver import solve_quiz_sequence

# Load environment
load_dotenv()

async def run_custom_quiz_test(start_stage: int = 1, end_stage: int = 24):
    """Run custom quiz test from start_stage to end_stage"""
    
    email = os.getenv("QUIZ_EMAIL", "test@example.com")
    secret = os.getenv("MASTER_QUIZ_SECRET")
    
    if not secret:
        print("ERROR: MASTER_QUIZ_SECRET not found in .env")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"Starting Custom Quiz Test: Stages {start_stage} to {end_stage}")
    print(f"Email: {email}")
    print(f"{'='*60}\n")
    
    # Create quiz request starting from stage 1
    # The solver will follow next_url links automatically
    quiz_request = QuizRequest(
        email=email,
        secret=secret,
        url=f"http://localhost:5000/stage{start_stage}"
    )
    
    # Run the quiz - it will follow links automatically through stage 24
    await solve_quiz_sequence(quiz_request)
    
    print(f"\n{'='*60}")
    print(f"Custom Quiz Test Complete!")
    print(f"Check quiz_solver.log for detailed results")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test custom quiz stages")
    parser.add_argument("--start", type=int, default=1, help="Starting stage number")
    parser.add_argument("--end", type=int, default=24, help="Ending stage number")
    
    args = parser.parse_args()
    
    # Run the test
    asyncio.run(run_custom_quiz_test(args.start, args.end))
