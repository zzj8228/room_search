"""Dedicated PostgreSQL database, independent encrypted configuration."""
from contextlib import contextmanager
import os

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from .paths import runtime_dir
from .auth import dpapi

CONFIG = runtime_dir() / "auth/postgres.dpapi"


def require_database_url():
    value = os.environ.get("PKU_CLASSROOM_DATABASE_URL")
    if value:
        return value
    if CONFIG.exists():
        return dpapi(CONFIG.read_bytes(), decrypt=True).decode("utf-8")
    raise RuntimeError("请先运行 classroom.py create-database 创建独立教室数据库。")


@contextmanager
def connection():
    with psycopg.connect(require_database_url(), connect_timeout=5, row_factory=dict_row) as conn:
        yield conn


def save_configuration(value):
    with psycopg.connect(value, connect_timeout=5) as conn:
        name = conn.execute("SELECT current_database()").fetchone()[0]
        if conn.execute("SELECT to_regclass('public.pku_lessons')").fetchone()[0]:
            raise ValueError("目标数据库包含回放表，请使用独立的课表数据库。")
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG.with_suffix(".tmp")
    try:
        temporary.write_bytes(dpapi(value.encode("utf-8")))
        temporary.replace(CONFIG)
    finally:
        temporary.unlink(missing_ok=True)
    return {"database": name, "configuration": "Windows DPAPI"}


def source_connection_url():
    value = os.environ.get("PKU_CLASSROOM_IMPORT_DATABASE_URL")
    if not value:
        raise ValueError("请显式设置 PKU_CLASSROOM_IMPORT_DATABASE_URL；不会读取其他项目配置。")
    return value


def create_database(name="pku_classroom"):
    """Use explicit admin connection, without opening any other app's config."""
    import re
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", name):
        raise ValueError("数据库名称无效。")
    value = os.environ.get("PKU_CLASSROOM_ADMIN_DATABASE_URL")
    if not value:
        raise ValueError("请在当前进程设置 PKU_CLASSROOM_ADMIN_DATABASE_URL。")
    params = conninfo_to_dict(value)
    if name == params.get("dbname"):
        raise ValueError("教室数据库必须与原回放数据库不同。")
    admin = {**params, "dbname": "postgres", "connect_timeout": 5}
    with psycopg.connect(**admin, autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname=%s", (name,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    value = make_conninfo(**{**params, "dbname": name})
    return save_configuration(value)
