from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "School CRM API"
    environment: str = "development"
    database_url: str = "sqlite:///./schoolcrm.db"
    migration_database_url: str | None = None
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 120
    auth_required: bool = False
    bootstrap_secret: str | None = None
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    frontend_url: str = "http://localhost:8080"
    public_intake_window_minutes: int = 10
    public_intake_ip_limit: int = 20
    public_intake_phone_limit: int = 5
    auth_login_window_minutes: int = 15
    auth_login_ip_limit: int = 30
    auth_login_email_limit: int = 10
    read_only_mode: bool = False
    strict_rbac: bool = False
    transactional_email_enabled: bool = False
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str | None = None
    smtp_starttls: bool = True

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
            if self.migration_database_url and not self.migration_database_url.startswith("postgresql"):
                raise ValueError("Production MIGRATION_DATABASE_URL must use PostgreSQL")
            if not self.bootstrap_secret or len(self.bootstrap_secret) < 16:
                raise ValueError("Production BOOTSTRAP_SECRET must contain at least 16 characters")
            origins = [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]
            if not origins or "*" in origins:
                raise ValueError("Production CORS_ORIGINS must explicitly list trusted HTTPS origins")
            if any(not origin.startswith("https://") for origin in origins):
                raise ValueError("Production CORS_ORIGINS must use HTTPS")
            if not self.frontend_url.startswith("https://"):
                raise ValueError("Production FRONTEND_URL must use HTTPS")
            if self.access_token_minutes > 240:
                raise ValueError("Production access tokens must not live longer than 4 hours")
            if self.transactional_email_enabled:
                missing = [
                    name for name, value in {
                        "SMTP_HOST": self.smtp_host,
                        "SMTP_USERNAME": self.smtp_username,
                        "SMTP_PASSWORD": self.smtp_password,
                        "SMTP_FROM_EMAIL": self.smtp_from_email,
                    }.items() if not value
                ]
                if missing:
                    raise ValueError(f"Transactional email enabled but missing: {', '.join(missing)}")
            self.strict_rbac = True
        return self


settings = Settings()
