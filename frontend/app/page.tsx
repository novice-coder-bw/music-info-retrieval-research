import React from 'react';
import UploadPanel from '../components/UploadPanel';

export default function Home() {
  return (
    <main style={{ padding: '2rem', fontFamily: 'system-ui, sans-serif' }}>
      <h1>Music Analysis Platform</h1>
      <p>Upload WAV or MP3 files, track upload progress, and start the audio analysis workflow.</p>
      <section style={{ marginTop: '2rem' }}>
        <UploadPanel />
      </section>
    </main>
  );
}
