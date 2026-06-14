from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _url(user, pw, host, port, db):
    return f"mysql+pymysql://{user}:{pw}@{host}:{port}/{db}"


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    olist_db: str
    app_db: str
    ro_user: str
    ro_password: str
    etl_user: str
    etl_password: str
    llm_provider: str
    cloud_api_key: str
    cloud_base_url: str
    cloud_model: str
    cloud_use_proxy: bool
    ollama_base_url: str
    ollama_model: str

    @property
    def olist_ro_url(self):
        return _url(self.ro_user, self.ro_password, self.host, self.port, self.olist_db)

    @property
    def app_server_url(self):
        return _url(self.etl_user, self.etl_password, self.host, self.port, "")

    @property
    def app_url(self):
        return _url(self.etl_user, self.etl_password, self.host, self.port, self.app_db)


@lru_cache
def get_settings() -> Settings:
    load_dotenv(BACKEND_ROOT / ".env")
    return Settings(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        olist_db=os.getenv("OLIST_DB", "olist_bi"),
        app_db=os.getenv("APP_DB", "agentic_app"),
        ro_user=os.getenv("MYSQL_RO_USER", "olist_ro"),
        ro_password=os.getenv("MYSQL_RO_PASSWORD", "ro_pass_2024"),
        etl_user=os.getenv("MYSQL_ETL_USER", "olist_etl"),
        etl_password=os.getenv("MYSQL_ETL_PASSWORD", "etl_pass_2024"),
        llm_provider=os.getenv("LLM_PROVIDER", "cloud"),
        cloud_api_key=os.getenv("CLOUD_API_KEY", os.getenv("DEEPSEEK_API_KEY", "")),
        cloud_base_url=os.getenv("CLOUD_BASE_URL", "https://api.deepseek.com"),
        cloud_model=os.getenv("CLOUD_MODEL", "deepseek-chat"),
        cloud_use_proxy=os.getenv("CLOUD_USE_PROXY", "false").lower() in ("1", "true", "yes"),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1"),
        ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
    )
