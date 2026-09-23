'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useWavesurfer } from '@wavesurfer/react';
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions';
import { Pause, Play } from 'lucide-react';

type StemArtifact = {
  name: string;
  url: string;
  size?: number | null;
  format?: string | null;
  mime_type?: string | null;
  // Pre-computed waveform peaks for instant rendering (WaveSurfer v7)
  peaks?: (number[] | Float32Array)[];
  duration?: number;
};

type SelectedRegion = {
  id: string;
  start: number; // seconds
  end: number; // seconds
};

type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

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

const REGION_FILL = 'rgba(56, 189, 248, 0.18)';
const REGION_BORDER = '#38bdf8';
const REGION_STEP_SECONDS = 0.25;
const SAVE_DEBOUNCE_MS = 500;

type PlaybackWaveProps = {
  url: string;
  plugins: any[];
  peaks?: (number[] | Float32Array)[];
  duration?: number;
  onReady: (ws: any) => void;
  onPlay: (ws: any) => void;
  onPause: (ws: any) => void;
  onFinish: (ws: any) => void;
  onTimeupdate: (ws: any, t: number) => void;
  onError: (err: any) => void;
};

// Memoized so a per-tick time update never re-subscribes / re-creates the
// underlying WaveSurfer instance while a stem is playing (the timeupdate
// subscription re-renders this component, but its options are unchanged).
const PlaybackWave = React.memo(function PlaybackWave({
  url,
  plugins,
  peaks,
  duration,
  onReady,
  onPlay,
  onPause,
  onFinish,
  onTimeupdate,
  onError,
}: PlaybackWaveProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  // `useWavesurfer` hands back the live instance as component state, so this
  // component can register it deterministically and re-render without
  // re-creating it. That matters because the instance must NOT be discovered
  // via the `ready` event: when pre-computed `peaks` + `duration` are supplied
  // (the fast-path the worker feeds us), `load()` never awaits any I/O, so
  // WaveSurfer emits `ready` in the same microtask chain as `create()` — before
  // a listener attached on a later render could exist. Relying on `onReady`
  // alone left the timeline without a playable instance, so pressing Play did
  // nothing at all.
  const { wavesurfer } = useWavesurfer({
    container: containerRef,
    url,
    peaks,
    duration,
    height: 80,
    waveColor: '#334155',
    progressColor: '#38bdf8',
    cursorColor: '#38bdf8',
    plugins,
  });

  // `useWavesurfer` does not auto-subscribe the `onXxx` props the way
  // `WavesurferPlayer` does, so the stem's playback callbacks are wired here.
  // `onReady` is invoked both eagerly (as soon as the instance exists) and on
  // the `ready` event; the handler is idempotent, and this keeps instance
  // registration independent of event timing in either direction.
  useEffect(() => {
    if (!wavesurfer) return;
    onReady(wavesurfer);
    const unsubscribes = [
      wavesurfer.on('ready', () => onReady(wavesurfer)),
      wavesurfer.on('play', () => onPlay(wavesurfer)),
      wavesurfer.on('pause', () => onPause(wavesurfer)),
      wavesurfer.on('finish', () => onFinish(wavesurfer)),
      wavesurfer.on('timeupdate', (time: number) => onTimeupdate(wavesurfer, time)),
      wavesurfer.on('error', (err: unknown) => onError(err)),
    ];
    return () => unsubscribes.forEach((unsubscribe) => unsubscribe());
  }, [wavesurfer, onReady, onPlay, onPause, onFinish, onTimeupdate, onError]);

  return <div ref={containerRef} style={{ borderRadius: 6, overflow: 'hidden', minHeight: 80 }} />;
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
        peaks={stem.peaks}
        duration={stem.duration}
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

export default function StemTimeline({ stems, fileId }: { stems: StemArtifact[]; fileId?: string | null }) {
  const [mounted, setMounted] = useState(false);
  const [activeStem, setActiveStem] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, boolean>>({});

  // --- Region selection state (Story 3.2) ---
  const [regions, setRegions] = useState<SelectedRegion[]>([]);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');
  const [saveError, setSaveError] = useState<string | null>(null);

  // Refs
  const wavesurferMap = useRef<Map<string, any>>(new Map());
  const wsToName = useRef<WeakMap<object, string>>(new WeakMap());
  const callbacksByStem = useRef<Map<string, StemCallbacks>>(new Map());
  const regionPluginsRef = useRef<Map<string, any>>(new Map());
  const wiredRef = useRef<Set<string>>(new Set());
  const regionsRef = useRef<SelectedRegion[]>([]);
  const syncingRef = useRef(false);
  const saveTimerRef = useRef<number | null>(null);
  const durationRef = useRef(0);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Restore regions on mount (process restart persistence)
  useEffect(() => {
    if (!fileId) return;
    let cancelled = false;
    fetch(`/api/session/${encodeURIComponent(fileId)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((session) => {
        if (cancelled || !session) return;
        const stored = session.regions?.regions;
        if (!Array.isArray(stored) || stored.length === 0) return;
        const loaded: SelectedRegion[] = stored
          .filter((r: any) => typeof r?.start_ms === 'number' && typeof r?.end_ms === 'number')
          .map((r: any) => ({
            id: typeof r.id === 'string' ? r.id : `region-${r.start_ms}-${r.end_ms}`,
            start: r.start_ms / 1000,
            end: r.end_ms / 1000,
          }));
        if (loaded.length > 0) {
          regionsRef.current = loaded;
          setRegions(loaded);
          applyRegionsToPatches(loaded);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [fileId]);

  // Apply regions to all wave surfer instances
  const applyRegionsToPatches = useCallback((next: SelectedRegion[]) => {
    regionPluginsRef.current.forEach((plugin) => {
      if (!plugin || typeof plugin.getRegions !== 'function') return;
      let existing: any;
      try {
        existing = plugin.getRegions();
      } catch {
        return;
      }
      const seen = new Set<string>();
      next.forEach((region) => {
        seen.add(region.id);
        const current = existing.get ? existing.get(region.id) : undefined;
        if (!current) {
          if (typeof plugin.addRegion === 'function') {
            plugin.addRegion({
              id: region.id,
              start: region.start,
              end: region.end,
              color: REGION_FILL,
              drag: true,
              resize: true,
              minLength: 0.1,
            });
          }
        } else if (
          Math.abs(current.start - region.start) > 0.001 ||
          Math.abs(current.end - region.end) > 0.001
        ) {
          if (typeof current.setOptions === 'function') {
            current.setOptions({ start: region.start, end: region.end });
          }
        }
      });
      if (typeof existing.forEach === 'function') {
        const toRemove: string[] = [];
        existing.forEach((reg: any) => {
          if (!seen.has(reg.id)) toRemove.push(reg.id);
        });
        toRemove.forEach((id) => {
          const reg = existing.get ? existing.get(id) : undefined;
          if (reg && typeof reg.remove === 'function') reg.remove();
        });
      }
    });
  }, []);

  const wirePlugin = useCallback(
    (name: string) => {
      const plugin = regionPluginsRef.current.get(name);
      if (!plugin || wiredRef.current.has(name)) return;
      wiredRef.current.add(name);
      if (typeof plugin.enableDragSelection === 'function') {
        try {
          plugin.enableDragSelection({ color: REGION_FILL });
        } catch {
          // drag-to-create is progressive enhancement
        }
      }
      if (typeof plugin.on === 'function') {
        plugin.on('region-created', (region: any) => {
          if (syncingRef.current) return;
          const current = regionsRef.current;
          if (!current.some((r) => r.id === region.id)) {
            const next = [...current, { id: region.id, start: Number(region.start ?? 0), end: Number(region.end ?? 0) }];
            regionsRef.current = next;
            setRegions(next);
          }
        });
        plugin.on('region-updated', (region: any) => {
          if (syncingRef.current) return;
          const current = regionsRef.current;
          const next = current.map((r) =>
            r.id === region.id ? { ...r, start: Number(region.start ?? 0), end: Number(region.end ?? 0) } : r,
          );
          regionsRef.current = next;
          setRegions(next);
        });
        plugin.on('region-removed', (region: any) => {
          if (syncingRef.current) return;
          const current = regionsRef.current;
          const next = current.filter((r) => r.id !== region.id);
          regionsRef.current = next;
          setRegions(next);
        });
      }
    }, []);

  const persistRegions = useCallback(async (next: SelectedRegion[]) => {
    if (!fileId) return;
    try {
      await fetch(`/api/session/${encodeURIComponent(fileId)}/regions`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({
          regions: next.map((region) => ({
            id: region.id,
            start_ms: Math.round(region.start * 1000),
            end_ms: Math.round(region.end * 1000),
          })),
        }),
      });
    } catch {
      // background save - non-blocking
    }
  }, [fileId]);

  // Debounce and persist regions
  useEffect(() => {
    const timer = window.setTimeout(() => {
      persistRegions(regions);
    }, SAVE_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [regions, persistRegions]);

  const stemPluginArrays = useMemo(() => {
    const map = new Map<string, any[]>();
    stems.forEach((stem) => {
      let plugin = regionPluginsRef.current.get(stem.name);
      if (!plugin) {
        plugin = RegionsPlugin.create();
        regionPluginsRef.current.set(stem.name, plugin);
      }
      map.set(stem.name, [plugin]);
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
        wirePlugin(name);
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

      {/* Region selection UI (Story 3.2) */}
      <section
        aria-label="Region selection"
        style={{
          display: 'grid',
          gap: '0.5rem',
          padding: '0.9rem',
          borderRadius: 10,
          background: '#111827',
          border: `1px solid ${regions.length > 0 ? '#38bdf8' : '#334155'}`,
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <strong style={{ color: '#f8fafc' }}>Selected Regions</strong>
          <span aria-label="Region summary" style={{ color: '#94a3b8', fontSize: '0.85rem' }}>
            {regions.length} region{regions.length === 1 ? '' : 's'} · {formatTime(regions.reduce((s, r) => s + (r.end - r.start), 0))} selected
          </span>
        </div>

        {regions.length > 0 && (
          <ul aria-label="Region list" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'grid', gap: '0.25rem' }}>
            {regions.map((region, index) => {
              const label = `Region ${index + 1}, ${formatTime(region.start)} to ${formatTime(region.end)}`;
              return (
                <li key={region.id}>
                  <div
                    role="region"
                    tabIndex={0}
                    aria-label={`${label}. Use arrow keys to nudge, Delete to remove.`}
                    onKeyDown={(e) => {
                      if (e.key === 'Delete' || e.key === 'Backspace') {
                        e.preventDefault();
                        setRegions((prev) => prev.filter((r) => r.id !== region.id));
                      }
                      if (e.key === 'ArrowLeft') {
                        e.preventDefault();
                        setRegions((prev) =>
                          prev.map((r) => r.id === region.id ? { ...r, start: Math.max(0, r.start - 0.25) } : r),
                        );
                      }
                      if (e.key === 'ArrowRight') {
                        e.preventDefault();
                        setRegions((prev) =>
                          prev.map((r) => r.id === region.id ? { ...r, end: r.end + 0.25 } : r),
                        );
                      }
                    }}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                      padding: '0.45rem 0.6rem',
                      borderRadius: 8,
                      background: '#0f172a',
                      border: '1px solid #334155',
                    }}
                  >
                    <span style={{ color: '#e2e8f0', fontSize: '0.85rem' }}>{label}</span>
                    <span style={{ color: '#64748b', fontSize: '0.75rem' }}>{formatTime(region.end - region.start)}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}
