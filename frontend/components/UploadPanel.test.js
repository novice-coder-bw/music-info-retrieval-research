import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import UploadPanel from './UploadPanel';

// Mock WaveSurfer so the timeline component is testable under jsdom (the real
// library needs Window/AudioContext and a real audio fetch to fire `onReady`).
jest.mock('@wavesurfer/react', () => {
  const ReactMock = require('react');
  const fakeWs = {
    play: jest.fn(),
    pause: jest.fn(),
    isPlaying: jest.fn(() => false),
    getDuration: jest.fn(() => 10),
    getCurrentTime: jest.fn(() => 0),
    seekTo: jest.fn(),
  };
  return {
    __esModule: true,
    default: ({ onReady }) => {
      ReactMock.useEffect(() => {
        if (onReady) onReady(fakeWs);
      }, [onReady]);
      return ReactMock.createElement('div', { 'data-testid': 'waveform' });
    },
  };
});

jest.mock('wavesurfer.js/dist/plugins/regions', () => ({
  __esModule: true,
  default: { create: () => ({}) },
}));

describe('UploadPanel', () => {
  it('renders workflow progress panel and upload controls', () => {
    render(<UploadPanel />);

    expect(screen.getByText('Upload audio')).toBeInTheDocument();
    expect(screen.getByText('Workflow Progress')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Upload to backend/i })).toBeDisabled();
  });

  it('displays all workflow stages in the progress panel', () => {
    render(<UploadPanel />);

    expect(screen.getByText('Upload')).toBeInTheDocument();
    expect(screen.getByText('Analysis')).toBeInTheDocument();
    expect(screen.getByText('Stem Separation')).toBeInTheDocument();
    expect(screen.getByText('Transcription')).toBeInTheDocument();
    expect(screen.getByText('Export')).toBeInTheDocument();
    expect(screen.getByText('0/5 completed')).toBeInTheDocument();
  });

  it('rejects unsupported files and displays error message', () => {
    render(<UploadPanel />);

    const fileInput = screen.getByLabelText(/upload audio/i);
    const unsupportedFile = new File(['hello'], 'test.txt', { type: 'text/plain' });

    fireEvent.change(fileInput, { target: { files: [unsupportedFile] } });

    expect(screen.getByRole('alert')).toHaveTextContent('Unsupported file type. Please upload WAV or MP3.');
    expect(screen.getByRole('button', { name: /Upload to backend/i })).toBeDisabled();
  });

  it('renders analysis summary cards when analysis completes', async () => {
    const uploadResponse = {
      file_id: 'abc-123',
      filename: 'track.wav',
      content_type: 'audio/wav',
      size: 100,
      artifact_url: '/uploads/track.wav',
      workflow_stages: [
        { stage: 'upload', status: 'completed', message: 'Upload completed successfully.' },
        { stage: 'analysis', status: 'pending', message: 'Analysis has not started yet.' },
      ],
    };

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        analysis: {
          status: 'completed',
          bpm: 118,
          key: 'D minor',
          structure: ['intro', 'verse', 'chorus', 'outro'],
          message: 'Analysis completed successfully.',
          task_id: 'task-123',
        },
        workflow_stages: [
          { stage: 'upload', status: 'completed', message: 'Upload completed successfully.' },
          { stage: 'analysis', status: 'completed', message: 'Analysis completed successfully.' },
        ],
      }),
    });

    const xhrMock = {
      open: jest.fn(),
      send: jest.fn(function send() {
        Object.defineProperty(this, 'status', { value: 200, configurable: true });
        Object.defineProperty(this, 'responseText', {
          value: JSON.stringify(uploadResponse),
          configurable: true,
        });
        if (typeof this.onload === 'function') {
          this.onload();
        }
      }),
      upload: { onprogress: null },
      setRequestHeader: jest.fn(),
    };
    jest.spyOn(global, 'XMLHttpRequest').mockImplementation(() => xhrMock);

    render(<UploadPanel />);

    const fileInput = screen.getByLabelText(/upload audio/i);
    const audioFile = new File(['RIFF....WAVE'], 'track.wav', { type: 'audio/wav' });
    fireEvent.change(fileInput, { target: { files: [audioFile] } });

    fireEvent.click(screen.getByRole('button', { name: /Upload to backend/i }));

    expect(await screen.findByLabelText('Analysis summary')).toBeInTheDocument();
    expect(screen.getByLabelText('BPM summary card')).toHaveTextContent('118');
    expect(screen.getByLabelText('Key summary card')).toHaveTextContent('D minor');
    expect(screen.getByLabelText('Structure summary card')).toHaveTextContent('intro, verse, chorus, outro');
  });

  it('chains stem separation after analysis and shows stems ready for review', async () => {
    const uploadResponse = {
      file_id: 'abc-123',
      filename: 'track.wav',
      content_type: 'audio/wav',
      size: 100,
      artifact_url: '/uploads/track.wav',
      workflow_stages: [
        { stage: 'upload', status: 'completed', message: 'Upload completed successfully.' },
        { stage: 'analysis', status: 'pending', message: 'Analysis has not started yet.' },
      ],
    };

    global.fetch = jest.fn().mockImplementation((url) => {
      if (url === '/api/analyze') {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            analysis: {
              status: 'completed',
              bpm: 118,
              key: 'D minor',
              structure: ['intro', 'verse', 'chorus', 'outro'],
              message: 'Analysis completed successfully.',
              task_id: 'task-123',
            },
            workflow_stages: [
              { stage: 'upload', status: 'completed' },
              { stage: 'analysis', status: 'completed' },
            ],
          }),
        });
      }
      if (url === '/api/separate') {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            stems: {
              status: 'completed',
              method: 'placeholder',
              message: 'Stem separation completed successfully.',
              stems: [
                { name: 'drums', url: '/uploads/stems/abc-123/drums.wav', format: 'wav' },
                { name: 'bass', url: '/uploads/stems/abc-123/bass.wav', format: 'wav' },
                { name: 'other', url: '/uploads/stems/abc-123/other.wav', format: 'wav' },
                { name: 'vocals', url: '/uploads/stems/abc-123/vocals.wav', format: 'wav' },
              ],
            },
            workflow_stages: [
              { stage: 'upload', status: 'completed' },
              { stage: 'analysis', status: 'completed' },
              { stage: 'stem_separation', status: 'completed' },
            ],
          }),
        });
      }
      return Promise.resolve({ ok: false, json: async () => ({}) });
    });

    const xhrMock = {
      open: jest.fn(),
      send: jest.fn(function send() {
        Object.defineProperty(this, 'status', { value: 200, configurable: true });
        Object.defineProperty(this, 'responseText', { value: JSON.stringify(uploadResponse), configurable: true });
        if (typeof this.onload === 'function') {
          this.onload();
        }
      }),
      upload: { onprogress: null },
      setRequestHeader: jest.fn(),
    };
    jest.spyOn(global, 'XMLHttpRequest').mockImplementation(() => xhrMock);

    render(<UploadPanel />);

    const fileInput = screen.getByLabelText(/upload audio/i);
    const audioFile = new File(['RIFF....WAVE'], 'track.wav', { type: 'audio/wav' });
    fireEvent.change(fileInput, { target: { files: [audioFile] } });

    fireEvent.click(screen.getByRole('button', { name: /Upload to backend/i }));

    expect(await screen.findByLabelText('Stem separation')).toBeInTheDocument();
    expect(await screen.findByLabelText('Stems ready for review')).toBeInTheDocument();
    const timeline = screen.getByLabelText('Stem timeline');
    expect(timeline).toBeInTheDocument();
    expect(timeline).toHaveTextContent('drums');
    expect(timeline).toHaveTextContent('bass');
    expect(timeline).toHaveTextContent('other');
    expect(timeline).toHaveTextContent('vocals');
    expect(screen.getAllByRole('button', { name: /Play /i })).toHaveLength(4);
  });

  it('shows stem separation failure state', async () => {
    const uploadResponse = {
      file_id: 'abc-123',
      filename: 'track.wav',
      content_type: 'audio/wav',
      size: 100,
      artifact_url: '/uploads/track.wav',
      workflow_stages: [
        { stage: 'upload', status: 'completed', message: 'Upload completed successfully.' },
        { stage: 'analysis', status: 'pending', message: 'Analysis has not started yet.' },
      ],
    };

    global.fetch = jest.fn().mockImplementation((url) => {
      if (url === '/api/analyze') {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            analysis: {
              status: 'completed',
              bpm: 118,
              key: 'D minor',
              structure: ['intro', 'verse', 'chorus', 'outro'],
              message: 'Analysis completed successfully.',
              task_id: 'task-123',
            },
            workflow_stages: [
              { stage: 'upload', status: 'completed' },
              { stage: 'analysis', status: 'completed' },
            ],
          }),
        });
      }
      if (url === '/api/separate') {
        return Promise.resolve({
          ok: false,
          json: async () => ({ message: 'Stem separation failed.', next_action: 'Retry stem separation.' }),
        });
      }
      return Promise.resolve({ ok: false, json: async () => ({}) });
    });

    const xhrMock = {
      open: jest.fn(),
      send: jest.fn(function send() {
        Object.defineProperty(this, 'status', { value: 200, configurable: true });
        Object.defineProperty(this, 'responseText', { value: JSON.stringify(uploadResponse), configurable: true });
        if (typeof this.onload === 'function') {
          this.onload();
        }
      }),
      upload: { onprogress: null },
      setRequestHeader: jest.fn(),
    };
    jest.spyOn(global, 'XMLHttpRequest').mockImplementation(() => xhrMock);

    render(<UploadPanel />);

    const fileInput = screen.getByLabelText(/upload audio/i);
    const audioFile = new File(['RIFF....WAVE'], 'track.wav', { type: 'audio/wav' });
    fireEvent.change(fileInput, { target: { files: [audioFile] } });

    fireEvent.click(screen.getByRole('button', { name: /Upload to backend/i }));

    expect(await screen.findByLabelText('Stem separation status: failed')).toBeInTheDocument();
    expect(screen.getAllByText(/Stem separation failed\./i).length).toBeGreaterThan(0);
  });

  it('renders timeline rows with accessibility labels and keyboard support', async () => {
    const uploadResponse = {
      file_id: 'abc-123',
      filename: 'track.wav',
      content_type: 'audio/wav',
      size: 100,
      artifact_url: '/uploads/track.wav',
      workflow_stages: [
        { stage: 'upload', status: 'completed', message: 'Upload completed successfully.' },
        { stage: 'analysis', status: 'pending', message: 'Analysis has not started yet.' },
      ],
    };

    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        analysis: {
          status: 'completed',
          bpm: 118,
          key: 'D minor',
          structure: ['intro', 'verse', 'chorus', 'outro'],
          message: 'Analysis completed successfully.',
          task_id: 'task-123',
        },
        workflow_stages: [
          { stage: 'upload', status: 'completed', message: 'Upload completed successfully.' },
          { stage: 'analysis', status: 'completed', message: 'Analysis completed successfully.' },
        ],
      }),
    });

    const xhrMock = {
      open: jest.fn(),
      send: jest.fn(function send() {
        Object.defineProperty(this, 'status', { value: 200, configurable: true });
        Object.defineProperty(this, 'responseText', {
          value: JSON.stringify(uploadResponse),
          configurable: true,
        });
        if (typeof this.onload === 'function') {
          this.onload();
        }
      }),
      upload: { onprogress: null },
      setRequestHeader: jest.fn(),
    };
    jest.spyOn(global, 'XMLHttpRequest').mockImplementation(() => xhrMock);

    render(<UploadPanel />);

    const fileInput = screen.getByLabelText(/upload audio/i);
    const audioFile = new File(['RIFF....WAVE'], 'track.wav', { type: 'audio/wav' });
    fireEvent.change(fileInput, { target: { files: [audioFile] } });

    fireEvent.click(screen.getByRole('button', { name: /Upload to backend/i }));

    const timeline = await screen.findByLabelText('Stem timeline');
    expect(timeline).toBeInTheDocument();

    // Accessibility labels present
    expect(screen.getByLabelText('Play drums')).toBeInTheDocument();
    expect(screen.getByLabelText('Play bass')).toBeInTheDocument();
    expect(screen.getByLabelText('Play other')).toBeInTheDocument();
    expect(screen.getByLabelText('Play vocals')).toBeInTheDocument();

    // Stem names displayed
    expect(timeline).toHaveTextContent('drums');
    expect(timeline).toHaveTextContent('bass');
    expect(timeline).toHaveTextContent('other');
    expect(timeline).toHaveTextContent('vocals');

    // Playback buttons present
    const playButtons = screen.getAllByRole('button', { name: /Play /i });
    expect(playButtons).toHaveLength(4);

    // Keyboard support: Space key toggles playback via the label change
    const drumsButton = screen.getByLabelText('Play drums');
    fireEvent.keyDown(drumsButton, { key: ' ' });
    expect(screen.getByLabelText('Pause drums')).toBeInTheDocument();
  });
});
