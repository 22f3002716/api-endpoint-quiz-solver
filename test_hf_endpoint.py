"""
Test Script for Hugging Face Deployed Quiz Solver
Tests the deployed endpoint against custom quiz server stages
"""

import requests
import time
import json
from datetime import datetime

# Configuration
HF_ENDPOINT = "https://karthikeyan414-api-endpoint-quiz-solver.hf.space/quiz-task"
CUSTOM_QUIZ_BASE = "http://localhost:5000"  # Start custom_quiz_server.py locally
EMAIL = "22f3002716@ds.study.iitm.ac.in"
SECRET = "Habshan2025Q4!!!"

# All available stages in custom quiz server
STAGES = [
    {"id": 1, "name": "Web Scraping (JavaScript)", "url": f"{CUSTOM_QUIZ_BASE}/stage1"},
    {"id": 2, "name": "API Data Extraction", "url": f"{CUSTOM_QUIZ_BASE}/stage2"},
    {"id": 3, "name": "Base64 Decoding", "url": f"{CUSTOM_QUIZ_BASE}/stage3"},
    {"id": 4, "name": "CSV Data Analysis", "url": f"{CUSTOM_QUIZ_BASE}/stage4"},
    {"id": 5, "name": "JSON Parsing", "url": f"{CUSTOM_QUIZ_BASE}/stage5"},
    {"id": 6, "name": "Regex Validation", "url": f"{CUSTOM_QUIZ_BASE}/stage6"},
    {"id": 7, "name": "Date Calculation", "url": f"{CUSTOM_QUIZ_BASE}/stage7"},
    {"id": 8, "name": "Mathematical Operations", "url": f"{CUSTOM_QUIZ_BASE}/stage8"},
    {"id": 9, "name": "String Manipulation", "url": f"{CUSTOM_QUIZ_BASE}/stage9"},
    {"id": 10, "name": "Conditional Logic", "url": f"{CUSTOM_QUIZ_BASE}/stage10"},
    {"id": 11, "name": "Data Filtering", "url": f"{CUSTOM_QUIZ_BASE}/stage11"},
    {"id": 12, "name": "Aggregation", "url": f"{CUSTOM_QUIZ_BASE}/stage12"},
    {"id": 13, "name": "Sorting & Ranking", "url": f"{CUSTOM_QUIZ_BASE}/stage13"},
    {"id": 14, "name": "Multi-step Calculation", "url": f"{CUSTOM_QUIZ_BASE}/stage14"},
    {"id": 15, "name": "Pattern Matching", "url": f"{CUSTOM_QUIZ_BASE}/stage15"},
    {"id": 16, "name": "Data Validation", "url": f"{CUSTOM_QUIZ_BASE}/stage16"},
    {"id": 17, "name": "Complex Filtering", "url": f"{CUSTOM_QUIZ_BASE}/stage17"},
    {"id": 18, "name": "Statistical Analysis", "url": f"{CUSTOM_QUIZ_BASE}/stage18"},
    {"id": 19, "name": "Time Series Data", "url": f"{CUSTOM_QUIZ_BASE}/stage19"},
    {"id": 20, "name": "Nested JSON", "url": f"{CUSTOM_QUIZ_BASE}/stage20"},
]


def test_single_stage(stage_id, stage_name, stage_url):
    """Test a single stage against the HF endpoint"""
    print(f"\n{'='*80}")
    print(f"Testing Stage {stage_id}: {stage_name}")
    print(f"URL: {stage_url}")
    print(f"{'='*80}")
    
    payload = {
        "email": EMAIL,
        "secret": SECRET,
        "url": stage_url
    }
    
    try:
        print(f"⏳ Sending request to HF endpoint...")
        start_time = time.time()
        
        response = requests.post(HF_ENDPOINT, json=payload, timeout=300)
        
        elapsed = time.time() - start_time
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Response received in {elapsed:.2f}s")
            print(f"📋 Response: {json.dumps(result, indent=2)}")
            return {
                "stage_id": stage_id,
                "stage_name": stage_name,
                "status": "SUCCESS",
                "time": elapsed,
                "response": result
            }
        else:
            print(f"❌ Failed with status {response.status_code}")
            print(f"Response: {response.text}")
            return {
                "stage_id": stage_id,
                "stage_name": stage_name,
                "status": "FAILED",
                "time": elapsed,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
    
    except requests.Timeout:
        print(f"⏱️ Request timed out after 300s")
        return {
            "stage_id": stage_id,
            "stage_name": stage_name,
            "status": "TIMEOUT",
            "time": 300,
            "error": "Request timeout"
        }
    
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        return {
            "stage_id": stage_id,
            "stage_name": stage_name,
            "status": "ERROR",
            "time": 0,
            "error": str(e)
        }


def run_all_tests():
    """Run tests for all stages"""
    print(f"\n{'#'*80}")
    print(f"# Hugging Face Endpoint Test Suite")
    print(f"# Endpoint: {HF_ENDPOINT}")
    print(f"# Custom Quiz: {CUSTOM_QUIZ_BASE}")
    print(f"# Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'#'*80}\n")
    
    # Check if custom quiz server is running
    try:
        test_response = requests.get(f"{CUSTOM_QUIZ_BASE}/stage1", timeout=5)
        print(f"✅ Custom quiz server is accessible\n")
    except Exception as e:
        print(f"❌ Cannot reach custom quiz server at {CUSTOM_QUIZ_BASE}")
        print(f"   Please start it with: python custom_quiz_server.py")
        print(f"   Error: {e}\n")
        return
    
    # Check if HF endpoint is accessible
    try:
        test_response = requests.get(HF_ENDPOINT.replace('/quiz-task', '/'), timeout=10)
        print(f"✅ Hugging Face endpoint is accessible\n")
    except Exception as e:
        print(f"⚠️  Warning: Cannot reach HF endpoint (may be cold start)")
        print(f"   Error: {e}\n")
    
    results = []
    
    # Test each stage
    for stage in STAGES:
        result = test_single_stage(stage["id"], stage["name"], stage["url"])
        results.append(result)
        
        # Wait between requests to avoid rate limiting
        print(f"\n⏸️  Waiting 5s before next test...")
        time.sleep(5)
    
    # Summary
    print(f"\n\n{'='*80}")
    print(f"TEST SUMMARY")
    print(f"{'='*80}\n")
    
    success_count = sum(1 for r in results if r["status"] == "SUCCESS")
    failed_count = sum(1 for r in results if r["status"] == "FAILED")
    timeout_count = sum(1 for r in results if r["status"] == "TIMEOUT")
    error_count = sum(1 for r in results if r["status"] == "ERROR")
    
    print(f"Total Stages: {len(results)}")
    print(f"✅ Success: {success_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"⏱️  Timeout: {timeout_count}")
    print(f"🔴 Error: {error_count}")
    print(f"Success Rate: {(success_count/len(results)*100):.1f}%\n")
    
    # Detailed results
    print(f"{'Stage':<8} {'Name':<35} {'Status':<10} {'Time':<8}")
    print(f"{'-'*80}")
    for r in results:
        status_icon = {"SUCCESS": "✅", "FAILED": "❌", "TIMEOUT": "⏱️", "ERROR": "🔴"}[r["status"]]
        print(f"{r['stage_id']:<8} {r['stage_name']:<35} {status_icon} {r['status']:<10} {r['time']:.2f}s")
    
    # Save results to file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f"test_results_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "endpoint": HF_ENDPOINT,
            "custom_quiz_base": CUSTOM_QUIZ_BASE,
            "summary": {
                "total": len(results),
                "success": success_count,
                "failed": failed_count,
                "timeout": timeout_count,
                "error": error_count,
                "success_rate": round(success_count/len(results)*100, 2)
            },
            "results": results
        }, f, indent=2)
    
    print(f"\n📄 Detailed results saved to: {filename}\n")


def test_specific_stage(stage_id):
    """Test a specific stage by ID"""
    stage = next((s for s in STAGES if s["id"] == stage_id), None)
    if stage:
        result = test_single_stage(stage["id"], stage["name"], stage["url"])
        print(f"\n{'='*80}")
        print(f"RESULT: {result['status']}")
        print(f"{'='*80}\n")
    else:
        print(f"❌ Stage {stage_id} not found. Available stages: 1-{len(STAGES)}")


if __name__ == "__main__":
    import sys
    
    print("""
╔═══════════════════════════════════════════════════════════════════════════╗
║         HUGGING FACE ENDPOINT TEST SUITE - Custom Quiz Server            ║
╚═══════════════════════════════════════════════════════════════════════════╝
    """)
    
    if len(sys.argv) > 1:
        # Test specific stage
        try:
            stage_id = int(sys.argv[1])
            test_specific_stage(stage_id)
        except ValueError:
            print(f"❌ Invalid stage ID. Use: python test_hf_endpoint.py [stage_number]")
    else:
        # Run all tests
        print("Starting full test suite...")
        print("This will test all 20 stages (may take 30-60 minutes)\n")
        
        confirm = input("Continue? (y/n): ")
        if confirm.lower() == 'y':
            run_all_tests()
        else:
            print("Test cancelled.")
