import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import UploadPanel from './UploadPanel';

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
});
