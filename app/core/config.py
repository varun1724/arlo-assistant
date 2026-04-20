from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://arlo_assistant:arlo_assistant_dev@db:5432/arlo_assistant"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8002
    api_key: str = "arlo-assistant-dev-key"  # legacy dev key, still accepted

    # JWT Auth
    jwt_secret: str = "dev-jwt-secret-change-in-production"
    jwt_access_expiry_minutes: int = 30
    jwt_refresh_expiry_days: int = 7

    # Claude Code CLI
    claude_code_oauth_token: str = ""
    claude_command: str = "claude"
    claude_model: str = "sonnet"
    claude_timeout_seconds: int = 120

    # Arlo Runtime
    arlo_runtime_url: str = "http://localhost:8000"
    arlo_runtime_token: str = "change-me-to-a-real-secret"

    # Environment
    environment: str = "development"  # development, staging, production
    log_level: str = "INFO"
    cors_origins: str = "*"  # comma-separated origins, or * for all

    # User timezone (IANA name, e.g. America/Los_Angeles)
    user_timezone: str = "America/Los_Angeles"

    # Weather
    weather_api_key: str = ""
    weather_location: str = "San Francisco,US"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
