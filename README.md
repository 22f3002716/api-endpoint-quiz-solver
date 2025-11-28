title: API ENDPOINT QUIZ SOLVER
emoji: ⚡
colorFrom: indigo
colorTo: green
sdk: docker
pinned: false
license: mit
short_description: TDS Project2

 # 🎯 API Endpoint Quiz Solver

An intelligent, automated quiz-solving system powered by Google's Gemini AI that navigates multi-stage web quizzes, analyzes questions, processes data, and submits answers with high accuracy.

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Project Structure](#project-structure)
- [Testing](#testing)
- [Performance Metrics](#performance-metrics)
- [API Documentation](#api-documentation)
- [Advanced Features](#advanced-features)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## 🌟 Overview

This project implements an AI-powered quiz solver that can autonomously complete complex multi-stage quizzes by:
- Scraping and understanding quiz questions
- Processing various data formats (CSV, JSON, tables, audio, images)
- Performing calculations, validations, and data transformations
- Applying smart answer formatting with automatic padding detection
- Managing API rate limits and timeouts efficiently

**Achievement**: 100% success rate across 32 diverse quiz stages with complex conditional logic, data validation, and multi-step calculations. Successfully handles multimodal inputs including canvas rendering, audio transcription, and large dataset analysis.

## ✨ Key Features

### 🤖 Intelligent Question Processing
- **Multimodal Support**: Handles text, CSV data, audio files, images, canvas rendering, and base64 encoded content
- **Canvas Vision**: Captures rendered canvas elements as images and analyzes using vision-enabled LLM
- **Deterministic Solving**: Attempts computational solutions for canvas-based alphametic puzzles before LLM call
- **Adaptive Complexity Detection**: Automatically adjusts token limits based on question complexity
- **Smart HTML Cleaning**: Preserves essential information while removing noise
- **Format Padding Detection**: Automatically applies zero-padding based on placeholder patterns (e.g., `MATRIX-???` → `MATRIX-094`)

### 🚀 Performance Optimization
- **Per-Stage Time Budgets**: Independent 120-second timeout per stage
- **Rate Limiting**: Intelligent API rate management (RPM/TPM/RPD limits)
- **Retry Logic**: Exponential backoff with error context propagation
- **Parallel Context Gathering**: Efficient batch processing of independent operations

### 🧠 Advanced AI Capabilities
- **Structured Output**: JSON-formatted responses with reasoning traces
- **Error Feedback Loop**: Learns from failed attempts within the same stage
- **Enhanced Prompts**: Task-specific instructions (extract, calculate, transcribe, apply logic)
- **Complexity Tiers**: 
  - Simple (512 tokens) - Basic extraction
  - Medium (1536 tokens) - Moderate calculations
  - Complex (2048 tokens) - Large datasets, validation, branching logic
  - Very Complex (4096 tokens) - Audio transcription + CSV filtering, canvas vision with computation

### 🛡️ Robustness
- **Comprehensive Error Handling**: Graceful degradation on failures
- **Fallback Mechanisms**: Multiple strategies for URL extraction, format detection
- **Logging**: Detailed execution traces with emoji indicators for easy monitoring

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Application                       │
│                         (main.py)                            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ├──► Solver Core (solver.py)
                   │    ├─ Playwright-based web scraping
                   │    ├─ HTML content cleaning
                   │    ├─ Stage sequencing & navigation
                   │    └─ Answer formatting & submission
                   │
                   ├──► LLM Service (llm_service.py)
                   │    ├─ Gemini AI integration
                   │    ├─ Complexity detection
                   │    ├─ Structured output generation
                   │    └─ Token limit management
                   │
                   ├──► Rate Limiter (rate_limiter.py)
                   │    ├─ RPM/TPM/RPD tracking
                   │    ├─ Sliding window algorithm
                   │    └─ Automatic throttling
                   │
                   └──► Utilities
                        ├─ Logger (logger.py)
                        ├─ Models (models.py)
                        └─ Custom Quiz Server (custom_quiz_server.py)
```

## 📦 Installation

### Prerequisites
- Python 3.9 or higher
- Google Gemini API key
- Internet connection

### Steps

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd api-endpoint-quiz-solver
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers**
   ```bash
   playwright install
   ```

5. **Configure environment variables**
   ```bash
   # Create .env file
   echo GEMINI_API_KEY=your_api_key_here > .env
   ```

## ⚙️ Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Required
GEMINI_API_KEY=your_gemini_api_key_here
MASTER_QUIZ_SECRET=your_secret_key_here

# Optional (with defaults)
MAX_STAGE_TIME_SECONDS=120
MAX_ATTEMPTS=3
LOG_LEVEL=INFO
USE_MOCK_LLM=false
```

### API Rate Limits

Configure in `rate_limiter.py`:

```python
# Free Tier (Default)
RPM_LIMIT = 10    # Requests per minute
TPM_LIMIT = 1_000_000  # Tokens per minute
RPD_LIMIT = 1500  # Requests per day

# Tier 1 (Paid)
# RPM_LIMIT = 1000
# TPM_LIMIT = 4_000_000
# RPD_LIMIT = 10000
```

## 🚀 Usage

### Running the Main Application

```bash
# Start the FastAPI server
python main.py

# Server runs on http://localhost:8000
```

### API Request Example

```python
import requests

payload = {
    "email": "your_email@example.com",
    "secret": "your_secret_key",
    "url": "https://quiz-server.com/demo"
}

response = requests.post(
    "http://localhost:8000/quiz-task",
    json=payload,
    timeout=300
)

print(response.json())
```

### Testing with Custom Quiz Server

```bash
# Terminal 1: Start custom quiz server
python custom_quiz_server.py

# Terminal 2: Run test suite
python test_runner.py --start 1 --end 32
```

### Testing Specific Stages

```bash
# Test stages 20-25
python test_runner.py --start 20 --end 25

# Test single stage
python test_runner.py --start 23 --end 23
```

## 📁 Project Structure

```
api-endpoint-quiz-solver/
│
├── 🔷 Core Application Files (Required for Deployment)
│   ├── main.py                      # FastAPI application entry point
│   ├── solver.py                    # Core quiz-solving logic
│   ├── llm_service.py              # Gemini AI integration
│   ├── rate_limiter.py             # API rate limiting
│   ├── logger.py                   # Logging configuration
│   ├── models.py                   # Pydantic data models
│   └── requirements.txt            # Python dependencies
│
├── 🧪 Testing & Development (Optional - not needed for deployment)
│   ├── llm_service_mock.py         # Mock LLM for testing without API costs
│   ├── custom_quiz_server.py       # Local test server (32 stages)
│   ├── test_runner.py              # Automated test suite
│   └── test_quiz_solver.py         # Unit tests
│
├── ⚙️ Configuration
│   ├── .env.example                # Environment variables template
│   ├── .env                        # Your environment variables (create this)
│   ├── .gitignore                  # Git ignore rules
│   └── LICENSE                     # MIT License
│
└── 📖 README.md                    # This documentation
```

**Note**: 
- This project uses a **flat structure** for simplicity and ease of deployment
- Log files (`*.log`), virtual environment (`venv/`), and Python cache (`__pycache__/`) are automatically excluded via `.gitignore`
- The `.env` file contains secrets and is never committed to git

## 🧪 Testing

### Run All Tests

```bash
pytest test_quiz_solver.py -v
```

### Manual Testing

1. **Demo Quiz (3 stages)**
   ```bash
   python test_runner.py --url https://tds-llm-analysis.s-anand.net/demo
   ```

2. **Custom Quiz (32 stages)**
   ```bash
   # Start server first
   python custom_quiz_server.py
   
   # Run tests
   python test_runner.py --start 1 --end 32
   ```

### Test Coverage

The custom quiz server includes 32 diverse test cases:

| Stage Range | Category | Examples |
|------------|----------|----------|
| 1-8 | Basic Extraction | Web scraping, API keys, audio data, word counting |
| 9-16 | Data Processing | Base64 decoding, CSV aggregation, JSON parsing, calculations |
| 17-20 | Validation & Regex | Pattern matching, date calculations, percentages |
| 21-24 | Complex Logic | Data validation, conditional branching, multi-source fusion |
| 25-32 | Advanced Operations | Cryptography, matrix operations, pivot tables, nested JSON |

## 📊 Performance Metrics

### Success Rates

| Quiz Type | Stages | Success Rate | Avg Time/Stage |
|-----------|--------|--------------|----------------|
| Demo Quiz | 3 | 100% | ~10s |
| Custom Quiz | 32 | 100% (32/32) | ~6s |

### Complexity Distribution

| Tier | Token Limit | Usage | Success Rate |
|------|-------------|-------|--------------|-------------|
| Simple | 512 | Basic text extraction | 100% |
| Medium | 1536 | Calculations, data processing | 100% |
| Complex | 2048 | Large datasets, validation | 100% |
| Very Complex | 4096 | Audio+CSV, canvas vision | 100% |

### Key Improvements

- ✅ **Canvas Vision**: Captures canvas as image → multimodal LLM analysis
- ✅ **Deterministic Solving**: SHA1-based computation for alphametic puzzles
- ✅ **Audio Stage**: Enhanced prompts with filter-then-sum logic → 100% accuracy
- ✅ **Token Optimization**: Balanced 4096 tokens for audio+CSV (no timeouts)
- ✅ **Enhanced Prompts**: "Analyze and determine" with explicit task categories
- ✅ **Fallback Parser**: Extracts JSON from partial responses on MAX_TOKENS errors

## 📚 API Documentation

### POST /quiz-task

**Request Body:**
```json
{
  "email": "string (required)",
  "secret": "string (required)",
  "url": "string (required)"
}
```

**Response (Success):**
```json
{
  "status": "success",
  "final_answer": "STAGE32-ANSWER",
  "stages_completed": 32,
  "total_time": 245.67,
  "message": "Quiz completed successfully!"
}
```

**Response (Error):**
```json
{
  "status": "error",
  "error": "Error message",
  "stage_failed": "http://example.com/stage15",
  "stages_completed": 14
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

## 🔧 Advanced Features

### Smart Format Padding

Automatically detects and applies correct number formatting:

```python
# Input placeholder: "MATRIX-???"
# LLM answer: "MATRIX-94"
# Auto-corrected: "MATRIX-094"

# Strategies:
# 1. Leading zero examples (REGEX-008)
# 2. Placeholder patterns (MATRIX-???, DATE-XXX)
# 3. Format hints (e.g., PARSE-137)
```

### Adaptive Complexity Detection

```python
# Detects:
- Canvas elements → captures as PNG image for vision analysis
- Audio files + CSV data → VERY_COMPLEX tier (4096 tokens)
- Large validation tables (>800 chars) → COMPLEX tier
- Complex conditional logic (bonus calculations) → COMPLEX tier
- Multi-dimensional data aggregation → COMPLEX tier

# Auto-selects appropriate token limits
# Attempts deterministic solving for canvas alphametic puzzles
```

### Error Recovery

```python
# Features:
- Learns from previous attempt errors
- Exponential backoff for API overload
- Fallback URL extraction
- Emergency mode for low time budgets
```

## 🐛 Troubleshooting

### Common Issues

**1. Gemini API Key Error**
```
Error: GOOGLE_GENAI_API_KEY environment variable is not set
Solution: Set GEMINI_API_KEY in .env file
```

**2. Rate Limit Exceeded**
```
Error: 429 Too Many Requests
Solution: Automatic retry with exponential backoff (already implemented)
```

**3. Playwright Installation**
```
Error: Playwright browsers not found
Solution: Run `playwright install`
```

**4. Timeout Errors**
```
Error: Stage timeout after 120s
Solution: Increase MAX_STAGE_TIME_SECONDS in .env
```

### Debugging

Enable detailed logging:

```python
# In logger.py
LOG_LEVEL = logging.DEBUG

# View logs
tail -f quiz_solver.log
```

## 🤝 Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- Follow PEP 8 guidelines
- Use type hints
- Add docstrings to functions
- Include unit tests for new features

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **Google Gemini AI**: Powerful LLM for intelligent question answering
- **Playwright**: Robust browser automation
- **FastAPI**: Modern web framework for APIs
- **IIT Madras**: Project inspiration and requirements

## 📞 Contact

For questions or support:
- **Email**: 22f3002716@ds.study.iitm.ac.in
- **GitHub Issues**: Create an issue in this repository

---

**Built with ❤️ for IIT Madras BS Data Science Program (Project 2)**

Last Updated: November 28, 2025
