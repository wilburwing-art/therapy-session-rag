"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type RecorderState = "idle" | "requesting" | "recording" | "paused" | "review";

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function AudioRecorder({
  onComplete,
  disabled,
}: {
  onComplete: (blob: Blob) => void | Promise<void>;
  disabled?: boolean;
}) {
  const [state, setState] = useState<RecorderState>("idle");
  const [duration, setDuration] = useState(0);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<number | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animationRef = useRef<number | null>(null);

  const cleanup = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (animationRef.current !== null) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => undefined);
      audioCtxRef.current = null;
    }
    analyserRef.current = null;
  }, []);

  useEffect(() => cleanup, [cleanup]);

  async function start() {
    setError(null);
    setState("requesting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
        },
      });
      streamRef.current = stream;

      const AudioCtx =
        window.AudioContext ??
        (window as unknown as { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;
      if (AudioCtx) {
        const ctx = new AudioCtx();
        const src = ctx.createMediaStreamSource(stream);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        src.connect(analyser);
        audioCtxRef.current = ctx;
        analyserRef.current = analyser;
        const buffer = new Uint8Array(analyser.frequencyBinCount);
        const tick = () => {
          if (!analyserRef.current) return;
          analyserRef.current.getByteFrequencyData(buffer);
          let sum = 0;
          for (const v of buffer) sum += v;
          setLevel(Math.min(1, sum / buffer.length / 120));
          animationRef.current = requestAnimationFrame(tick);
        };
        tick();
      }

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/webm")
          ? "audio/webm"
          : "";
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (ev) => {
        if (ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      recorder.onstop = () => {
        const finalBlob = new Blob(chunksRef.current, {
          type: recorder.mimeType || "audio/webm",
        });
        setBlob(finalBlob);
        setState("review");
      };
      recorder.start(1000);
      mediaRecorderRef.current = recorder;

      setDuration(0);
      timerRef.current = window.setInterval(() => {
        setDuration((d) => d + 1);
      }, 1000);
      setState("recording");
    } catch (err) {
      cleanup();
      setState("idle");
      setError(
        err instanceof DOMException && err.name === "NotAllowedError"
          ? "Microphone permission denied."
          : "Couldn't access the microphone.",
      );
    }
  }

  function pause() {
    mediaRecorderRef.current?.pause();
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    setState("paused");
  }

  function resume() {
    mediaRecorderRef.current?.resume();
    timerRef.current = window.setInterval(() => {
      setDuration((d) => d + 1);
    }, 1000);
    setState("recording");
  }

  function stop() {
    mediaRecorderRef.current?.stop();
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (animationRef.current !== null) {
      cancelAnimationFrame(animationRef.current);
      animationRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }

  function discard() {
    setBlob(null);
    setDuration(0);
    setState("idle");
  }

  async function submit() {
    if (!blob) return;
    await onComplete(blob);
  }

  const sizeMB = blob ? blob.size / (1024 * 1024) : 0;
  const tooBig = sizeMB > 95;

  return (
    <div>
      <div className="flex items-center gap-4">
        <span className="font-mono text-2xl tabular-nums">
          {formatDuration(duration)}
        </span>
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-200">
          <div
            className="h-full bg-brand-600 transition-[width]"
            style={{ width: `${Math.round(level * 100)}%` }}
          />
        </div>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {state === "idle" && (
          <button
            onClick={start}
            disabled={disabled}
            className="w-full rounded-md bg-red-600 px-4 py-3 text-sm text-white hover:bg-red-700 disabled:opacity-50 sm:w-auto"
          >
            ● Start recording
          </button>
        )}
        {state === "requesting" && (
          <p className="text-sm text-slate-600">Requesting microphone…</p>
        )}
        {state === "recording" && (
          <>
            <button
              onClick={pause}
              className="flex-1 rounded-md border border-slate-300 px-4 py-3 text-sm hover:bg-slate-50 sm:flex-none"
            >
              ‖ Pause
            </button>
            <button
              onClick={stop}
              className="flex-1 rounded-md bg-slate-900 px-4 py-3 text-sm text-white hover:bg-slate-700 sm:flex-none"
            >
              ■ Stop
            </button>
          </>
        )}
        {state === "paused" && (
          <>
            <button
              onClick={resume}
              className="flex-1 rounded-md bg-red-600 px-4 py-3 text-sm text-white hover:bg-red-700 sm:flex-none"
            >
              ● Resume
            </button>
            <button
              onClick={stop}
              className="flex-1 rounded-md bg-slate-900 px-4 py-3 text-sm text-white hover:bg-slate-700 sm:flex-none"
            >
              ■ Stop
            </button>
          </>
        )}
        {state === "review" && blob && (
          <>
            <audio
              controls
              src={URL.createObjectURL(blob)}
              className="w-full"
            />
            <div className="flex w-full flex-wrap items-center justify-between gap-2 text-sm text-slate-600">
              <span>
                {formatDuration(duration)} · {sizeMB.toFixed(1)} MB
              </span>
              {tooBig && (
                <span className="text-red-600">
                  File is large — uploads over 100 MB aren&apos;t supported
                </span>
              )}
            </div>
            <div className="flex w-full flex-col gap-2 sm:flex-row">
              <button
                onClick={discard}
                disabled={disabled}
                className="w-full rounded-md border border-slate-300 px-4 py-3 text-sm hover:bg-slate-50 disabled:opacity-50 sm:w-auto"
              >
                Discard
              </button>
              <button
                onClick={submit}
                disabled={disabled || tooBig}
                className="w-full rounded-md bg-brand-600 px-4 py-3 text-sm text-white hover:bg-brand-700 disabled:opacity-50 sm:w-auto"
              >
                Upload recording
              </button>
            </div>
          </>
        )}
      </div>

      {error && (
        <p className="mt-3 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
