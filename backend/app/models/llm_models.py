from llama_cpp import Llama
from sentence_transformers import SentenceTransformer
from ..config import config
import os

class LLM:
    def __init__(self):
        # Check if model exists
        if not os.path.exists(config.MODEL_PATH):
            raise FileNotFoundError(
                f"Model file not found at: {config.MODEL_PATH}\n"
                "Please run 'python backend/download_models.py' first."
            )

        print(f"Loading LLM from: {config.MODEL_PATH}")
        # Initialize Llama model (llama-cpp-python supports Qwen2)
        self.llm = Llama(
            model_path=config.MODEL_PATH,
            n_ctx=2048,          # Context window size
            n_gpu_layers=0,      # 0 = CPU only. Change to -1 if you have a GPU installed.
            verbose=False
        )
        
        print("Loading Embedding Model...")
        self.embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)

    def generate(self, prompt: str, max_tokens: int = 200) -> str:
        # llama_cpp returns a dictionary; we extract the text
        output = self.llm(
            prompt, 
            max_tokens=max_tokens, 
            stop=["User:", "\nUser", "<|im_end|>"], # Stop tokens to prevent hallucination
            echo=False
        )
        return output['choices'][0]['text'].strip()

    def embed(self, text: str) -> list[float]:
        return self.embedding_model.encode(text).tolist()

# Initialize the singleton instance
llm = LLM()