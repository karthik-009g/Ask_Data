from urllib.parse import urlparse, urlunparse
from types import SimpleNamespace
from typing import Any

from sqlalchemy.engine import URL, make_url
from sqlalchemy import create_engine
from pymongo import MongoClient

from app.core.encryption import decrypt_secret


def _coerce_connection(connection: Any) -> Any:
    if isinstance(connection, dict):
        return SimpleNamespace(**connection)
    return connection


def _normalized_db_type(connection: Any) -> str:
    value = getattr(connection, "db_type", "")
    return str(value or "").strip().lower()


def build_mongo_uri(connection: Any) -> str:
    connection = _coerce_connection(connection)
    password = decrypt_secret(connection.encrypted_password or "") if connection.encrypted_password else ""
    if connection.connection_url:
        parsed = urlparse(connection.connection_url)
        if connection.username and password:
            netloc = f"{connection.username}:{password}@{parsed.hostname or connection.host}"
            if parsed.port or connection.port:
                netloc = f"{netloc}:{parsed.port or connection.port}"
            path = parsed.path if parsed.path else f"/{connection.database_name or ''}"
            return urlunparse((parsed.scheme or "mongodb", netloc, path, parsed.params, parsed.query, parsed.fragment))
        return connection.connection_url

    return f"mongodb://{connection.username}:{password}@{connection.host}:{connection.port}/{connection.database_name}"


def resolve_mongo_database(client: MongoClient, connection: Any):
    connection = _coerce_connection(connection)
    database_name = getattr(connection, "database_name", None) or None
    if database_name:
        return client[database_name]

    connection_url = getattr(connection, "connection_url", None) or ""
    if connection_url:
        parsed = urlparse(connection_url)
        path_db = (parsed.path or "").strip("/")
        if path_db:
            return client[path_db]

    raise ValueError("MongoDB database name is required for Atlas URL connections. Add the database in the URL path or fill the Database Name field.")


def build_sqlalchemy_url(connection: Any) -> str:
    connection = _coerce_connection(connection)
    db_type = _normalized_db_type(connection)
    if db_type == "mongodb":
        raise ValueError("MongoDB connections must use the MongoDB client, not SQLAlchemy")

    if connection.connection_url:
        if connection.encrypted_password:
            password = decrypt_secret(connection.encrypted_password)
            parsed = make_url(connection.connection_url)
            return parsed.set(password=password).render_as_string(hide_password=False)
        return connection.connection_url

    if not connection.username or not connection.encrypted_password:
        raise ValueError("Missing username or password")

    password = decrypt_secret(connection.encrypted_password)
    driver = "mysql+pymysql" if db_type == "mysql" else "postgresql+psycopg2"
    url = URL.create(
        drivername=driver,
        username=connection.username,
        password=password,
        host=connection.host,
        port=connection.port,
        database=connection.database_name,
    )
    return url.render_as_string(hide_password=False)


def test_connection(connection: Any) -> None:
    connection = _coerce_connection(connection)
    db_type = _normalized_db_type(connection)
    if db_type == "mongodb":
        client = MongoClient(build_mongo_uri(connection), serverSelectionTimeoutMS=5000)
        try:
            client.admin.command("ping")
        finally:
            client.close()
        return

    connect_args = {}
    if db_type == "postgresql":
        connect_args = {"connect_timeout": 5}
    elif db_type == "mysql":
        connect_args = {"connect_timeout": 5, "read_timeout": 5, "write_timeout": 5}

    engine = create_engine(build_sqlalchemy_url(connection), pool_pre_ping=True, connect_args=connect_args)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    finally:
        engine.dispose()
