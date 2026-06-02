"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  BriefcaseBusiness,
  CalendarClock,
  CheckCircle2,
  Heart,
  MessageCircleHeart,
  ShieldAlert,
  Sparkles,
  Target,
  UsersRound,
} from "lucide-react";

type LabMode = "life" | "chief";

const companionCards = [
  {
    title: "Gentle check-in",
    body: "You have been carrying a lot lately. Want to unpack the day or just sit with it for a bit?",
    meta: "Emotional presence",
    icon: Heart,
  },
  {
    title: "People that matter",
    body: "Aghnia, Zahra, and close family context stay visible so Aliyya can respond with continuity.",
    meta: "Relationship memory",
    icon: UsersRound,
  },
  {
    title: "Reflection thread",
    body: "A soft space for journaling, life updates, identity, memories, and long-running personal goals.",
    meta: "Life continuity",
    icon: MessageCircleHeart,
  },
];

const chiefCards = [
  {
    title: "Top priorities",
    body: "Clarify the three things that matter most today and decide what can be deferred.",
    meta: "Execution",
    icon: Target,
  },
  {
    title: "Calendar pressure",
    body: "Detect tight windows, meeting load, travel buffers, and follow-ups before they become risks.",
    meta: "Time control",
    icon: CalendarClock,
  },
  {
    title: "Risk & decision queue",
    body: "Surface blockers, open decisions, dependencies, and next actions in executive format.",
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
    text: "Aku di sini. Kita pelan-pelan aja ya. Ceritain satu hal yang paling berat dulu, nanti aku bantu rapihin jadi langkah kecil.",
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
          "Structured, concise, decision-oriented. Aliyya helps you prioritize, identify risks, and move execution forward.",
        input: "Ask Aliyya to brief, prioritize, decide, or structure next actions...",
        status: "Execution posture active",
      };
    }

    return {
      eyebrow: "SOFT PERSONAL SANCTUARY",
      title: "Life Companion",
      subtitle:
        "Warm, personal, emotionally present. Aliyya helps you reflect, remember, and navigate life with continuity.",
      input: "Tell Aliyya what you are feeling, thinking, or carrying today...",
      status: "Companion posture active",
    };
  }, [isChief]);

  return (
    <main
      className={
        isChief
          ? "min-h-dvh overflow-hidden bg-slate-950 text-slate-50"
          : "min-h-dvh overflow-hidden bg-[#fbf8f4] text-slate-900"
      }
    >
      <div className="fixed inset-0 pointer-events-none">
        {isChief ? <ChiefBackground /> : <LifeBackground />}
      </div>

      <div className="relative z-10 mx-auto flex min-h-dvh max-w-7xl flex-col px-4 py-4 sm:px-6 lg:px-8">
        <header className="flex items-center justify-between gap-4">
          <Link
            href="/chat"
            className={
              isChief
                ? "inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-white/[0.04] px-3 py-2 text-xs font-medium text-cyan-50 backdrop-blur transition hover:bg-white/[0.08]"
                : "inline-flex items-center gap-2 rounded-full border border-slate-900/10 bg-white/55 px-3 py-2 text-xs font-medium text-slate-700 shadow-sm backdrop-blur transition hover:bg-white/80"
            }
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to app
          </Link>

          <div
            className={
              isChief
                ? "rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-100"
                : "rounded-full border border-rose-200/80 bg-white/60 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.22em] text-rose-500 shadow-sm"
            }
          >
            AI Studio Lab
          </div>
        </header>

        <section className="grid flex-1 items-center gap-8 py-8 lg:grid-cols-[1.05fr_0.95fr] lg:py-10">
          <div>
            <div
              className={
                isChief
                  ? "mb-5 inline-flex items-center gap-2 rounded-full border border-cyan-300/15 bg-cyan-300/10 px-3 py-1.5 text-xs font-medium text-cyan-100"
                  : "mb-5 inline-flex items-center gap-2 rounded-full border border-rose-200/70 bg-white/60 px-3 py-1.5 text-xs font-medium text-rose-600 shadow-sm"
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
                  ? "max-w-3xl text-5xl font-semibold tracking-[-0.06em] text-white sm:text-7xl"
                  : "max-w-3xl text-5xl font-semibold tracking-[-0.06em] text-slate-950 sm:text-7xl"
              }
            >
              {modeCopy.title}
            </h1>

            <p
              className={
                isChief
                  ? "mt-5 max-w-2xl text-base leading-8 text-slate-300 sm:text-lg"
                  : "mt-5 max-w-2xl text-base leading-8 text-slate-600 sm:text-lg"
              }
            >
              {modeCopy.subtitle}
            </p>

            <div
              className={
                isChief
                  ? "mt-7 inline-flex rounded-full border border-cyan-300/20 bg-slate-900/70 p-1 shadow-2xl shadow-cyan-950/40 backdrop-blur"
                  : "mt-7 inline-flex rounded-full border border-slate-900/10 bg-white/70 p-1 shadow-lg shadow-rose-100/50 backdrop-blur"
              }
            >
              <button
                type="button"
                onClick={() => setMode("life")}
                className={
                  !isChief
                    ? "rounded-full bg-white px-4 py-2 text-sm font-semibold text-rose-600 shadow-sm"
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
                    ? "rounded-full bg-cyan-300 px-4 py-2 text-sm font-semibold text-slate-950 shadow-lg shadow-cyan-500/20"
                    : "rounded-full px-4 py-2 text-sm font-medium text-slate-500 transition hover:text-slate-900"
                }
              >
                Chief of Staff
              </button>
            </div>

            <div className="mt-8 grid gap-3 sm:grid-cols-3">
              {cards.map((card) => {
                const Icon = card.icon;
                return (
                  <article
                    key={card.title}
                    className={
                      isChief
                        ? "rounded-3xl border border-cyan-300/12 bg-white/[0.045] p-4 shadow-2xl shadow-black/20 backdrop-blur-xl"
                        : "rounded-3xl border border-white/70 bg-white/55 p-4 shadow-xl shadow-rose-100/60 backdrop-blur-xl"
                    }
                  >
                    <div
                      className={
                        isChief
                          ? "mb-3 flex h-9 w-9 items-center justify-center rounded-2xl bg-cyan-300/10 text-cyan-200"
                          : "mb-3 flex h-9 w-9 items-center justify-center rounded-2xl bg-rose-100 text-rose-500"
                      }
                    >
                      <Icon className="h-4 w-4" />
                    </div>
                    <p
                      className={
                        isChief
                          ? "text-sm font-semibold text-white"
                          : "text-sm font-semibold text-slate-900"
                      }
                    >
                      {card.title}
                    </p>
                    <p
                      className={
                        isChief
                          ? "mt-2 text-xs leading-5 text-slate-400"
                          : "mt-2 text-xs leading-5 text-slate-600"
                      }
                    >
                      {card.body}
                    </p>
                    <p
                      className={
                        isChief
                          ? "mt-4 text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-300/70"
                          : "mt-4 text-[10px] font-semibold uppercase tracking-[0.2em] text-rose-400"
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
                ? "relative rounded-[2rem] border border-cyan-300/15 bg-slate-950/58 p-4 shadow-2xl shadow-cyan-950/30 backdrop-blur-xl"
                : "relative rounded-[2rem] border border-white/70 bg-white/50 p-4 shadow-2xl shadow-rose-100/70 backdrop-blur-xl"
            }
          >
            <div className="mb-4 flex items-center justify-between px-2">
              <div>
                <p
                  className={
                    isChief
                      ? "text-xs font-semibold uppercase tracking-[0.24em] text-cyan-200/80"
                      : "text-xs font-semibold uppercase tracking-[0.24em] text-rose-400"
                  }
                >
                  Live preview
                </p>
                <p
                  className={
                    isChief
                      ? "mt-1 text-sm text-slate-400"
                      : "mt-1 text-sm text-slate-500"
                  }
                >
                  {modeCopy.status}
                </p>
              </div>
              {isChief ? (
                <div className="relative h-16 w-16">
                  <div className="absolute inset-0 rounded-full border border-cyan-300/30" />
                  <div className="absolute inset-3 rounded-full border border-cyan-300/20" />
                  <div className="absolute inset-[1.35rem] rounded-full bg-cyan-200 shadow-[0_0_32px_rgba(34,211,238,0.65)]" />
                </div>
              ) : (
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-gradient-to-br from-rose-100 to-violet-100 text-rose-500 shadow-inner">
                  <Heart className="h-5 w-5" />
                </div>
              )}
            </div>

            <div
              className={
                isChief
                  ? "min-h-[420px] rounded-[1.5rem] border border-white/8 bg-slate-950/45 p-4"
                  : "min-h-[420px] rounded-[1.5rem] border border-white/70 bg-white/45 p-4"
              }
            >
              <div className="space-y-4">
                {messages.map((message, index) => (
                  <div
                    key={`${message.from}-${index}`}
                    className={
                      message.from === "user"
                        ? "ml-auto max-w-[78%] rounded-3xl bg-slate-900 px-4 py-3 text-sm leading-6 text-white shadow-sm"
                        : isChief
                          ? "max-w-[86%] rounded-3xl border border-cyan-300/12 bg-white/[0.06] px-4 py-3 text-sm leading-6 text-slate-100 shadow-sm"
                          : "max-w-[86%] rounded-3xl border border-white/80 bg-white/70 px-4 py-3 text-sm leading-6 text-slate-700 shadow-sm"
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
                        ? "flex items-center gap-3 rounded-2xl border border-cyan-300/10 bg-cyan-300/[0.035] px-4 py-3 text-sm text-cyan-50"
                        : "flex items-center gap-3 rounded-2xl border border-rose-100 bg-white/55 px-4 py-3 text-sm text-slate-700"
                    }
                  >
                    <CheckCircle2
                      className={
                        isChief
                          ? "h-4 w-4 text-cyan-300"
                          : "h-4 w-4 text-rose-400"
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
                  ? "mt-4 rounded-full border border-cyan-300/15 bg-black/20 px-4 py-3 text-sm text-slate-400"
                  : "mt-4 rounded-full border border-white/80 bg-white/70 px-4 py-3 text-sm text-slate-500"
              }
            >
              {modeCopy.input}
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}

function LifeBackground() {
  return (
    <>
      <div className="absolute left-[8%] top-[10%] h-[34rem] w-[34rem] rounded-full bg-rose-200/45 blur-3xl" />
      <div className="absolute right-[10%] top-[18%] h-[30rem] w-[30rem] rounded-full bg-violet-200/40 blur-3xl" />
      <div className="absolute bottom-[-10%] left-[28%] h-[32rem] w-[32rem] rounded-full bg-amber-100/55 blur-3xl" />
    </>
  );
}

function ChiefBackground() {
  return (
    <>
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_42%,rgba(34,211,238,0.20),transparent_24rem),radial-gradient(circle_at_70%_20%,rgba(59,130,246,0.10),transparent_28rem)]" />
      <div className="absolute inset-0 opacity-[0.14] [background-image:linear-gradient(rgba(34,211,238,0.22)_1px,transparent_1px),linear-gradient(90deg,rgba(34,211,238,0.16)_1px,transparent_1px)] [background-size:52px_52px]" />
      <div className="absolute left-1/2 top-[38%] h-[32rem] w-[32rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-300/20 shadow-[0_0_80px_rgba(34,211,238,0.12)]" />
      <div className="absolute left-1/2 top-[38%] h-[19rem] w-[19rem] -translate-x-1/2 -translate-y-1/2 rounded-full border border-cyan-300/10" />
    </>
  );
}
