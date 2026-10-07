"""Lazy adapters for optional local LLM and embedding runtimes."""

import logging
import threading
from typing import Any

from ..config import config

logger = logging.getLogger(__name__)


class LLM:
    """Load optional model runtimes only when an AI feature is invoked."""

    def __init__(self) -> None:
        self.llm: Any = None
        self.embedding_model: Any = None
        self._llm_attempted = False
        self._embedding_attempted = False
        self._lock = threading.RLock()

    def _load_llm(self) -> Any:
        with self._lock:
            if self.llm is not None:
                return self.llm
            if self._llm_attempted:
                raise RuntimeError(
                    "The local LLM is unavailable. Install optional AI dependencies and provide the configured GGUF model."
                )
            self._llm_attempted = True
            if not config.model_path.exists():
                raise RuntimeError(
                    f"The configured GGUF model was not found at {config.model_path}. "
                    "Run the model setup command before using AI features."
                )
            try:
                from llama_cpp import Llama
            except ImportError as exc:
                raise RuntimeError(
                    "llama-cpp-python is not installed. Install the optional local-model dependencies."
                ) from exc
            try:
                self.llm = Llama(
                    model_path=str(config.model_path),
                    n_ctx=config.llm_context_window,
                    n_gpu_layers=config.n_gpu_layers if config.use_gpu else 0,
                    verbose=False,
                    n_threads=4,
                )
                return self.llm
            except Exception as exc:
                logger.exception("Local LLM initialization failed")
                raise RuntimeError("The configured local LLM could not be initialized.") from exc

    def _load_embeddings(self) -> Any:
        with self._lock:
            if self.embedding_model is not None:
                return self.embedding_model
            if self._embedding_attempted:
                raise RuntimeError(
                    "The embedding model is unavailable. Install optional RAG dependencies and provision the embedding model."
                )
            self._embedding_attempted = True
            if not config.embedding_model_path.is_dir():
                raise RuntimeError(
                    f"The embedding model is not provisioned at {config.embedding_model_path}. "
                    "Run the explicit embedding provisioning command before using RAG features."
                )
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is not installed. Install the optional RAG dependencies."
                ) from exc
            try:
                self.embedding_model = SentenceTransformer(
                    str(config.embedding_model_path),
                    device="cuda" if config.use_gpu else "cpu",
                )
                return self.embedding_model
            except Exception as exc:
                logger.exception("Embedding model initialization failed")
                raise RuntimeError("The configured embedding model could not be initialized.") from exc

    def generate(self, prompt: str, max_tokens: int | None = None, *, temperature: float | None = None) -> str:
        model = self._load_llm()
        output = model(
            prompt,
            max_tokens=max_tokens or config.llm_max_tokens,
            stop=["<|end|>", "<|user|>", "<|assistant|>"],
            echo=False,
            temperature=config.llm_temperature if temperature is None else temperature,
            top_p=0.8,
            repeat_penalty=1.2,
            top_k=40,
        )
        if not output or "choices" not in output:
            raise RuntimeError("The local LLM returned an invalid response.")
        response = output["choices"][0]["text"].strip()
        for stop_token in ("<|end|>", "<|user|>", "<|assistant|>"):
            if stop_token in response:
                response = response.split(stop_token)[0].strip()
        return response

    def embed(self, text: str) -> list[float]:
        model = self._load_embeddings()
        try:
            embedding = model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as exc:
            logger.exception("Embedding generation failed")
            raise RuntimeError("The embedding model failed to generate a vector.") from exc


# Constructing this object is cheap and does not load a model or access the network.
llm = LLM()
