from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_BUCKET: str = "cloudvault"
    TEST_SUPABASE_BUCKET: str = "cloudvault-test"
    SECRET_KEY: str
    ACCESS_TOKEN_MINUTES: int = 60
    MAX_UPLOAD_BYTES: int = 500_000_000
    STORAGE_UPLOAD_TIMEOUT_SECONDS: float = 600.0
    DEFAULT_QUOTA_BYTES: int = 2_000_000_000
    FRONTEND_ORIGIN: str = "http://localhost:4200"
    STORAGE_PROVIDER: str = "supabase"
    B2_ENDPOINT: str = ""
    B2_REGION: str = "us-west-004"
    B2_BUCKET: str = ""
    B2_KEY_ID: str = ""
    B2_APPLICATION_KEY: str = ""
    B2_MULTIPART_THRESHOLD_BYTES: int = 8_388_608
    B2_MULTIPART_CHUNK_BYTES: int = 32_000_000
    B2_MAX_CONCURRENCY: int = 8
    DIRECT_UPLOAD_SESSION_TTL_MINUTES: int = 120

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()