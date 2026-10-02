from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "School CRM API"
    environment: str = "development"
    database_url: str = "sqlite:///./schoolcrm.db"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 720
    auth_required: bool = False
    bootstrap_secret: str | None = None
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    public_intake_window_minutes: int = 10
    public_intake_ip_limit: int = 20
    public_intake_phone_limit: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_production_settings(self):
        if self.environment.lower() == "production":
            if self.jwt_secret == "change-me-in-production" or len(self.jwt_secret) < 32:
                raise ValueError("Production JWT_SECRET must be a strong value of at least 32 characters")
            if not self.database_url.startswith("postgresql"):
                raise ValueError("Production DATABASE_URL must use PostgreSQL")
            if not self.bootstrap_secret or len(self.bootstrap_secret) < 16:
                raise ValueError("Production BOOTSTRAP_SECRET must contain at least 16 characters")
        return self


settings = Settings()
