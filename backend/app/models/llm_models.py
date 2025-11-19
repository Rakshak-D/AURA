import ctransformers
from sentence_transformers import SentenceTransformer
from config import config
import torch

class LLM:
    def __init__(self):
        self.llm = ctransformers.AutoModel.from_pretrained(
            config.MODEL_PATH, model_type="qwen", gpu_layers=0  # CPU
        )
        self.embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)

    def generate(self, prompt: str, max_tokens: int = 200) -> str:
        return self.llm(prompt, max_tokens=max_tokens, temperature=0.7)

    def embed(self, text: str) -> list[float]:
        return self.embedding_model.encode(text).tolist()

llm = LLM()