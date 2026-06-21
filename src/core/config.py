from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ecops"
    anthropic_api_key: str = "lmstudio"
    lmstudio_base_url: str = "http://localhost:1234"
    lm_model: str = "Qwen/Qwen2.5-7B-Instruct-GGUF"
    port: int = 8002

    # Auth — override JWT_SECRET_KEY with a strong random string in production
    jwt_secret_key: str = "change-me-in-production-use-a-long-random-string"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24 hours

    # Logging — set LOG_LEVEL=DEBUG in .env to trace LM Studio requests/responses
    log_level: str = "INFO"


settings = Settings()
