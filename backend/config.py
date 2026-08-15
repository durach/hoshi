from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    provider: str = "openai"
    model: str = "gpt-5.6-terra"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    tokens_file: str = "tokens.json"

    model_config = {"env_file": ".env"}
