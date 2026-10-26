from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str
    # Every request except GET /health must send this as X-API-Key.
    API_KEY: str = Field(min_length=1)


settings = Settings()
