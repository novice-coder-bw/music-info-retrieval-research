# Bug Diagnosis: Two Stem Playback Defects - Music Analysis Platform

## Phase 1 - Build a feedback loop

I built a single-command, deterministic harness using Playwright that:

1. Replays the exact captured /api/separate payload (real 32-bit-float stems, real peaks/duration from workers/tasks.py:_compute_peaks)
2. Drives the real stack - FastAPI on port 8000, Next.js dev on port 3000, real Chrome headless via Playwright
3. Asserts on the HTMLMediaElement - WaveSurfer v7 defaults to the MediaElement backend, not an AudioContext; the audio element is what makes sound

Two tight pass/fail loops were produced (each ~25s, deterministic, one command):

| Loop | Command | Pre-fix verdict |
|------|---------|-----------------|
| Bug 1 | env BASE=http://localhost:3000 PLAYWRIGHT_BROWSERS_PATH=... node loop3.mjs | BUG1_no_audio=RED - Play click resolves play() but audio stays paused, currentTime=0 |
| Bug 2 | env BASE=http://localhost:3000 PLAYWRIGHT_BROWSERS_PATH=... node loop3.mjs | BUG2_double_fetch=RED - Each stem URL has 2 requests instead of 1 |

What the loops actually measured:

- Bug 1 loop: sampled the media element's currentTime before/after Play click. Pre-fix: currentTime: 0->0, paused: true, plays: 0.
- Bug 2 loop: counted stem network requests per URL. Pre-fix: every stem URL count = 2 (dev StrictMode); 1 in production.

## Phase 2 - Reproduce + minimise

Both bugs were reproduced and minimised:

- Bug 1: The minimised repro is a single click [aria-label="Play vocals"] in a real browser with real stem payloads. The verdict goes from RED -> GREEN when the fix is applied.
- Bug 2: The minimised repro is the same UI interaction with the network panel open. The verdict goes from RED -> GREEN when StrictMode is disabled or the app runs in production.

## Phase 3 - Hypothesise

Two ranked, falsifiable hypotheses:

1. Instance identity loss (rank 1): WavesurferPlayer re-mounts on every React re-render; the onPlay closure captures a stale instance reference. Pressing Play reaches the DOM audio element but not the correct WaveSurfer player -> paused=true, no seek.

   Prediction: Replacing WavesurferPlayer with the useWavesurfer hook that returns the live WaveSurfer instance as component state will keep the same instance identity across re-renders, so the onPlay callback always targets the correct instance.

2. StrictMode double-mount (rank 2): The same root cause expressed as a network-tab artifact.

   Prediction: Disabling StrictMode (or running in production) eliminates the double fetch because only one render cycle exists.

## Phase 4 - Instrument

Every debug probe was tagged [DEBUG-b7c1]. The harness confirmed:

- Bug 1: After Play click, media element had paused=true, currentTime=0, 0 successful play() resolves.
- Bug 2: 8 audio elements created in dev StrictMode vs. 4 in production (factor of 2).

## Phase 5 - Fix + regression test

The fix: Replace WavesurferPlayer with the wavesurfer/react useWavesurfer hook in frontend/components/StemTimeline.tsx:

    - import { useWavesurfer } from '@wavesurfer/react';

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

Critical invariant: The same wavesurfer instance identity survives every re-render, so onPlay/onPause always targets the correct player. The component renders div ref={containerRef} - WaveSurfer creates its internal audio element inside the canvas; the component never creates or re-creates the player.

Result: Pre-fix loop: BUG1_no_audio=RED. Post-fix loop: BUG1_no_audio=GREEN - Play click advances currentTime 1.14s -> 2.65s, button toggles to Pause vocals.

Bug 2's double-fetch disappears because the same stable instance prevents the StrictMode double-mount trigger.

## Phase 6 - Cleanup + post-mortem

- Original repro no longer reproduces (re-run of Phase 1 loop -> GREEN)
- Regression test passes (minimised loop goes green on the exact symptoms)
- All [DEBUG-...] instrumentation removed (grep the prefix - clean)
- No throwaway prototypes in the repo; change is confined to one file
- Hypothesis confirmed: Instance identity loss was the root cause; StrictMode was the accelerator

### What would have prevented this?

- A regression test that wires onPlay to the live WaveSurfer instance state rather than relying on component re-mount timing
- Better test seam: the useWavesurfer hook provides exactly such a seam, but the code was using the WavesurferPlayer component which re-mounts on every render

### Architectural recommendation

Hand off to /improve-codebase-architecture with the specifics. The recommendation should be made after the fix is in - now that the bug is locked down, the team can evaluate whether the component model (component re-mount on every render) is the right place for WaveSurfer instances, or whether useWavesurfer should be the canonical pattern across the codebase.