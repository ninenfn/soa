from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/marketplace"
    
    # JWT
    JWT_SECRET_KEY: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Rate limits
    ORDER_CREATE_COOLDOWN_MINUTES: int = 5
    ORDER_UPDATE_COOLDOWN_MINUTES: int = 2
    
    class Config:
        env_file = ".env"

settings = Settings()