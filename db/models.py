from typing import Optional
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text, JSON
from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class SessionRecord(Base):
    """Database model for an analysis/separation session."""
    __tablename__ = 'sessions'

    file_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    filename: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    artifact_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    stems: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    workflow_stages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[Optional[str]] = mapped_column(String(64), default=utc_now_iso, nullable=True)
    updated_at: Mapped[str] = mapped_column(String(64), default=utc_now_iso, onupdate=utc_now_iso)


class ArtifactRecord(Base):
    """Database model for stored audio and stem artifacts."""
    __tablename__ = 'artifacts'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(256))
    url: Mapped[Text] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32), default='asset')
    storage_backend: Mapped[str] = mapped_column(String(16), default='r2')
    key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    format: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[str] = mapped_column(String(64), default=utc_now_iso)
