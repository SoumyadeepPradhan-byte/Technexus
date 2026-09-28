"""
app/core/config.py  –  ALL SETTINGS IN ONE PLACE
==================================================
Values here can be overridden by putting the same name in a `.env` file
(copy .env.example → .env). That way secrets never get committed to GitHub.

Use anywhere in code:   from app.core.config import settings ; settings.DATABASE_URL
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_NAME: str = "TechNexus Telehealth Bridge"
    API_PREFIX: str = "/api/v1"                    # every endpoint starts with this

    # sqlite:///./telehealth.db = a single file in this folder. Perfect for development.
    DATABASE_URL: str = "sqlite:///./telehealth.db"

    # Used to sign login tokens. CHANGE THIS in .env before any real deployment.
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200       # 30 days - rural users can't re-login every day

    ANTHROPIC_API_KEY: str = ""                    # optional: LLM translation + richer triage advice

    # ---- Rules the problem statement cares about ----
    SUPPORTED_LANGUAGES: str = "en,hi,or"          # English, Hindi, Odia (add te, ta, bn... in .env)
    DEFAULT_LANGUAGE: str = "hi"
    RESERVATION_HOURS: int = 24                    # how long a medicine reservation is held at the pharmacy
    EMERGENCY_NUMBER: str = "108"                  # India ambulance
    LOW_BANDWIDTH_KBPS: int = 300                  # below this we recommend audio/text instead of video
    GZIP_MIN_BYTES: int = 500                      # compress every response bigger than this (low bandwidth)


settings = Settings()   # created once; import this object everywhere
