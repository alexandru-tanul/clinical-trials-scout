from pydantic import computed_field
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_ignore_empty=True
    )
    """Load .env file if it exists. Ignore fields not defined in this model."""

    # Database (PostgreSQL only)
    # --------------------
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "chatbot"

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        """Build PostgreSQL database URL."""
        return f"postgres://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @computed_field
    @property
    def TORTOISE_ORM(self) -> dict:
        """TortoiseORM configuration."""
        return {
            "connections": {
                "default": {
                    "engine": "tortoise.backends.asyncpg",
                    "credentials": {
                        "host": self.POSTGRES_HOST,
                        "port": self.POSTGRES_PORT,
                        "user": self.POSTGRES_USER,
                        "password": self.POSTGRES_PASSWORD,
                        "database": self.POSTGRES_DB,
                        "minsize": 5,  # Minimum pool size
                        "maxsize": 20,  # Maximum pool size
                    }
                }
            },
            "apps": {
                "models": {
                    "models": ["app.models"],
                    "default_connection": "default",
                }
            },
        }

    # Directories
    # --------------------
    BASE_DIR: Path = Path(__file__).resolve().parent

    @computed_field
    @property
    def TEMPLATES_DIR(self) -> Path:
        return self.BASE_DIR / "templates"

    # LLM Configuration (using LiteLLM)
    # --------------------
    MODEL: str = "gpt-5-nano"
    SYNTHESIS_MODEL: str = "gpt-4o-mini"

    # Session
    # --------------------
    SECRET_KEY: str = "your-secret-key-here"  # Should be set in .env

    # App Settings
    # --------------------
    DEBUG: bool = True


settings = Settings()  # type: ignore
