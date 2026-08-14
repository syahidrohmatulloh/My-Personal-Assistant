"use client";

import Link from "next/link";
import {
  ArrowRight,
  Bell,
  Brain,
  BriefcaseBusiness,
  CalendarDays,
  CircleDot,
  Heart,
  MessageCircle,
  Mic,
  Sparkles,
  Target,
  Users,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getCompanionSettings, patchCompanionSettings } from "@/lib/api";
import {
  ASSISTANT_MODE_EVENT,
  changeAssistantMode,
  extractAssistantMode,
} from "../chat-v2/mode-events";

type AssistantMode = "life_companion" | "chief_of_staff";

const ASSISTANT_NAME_CACHE_KEY = "app:assistant-name";

function cleanAssistantName(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const cleaned = value
    .trim()
    .replace(/^(sekarang|jadi|menjadi|adalah|namanya|itu)\s+/i, "")
    .trim();

  return cleaned.length > 0 ? cleaned : null;
}

function readCachedAssistantName(): string | null {
  if (typeof window === "undefined") return null;

  try {
    return cleanAssistantName(window.localStorage.getItem(ASSISTANT_NAME_CACHE_KEY));
  } catch {
    return null;
  }
}

function readCachedMode(): AssistantMode {
  if (typeof window === "undefined") return "life_companion";

  try {
    const saved = window.localStorage.getItem("aliyya.chatV2.mode");
    return saved === "chief_of_staff" ? "chief_of_staff" : "life_companion";
  } catch {
    return "life_companion";
  }
}

function getGreeting(now = new Date()): string {
  const hour = now.getHours();

  if (hour < 11) return "Selamat pagi";
  if (hour < 15) return "Selamat siang";
  if (hour < 18) return "Selamat sore";
  return "Selamat malam";
}

function formatDayTime(now = new Date()): string {
  return new Intl.DateTimeFormat("id-ID", {
    weekday: "long",
    hour: "2-digit",
    minute: "2-digit",
  })
    .format(now)
    .replace(".", ":")
    .toUpperCase();
}

function getModeCopy(mode: AssistantMode, assistantName: string) {
  if (mode === "chief_of_staff") {
    return {
      eyebrow: "Chief of Staff command center",
      title: "Your day, structured before the first message.",
      summary:
        "Agenda, goals, reminders, and unresolved threads stay visible here. Continue into chat when you need execution.",
      prompt: `Ask ${assistantName} to brief, prioritize, or turn this into action...`,
      primary: "Open execution chat",
      secondary: "Review priorities",
    };
  }

  return {
    eyebrow: "Life Companion command center",
    title: "Calm overview before you start talking.",
    summary:
      "A soft landing for your day: what matters, what can wait, and one gentle doorway into conversation.",
    prompt: `Cerita apa pun ke ${assistantName}...`,
    primary: "Talk to companion",
    secondary: "Start reflection",
  };
}

export function HomeCommandCenterClient() {
  const [mode, setModeState] = useState<AssistantMode>("life_companion");
  const [assistantName, setAssistantName] = useState<string>(() => readCachedAssistantName() ?? "Hana");
  const [now, setNow] = useState<Date>(() => new Date());

  useEffect(() => {
    setModeState(readCachedMode());

    let cancelled = false;

    getCompanionSettings()
      .then((settings) => {
        if (cancelled) return;

        const nextMode = extractAssistantMode(settings);
        if (nextMode) setModeState(nextMode);

        const nextName = cleanAssistantName(settings.assistant_name);
        if (nextName) setAssistantName(nextName);
      })
      .catch(() => {
        // Home shell stays available even if companion settings are temporarily unavailable.
      });

    function onModeEvent(event: Event) {
      const detail = (event as CustomEvent).detail;
      const nextMode = extractAssistantMode(detail);
      if (nextMode) setModeState(nextMode);
    }

    window.addEventListener(ASSISTANT_MODE_EVENT, onModeEvent);

    const timer = window.setInterval(() => setNow(new Date()), 30_000);

    return () => {
      cancelled = true;
      window.removeEventListener(ASSISTANT_MODE_EVENT, onModeEvent);
      window.clearInterval(timer);
    };
  }, []);

  const copy = useMemo(() => getModeCopy(mode, assistantName), [assistantName, mode]);
  const isChief = mode === "chief_of_staff";
  const greeting = getGreeting(now);
  const dayTime = formatDayTime(now);

  function applyModeLocally(nextMode: AssistantMode) {
    setModeState(nextMode);

    try {
      window.localStorage.setItem("aliyya.chatV2.mode", nextMode);
    } catch {}
  }

  function setMode(nextMode: AssistantMode) {
    void changeAssistantMode(nextMode, {
      applyLocally: applyModeLocally,
      persist: (mode) => patchCompanionSettings({ assistant_mode: mode }),
      fetchServerMode: async () => {
        const settings = await getCompanionSettings();
        return settings.assistant_mode === "chief_of_staff"
          ? "chief_of_staff"
          : "life_companion";
      },
    });
  }

  return (
    <main
      className={[
        "relative min-h-dvh overflow-hidden transition-colors duration-700",
        isChief ? "bg-[#070d14] text-slate-100" : "bg-[#f7f3ea] text-stone-950",
      ].join(" ")}
    >
      <HomeNebulaBackground mode={mode} />

      <div className="relative z-10 mx-auto flex min-h-dvh w-full max-w-[1500px] flex-col px-4 py-5 sm:px-6 lg:px-8">
        <header className="mb-5 flex items-center justify-between gap-3">
          <Link
            href="/chat-v2"
            className={[
              "inline-flex h-10 items-center gap-2 rounded-full border px-4 text-sm font-semibold shadow-sm backdrop-blur transition active:scale-[0.98]",
              isChief
                ? "border-white/10 bg-white/[0.045] text-slate-300 hover:bg-white/[0.07] hover:text-white"
                : "border-white/75 bg-white/70 text-stone-600 hover:bg-white hover:text-stone-950",
            ].join(" ")}
          >
            <MessageCircle className="h-4 w-4" />
            Chat V2
          </Link>

          <div
            className={[
              "hidden rounded-full border px-4 py-2 text-[11px] font-bold uppercase tracking-[0.26em] sm:block",
              isChief
                ? "border-teal-200/15 bg-teal-200/[0.06] text-teal-100"
                : "border-white/75 bg-white/60 text-stone-500",
            ].join(" ")}
          >
            Home Command Center
          </div>
        </header>

        <section className="grid flex-1 gap-5 lg:grid-cols-[1.05fr_0.95fr]">
          <section className="flex min-h-0 flex-col">
            <div
              className={[
                "relative overflow-hidden rounded-[2.25rem] border p-5 shadow-2xl backdrop-blur-xl sm:p-7 lg:min-h-[calc(100dvh-8.75rem)]",
                isChief
                  ? "border-white/10 bg-white/[0.05] shadow-black/35"
                  : "border-white/80 bg-white/58 shadow-stone-200/60",
              ].join(" ")}
            >
              <div className="pointer-events-none absolute inset-0 opacity-70">
                <div
                  className={[
                    "absolute left-10 top-10 h-64 w-64 rounded-full blur-3xl",
                    isChief ? "bg-teal-400/10" : "bg-amber-300/18",
                  ].join(" ")}
                />
                <div
                  className={[
                    "absolute bottom-8 right-8 h-72 w-72 rounded-full blur-3xl",
                    isChief ? "bg-cyan-400/10" : "bg-pink-300/14",
                  ].join(" ")}
                />
              </div>

              <div className="relative">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p
                      className={[
                        "text-[11px] font-bold uppercase tracking-[0.32em]",
                        isChief ? "text-teal-200/75" : "text-stone-400",
                      ].join(" ")}
                    >
                      {dayTime}
                    </p>
                    <h1 className="mt-5 max-w-3xl text-5xl font-semibold tracking-[-0.065em] sm:text-6xl lg:text-7xl">
                      {greeting}, Syahid.
                    </h1>
                  </div>

                  <ModeToggle mode={mode} onChange={setMode} />
                </div>

                <div className="mt-8 max-w-2xl">
                  <p
                    className={[
                      "text-[11px] font-bold uppercase tracking-[0.24em]",
                      isChief ? "text-teal-100/70" : "text-stone-400",
                    ].join(" ")}
                  >
                    {copy.eyebrow}
                  </p>
                  <h2 className="mt-3 text-2xl font-semibold tracking-[-0.04em] sm:text-3xl">
                    {copy.title}
                  </h2>
                  <p
                    className={[
                      "mt-4 text-base leading-8 sm:text-lg",
                      isChief ? "text-slate-300" : "text-stone-600",
                    ].join(" ")}
                  >
                    {copy.summary}
                  </p>
                </div>

                <div
                  className={[
                    "mt-8 rounded-[2rem] border p-3 backdrop-blur-xl",
                    isChief
                      ? "border-white/10 bg-black/18"
                      : "border-white/75 bg-white/68",
                  ].join(" ")}
                >
                  <div
                    className={[
                      "min-h-28 rounded-[1.55rem] border px-4 py-4 text-sm leading-7",
                      isChief
                        ? "border-white/10 bg-white/[0.045] text-slate-400"
                        : "border-stone-200/80 bg-white/64 text-stone-500",
                    ].join(" ")}
                  >
                    {copy.prompt}
                  </div>

                  <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div className="flex flex-wrap gap-2">
                      <HomeChip icon={<Sparkles className="h-3.5 w-3.5" />} label={copy.secondary} isChief={isChief} />
                      <HomeChip icon={<Mic className="h-3.5 w-3.5" />} label="Voice later" isChief={isChief} />
                    </div>

                    <Link
                      href="/chat-v2"
                      className={[
                        "inline-flex h-11 items-center justify-center gap-2 rounded-full px-5 text-sm font-semibold shadow-sm transition active:scale-[0.98]",
                        isChief
                          ? "bg-teal-100 text-slate-950 hover:bg-white"
                          : "bg-stone-950 text-white hover:bg-stone-800",
                      ].join(" ")}
                    >
                      {copy.primary}
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                  </div>
                </div>

                <div className="mt-6 grid gap-3 sm:grid-cols-3">
                  <VitalSign label="Calendar" value="Ready" icon={<CalendarDays className="h-4 w-4" />} isChief={isChief} />
                  <VitalSign label="Memory" value="Ready" icon={<Brain className="h-4 w-4" />} isChief={isChief} />
                  <VitalSign label="Goals" value="Ready" icon={<Target className="h-4 w-4" />} isChief={isChief} />
                </div>
              </div>
            </div>
          </section>

          <aside className="grid min-h-0 gap-4 lg:h-[calc(100dvh-8.75rem)] lg:overflow-y-auto lg:overscroll-contain lg:pr-1 lg:[scrollbar-width:thin]">
            <HomePanel
              title="Aliyya offers"
              badge="Preview"
              icon={<Sparkles className="h-4 w-4" />}
              isChief={isChief}
            >
              <div className="grid gap-2">
                {(isChief
                  ? ["Brief me for today", "Prioritize next actions", "Find blockers"]
                  : ["Tulis refleksi singkat", "Apa yang perlu ditengok?", "Bantu aku mulai pelan-pelan"]
                ).map((item) => (
                  <Link
                    key={item}
                    href="/chat-v2"
                    className={[
                      "flex items-center justify-between rounded-2xl border px-4 py-3 text-sm transition",
                      isChief
                        ? "border-white/10 bg-white/[0.035] text-slate-300 hover:bg-white/[0.06]"
                        : "border-stone-200/75 bg-white/52 text-stone-600 hover:bg-white/75 hover:text-stone-950",
                    ].join(" ")}
                  >
                    {item}
                    <ArrowRight className="h-3.5 w-3.5 opacity-55" />
                  </Link>
                ))}
              </div>
            </HomePanel>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-1">
              <HomePanel
                title="Today’s agenda"
                badge="Calendar"
                icon={<CalendarDays className="h-4 w-4" />}
                isChief={isChief}
              >
                <PreviewLine title="05:52 Golf dengan Indosat" detail="Rainbow Hills" />
                <PreviewLine title="14:00 Sync banking Q2" detail="Online" />
              </HomePanel>

              <HomePanel
                title="Upcoming reminders"
                badge="Reminders"
                icon={<Bell className="h-4 w-4" />}
                isChief={isChief}
              >
                <PreviewLine title="Dalam 2 jam" detail={`Chat sama ${assistantName}`} />
                <PreviewLine title="Besok 09:00" detail="Review goals mingguan" />
              </HomePanel>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-1">
              <HomePanel
                title="Recent memories"
                badge="Memory"
                icon={<Brain className="h-4 w-4" />}
                isChief={isChief}
              >
                <PreviewLine title="Suka kopi tanpa gula" detail="Preference" />
                <PreviewLine title="Main padel Sabtu pagi" detail="Routine" />
              </HomePanel>

              <HomePanel
                title="People who matter"
                badge="People"
                icon={<Users className="h-4 w-4" />}
                isChief={isChief}
              >
                <PreviewLine title="Indah" detail="Belum follow up" />
                <PreviewLine title="Tim Indosat" detail="Golf hari ini" />
              </HomePanel>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}

function HomeNebulaBackground({ mode }: { mode: AssistantMode }) {
  const isChief = mode === "chief_of_staff";

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className={[
          "absolute inset-0 transition-opacity duration-700",
          isChief
            ? "bg-[radial-gradient(circle_at_20%_12%,rgba(45,212,191,0.13),transparent_30rem),radial-gradient(circle_at_78%_18%,rgba(56,189,248,0.10),transparent_34rem),radial-gradient(circle_at_48%_88%,rgba(20,184,166,0.08),transparent_30rem)]"
            : "bg-[radial-gradient(circle_at_18%_12%,rgba(251,191,36,0.16),transparent_30rem),radial-gradient(circle_at_82%_16%,rgba(45,212,191,0.12),transparent_34rem),radial-gradient(circle_at_70%_86%,rgba(244,114,182,0.11),transparent_30rem)]",
        ].join(" ")}
      />
      <div
        className={[
          "absolute inset-0 opacity-[0.05] [background-image:linear-gradient(rgba(120,113,108,0.45)_1px,transparent_1px),linear-gradient(90deg,rgba(120,113,108,0.35)_1px,transparent_1px)] [background-size:46px_46px]",
          isChief ? "mix-blend-screen" : "",
        ].join(" ")}
      />
      <div
        className={[
          "absolute left-1/2 top-1/2 h-[42rem] w-[42rem] -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl transition-colors duration-700",
          isChief ? "bg-teal-400/[0.035]" : "bg-white/35",
        ].join(" ")}
      />
    </div>
  );
}

function ModeToggle({
  mode,
  onChange,
}: {
  mode: AssistantMode;
  onChange: (mode: AssistantMode) => void;
}) {
  const isChief = mode === "chief_of_staff";

  return (
    <div
      className={[
        "inline-flex rounded-full border p-1 backdrop-blur",
        isChief ? "border-white/10 bg-white/[0.045]" : "border-white/75 bg-white/65",
      ].join(" ")}
    >
      <button
        type="button"
        onClick={() => onChange("life_companion")}
        className={[
          "inline-flex h-9 items-center gap-2 rounded-full px-3 text-xs font-semibold transition",
          mode === "life_companion"
            ? isChief
              ? "bg-white text-slate-950"
              : "bg-stone-950 text-white"
            : isChief
              ? "text-slate-400 hover:text-white"
              : "text-stone-500 hover:text-stone-950",
        ].join(" ")}
      >
        <Heart className="h-3.5 w-3.5" />
        Life
      </button>
      <button
        type="button"
        onClick={() => onChange("chief_of_staff")}
        className={[
          "inline-flex h-9 items-center gap-2 rounded-full px-3 text-xs font-semibold transition",
          mode === "chief_of_staff"
            ? "bg-teal-100 text-slate-950"
            : isChief
              ? "text-slate-400 hover:text-white"
              : "text-stone-500 hover:text-stone-950",
        ].join(" ")}
      >
        <BriefcaseBusiness className="h-3.5 w-3.5" />
        Chief
      </button>
    </div>
  );
}

function HomeChip({
  icon,
  label,
  isChief,
}: {
  icon: React.ReactNode;
  label: string;
  isChief: boolean;
}) {
  return (
    <span
      className={[
        "inline-flex h-8 items-center gap-2 rounded-full border px-3 text-xs font-medium",
        isChief
          ? "border-white/10 bg-white/[0.035] text-slate-300"
          : "border-stone-200/75 bg-white/58 text-stone-600",
      ].join(" ")}
    >
      {icon}
      {label}
    </span>
  );
}

function VitalSign({
  label,
  value,
  icon,
  isChief,
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  isChief: boolean;
}) {
  return (
    <div
      className={[
        "rounded-2xl border p-4 backdrop-blur",
        isChief
          ? "border-white/10 bg-white/[0.04]"
          : "border-white/75 bg-white/58",
      ].join(" ")}
    >
      <div className="flex items-center justify-between gap-3">
        <p
          className={[
            "text-[10px] font-bold uppercase tracking-[0.22em]",
            isChief ? "text-slate-500" : "text-stone-400",
          ].join(" ")}
        >
          {label}
        </p>
        <span className={isChief ? "text-teal-100/80" : "text-stone-500"}>{icon}</span>
      </div>
      <p className="mt-3 flex items-center gap-2 text-sm font-semibold">
        <CircleDot className={isChief ? "h-3.5 w-3.5 text-teal-200" : "h-3.5 w-3.5 text-emerald-600"} />
        {value}
      </p>
    </div>
  );
}

function HomePanel({
  title,
  badge,
  icon,
  isChief,
  children,
}: {
  title: string;
  badge: string;
  icon: React.ReactNode;
  isChief: boolean;
  children: React.ReactNode;
}) {
  return (
    <section
      className={[
        "rounded-[1.75rem] border p-4 shadow-xl backdrop-blur-xl",
        isChief
          ? "border-white/10 bg-white/[0.045] shadow-black/25"
          : "border-white/80 bg-white/58 shadow-stone-200/45",
      ].join(" ")}
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p
            className={[
              "text-[10px] font-bold uppercase tracking-[0.22em]",
              isChief ? "text-teal-100/55" : "text-stone-400",
            ].join(" ")}
          >
            {badge}
          </p>
          <h3 className="mt-1 text-lg font-semibold tracking-[-0.035em]">{title}</h3>
        </div>
        <span
          className={[
            "grid h-9 w-9 shrink-0 place-items-center rounded-full",
            isChief ? "bg-teal-200/[0.07] text-teal-100" : "bg-white/70 text-stone-500",
          ].join(" ")}
        >
          {icon}
        </span>
      </div>
      <div className="grid gap-2">{children}</div>
    </section>
  );
}

function PreviewLine({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="rounded-2xl border border-current/10 bg-white/[0.035] px-3 py-3">
      <p className="text-sm font-semibold leading-5">{title}</p>
      <p className="mt-1 text-xs leading-5 opacity-60">{detail}</p>
    </div>
  );
}
