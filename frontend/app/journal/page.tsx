"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, Save } from "lucide-react";
import {
  type JournalEntry,
  getRecentJournal,
  getTodaysJournal,
  postJournal,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type Scale = { value: number | null; set: (n: number | null) => void };

export default function JournalPage() {
  const [todayEntry, setTodayEntry] = useState<JournalEntry | null>(null);
  const [history, setHistory] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const [mood, setMood] = useState<number | null>(null);
  const [energy, setEnergy] = useState<number | null>(null);
  const [stress, setStress] = useState<number | null>(null);
  const [note, setNote] = useState("");

  const [saving, setSaving] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getTodaysJournal(), getRecentJournal()])
      .then(([today, recent]) => {
        if (cancelled) return;
        setTodayEntry(today.entry);
        setHistory(recent);
        if (today.entry) {
          setMood(today.entry.mood);
          setEnergy(today.entry.energy);
          setStress(today.entry.stress);
          setNote(today.entry.note ?? "");
        }
      })
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (mood == null && energy == null && stress == null && !note.trim()) {
      setError("Add at least one rating or a note.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const saved = await postJournal({
        mood,
        energy,
        stress,
        note: note.trim() || null,
      });
      setTodayEntry(saved);
      const recent = await getRecentJournal();
      setHistory(recent);
      setJustSaved(true);
      setTimeout(() => setJustSaved(false), 2000);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="min-h-dvh">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-5 sm:py-8 fade-up">
        <Link
          href="/chat"
          className="inline-flex items-center gap-1.5 text-sm text-fg-muted hover:text-fg mb-6 transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to chat
        </Link>

        <h1 className="text-3xl font-semibold text-fg mb-1 tracking-tighter">
          How are you today?
        </h1>
        <p className="text-base text-fg-muted mb-8">
          {todayEntry
            ? "You already checked in today — you can update if anything has shifted."
            : "A quick check-in. Skip what you don't want to answer."}
        </p>

        {loading ? (
          <p className="text-sm text-fg-muted">Loading…</p>
        ) : (
          <form onSubmit={handleSave} className="glass rounded-2xl p-6 space-y-6">
            <ScaleRow label="Mood" hint="how you feel overall" scale={{ value: mood, set: setMood }} />
            <ScaleRow label="Energy" hint="physical and mental" scale={{ value: energy, set: setEnergy }} />
            <ScaleRow label="Stress" hint="tension you're carrying" scale={{ value: stress, set: setStress }} />

            <div>
              <label className="block">
                <span className="text-sm font-medium text-fg">A few sentences</span>
                <span className="block text-xs text-fg-muted mt-0.5">
                  What's going on? Anything worth remembering?
                </span>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={4}
                  placeholder="Long meeting with the team about the launch. Felt clearer after lunch…"
                  className="mt-2 w-full resize-none rounded-xl border border-border-strong bg-bg/40 backdrop-blur-sm px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all"
                />
              </label>
            </div>

            {error && <p className="text-sm text-danger">{error}</p>}

            <div className="flex items-center justify-between pt-1 border-t border-border">
              <p className="text-xs text-fg-subtle">
                {todayEntry
                  ? `Last saved ${new Date(todayEntry.observed_at).toLocaleTimeString()}`
                  : "Not saved yet"}
              </p>
              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center gap-1.5 rounded-xl bg-accent text-on-accent px-4 py-2 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-all active:scale-[0.98] shadow-md shadow-accent/25"
              >
                {justSaved ? (
                  <>
                    <Check className="h-3.5 w-3.5" strokeWidth={2.5} />
                    Saved
                  </>
                ) : (
                  <>
                    <Save className="h-3.5 w-3.5" strokeWidth={2.5} />
                    {saving ? "Saving…" : todayEntry ? "Update" : "Save"}
                  </>
                )}
              </button>
            </div>
          </form>
        )}

        {history.length > 1 && (
          <div className="mt-10">
            <h2 className="text-lg font-semibold text-fg mb-3 tracking-tighter">Recent</h2>
            <ul className="space-y-2">
              {history.slice(1, 8).map((h) => (
                <li key={h.id} className="glass rounded-xl p-3.5">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-fg-muted">
                      {new Date(h.observed_at).toLocaleDateString(undefined, {
                        weekday: "short",
                        month: "short",
                        day: "numeric",
                      })}
                    </span>
                    <div className="flex items-center gap-3 text-xs text-fg-muted">
                      {h.mood != null && <Pill label="mood" value={h.mood} />}
                      {h.energy != null && <Pill label="energy" value={h.energy} />}
                      {h.stress != null && <Pill label="stress" value={h.stress} />}
                    </div>
                  </div>
                  {h.note && <p className="text-sm text-fg-soft mt-1">{h.note}</p>}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </main>
  );
}

function ScaleRow({
  label,
  hint,
  scale,
}: {
  label: string;
  hint: string;
  scale: Scale;
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <div>
          <span className="text-sm font-medium text-fg">{label}</span>
          <span className="text-xs text-fg-muted ml-2">{hint}</span>
        </div>
        <span className="text-sm tabular-nums text-fg-muted">
          {scale.value == null ? "—" : scale.value > 0 ? `+${scale.value}` : scale.value}
        </span>
      </div>
      <div className="grid grid-cols-11 gap-1">
        {Array.from({ length: 11 }, (_, i) => i - 5).map((n) => (
          <button
            key={n}
            type="button"
            onClick={() => scale.set(scale.value === n ? null : n)}
            className={cn(
              "h-9 rounded-lg text-xs font-medium tabular-nums transition-all border",
              scale.value === n
                ? "bg-accent text-on-accent border-accent shadow-md shadow-accent/25"
                : "bg-bg/40 border-border-strong text-fg-soft hover:bg-bg/70 hover:border-accent/40",
            )}
            aria-label={`${label} ${n}`}
          >
            {n > 0 ? `+${n}` : n}
          </button>
        ))}
      </div>
    </div>
  );
}

function Pill({ label, value }: { label: string; value: number }) {
  return (
    <span className="inline-flex items-baseline gap-1">
      <span className="text-fg-subtle">{label}</span>
      <span className="text-fg tabular-nums">{value > 0 ? `+${value}` : value}</span>
    </span>
  );
}
