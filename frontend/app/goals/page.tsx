"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Check, Pause, Plus, Target, Trash2, X } from "lucide-react";
import {
  type Goal,
  type GoalInput,
  createGoal,
  deleteGoal,
  listGoals,
  updateGoalStatus,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { BackToChatButton } from "@/components/settings/back-to-chat-button";
import { AppHeaderAction, AppPageShell, AppPanel, AppToolbar } from "@/components/ui/app-page-shell";

const HORIZONS: Goal["horizon"][] = ["week", "month", "quarter", "year", "multi_year", "life"];
const HORIZON_LABELS: Record<Goal["horizon"], string> = {
  week: "This week",
  month: "This month",
  quarter: "This quarter",
  year: "This year",
  multi_year: "Multi-year",
  life: "Lifetime",
};

const STATUS_LABELS: Record<Goal["status"] | "all", string> = {
  active: "Active",
  paused: "Paused",
  achieved: "Done",
  abandoned: "Dropped",
  all: "All",
};

export default function GoalsPage() {
  const [goals, setGoals] = useState<Goal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<Goal["status"] | "all">("active");
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // form state
  const [title, setGoal] = useState("");
  const [description, setDescription] = useState("");
  const [horizon, setTimeline] = useState<Goal["horizon"]>("quarter");
  const [weight, setWeight] = useState(5);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listGoals(filter)
      .then((data) => !cancelled && setGoals(data))
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [filter]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const input: GoalInput = {
        title: title.trim(),
        description: description.trim() || null,
        horizon,
        emotional_weight: weight,
      };
      const created = await createGoal(input);
      setGoals((prev) => [created, ...prev]);
      setGoal("");
      setDescription("");
      setShowForm(false);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleStatus(id: string, status: Goal["status"]) {
    const prev = goals;
    setGoals((g) => g.map((x) => (x.id === id ? { ...x, status } : x)));
    try {
      await updateGoalStatus(id, status);
      if (filter !== "all" && status !== filter) {
        setGoals((g) => g.filter((x) => x.id !== id));
      }
    } catch (e) {
      setGoals(prev);
      setError(String(e));
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this goal? This cannot be undone.")) return;
    const prev = goals;
    setGoals((g) => g.filter((x) => x.id !== id));
    try {
      await deleteGoal(id);
    } catch (e) {
      setGoals(prev);
      setError(String(e));
    }
  }

  return (
    <AppPageShell
      eyebrow="Aliyya Goals"
      title="Goals"
      description="Tell Aliyya what you are working toward, so she can help you make better plans and decisions."
      maxWidthClassName="max-w-5xl"
      actions={
        <>
          <AppHeaderAction href="/chat">Back to chat</AppHeaderAction>
          <AppHeaderAction
            onClick={() => setShowForm((v) => !v)}
            variant="primary"
            icon={showForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
          >
            {showForm ? "Close" : "Add goal"}
          </AppHeaderAction>
        </>
      }
    >
      <AppToolbar>
        <div className="flex w-full gap-1 overflow-x-auto rounded-full border border-slate-200/70 bg-white/65 p-1 dark:border-white/10 dark:bg-black/20 md:w-auto">
          {(["active", "paused", "achieved", "abandoned", "all"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={cn(
                "whitespace-nowrap rounded-full px-3 py-2 text-xs font-medium transition-colors",
                filter === s
                  ? "bg-slate-950 text-white dark:bg-white dark:text-slate-950"
                  : "text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white",
              )}
            >
              {STATUS_LABELS[s]}
            </button>
          ))}
        </div>
      </AppToolbar>

      {showForm && (
        <form onSubmit={handleCreate} className="rounded-[1.5rem] border border-slate-200/70 bg-white/75 p-5 shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.04]">
          <label className="mb-4 block">
            <span className="text-sm font-medium text-slate-900 dark:text-white">Goal</span>
            <input
              type="text"
              required
              value={title}
              onChange={(e) => setGoal(e.target.value)}
              placeholder="Get back in shape"
              className={inputCls}
            />
          </label>

          <label className="mb-4 block">
            <span className="text-sm font-medium text-slate-900 dark:text-white">Why this matters</span>
            <textarea
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Energy for the long haul, not aesthetics"
              className={cn(inputCls, "resize-none")}
            />
          </label>

          <div className="mb-4 grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium text-slate-900 dark:text-white">Timeline</span>
              <select
                value={horizon}
                onChange={(e) => setTimeline(e.target.value as Goal["horizon"])}
                className={inputCls}
              >
                {HORIZONS.map((h) => (
                  <option key={h} value={h}>
                    {HORIZON_LABELS[h]}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-sm font-medium text-slate-900 dark:text-white">
                How important is this? ({weight})
              </span>
              <input
                type="range"
                min={1}
                max={10}
                value={weight}
                onChange={(e) => setWeight(Number(e.target.value))}
                className="mt-3 w-full accent-cyan-400"
              />
            </label>
          </div>

          <div className="flex flex-col gap-2 border-t border-slate-200/70 pt-4 dark:border-white/10 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="min-h-10 rounded-full border border-slate-200/70 px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-white/10"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !title.trim()}
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-full bg-cyan-400 px-4 py-2 text-sm font-medium text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Save goal"}
            </button>
          </div>
        </form>
      )}

      {error && (
        <div className="rounded-2xl border border-red-400/40 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-100">
          {error}
        </div>
      )}

      {loading ? (
        <AppPanel>
          <div className="p-6 text-sm text-slate-600 dark:text-zinc-300">Loading…</div>
        </AppPanel>
      ) : goals.length === 0 ? (
        <AppPanel>
          <div className="py-12 text-center">
            <Target className="mx-auto mb-2 h-6 w-6 text-slate-400 opacity-70 dark:text-zinc-500" />
            <p className="text-sm text-slate-500 dark:text-zinc-400">
              No {filter !== "all" ? filter : ""} goals.
            </p>
          </div>
        </AppPanel>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {goals.map((g) => (
            <article key={g.id} className="group rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-lg shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-black/20">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="break-words text-sm font-semibold text-slate-950 dark:text-white">{g.title}</p>
                  {g.description && (
                    <p className="mt-1 text-xs leading-5 text-slate-600 dark:text-zinc-400">{g.description}</p>
                  )}
                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-zinc-400">
                    <span className="rounded-full border border-cyan-500/20 bg-cyan-50 px-2 py-1 text-[10px] font-medium text-cyan-800 dark:border-cyan-300/20 dark:bg-cyan-300/10 dark:text-cyan-100">
                      {HORIZON_LABELS[g.horizon]}
                    </span>
                    <span>weight {g.emotional_weight}/10</span>
                    {g.status !== "active" && <span>· {STATUS_LABELS[g.status]}</span>}
                  </div>
                </div>

                <div className="flex shrink-0 items-center gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
                  {g.status === "active" && (
                    <>
                      <button
                        onClick={() => handleStatus(g.id, "achieved")}
                        aria-label="Mark done"
                        className="rounded-full border border-slate-200/70 p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:border-white/10 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white"
                      >
                        <Check className="h-3.5 w-3.5" />
                      </button>
                      <button
                        onClick={() => handleStatus(g.id, "paused")}
                        aria-label="Pause"
                        className="rounded-full border border-slate-200/70 p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:border-white/10 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white"
                      >
                        <Pause className="h-3.5 w-3.5" />
                      </button>
                    </>
                  )}
                  {g.status === "paused" && (
                    <button
                      onClick={() => handleStatus(g.id, "active")}
                      className="rounded-full border border-slate-200/70 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-100 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-white/10"
                    >
                      Resume
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(g.id)}
                    aria-label="Delete"
                    className="rounded-full border border-red-400/40 p-2 text-red-700 hover:bg-red-50 dark:border-red-400/30 dark:text-red-200 dark:hover:bg-red-500/10"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </AppPageShell>
  );
}

const inputCls =
  "mt-1.5 w-full rounded-xl border border-border-strong bg-bg/40 backdrop-blur-sm px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all";

function IconBtn({
  onClick,
  icon,
  label,
  danger,
}: {
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  danger?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      className={cn(
        "h-7 w-7 grid place-items-center rounded-md transition-colors",
        danger
          ? "text-fg-subtle hover:text-danger hover:bg-danger-soft"
          : "text-fg-muted hover:text-fg hover:bg-fg/5",
      )}
    >
      {icon}
    </button>
  );
}
