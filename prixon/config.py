from pydantic_settings import BaseSettings, SettingsConfigDict


class PrixonSettings(BaseSettings):
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b-instruct"
    ollama_timeout_seconds: float = 60.0
    ollama_keep_alive: str = "10m"
    agent_max_plan_steps: int = 8
    agent_wall_clock_seconds: float = 60.0
    agent_step_timeout_seconds: float = 12.0
    agent_max_replans: int = 2
    agent_max_model_tokens: int = 1024
    agent_max_actions_per_minute: int = 20
    agent_loop_poll_seconds: float = 2.0
    semantic_enabled: bool = False
    agent_autostart: bool = True
    voice_kill_enabled: bool = False
    voice_model_path: str = ""
    voice_capture_seconds: float = 5.0
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="PRIXON_")
