from types import SimpleNamespace

import pytest

from shared.schemas import AnalysisMetadata, WorkflowStageStatus
from workers import tasks


@pytest.mark.parametrize('essentia_available', [False, True])
def test_completed_analysis_matches_schema(monkeypatch, essentia_available):
    monkeypatch.setattr(tasks, 'ESSENTIA_AVAILABLE', essentia_available)
    monkeypatch.setenv('ALLOW_PLACEHOLDER_STEMS', '1')
    if essentia_available:
        fake_es = SimpleNamespace(
            MonoLoader=lambda **kwargs: lambda: [0] * 88200,
            RhythmExtractor2013=lambda **kwargs: lambda audio: (120, None, None, None, None),
            KeyExtractor=lambda: lambda audio: ('C', 'major', None),
        )
        monkeypatch.setattr(tasks, 'es', fake_es, raising=False)
    result = AnalysisMetadata(**tasks.build_analysis_result('file', 'source.wav'))
    assert result.structure == (['segment'] if essentia_available else ['verse'])
    assert result.duration == (2.0 if essentia_available else 10.0)


@pytest.mark.parametrize('task_name, stage', [
    ('analyze_audio_task', 'analysis'),
    ('separate_stems_task', 'stem_separation'),
])
def test_task_starts_with_active_stage(monkeypatch, tmp_path, task_name, stage):
    stages = []
    monkeypatch.setattr(tasks, 'update_session_stage', lambda file_id, name, status, message: stages.append(
        WorkflowStageStatus(stage=name, status=status, message=message)
    ))
    monkeypatch.setattr(tasks.db_store, 'get_session', lambda file_id: None)
    monkeypatch.setattr(tasks, 'build_analysis_result', lambda *args: {'status': 'completed'})
    monkeypatch.setattr(tasks, 'separate_stems_with_demucs', lambda *args: {'status': 'completed', 'stems': []})
    monkeypatch.setenv('SCRATCH_DIR', str(tmp_path))
    getattr(tasks, task_name).run('file', 'source.wav')
    assert stages[0].stage == stage
    assert stages[0].status == 'active'
