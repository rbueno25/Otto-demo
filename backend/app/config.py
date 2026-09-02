import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


@dataclass
class Settings:
    odoo_url: str
    odoo_db: str
    odoo_user: str
    odoo_password: str
    ai_api_endpoint: str
    ai_api_key: str
    ai_model: str
    host: str = "0.0.0.0"
    port: int = 8000
    max_iterations: int = 10

    def is_odoo_configured(self) -> bool:
        return bool(
            self.odoo_url
            and self.odoo_db
            and self.odoo_user
            and self.odoo_password
        )


def load_settings() -> Settings:
    return Settings(
        odoo_url=os.getenv("ODOO_URL", "").rstrip("/"),
        odoo_db=os.getenv("ODOO_DB", ""),
        odoo_user=os.getenv("ODOO_USER", ""),
        odoo_password=os.getenv("ODOO_PASSWORD", ""),
        ai_api_endpoint=os.getenv("AI_API_ENDPOINT", "").rstrip("/"),
        ai_api_key=os.getenv("AI_API_KEY", ""),
        ai_model=os.getenv("AI_MODEL", "glm-5.2"),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        max_iterations=int(os.getenv("MAX_ITERATIONS", "10")),
    )
