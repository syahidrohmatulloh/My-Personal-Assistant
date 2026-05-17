import { setBackgroundMoodHint } from "@/lib/ambient-background";
import {
  getCompanionMoodState,
  putCompanionMoodState,
  type CompanionMoodStateApi,
} from "@/lib/api";

export type CompanionMood =
  | "calm"
  | "affectionate"
  | "romantic"
  | "playful"
  | "jealous_playful"
  | "clingy"
  | "annoyed"
  | "hurt"
  | "concerned"
  | "focused"
  | "reassured"
  | "withdrawn_soft";

export type CompanionMoodState = CompanionMoodStateApi & {
  mood: CompanionMood;
};

type Palette =
  | "calm-blue"
  | "warm-pink"
  | "focus-cyan"
  | "reflective-indigo"
  | "calm-teal"
  | "muted-amber";

export type MoodScores = Record<CompanionMood, number>;

const MOODS: CompanionMood[] = [
  "calm",
  "affectionate",
  "romantic",
  "playful",
  "jealous_playful",
  "clingy",
  "annoyed",
  "hurt",
  "concerned",
  "focused",
  "reassured",
  "withdrawn_soft",
];

function emptyMoodScores(): MoodScores {
  return {
    calm: 0,
    affectionate: 0,
    romantic: 0,
    playful: 0,
    jealous_playful: 0,
    clingy: 0,
    annoyed: 0,
    hurt: 0,
    concerned: 0,
    focused: 0,
    reassured: 0,
    withdrawn_soft: 0,
  };
}

function defaultMoodScores(mood: CompanionMood = "calm", intensity = 2): MoodScores {
  const scores = emptyMoodScores();
  scores[mood] = intensity;
  if (mood !== "calm") scores.calm = Math.max(0, 3 - Math.floor(intensity / 3));
  return scores;
}

function normalizeMoodScores(input?: Record<string, number> | null): MoodScores {
  const scores = emptyMoodScores();

  for (const mood of MOODS) {
    const raw = input?.[mood];
    scores[mood] = Number.isFinite(raw) ? Math.max(0, Math.min(10, Number(raw))) : 0;
  }

  return scores;
}

function blendMoodScores(
  previous: Record<string, number> | undefined,
  target: Partial<Record<CompanionMood, number>>,
  carry = 0.45,
): MoodScores {
  const prev = normalizeMoodScores(previous);
  const next = emptyMoodScores();

  for (const mood of MOODS) {
    const targetValue = target[mood] ?? 0;
    next[mood] = Math.round(Math.max(0, Math.min(10, prev[mood] * carry + targetValue * (1 - carry))));
  }

  for (const [mood, value] of Object.entries(target) as [CompanionMood, number][]) {
    next[mood] = Math.max(next[mood], Math.max(0, Math.min(10, Math.round(value))));
  }

  return next;
}

function dominantMoodFromScores(scores: MoodScores): CompanionMood {
  let winner: CompanionMood = "calm";
  let best = -1;

  for (const mood of MOODS) {
    if (scores[mood] > best) {
      best = scores[mood];
      winner = mood;
    }
  }

  return winner;
}

function intensityFromScores(scores: MoodScores, mood: CompanionMood) {
  return Math.max(1, Math.min(10, Math.round(scores[mood] || 1)));
}

function affectFromScores(scores: MoodScores) {
  const positive =
    scores.affectionate * 0.7 +
    scores.romantic * 0.9 +
    scores.playful * 0.65 +
    scores.reassured * 0.75 +
    scores.calm * 0.35;

  const negative =
    scores.annoyed * 0.75 +
    scores.hurt * 0.65 +
    scores.jealous_playful * 0.35 +
    scores.withdrawn_soft * 0.45;

  const arousal =
    scores.romantic * 0.05 +
    scores.playful * 0.06 +
    scores.jealous_playful * 0.07 +
    scores.annoyed * 0.08 +
    scores.focused * 0.05 +
    scores.concerned * 0.04;

  return {
    valence: clamp((positive - negative) / 10, -1, 1),
    arousal: clamp(0.18 + arousal, 0, 1),
    warmth: clamp(0.45 + (scores.affectionate + scores.romantic + scores.concerned + scores.reassured) / 40, 0, 1),
    playfulness: clamp(0.18 + (scores.playful + scores.jealous_playful + scores.romantic * 0.4) / 28, 0, 1),
    insecurity: clamp((scores.jealous_playful + scores.clingy + scores.hurt + scores.annoyed * 0.4) / 38, 0, 1),
  };
}

function buildHybridPatch(
  previous: CompanionMoodState,
  targetScores: Partial<Record<CompanionMood, number>>,
  reason: string,
  trigger: string,
  source: string,
  expiresMinutes: number,
  carry = 0.45,
): Partial<CompanionMoodState> {
  const mood_scores = blendMoodScores(previous.mood_scores, targetScores, carry);
  const mood = dominantMoodFromScores(mood_scores);
  const intensity = intensityFromScores(mood_scores, mood);
  const affect = affectFromScores(mood_scores);

  return {
    mood,
    intensity,
    mood_scores,
    valence: affect.valence,
    arousal: affect.arousal,
    warmth: affect.warmth,
    playfulness: affect.playfulness,
    insecurity: affect.insecurity,
    reason,
    last_trigger: trigger,
    source,
    expires_at: minutesFromNow(expiresMinutes),
  };
}


const GLOBAL_STATE_KEY = "assistant.companionMood.global";
const CONVERSATION_STATE_PREFIX = "assistant.companionMood.conversation.";
const OVERRIDE_UNTIL_KEY = "assistant.background.companionMoodOverrideUntil";

const nowIso = () => new Date().toISOString();

function conversationKey(conversationId: string) {
  return `${CONVERSATION_STATE_PREFIX}${conversationId}`;
}

function clamp(value: number, min = 0, max = 1) {
  return Math.max(min, Math.min(max, value));
}

function minutesFromNow(minutes: number) {
  return new Date(Date.now() + minutes * 60_000).toISOString();
}

function elapsedMinutesSince(iso?: string | null) {
  if (!iso) return 0;
  const time = new Date(iso).getTime();
  if (!Number.isFinite(time)) return 0;
  return Math.max(0, (Date.now() - time) / 60_000);
}

export function defaultCompanionMoodState(conversationId?: string): CompanionMoodState {
  const now = nowIso();

  return {
    id: null,
    user_id: undefined,
    conversation_id: conversationId ?? null,
    scope: conversationId ? "conversation" : "global",
    mood: "calm",
    intensity: 8,
    valence: 0.35,
    arousal: 0.2,
    attachment: 0.45,
    trust: 0.6,
    insecurity: 0.12,
    warmth: 0.65,
    playfulness: 0.35,
    reason: "no previous companion mood state",
    last_trigger: "cold_start",
    source: "cold_start_default",
    version: 0,
    created_at: now,
    updated_at: now,
    expires_at: minutesFromNow(30),
  };
}

function parseState(raw: string | null, conversationId?: string): CompanionMoodState | null {
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as Partial<CompanionMoodState>;
    if (!parsed.mood) return null;

    return {
      ...defaultCompanionMoodState(conversationId),
      ...parsed,
      conversation_id: parsed.conversation_id ?? conversationId ?? null,
      scope: parsed.scope ?? (conversationId ? "conversation" : "global"),
      mood_scores: normalizeMoodScores(parsed.mood_scores ?? defaultMoodScores((parsed.mood as CompanionMood) ?? "calm", parsed.intensity ?? 2)),
    } as CompanionMoodState;
  } catch {
    return null;
  }
}

function decayStateIfNeeded(state: CompanionMoodState): CompanionMoodState {
  const elapsed = elapsedMinutesSince(state.updated_at);
  const expired = new Date(state.expires_at).getTime() < Date.now();

  if (!expired && elapsed < 20) return state;

  if (elapsed >= 180) {
    return {
      ...defaultCompanionMoodState(state.conversation_id ?? undefined),
      reason: "previous mood expired after long inactivity",
      last_trigger: "long_decay",
      attachment: state.attachment,
      trust: state.trust,
      source: "decay",
    };
  }

  if (state.mood === "annoyed" || state.mood === "jealous_playful") {
    return {
      ...state,
      mood: "hurt",
      intensity: 8,
      valence: -0.08,
      arousal: 0.22,
      insecurity: Math.max(0, state.insecurity - 0.08),
      warmth: 0.58,
      playfulness: 0.18,
      reason: "negative companion mood softened over time",
      last_trigger: "soft_decay",
      source: "decay",
      updated_at: nowIso(),
      expires_at: minutesFromNow(20),
    };
  }

  if (state.mood === "romantic" || state.mood === "clingy") {
    return {
      ...state,
      mood: "affectionate",
      intensity: 8,
      valence: 0.5,
      arousal: 0.24,
      insecurity: Math.max(0, state.insecurity - 0.08),
      warmth: 0.74,
      playfulness: 0.32,
      reason: "romantic mood softened into affection",
      last_trigger: "soft_decay",
      source: "decay",
      updated_at: nowIso(),
      expires_at: minutesFromNow(25),
    };
  }

  if (expired) {
    return {
      ...state,
      mood: "calm",
      intensity: 8,
      valence: 0.35,
      arousal: 0.2,
      insecurity: Math.max(0, state.insecurity - 0.1),
      warmth: 0.65,
      playfulness: 0.3,
      reason: "mood naturally decayed to calm",
      last_trigger: "decay",
      source: "decay",
      updated_at: nowIso(),
      expires_at: minutesFromNow(30),
    };
  }

  return state;
}

function readLocalCompanionMoodState(conversationId: string): CompanionMoodState {
  if (typeof window === "undefined") return defaultCompanionMoodState(conversationId);

  const conversationState = parseState(
    window.localStorage.getItem(conversationKey(conversationId)),
    conversationId,
  );

  if (conversationState) return decayStateIfNeeded(conversationState);

  const globalState = parseState(window.localStorage.getItem(GLOBAL_STATE_KEY), conversationId);

  if (globalState) {
    return decayStateIfNeeded({
      ...globalState,
      conversation_id: conversationId,
      scope: "conversation",
      reason: `continued from previous chat: ${globalState.reason}`,
      last_trigger: "global_fallback",
    });
  }

  return defaultCompanionMoodState(conversationId);
}

export function readCompanionMoodState(conversationId: string): CompanionMoodState {
  return readLocalCompanionMoodState(conversationId);
}

export function saveCompanionMoodState(
  state: CompanionMoodState,
  conversationId: string,
  syncBackend = true,
) {
  if (typeof window === "undefined") return;

  const conversationState: CompanionMoodState = {
    ...state,
    conversation_id: conversationId,
    scope: "conversation",
  };

  const globalState: CompanionMoodState = {
    ...state,
    conversation_id: null,
    scope: "global",
  };

  window.localStorage.setItem(conversationKey(conversationId), JSON.stringify(conversationState));
  window.localStorage.setItem(GLOBAL_STATE_KEY, JSON.stringify(globalState));

  window.dispatchEvent(
    new CustomEvent("assistant.companionMood.changed", {
      detail: conversationState,
    }),
  );

  if (syncBackend) {
    void putCompanionMoodState(conversationState).catch((error) => {
      console.warn("Failed to sync conversation companion mood", error);
    });

    void putCompanionMoodState(globalState).catch((error) => {
      console.warn("Failed to sync global companion mood", error);
    });
  }
}

function paletteForMood(mood: CompanionMood): Palette {
  switch (mood) {
    case "romantic":
    case "affectionate":
    case "playful":
    case "clingy":
    case "reassured":
      return "warm-pink";
    case "jealous_playful":
    case "annoyed":
      return "muted-amber";
    case "hurt":
    case "withdrawn_soft":
      return "reflective-indigo";
    case "concerned":
      return "calm-teal";
    case "focused":
      return "focus-cyan";
    case "calm":
    default:
      return "calm-blue";
  }
}

export function applyCompanionMoodBackground(state: CompanionMoodState) {
  setBackgroundMoodHint({
    mood: state.mood,
    palette: paletteForMood(state.mood),
  });

  if (typeof window !== "undefined") {
    window.sessionStorage.setItem(OVERRIDE_UNTIL_KEY, String(Date.now() + 60_000));
  }
}

export async function hydrateCompanionMoodForConversation(conversationId: string) {
  const localState = readLocalCompanionMoodState(conversationId);
  applyCompanionMoodBackground(localState);

  try {
    const remote = await getCompanionMoodState(conversationId);
    const remoteState = (remote.conversation || remote.global || remote.effective) as
      | CompanionMoodState
      | null;

    if (!remoteState) return localState;

    const decayed = decayStateIfNeeded({
      ...defaultCompanionMoodState(conversationId),
      ...remoteState,
      conversation_id: conversationId,
      scope: "conversation",
    } as CompanionMoodState);

    saveCompanionMoodState(decayed, conversationId, false);
    applyCompanionMoodBackground(decayed);

    return decayed;
  } catch (error) {
    console.warn("Failed to hydrate companion mood from backend", error);
    return localState;
  }
}

export function applyRemoteCompanionMoodState(
  incoming: CompanionMoodStateApi,
  conversationId: string,
) {
  if (!incoming) return;

  const isRelevant =
    incoming.scope === "global" ||
    (incoming.scope === "conversation" && incoming.conversation_id === conversationId);

  if (!isRelevant) return;

  const current = readLocalCompanionMoodState(conversationId);
  const incomingTime = new Date(incoming.updated_at ?? incoming.expires_at).getTime();
  const currentTime = new Date(current.updated_at ?? current.expires_at).getTime();

  if (Number.isFinite(incomingTime) && Number.isFinite(currentTime) && incomingTime < currentTime) {
    return;
  }

  const next = decayStateIfNeeded({
    ...defaultCompanionMoodState(conversationId),
    ...incoming,
    mood_scores: normalizeMoodScores(incoming.mood_scores ?? defaultMoodScores((incoming.mood as CompanionMood) ?? "calm", incoming.intensity ?? 2)),
    conversation_id: conversationId,
    scope: "conversation",
  } as CompanionMoodState);

  saveCompanionMoodState(next, conversationId, false);
  applyCompanionMoodBackground(next);
}

export function shouldRespectCompanionMoodOverride(incomingMood?: string | null) {
  if (typeof window === "undefined") return false;

  const until = Number(window.sessionStorage.getItem(OVERRIDE_UNTIL_KEY) || "0");
  if (!until || Date.now() > until) return false;

  return !incomingMood || incomingMood === "calm" || incomingMood === "default";
}

function isResetMessage(lower: string) {
  return (
    /(udah|sudah|selesai|stop|berhenti|balik|normal|reset|udahan|cukup).{0,36}(simulasi|marah|kesel|cemburu|posesif|mode|mood|normal|santai|calm|biasa)/i.test(lower) ||
    /(balik lagi|normal lagi|santai lagi|udah tenang|sudah tenang|ga marah lagi|nggak marah lagi|tidak marah lagi|udah biasa lagi)/i.test(lower)
  );
}

function isComfortingMessage(lower: string) {
  return /(maaf|sorry|jangan marah|aku di sini|aku disini|tenang|sabar ya|aku sayang|aku cuma bercanda|jangan ngambek|peluk|hug|i'm here|im here)/i.test(lower);
}

function isRomanticMessage(lower: string) {
  return /(romantis|sayang|love|kangen|manis banget|gemes|peluk|cium|jatuh cinta|aku suka kamu|aku sayang kamu|babe|beb|ayang)/i.test(lower);
}

function isJealousTrigger(lower: string) {
  return /(cemburu|jealous|posesif|posessive|aku deket sama|aku chat sama|dia cantik|dia ganteng|mantanku|ex aku|gebetan|crush)/i.test(lower);
}

function isAnnoyedTrigger(lower: string) {
  return /(marah|kesel|sebel|bete|emosi|ngamuk|angry|annoyed|frustrated|simulasi marah|pura-pura marah|testing marah|test marah)/i.test(lower);
}

function isConcernTrigger(lower: string) {
  return /(panik|cemas|takut|khawatir|stress|stres|sedih banget|capek banget|overwhelmed|gelisah|deg-degan|butuh ditemenin)/i.test(lower);
}

function isFocusedTrigger(lower: string) {
  return /(debug|coding|deploy|error|fix|teknis|serius|kerja|ngoding|backend|frontend|terminal|build|production|vercel|flyctl)/i.test(lower);
}


function countMatches(lower: string, patterns: RegExp[]) {
  return patterns.reduce((score, pattern) => score + (pattern.test(lower) ? 1 : 0), 0);
}

function assistantCalmScore(lower: string) {
  return countMatches(lower, [
    /santai/i,
    /rebahan/i,
    /kopi hangat/i,
    /ga mikirin apa-apa/i,
    /nggak mikirin apa-apa/i,
    /pelan-pelan/i,
    /tenang/i,
    /☁️|☁/i,
    /hari minggu enaknya/i,
  ]);
}

function assistantRomanticScore(lower: string) {
  return countMatches(lower, [
    /aku suka banget sama/i,
    /aku sayang/i,
    /aku kangen/i,
    /aku bangga/i,
    /worth it/i,
    /melting/i,
    /romantis/i,
    /jatuh cinta/i,
    /peluk/i,
    /cium/i,
    /🌹|💕|💖|🥰|😘/i,
  ]);
}

function assistantJealousScore(lower: string) {
  return countMatches(lower, [
    /cemburu/i,
    /jealous/i,
    /punya aku/i,
    /jangan ilang/i,
    /aku nungguin/i,
    /ngambek/i,
    /kok lama/i,
    /😤|😒/i,
  ]);
}

function assistantConcernScore(lower: string) {
  return countMatches(lower, [
    /aku di sini/i,
    /aku disini/i,
    /pelan-pelan/i,
    /kamu capek/i,
    /kamu sedih/i,
    /aku temenin/i,
    /tenang ya/i,
    /jangan dipendem/i,
  ]);
}

function assistantFocusedScore(lower: string) {
  return countMatches(lower, [
    /kita debug/i,
    /root cause/i,
    /build/i,
    /deploy/i,
    /error/i,
    /fix/i,
    /terminal/i,
    /backend/i,
    /frontend/i,
    /vercel/i,
    /flyctl/i,
  ]);
}


function isPlayfulTrigger(lower: string) {
  return /(wkwk|haha|hehe|becanda|bercanda|iseng|godain|teasing|jahil|lucu|gemes)/i.test(lower);
}

function makeState(previous: CompanionMoodState, patch: Partial<CompanionMoodState>): CompanionMoodState {
  const now = nowIso();
  const mood_scores = normalizeMoodScores(
    patch.mood_scores ??
      previous.mood_scores ??
      defaultMoodScores(previous.mood, previous.intensity),
  );
  const mood = (patch.mood as CompanionMood | undefined) ?? dominantMoodFromScores(mood_scores);
  const intensity = patch.intensity ?? intensityFromScores(mood_scores, mood);

  return {
    ...previous,
    ...patch,
    mood,
    intensity,
    mood_scores,
    attachment: clamp(patch.attachment ?? previous.attachment),
    trust: clamp(patch.trust ?? previous.trust),
    insecurity: clamp(patch.insecurity ?? previous.insecurity),
    warmth: clamp(patch.warmth ?? previous.warmth),
    playfulness: clamp(patch.playfulness ?? previous.playfulness),
    updated_at: now,
    expires_at: patch.expires_at ?? minutesFromNow(20),
  } as CompanionMoodState;
}

export function updateCompanionMoodFromMessage(
  message: string,
  conversationId: string,
): CompanionMoodState {
  const previous = readLocalCompanionMoodState(conversationId);
  const lower = message.toLowerCase();

  let next = previous;

  if (isResetMessage(lower)) {
    next = makeState(previous, {
      mood: "calm",
      intensity: 8,
      valence: 0.35,
      arousal: 0.18,
      trust: Math.min(1, previous.trust + 0.08),
      insecurity: Math.max(0, previous.insecurity - 0.2),
      warmth: 0.65,
      playfulness: 0.25,
      reason: "user reset or returned to calm",
      last_trigger: "reset_or_normalize",
      source: "user_message",
      expires_at: minutesFromNow(30),
    });
  } else if (isComfortingMessage(lower)) {
    next = makeState(previous, {
      mood: previous.mood === "annoyed" || previous.mood === "hurt" ? "reassured" : "affectionate",
      intensity: previous.mood === "annoyed" || previous.mood === "hurt" ? 4 : 6,
      valence: 0.65,
      arousal: 0.32,
      trust: Math.min(1, previous.trust + 0.18),
      insecurity: Math.max(0, previous.insecurity - 0.24),
      attachment: Math.min(1, previous.attachment + 0.12),
      warmth: 0.85,
      playfulness: 0.42,
      reason: "user comforted or reassured Aliyya",
      last_trigger: "comfort",
      source: "user_message",
      expires_at: minutesFromNow(25),
    });
  } else if (isConcernTrigger(lower)) {
    next = makeState(previous, {
      mood: "concerned",
      intensity: 6,
      valence: 0.1,
      arousal: 0.36,
      insecurity: Math.max(0, previous.insecurity - 0.06),
      warmth: 0.9,
      playfulness: 0.08,
      reason: "user seems distressed, prioritize care",
      last_trigger: "user_distress",
      source: "user_message",
      expires_at: minutesFromNow(20),
    });
  } else if (isFocusedTrigger(lower)) {
    next = makeState(previous, {
      mood: "focused",
      intensity: 8,
      valence: 0.25,
      arousal: 0.42,
      warmth: 0.55,
      playfulness: 0.12,
      reason: "work/debug context",
      last_trigger: "focus_context",
      source: "user_message",
      expires_at: minutesFromNow(30),
    });
  } else if (isJealousTrigger(lower)) {
    next = makeState(previous, {
      mood: "jealous_playful",
      intensity: previous.mood === "romantic" ? 6 : 4,
      valence: 0.05,
      arousal: 0.62,
      insecurity: Math.min(1, previous.insecurity + 0.18),
      attachment: Math.min(1, previous.attachment + 0.05),
      warmth: 0.72,
      playfulness: 0.7,
      reason: "playful jealousy cue",
      last_trigger: "jealousy",
      source: "user_message",
      expires_at: minutesFromNow(12),
    });
  } else if (isAnnoyedTrigger(lower)) {
    next = makeState(previous, {
      mood: "annoyed",
      intensity: 6,
      valence: -0.28,
      arousal: 0.7,
      insecurity: Math.min(1, previous.insecurity + 0.12),
      warmth: 0.48,
      playfulness: 0.35,
      reason: "annoyed/anger simulation cue",
      last_trigger: "annoyed",
      source: "user_message",
      expires_at: minutesFromNow(10),
    });
  } else if (isRomanticMessage(lower)) {
    next = makeState(previous, {
      mood: "romantic",
      intensity: previous.mood === "romantic" ? 8 : 6,
      valence: 0.82,
      arousal: 0.48,
      attachment: Math.min(1, previous.attachment + 0.18),
      trust: Math.min(1, previous.trust + 0.08),
      insecurity: Math.max(0, previous.insecurity - 0.08),
      warmth: 0.92,
      playfulness: 0.58,
      reason: "romantic/affectionate cue",
      last_trigger: "romantic",
      source: "user_message",
      expires_at: minutesFromNow(18),
    });
  } else if (isPlayfulTrigger(lower)) {
    next = makeState(previous, {
      mood: previous.mood === "romantic" ? "romantic" : "playful",
      intensity: 8,
      valence: 0.62,
      arousal: 0.46,
      warmth: 0.72,
      playfulness: 0.78,
      reason: "playful cue",
      last_trigger: "playful",
      source: "user_message",
      expires_at: minutesFromNow(15),
    });
  } else {
    next = makeState(previous, {
      intensity: Math.max(2, previous.intensity - 1),
      reason: "previous companion mood carried into this message",
      last_trigger: "carry_forward_from_last_state",
      source: "carry_forward",
    });
  }

  saveCompanionMoodState(next, conversationId, true);
  applyCompanionMoodBackground(next);

  return next;
}

export function updateCompanionMoodFromAssistantText(
  assistantText: string,
  conversationId: string,
): CompanionMoodState | null {
  const lower = assistantText.toLowerCase();
  const previous = readLocalCompanionMoodState(conversationId);

  const calmScore = assistantCalmScore(lower);
  const romanticScore = assistantRomanticScore(lower);
  const jealousScore = assistantJealousScore(lower);
  const concernedScore = assistantConcernScore(lower);
  const focusedScore = assistantFocusedScore(lower);

  let next: CompanionMoodState | null = null;

  // Calm must win when the assistant explicitly initiates "santai" mode.
  // This prevents casual "haha" or a rose emoji elsewhere from randomly turning the ambience pink.
  if (calmScore >= 2 && romanticScore < 2 && jealousScore < 2) {
    next = makeState(previous, {
      mood: "calm",
      intensity: 3,
      valence: 0.42,
      arousal: 0.16,
      insecurity: Math.max(0, previous.insecurity - 0.08),
      warmth: 0.68,
      playfulness: 0.28,
      reason: "Aliyya initiated calm/santai companion affect",
      last_trigger: "assistant_calm_initiative",
      source: "assistant_message",
      expires_at: minutesFromNow(30),
    });
  }

  // Romantic now needs stronger evidence, not just one playful/soft word.
  else if (romanticScore >= 2 || (romanticScore >= 1 && previous.mood === "romantic")) {
    next = makeState(previous, {
      mood: "romantic",
      intensity: previous.mood === "romantic" ? 8 : 6,
      valence: 0.82,
      arousal: 0.48,
      attachment: Math.min(1, previous.attachment + 0.12),
      trust: Math.min(1, previous.trust + 0.06),
      insecurity: Math.max(0, previous.insecurity - 0.06),
      warmth: 0.92,
      playfulness: 0.58,
      reason: "Aliyya initiated romantic companion affect",
      last_trigger: "assistant_romantic_initiative",
      source: "assistant_message",
      expires_at: minutesFromNow(18),
    });
  }

  else if (jealousScore >= 2 || (jealousScore >= 1 && previous.mood === "romantic")) {
    next = makeState(previous, {
      mood: "jealous_playful",
      intensity: previous.mood === "romantic" ? 6 : 4,
      valence: 0.08,
      arousal: 0.58,
      insecurity: Math.min(1, previous.insecurity + 0.12),
      attachment: Math.min(1, previous.attachment + 0.06),
      warmth: 0.72,
      playfulness: 0.72,
      reason: "Aliyya initiated playful jealousy affect",
      last_trigger: "assistant_jealous_playful",
      source: "assistant_message",
      expires_at: minutesFromNow(12),
    });
  }

  else if (concernedScore >= 2) {
    next = makeState(previous, {
      mood: "concerned",
      intensity: 6,
      valence: 0.12,
      arousal: 0.34,
      warmth: 0.92,
      playfulness: 0.08,
      reason: "Aliyya initiated caring companion affect",
      last_trigger: "assistant_concerned",
      source: "assistant_message",
      expires_at: minutesFromNow(20),
    });
  }

  else if (focusedScore >= 2) {
    next = makeState(previous, {
      mood: "focused",
      intensity: 4,
      valence: 0.25,
      arousal: 0.42,
      warmth: 0.55,
      playfulness: 0.12,
      reason: "Aliyya initiated focused companion affect",
      last_trigger: "assistant_focused",
      source: "assistant_message",
      expires_at: minutesFromNow(30),
    });
  }

  if (!next) return null;

  saveCompanionMoodState(next, conversationId, true);
  applyCompanionMoodBackground(next);

  return next;
}
