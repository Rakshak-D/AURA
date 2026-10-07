"""Typed, side-effect-free application configuration."""

import logging
from pathlib import Path

from pydantic import Field, field_validator, model_validator
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
    embedding_model_path_override: Path | None = Field(default=None, validation_alias="EMBEDDING_MODEL_PATH")

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
    auth_secret_key: str = Field(default="dev-only-change-me", validation_alias="AUTH_SECRET_KEY")
    auth_bootstrap_token: str | None = Field(default=None, validation_alias="AUTH_BOOTSTRAP_TOKEN")
    access_token_expire_minutes: int = Field(default=30, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    allowed_origins: str = Field(
        default="http://127.0.0.1:8000,http://localhost:8000",
        validation_alias="ALLOWED_ORIGINS",
    )

    max_upload_size: int = 50 * 1024 * 1024
    allowed_extensions: set[str] = {".pdf", ".txt", ".docx", ".md"}
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_top_k: int = 3
    reminder_scheduler_enabled: bool = Field(default=True, validation_alias="REMINDER_SCHEDULER_ENABLED")
    reminder_poll_interval_seconds: int = Field(default=30, validation_alias="REMINDER_POLL_INTERVAL_SECONDS")
    reminder_max_attempts: int = Field(default=3, validation_alias="REMINDER_MAX_ATTEMPTS")
    reminder_processing_timeout_seconds: int = Field(default=300, validation_alias="REMINDER_PROCESSING_TIMEOUT_SECONDS")
    reminder_retry_delay_seconds: int = Field(default=60, validation_alias="REMINDER_RETRY_DELAY_SECONDS")
    reminder_delivery_timeout_seconds: float = Field(default=5.0, validation_alias="REMINDER_DELIVERY_TIMEOUT_SECONDS")
    websocket_max_message_bytes: int = Field(default=4096, validation_alias="WEBSOCKET_MAX_MESSAGE_BYTES")
    websocket_heartbeat_interval_seconds: int = Field(default=30, validation_alias="WEBSOCKET_HEARTBEAT_INTERVAL_SECONDS")
    websocket_outbound_queue_size: int = Field(default=32, validation_alias="WEBSOCKET_OUTBOUND_QUEUE_SIZE")

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"development", "test", "production"}:
            raise ValueError("ENVIRONMENT must be development, test, or production")
        return value

    @field_validator("model_filename")
    @classmethod
    def validate_model_filename(cls, value: str) -> str:
        if not value or value in {".", ".."} or Path(value).name != value:
            raise ValueError("MODEL_FILENAME must be a safe filename, not a path")
        if "/" in value or "\\" in value:
            raise ValueError("MODEL_FILENAME must not contain path separators")
        return value

    @field_validator("n_gpu_layers")
    @classmethod
    def validate_gpu_layers(cls, value: int) -> int:
        if value < 0:
            raise ValueError("N_GPU_LAYERS cannot be negative")
        return value

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if not 1 <= value <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        return value

    @field_validator(
        "llm_context_window", "llm_max_tokens", "max_upload_size", "rag_chunk_size", "rag_top_k",
        "access_token_expire_minutes",
        "reminder_poll_interval_seconds", "reminder_max_attempts",
        "reminder_processing_timeout_seconds", "reminder_retry_delay_seconds",
        "reminder_delivery_timeout_seconds",
        "websocket_max_message_bytes", "websocket_heartbeat_interval_seconds",
        "websocket_outbound_queue_size",
    )
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

    @model_validator(mode="after")
    def validate_combinations(self) -> "Settings":
        if self.llm_max_tokens > self.llm_context_window:
            raise ValueError("LLM_MAX_TOKENS cannot exceed CONTEXT_WINDOW")
        if self.rag_chunk_overlap >= self.rag_chunk_size:
            raise ValueError("RAG_CHUNK_OVERLAP must be smaller than RAG_CHUNK_SIZE")
        if self.environment == "production":
            if self.auth_secret_key == "dev-only-change-me" or len(self.auth_secret_key) < 32:
                raise ValueError("AUTH_SECRET_KEY must be a unique value of at least 32 characters in production")
            if not self.allowed_origins.strip() or "*" in self.allowed_origins:
                raise ValueError("ALLOWED_ORIGINS must explicitly list origins in production")
        return self

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

    @property
    def manifest_path(self) -> Path:
        return self.base_dir / "backend" / "model_manifest.json"

    @property
    def embedding_cache_dir(self) -> Path:
        return self.models_dir / "embedding-cache"

    @property
    def embedding_model_path(self) -> Path:
        if self.embedding_model_path_override:
            return self.embedding_model_path_override.resolve()
        safe_name = self.embedding_model.replace("/", "--")
        return self.models_dir / "embeddings" / safe_name

    @property
    def cors_allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

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
