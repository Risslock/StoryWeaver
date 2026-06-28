from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# packages/core/core/config.py → go up 4 levels to reach repo root
_repo_root = Path(__file__).resolve().parent.parent.parent.parent
_default_db = "sqlite+aiosqlite:///" + str(_repo_root / "data" / "storyweaver.db").replace("\\", "/")


def _resolve_sqlite_url(url: str) -> str:
    """Convert relative sqlite+aiosqlite paths to absolute using the repo root.

    Relative paths in DATABASE_URL break when the app is launched from a
    subdirectory (e.g. apps/web/). This ensures the path is always anchored
    to the repository root regardless of CWD.
    """
    prefix = "sqlite+aiosqlite:///"
    if not url.startswith(prefix):
        return url
    path_part = url[len(prefix):]
    resolved = Path(path_part)
    if not resolved.is_absolute():
        # Strip a leading "./" if present, then join against repo root
        resolved = (_repo_root / path_part.lstrip("./")).resolve()
    return prefix + str(resolved).replace("\\", "/")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_repo_root / ".env"), env_file_encoding="utf-8", extra="ignore")

    database_url: str = _default_db
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    llm_api_key: str = ""
    hf_llm_model: str = "mistralai/Mistral-7B-Instruct-v0.3"
    image_provider: str = "huggingface"
    hf_api_key: str = ""
    hf_image_model: str = "black-forest-labs/FLUX.1-schnell"
    comfyui_url: str = "http://localhost:8188"
    embedding_provider: str = "ollama"
    max_twin_turns: int = 20
    images_dir: str = str(_repo_root / "data" / "images")

    # Knowledge Q&A (RAG) settings
    knowledge_enrich_provider: str = "ollama"
    knowledge_embed_provider: str = "ollama"
    knowledge_embed_model: str = "nomic-embed-text"
    knowledge_enrich_model: str = "llama3.2"   # fast small model for chunk enrichment
    knowledge_llm_model: str = "llama3.1"      # larger model for Q&A answers
    knowledge_max_chunk_tokens: int = 800
    knowledge_chunk_overlap_tokens: int = 50
    knowledge_top_k: int = 8
    knowledge_rrf_k: int = 30
    knowledge_expansion_count: int = 3
    knowledge_enrich_batch_size: int = 5

    # Knowledge Pipeline — Chunking (legacy text/vision paths)
    knowledge_chunking_strategy: str = "agentic"
    knowledge_min_chunk_chars: int = 150
    knowledge_max_chunk_chars: int = 15000
    knowledge_agentic_batch_sections: int = 3
    knowledge_agentic_skip_tokens: int = 400
    knowledge_agentic_prose_threshold: float = 0.3
    knowledge_agentic_system_prompt: str = ""
    knowledge_agentic_user_prompt_prefix: str = ""
    knowledge_semantic_breakpoint_percentile: int = 95
    knowledge_semantic_min_chunk_tokens: int = 50

    # Knowledge Pipeline — Docling / Vision / Cleaning
    knowledge_docling_page_batch_size: int = 10
    knowledge_vision_model: str = "blaifa/Nanonets-OCR-s"
    knowledge_vision_timeout_secs: int = 120
    knowledge_vision_max_retries: int = 1
    knowledge_cleaning_frontmatter_pages: int = 10

    @model_validator(mode="after")
    def _resolve_db_path(self) -> "Settings":
        self.database_url = _resolve_sqlite_url(self.database_url)
        return self


settings = Settings()
