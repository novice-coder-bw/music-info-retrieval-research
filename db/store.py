from typing import Optional
from sqlalchemy.orm import sessionmaker

from db.engine import get_session_factory
from db.models import ArtifactRecord, SessionRecord, UploadIntentRecord, utc_now_iso

_SESSION_COLUMNS = (
    'file_id',
    'user_id',
    'filename',
    'content_type',
    'size',
    'artifact_url',
    'analysis',
    'stems',
    'workflow_stages',
    'created_at',
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
                if column != 'file_id' and value is not None:
                    setattr(row, column, value)
        db.commit()


def get_session(file_id: str, session_factory: Optional[sessionmaker] = None) -> Optional[dict]:
    """Return the stored session dict for ``file_id``, or None."""
    factory = session_factory or get_session_factory()
    with factory() as db:
        row = db.get(SessionRecord, file_id)
        if row is None:
            return None
        data = {column: getattr(row, column) for column in _SESSION_COLUMNS}
        data['updated_at'] = row.updated_at
        return data


def save_artifact(artifact: dict, session_factory: Optional[sessionmaker] = None) -> None:
    """Upsert an artifact row keyed by ``(file_id, name, kind)``."""
    factory = session_factory or get_session_factory()
    allowed = {column.name for column in ArtifactRecord.__table__.columns}
    values = {k: v for k, v in artifact.items() if k in allowed and k != 'id'}
    values.setdefault('storage_backend', 'r2')
    with factory() as db:
        row = (
            db.query(ArtifactRecord)
            .filter_by(
                file_id=values.get('file_id'),
                name=values.get('name'),
                kind=values.get('kind', 'asset'),
            )
            .first()
        )
        if row is None:
            db.add(ArtifactRecord(**values))
        else:
            for column, value in values.items():
                if column != 'id':
                    setattr(row, column, value)
        db.commit()


def save_upload_intent(intent: dict, session_factory: Optional[sessionmaker] = None) -> None:
    """Save a presigned upload intent."""
    factory = session_factory or get_session_factory()
    with factory() as db:
        record = UploadIntentRecord(
            object_key=intent['object_key'],
            file_id=intent['file_id'],
            user_id=intent['user_id'],
            expected_content_type=intent['expected_content_type'],
            expected_max_size=intent['expected_max_size'],
            completed=intent.get('completed', False),
            created_at=utc_now_iso(),
        )
        db.merge(record)
        db.commit()


def get_upload_intent(object_key: str, session_factory: Optional[sessionmaker] = None) -> Optional[dict]:
    """Retrieve an upload intent by object key."""
    factory = session_factory or get_session_factory()
    with factory() as db:
        row = db.get(UploadIntentRecord, object_key)
        if not row:
            return None
        return {
            'object_key': row.object_key,
            'file_id': row.file_id,
            'user_id': row.user_id,
            'expected_content_type': row.expected_content_type,
            'expected_max_size': row.expected_max_size,
            'completed': row.completed,
            'created_at': row.created_at,
        }


def mark_upload_intent_completed(object_key: str, session_factory: Optional[sessionmaker] = None) -> bool:
    """Mark an upload intent as completed atomically; returns False if not found or already completed."""
    factory = session_factory or get_session_factory()
    with factory() as db:
        row = db.get(UploadIntentRecord, object_key)
        if not row or row.completed:
            return False
        row.completed = True
        db.commit()
        return True


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
