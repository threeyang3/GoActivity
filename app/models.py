from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.utils.time import utcnow


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    article_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    mp_name: Mapped[str] = mapped_column(String(255), default="")
    publish_time: Mapped[str] = mapped_column(String(64), default="")
    url: Mapped[str] = mapped_column(Text, default="")
    pic_url: Mapped[str] = mapped_column(Text, default="")
    raw_payload: Mapped[str] = mapped_column(Text, default="{}")
    raw_markdown: Mapped[str] = mapped_column(Text, default="")
    processed_markdown: Mapped[str] = mapped_column(Text, default="")
    markdown_path: Mapped[str] = mapped_column(Text, default="")
    processed_markdown_path: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    images: Mapped[list["Image"]] = relationship(back_populates="article")
    events: Mapped[list["Event"]] = relationship(back_populates="article")


class Image(Base):
    __tablename__ = "images"
    __table_args__ = (UniqueConstraint("article_id", "original_url", name="uq_article_image_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    image_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.article_id"), index=True)
    original_url: Mapped[str] = mapped_column(Text)
    local_path: Mapped[str] = mapped_column(Text, default="")
    width: Mapped[int] = mapped_column(Integer, default=0)
    height: Mapped[int] = mapped_column(Integer, default=0)
    download_status: Mapped[str] = mapped_column(String(64), default="pending")
    failure_reason: Mapped[str] = mapped_column(Text, default="")
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    vision_result: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    article: Mapped["Article"] = relationship(back_populates="images")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    article_id: Mapped[str] = mapped_column(ForeignKey("articles.article_id"), index=True)
    title: Mapped[str] = mapped_column(String(512), default="")
    category_1: Mapped[str] = mapped_column(String(128), default="其他")
    category_2: Mapped[str] = mapped_column(String(128), default="")
    start_time: Mapped[str] = mapped_column(String(128), default="", index=True)
    end_time: Mapped[str] = mapped_column(String(128), default="")
    location: Mapped[str] = mapped_column(String(512), default="")
    speaker: Mapped[str] = mapped_column(String(512), default="")
    organizer: Mapped[str] = mapped_column(String(512), default="")
    registration: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    article_type: Mapped[str] = mapped_column(String(64), default="other")
    article_type_reason: Mapped[str] = mapped_column(Text, default="")
    activity_kind: Mapped[str] = mapped_column(String(64), default="general_event")
    activity_kind_reason: Mapped[str] = mapped_column(Text, default="")
    is_event_related: Mapped[bool] = mapped_column(Boolean, default=True)
    relevance_reason: Mapped[str] = mapped_column(Text, default="")
    event_time_status: Mapped[str] = mapped_column(String(64), default="unknown")
    retention_decision: Mapped[str] = mapped_column(String(64), default="keep")
    user_keep: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    poster_images: Mapped[str] = mapped_column(Text, default="[]")
    cover_image: Mapped[str] = mapped_column(Text, default="")
    ocr_text: Mapped[str] = mapped_column(Text, default="")
    vision_result: Mapped[str] = mapped_column(Text, default="{}")
    source_url: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(64), default="pending", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    feishu_record_id: Mapped[str] = mapped_column(String(255), default="", index=True)
    dedup_key: Mapped[str] = mapped_column(String(255), default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    # 演出信息
    performance_type: Mapped[str] = mapped_column(String(128), default="")
    performance_name: Mapped[str] = mapped_column(String(512), default="")
    performer: Mapped[str] = mapped_column(String(512), default="")
    ticket_info: Mapped[str] = mapped_column(Text, default="")

    # 讲座信息
    lecture_topic: Mapped[str] = mapped_column(String(512), default="")
    speaker_title: Mapped[str] = mapped_column(String(512), default="")
    lecture_series: Mapped[str] = mapped_column(String(255), default="")

    # 比赛信息
    competition_name: Mapped[str] = mapped_column(String(512), default="")
    competition_type: Mapped[str] = mapped_column(String(128), default="")
    deadline: Mapped[str] = mapped_column(String(128), default="")
    prize_info: Mapped[str] = mapped_column(Text, default="")

    # 报名信息
    registration_url: Mapped[str] = mapped_column(Text, default="")
    registration_deadline: Mapped[str] = mapped_column(String(128), default="")
    participant_limit: Mapped[str] = mapped_column(String(128), default="")

    article: Mapped["Article"] = relationship(back_populates="events")


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    target: Mapped[str] = mapped_column(String(128))
    target_id: Mapped[str] = mapped_column(String(128), default="")
    command: Mapped[str] = mapped_column(Text, default="")
    return_code: Mapped[int] = mapped_column(Integer, default=0)
    stdout: Mapped[str] = mapped_column(Text, default="")
    stderr: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(64), default="running")
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    result_preview: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
