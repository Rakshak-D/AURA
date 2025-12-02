from llama_cpp import Llama
from sentence_transformers import SentenceTransformer
from pathlib import Path
import logging
import sys

# Absolute imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.config import config

logger = logging.getLogger(__name__)

class LLM:
    def __init__(self):
        self.llm = None
        self.embedding_model = None
        self.fallback_mode = False
        
        # Load LLM
        logger.info(f"[INFO] Checking model path: {config.MODEL_PATH.resolve()}")
        
        # 1. RAM Check
        try:
            import psutil
            total_ram = psutil.virtual_memory().total / (1024 ** 3) # GB
            logger.info(f"[INFO] System RAM: {total_ram:.2f} GB")
            if total_ram < 8:
                logger.warning("[WARNING] Low RAM detected (< 8GB). Model loading might fail or be slow.")
        except ImportError:
            logger.warning("[WARNING] psutil not installed. Skipping RAM check.")
        
        if not config.MODEL_PATH.exists():
            logger.error(f"[CRITICAL] Model not found at {config.MODEL_PATH}")
            logger.error("   Run 'python backend/download_models.py' to download the model")
            self.fallback_mode = True
        else:
            # 2. Quantization Check
            model_name = config.MODEL_PATH.name.lower()
            if "q4" in model_name or "quantized" in model_name:
                logger.info(f"[OK] Quantized model detected: {model_name}")
            else:
                logger.warning(f"[WARNING] Model might not be quantized: {model_name}. Ensure it fits in RAM.")

            try:
                logger.info(f"[INFO] Loading LLM from {config.MODEL_PATH}...")
                self.llm = Llama(
                    model_path=str(config.MODEL_PATH),
                    n_ctx=config.LLM_CONTEXT_WINDOW,
                    n_gpu_layers=-1 if config.USE_GPU else 0,
                    verbose=False,
                    n_threads=4  # CPU threads
                )
                logger.info("[OK] LLM Loaded successfully")
            except Exception as e:
                logger.exception(f"[ERROR] Error loading LLM: {e}")
                self.fallback_mode = True

        # Load Embeddings
        try:
            logger.info("[INFO] Loading Embeddings model...")
            self.embedding_model = SentenceTransformer(
                config.EMBEDDING_MODEL,
                device='cuda' if config.USE_GPU else 'cpu'
            )
            logger.info("[OK] Embeddings Loaded successfully")
        except Exception as e:
            logger.exception(f"[ERROR] Error loading Embeddings: {e}")
            logger.warning("[WARNING] System will work without semantic search")

    def generate(self, prompt: str, max_tokens: int = None, *, temperature: float = None) -> str:
        """Generate text using LLM with error handling"""
        if max_tokens is None:
            max_tokens = config.LLM_MAX_TOKENS
        if temperature is None:
            temperature = config.LLM_TEMPERATURE
            
        if self.fallback_mode or not self.llm:
            logger.warning("[WARNING] Running in offline mode - model not available")
            return ("[WARNING] AURA is running in offline mode. "
                   "Please download the model using: python backend/download_models.py")
        
        try:
            output = self.llm(
                prompt,
                max_tokens=max_tokens,
                stop=["<|end|>", "<|user|>", "<|assistant|>"],
                echo=False,
                temperature=temperature,
                top_p=0.8,
                repeat_penalty=1.2,
                top_k=40
            )
            
            if not output or 'choices' not in output:
                logger.error("Invalid LLM output format")
                return "I encountered an error generating a response."
            
            response = output['choices'][0]['text'].strip()
            
            # Safety check - remove stop tokens if they leaked through
            for stop_token in ["<|end|>", "<|user|>", "<|assistant|>"]:
                if stop_token in response:
                    response = response.split(stop_token)[0].strip()
            
            return response
            
        except Exception as e:
            logger.exception(f"Generation error: {e}")
            return "I encountered an error. Please try again."

    def embed(self, text: str) -> list:
        """Generate embeddings for text"""
        if not self.embedding_model:
            logger.warning("Embedding model not available")
            return [0.0] * 384
        
        try:
            embedding = self.embedding_model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            logger.exception(f"Embedding error: {e}")
            return [0.0] * 384

# Global singleton
try:
    llm = LLM()
except Exception as e:
    logger.exception(f"Failed to initialize LLM: {e}")
    llm = LLM()  # This will trigger fallback mode