"""Typed, side-effect-free application configuration."""

import logging
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(PROJECT_DIR / ".env"),),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    base_dir: Path = Field(default=PROJECT_DIR, validation_alias="BASE_DIR")
    data_dir: Path | None = Field(default=None, validation_alias="DATA_DIR")
    models_dir: Path | None = Field(default=None, validation_alias="MODELS_DIR")
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    db_path: Path | None = Field(default=None, validation_alias="DB_PATH")
    chroma_path: Path | None = Field(default=None, validation_alias="CHROMA_PATH")
    uploads_dir: Path | None = Field(default=None, validation_alias="UPLOADS_DIR")
    logs_dir: Path | None = Field(default=None, validation_alias="LOGS_DIR")

    model_filename: str = Field(default="phi-3-mini-4k-instruct-q4.gguf", validation_alias="MODEL_FILENAME")
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        validation_alias="EMBEDDING_MODEL",
    )
    use_gpu: bool = Field(default=False, validation_alias="USE_GPU")
    n_gpu_layers: int = Field(default=0, validation_alias="N_GPU_LAYERS")
    llm_context_window: int = Field(default=2048, validation_alias="CONTEXT_WINDOW")
    llm_max_tokens: int = Field(default=500, validation_alias="LLM_MAX_TOKENS")
    llm_temperature: float = Field(default=0.1, validation_alias="LLM_TEMPERATURE")

    host: str = Field(default="127.0.0.1", validation_alias="HOST")
    port: int = Field(default=8000, validation_alias="PORT")
    reload: bool = Field(default=False, validation_alias="RELOAD")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    wake_word: str = Field(default="hey aura", validation_alias="WAKE_WORD")
    secret_key: str = Field(default="dev-only-change-me", validation_alias="SECRET_KEY")

    max_upload_size: int = 50 * 1024 * 1024
    allowed_extensions: set[str] = {".pdf", ".txt", ".docx", ".md"}
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_top_k: int = 3

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"development", "test", "production"}:
            raise ValueError("ENVIRONMENT must be development, test, or production")
        return value

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        return value

    @field_validator("llm_context_window", "llm_max_tokens", "max_upload_size", "rag_chunk_size", "rag_top_k")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("configuration values must be positive")
        return value

    @field_validator("rag_chunk_overlap")
    @classmethod
    def validate_overlap(cls, value: int) -> int:
        if value < 0:
            raise ValueError("RAG_CHUNK_OVERLAP cannot be negative")
        return value

    @field_validator("llm_temperature")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if not 0 <= value <= 2:
            raise ValueError("LLM_TEMPERATURE must be between 0 and 2")
        return value

    def model_post_init(self, __context: object, /) -> None:
        base = self.base_dir.resolve()
        data = (self.data_dir or base / "data").resolve()
        models = (self.models_dir or base / "models").resolve()
        object.__setattr__(self, "base_dir", base)
        object.__setattr__(self, "data_dir", data)
        object.__setattr__(self, "models_dir", models)
        object.__setattr__(self, "db_path", (self.db_path or data / "aura.db").resolve())
        object.__setattr__(self, "chroma_path", (self.chroma_path or data / "chroma_db").resolve())
        object.__setattr__(self, "uploads_dir", (self.uploads_dir or data / "uploads").resolve())
        object.__setattr__(self, "logs_dir", (self.logs_dir or data / "logs").resolve())

    @property
    def model_path(self) -> Path:
        return self.models_dir / self.model_filename

    # Compatibility aliases for existing feature code. These are read-only
    # views over the typed settings and can be removed in a later migration.
    @property
    def MODEL_PATH(self) -> Path:
        return self.model_path

    @property
    def LLM_CONTEXT_WINDOW(self) -> int:
        return self.llm_context_window

    @property
    def LLM_MAX_TOKENS(self) -> int:
        return self.llm_max_tokens

    @property
    def LLM_TEMPERATURE(self) -> float:
        return self.llm_temperature

    @property
    def USE_GPU(self) -> bool:
        return self.use_gpu

    @property
    def EMBEDDING_MODEL(self) -> str:
        return self.embedding_model

    @property
    def RAG_CHUNK_SIZE(self) -> int:
        return self.rag_chunk_size

    @property
    def RAG_CHUNK_OVERLAP(self) -> int:
        return self.rag_chunk_overlap

    @property
    def RAG_TOP_K(self) -> int:
        return self.rag_top_k

    @property
    def FRONTEND_DIR(self) -> Path:
        return self.frontend_dir

    @property
    def frontend_dir(self) -> Path:
        return self.base_dir / "frontend"

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.db_path.as_posix()}"

    def init_dirs(self) -> None:
        for directory in (self.data_dir, self.models_dir, self.chroma_path, self.uploads_dir, self.logs_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def setup_logging(self) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            level=getattr(logging, self.log_level.upper(), logging.INFO),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(self.logs_dir / "aura.log"), logging.StreamHandler()],
        )


config = Settings()
logger = logging.getLogger(__name__)
