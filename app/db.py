from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {
            "connect_args": {
                "check_same_thread": False,
                "timeout": 30,  # SQLite 锁等待超时
            }
        }
    return {}


settings = get_settings()
engine = create_engine(settings.database_url, **_engine_args(settings.database_url))

# 启用 SQLite WAL 模式，提升并发读写性能
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create tables and run Alembic migrations.

    - New installs: ``create_all`` builds everything from the current models,
      then ``alembic stamp head`` marks the schema as fully migrated.
    - Existing installs: ``alembic upgrade head`` applies any pending migrations.
    """
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _run_alembic_upgrade()


def _run_alembic_upgrade() -> None:
    """Apply pending Alembic migrations, or stamp head on a fresh database."""
    import logging
    from pathlib import Path

    from alembic.config import Config
    from alembic import command

    logger = logging.getLogger(__name__)

    alembic_ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    if not alembic_ini.exists():
        logger.warning("alembic.ini not found at %s – skipping migrations", alembic_ini)
        return

    try:
        alembic_cfg = Config(str(alembic_ini))
        # If the alembic_version table doesn't exist yet (fresh DB), stamp head
        # so future upgrades start from the right baseline.
        from sqlalchemy import inspect as sa_inspect

        inspector = sa_inspect(engine)
        if "alembic_version" not in inspector.get_table_names():
            command.stamp(alembic_cfg, "head")
            logger.info("Fresh database – stamped as head")
        else:
            command.upgrade(alembic_cfg, "head")
            logger.info("Alembic upgrade head completed")
    except Exception:
        logger.exception(
            "Alembic migration failed — the app will continue with the current schema. "
            "This may cause runtime errors if the schema is out of date."
        )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
