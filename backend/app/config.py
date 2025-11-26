import os
from pathlib import Path
import logging

class Config:
    # Base directories - absolute paths for Docker compatibility
    BASE_DIR = Path(__file__).resolve().parent.parent
    DATA_DIR = BASE_DIR / "data"
    MODELS_DIR = BASE_DIR / "models"
    FRONTEND_DIR = BASE_DIR.parent / "frontend"
    UPLOADS_DIR = DATA_DIR / "uploads"
    LOGS_DIR = DATA_DIR / "logs"
    
    # Database & Vector Store
    DB_PATH = DATA_DIR / "aura.db"
    CHROMA_PATH = DATA_DIR / "chroma_db"
    
    # Model Configuration
    MODEL_FILENAME = os.getenv("MODEL_FILENAME", "Phi-3-mini-4k-instruct-q4.gguf")
    MODEL_PATH = MODELS_DIR / MODEL_FILENAME
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    
    # Server Configuration
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    PORT = int(os.getenv("PORT", 8000))
    USE_GPU = os.getenv("USE_GPU", "false").lower() == "true"
    
    # Security
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-key-change-in-production")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 30
    
    # Upload Configuration
    MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
    ALLOWED_EXTENSIONS = {'.pdf', '.txt', '.docx', '.md'}
    
    # LLM Configuration
    LLM_CONTEXT_WINDOW = 2048
    LLM_MAX_TOKENS = 500
    LLM_TEMPERATURE = 0.1
    
    # RAG Configuration
    RAG_CHUNK_SIZE = 500
    RAG_CHUNK_OVERLAP = 50
    RAG_TOP_K = 3
    
    @classmethod
    def init_dirs(cls):
        """Initialize all required directories"""
        for directory in [cls.DATA_DIR, cls.MODELS_DIR, cls.CHROMA_PATH, cls.UPLOADS_DIR, cls.LOGS_DIR]:
            directory.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def setup_logging(cls):
        """Configure logging"""
        logging.basicConfig(
            level=getattr(logging, cls.LOG_LEVEL),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(cls.LOGS_DIR / 'aura.log'),
                logging.StreamHandler()
            ]
        )

config = Config()
config.init_dirs()
config.setup_logging()
logger = logging.getLogger(__name__)