import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Core
    IDEA_MODE: int = 1
    
    # LLM Settings
    LLM_MODEL: str = "google/gemini-3-flash-preview"
    OPENROUTER_API_KEY: str = ""
    
    # Discovery Settings
    IDEA_LANGS: str = "en,ru,es"
    IDEA_OUTPUT_LANG: str = "ru"
    SOURCES: str = "x,reddit,hn,producthunt,indiehackers"
    
    # Filtering & Thresholds
    IDEA_MIN_SCORE: int = 70
    IDEA_MAX_PER_DAY: int = 20      # How many top ideas to send to Telegram
    IDEA_TARGET_RAW: int = 60       # Target number of raw ideas before picking top N
    IDEA_MIN_EVIDENCE_DENSITY: int = 3
    
    # Memory & Dedup Settings
    IDEA_MEMORY_DAYS: int = 60
    IDEA_ALLOW_REFRAMED: int = 1
    IDEA_REFRAMED_MAX_PER_DAY: int = 3
    IDEA_GROWING_THRESHOLD: float = 0.3
    
    # Content Logic
    IDEA_ANTITHESIS: int = 1
    
    class Config:
        env_file = ".env"
        extra = "ignore"  # Ignore other settings not relevant to radar

# Global singleton
config = Settings()

# Validation block
if not config.OPENROUTER_API_KEY:
    # Try looking for it in the environment just in case it wasn't picked up by pydantic
    config.OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")

def is_enabled() -> bool:
    return config.IDEA_MODE == 1
