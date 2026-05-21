"use client";

import { useCallback, useEffect, useState } from "react";

import {
  playAvatarAudioBlob,
  playAvatarAudioResponse,
  playAvatarAudioUrl,
  stopAvatarAudioPlayback,
} from "@/lib/avatar-audio";

export function useAvatarAudioPlayer() {
  const [isPlaying, setIsPlaying] = useState(false);

  const attachLifecycle = useCallback((audio: HTMLAudioElement) => {
    setIsPlaying(true);

    const finish = () => setIsPlaying(false);

    audio.addEventListener("ended", finish, { once: true });
    audio.addEventListener("pause", finish, { once: true });
    audio.addEventListener("error", finish, { once: true });
  }, []);

  const playUrl = useCallback(
    async (sourceUrl: string, source = "voice") => {
      const audio = await playAvatarAudioUrl(sourceUrl, source);
      attachLifecycle(audio);
      return audio;
    },
    [attachLifecycle],
  );

  const playBlob = useCallback(
    async (blob: Blob, source = "voice") => {
      const audio = await playAvatarAudioBlob(blob, source);
      attachLifecycle(audio);
      return audio;
    },
    [attachLifecycle],
  );

  const playResponse = useCallback(
    async (response: Response, source = "voice") => {
      const audio = await playAvatarAudioResponse(response, source);
      attachLifecycle(audio);
      return audio;
    },
    [attachLifecycle],
  );

  const stop = useCallback(() => {
    stopAvatarAudioPlayback();
    setIsPlaying(false);
  }, []);

  useEffect(() => stop, [stop]);

  return {
    isPlaying,
    playUrl,
    playBlob,
    playResponse,
    stop,
  };
}
