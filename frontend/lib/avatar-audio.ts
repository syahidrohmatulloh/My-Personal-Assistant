import {
  bindAvatarActivityToAudioElement,
  emitAvatarSpeakingEnd,
  emitAvatarSpeakingStart,
} from "@/lib/avatar-activity";

let activeAvatarAudioCleanup: (() => void) | null = null;
let activeAvatarAudioElement: HTMLAudioElement | null = null;

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
    throw error;
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
    throw error;
  }
}

export async function playAvatarAudioResponse(response: Response, source = "voice"): Promise<HTMLAudioElement> {
  if (!response.ok) {
    throw new Error(`Audio response failed: ${response.status}`);
  }

  const blob = await response.blob();
  return playAvatarAudioBlob(blob, source);
}
