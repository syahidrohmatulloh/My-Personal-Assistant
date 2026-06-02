"use client";

import Link from "next/link";
import {
  ArrowLeft,
  Brain,
  BriefcaseBusiness,
  CalendarDays,
  CheckCircle2,
  CircleDot,
  Compass,
  Expand,
  Heart,
  Lightbulb,
  Minimize2,
  Newspaper,
  Sparkles,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { Message } from "@/lib/api";

type AssistantMode = "life_companion" | "chief_of_staff";

type LayoutMode = "split" | "expanded";

const modeCopy = {
  life_companion: {
    eyebrow: "Soft personal sanctuary",
    title: "Life Companion",
    description:
      "Warm, personal, and emotionally present. Aliyya helps you reflect, remember, and navigate life with continuity.",
    input: "Cerita ke Aliyya...",
    user: "Aku capek hari ini, tapi pikiranku masih rame.",
    assistant:
      "Aku di sini. Kita pelan-pelan aja ya. Ceritain satu hal yang paling berat dulu, nanti aku bantu rapihin jadi langkah kecil.",
  },
  chief_of_staff: {
    eyebrow: "Calm executive cockpit",
    title: "Chief of Staff",
    description:
      "Structured, concise, and decision-oriented. Aliyya helps prioritize, identify risks, and move execution forward.",
    input: "Ask Aliyya to brief, prioritize, or structure next actions...",
    user: "Besok banyak agenda. Bantu aku prioritasin.",
    assistant:
      "Baik, Syahid. Bottom line: kita pisahkan agenda menjadi keputusan, follow-up, dan deep work. Kirim daftar agendanya; aku susun prioritas, risiko, dan next action.",
  },
};

export function ChatV2Client({
  initialMessages = [],
  conversationTitle = null,
}: {
  initialMessages?: Message[];
  conversationTitle?: string | null;
}) {
  const [mode, setModeState] = useState<AssistantMode>("life_companion");
  const [layout, setLayoutState] = useState<LayoutMode>("split");

  const isChief = mode === "chief_of_staff";

  useEffect(() => {
    try {
      const savedMode = window.localStorage.getItem("aliyya.chatV2.mode");
      const nextMode: AssistantMode =
        savedMode === "chief_of_staff" ? "chief_of_staff" : "life_companion";

      const savedLayout = window.localStorage.getItem(`aliyya.chatV2.layout.${nextMode}`);
      const defaultLayout: LayoutMode = "split";
      const nextLayout: LayoutMode =
        savedLayout === "split" || savedLayout === "expanded" ? savedLayout : defaultLayout;

      setModeState(nextMode);
      setLayoutState(nextLayout);
    } catch {
      setModeState("life_companion");
      setLayoutState("split");
    }
  }, []);

  function setMode(nextMode: AssistantMode) {
    setModeState(nextMode);

    try {
      window.localStorage.setItem("aliyya.chatV2.mode", nextMode);
      const savedLayout = window.localStorage.getItem(`aliyya.chatV2.layout.${nextMode}`);
      const defaultLayout: LayoutMode = "split";

      setLayoutState(
        savedLayout === "split" || savedLayout === "expanded" ? savedLayout : defaultLayout,
      );
    } catch {
      setLayoutState("split");
    }
  }

  function setLayout(nextLayout: LayoutMode) {
    setLayoutState(nextLayout);

    try {
      window.localStorage.setItem(`aliyya.chatV2.layout.${mode}`, nextLayout);
    } catch {}
  }

  const isExpanded = layout === "expanded";
  const copy = modeCopy[mode];

  const leftPanel = useMemo(() => {
    return isChief ? <ChiefDeskPanel /> : <CompanionDeskPanel />;
  }, [isChief]);

  return (
    <main
      className={[
        "relative min-h-dvh overflow-hidden transition-colors duration-700",
        isChief ? "bg-[#080d14] text-slate-100" : "bg-[#f7f3ea] text-stone-950",
      ].join(" ")}
    >
      <ModeBackground mode={mode} />

      <div className="relative z-10 mx-auto flex min-h-dvh w-full max-w-[1500px] flex-col px-4 py-5 sm:px-6 lg:px-8">
        <header className="mb-5 flex items-center justify-between gap-3">
          <Link
            href="/chat"
            className={[
              "inline-flex h-10 items-center gap-2 rounded-full border px-4 text-sm font-medium shadow-sm backdrop-blur transition active:scale-[0.98]",
              isChief
                ? "border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.07] hover:text-white"
                : "border-stone-200 bg-white/70 text-stone-600 hover:bg-white hover:text-stone-950",
            ].join(" ")}
          >
            <ArrowLeft className="h-4 w-4" />
            Back to app
          </Link>

          <div
            className={[
              "hidden rounded-full border px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.26em] sm:block",
              isChief
                ? "border-teal-200/15 bg-teal-200/[0.06] text-teal-100"
                : "border-stone-200 bg-white/65 text-stone-500",
            ].join(" ")}
          >
            Chat V2 Preview
          </div>
        </header>

        <section
          className={[
            "grid flex-1 gap-5 transition-all duration-700",
            isExpanded ? "grid-cols-1" : "grid-cols-1 xl:grid-cols-[0.82fr_1.18fr]",
          ].join(" ")}
        >
          {!isExpanded ? (
            <aside className="min-h-0">
              <div className="mb-5">
                <ModePill mode={mode} />
                <h1 className="mt-5 max-w-2xl text-5xl font-semibold tracking-[-0.06em] sm:text-6xl lg:text-7xl">
                  {copy.title}
                </h1>
                <p
                  className={[
                    "mt-5 max-w-xl text-base leading-8 sm:text-lg",
                    isChief ? "text-slate-300" : "text-stone-600",
                  ].join(" ")}
                >
                  {copy.description}
                </p>
              </div>

              <ModeToggle mode={mode} setMode={setMode} />

              <div className="mt-5">{leftPanel}</div>
            </aside>
          ) : null}

          <section className="flex min-h-0 flex-col">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <p
                  className={[
                    "text-[11px] font-semibold uppercase tracking-[0.28em]",
                    isChief ? "text-teal-200/80" : "text-stone-400",
                  ].join(" ")}
                >
                  {copy.eyebrow}
                </p>
                <p
                  className={[
                    "mt-1 text-sm",
                    isChief ? "text-slate-400" : "text-stone-500",
                  ].join(" ")}
                >
                  {isExpanded ? "Focus chat active" : "Assistant desk active"}
                </p>
              </div>

              <div className="flex items-center gap-2">
                {isExpanded ? <ModeToggle mode={mode} setMode={setMode} compact /> : null}
                <button
                  type="button"
                  onClick={() => setLayout(isExpanded ? "split" : "expanded")}
                  className={[
                    "inline-flex h-10 items-center gap-2 rounded-full border px-3 text-sm font-medium shadow-sm backdrop-blur transition active:scale-[0.98]",
                    isChief
                      ? "border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.07] hover:text-white"
                      : "border-stone-200 bg-white/70 text-stone-600 hover:bg-white hover:text-stone-950",
                  ].join(" ")}
                >
                  {isExpanded ? (
                    <>
                      <Minimize2 className="h-4 w-4" />
                      Split
                    </>
                  ) : (
                    <>
                      <Expand className="h-4 w-4" />
                      Expand
                    </>
                  )}
                </button>
              </div>
            </div>

            <ChatFrame mode={mode} isExpanded={isExpanded} messages={initialMessages} conversationTitle={conversationTitle} />
          </section>
        </section>
      </div>
    </main>
  );
}

function ModeBackground({ mode }: { mode: AssistantMode }) {
  if (mode === "chief_of_staff") {
    return (
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[#080d14]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_24%,rgba(45,212,191,0.16),transparent_28rem),radial-gradient(circle_at_18%_78%,rgba(96,165,250,0.08),transparent_32rem),radial-gradient(circle_at_82%_88%,rgba(180,130,58,0.05),transparent_26rem)]" />
        <div className="absolute inset-0 opacity-[0.045] [background-image:linear-gradient(rgba(148,163,184,0.30)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.24)_1px,transparent_1px)] [background-size:48px_48px]" />
        <div className="absolute right-[-8%] top-[4%] h-[42rem] w-[42rem] rounded-full bg-teal-300/[0.08] blur-[120px]" />
        <div className="absolute bottom-[-20%] left-[-14%] h-[44rem] w-[44rem] rounded-full bg-blue-400/[0.05] blur-[150px]" />
      </div>
    );
  }

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      <div className="absolute inset-0 bg-[#f7f3ea]" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(244,194,194,0.42),transparent_28rem),radial-gradient(circle_at_76%_18%,rgba(206,220,183,0.34),transparent_30rem),radial-gradient(circle_at_48%_86%,rgba(235,224,166,0.36),transparent_34rem)]" />
      <div className="absolute bottom-[-18%] left-[10%] h-[34rem] w-[34rem] rounded-full bg-lime-200/20 blur-[120px]" />
      <div className="absolute right-[-10%] top-[20%] h-[34rem] w-[34rem] rounded-full bg-rose-200/20 blur-[130px]" />
    </div>
  );
}

function ModePill({ mode }: { mode: AssistantMode }) {
  const isChief = mode === "chief_of_staff";
  const Icon = isChief ? BriefcaseBusiness : Sparkles;

  return (
    <div
      className={[
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] shadow-sm backdrop-blur",
        isChief
          ? "border-teal-200/15 bg-teal-200/[0.06] text-teal-100"
          : "border-stone-200 bg-white/65 text-stone-500",
      ].join(" ")}
    >
      <Icon className="h-3.5 w-3.5" />
      {isChief ? "Calm executive cockpit" : "Soft personal sanctuary"}
    </div>
  );
}

function ModeToggle({
  mode,
  setMode,
  compact = false,
}: {
  mode: AssistantMode;
  setMode: (mode: AssistantMode) => void;
  compact?: boolean;
}) {
  const isChief = mode === "chief_of_staff";

  return (
    <div
      className={[
        "inline-flex rounded-full border p-1 shadow-sm backdrop-blur",
        isChief
          ? "border-white/10 bg-black/20"
          : "border-stone-200 bg-white/65",
      ].join(" ")}
    >
      <button
        type="button"
        onClick={() => setMode("life_companion")}
        className={[
          "rounded-full px-4 py-2 text-sm font-semibold transition",
          compact ? "px-3 py-1.5 text-xs" : "",
          !isChief
            ? "bg-white text-stone-950 shadow-sm"
            : "text-slate-400 hover:text-white",
        ].join(" ")}
      >
        Life
      </button>
      <button
        type="button"
        onClick={() => setMode("chief_of_staff")}
        className={[
          "rounded-full px-4 py-2 text-sm font-semibold transition",
          compact ? "px-3 py-1.5 text-xs" : "",
          isChief
            ? "border border-teal-200/20 bg-slate-800/80 text-white shadow-sm"
            : "text-stone-500 hover:text-stone-950",
        ].join(" ")}
      >
        Chief
      </button>
    </div>
  );
}

function CompanionDeskPanel() {
  return (
    <div className="grid gap-3">
      <PanelCard tone="life" icon={<Heart className="h-4 w-4" />} title="Gentle check-in">
        <p>You may want a slower space tonight. Keep the chat open and process one thing at a time.</p>
      </PanelCard>
      <PanelCard tone="life" icon={<Lightbulb className="h-4 w-4" />} title="Ideas to revisit">
        <ul>
          <li>Chat V2 flexible workspace</li>
          <li>Voice cloning research notes</li>
          <li>Personal briefing preferences</li>
        </ul>
      </PanelCard>
      <PanelCard tone="life" icon={<Brain className="h-4 w-4" />} title="Memory signal">
        <p>Family, personal rhythm, and project continuity stay visible without crowding the chat.</p>
      </PanelCard>
      <PanelCard tone="life" icon={<Compass className="h-4 w-4" />} title="Optional briefing">
        <p>Later this can become a personal digest: family, ideas, health rhythm, or topics you ask Aliyya to track.</p>
      </PanelCard>
    </div>
  );
}

function ChiefDeskPanel() {
  return (
    <div className="grid gap-3">
      <PanelCard tone="chief" icon={<CalendarDays className="h-4 w-4" />} title="Today brief">
        <ul>
          <li>3 agenda blocks to review</li>
          <li>2 follow-ups open</li>
          <li>1 decision queue item</li>
        </ul>
      </PanelCard>
      <PanelCard tone="chief" icon={<CheckCircle2 className="h-4 w-4" />} title="Priority queue">
        <ul>
          <li>Decide Chat V2 scope</li>
          <li>Clean quick action UX</li>
          <li>Plan briefing panel sources</li>
        </ul>
      </PanelCard>
      <PanelCard tone="chief" icon={<Newspaper className="h-4 w-4" />} title="Briefing topics">
        <p>Economy, banking, AI, tech, market news, or any custom topic you ask Aliyya to track.</p>
      </PanelCard>
      <PanelCard tone="chief" icon={<CircleDot className="h-4 w-4" />} title="Risks & blockers">
        <p>Keep visual experiments isolated in Chat V2 until the main chat replacement is proven stable.</p>
      </PanelCard>
    </div>
  );
}

function PanelCard({
  tone,
  icon,
  title,
  children,
}: {
  tone: "life" | "chief";
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  const isChief = tone === "chief";

  return (
    <div
      className={[
        "rounded-3xl border p-4 shadow-sm backdrop-blur",
        isChief
          ? "border-white/10 bg-white/[0.045] text-slate-300"
          : "border-white/70 bg-white/52 text-stone-600",
      ].join(" ")}
    >
      <div className="mb-3 flex items-center gap-2">
        <span
          className={[
            "grid h-8 w-8 place-items-center rounded-full",
            isChief ? "bg-teal-200/[0.08] text-teal-100" : "bg-white/70 text-stone-500",
          ].join(" ")}
        >
          {icon}
        </span>
        <h2 className={isChief ? "font-semibold text-white" : "font-semibold text-stone-950"}>
          {title}
        </h2>
      </div>
      <div className="text-sm leading-6 [&_ul]:space-y-1 [&_li]:list-inside [&_li]:list-disc">
        {children}
      </div>
    </div>
  );
}

function ChatFrame({
  mode,
  isExpanded,
  messages,
  conversationTitle,
}: {
  mode: AssistantMode;
  isExpanded: boolean;
  messages: Message[];
  conversationTitle?: string | null;
}) {
  const isChief = mode === "chief_of_staff";
  const copy = modeCopy[mode];

  return (
    <div
      className={[
        "flex h-[calc(100dvh-8.75rem)] min-h-[520px] flex-col overflow-hidden rounded-[2rem] border shadow-2xl backdrop-blur-xl transition-all duration-700",
        isExpanded ? "mx-auto w-full max-w-5xl" : "w-full",
        isChief
          ? "border-teal-100/20 bg-[#0b141d]/82 shadow-black/35"
          : "border-white/80 bg-white/62 shadow-stone-200/60",
      ].join(" ")}
    >
      <div
        className={[
          "flex items-center justify-between border-b px-5 py-4",
          isChief ? "border-white/10" : "border-stone-200/70",
        ].join(" ")}
      >
        <div>
          <p
            className={[
              "text-[11px] font-semibold uppercase tracking-[0.28em]",
              isChief ? "text-teal-200/80" : "text-stone-400",
            ].join(" ")}
          >
            Live workspace
          </p>
          <p className={isChief ? "mt-1 text-sm text-slate-400" : "mt-1 text-sm text-stone-500"}>
            {conversationTitle || (isExpanded ? "Expanded chat" : "Split assistant desk")}
          </p>
        </div>

        <div
          className={[
            "grid h-12 w-12 place-items-center rounded-full border",
            isChief
              ? "border-teal-200/15 bg-teal-200/[0.06] shadow-[0_0_24px_rgba(45,212,191,0.20)]"
              : "border-stone-200 bg-white/70",
          ].join(" ")}
        >
          {isChief ? <CircleDot className="h-5 w-5 text-teal-100" /> : <Heart className="h-5 w-5 text-stone-500" />}
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-6 pr-3 scroll-smooth [scrollbar-width:thin]">
        {(messages.length > 0 ? messages.slice(-12) : null)?.map((message) => (
          <div
            key={message.id}
            className={[
              message.role === "user"
                ? "ml-auto max-w-[78%] rounded-full px-5 py-3 text-sm leading-6"
                : "max-w-[86%] rounded-3xl border px-5 py-4 text-sm leading-7",
              message.role === "user"
                ? isChief
                  ? "bg-slate-100 text-slate-950"
                  : "bg-stone-900 text-stone-50"
                : isChief
                  ? "border-white/10 bg-white/[0.055] text-slate-200"
                  : "border-white/80 bg-white/72 text-stone-800",
            ].join(" ")}
          >
            {message.content}
          </div>
        ))}

        {messages.length === 0 ? (
          <>
            <div
              className={[
                "ml-auto max-w-[78%] rounded-full px-5 py-3 text-sm leading-6",
                isChief ? "bg-slate-100 text-slate-950" : "bg-stone-900 text-stone-50",
              ].join(" ")}
            >
              {copy.user}
            </div>

            <div
              className={[
                "max-w-[86%] rounded-3xl border px-5 py-4 text-sm leading-7",
                isChief
                  ? "border-white/10 bg-white/[0.055] text-slate-200"
                  : "border-white/80 bg-white/72 text-stone-800",
              ].join(" ")}
            >
              {copy.assistant}
            </div>
          </>
        ) : null}

        <div className="grid gap-3 pt-4">
          {(isChief
            ? ["Brief me for today", "Prioritize my next actions", "Find risks and blockers"]
            : ["Help me reflect", "Write a gentle journal", "Remember this moment"]
          ).map((item) => (
            <button
              key={item}
              type="button"
              className={[
                "flex items-center gap-3 rounded-2xl border px-4 py-3 text-left text-sm transition",
                isChief
                  ? "border-teal-100/10 bg-black/12 text-slate-300 hover:bg-white/[0.055]"
                  : "border-stone-200/70 bg-white/45 text-stone-600 hover:bg-white/65",
              ].join(" ")}
            >
              <CheckCircle2 className={isChief ? "h-4 w-4 text-teal-200/70" : "h-4 w-4 text-stone-400"} />
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="shrink-0 p-5">
        <div
          className={[
            "rounded-2xl border px-4 py-3 text-sm",
            isChief
              ? "border-white/15 bg-black/15 text-slate-400"
              : "border-white/80 bg-white/76 text-stone-500",
          ].join(" ")}
        >
          {copy.input}
        </div>
      </div>
    </div>
  );
}
