"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  BriefcaseBusiness,
  CalendarClock,
  CheckCircle2,
  Heart,
  Layers3,
  MessageCircleHeart,
  Route,
  ShieldAlert,
  Sparkles,
  Target,
  UsersRound,
} from "lucide-react";

type LabMode = "life" | "chief";

const companionCards = [
  {
    title: "Gentle check-in",
    body: "A calm space to name what you feel, unpack the day, and turn emotional noise into something lighter.",
    meta: "Emotional presence",
    icon: Heart,
  },
  {
    title: "People that matter",
    body: "Family, close relationships, and personal context stay visible so Aliyya can respond with continuity.",
    meta: "Relationship memory",
    icon: UsersRound,
  },
  {
    title: "Reflection thread",
    body: "Journaling, identity, memories, and long-running personal goals are treated as part of one life narrative.",
    meta: "Life continuity",
    icon: MessageCircleHeart,
  },
];

const chiefCards = [
  {
    title: "Top priorities",
    body: "Identify the few things that matter most today, then separate urgent noise from true execution leverage.",
    meta: "Execution",
    icon: Target,
  },
  {
    title: "Calendar pressure",
    body: "Detect tight windows, meeting load, travel buffers, and follow-ups before they become operational risks.",
    meta: "Time control",
    icon: CalendarClock,
  },
  {
    title: "Risk & decision queue",
    body: "Surface blockers, open decisions, dependencies, and next actions in a crisp executive format.",
    meta: "Chief of Staff",
    icon: ShieldAlert,
  },
];

const companionMessages = [
  {
    from: "user",
    text: "Aku capek banget hari ini, tapi masih banyak yang kepikiran.",
  },
  {
    from: "assistant",
    text: "Aku di sini. Kita pelan-pelan aja. Ceritain satu hal yang paling berat dulu, nanti aku bantu rapihin jadi langkah kecil.",
  },
];

const chiefMessages = [
  {
    from: "user",
    text: "Besok banyak agenda. Bantu aku prioritasin.",
  },
  {
    from: "assistant",
    text: "Baik, Syahid. Bottom line: kita pisahkan agenda menjadi keputusan, follow-up, dan deep work. Kirim daftar agendanya; aku susun prioritas, risiko, dan next action.",
  },
];

const roadmapCards = [
  {
    title: "Mode-aware background",
    body: "Life Companion keeps the user’s saved sanctuary background. Chief of Staff can activate a calmer executive cockpit layer.",
    icon: Layers3,
  },
  {
    title: "Composer posture",
    body: "The input area can change from reflective prompts to execution prompts without changing the chat backend.",
    icon: MessageCircleHeart,
  },
  {
    title: "Gradual porting",
    body: "Only approved lab components move into /chat later, one layer at a time, so the main app remains stable.",
    icon: Route,
  },
];

export default function AIStudioLabPage() {
  const [mode, setMode] = useState<LabMode>("life");
  const isChief = mode === "chief";

  const cards = isChief ? chiefCards : companionCards;
  const messages = isChief ? chiefMessages : companionMessages;

  const modeCopy = useMemo(() => {
    if (isChief) {
      return {
        eyebrow: "CALM EXECUTIVE COCKPIT",
        title: "Chief of Staff",
        subtitle:
          "Structured, concise, decision-oriented. Aliyya helps prioritize, identify risks, and move execution forward without emotional clutter.",
        input: "Ask Aliyya to brief, prioritize, decide, or structure next actions...",
        status: "Execution posture active",
      };
    }

    return {
      eyebrow: "SOFT PERSONAL SANCTUARY",
      title: "Life Companion",
      subtitle:
        "Warm, personal, and emotionally present. Aliyya helps you reflect, remember, and navigate life with continuity.",
      input: "Tell Aliyya what you are feeling, thinking, or carrying today...",
      status: "Companion posture active",
    };
  }, [isChief]);

  return (
    <main
      className={
        isChief
          ? "min-h-dvh overflow-x-hidden bg-[#090d16] text-slate-50 transition-all duration-1000 ease-in-out"
          : "min-h-dvh overflow-x-hidden bg-[#fbf8f2] text-slate-900 transition-all duration-1000 ease-in-out"
      }
    >
      <div className="fixed inset-0 pointer-events-none transition-opacity duration-1000 ease-in-out">
        {isChief ? <ChiefBackground /> : <LifeBackground />}
      </div>

      <div className="relative z-10 mx-auto flex min-h-dvh max-w-7xl flex-col px-4 py-4 sm:px-6 lg:px-8">
        <header className="flex items-center justify-between gap-4 transition-all duration-700 ease-in-out">
          <Link
            href="/chat"
            className={
              isChief
                ? "inline-flex items-center gap-2 rounded-full border border-teal-200/15 bg-white/[0.045] px-3 py-2 text-xs font-medium text-teal-50 backdrop-blur transition hover:bg-white/[0.08]"
                : "inline-flex items-center gap-2 rounded-full border border-stone-900/10 bg-white/60 px-3 py-2 text-xs font-medium text-stone-700 shadow-sm backdrop-blur transition hover:bg-white/85"
            }
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to app
          </Link>

          <div
            className={
              isChief
                ? "rounded-full border border-teal-200/15 bg-teal-200/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.22em] text-teal-100 transition-all duration-700"
                : "rounded-full border border-stone-200/80 bg-white/65 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 shadow-sm transition-all duration-700"
            }
          >
            AI Studio Lab
          </div>
        </header>

        <section className="grid flex-1 items-center gap-8 py-8 lg:grid-cols-12 lg:py-10">
          <div className="lg:col-span-5">
            <div
              className={
                isChief
                  ? "mb-5 inline-flex items-center gap-2 rounded-full border border-teal-200/15 bg-teal-200/10 px-3 py-1.5 text-xs font-medium text-teal-100 transition-all duration-700"
                  : "mb-5 inline-flex items-center gap-2 rounded-full border border-stone-200/80 bg-white/65 px-3 py-1.5 text-xs font-medium text-stone-600 shadow-sm transition-all duration-700"
              }
            >
              {isChief ? (
                <BriefcaseBusiness className="h-3.5 w-3.5" />
              ) : (
                <Sparkles className="h-3.5 w-3.5" />
              )}
              {modeCopy.eyebrow}
            </div>

            <h1
              className={
                isChief
                  ? "max-w-3xl text-5xl font-semibold tracking-[-0.06em] text-white transition-colors duration-700 sm:text-7xl"
                  : "max-w-3xl text-5xl font-semibold tracking-[-0.06em] text-stone-950 transition-colors duration-700 sm:text-7xl"
              }
            >
              {modeCopy.title}
            </h1>

            <p
              className={
                isChief
                  ? "mt-5 max-w-2xl text-base leading-8 text-slate-300 transition-colors duration-700 sm:text-lg"
                  : "mt-5 max-w-2xl text-base leading-8 text-stone-600 transition-colors duration-700 sm:text-lg"
              }
            >
              {modeCopy.subtitle}
            </p>

            <div
              className={
                isChief
                  ? "mt-7 inline-flex rounded-full border border-teal-200/15 bg-slate-900/72 p-1 shadow-2xl shadow-black/30 backdrop-blur transition-all duration-700"
                  : "mt-7 inline-flex rounded-full border border-stone-900/10 bg-white/75 p-1 shadow-lg shadow-stone-200/60 backdrop-blur transition-all duration-700"
              }
            >
              <button
                type="button"
                onClick={() => setMode("life")}
                className={
                  !isChief
                    ? "rounded-full bg-white px-4 py-2 text-sm font-semibold text-stone-800 shadow-sm transition-all duration-500"
                    : "rounded-full px-4 py-2 text-sm font-medium text-slate-400 transition hover:text-white"
                }
              >
                Life Companion
              </button>
              <button
                type="button"
                onClick={() => setMode("chief")}
                className={
                  isChief
                    ? "rounded-full border border-teal-200/18 bg-slate-800/80 px-4 py-2 text-sm font-semibold text-white shadow-sm shadow-black/20 transition-all duration-500"
                    : "rounded-full px-4 py-2 text-sm font-medium text-stone-500 transition hover:text-stone-900"
                }
              >
                Chief of Staff
              </button>
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-3 lg:grid-cols-1 xl:grid-cols-3">
              {cards.map((card) => {
                const Icon = card.icon;
                return (
                  <article
                    key={card.title}
                    className={
                      isChief
                        ? "rounded-3xl border border-teal-200/10 bg-white/[0.045] p-4 shadow-2xl shadow-black/20 backdrop-blur-xl transition-all delay-100 duration-500"
                        : "rounded-3xl border border-white/75 bg-white/58 p-4 shadow-xl shadow-stone-200/50 backdrop-blur-xl transition-all delay-100 duration-500"
                    }
                  >
                    <div
                      className={
                        isChief
                          ? "mb-3 flex h-9 w-9 items-center justify-center rounded-2xl bg-teal-200/10 text-teal-200 transition-all duration-500"
                          : "mb-3 flex h-9 w-9 items-center justify-center rounded-2xl bg-stone-100 text-stone-600 transition-all duration-500"
                      }
                    >
                      <Icon className="h-4 w-4" />
                    </div>
                    <p
                      className={
                        isChief
                          ? "text-sm font-semibold text-white"
                          : "text-sm font-semibold text-stone-950"
                      }
                    >
                      {card.title}
                    </p>
                    <p
                      className={
                        isChief
                          ? "mt-2 text-xs leading-5 text-slate-400"
                          : "mt-2 text-xs leading-5 text-stone-600"
                      }
                    >
                      {card.body}
                    </p>
                    <p
                      className={
                        isChief
                          ? "mt-4 text-[10px] font-semibold uppercase tracking-[0.2em] text-teal-200/70"
                          : "mt-4 text-[10px] font-semibold uppercase tracking-[0.2em] text-stone-400"
                      }
                    >
                      {card.meta}
                    </p>
                  </article>
                );
              })}
            </div>
          </div>

          <div
            className={
              isChief
                ? "relative rounded-[2rem] border border-teal-200/12 bg-slate-950/62 p-4 shadow-2xl shadow-black/35 backdrop-blur-xl transition-all delay-100 duration-700 lg:col-span-7"
                : "relative rounded-[2rem] border border-white/75 bg-white/55 p-4 shadow-2xl shadow-stone-200/60 backdrop-blur-xl transition-all delay-100 duration-700 lg:col-span-7"
            }
          >
            <div className="mb-4 flex items-center justify-between px-2">
              <div>
                <p
                  className={
                    isChief
                      ? "text-xs font-semibold uppercase tracking-[0.24em] text-teal-200/80"
                      : "text-xs font-semibold uppercase tracking-[0.24em] text-stone-400"
                  }
                >
                  Live preview
                </p>
                <p
                  className={
                    isChief
                      ? "mt-1 text-sm text-slate-400"
                      : "mt-1 text-sm text-stone-500"
                  }
                >
                  {modeCopy.status}
                </p>
              </div>
              {isChief ? (
                <div className="relative h-16 w-16">
                  <div className="absolute inset-0 rounded-full border border-teal-200/25" />
                  <div className="absolute inset-3 rounded-full border border-blue-200/15" />
                  <div className="absolute inset-[1.35rem] rounded-full bg-teal-100 shadow-[0_0_18px_rgba(45,212,191,0.55),0_0_42px_rgba(45,212,191,0.28)]" />
                </div>
              ) : (
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-stone-100 via-white to-lavender-100 text-stone-500 shadow-inner">
                  <Heart className="h-5 w-5" />
                </div>
              )}
            </div>

            <div
              className={
                isChief
                  ? "min-h-[420px] rounded-[1.5rem] border border-white/8 bg-slate-950/45 p-4 transition-all duration-700"
                  : "min-h-[420px] rounded-[1.5rem] border border-white/75 bg-white/48 p-4 transition-all duration-700"
              }
            >
              <div className="space-y-4">
                {messages.map((message, index) => (
                  <div
                    key={`${message.from}-${index}`}
                    className={
                      message.from === "user"
                        ? isChief
                          ? "ml-auto max-w-[78%] rounded-3xl bg-teal-50 px-4 py-3 text-sm leading-6 text-slate-950 shadow-sm transition-all duration-500"
                          : "ml-auto max-w-[78%] rounded-3xl bg-stone-800 px-4 py-3 text-sm leading-6 text-stone-50 shadow-sm transition-all duration-500"
                        : isChief
                          ? "max-w-[86%] rounded-3xl border border-teal-200/10 bg-white/[0.06] px-4 py-3 text-sm leading-6 text-slate-100 shadow-sm transition-all duration-500"
                          : "max-w-[86%] rounded-3xl border border-white/80 bg-white/78 px-4 py-3 text-sm leading-6 text-stone-800 shadow-sm transition-all duration-500"
                    }
                  >
                    {message.text}
                  </div>
                ))}
              </div>

              <div className="mt-8 grid gap-3">
                {(isChief
                  ? [
                      "Brief me for today",
                      "Prioritize my next actions",
                      "Find risks and blockers",
                    ]
                  : [
                      "Help me reflect",
                      "Write a gentle journal",
                      "Remember this moment",
                    ]
                ).map((item) => (
                  <div
                    key={item}
                    className={
                      isChief
                        ? "flex items-center gap-3 rounded-2xl border border-teal-200/10 bg-teal-200/[0.035] px-4 py-3 text-sm text-teal-50 transition-all duration-500"
                        : "flex items-center gap-3 rounded-2xl border border-stone-100 bg-white/58 px-4 py-3 text-sm text-stone-700 transition-all duration-500"
                    }
                  >
                    <CheckCircle2
                      className={
                        isChief
                          ? "h-4 w-4 text-teal-200"
                          : "h-4 w-4 text-stone-400"
                      }
                    />
                    {item}
                  </div>
                ))}
              </div>
            </div>

            <div
              className={
                isChief
                  ? "mt-4 rounded-2xl border border-teal-200/12 bg-black/18 px-4 py-3 text-sm text-slate-300 transition-all duration-700"
                  : "mt-4 rounded-full border border-white/80 bg-white/80 px-4 py-3 text-sm text-stone-600 shadow-sm transition-all duration-700"
              }
            >
              {modeCopy.input}
            </div>
          </div>
        </section>

        <section
          className={
            isChief
              ? "mb-8 rounded-[2rem] border border-teal-200/10 bg-white/[0.035] p-5 shadow-2xl shadow-black/20 backdrop-blur-xl transition-all duration-700"
              : "mb-8 rounded-[2rem] border border-white/75 bg-white/52 p-5 shadow-xl shadow-stone-200/50 backdrop-blur-xl transition-all duration-700"
          }
        >
          <div className="mb-5">
            <p
              className={
                isChief
                  ? "text-xs font-semibold uppercase tracking-[0.24em] text-teal-200/70"
                  : "text-xs font-semibold uppercase tracking-[0.24em] text-stone-400"
              }
            >
              Product translation
            </p>
            <h2
              className={
                isChief
                  ? "mt-2 text-2xl font-semibold tracking-[-0.04em] text-white"
                  : "mt-2 text-2xl font-semibold tracking-[-0.04em] text-stone-950"
              }
            >
              How this translates to the real Aliyya app
            </h2>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            {roadmapCards.map((card) => {
              const Icon = card.icon;
              return (
                <div
                  key={card.title}
                  className={
                    isChief
                      ? "rounded-3xl border border-white/8 bg-slate-950/35 p-4"
                      : "rounded-3xl border border-white/75 bg-white/55 p-4"
                  }
                >
                  <Icon
                    className={
                      isChief
                        ? "mb-3 h-5 w-5 text-teal-200"
                        : "mb-3 h-5 w-5 text-stone-500"
                    }
                  />
                  <p
                    className={
                      isChief
                        ? "text-sm font-semibold text-white"
                        : "text-sm font-semibold text-stone-950"
                    }
                  >
                    {card.title}
                  </p>
                  <p
                    className={
                      isChief
                        ? "mt-2 text-xs leading-5 text-slate-400"
                        : "mt-2 text-xs leading-5 text-stone-600"
                    }
                  >
                    {card.body}
                  </p>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </main>
  );
}

function LifeBackground() {
  return (
    <>
      <div className="absolute left-[4%] top-[8%] h-[34rem] w-[34rem] rounded-full bg-stone-200/42 blur-3xl transition-all duration-1000" />
      <div className="absolute right-[8%] top-[16%] h-[30rem] w-[30rem] rounded-full bg-violet-100/48 blur-3xl transition-all duration-1000" />
      <div className="absolute bottom-[-10%] left-[26%] h-[32rem] w-[32rem] rounded-full bg-amber-100/60 blur-3xl transition-all duration-1000" />
      <div className="absolute left-[18%] bottom-[12%] h-[22rem] w-[22rem] rounded-full bg-emerald-100/30 blur-3xl transition-all duration-1000" />
    </>
  );
}

function ChiefBackground() {
  return (
    <>
      {/* Calm executive cockpit: visible soft aura + tactical grid, no hard sci-fi rings. */}
      <div className="absolute inset-0 bg-[#090d16] transition-all duration-1000" />

      <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_30%,rgba(45,212,191,0.16),transparent_27rem),radial-gradient(circle_at_22%_76%,rgba(96,165,250,0.085),transparent_32rem),radial-gradient(circle_at_78%_88%,rgba(180,130,58,0.052),transparent_24rem)] transition-all duration-1000" />

      <div className="absolute inset-0 opacity-[0.04] [background-image:linear-gradient(rgba(148,163,184,0.30)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.24)_1px,transparent_1px)] [background-size:48px_48px]" />

      <div className="absolute right-[-10%] top-[4%] h-[42rem] w-[42rem] rounded-full bg-teal-300/[0.095] blur-[118px] transition-all duration-1000 ease-in-out" />
      <div className="absolute right-[18%] top-[18%] h-[26rem] w-[26rem] rounded-full bg-cyan-200/[0.055] blur-[96px] transition-all duration-1000 ease-in-out" />
      <div className="absolute bottom-[-20%] left-[-14%] h-[44rem] w-[44rem] rounded-full bg-blue-400/[0.052] blur-[150px] transition-all duration-1000 ease-in-out" />
      <div className="absolute bottom-[-16%] right-[-8%] h-[34rem] w-[34rem] rounded-full bg-amber-500/[0.028] blur-[140px] transition-all duration-1000 ease-in-out" />

      <div className="absolute left-0 right-0 top-0 h-32 bg-gradient-to-b from-white/[0.035] to-transparent" />
    </>
  );
}
