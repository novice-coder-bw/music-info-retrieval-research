import '../styles/globals.css';
import React from 'react';

export const metadata = {
  title: 'Music Analysis Platform',
  description: 'Upload a song and begin the audio analysis workflow.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
