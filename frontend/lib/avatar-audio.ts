import {
  bindAvatarActivityToAudioElement,
  emitAvatarSpeakingEnd,
  emitAvatarSpeakingStart,
} from "@/lib/avatar-activity";

let activeAvatarAudioCleanup: (() => void) | null = null;
let activeAvatarAudioElement: HTMLAudioElement | null = null;

function createPlaybackError(error: unknown): Error {
  const name = error instanceof DOMException ? error.name : "";
  const message = error instanceof Error ? error.message : "";

  if (
    name === "NotAllowedError" ||
    /not allowed|permission|user agent|platform/i.test(message)
  ) {
    return new Error("Safari memblokir audio playback. Tap Speak sekali lagi atau cek permission audio browser.");
  }

  if (name === "NotSupportedError") {
    return new Error("Format audio belum bisa diputar oleh browser ini.");
  }

  return new Error("Audio belum bisa diputar. Coba tap Speak lagi.");
}

function cleanupActiveAvatarAudio(): void {
  if (activeAvatarAudioCleanup) {
    activeAvatarAudioCleanup();
    activeAvatarAudioCleanup = null;
  }

  if (activeAvatarAudioElement) {
    activeAvatarAudioElement.pause();
    activeAvatarAudioElement.src = "";
    activeAvatarAudioElement.load();
    activeAvatarAudioElement = null;
  }

  emitAvatarSpeakingEnd("voice");
}

export function stopAvatarAudioPlayback(): void {
  cleanupActiveAvatarAudio();
}

export function createAvatarBoundAudioElement(sourceUrl: string, source = "voice"): HTMLAudioElement {
  cleanupActiveAvatarAudio();

  const audio = new Audio(sourceUrl);
  audio.preload = "auto";

  activeAvatarAudioCleanup = bindAvatarActivityToAudioElement(audio, source);
  activeAvatarAudioElement = audio;

  return audio;
}

export async function playAvatarAudioUrl(sourceUrl: string, source = "voice"): Promise<HTMLAudioElement> {
  const audio = createAvatarBoundAudioElement(sourceUrl, source);

  try {
    emitAvatarSpeakingStart(source);
    await audio.play();
    return audio;
  } catch (error) {
    cleanupActiveAvatarAudio();
    throw createPlaybackError(error);
  }
}

export async function playAvatarAudioBlob(blob: Blob, source = "voice"): Promise<HTMLAudioElement> {
  const objectUrl = URL.createObjectURL(blob);
  const audio = createAvatarBoundAudioElement(objectUrl, source);

  const revokeObjectUrl = () => URL.revokeObjectURL(objectUrl);
  audio.addEventListener("ended", revokeObjectUrl, { once: true });
  audio.addEventListener("error", revokeObjectUrl, { once: true });

  try {
    emitAvatarSpeakingStart(source);
    await audio.play();
    return audio;
  } catch (error) {
    revokeObjectUrl();
    cleanupActiveAvatarAudio();
    throw createPlaybackError(error);
  }
}

export async function playAvatarAudioResponse(response: Response, source = "voice"): Promise<HTMLAudioElement> {
  if (!response.ok) {
    throw new Error(`Audio response failed: ${response.status}`);
  }

  const blob = await response.blob();
  return playAvatarAudioBlob(blob, source);
}
