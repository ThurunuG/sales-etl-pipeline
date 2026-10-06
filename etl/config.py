"""Central configuration. All settings come from environment variables (.env)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _path(env_name: str, default: str) -> Path:
    p = Path(os.getenv(env_name, default))
    return p if p.is_absolute() else PROJECT_ROOT / p


@dataclass(frozen=True)
class Settings:
    db_host: str = os.getenv("POSTGRES_HOST", "localhost")
    db_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    db_name: str = os.getenv("POSTGRES_DB", "sales_dw")
    db_user: str = os.getenv("POSTGRES_USER", "etl_user")
    db_password: str = os.getenv("POSTGRES_PASSWORD", "")

    raw_path: Path = _path("RAW_DATA_PATH", "data/raw/sales_raw.csv")
    processed_path: Path = _path("PROCESSED_DATA_PATH", "data/processed/sales_clean.csv")
    rejected_path: Path = _path("REJECTED_DATA_PATH", "logs/rejected_records.csv")
    log_path: Path = _path("LOG_PATH", "logs/pipeline.log")
    sql_dir: Path = PROJECT_ROOT / "sql"

    def dsn(self) -> dict:
        return dict(host=self.db_host, port=self.db_port, dbname=self.db_name,
                    user=self.db_user, password=self.db_password)


def get_settings() -> Settings:
    return Settings()
