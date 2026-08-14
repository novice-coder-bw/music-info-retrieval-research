'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import WavesurferPlayer from '@wavesurfer/react';
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions';
import { Pause, Play } from 'lucide-react';

type StemArtifact = {
  name: string;
  url: string;
  size?: number | null;
  format?: string | null;
  mime_type?: string | null;
};

// The backend serves audio under /uploads/... on a DIFFERENT origin than the
// frontend. To stay same-origin (no CORS) and reuse the proxy-route pattern,
// route stem audio through the Next.js /api/uploads proxy.
function resolveAudioUrl(url: string): string {
  if (!url) return url;
  return url.startsWith('/uploads/') ? `/api${url}` : url;
}

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

type PlaybackWaveProps = {
  url: string;
  plugins: any[];
  onReady: (ws: any) => void;
  onPlay: (ws: any) => void;
  onPause: (ws: any) => void;
  onFinish: (ws: any) => void;
  onTimeupdate: (ws: any, t: number) => void;
  onError: (err: any) => void;
};

// Memoized so a per-tick time update never re-renders / re-subscribes the
// underlying WaveSurfer instance while a stem is playing.
const PlaybackWave = React.memo(function PlaybackWave({
  url,
  plugins,
  onReady,
  onPlay,
  onPause,
  onFinish,
  onTimeupdate,
  onError,
}: PlaybackWaveProps) {
  return (
    <div style={{ borderRadius: 6, overflow: 'hidden', minHeight: 80 }}>
      <WavesurferPlayer
        url={url}
        height={80}
        waveColor="#334155"
        progressColor="#38bdf8"
        cursorColor="#38bdf8"
        plugins={plugins}
        onReady={onReady}
        onPlay={onPlay}
        onPause={onPause}
        onTimeupdate={onTimeupdate}
        onFinish={onFinish}
        onError={onError}
      />
    </div>
  );
});

type StemCallbacks = {
  onReady: (ws: any) => void;
  onPlay: () => void;
  onPause: (ws: any) => void;
  onFinish: (ws: any) => void;
  onError: (err: unknown) => void;
  onToggle: () => void;
  onKeyDown: (e: React.KeyboardEvent<HTMLButtonElement>) => void;
};

type StemRowProps = {
  stem: StemArtifact;
  plugins: unknown[];
  callbacks: StemCallbacks;
  isActive: boolean;
  hasError: boolean;
};

function StemRow({ stem, plugins, callbacks, isActive, hasError }: StemRowProps) {
  // Per-row time display is intentionally local so only this row re-renders on
  // each audio tick; the memoized PlaybackWave stays put (no re-subscription).
  const [time, setTime] = useState(0);
  const handleTime = useCallback((_ws: any, t: number) => setTime(t), []);
  void plugins;

  return (
    <div
      role="group"
      aria-label={stem.name}
      style={{
        display: 'grid',
        gap: '0.5rem',
        padding: '0.75rem',
        borderRadius: 8,
        background: '#111827',
        border: `1px solid ${isActive ? '#38bdf8' : '#334155'}`,
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          gap: '0.75rem',
        }}
      >
        <strong style={{ color: '#f8fafc' }}>{stem.name}</strong>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span
            aria-hidden="true"
            style={{
              color: '#94a3b8',
              fontSize: '0.85rem',
              fontVariantNumeric: 'tabular-nums',
            }}
          >
            {formatTime(time)}
          </span>
          <button
            type="button"
            onClick={callbacks.onToggle}
            onKeyDown={callbacks.onKeyDown}
            aria-pressed={isActive}
            aria-label={`${isActive ? 'Pause' : 'Play'} ${stem.name}`}
            style={{
              padding: '0.35rem 0.75rem',
              borderRadius: 6,
              background: isActive ? '#22c55e' : '#38bdf8',
              color: '#0f172a',
              border: 'none',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.85rem',
            }}
          >
            {isActive ? <Pause size={16} aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}
          </button>
        </div>
      </div>
      {hasError && (
        <p role="alert" style={{ margin: 0, color: '#f8b4b4', fontSize: '0.85rem' }}>
          Unable to load {stem.name} audio.
        </p>
      )}
      <PlaybackWave
        url={resolveAudioUrl(stem.url)}
        plugins={plugins}
        onReady={callbacks.onReady}
        onPlay={callbacks.onPlay}
        onPause={callbacks.onPause}
        onFinish={callbacks.onFinish}
        onTimeupdate={handleTime}
        onError={callbacks.onError}
      />
    </div>
  );
}

export default function StemTimeline({ stems }: { stems: StemArtifact[] }) {
  const [mounted, setMounted] = useState(false);
  const [activeStem, setActiveStem] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, boolean>>({});
  const wavesurferMap = useRef<Map<string, any>>(new Map());
  const wsToName = useRef<WeakMap<object, string>>(new WeakMap());
  const callbacksByStem = useRef<Map<string, StemCallbacks>>(new Map());

  useEffect(() => {
    setMounted(true);
  }, []);

  const stemPluginArrays = useMemo(() => {
    const map = new Map<string, any[]>();
    stems.forEach((stem) => {
      if (!map.has(stem.name)) map.set(stem.name, [RegionsPlugin.create()]);
    });
    return map;
  }, [stems]);

  // Build a stable set of callbacks per stem, created once. Held in a ref so
  // their identities never change across re-renders (keeps PlaybackWave memoized
  // and avoids re-subscribing WaveSurfer on every audio tick).
  const getCallbacks = useCallback((name: string): StemCallbacks => {
    const cached = callbacksByStem.current.get(name);
    if (cached) return cached;

    const callbacks = {
      onReady: (ws: any) => {
        wavesurferMap.current.set(name, ws);
        wsToName.current.set(ws, name);
        setErrors((prev) => (prev[name] ? { ...prev, [name]: false } : prev));
      },
      onPlay: () => {
        wavesurferMap.current.forEach((otherWs, otherName) => {
          if (otherName !== name) otherWs.pause();
        });
        setActiveStem(name);
      },
      onPause: (ws: any) => {
        const owner = wsToName.current.get(ws);
        setActiveStem((cur) => (cur === owner ? null : cur));
      },
      onFinish: (ws: any) => {
        const owner = wsToName.current.get(ws);
        setActiveStem((cur) => (cur === owner ? null : cur));
      },
      onError: () => {
        setErrors((prev) => ({ ...prev, [name]: true }));
        setActiveStem((cur) => (cur === name ? null : cur));
      },
      onToggle: () => {
        const ws = wavesurferMap.current.get(name);
        if (!ws) return;

        if (ws.isPlaying()) {
          ws.pause();
          setActiveStem((cur) => (cur === name ? null : cur));
          return;
        }

        // Pause any other playing stem and sync the playhead position.
        let sourceTime = 0;
        wavesurferMap.current.forEach((otherWs, otherName) => {
          if (otherName !== name && otherWs.isPlaying()) {
            sourceTime = otherWs.getCurrentTime();
            otherWs.pause();
          }
        });

        if (sourceTime > 0) {
          const duration = ws.getDuration();
          if (duration > 0) ws.seekTo(sourceTime / duration);
        }

        ws.play();
        setActiveStem(name);
      },
    };

    const fullCallbacks = callbacks as unknown as StemCallbacks;
    fullCallbacks.onKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>) => {
      if (e.repeat) return; // ignore held-key auto-repeat toggling
      if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        fullCallbacks.onToggle();
      }
    };

    callbacksByStem.current.set(name, fullCallbacks);
    return fullCallbacks;
  }, []);

  if (!mounted) {
    return (
      <div
        role="status"
        style={{ padding: '1rem', borderRadius: 10, background: '#0f172a', color: '#94a3b8' }}
      >
        Loading timeline...
      </div>
    );
  }

  return (
    <div
      role="group"
      aria-label="Stem timeline"
      style={{
        display: 'grid',
        gap: '0.75rem',
        padding: '0.9rem',
        borderRadius: 10,
        background: '#0f172a',
      }}
    >
      {stems.map((stem) => (
        <StemRow
          key={stem.name}
          stem={stem}
          plugins={stemPluginArrays.get(stem.name) || []}
          callbacks={getCallbacks(stem.name)}
          isActive={activeStem === stem.name}
          hasError={!!errors[stem.name]}
        />
      ))}
    </div>
  );
}
