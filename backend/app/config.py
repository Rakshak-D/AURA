import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    MODEL_PATH = os.getenv("MODEL_PATH", "./models/qwen2-1.5b.gguf")
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    CHROMA_PATH = os.getenv("CHROMA_PATH", "./data/chroma")
    DB_PATH = os.getenv("DB_PATH", "./data/db.sqlite")
    WAKE_WORD = os.getenv("WAKE_WORD", "hey aura")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    PORT = int(os.getenv("PORT", 8000))

config = Config()