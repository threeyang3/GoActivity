"""测试公共 fixture。

每个测试结束后清理测试数据。使用 DELETE WHERE 条件，
只清理测试创建的记录，不碰生产数据。
"""

import pytest
from sqlalchemy import text

from app.db import SessionLocal, init_db


@pytest.fixture(scope="session", autouse=True)
def _init_database():
    """整个测试会话只初始化一次数据库 schema。"""
    init_db()


def _batch_delete(conn, table: str, id_col: str, new_ids: set) -> None:
    """批量删除记录。使用 executemany 提高效率。"""
    if not new_ids:
        return
    stmt = text(f"DELETE FROM {table} WHERE {id_col} = :id")
    conn.execute(stmt, [{"id": id} for id in new_ids])


@pytest.fixture(autouse=True)
def _clean_test_data():
    """每个测试结束后清理测试创建的数据。

    策略：保留测试前已存在的记录，只删除测试期间新增的。
    """
    from app.db import engine

    # 记录测试前各表的 ID 集合
    with engine.connect() as conn:
        existing_article_ids = {r[0] for r in conn.execute(text("SELECT article_id FROM articles")).fetchall()}
        existing_event_ids = {r[0] for r in conn.execute(text("SELECT event_id FROM events")).fetchall()}
        existing_log_ids = {r[0] for r in conn.execute(text("SELECT id FROM sync_logs")).fetchall()}
        existing_run_ids = {r[0] for r in conn.execute(text("SELECT run_id FROM sync_runs")).fetchall()}
        existing_image_ids = {r[0] for r in conn.execute(text("SELECT image_id FROM images")).fetchall()}

    yield

    # 清理测试新增的记录（不在测试前集合中的）
    with engine.begin() as conn:
        # sync_logs
        new_ids = {r[0] for r in conn.execute(text("SELECT id FROM sync_logs")).fetchall()} - existing_log_ids
        _batch_delete(conn, "sync_logs", "id", new_ids)

        # sync_runs
        new_ids = {r[0] for r in conn.execute(text("SELECT run_id FROM sync_runs")).fetchall()} - existing_run_ids
        _batch_delete(conn, "sync_runs", "run_id", new_ids)

        # events（先删，因为有外键）
        new_ids = {r[0] for r in conn.execute(text("SELECT event_id FROM events")).fetchall()} - existing_event_ids
        _batch_delete(conn, "events", "event_id", new_ids)

        # images（使用与其他表一致的 set-difference 策略）
        new_ids = {r[0] for r in conn.execute(text("SELECT image_id FROM images")).fetchall()} - existing_image_ids
        _batch_delete(conn, "images", "image_id", new_ids)

        # articles
        new_ids = {r[0] for r in conn.execute(text("SELECT article_id FROM articles")).fetchall()} - existing_article_ids
        _batch_delete(conn, "articles", "article_id", new_ids)


@pytest.fixture()
def db():
    """提供一个数据库 session，测试结束后自动回滚并关闭。"""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
