from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_master_key: str
    database_url: str = "sqlite:///./data.db"
    max_concurrent_jobs: int = 3
    max_image_mb: int = 12
    model_name: str = "isnet-general-use"

    class Config:
        env_file = ".env"


settings = Settings()
