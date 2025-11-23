import os
from pathlib import Path

class Config:
    BASE_DIR = Path(__file__).parent.parent
    DATA_DIR = BASE_DIR / "data"
    MODELS_DIR = BASE_DIR / "models"
    FRONTEND_DIR = BASE_DIR.parent / "frontend"
    
    DB_PATH = DATA_DIR / "aura.db"
    CHROMA_PATH = DATA_DIR / "chroma_db"
    
    # Correct model name: Phi-3-mini-4k-instruct-q4.gguf
    MODEL_FILENAME = "Phi-3-mini-4k-instruct-q4.gguf"
    MODEL_PATH = MODELS_DIR / MODEL_FILENAME
    EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    PORT = int(os.getenv("PORT", 8000))
    USE_GPU = os.getenv("USE_GPU", "false").lower() == "true"
    
    def init_dirs(self):
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.MODELS_DIR.mkdir(parents=True, exist_ok=True)
        self.CHROMA_PATH.mkdir(parents=True, exist_ok=True)

config = Config()
config.init_dirs()
