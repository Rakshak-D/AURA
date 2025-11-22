from llama_cpp import Llama
from sentence_transformers import SentenceTransformer
from ..config import config
import os

class LLM:
    def __init__(self):
        self.llm = None
        self.embedding_model = None
        
        # Load LLM
        print(f"🔍 Checking model path: {config.MODEL_PATH.resolve()}")
        if not config.MODEL_PATH.exists():
            print(f"⚠️ CRITICAL: Model not found at {config.MODEL_PATH}")
            print("   Run 'python backend/download_models.py' to fix this.")
        else:
            try:
                print(f"🚀 Loading LLM from {config.MODEL_PATH}...")
                self.llm = Llama(
                    model_path=str(config.MODEL_PATH),
                    n_ctx=4096,
                    n_gpu_layers=-1 if config.USE_GPU else 0,
                    verbose=False
                )
                print("✅ LLM Loaded")
            except Exception as e:
                print(f"❌ Error loading LLM: {e}")

        # Load Embeddings
        try:
            print("🧠 Loading Embeddings...")
            self.embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
            print("✅ Embeddings Loaded")
        except Exception as e:
            print(f"❌ Error loading Embeddings: {e}")

    def generate(self, prompt: str, max_tokens: int = 500) -> str:
        if not self.llm:
            return "Error: AI Model file is missing. Please check server logs."
        
        try:
            output = self.llm(
                prompt,
                max_tokens=max_tokens,
                stop=["User:", "\nUser", "<|im_end|>"],
                echo=False,
                temperature=0.7
            )
            return output['choices'][0]['text'].strip()
        except Exception as e:
            print(f"Generation Error: {e}")
            return "I encountered an error generating a response."

    def embed(self, text: str) -> list[float]:
        if not self.embedding_model:
            return [0.0] * 384 # Return dummy vector if failed
        return self.embedding_model.encode(text).tolist()

# Initialize singleton
llm = LLM()