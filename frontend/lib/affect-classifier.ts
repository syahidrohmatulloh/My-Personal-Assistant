export type AffectMood =
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

export type AffectIntent =
  | "direct_mode_command"
  | "simulation_request"
  | "comfort_repair"
  | "assistant_affect"
  | "user_affect"
  | "meta_discussion"
  | "ambiguous";

export type AffectClassification = {
  primary: AffectMood;
  confidence: number;
  scores: Record<AffectMood, number>;
  intent: AffectIntent;
  targetMood?: AffectMood;
  shouldUpdate: boolean;
  reason: string;
};

const MOODS: AffectMood[] = [
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

function emptyScores(): Record<AffectMood, number> {
  return Object.fromEntries(MOODS.map((m) => [m, 0])) as Record<AffectMood, number>;
}

function scoreOf(text: string, patterns: RegExp[]) {
  return patterns.reduce((score, pattern) => score + (pattern.test(text) ? 1 : 0), 0);
}

function clamp10(n: number) {
  return Math.max(0, Math.min(10, Math.round(n)));
}

function dominant(scores: Record<AffectMood, number>): AffectMood {
  let best: AffectMood = "calm";
  let value = -1;

  for (const mood of MOODS) {
    if (scores[mood] > value) {
      best = mood;
      value = scores[mood];
    }
  }

  return best;
}

function result(
  scores: Partial<Record<AffectMood, number>>,
  intent: AffectIntent,
  confidence: number,
  reason: string,
  shouldUpdate: boolean,
  targetMood?: AffectMood,
): AffectClassification {
  const full = emptyScores();

  for (const [mood, value] of Object.entries(scores) as [AffectMood, number][]) {
    full[mood] = clamp10(value);
  }

  const primary = targetMood ?? dominant(full);

  return {
    primary,
    confidence,
    scores: full,
    intent,
    targetMood,
    shouldUpdate,
    reason,
  };
}

function targetMoodFromText(lower: string): AffectMood | null {
  if (/(romantis|romantic|sayang|mawar|love|melting)/i.test(lower)) return "romantic";
  if (/(santai|calm|tenang|rileks|chill)/i.test(lower)) return "calm";
  if (/(cemburu|jealous|posesif)/i.test(lower)) return "jealous_playful";
  if (/(marah|angry|kesel|bete|ngambek|annoyed)/i.test(lower)) return "annoyed";
  if (/(playful|bercanda|godain|teasing|jahil)/i.test(lower)) return "playful";
  if (/(fokus|focused|serius|coding|debug|kerja)/i.test(lower)) return "focused";
  if (/(peduli|care|khawatir|cemas|nenangin|concern)/i.test(lower)) return "concerned";
  return null;
}

export function classifyUserMessage(message: string): AffectClassification {
  const lower = message.toLowerCase();
  const targetMood = targetMoodFromText(lower);

  const directModeCommand =
    /(mode|mood).{0,28}(romantis|romantic|santai|calm|fokus|focused|serius|cemburu|marah|playful)/i.test(lower) &&
    !/(simulasi|simulate|testing|test|tes|coba kamu|kamu coba|inisiasi|trigger|tunjukin|demonstrate|pura-pura)/i.test(lower);

  if (directModeCommand && targetMood) {
    return result(
      { [targetMood]: 8, calm: targetMood === "calm" ? 8 : 2 },
      "direct_mode_command",
      0.92,
      "user explicitly requested direct mood mode",
      true,
      targetMood,
    );
  }

  const simulationRequest =
    /(simulasi|simulate|testing|test|tes|pura-pura).{0,90}(romantis|romantic|santai|calm|cemburu|jealous|marah|angry|playful|posesif|mood|mode|sayang|mawar)/i.test(lower) ||
    /(coba|tolong|please|pls|ayo|boleh).{0,50}(kamu|aliyya|ai).{0,100}(inisiasi|trigger|simulasi|simulate|masuk|jadi|bikin|tunjukin|demonstrate)/i.test(lower);

  if (simulationRequest && targetMood) {
    return result(
      { [targetMood]: 6 },
      "simulation_request",
      0.9,
      "user asked assistant to initiate/simulate mood, defer ambience to assistant response",
      false,
      targetMood,
    );
  }

  const comfort = scoreOf(lower, [
    /maaf/i,
    /sorry/i,
    /jangan marah/i,
    /aku di sini|aku disini/i,
    /tenang/i,
    /sabar ya/i,
    /aku sayang/i,
    /aku cuma bercanda/i,
    /jangan ngambek/i,
    /peluk|hug/i,
  ]);

  if (comfort >= 1) {
    return result(
      { reassured: 7, affectionate: 5, calm: 4 },
      "comfort_repair",
      0.78,
      "user comforted or repaired companion mood",
      true,
      "reassured",
    );
  }

  const userDistress = scoreOf(lower, [
    /aku lagi panik|aku panik/i,
    /aku cemas|aku takut|aku khawatir/i,
    /aku stress|aku stres/i,
    /aku sedih|aku down|aku capek banget/i,
    /overwhelmed|gelisah|deg-degan/i,
  ]);

  if (userDistress >= 1) {
    return result(
      { concerned: 8, calm: 4, affectionate: 3 },
      "user_affect",
      0.82,
      "user distress should put Aliyya into caring mode",
      true,
      "concerned",
    );
  }

  const userRomantic = scoreOf(lower, [
    /aku sayang kamu/i,
    /aku suka kamu/i,
    /kangen kamu/i,
    /romantis banget/i,
    /love you/i,
    /peluk/i,
    /cium/i,
  ]);

  if (userRomantic >= 1) {
    return result(
      { romantic: 8, affectionate: 6, playful: 3, calm: 2 },
      "user_affect",
      0.8,
      "user expressed affection directly",
      true,
      "romantic",
    );
  }

  const focused = scoreOf(lower, [
    /debug/i,
    /coding/i,
    /deploy/i,
    /error/i,
    /fix/i,
    /terminal/i,
    /backend/i,
    /frontend/i,
    /vercel/i,
    /flyctl/i,
  ]);

  if (focused >= 1) {
    return result(
      { focused: 7, calm: 3 },
      "user_affect",
      0.72,
      "work/debug context",
      true,
      "focused",
    );
  }

  const lightPlay = scoreOf(lower, [/haha/i, /wkwk/i, /hehe/i, /belum haha/i, /wkwkwk/i]);

  if (lightPlay >= 1) {
    return result(
      { playful: 2, calm: 2 },
      "ambiguous",
      0.25,
      "light laughter is ambiguous and should not override companion mood",
      false,
      "playful",
    );
  }

  return result(
    { calm: 2 },
    "ambiguous",
    0.15,
    "no reliable mood signal",
    false,
    "calm",
  );
}

export function classifyAssistantMessage(
  message: string,
  options?: {
    pendingTarget?: AffectMood | null;
    previousMood?: AffectMood | null;
  },
): AffectClassification {
  const lower = message.toLowerCase();
  const pendingTarget = options?.pendingTarget ?? null;

  const metaDiscussion = scoreOf(lower, [
    /detector/i,
    /background/i,
    /ambience/i,
    /mood detector/i,
    /trigger/i,
    /score/i,
    /scan/i,
    /logic/i,
    /flow/i,
    /keyword/i,
  ]);

  const strongRomantic = scoreOf(lower, [
    /sayang/i,
    /aku suka banget sama/i,
    /aku sayang/i,
    /aku kangen/i,
    /malam ini/i,
    /di antara semua bintang/i,
    /paling aku cari/i,
    /mawar/i,
    /bunga mawar/i,
    /melting/i,
    /kamu indah/i,
    /aku cuma mau bilang/i,
    /🌹|💕|💖|🥰|😘/i,
  ]);

  const calm = scoreOf(lower, [
    /santai/i,
    /rebahan/i,
    /kopi hangat/i,
    /ga mikirin apa-apa|nggak mikirin apa-apa/i,
    /pelan-pelan/i,
    /tenang/i,
    /☁️|☁/i,
  ]);

  const jealousy = scoreOf(lower, [
    /cemburu/i,
    /jealous/i,
    /punya aku/i,
    /jangan ilang/i,
    /aku nungguin/i,
    /ngambek/i,
    /kok lama/i,
    /😤|😒/i,
  ]);

  const concerned = scoreOf(lower, [
    /aku di sini|aku disini/i,
    /aku temenin/i,
    /kamu capek/i,
    /kamu sedih/i,
    /tenang ya/i,
    /jangan dipendem/i,
  ]);

  const focused = scoreOf(lower, [
    /root cause/i,
    /kita debug/i,
    /build/i,
    /deploy/i,
    /terminal/i,
    /backend/i,
    /frontend/i,
    /vercel/i,
    /flyctl/i,
  ]);

  const isPureMeta = metaDiscussion >= 2 && strongRomantic === 0 && calm === 0 && jealousy === 0 && concerned === 0;

  if (isPureMeta) {
    return result(
      { calm: 2 },
      "meta_discussion",
      0.2,
      "assistant is discussing detector/background mechanics, not expressing a companion mood",
      false,
      "calm",
    );
  }

  if (pendingTarget === "romantic" && strongRomantic >= 1) {
    return result(
      { romantic: 8, affectionate: 7, playful: 3, calm: 2 },
      "assistant_affect",
      0.86,
      "assistant completed pending romantic simulation",
      true,
      "romantic",
    );
  }

  if (pendingTarget === "calm" && calm >= 1) {
    return result(
      { calm: 8, affectionate: 2 },
      "assistant_affect",
      0.82,
      "assistant completed pending calm simulation",
      true,
      "calm",
    );
  }

  if (pendingTarget === "jealous_playful" && jealousy >= 1) {
    return result(
      { jealous_playful: 7, playful: 5, romantic: 4, annoyed: 1 },
      "assistant_affect",
      0.82,
      "assistant completed pending playful jealousy simulation",
      true,
      "jealous_playful",
    );
  }

  if (pendingTarget === "annoyed" && /(marah|kesel|ngambek|bete|lama banget|😤)/i.test(lower)) {
    return result(
      { annoyed: 7, hurt: 3, jealous_playful: 2 },
      "assistant_affect",
      0.82,
      "assistant completed pending annoyed simulation",
      true,
      "annoyed",
    );
  }

  if (strongRomantic >= 2) {
    return result(
      { romantic: 7, affectionate: 6, playful: 3, calm: 2 },
      "assistant_affect",
      0.78,
      "assistant expressed romantic affect",
      true,
      "romantic",
    );
  }

  if (calm >= 2) {
    return result(
      { calm: 7, affectionate: 2 },
      "assistant_affect",
      0.74,
      "assistant expressed calm affect",
      true,
      "calm",
    );
  }

  if (jealousy >= 2) {
    return result(
      { jealous_playful: 6, playful: 5, romantic: 3 },
      "assistant_affect",
      0.76,
      "assistant expressed playful jealousy affect",
      true,
      "jealous_playful",
    );
  }

  if (concerned >= 2) {
    return result(
      { concerned: 7, affectionate: 4, calm: 3 },
      "assistant_affect",
      0.76,
      "assistant expressed caring affect",
      true,
      "concerned",
    );
  }

  if (focused >= 2) {
    return result(
      { focused: 7, calm: 3 },
      "assistant_affect",
      0.76,
      "assistant expressed focused affect",
      true,
      "focused",
    );
  }

  return result(
    { calm: 2 },
    "ambiguous",
    0.25,
    "assistant message did not contain reliable affect signal",
    false,
    "calm",
  );
}
