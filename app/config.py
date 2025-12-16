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

    # DrugCentral Database
    # --------------------
    DRUGCENTRAL_HOST: str = "drugcentral_db"
    DRUGCENTRAL_PORT: int = 5432
    DRUGCENTRAL_USER: str = "postgres"
    DRUGCENTRAL_PASSWORD: str
    DRUGCENTRAL_DB: str = "drugcentral"

    @computed_field
    @property
    def DATABASE_URL(self) -> str:
        """Build PostgreSQL database URL."""
        return f"postgres://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    @computed_field
    @property
    def DRUGCENTRAL_DATABASE_URL(self) -> str:
        """Build DrugCentral database URL."""
        return f"postgres://{self.DRUGCENTRAL_USER}:{self.DRUGCENTRAL_PASSWORD}@{self.DRUGCENTRAL_HOST}:{self.DRUGCENTRAL_PORT}/{self.DRUGCENTRAL_DB}"

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
                },
                "drugcentral": {
                    "engine": "tortoise.backends.asyncpg",
                    "credentials": {
                        "host": self.DRUGCENTRAL_HOST,
                        "port": self.DRUGCENTRAL_PORT,
                        "user": self.DRUGCENTRAL_USER,
                        "password": self.DRUGCENTRAL_PASSWORD,
                        "database": self.DRUGCENTRAL_DB,
                        "minsize": 2,  # Minimum pool size
                        "maxsize": 10,  # Maximum pool size
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
    MODEL: str = "claude-haiku-4-5"  # For tool calling (search decision)
    SYNTHESIS_MODEL: str = "claude-haiku-4-5"  # For result synthesis (supports thinking)

    # Extended Thinking Mode (for Claude models that support it)
    # Supported models: claude-sonnet-4-5, claude-opus-4-5, etc.
    # --------------------
    ENABLE_THINKING: bool = False  # Set to True to enable extended thinking
    THINKING_BUDGET_TOKENS: int = 10000  # Tokens Claude can use for thinking (1024-32000)
    SHOW_THINKING: bool = True  # Show thinking content to users

    # Session
    # --------------------
    SECRET_KEY: str = "your-secret-key-here"  # Should be set in .env

    # App Settings
    # --------------------
    DEBUG: bool = True


settings = Settings()  # type: ignore
