from pathlib import Path
from typing import Literal
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAGVANTA_", env_file=".env", extra="ignore")
    data_dir: Path = Path(".runtime")
    provider: Literal["extractive", "gemini", "ollama"] = "extractive"
    model: str = "extractive-v1"
    retrieval: Literal["lexical", "semantic"] = "lexical"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_revision: str = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"
    gemini_api_key: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    api_token: str = ""
    actor_id: str = "local-operator"
    max_file_bytes: int = Field(10 * 1024 * 1024, ge=1, le=10 * 1024 * 1024)
    max_pages: int = Field(50, ge=1, le=50)
    max_files: int = Field(100, ge=1, le=100)
    max_text_chars: int = Field(250000, ge=1, le=250000)
    chunk_size: int = Field(800, ge=200, le=900)
    chunk_overlap: int = Field(100, ge=0, lt=200)
    timeout: float = Field(30, gt=0, le=30)
    retries: int = Field(2, ge=0, le=2)
    max_output_tokens: int = Field(1024, ge=1, le=1024)
    requests_per_minute: int = Field(30, ge=1, le=30)
    retention_days: int = Field(30, ge=1, le=30)
    deployment: Literal["local", "hosted"] = "local"
    public_url: str = ""
    session_hours: int = Field(8, ge=1, le=24)
    max_collections: int = Field(10, ge=1, le=100)
    max_user_text_chars: int = Field(5000000, ge=1000, le=25000000)
    max_experiment_runs: int = Field(100, ge=1, le=500)
    daily_user_model_calls: int = Field(200, ge=1, le=10000)
    daily_global_model_calls: int = Field(1000, ge=1, le=50000)
    pdf_memory_mb: int = Field(512, ge=128, le=1024)

    @model_validator(mode="after")
    def validate_hosted(self):
        from urllib.parse import urlparse
        if self.deployment == "hosted":
            url = urlparse(self.public_url)
            if url.scheme != "https" or not url.hostname or url.path not in ("", "/") or url.query or url.fragment or url.username is not None or url.password is not None:
                raise ValueError("Hosted mode requires an HTTPS public_url containing only the origin")
            if self.api_token:
                raise ValueError("Hosted mode uses individual accounts, not the local shared token")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap must be smaller than chunk size")
        return self
