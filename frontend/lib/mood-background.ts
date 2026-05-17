import { setBackgroundMoodHint } from "@/lib/ambient-background";

const LOCAL_MOOD_OVERRIDE_UNTIL_KEY = "assistant.background.localMoodOverrideUntil";

type MoodPalette =
  | "calm-blue"
  | "warm-pink"
  | "focus-cyan"
  | "reflective-indigo"
  | "calm-teal"
  | "muted-amber";

type MoodHint = {
  mood: string;
  palette: MoodPalette;
};

export function inferMoodBackgroundFromMessage(message: string): MoodHint | null {
  const lower = message.toLowerCase();

  // Reset / stop simulation / back to normal should win first.
  if (
    /(udah|sudah|selesai|stop|berhenti|balik|normal|reset|udahan|cukup).{0,32}(simulasi|marah|kesel|mode|mood|normal|santai|calm|biasa)/i.test(lower) ||
    /(balik lagi|normal lagi|santai lagi|udah tenang|sudah tenang|ga marah lagi|nggak marah lagi|tidak marah lagi|udah biasa lagi)/i.test(lower)
  ) {
    return { mood: "calm", palette: "calm-blue" };
  }

  // Angry/annoyed, including simulation or roleplay.
  if (
    /(simulasi|simulate|roleplay|pura-pura|testing|test).{0,50}(marah|kesel|bete|emosi|angry|rage|ngamuk)/i.test(lower) ||
    /(marah|kesel|sebel|bete|emosi|ngamuk|rage|angry|annoyed|frustrated|gua marah|gue marah|aku marah|saya marah|iya gua marah|iya aku marah)/i.test(lower)
  ) {
    return { mood: "annoyed", palette: "muted-amber" };
  }

  if (/(panik|cemas|takut|khawatir|stress|stres|anxious|panic|overwhelmed|deg-degan|gelisah)/i.test(lower)) {
    return { mood: "stressed", palette: "calm-teal" };
  }

  if (/(happy|senang|bahagia|excited|semangat|love|romantis|sayang|hepi|happy banget|jatuh cinta)/i.test(lower)) {
    return { mood: "happy", palette: "warm-pink" };
  }

  if (/(mellow|sedih|galau|down|murung|refleksi|merenung|reflective|sad|melankolis)/i.test(lower)) {
    return { mood: "reflective", palette: "reflective-indigo" };
  }

  if (/(debug|coding|deploy|error|fix|teknis|serius|kerja|ngoding|production|build|terminal|backend|frontend)/i.test(lower)) {
    return { mood: "focused", palette: "focus-cyan" };
  }

  if (/(santai|chill|tenang|rileks|calm|ngobrol ringan|mode santai|slow dulu)/i.test(lower)) {
    return { mood: "calm", palette: "calm-blue" };
  }

  return null;
}

export function applyMoodBackgroundFromMessage(message: string) {
  const hint = inferMoodBackgroundFromMessage(message);
  if (!hint) return null;

  setBackgroundMoodHint(hint);

  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(
      LOCAL_MOOD_OVERRIDE_UNTIL_KEY,
      String(Date.now() + 45_000),
    );
  }

  return hint;
}

export function shouldRespectLocalMoodOverride(incomingMood?: string | null) {
  if (typeof window === "undefined") return false;

  const until = Number(window.sessionStorage.getItem(LOCAL_MOOD_OVERRIDE_UNTIL_KEY) || "0");
  if (!until || Date.now() > until) return false;

  // Prevent backend "calm/default" from instantly overriding an explicit local mood.
  return !incomingMood || incomingMood === "calm" || incomingMood === "default";
}
