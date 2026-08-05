'use client';

import React, { useCallback, useState } from 'react';

const acceptedTypes = ['audio/wav', 'audio/x-wav', 'audio/mpeg', 'audio/mp3'];
const acceptedExtensions = ['.wav', '.mp3'];

type SessionMetadata = {
  session_id: string;
  filename: string;
  content_type: string;
  size: number;
  artifact_url: string;
};

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

  const isContentTypeExtensionCompatible = useCallback((contentType: string, extension: string) => {
    return (
      (extension === '.wav' && ['audio/wav', 'audio/x-wav'].includes(contentType)) ||
      (extension === '.mp3' && ['audio/mpeg', 'audio/mp3'].includes(contentType))
    );
  }, []);

  const validateFile = useCallback((file: File) => {
    const typeOk = acceptedTypes.includes(file.type);
    const extension = file.name.toLowerCase().includes('.')
      ? file.name.toLowerCase().slice(file.name.lastIndexOf('.'))
      : '';
    const extensionOk = acceptedExtensions.includes(extension);
    return typeOk && extensionOk && isContentTypeExtensionCompatible(file.type, extension);
  }, [isContentTypeExtensionCompatible]);

  const clickFileInput = useCallback(() => {
    const input = document.getElementById('audio-upload') as HTMLInputElement | null;
    input?.click();
  }, []);

  const handleFile = useCallback((file: File) => {
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
  }, [validateFile]);

  const parseServerError = useCallback((responseText: string) => {
    if (!responseText) {
      return 'Server returned an empty error response.';
    }

    try {
      const payload = JSON.parse(responseText);
      if (payload?.message) {
        return payload.detail ? `${payload.message} ${payload.detail}` : payload.message;
      }
    } catch {
      // Ignore parse errors and fall back to raw text.
    }

    return responseText;
  }, []);

  const uploadFile = useCallback(() => {
    if (!selectedFile) {
      return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');

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
        } catch (error) {
          setError('Upload failed: invalid response from server.');
          setUploadStatus('Upload failed');
        }
      } else {
        const serverError = parseServerError(xhr.responseText);
        setError(`Upload failed. ${serverError}`);
        setUploadStatus('Upload failed');
      }
    };

    xhr.onerror = () => {
      setError('Upload failed due to network error. Please check your connection and try again.');
      setUploadStatus('Upload failed');
    };

    setUploadStatus('Uploading...');
    xhr.send(formData);
  }, [selectedFile, parseServerError]);

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
        <button
          type="button"
          onClick={() => document.getElementById('audio-upload')?.click()}
          style={{
            marginTop: '1rem',
            padding: '0.75rem 1rem',
            borderRadius: 8,
            background: '#222',
            color: '#fff',
            border: 'none',
          }}
        >
          Select file
        </button>
      </div>
      <input
        id="audio-upload"
        type="file"
        accept="audio/wav,audio/x-wav,audio/mpeg,audio/mp3"
        style={{ display: 'none' }}
        onChange={handleChange}
      />

      {error && (
        <div role="alert" style={{ color: '#ff6b6b' }}>
          {error}
        </div>
      )}

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
