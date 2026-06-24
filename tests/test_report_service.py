"""测试 ReportService 的日报/周报功能。"""

from datetime import timedelta

from app.db import SessionLocal, init_db
from app.models import Article, Event
from app.services.report_service import ReportService
from app.utils.constants import ACTIVITY_KIND_LABELS
from app.utils.time import utcnow


def test_daily_report_format() -> None:
    """测试日报输出格式。"""
    init_db()
    db = SessionLocal()

    # 创建测试数据
    article = Article(
        article_id="article_report_test_1",
        title="测试讲座",
        mp_name="北大团委",
        publish_time=utcnow().isoformat(),
    )
    event = Event(
        event_id="event_report_test_1",
        article_id=article.article_id,
        title="测试讲座",
        activity_kind="lecture",
        start_time=(utcnow() + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
        end_time=(utcnow() + timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S"),
        location="学术报告厅",
        status="extracted",
        confidence=0.8,
        created_at=utcnow(),
    )
    db.add(article)
    db.add(event)
    db.commit()

    try:
        service = ReportService(db)
        report = service.daily_report()

        # 验证格式
        assert "# 校园活动日报" in report
        assert "## 📊 概览" in report
        assert "## 📈 分类统计" in report
        assert "## ⭐ 推荐 TOP5" in report
        assert "## 📋 活动列表" in report
        assert "测试讲座" in report
        assert "讲座" in report
        assert "学术报告厅" in report
    finally:
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.query(Article).filter(Article.article_id == article.article_id).delete()
        db.commit()
        db.close()


def test_weekly_report_format() -> None:
    """测试周报输出格式。"""
    init_db()
    db = SessionLocal()

    # 创建测试数据
    article = Article(
        article_id="article_report_test_2",
        title="测试演出",
        mp_name="北大团委",
        publish_time=utcnow().isoformat(),
    )
    event = Event(
        event_id="event_report_test_2",
        article_id=article.article_id,
        title="测试演出",
        activity_kind="performance",
        start_time=(utcnow() + timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S"),
        end_time=(utcnow() + timedelta(days=2, hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
        location="百周年纪念讲堂",
        status="synced",
        confidence=0.9,
        created_at=utcnow(),
    )
    db.add(article)
    db.add(event)
    db.commit()

    try:
        service = ReportService(db)
        report = service.weekly_report()

        # 验证格式
        assert "# 校园活动周报" in report
        assert "## 📊 概览" in report
        assert "## 📈 分类统计" in report
        assert "## 📊 状态统计" in report
        assert "## ⭐ 推荐 TOP10" in report
        assert "## 📋 活动列表" in report
        assert "测试演出" in report
        assert "演出·放映" in report
        assert "百周年纪念讲堂" in report
    finally:
        db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.query(Article).filter(Article.article_id == article.article_id).delete()
        db.commit()
        db.close()


def test_compute_stats() -> None:
    """测试统计计算。"""
    init_db()
    db = SessionLocal()

    # 创建测试数据
    now = utcnow()
    events = [
        Event(
            event_id=f"event_stats_test_{i}",
            article_id=f"article_stats_test_{i}",
            title=f"测试活动 {i}",
            activity_kind=kind,
            status="extracted",
            confidence=0.5,
            created_at=now,
        )
        for i, kind in enumerate(["lecture", "lecture", "performance", "competition"])
    ]
    db.add_all(events)
    db.commit()

    try:
        service = ReportService(db)
        stats = service._compute_stats(events)

        assert stats["total"] == 4
        assert stats["by_kind"]["lecture"] == 2
        assert stats["by_kind"]["performance"] == 1
        assert stats["by_kind"]["competition"] == 1
        assert stats["new_count"] == 4  # 所有都是今天创建的
    finally:
        for event in events:
            db.query(Event).filter(Event.event_id == event.event_id).delete()
        db.commit()
        db.close()


def test_activity_kind_labels() -> None:
    """测试活动类型标签映射。"""
    assert ACTIVITY_KIND_LABELS["lecture"] == "讲座"
    assert ACTIVITY_KIND_LABELS["performance"] == "演出·放映"
    assert ACTIVITY_KIND_LABELS["competition"] == "比赛·征稿"
    assert ACTIVITY_KIND_LABELS["volunteer_recruitment"] == "志愿者招募"
    assert ACTIVITY_KIND_LABELS["general_recruitment"] == "普通招募"
    assert ACTIVITY_KIND_LABELS["general_event"] == "普通活动"
    assert ACTIVITY_KIND_LABELS["non_event"] == "非活动"
