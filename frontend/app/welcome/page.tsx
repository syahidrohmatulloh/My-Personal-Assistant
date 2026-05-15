"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Check, Sparkles } from "lucide-react";
import {
  type GoalInput,
  createGoal,
  getIdentity,
  putIdentity,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type Step = 1 | 2 | 3;

export default function WelcomePage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>(1);
  const [loading, setLoading] = useState(true);

  // step 1 — basic identity
  const [name, setName] = useState("");
  const [communication, setCommunication] = useState("");

  // step 2 — narrative
  const [narrative, setNarrative] = useState("");

  // step 3 — first goal (optional)
  const [goalTitle, setGoalTitle] = useState("");
  const [goalHorizon, setGoalHorizon] = useState<"week" | "month" | "quarter" | "year">("quarter");

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Skip onboarding if identity already set.
  useEffect(() => {
    let cancelled = false;
    getIdentity()
      .then((data) => {
        if (cancelled) return;
        if (data.profile && Object.keys(data.profile).length > 0) {
          router.replace("/chat");
          return;
        }
        setLoading(false);
      })
      .catch(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [router]);

  async function handleFinish() {
    setSaving(true);
    setError(null);
    try {
      const profile: Record<string, unknown> = {};
      if (name.trim()) profile.name = name.trim();
      if (communication.trim()) {
        profile.communication_preferences = { tone: communication.trim() };
      }
      await putIdentity(profile, narrative.trim() || null);

      if (goalTitle.trim()) {
        const goal: GoalInput = {
          title: goalTitle.trim(),
          horizon: goalHorizon,
          emotional_weight: 7,
        };
        await createGoal(goal);
      }

      router.replace("/chat");
    } catch (e) {
      setError(String(e));
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main className="min-h-screen grid place-items-center">
        <p className="text-sm text-fg-muted">…</p>
      </main>
    );
  }

  return (
    <main className="min-h-dvh grid place-items-center px-5 sm:px-6 py-8 py-12">
      <div className="w-full max-w-md fade-up">
        {/* Logo */}
        <div className="flex flex-col items-center mb-6">
          <div className="h-12 w-12 rounded-2xl bg-accent grid place-items-center shadow-xl shadow-accent/30 mb-3">
            <Sparkles className="h-5 w-5 text-on-accent" strokeWidth={2.2} />
          </div>
        </div>

        {/* Progress */}
        <div className="flex items-center justify-center gap-2 mb-6">
          {[1, 2, 3].map((n) => (
            <div
              key={n}
              className={cn(
                "h-1 rounded-full transition-all",
                step >= n ? "bg-accent w-8" : "bg-border-strong w-4",
              )}
            />
          ))}
        </div>

        {/* Step content */}
        <div className="glass rounded-2xl p-6">
          {step === 1 && (
            <Step1
              name={name}
              setName={setName}
              communication={communication}
              setCommunication={setCommunication}
            />
          )}
          {step === 2 && <Step2 narrative={narrative} setNarrative={setNarrative} />}
          {step === 3 && (
            <Step3
              title={goalTitle}
              setTitle={setGoalTitle}
              horizon={goalHorizon}
              setHorizon={setGoalHorizon}
            />
          )}

          {error && <p className="text-sm text-danger mt-3">{error}</p>}

          {/* Nav */}
          <div className="flex items-center justify-between mt-6 pt-4 border-t border-border">
            {step > 1 ? (
              <button
                type="button"
                onClick={() => setStep((s) => (s - 1) as Step)}
                className="text-sm text-fg-muted hover:text-fg"
              >
                Back
              </button>
            ) : (
              <button
                type="button"
                onClick={() => router.replace("/chat")}
                className="text-sm text-fg-subtle hover:text-fg-muted"
              >
                Skip for now
              </button>
            )}

            {step < 3 ? (
              <button
                onClick={() => setStep((s) => (s + 1) as Step)}
                className="inline-flex items-center gap-1.5 rounded-xl bg-accent text-on-accent px-4 py-2 text-sm font-medium hover:bg-accent-hover transition-all active:scale-[0.98] shadow-md shadow-accent/25"
              >
                Continue
                <ArrowRight className="h-3.5 w-3.5" strokeWidth={2.5} />
              </button>
            ) : (
              <button
                onClick={handleFinish}
                disabled={saving}
                className="inline-flex items-center gap-1.5 rounded-xl bg-accent text-on-accent px-4 py-2 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-all active:scale-[0.98] shadow-md shadow-accent/25"
              >
                {saving ? "Saving…" : "Get started"}
                <Check className="h-3.5 w-3.5" strokeWidth={2.5} />
              </button>
            )}
          </div>
        </div>

        <p className="text-xs text-fg-subtle text-center mt-4">
          You can change all of this anytime in <span className="text-fg-muted">Identity</span> and{" "}
          <span className="text-fg-muted">Goals</span>.
        </p>
      </div>
    </main>
  );
}

function Step1({
  name,
  setName,
  communication,
  setCommunication,
}: {
  name: string;
  setName: (v: string) => void;
  communication: string;
  setCommunication: (v: string) => void;
}) {
  return (
    <>
      <h2 className="text-xl font-semibold text-fg mb-1 tracking-tighter">Hi. Who are you?</h2>
      <p className="text-sm text-fg-muted mb-5">
        I&apos;ll use this to know how to talk to you. Both fields optional.
      </p>

      <label className="block mb-4">
        <span className="text-sm font-medium text-fg">What should I call you?</span>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Syahid"
          className={inputCls}
          autoFocus
        />
      </label>

      <label className="block">
        <span className="text-sm font-medium text-fg">How should I communicate with you?</span>
        <span className="block text-xs text-fg-muted mt-0.5">
          Tone, style, anything that matters
        </span>
        <input
          type="text"
          value={communication}
          onChange={(e) => setCommunication(e.target.value)}
          placeholder="Warm but direct. Don't soften hard truths."
          className={inputCls}
        />
      </label>
    </>
  );
}

function Step2({
  narrative,
  setNarrative,
}: {
  narrative: string;
  setNarrative: (v: string) => void;
}) {
  return (
    <>
      <h2 className="text-xl font-semibold text-fg mb-1 tracking-tighter">
        Tell me a bit about your life right now.
      </h2>
      <p className="text-sm text-fg-muted mb-5">
        A few sentences. Work, relationships, what you&apos;re focused on. I&apos;ll reference
        this to stay grounded.
      </p>

      <label className="block">
        <textarea
          value={narrative}
          onChange={(e) => setNarrative(e.target.value)}
          rows={6}
          placeholder="I'm a founder in Jakarta building an AI assistant. I tend to be most clear-headed in the morning. Lately I've been working too late and not exercising enough — trying to fix that."
          className={cn(inputCls, "resize-none")}
          autoFocus
        />
      </label>
    </>
  );
}

function Step3({
  title,
  setTitle,
  horizon,
  setHorizon,
}: {
  title: string;
  setTitle: (v: string) => void;
  horizon: "week" | "month" | "quarter" | "year";
  setHorizon: (v: "week" | "month" | "quarter" | "year") => void;
}) {
  return (
    <>
      <h2 className="text-xl font-semibold text-fg mb-1 tracking-tighter">
        One thing you&apos;re working toward?
      </h2>
      <p className="text-sm text-fg-muted mb-5">
        Optional — but if you have one in mind, I&apos;ll remember it. You can add more
        anytime.
      </p>

      <label className="block mb-4">
        <span className="text-sm font-medium text-fg">Goal</span>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Ship the assistant by end of quarter"
          className={inputCls}
          autoFocus
        />
      </label>

      <div>
        <span className="text-sm font-medium text-fg block mb-2">By when?</span>
        <div className="grid grid-cols-4 gap-2">
          {(["week", "month", "quarter", "year"] as const).map((h) => (
            <button
              key={h}
              type="button"
              onClick={() => setHorizon(h)}
              className={cn(
                "px-3 py-2 rounded-lg text-xs font-medium border transition-all",
                horizon === h
                  ? "bg-accent text-on-accent border-accent"
                  : "bg-bg/40 border-border-strong text-fg-soft hover:border-accent/40",
              )}
            >
              {h}
            </button>
          ))}
        </div>
      </div>
    </>
  );
}

const inputCls =
  "mt-1.5 w-full rounded-xl border border-border-strong bg-bg/40 backdrop-blur-sm px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all";
