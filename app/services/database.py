"""PostgreSQL connections. Every connection gets a connect timeout and a statement timeout,
so a slow or stuck database fails fast instead of holding the request (PY rules)."""

import psycopg

from app.config import Settings


def connect(settings: Settings) -> psycopg.Connection:
    timeout = settings.postgres_timeout_seconds
    return psycopg.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password.get_secret_value(),
        connect_timeout=timeout,
        options=f"-c statement_timeout={timeout * 1000}",
    )
