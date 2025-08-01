from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # Database Configuration
    database_url: str = os.getenv("DATABASE_URL")
    
    # LLM API Keys
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
    google_api_key: Optional[str] = os.getenv("GOOGLE_API_KEY")
    deepseek_api_key: Optional[str] = os.getenv("DEEPSEEK_API_KEY")
    
    # Perplexity API
    perplexity_api_key: Optional[str] 
    
    # MinIO Configuration
    minio_endpoint: str
    minio_access_key: str = Field(alias="MINIO_ROOT_USER")
    minio_secret_key: str = Field(alias="MINIO_ROOT_PASSWORD")
    minio_bucket_name: str
    minio_secure: bool = Field(alias="MINIO_USE_SSL")
    minio_region: Optional[str] = None
    
    # Application Settings
    app_env: str = "development"
    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    
    # CrewAI Settings
    crewai_telemetry_opt_out: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings() 