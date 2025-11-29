# Testing Hugging Face Deployment Against Custom Quiz Server

## Overview
This guide explains how to test your deployed Hugging Face quiz solver against the custom quiz server stages.

## Prerequisites

1. **Custom Quiz Server Running Locally**
   ```bash
   python custom_quiz_server.py
   ```
   The server will start on `http://localhost:5000`

2. **Hugging Face Endpoint Active**
   - Your endpoint: `https://karthikeyan414-api-endpoint-quiz-solver.hf.space/quiz-task`
   - Verify it's running (may need cold start warm-up)

## Test Methods

### Method 1: Quick Single Stage Test

Test one stage at a time (recommended for initial testing):

```bash
python quick_test.py 1
```

This will test Stage 1 against your HF endpoint.

**Example Output:**
```
🚀 Testing Stage 1
📍 URL: http://localhost:5000/stage1
⏳ Sending request to HF...

✅ SUCCESS!
📋 Response:
{
  "message": "Quiz task accepted and processing in the background.",
  "url": "http://localhost:5000/stage1"
}
```

### Method 2: Full Test Suite

Test all 20 stages (takes 30-60 minutes):

```bash
python test_hf_endpoint.py
```

**Output Includes:**
- Real-time progress for each stage
- Success/failure status
- Execution time per stage
- Comprehensive summary
- JSON report saved to `test_results_YYYYMMDD_HHMMSS.json`

### Method 3: Test Specific Stage

```bash
python test_hf_endpoint.py 5
```

This tests only Stage 5.

## Custom Quiz Server Stages

| Stage | Challenge Type | Description |
|-------|---------------|-------------|
| 1 | Web Scraping | JavaScript-rendered content |
| 2 | API Interaction | Data extraction from API responses |
| 3 | Base64 Decoding | Decode hidden messages |
| 4 | CSV Analysis | Data processing and calculations |
| 5 | JSON Parsing | Complex nested JSON structures |
| 6 | Regex Validation | Pattern matching and validation |
| 7 | Date Calculation | Time-based computations |
| 8 | Math Operations | Complex mathematical formulas |
| 9 | String Manipulation | Text processing challenges |
| 10 | Conditional Logic | If-then-else reasoning |
| 11 | Data Filtering | Filter datasets by conditions |
| 12 | Aggregation | Sum, avg, count operations |
| 13 | Sorting & Ranking | Order data by criteria |
| 14 | Multi-step Calc | Sequential calculations |
| 15 | Pattern Matching | Find patterns in data |
| 16 | Data Validation | Verify data integrity |
| 17 | Complex Filtering | Multi-condition filters |
| 18 | Statistical Analysis | Mean, median, std dev |
| 19 | Time Series | Temporal data analysis |
| 20 | Nested JSON | Deep JSON navigation |

## Expected Behavior

### Successful Test
```
✅ Response received in 15.43s
📋 Response: {
  "message": "Quiz task accepted and processing in the background.",
  "url": "http://localhost:5000/stage1"
}
```

### Failed Test
```
❌ Failed with status 500
Response: Internal Server Error
```

### Timeout
```
⏱️ Request timed out after 300s
```

## Troubleshooting

### 1. Custom Quiz Server Not Running
**Error:** `Cannot reach custom quiz server at http://localhost:5000`

**Solution:**
```bash
python custom_quiz_server.py
```

### 2. Hugging Face Cold Start
**Error:** `Cannot reach HF endpoint`

**Solution:** 
- Visit https://karthikeyan414-api-endpoint-quiz-solver.hf.space/ in browser first
- Wait 30-60 seconds for cold start
- Try again

### 3. Rate Limiting
**Error:** `429 Too Many Requests`

**Solution:**
- Wait 60 seconds between tests
- Use `time.sleep(60)` between stages

### 4. Connection Timeout
**Error:** `Request timeout after 300s`

**Solution:**
- Check HF endpoint logs for errors
- Verify stage URL is correct
- Test simpler stages first (1-5)

## Analyzing Results

### View Detailed Report
```bash
# Open the generated JSON file
cat test_results_20251129_142530.json
```

### Check Success Rate
```python
import json

with open('test_results_20251129_142530.json') as f:
    data = json.load(f)
    
print(f"Success Rate: {data['summary']['success_rate']}%")
print(f"Total Success: {data['summary']['success']}/{data['summary']['total']}")
```

## Manual Testing with cURL

Test a single stage manually:

```bash
curl -X POST https://karthikeyan414-api-endpoint-quiz-solver.hf.space/quiz-task \
  -H "Content-Type: application/json" \
  -d '{
    "email": "22f3002716@ds.study.iitm.ac.in",
    "secret": "Habshan2025Q4!!!",
    "url": "http://localhost:5000/stage1"
  }'
```

## Best Practices

1. **Start Small:** Test stages 1-3 first to verify setup
2. **Monitor Logs:** Watch HF endpoint logs for errors
3. **Sequential Testing:** Don't run parallel tests (rate limits)
4. **Wait Between Tests:** 5-10 second delays prevent quota issues
5. **Save Results:** Keep JSON reports for comparison

## Next Steps

After successful testing:
1. Review failed stages and debug
2. Optimize for slower stages
3. Document any stage-specific issues
4. Share results for evaluation

## Support

If you encounter issues:
1. Check HF endpoint logs: https://huggingface.co/spaces/Karthikeyan414/API-ENDPOINT-QUIZ-SOLVER/logs
2. Verify custom quiz server is running
3. Check `quiz_solver.log` for detailed errors
