"""
Quick Test Script for Hugging Face Endpoint
Tests individual stages quickly
"""

import requests
import json

# Configuration
HF_ENDPOINT = "https://karthikeyan414-api-endpoint-quiz-solver.hf.space/quiz-task"
EMAIL = "22f3002716@ds.study.iitm.ac.in"
SECRET = "Habshan2025Q4!!!"

# Quick test stages (replace with your local custom quiz server URL if different)
# CUSTOM_QUIZ_BASE = "http://localhost:5000"

# To (replace with YOUR ngrok URL):
CUSTOM_QUIZ_BASE = "https://electrical-pluviometrical-ciera.ngrok-free.dev"

def quick_test(stage_num):
    """Quick test of a single stage"""
    stage_url = f"{CUSTOM_QUIZ_BASE}/stage{stage_num}"
    
    payload = {
        "email": EMAIL,
        "secret": SECRET,
        "url": stage_url
    }
    
    print(f"\n🚀 Testing Stage {stage_num}")
    print(f"📍 URL: {stage_url}")
    print(f"⏳ Sending request to HF...\n")
    
    try:
        response = requests.post(HF_ENDPOINT, json=payload, timeout=300)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ SUCCESS!")
            print(f"📋 Response:\n{json.dumps(result, indent=2)}\n")
            return True
        else:
            print(f"❌ FAILED: HTTP {response.status_code}")
            print(f"Response: {response.text}\n")
            return False
    
    except Exception as e:
        print(f"❌ ERROR: {str(e)}\n")
        return False


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        stage = int(sys.argv[1])
        quick_test(stage)
    else:
        print("Usage: python quick_test.py <stage_number>")
        print("Example: python quick_test.py 1")
