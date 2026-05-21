export type AvatarActivityState = "idle" | "typing" | "speaking";

export type AvatarActivityDetail = {
  state: AvatarActivityState;
  source?: string;
};

export const AVATAR_ACTIVITY_EVENT = "assistant-avatar-activity";

export function emitAvatarActivity(state: AvatarActivityState, source = "app"): void {
  if (typeof window === "undefined") return;

  window.dispatchEvent(
    new CustomEvent<AvatarActivityDetail>(AVATAR_ACTIVITY_EVENT, {
      detail: { state, source },
    }),
  );
}

export function emitAvatarSpeakingStart(source = "voice"): void {
  emitAvatarActivity("speaking", source);
}

export function emitAvatarSpeakingEnd(source = "voice"): void {
  emitAvatarActivity("idle", source);
}

export function bindAvatarActivityToAudioElement(audio: HTMLAudioElement, source = "voice"): () => void {
  const onPlay = () => emitAvatarSpeakingStart(source);
  const onPlaying = () => emitAvatarSpeakingStart(source);
  const onPause = () => emitAvatarSpeakingEnd(source);
  const onEnded = () => emitAvatarSpeakingEnd(source);
  const onError = () => emitAvatarSpeakingEnd(source);

  audio.addEventListener("play", onPlay);
  audio.addEventListener("playing", onPlaying);
  audio.addEventListener("pause", onPause);
  audio.addEventListener("ended", onEnded);
  audio.addEventListener("error", onError);

  return () => {
    audio.removeEventListener("play", onPlay);
    audio.removeEventListener("playing", onPlaying);
    audio.removeEventListener("pause", onPause);
    audio.removeEventListener("ended", onEnded);
    audio.removeEventListener("error", onError);
  };
}
