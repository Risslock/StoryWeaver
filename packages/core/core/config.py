from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# packages/core/core/config.py → go up 4 levels to reach repo root
_repo_root = Path(__file__).resolve().parent.parent.parent.parent
_default_db = "sqlite+aiosqlite:///" + str(_repo_root / "storyweaver.db").replace("\\", "/")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = _default_db
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    image_provider: str = "comfyui"
    hf_api_key: str = ""
    comfyui_url: str = "http://localhost:8188"
    embedding_provider: str = "ollama"
    max_twin_turns: int = 20


settings = Settings()