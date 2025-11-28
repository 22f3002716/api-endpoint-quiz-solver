import logging
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
LOG_FILE = os.getenv('LOG_FILE_PATH', '/home/user/app/quiz_solver.log')

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO, # Set logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        # Console Handler (for quick viewing in terminal)
        logging.StreamHandler(),
        # File Handler (for permanent record)
        logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    ]
)

# Export a logger instance for the main application
quiz_logger = logging.getLogger("QUIZ_TASK_GATEWAY")