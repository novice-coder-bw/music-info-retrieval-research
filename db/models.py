"""SQLAlchemy 2.0 declarative models for the durable session store (AD-2).

The models mirror the in-memory ``SESSIONS`` dict contract from
``backend/app/main.py`` so downstream consumers (Epic 3/4) read the same
shapes from the store that they read from the dict today.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now_iso() -> str:
    """UTC ISO 8601 timestamp string, matching the platform-wide convention."""
    return datetime.now(timezone.utc).isoformat()


class Base(DeclarativeBase):
    pass


class SessionRecord(Base):
    """One row per upload session, keyed by ``file_id``.

    Each structured column (analysis / stems / workflow_stages) stores the exact
    JSON payload the API already produces, so no parallel data model exists.
    """

    __tablename__ = 'sessions'

    file_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    filename: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    content_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    artifact_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    analysis: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    stems: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    workflow_stages: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[str] = mapped_column(String(64), default=utc_now_iso)
    updated_at: Mapped[str] = mapped_column(String(64), default=utc_now_iso)


class ArtifactRecord(Base):
    """One row per stored object (raw audio, stem file, future MIDI/export).

    ``storage_backend`` records whether the object actually lives in Cloudflare
    R2 or the local uploads tree, so the platform never lies about which
    backend stored an artifact (AC-5).
    """

    __tablename__ = 'artifacts'

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(256))
    url: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32), default='asset')
    storage_backend: Mapped[str] = mapped_column(String(16), default='local')
    key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    format: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[str] = mapped_column(String(64), default=utc_now_iso)