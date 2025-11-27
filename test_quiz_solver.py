"""
Unit Test Script for Quiz Solver API
This script tests the API endpoint step by step.
"""
import asyncio
import json
import sys
from typing import Dict, Any
import requests
from logger import quiz_logger
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test configuration
API_BASE_URL = "http://127.0.0.1:8000"
TEST_EMAIL = "test_student@example.com"
TEST_SECRET = os.getenv("MASTER_QUIZ_SECRET", "test_secret_123")  # Use the same secret from .env


class QuizTester:
    """Test harness for the Quiz Solver API"""
    
    def __init__(self, base_url: str, email: str, secret: str):
        self.base_url = base_url
        self.email = email
        self.secret = secret
        self.session = requests.Session()
    
    def test_health_check(self) -> bool:
        """Test 1: Check if the server is running"""
        try:
            response = self.session.get(f"{self.base_url}/docs")
            if response.status_code == 200:
                print("✅ Server is running and reachable")
                return True
            else:
                print(f"❌ Server returned status {response.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to server. Is uvicorn running?")
            return False
        except Exception as e:
            print(f"❌ Health check failed: {e}")
            return False
    
    def test_invalid_secret(self) -> bool:
        """Test 2: Verify that invalid secrets are rejected (HTTP 403)"""
        payload = {
            "email": self.email,
            "secret": "wrong_secret",
            "url": "https://example.com/test"
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/quiz-task",
                json=payload,
                timeout=5
            )
            
            if response.status_code == 403:
                print("✅ Invalid secret correctly rejected (403)")
                return True
            else:
                print(f"❌ Expected 403, got {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            return False
    
    def test_invalid_json(self) -> bool:
        """Test 3: Verify that malformed requests are rejected (HTTP 422)"""
        # Missing required field 'url'
        payload = {
            "email": self.email,
            "secret": self.secret
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/quiz-task",
                json=payload,
                timeout=5
            )
            
            if response.status_code == 422:
                print("✅ Invalid JSON correctly rejected (422)")
                return True
            else:
                print(f"❌ Expected 422, got {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            return False
    
    def test_valid_request_demo(self) -> bool:
        """Test 4: Send valid request to demo URL"""
        payload = {
            "email": self.email,
            "secret": self.secret,
            "url": "https://tds-llm-analysis.s-anand.net/demo"
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/quiz-task",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Valid request accepted (200)")
                print(f"   Response: {json.dumps(data, indent=2)}")
                return True
            else:
                print(f"❌ Expected 200, got {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            return False
    
    def test_custom_url(self, url: str) -> bool:
        """Test 5: Send request to custom URL"""
        payload = {
            "email": self.email,
            "secret": self.secret,
            "url": url
        }
        
        try:
            response = self.session.post(
                f"{self.base_url}/quiz-task",
                json=payload,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"✅ Custom URL request accepted (200)")
                print(f"   Response: {json.dumps(data, indent=2)}")
                return True
            else:
                print(f"❌ Expected 200, got {response.status_code}")
                print(f"   Response: {response.text}")
                return False
        except Exception as e:
            print(f"❌ Test failed with error: {e}")
            return False


def run_tests_interactive():
    """Run tests step by step with user confirmation"""
    print("\n" + "="*60)
    print("Quiz Solver API - Interactive Test Suite")
    print("="*60 + "\n")
    
    # Initialize tester
    tester = QuizTester(API_BASE_URL, TEST_EMAIL, TEST_SECRET)
    
    tests = [
        ("Health Check", tester.test_health_check),
        ("Invalid Secret (403)", tester.test_invalid_secret),
        ("Invalid JSON (422)", tester.test_invalid_json),
        ("Valid Demo Request", tester.test_valid_request_demo),
    ]
    
    results = []
    
    for i, (test_name, test_func) in enumerate(tests, 1):
        print(f"\n{'─'*60}")
        print(f"Test {i}/{len(tests)}: {test_name}")
        print(f"{'─'*60}")
        
        # Ask for permission
        response = input(f"\nRun this test? (y/n/q to quit): ").strip().lower()
        
        if response == 'q':
            print("\n⚠️  Testing interrupted by user")
            break
        elif response != 'y':
            print("⏭️  Skipped")
            continue
        
        # Run the test
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"💥 Test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total


def run_all_tests_auto():
    """Run all tests automatically without prompts"""
    print("\n" + "="*60)
    print("Quiz Solver API - Automated Test Suite")
    print("="*60 + "\n")
    
    tester = QuizTester(API_BASE_URL, TEST_EMAIL, TEST_SECRET)
    
    tests = [
        ("Health Check", tester.test_health_check),
        ("Invalid Secret (403)", tester.test_invalid_secret),
        ("Invalid JSON (422)", tester.test_invalid_json),
        ("Valid Demo Request", tester.test_valid_request_demo),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\nRunning: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"💥 Test crashed: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    print("\nQuiz Solver Test Script")
    print("Make sure:")
    print(f"  1. Uvicorn is running on {API_BASE_URL}")
    print(f"  2. MASTER_QUIZ_SECRET in .env is: {TEST_SECRET}")
    print(f"  3. USE_MOCK_LLM=true is set in .env (for testing without API keys)\n")
    
    mode = input("Choose mode:\n  [1] Interactive (step-by-step with prompts)\n  [2] Automated (all tests)\n\nChoice (1/2): ").strip()
    
    if mode == "1":
        success = run_tests_interactive()
    else:
        success = run_all_tests_auto()
    
    sys.exit(0 if success else 1)
