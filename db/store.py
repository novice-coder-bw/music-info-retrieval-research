"""Store adapter for the durable session store (AD-2).

Mirrors the existing in-memory ``SESSIONS`` dict contract in
``backend/app/main.py``: ``get_session``/``save_session`` by ``file_id`` and
``list_artifacts`` per session. Callers that need to simulate a process restart
can pass an explicit ``session_factory`` (e.g. a fresh engine bound to the same
database file).
"""

from typing import Optional

from sqlalchemy.orm import sessionmaker

from db.engine import get_session_factory
from db.models import ArtifactRecord, SessionRecord, utc_now_iso

_SESSION_COLUMNS = (
    'file_id',
    'filename',
    'content_type',
    'size',
    'artifact_url',
    'analysis',
    'stems',
    'workflow_stages',
)


def save_session(session_data: dict, session_factory: Optional[sessionmaker] = None) -> None:
    """Upsert a session row keyed by ``session_data['file_id']``."""
    file_id = session_data.get('file_id')
    if not file_id:
        return
    factory = session_factory or get_session_factory()
    values = {column: session_data.get(column) for column in _SESSION_COLUMNS}
    values['updated_at'] = utc_now_iso()
    with factory() as db:
        row = db.get(SessionRecord, file_id)
        if row is None:
            db.add(SessionRecord(**values))
        else:
            for column, value in values.items():
                if column != 'file_id':
                    setattr(row, column, value)
        db.commit()


def get_session(file_id: str, session_factory: Optional[sessionmaker] = None) -> Optional[dict]:
    """Return the stored session dict for ``file_id``, or None."""
    factory = session_factory or get_session_factory()
    with factory() as db:
        row = db.get(SessionRecord, file_id)
        if row is None:
            return None
        return {column: getattr(row, column) for column in _SESSION_COLUMNS}


def save_artifact(artifact: dict, session_factory: Optional[sessionmaker] = None) -> None:
    """Insert an artifact row (raw audio, stem file, or other asset)."""
    factory = session_factory or get_session_factory()
    allowed = {column.name for column in ArtifactRecord.__table__.columns}
    values = {k: v for k, v in artifact.items() if k in allowed and k != 'id'}
    with factory() as db:
        db.add(ArtifactRecord(**values))
        db.commit()


def list_artifacts(file_id: str, session_factory: Optional[sessionmaker] = None) -> list[dict]:
    """Return all stored artifact rows for a session, oldest first."""
    factory = session_factory or get_session_factory()
    columns = [column.name for column in ArtifactRecord.__table__.columns]
    with factory() as db:
        rows = (
            db.query(ArtifactRecord)
            .filter(ArtifactRecord.file_id == file_id)
            .order_by(ArtifactRecord.id.asc())
            .all()
        )
        return [{column: getattr(row, column) for column in columns} for row in rows]