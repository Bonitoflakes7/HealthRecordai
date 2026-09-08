from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "Health Record AI"
    app_env: str = "development"
    data_dir: Path = PROJECT_ROOT / "data"
    max_upload_mb: int = 25
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    pdftoppm_cmd: str = "pdftoppm"
    tesseract_cmd: str = "tesseract"
    llm_model: str | None = None
    llm_provider: str = "google_genai"
    gemini_api_key: str | None = None
    conversation_db_path: Path | None = None
    pubmed_email: str | None = None
    auth_enabled: bool = False
    auth_secret_key: str = "change-me-in-development"
    access_token_expire_minutes: int = 60
    auth_cookie_name: str = "health_access_token"
    auth_cookie_secure: bool = False
    semantic_retrieval_enabled: bool = False
    semantic_retrieval_weight: float = 0.35
    semantic_model_name: str = "all-MiniLM-L6-v2"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
