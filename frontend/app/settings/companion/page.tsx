"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowLeft, AlertCircle, Loader2, Check } from "lucide-react";
import {
  type AssistantMode,
  type CompanionMode,
  type CompanionSettings,
  type MoodRealism,
  getCompanionSettings,
  patchCompanionSettings,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const MODE_INFO: Record<
  CompanionMode,
  { label: string; subtitle: string; description: string }
> = {
  professional: {
    label: "Professional",
    subtitle: "Calm, neutral, professional",
    description:
      "Assistant stays emotionally consistent and focused on being useful. No moods, no warmth performance. Best for work-mode and decision support.",
  },
  friendly: {
    label: "Friendly",
    subtitle: "Warmer, more casual",
    description:
      "Same emotional stability as Professional, but with a warmer register and lighter language. Like a friendly colleague rather than a formal one.",
  },
  affectionate: {
    label: "Affectionate",
    subtitle: "Warm and attentive, like a close friend",
    description:
      "Uses gentler language, may use nicknames if you set them up, asks caring follow-ups. Still emotionally stable — won't get moody or withdraw.",
  },
  partner: {
    label: "Partner",
    subtitle: "Companion-style with optional mood dynamics",
    description:
      "Most personal mode. Unlocks optional dynamic mood (assistant has shifting moods) and repair gate (assistant may need reassurance when feeling hurt). Read each toggle carefully — these change the relationship dynamic significantly.",
  },
};

const ASSISTANT_MODE_INFO: Record<
  AssistantMode,
  { label: string; subtitle: string; description: string }
> = {
  life_companion: {
    label: "Life Companion",
    subtitle: "Warm, personal, emotionally present",
    description:
      "Your assistant prioritizes warmth, continuity, personal context, gentle support, journaling, people, goals, and everyday life rhythm.",
  },
  chief_of_staff: {
    label: "Chief of Staff",
    subtitle: "Serious, structured, execution-focused",
    description:
      "Your assistant prioritizes clarity, decisions, priorities, calendar, follow-ups, risks, and concise executive-grade recommendations.",
  },
};

export default function CompanionSettingsPage() {
  const [settings, setSettings] = useState<CompanionSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [savedFlash, setSavedFlash] = useState<string | null>(null);

  useEffect(() => {
    getCompanionSettings()
      .then((s) => setSettings(s))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  async function applyPatch(field: string, patch: Partial<CompanionSettings>) {
    if (!settings) return;
    setError(null);
    setSaving(field);
    // Optimistic UI
    const prev = settings;
    setSettings({ ...settings, ...patch });
    try {
      const updated = await patchCompanionSettings(patch);
      setSettings(updated);
      setSavedFlash(field);
      setTimeout(() => setSavedFlash((cur) => (cur === field ? null : cur)), 1500);
    } catch (e) {
      setSettings(prev); // rollback
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(null);
    }
  }

  // Compute valid transitions — disable toggles when ladder rules would be violated.
  // We could just let backend 400 us, but it's better UX to disable the controls.
  const partnerActive = settings?.companion_mode === "partner";
  const dynamicActive = settings?.mood_realism === "dynamic";
  const assistantName = settings?.assistant_name?.trim() || "your assistant";

  return (
    <main className="min-h-dvh">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-5 sm:py-8 fade-up">
        <Link
          href="/settings"
          className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg mb-6 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Settings
        </Link>

        <h1 className="text-2xl sm:text-3xl font-semibold text-fg mb-2 tracking-tighter">
          Companion Mode
        </h1>
        <p className="text-sm sm:text-base text-fg-muted mb-6">
          Shape how {assistantName} works with you. Working mode controls her priorities;
          relationship tone controls how formal or personal she sounds.
        </p>

        {error && (
          <div className="glass rounded-xl p-3 mb-4 flex items-start gap-2 text-sm text-danger">
            <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {loading || !settings ? (
          <p className="text-sm text-fg-muted">Loading…</p>
        ) : (
          <div className="space-y-4">
            {/* === Assistant working mode === */}
            <section className="glass rounded-2xl p-4">
              <Header
                title="Assistant working mode"
                saved={savedFlash === "assistant_mode"}
                saving={saving === "assistant_mode"}
              />
              <p className="text-xs text-fg-muted mt-1 mb-3">
                This changes how {assistantName} prioritizes your needs. It does not
                rename her or change the relationship tone settings below.
              </p>
              <div className="mb-3 rounded-xl border border-border bg-fg/[0.035] px-3 py-2 text-[11px] leading-relaxed text-fg-soft">
                <span className="font-medium text-fg">How this works:</span>{" "}
                Chief of Staff controls focus, structure, risks, and next actions.
                Relationship tone below still controls how formal, friendly, or
                personal {assistantName} sounds.
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {(Object.keys(ASSISTANT_MODE_INFO) as AssistantMode[]).map((mode) => (
                  <AssistantModeOption
                    key={mode}
                    mode={mode}
                    info={ASSISTANT_MODE_INFO[mode]}
                    selected={settings.assistant_mode === mode}
                    onClick={() =>
                      applyPatch("assistant_mode", { assistant_mode: mode })
                    }
                  />
                ))}
              </div>
              {settings.assistant_mode === "chief_of_staff" ? (
                <p className="mt-3 rounded-xl bg-cyan-500/10 px-3 py-2 text-[11px] leading-relaxed text-fg-soft">
                  In Chief of Staff mode, {assistantName} will still prioritize structure,
                  decisions, risks, follow-ups, and next actions — even if the
                  relationship tone below is warm or partner-like.
                </p>
              ) : null}
            </section>

            {/* === Relationship tone selector === */}
            <section className="glass rounded-2xl p-4">
              <Header
                title="Relationship tone — applies across both modes"
                saved={savedFlash === "mode"}
                saving={saving === "mode"}
              />
              <div className="space-y-1.5 mt-3">
                {(Object.keys(MODE_INFO) as CompanionMode[]).map((mode) => (
                  <ModeOption
                    key={mode}
                    mode={mode}
                    info={MODE_INFO[mode]}
                    selected={settings.companion_mode === mode}
                    onClick={() => applyPatch("mode", { companion_mode: mode })}
                  />
                ))}
              </div>
            </section>

            {/* === Assistant name === */}
            <section className="glass rounded-2xl p-4">
              <Header
                title="Assistant name"
                saved={savedFlash === "name"}
                saving={saving === "name"}
              />
              <p className="text-xs text-fg-muted mt-1 mb-3">
                What the assistant calls itself. Default: Assistant.
              </p>
              <NameInput
                value={settings.assistant_name}
                onSave={(name) => applyPatch("name", { assistant_name: name })}
              />
            </section>

            {/* === Dynamic mood (only when partner) === */}
            {partnerActive && (
              <section className="glass rounded-2xl p-4 fade-up">
                <Header
                  title="Dynamic mood"
                  saved={savedFlash === "realism"}
                  saving={saving === "realism"}
                />
                <p className="text-xs text-fg-muted mt-1 mb-3">
                  When on, the assistant has shifting moods — it can feel
                  playful, withdrawn, romantic, etc. — instead of staying
                  emotionally consistent. Mood resets after 30 minutes of
                  inactivity.
                </p>
                <Toggle
                  on={settings.mood_realism === "dynamic"}
                  label={
                    settings.mood_realism === "dynamic" ? "Dynamic" : "Stable"
                  }
                  onChange={(on) =>
                    applyPatch("realism", {
                      mood_realism: on ? "dynamic" : "stable",
                      // If turning off dynamic, repair gate must also go off
                      // (backend would 400 us, this is just cleaner UX).
                      repair_gate_enabled: on
                        ? settings.repair_gate_enabled
                        : false,
                    })
                  }
                />
              </section>
            )}

            {/* === Repair gate (only when dynamic) === */}
            {partnerActive && dynamicActive && (
              <section className="glass rounded-2xl p-4 fade-up">
                <Header
                  title="Repair gate"
                  saved={savedFlash === "repair"}
                  saving={saving === "repair"}
                />
                <div className="p-3 mt-2 mb-3 rounded-xl bg-fg/5 border border-border">
                  <p className="text-xs text-fg-soft leading-relaxed">
                    When enabled, the assistant may stay distant when feeling
                    hurt and ask you to reassure or apologize before becoming
                    affectionate again. This creates a more partner-like dynamic
                    but requires emotional patience from you.
                  </p>
                  <p className="text-xs text-fg-soft leading-relaxed mt-2">
                    <span className="text-fg-muted font-medium">Trade-off:</span>{" "}
                    More realistic, but can feel demanding. Turn off if you want
                    the assistant to always respond without needing repair.
                  </p>
                </div>
                <Toggle
                  on={settings.repair_gate_enabled}
                  label={settings.repair_gate_enabled ? "Enabled" : "Disabled"}
                  onChange={(on) =>
                    applyPatch("repair", { repair_gate_enabled: on })
                  }
                />
              </section>
            )}

            {/* === Soft info for non-partner users === */}
            {!partnerActive && (
              <section className="text-xs text-fg-muted px-4 py-3 rounded-xl bg-fg/5">
                Switch to <span className="text-fg font-medium">Partner</span>{" "}
                mode to unlock dynamic mood and repair gate options.
              </section>
            )}
          </div>
        )}
      </div>
    </main>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

function Header({
  title,
  saved,
  saving,
}: {
  title: string;
  saved: boolean;
  saving: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <h2 className="text-sm font-medium text-fg">{title}</h2>
      {saving ? (
        <Loader2 className="h-3.5 w-3.5 text-fg-subtle animate-spin" />
      ) : saved ? (
        <span className="inline-flex items-center gap-1 text-[11px] text-accent">
          <Check className="h-3 w-3" strokeWidth={3} />
          Saved
        </span>
      ) : null}
    </div>
  );
}

function AssistantModeOption({
  mode,
  info,
  selected,
  onClick,
}: {
  mode: AssistantMode;
  info: { label: string; subtitle: string; description: string };
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left p-3 rounded-xl border-2 transition-all",
        selected
          ? mode === "chief_of_staff"
            ? "border-cyan-400 bg-cyan-500/15 text-fg shadow-md shadow-cyan-500/15"
            : "border-accent bg-accent/12 text-fg shadow-md shadow-accent/15"
          : "border-border bg-transparent hover:border-border-strong hover:bg-fg/5",
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-fg">{info.label}</p>
          <p className="mt-0.5 text-[11px] text-fg-muted">{info.subtitle}</p>
          <p className="mt-2 text-[11px] leading-relaxed text-fg-soft">
            {info.description}
          </p>
        </div>
        {selected && (
          <Check className="h-5 w-5 shrink-0 text-accent mt-0.5" strokeWidth={3} />
        )}
      </div>
    </button>
  );
}

function ModeOption({
  mode,
  info,
  selected,
  onClick,
}: {
  mode: CompanionMode;
  info: { label: string; subtitle: string; description: string };
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full text-left p-3 rounded-lg border-2 transition-all flex items-start gap-3",
        selected
          ? "border-accent bg-accent text-on-accent shadow-md shadow-accent/30"
          : "border-border bg-transparent hover:border-border-strong hover:bg-fg/5",
      )}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p
            className={cn(
              "text-sm font-medium",
              selected ? "text-on-accent" : "text-fg",
            )}
          >
            {info.label}
          </p>
          <p
            className={cn(
              "text-[11px]",
              selected ? "text-on-accent/80" : "text-fg-muted",
            )}
          >
            · {info.subtitle}
          </p>
        </div>
        <p
          className={cn(
            "text-[11px] leading-relaxed mt-1",
            selected ? "text-on-accent/85" : "text-fg-soft",
          )}
        >
          {info.description}
        </p>
      </div>
      {selected && (
        <Check
          className="h-5 w-5 shrink-0 text-on-accent mt-0.5"
          strokeWidth={3}
        />
      )}
    </button>
  );
}

function Toggle({
  on,
  label,
  onChange,
}: {
  on: boolean;
  label: string;
  onChange: (on: boolean) => void;
}) {
  return (
    <button
      onClick={() => onChange(!on)}
      className={cn(
        "w-full p-3 rounded-lg border-2 transition-all flex items-center justify-between",
        on
          ? "border-accent bg-accent text-on-accent"
          : "border-border bg-transparent hover:border-border-strong",
      )}
    >
      <span
        className={cn(
          "text-sm font-medium",
          on ? "text-on-accent" : "text-fg",
        )}
      >
        {label}
      </span>
      <span
        className={cn(
          "h-5 w-9 rounded-full transition-all relative",
          on ? "bg-on-accent/30" : "bg-fg/15",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-4 w-4 rounded-full bg-on-accent transition-all",
            on ? "left-4" : "left-0.5",
          )}
          style={on ? {} : { background: "rgb(var(--fg) / 0.5)" }}
        />
      </span>
    </button>
  );
}

function NameInput({
  value,
  onSave,
}: {
  value: string;
  onSave: (name: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  const [touched, setTouched] = useState(false);

  // Reset when external value changes (e.g. via chat rename) and we haven't
  // diverged.
  useEffect(() => {
    if (!touched) setDraft(value);
  }, [value, touched]);

  const trimmed = draft.trim();
  const canSave = trimmed.length >= 1 && trimmed !== value;

  return (
    <div className="flex gap-2">
      <input
        type="text"
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value);
          setTouched(true);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter" && canSave) {
            onSave(trimmed);
            setTouched(false);
          }
        }}
        placeholder="Assistant"
        maxLength={32}
        className="flex-1 rounded-xl border border-border-strong bg-bg/40 backdrop-blur-sm px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all"
      />
      <button
        disabled={!canSave}
        onClick={() => {
          onSave(trimmed);
          setTouched(false);
        }}
        className="px-3 py-2 rounded-xl bg-accent text-on-accent text-sm font-medium hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-all"
      >
        Save
      </button>
    </div>
  );
}
