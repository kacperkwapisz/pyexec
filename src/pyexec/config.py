from pydantic_settings import BaseSettings
from pathlib import Path
from typing import Optional


class Settings(BaseSettings):
    API_KEY: str
    API_KEY_NAME: str = "X-API-Key"
    BASE_SESSION_PATH: Path = "/tmp/sessions"

    # Optional Redis settings
    REDIS_URL: Optional[str] = None

    # Optional S3 settings
    S3_BUCKET_NAME: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: Optional[str] = None
    BASE_IMAGE_NAME: str = "pyexec-base"

    class Config:
        env_file = ".env"


settings = Settings()
