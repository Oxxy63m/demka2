from __future__ import annotations

import os

# Папка с Excel/картинками/ресурсами (относительно корня проекта).
DATA_DIR = "resources"


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v is not None and str(v).strip() else default


# Настройки для psycopg2 (используется в import_to_db.py)
DB_CONFIG = {
    "host": _env("DB_HOST", "localhost"),
    "port": int(_env("DB_PORT", "5432")),
    "dbname": _env("DB_NAME", "demka"),
    "user": _env("DB_USER", "postgres"),
    "password": _env("DB_PASSWORD", "1234"),
}


def sqlalchemy_url() -> str:
    # psycopg (v3) драйвер для SQLAlchemy
    host = DB_CONFIG["host"]
    port = DB_CONFIG["port"]
    dbname = DB_CONFIG["dbname"]
    user = DB_CONFIG["user"]
    password = DB_CONFIG["password"]
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"

