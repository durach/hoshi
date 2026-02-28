from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-5-20250929"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    tokens_file: str = "tokens.json"

    model_config = {"env_file": ".env"}
