import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Config:
    FRONTEND_DIR = BASE_DIR / "frontend"
    DATA_DIR = BASE_DIR / "data"
    MODELS_DIR = BASE_DIR / "models"
    
    DB_PATH = DATA_DIR / "db.sqlite"
    CHROMA_PATH = DATA_DIR / "chroma"
    
    MODEL_FILENAME = os.getenv("MODEL_FILENAME", "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf")
    MODEL_PATH = MODELS_DIR / MODEL_FILENAME
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    
    WAKE_WORD = os.getenv("WAKE_WORD", "hey aura")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    PORT = int(os.getenv("PORT", 8000))
    USE_GPU = os.getenv("USE_GPU", "false").lower() == "true"
    
    def init_dirs(self):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self.CHROMA_PATH.mkdir(parents=True, exist_ok=True)

config = Config()
config.init_dirs()
