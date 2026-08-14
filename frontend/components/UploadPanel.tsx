'use client';

import React, { useCallback, useMemo, useState } from 'react';
import StemTimeline from './StemTimeline';
import { CheckCircle2, Circle, Loader2, Music, UploadCloud, XCircle } from 'lucide-react';

const acceptedTypes = ['audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/mp3'];
const acceptedExtensions = ['.wav', '.mp3'];

type AnalysisSummary = {
  status: 'pending' | 'active' | 'completed' | 'failed';
  bpm?: number | null;
  key?: string | null;
  structure?: string[] | null;
  message?: string | null;
  next_action?: string | null;
  task_id?: string | null;
};

type StemArtifact = {
  name: string;
  url: string;
  size?: number | null;
  format?: string | null;
  mime_type?: string | null;
};

type StemsSummary = {
  status: 'pending' | 'active' | 'completed' | 'failed';
  stems?: StemArtifact[] | null;
  task_id?: string | null;
  method?: string | null;
  message?: string | null;
  next_action?: string | null;
};

const stageDefinitions = [
  { key: 'upload', label: 'Upload' },
  { key: 'analysis', label: 'Analysis' },
  { key: 'stem_separation', label: 'Stem Separation' },
  { key: 'transcription', label: 'Transcription' },
  { key: 'export', label: 'Export' },
];

type SessionMetadata = {
  session_id: string;
  filename: string;
  content_type: string;
  size: number;
  artifact_url: string;
};

type WorkflowStage = {
  stage: string;
  status: 'pending' | 'active' | 'completed' | 'failed';
  message?: string;
  next_action?: string;
};

type ServerErrorPayload = {
  message: string;
  stage: string;
  nextAction: string;
  workflowStages?: WorkflowStage[];
};

const defaultWorkflowStages: WorkflowStage[] = stageDefinitions.map((stage) => ({
  stage: stage.key,
  status: 'pending',
}));

function buildWorkflowStagesFromResponse(responseStages: Array<{ stage: string; status: WorkflowStage['status']; message?: string; next_action?: string }>) {
  return stageDefinitions.map((definition) => {
    const incoming = responseStages.find((stage) => stage.stage === definition.key);
    return incoming
      ? {
          stage: definition.key,
          status: incoming.status,
          message: incoming.message,
          next_action: incoming.next_action,
        }
      : {
          stage: definition.key,
          status: 'pending' as const,
        };
  });
}

export default function UploadPanel() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileName, setFileName] = useState('');
  const [fileSize, setFileSize] = useState(0);
  const [fileType, setFileType] = useState('');
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [uploadStatus, setUploadStatus] = useState('');
  const [error, setError] = useState('');
  const [dragActive, setDragActive] = useState(false);
  const [sessionMetadata, setSessionMetadata] = useState<SessionMetadata | null>(null);
  const [workflowStages, setWorkflowStages] = useState<WorkflowStage[]>(defaultWorkflowStages);
  const [workflowMessage, setWorkflowMessage] = useState('');
  const [analysisSummary, setAnalysisSummary] = useState<AnalysisSummary | null>(null);
  const [stemSeparation, setStemSeparation] = useState<StemsSummary | null>(null);

  const stageLabelMap = useMemo(
    () => stageDefinitions.reduce<Record<string, string>>((acc, stage) => {
      acc[stage.key] = stage.label;
      return acc;
    }, {}),
    [],
  );

  const isContentTypeExtensionCompatible = useCallback(
    (contentType: string, extension: string) => {
      return (
        (extension === '.wav' && ['audio/wav', 'audio/x-wav'].includes(contentType)) ||
        (extension === '.mp3' && ['audio/mpeg', 'audio/mp3'].includes(contentType))
      );
    },
    [],
  );

  const validateFile = useCallback(
    (file: File) => {
      const typeOk = acceptedTypes.includes(file.type);
      const extension = file.name.toLowerCase().includes('.')
        ? file.name.toLowerCase().slice(file.name.lastIndexOf('.'))
        : '';
      const extensionOk = acceptedExtensions.includes(extension);
      return typeOk && extensionOk && isContentTypeExtensionCompatible(file.type, extension);
    },
    [isContentTypeExtensionCompatible],
  );

  const clickFileInput = useCallback(() => {
    const input = document.getElementById('audio-upload') as HTMLInputElement | null;
    input?.click();
  }, []);

  const resetWorkflow = useCallback(() => {
    setWorkflowStages(defaultWorkflowStages);
    setWorkflowMessage('');
    setAnalysisSummary(null);
    setStemSeparation(null);
  }, []);

  const handleFile = useCallback(
    (file: File) => {
      resetWorkflow();

      if (!validateFile(file)) {
        setError('Unsupported file type. Please upload WAV or MP3.');
        setSelectedFile(null);
        setFileName('');
        setFileSize(0);
        setFileType('');
        setUploadStatus('');
        setUploadProgress(null);
        setSessionMetadata(null);
        return;
      }

      setError('');
      setSelectedFile(file);
      setFileName(file.name);
      setFileSize(file.size);
      setFileType(file.type);
      setUploadStatus('Ready to upload');
      setUploadProgress(null);
      setSessionMetadata(null);
    },
    [resetWorkflow, validateFile],
  );

  const parseServerError = useCallback((responseText: string) => {
    if (!responseText) {
      return {
        message: 'Server returned an empty error response.',
        stage: 'upload',
        nextAction: 'Retry the request or check server logs.',
      } satisfies ServerErrorPayload;
    }

    try {
      const payload = JSON.parse(responseText);
      const message = payload?.message
        ? payload.detail
          ? `${payload.message} ${payload.detail}`
          : payload.message
        : responseText;
      return {
        message,
        stage: payload?.stage ?? 'upload',
        nextAction: payload?.next_action ?? 'Please try again with a supported WAV or MP3 file.',
        workflowStages: payload?.workflow_stages,
      } as ServerErrorPayload;
    } catch {
      return {
        message: responseText,
        stage: 'upload',
        nextAction: 'Please try again or check the network connection.',
      } satisfies ServerErrorPayload;
    }
  }, []);

  const setStageStatus = useCallback((stageKey: string, status: WorkflowStage['status'], message?: string, nextAction?: string) => {
    setWorkflowStages((stages) =>
      stages.map((stage) =>
        stage.stage === stageKey
          ? { ...stage, status, message, next_action: nextAction }
          : stage,
      ),
    );
  }, []);

  const uploadFile = useCallback(() => {
    if (!selectedFile) {
      return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');

    setUploadStatus('Uploading...');
    setStageStatus('upload', 'active', 'Uploading file to backend.');

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        setUploadProgress(Math.round((event.loaded / event.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const response = JSON.parse(xhr.responseText);
          setUploadStatus('Upload complete');
          setSessionMetadata({
            session_id: response.file_id,
            filename: response.filename,
            content_type: response.content_type,
            size: response.size,
            artifact_url: response.artifact_url,
          });

          if (Array.isArray(response.workflow_stages) && response.workflow_stages.length > 0) {
            setWorkflowStages(buildWorkflowStagesFromResponse(response.workflow_stages));
          } else {
            setStageStatus('upload', 'completed', 'Upload completed successfully.');
          }

          setWorkflowMessage('Upload finished. Analysis is about to start.');
          void triggerAnalysis(response.file_id, response.filename, response.artifact_url);
        } catch {
          const message = 'Upload failed: invalid response from server.';
          setError(message);
          setUploadStatus('Upload failed');
          setStageStatus('upload', 'failed', message, 'Check the server response or contact support.');
        }
      } else {
        const serverError = parseServerError(xhr.responseText);
        setError(`Upload failed. ${serverError.message}`);
        setUploadStatus('Upload failed');
        if (serverError.workflowStages) {
          setWorkflowStages(buildWorkflowStagesFromResponse(serverError.workflowStages));
        } else {
          setStageStatus(serverError.stage, 'failed', serverError.message, serverError.nextAction);
        }
        setWorkflowMessage('Upload stage failed. Fix the issue and retry.');
      }
    };

    xhr.onerror = () => {
      const message = 'Upload failed due to network error. Please check your connection and try again.';
      setError(message);
      setUploadStatus('Upload failed');
      setStageStatus('upload', 'failed', message, 'Verify network connectivity and retry.');
      setWorkflowMessage('Network error prevented upload. Please retry.');
    };

    xhr.send(formData);
  }, [selectedFile, parseServerError, setStageStatus]);

  const triggerSeparation = useCallback(async (fileId: string) => {
    setStageStatus('stem_separation', 'active', 'Separating audio into stems.');
    setWorkflowMessage('Stem separation in progress. Stems will be ready shortly.');
    setStemSeparation({ status: 'active', message: 'Separating audio into stems.' });

    try {
      const response = await fetch('/api/separate', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ file_id: fileId }),
      });

      const payload = await response.json();
      if (!response.ok) {
        setStageStatus('stem_separation', 'failed', payload?.message ?? 'Stem separation failed.', payload?.next_action ?? 'Try again later.');
        setWorkflowMessage(payload?.message ?? 'Stem separation failed.');
        setStemSeparation({
          status: 'failed',
          message: payload?.message ?? 'Stem separation failed.',
          next_action: payload?.next_action ?? 'Try again later.',
        });
        if (Array.isArray(payload.workflow_stages)) {
          setWorkflowStages(buildWorkflowStagesFromResponse(payload.workflow_stages));
        }
        return;
      }

      setStageStatus('stem_separation', 'completed', payload.stems?.message ?? 'Stem separation completed successfully.');
      setWorkflowMessage('Stem separation complete. Stems are ready for review.');
      setStemSeparation({
        status: payload.stems?.status ?? 'completed',
        stems: payload.stems?.stems ?? [],
        method: payload.stems?.method ?? null,
        message: payload.stems?.message ?? null,
        task_id: payload.stems?.task_id ?? null,
      });
      if (Array.isArray(payload.workflow_stages)) {
        setWorkflowStages(buildWorkflowStagesFromResponse(payload.workflow_stages));
      }
    } catch {
      setStageStatus('stem_separation', 'failed', 'Stem separation failed because the request could not be completed.', 'Retry the stem separation step.');
      setWorkflowMessage('Stem separation failed. Please retry.');
      setStemSeparation({
        status: 'failed',
        message: 'Stem separation failed because the request could not be completed.',
        next_action: 'Retry the stem separation step.',
      });
    }
  }, [setStageStatus]);

  const triggerAnalysis = useCallback(async (fileId: string, filename: string, artifactUrl: string) => {
    setStageStatus('analysis', 'active', 'Analyzing audio metadata.');
    setWorkflowMessage('Analysis in progress. BPM, key, and structure will appear shortly.');
    setAnalysisSummary({
      status: 'active',
      message: 'Analyzing audio metadata.',
    });

    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ file_id: fileId, filename, artifact_url: artifactUrl }),
      });

      const payload = await response.json();
      if (!response.ok) {
        setStageStatus('analysis', 'failed', payload?.message ?? 'Analysis failed.', payload?.next_action ?? 'Try again later.');
        setWorkflowMessage(payload?.message ?? 'Analysis failed.');
        setAnalysisSummary({
          status: 'failed',
          message: payload?.message ?? 'Analysis failed.',
          next_action: payload?.next_action ?? 'Try again later.',
        });
        if (Array.isArray(payload.workflow_stages)) {
          setWorkflowStages(buildWorkflowStagesFromResponse(payload.workflow_stages));
        }
        return;
      }

      setStageStatus('analysis', 'completed', payload.analysis?.message ?? 'Analysis completed successfully.');
      setWorkflowMessage('Analysis completed. BPM, key, and structure are ready.');
      setAnalysisSummary({
        status: payload.analysis?.status ?? 'completed',
        bpm: payload.analysis?.bpm ?? null,
        key: payload.analysis?.key ?? null,
        structure: payload.analysis?.structure ?? [],
        message: payload.analysis?.message ?? null,
        task_id: payload.analysis?.task_id ?? null,
      });
      if (Array.isArray(payload.workflow_stages)) {
        setWorkflowStages(buildWorkflowStagesFromResponse(payload.workflow_stages));
      }
      void triggerSeparation(fileId);
    } catch {
      setStageStatus('analysis', 'failed', 'Analysis failed because the request could not be completed.', 'Retry the analysis step.');
      setWorkflowMessage('Analysis failed. Please retry.');
      setAnalysisSummary({
        status: 'failed',
        message: 'Analysis failed because the request could not be completed.',
        next_action: 'Retry the analysis step.',
      });
    }
  }, [setStageStatus, triggerSeparation]);

  const handleDrop = useCallback(
    (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setDragActive(false);
      if (event.dataTransfer.files.length > 0) {
        handleFile(event.dataTransfer.files[0]);
      }
    },
    [handleFile],
  );

  const handleChange = useCallback(
    (event: React.ChangeEvent<HTMLInputElement>) => {
      if (event.target.files && event.target.files.length > 0) {
        handleFile(event.target.files[0]);
      }
    },
    [handleFile],
  );

  return (
    <div style={{ display: 'grid', gap: '1rem', maxWidth: 640 }}>
      <label htmlFor="audio-upload" style={{ fontWeight: 600 }}>Upload audio</label>
      <div
        role="button"
        tabIndex={0}
        onClick={clickFileInput}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            clickFileInput();
          }
        }}
        onDragOver={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
        style={{
          padding: '2rem',
          border: '2px dashed #888',
          borderRadius: 12,
          background: dragActive ? '#111' : '#0d0d0d',
          color: '#fff',
          cursor: 'pointer',
          outline: dragActive ? '3px solid #4f46e5' : 'none',
        }}
        aria-live="polite"
      >
        <p>{dragActive ? 'Drop the file here' : 'Drag & drop WAV/MP3 here, or press Enter/Space to choose a file'}</p>
        <div
          role="button"
          tabIndex={0}
          onClick={clickFileInput}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ' ') {
              event.preventDefault();
              clickFileInput();
            }
          }}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginTop: '1rem',
            padding: '0.75rem 1rem',
            borderRadius: 8,
            background: '#222',
            color: '#fff',
            cursor: 'pointer',
          }}
        >
          Select file
        </div>
      </div>
      <input
        id="audio-upload"
        type="file"
        accept="audio/wav,audio/x-wav,audio/mpeg,audio/mp3"
        style={{ display: 'none' }}
        onChange={handleChange}
      />

      {error && (
        <div role="alert" style={{ color: '#ff6b6b', padding: '1rem', background: '#2b0404', borderRadius: 12 }}>
          {error}
        </div>
      )}

      <div style={{ display: 'grid', gap: '0.75rem', padding: '1rem', borderRadius: 12, background: '#111', color: '#fff' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Music size={16} aria-hidden="true" />
            <h2 style={{ margin: 0, fontSize: '1rem' }}>Workflow Progress</h2>
          </div>
          <span style={{ fontSize: '0.9rem', color: '#94a3b8' }}>
            {workflowStages.filter((stage) => stage.status === 'completed').length}/{workflowStages.length} completed
          </span>
        </div>
        {analysisSummary && (
          <div
            aria-label="Analysis summary"
            style={{ display: 'grid', gap: '0.75rem', padding: '0.9rem', borderRadius: 10, background: '#0f172a' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong>Analysis Summary</strong>
              <span
                aria-label={`Analysis status: ${analysisSummary.status}`}
                style={{
                  fontSize: '0.8rem',
                  padding: '0.2rem 0.55rem',
                  borderRadius: 999,
                  background:
                    analysisSummary.status === 'completed'
                      ? '#22c55e'
                      : analysisSummary.status === 'active'
                      ? '#38bdf8'
                      : analysisSummary.status === 'failed'
                      ? '#f97316'
                      : '#334155',
                  color: '#fff',
                }}
              >
                {analysisSummary.status}
              </span>
            </div>
            {analysisSummary.message && <p style={{ margin: 0, color: '#cbd5e1' }}>{analysisSummary.message}</p>}
            <div style={{ display: 'grid', gap: '0.5rem', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))' }}>
              <div aria-label="BPM summary card" style={{ padding: '0.65rem', borderRadius: 8, background: '#111827' }}>
                <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>BPM</div>
                <div style={{ fontSize: '1rem', fontWeight: 600 }}>
                  {analysisSummary.status === 'active' ? '…' : analysisSummary.bpm ?? '—'}
                </div>
              </div>
              <div aria-label="Key summary card" style={{ padding: '0.65rem', borderRadius: 8, background: '#111827' }}>
                <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Key</div>
                <div style={{ fontSize: '1rem', fontWeight: 600 }}>
                  {analysisSummary.status === 'active' ? '…' : analysisSummary.key ?? '—'}
                </div>
              </div>
              <div aria-label="Structure summary card" style={{ padding: '0.65rem', borderRadius: 8, background: '#111827' }}>
                <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Structure</div>
                <div style={{ fontSize: '1rem', fontWeight: 600 }}>
                  {analysisSummary.status === 'active'
                    ? '…'
                    : analysisSummary.structure?.length
                    ? analysisSummary.structure.join(', ')
                    : '—'}
                </div>
              </div>
            </div>
            {analysisSummary.next_action && (
              <p role="alert" style={{ margin: 0, color: '#f8b4b4', fontSize: '0.9rem' }}>{analysisSummary.next_action}</p>
            )}
          </div>
        )}
        {stemSeparation && (
          <div
            aria-label="Stem separation"
            style={{ display: 'grid', gap: '0.75rem', padding: '0.9rem', borderRadius: 10, background: '#0f172a' }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <strong>Stem Separation</strong>
              <span
                aria-label={`Stem separation status: ${stemSeparation.status}`}
                style={{
                  fontSize: '0.8rem',
                  padding: '0.2rem 0.55rem',
                  borderRadius: 999,
                  background:
                    stemSeparation.status === 'completed'
                      ? '#22c55e'
                      : stemSeparation.status === 'active'
                      ? '#38bdf8'
                      : stemSeparation.status === 'failed'
                      ? '#f97316'
                      : '#334155',
                  color: '#fff',
                }}
              >
                {stemSeparation.status}
              </span>
            </div>
            {stemSeparation.message && <p style={{ margin: 0, color: '#cbd5e1' }}>{stemSeparation.message}</p>}
            {stemSeparation.status === 'completed' && (
              <>
                <p aria-label="Stems ready for review" style={{ margin: 0, color: '#a7f3d0', fontWeight: 600 }}>
                  Stems are ready for review.
                </p>
                <StemTimeline stems={stemSeparation.stems ?? []} />
              </>
            )}
            {stemSeparation.next_action && (
              <p role="alert" style={{ margin: 0, color: '#f8b4b4', fontSize: '0.9rem' }}>
                {stemSeparation.next_action}
              </p>
            )}
          </div>
        )}
        <div style={{ display: 'grid', gap: '0.5rem' }}>
          {workflowStages.map((stage) => (
            <div
              key={stage.stage}
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr auto',
                gap: '0.75rem',
                padding: '0.75rem',
                borderRadius: 10,
                background: stage.status === 'failed' ? '#3f1f1f' : '#0f172a',
                border: `1px solid ${stage.status === 'active' ? '#38bdf8' : stage.status === 'completed' ? '#22c55e' : '#334155'}`,
              }}
            >
              <div>
                <strong>{stageLabelMap[stage.stage]}</strong>
                {stage.message && <p style={{ margin: '0.25rem 0 0', color: '#cbd5e1', fontSize: '0.9rem' }}>{stage.message}</p>}
                {stage.status === 'failed' && stage.next_action && (
                  <p style={{ margin: '0.35rem 0 0', color: '#f8b4b4', fontSize: '0.9rem' }}>
                    {stage.next_action}
                  </p>
                )}
              </div>
              <span
                style={{
                  alignSelf: 'center',
                  padding: '0.25rem 0.65rem',
                  borderRadius: 999,
                  fontSize: '0.8rem',
                  background:
                    stage.status === 'completed'
                      ? '#22c55e'
                      : stage.status === 'active'
                      ? '#38bdf8'
                      : stage.status === 'failed'
                      ? '#f97316'
                      : '#334155',
                  color: '#fff',
                  justifySelf: 'end',
                }}
              >
                {stage.status === 'completed' && <CheckCircle2 size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} aria-hidden="true" />}
                {stage.status === 'failed' && <XCircle size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} aria-hidden="true" />}
                {stage.status === 'active' && <Loader2 size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} aria-hidden="true" />}
                {stage.status === 'pending' && <Circle size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} aria-hidden="true" />}
                {stage.status}
              </span>
            </div>
          ))}
        </div>
        {workflowMessage && (
          <div style={{ padding: '0.75rem', borderRadius: 10, background: '#111827', color: '#e2e8f0' }}>
            {workflowMessage}
          </div>
        )}
      </div>

      {fileName && (
        <div style={{ padding: '1rem', borderRadius: 12, background: '#111', color: '#fff' }}>
          <p><strong>File:</strong> {fileName}</p>
          <p><strong>Type:</strong> {fileType}</p>
          <p><strong>Size:</strong> {(fileSize / 1024 / 1024).toFixed(2)} MB</p>
        </div>
      )}

      <button
        type="button"
        onClick={uploadFile}
        disabled={!selectedFile || !!error}
        style={{
          padding: '0.75rem 1rem',
          borderRadius: 8,
          background: selectedFile && !error ? '#4f46e5' : '#444',
          color: '#fff',
          border: 'none',
          cursor: selectedFile && !error ? 'pointer' : 'not-allowed',
        }}
      >
        <UploadCloud size={18} style={{ verticalAlign: 'middle', marginRight: 6 }} aria-hidden="true" />
        Upload to backend
      </button>

      {uploadStatus && (
        <div style={{ color: '#d9d9d9' }}>
          <p><strong>Status:</strong> {uploadStatus}</p>
          {uploadProgress !== null && <p><strong>Progress:</strong> {uploadProgress}%</p>}
        </div>
      )}

      {sessionMetadata && (
        <div style={{ padding: '1rem', borderRadius: 12, background: '#111', color: '#fff' }}>
          <p><strong>Session ID:</strong> {sessionMetadata.session_id}</p>
          <p><strong>Artifact URL:</strong> {sessionMetadata.artifact_url}</p>
          <p><strong>Uploaded file:</strong> {sessionMetadata.filename}</p>
        </div>
      )}
    </div>
  );
}
