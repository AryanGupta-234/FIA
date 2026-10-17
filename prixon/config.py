from pydantic_settings import BaseSettings, SettingsConfigDict


class PrixonSettings(BaseSettings):
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_timeout_seconds: float = 20.0
    agent_max_plan_steps: int = 8
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="PRIXON_")
