"use client";

import { useCallback, useRef, useState } from "react";

import { transcribeAudioBlob } from "@/lib/voice-api";

type VoiceInputStatus = "idle" | "recording" | "transcribing";

function getSupportedMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;

  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];

  return candidates.find((type) => MediaRecorder.isTypeSupported(type));
}

export function useVoiceInput(options: { language?: string | null } = {}) {
  const [status, setStatus] = useState<VoiceInputStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  const cleanup = useCallback(() => {
    recorderRef.current = null;
    chunksRef.current = [];

    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
  }, []);

  const start = useCallback(async () => {
    if (status !== "idle") return;

    setError(null);

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      setError("Microphone recording is not supported in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const mimeType = getSupportedMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      recorder.onerror = () => {
        setError("Recording failed.");
        setStatus("idle");
        cleanup();
      };

      recorder.start();
      setStatus("recording");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Microphone permission was denied.");
      setStatus("idle");
      cleanup();
    }
  }, [cleanup, status]);

  const stopAndTranscribe = useCallback(async (): Promise<string | null> => {
    const recorder = recorderRef.current;
    if (!recorder || status !== "recording") return null;

    setError(null);

    return new Promise((resolve) => {
      recorder.onstop = async () => {
        setStatus("transcribing");

        try {
          const mimeType = recorder.mimeType || "audio/webm";
          const blob = new Blob(chunksRef.current, { type: mimeType });
          const result = await transcribeAudioBlob(blob, { language: options.language });
          resolve(result.text?.trim() || null);
        } catch (err) {
          setError(err instanceof Error ? err.message : "Transcription failed.");
          resolve(null);
        } finally {
          setStatus("idle");
          cleanup();
        }
      };

      recorder.stop();
    });
  }, [cleanup, options.language, status]);

  const cancel = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    setStatus("idle");
    cleanup();
  }, [cleanup]);

  return {
    status,
    error,
    isRecording: status === "recording",
    isTranscribing: status === "transcribing",
    start,
    stopAndTranscribe,
    cancel,
  };
}
