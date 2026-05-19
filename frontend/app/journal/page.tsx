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
import { AppHeaderAction, AppPageShell, AppPanel } from "@/components/ui/app-page-shell";
import { useUserOwnedLabel } from "@/hooks/use-identity-owned-label";
import { BackToChatButton } from "@/components/settings/back-to-chat-button";

type Scale = { value: number | null; set: (n: number | null) => void };

export default function JournalPage() {
  const journalEyebrow = useUserOwnedLabel("Journal");
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
    <AppPageShell
      eyebrow={journalEyebrow}
      title="How are you today?"
      description={
        todayEntry
          ? "You already checked in today — you can update if anything has shifted."
          : "A quick check-in. Skip what you don't want to answer."
      }
      maxWidthClassName="max-w-4xl"
      actions={<BackToChatButton />}
    >
      {loading ? (
        <AppPanel>
          <div className="p-6 text-sm text-slate-600 dark:text-zinc-300">
            Loading…
          </div>
        </AppPanel>
      ) : (
        <form onSubmit={handleSave} className="rounded-[1.5rem] border border-slate-200/70 bg-white/75 p-5 shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.04] sm:p-6">
          <div className="space-y-6">
            <ScaleRow label="Mood" hint="how you feel overall" scale={{ value: mood, set: setMood }} />
            <ScaleRow label="Energy" hint="physical and mental" scale={{ value: energy, set: setEnergy }} />
            <ScaleRow label="Stress" hint="tension you're carrying" scale={{ value: stress, set: setStress }} />

            <div>
              <label className="block">
                <span className="text-sm font-medium text-slate-900 dark:text-white">A few sentences</span>
                <span className="mt-0.5 block text-xs text-slate-500 dark:text-zinc-400">
                  What&apos;s going on? Anything worth remembering?
                </span>
                <textarea
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  rows={4}
                  placeholder="Long meeting with the team about the launch. Felt clearer after lunch…"
                  className="mt-2 w-full resize-none rounded-2xl border border-slate-200/70 bg-white/80 px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition-all placeholder:text-slate-400 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"
                />
              </label>
            </div>

            {error && <p className="text-sm text-red-700 dark:text-red-300">{error}</p>}

            <div className="flex flex-col gap-3 border-t border-slate-200/70 pt-4 dark:border-white/10 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs text-slate-500 dark:text-zinc-500">
                {todayEntry
                  ? `Last saved ${new Date(todayEntry.observed_at).toLocaleTimeString()}`
                  : "Not saved yet"}
              </p>
              <button
                type="submit"
                disabled={saving}
                className="inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-full bg-cyan-400 px-4 py-2 text-sm font-medium text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300 disabled:opacity-50 active:scale-[0.98] sm:w-auto"
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
          </div>
        </form>
      )}

      {history.length > 1 && (
        <AppPanel>
          <div className="border-b border-slate-200/70 px-5 py-4 dark:border-white/10">
            <h2 className="text-lg font-semibold tracking-tight text-slate-950 dark:text-white">
              Recent
            </h2>
          </div>
          <ul className="divide-y divide-slate-200/70 dark:divide-white/10">
            {history.slice(1, 8).map((h) => (
              <li key={h.id} className="p-4">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                  <span className="text-xs text-slate-500 dark:text-zinc-400">
                    {new Date(h.observed_at).toLocaleDateString(undefined, {
                      weekday: "short",
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-zinc-400">
                    {h.mood != null && <Pill label="mood" value={h.mood} />}
                    {h.energy != null && <Pill label="energy" value={h.energy} />}
                    {h.stress != null && <Pill label="stress" value={h.stress} />}
                  </div>
                </div>
                {h.note && <p className="mt-2 text-sm leading-6 text-slate-700 dark:text-zinc-300">{h.note}</p>}
              </li>
            ))}
          </ul>
        </AppPanel>
      )}
    </AppPageShell>
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
