from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_BUCKET: str = "cloudvault"
    TEST_SUPABASE_BUCKET: str = "cloudvault-test"
    SECRET_KEY: str
    ACCESS_TOKEN_MINUTES: int = 60
    MAX_UPLOAD_BYTES: int = 100_000_000
    DEFAULT_QUOTA_BYTES: int = 2_000_000_000
    FRONTEND_ORIGIN: str = "http://localhost:5173"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()