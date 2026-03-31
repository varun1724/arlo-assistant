from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://arlo_assistant:arlo_assistant_dev@db:5432/arlo_assistant"

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8002
    api_key: str = "arlo-assistant-dev-key"

    # Claude Code CLI
    claude_code_oauth_token: str = ""
    claude_command: str = "claude"
    claude_model: str = "sonnet"
    claude_timeout_seconds: int = 120

    # Arlo Runtime
    arlo_runtime_url: str = "http://localhost:8000"
    arlo_runtime_token: str = "change-me-to-a-real-secret"

    # Weather
    weather_api_key: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
